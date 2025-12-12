"""Audio storage protocol and implementations for recording audio to various backends."""

from __future__ import annotations

import asyncio
import contextlib
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from livekit import rtc
from loguru import logger

if TYPE_CHECKING:
    pass


@dataclass
class AudioFileInfo:
    """Information about a recorded audio file."""

    filename: str
    location: str
    duration: int  # Duration in nanoseconds
    size: int  # Size in bytes

    # Optional second file info for dual-track recordings
    agent_filename: str | None = None
    agent_location: str | None = None
    agent_duration: int | None = None
    agent_size: int | None = None


class AudioRecorderProtocol(Protocol):
    """Protocol for audio recording implementations.

    Implementations can record audio from LiveKit rooms and store them
    to various backends (local files, S3, etc.).
    """

    async def start_recording(
        self, room_name: str, session_id: str | None = None
    ) -> str | None:
        """Start recording audio for a room.

        Args:
            room_name: Name of the LiveKit room to record
            session_id: Unique session identifier for matching audio/transcript files

        Returns:
            Recording ID if started successfully, None on failure
        """
        ...

    async def stop_recording(self) -> AudioFileInfo | None:
        """Stop the active recording and finalize the output.

        Returns:
            AudioFileInfo with file details if successful, None on error
        """
        ...

    async def close(self) -> None:
        """Clean up resources."""
        ...


class LocalAudioRecorder:
    """Records audio from LiveKit room to local WAV files.

    This implementation subscribes to both agent and user audio tracks
    and saves them as separate mono WAV files:
    - {room}-{session}-user.wav: User audio (microphone input)
    - {room}-{session}-agent.wav: Agent audio (TTS output)
    """

    # Audio configuration - match LiveKit Agents defaults (24kHz for voice AI)
    SAMPLE_RATE = 24000
    NUM_CHANNELS = 1  # Mono for each file
    SAMPLE_WIDTH = 2  # 16-bit audio

    # Class-level counter for unique instance IDs
    _instance_counter: int = 0

    def __init__(
        self,
        output_dir: str | Path = "temp",
        room: rtc.Room | None = None,
    ):
        """Initialize the local audio recorder.

        Args:
            output_dir: Directory to save audio files (default: temp/)
            room: LiveKit room to record from (can be set later via set_room)
        """
        # Assign unique instance ID to prevent handler cross-talk between sessions
        LocalAudioRecorder._instance_counter += 1
        self._instance_id = LocalAudioRecorder._instance_counter

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._room: rtc.Room | None = None
        self._recording_id: str | None = None
        self._session_id: str | None = None
        self._room_name: str | None = None
        self._recording_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._start_time: datetime | None = None
        self._user_output_path: Path | None = None
        self._agent_output_path: Path | None = None
        self._audio_streams: list[rtc.AudioStream] = []
        self._handlers_registered: bool = False
        self._closed: bool = False  # Flag to ignore events after close

        # Separate frame buffers for agent and user
        self._agent_frames: list[bytes] = []
        self._user_frames: list[bytes] = []
        self._frame_lock = asyncio.Lock()

        # Pending tracks that are subscribed before recording starts
        self._pending_user_tracks: list[rtc.Track] = []
        self._pending_agent_tracks: list[rtc.Track] = []

        logger.debug(
            f"LocalAudioRecorder initialized with output_dir={output_dir}, "
            f"instance_id={self._instance_id}"
        )

        # Set room if provided
        if room:
            self.set_room(room)

    def set_room(self, room: rtc.Room) -> None:
        """Set the LiveKit room to record from and register event handlers.

        This registers track subscription handlers immediately so we don't miss
        any tracks that are subscribed before start_recording() is called.

        Args:
            room: LiveKit room instance
        """
        self._room = room

        if self._handlers_registered:
            return

        self._handlers_registered = True

        # Capture instance_id to check in handlers (prevents cross-talk between sessions)
        handler_instance_id = self._instance_id

        # Register handlers for future track subscriptions
        @room.on("track_subscribed")
        def on_track_subscribed(
            track: rtc.Track,
            publication: rtc.RemoteTrackPublication,
            participant: rtc.RemoteParticipant,
        ):
            # Ignore if this recorder is closed or if this is an old handler
            if self._closed or self._instance_id != handler_instance_id:
                return

            if track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info(
                    f"User audio track subscribed: {track.sid} "
                    f"(recorder instance={self._instance_id})"
                )
                if self._stop_event and not self._stop_event.is_set():
                    # Recording is active and not stopping, subscribe immediately
                    _task = asyncio.create_task(self._subscribe_to_track(track, "user"))  # noqa: RUF006
                elif not self._stop_event:
                    # Recording not started yet, queue the track
                    self._pending_user_tracks.append(track)
                    logger.debug(f"Queued user track for later: {track.sid}")

        @room.on("local_track_published")
        def on_local_track_published(
            publication: rtc.LocalTrackPublication,
            track: rtc.Track,
        ):
            # Ignore if this recorder is closed or if this is an old handler
            if self._closed or self._instance_id != handler_instance_id:
                return

            if track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info(
                    f"Agent audio track published: {track.sid} "
                    f"(recorder instance={self._instance_id})"
                )
                if self._stop_event and not self._stop_event.is_set():
                    # Recording is active and not stopping, subscribe immediately
                    _task = asyncio.create_task(
                        self._subscribe_to_track(track, "agent")
                    )  # noqa: RUF006
                elif not self._stop_event:
                    # Recording not started yet, queue the track
                    self._pending_agent_tracks.append(track)
                    logger.debug(f"Queued agent track for later: {track.sid}")

        logger.debug(
            f"Registered track subscription handlers on room "
            f"(instance={self._instance_id})"
        )

    @property
    def recording_id(self) -> str | None:
        """Get the current recording ID if recording is active."""
        return self._recording_id

    async def start_recording(
        self, room_name: str, session_id: str | None = None
    ) -> str | None:
        """Start recording separate audio files for agent and user.

        Args:
            room_name: Name of the LiveKit room
            session_id: Unique session identifier for the filename

        Returns:
            Recording ID if started successfully, None on failure
        """
        if self._closed:
            logger.error("Cannot start recording on a closed recorder")
            return None

        if self._recording_id:
            logger.warning(
                f"Recording already active with ID {self._recording_id}, skipping start"
            )
            return self._recording_id

        if self._room is None:
            logger.error("No room set for LocalAudioRecorder")
            return None

        try:
            self._room_name = room_name
            self._session_id = session_id or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            self._recording_id = f"LOCAL_{self._session_id}"

            # Clear all buffers and pending tracks to start fresh
            self._agent_frames = []
            self._user_frames = []
            self._pending_user_tracks.clear()
            self._pending_agent_tracks.clear()

            self._start_time = datetime.now(UTC)
            self._stop_event = asyncio.Event()

            # Build output paths for both files
            audio_dir = self.output_dir / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)

            self._user_output_path = (
                audio_dir / f"{room_name}-{self._session_id}-user.wav"
            )
            self._agent_output_path = (
                audio_dir / f"{room_name}-{self._session_id}-agent.wav"
            )

            logger.info(
                f"Starting dual-track local audio recording for room {room_name}, "
                f"recording_id={self._recording_id}, "
                f"user_file={self._user_output_path}, "
                f"agent_file={self._agent_output_path}"
            )

            # Start background task to capture audio
            self._recording_task = asyncio.create_task(self._capture_audio())

            return self._recording_id

        except Exception as e:
            logger.error(f"Failed to start local audio recording: {e}")
            self._recording_id = None
            return None

    async def _capture_audio(self) -> None:
        """Background task to capture audio from agent and user tracks."""
        if self._room is None or self._stop_event is None:
            return

        subscription_tasks: list[asyncio.Task] = []

        try:
            # First, subscribe to any tracks that were queued before recording started
            for track in self._pending_user_tracks:
                logger.info(f"Subscribing to queued user audio track: {track.sid}")
                task = asyncio.create_task(self._subscribe_to_track(track, "user"))
                subscription_tasks.append(task)
            self._pending_user_tracks.clear()

            for track in self._pending_agent_tracks:
                logger.info(f"Subscribing to queued agent audio track: {track.sid}")
                task = asyncio.create_task(self._subscribe_to_track(track, "agent"))
                subscription_tasks.append(task)
            self._pending_agent_tracks.clear()

            # Subscribe to local participant's audio tracks (agent)
            local_participant = self._room.local_participant
            if local_participant:
                for publication in local_participant.track_publications.values():
                    if (
                        publication.track
                        and publication.kind == rtc.TrackKind.KIND_AUDIO
                    ):
                        logger.info(
                            f"Subscribing to agent audio track: {publication.track.sid}"
                        )
                        task = asyncio.create_task(
                            self._subscribe_to_track(publication.track, "agent")
                        )
                        subscription_tasks.append(task)

            # Subscribe to remote participants' audio tracks (users)
            for participant in self._room.remote_participants.values():
                for publication in participant.track_publications.values():
                    if (
                        publication.track
                        and publication.kind == rtc.TrackKind.KIND_AUDIO
                    ):
                        logger.info(
                            f"Subscribing to user audio track: {publication.track.sid}"
                        )
                        task = asyncio.create_task(
                            self._subscribe_to_track(publication.track, "user")
                        )
                        subscription_tasks.append(task)

            # Event handlers are already registered in set_room(), no need to add here

            # Wait for stop signal
            await self._stop_event.wait()

        except asyncio.CancelledError:
            logger.debug("Audio capture task cancelled")
        except Exception as e:
            logger.error(f"Error in audio capture: {e}")
        finally:
            # Cancel any remaining subscription tasks
            for task in subscription_tasks:
                if not task.done():
                    task.cancel()

    async def _subscribe_to_track(self, track: rtc.Track, channel: str) -> None:
        """Subscribe to an audio track and capture frames.

        Args:
            track: The audio track to subscribe to
            channel: "agent" or "user" to identify the audio source
        """
        if self._stop_event is None or self._closed:
            return

        try:
            audio_stream = rtc.AudioStream(
                track,
                sample_rate=self.SAMPLE_RATE,
                num_channels=self.NUM_CHANNELS,
            )
            self._audio_streams.append(audio_stream)

            logger.debug(
                f"Subscribed to {channel} audio track: {track.sid} "
                f"(recorder instance={self._instance_id})"
            )

            async for frame_event in audio_stream:
                # Stop if recording ended or recorder is closed
                if self._stop_event.is_set() or self._closed:
                    break

                # Capture raw audio data
                frame_data = bytes(frame_event.frame.data)

                # Add to appropriate buffer
                async with self._frame_lock:
                    if channel == "agent":
                        self._agent_frames.append(frame_data)
                    else:
                        self._user_frames.append(frame_data)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error capturing audio from {channel} track: {e}")

    async def stop_recording(self) -> AudioFileInfo | None:
        """Stop recording and save to separate WAV files for agent and user.

        Returns:
            AudioFileInfo with file details if successful, None on error
        """
        if not self._recording_id:
            logger.debug("No active recording to stop")
            return None

        recording_id = self._recording_id
        try:
            logger.info(f"Stopping local audio recording, recording_id={recording_id}")

            # Signal stop to capture task
            if self._stop_event:
                self._stop_event.set()

            # Wait for capture task to finish
            if self._recording_task:
                self._recording_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._recording_task

            # Close audio streams
            for stream in self._audio_streams:
                await stream.aclose()
            self._audio_streams = []

            # Write WAV files
            user_info = None
            agent_info = None

            if self._user_output_path and self._user_frames:
                user_info = await self._write_wav_file(
                    self._user_output_path, self._user_frames
                )
                logger.info(
                    f"User audio recording saved: "
                    f"location={user_info['location']}, "
                    f"duration={user_info['duration']}ns, "
                    f"size={user_info['size']} bytes"
                )
            else:
                logger.warning(
                    f"No user audio frames captured for recording_id={recording_id}"
                )

            if self._agent_output_path and self._agent_frames:
                agent_info = await self._write_wav_file(
                    self._agent_output_path, self._agent_frames
                )
                logger.info(
                    f"Agent audio recording saved: "
                    f"location={agent_info['location']}, "
                    f"duration={agent_info['duration']}ns, "
                    f"size={agent_info['size']} bytes"
                )
            else:
                logger.warning(
                    f"No agent audio frames captured for recording_id={recording_id}"
                )

            # Return combined info (user as primary, agent as secondary)
            if user_info or agent_info:
                # Use user info as primary if available, else agent
                primary = user_info or agent_info
                return AudioFileInfo(
                    filename=primary["filename"],
                    location=primary["location"],
                    duration=primary["duration"],
                    size=primary["size"],
                    agent_filename=agent_info["filename"] if agent_info else None,
                    agent_location=agent_info["location"] if agent_info else None,
                    agent_duration=agent_info["duration"] if agent_info else None,
                    agent_size=agent_info["size"] if agent_info else None,
                )
            else:
                logger.warning(
                    f"No audio frames captured for recording_id={recording_id}"
                )
                return None

        except Exception as e:
            logger.error(f"Failed to stop local audio recording: {e}")
            return None
        finally:
            self._recording_id = None
            self._recording_task = None
            self._stop_event = None
            self._agent_frames = []
            self._user_frames = []

    async def _write_wav_file(self, output_path: Path, frames: list[bytes]) -> dict:
        """Write captured audio frames to a WAV file.

        Args:
            output_path: Path to write the WAV file
            frames: List of audio frame data

        Returns:
            Dictionary with filename, location, duration, and size
        """
        # Calculate duration
        total_samples = sum(len(frame) // self.SAMPLE_WIDTH for frame in frames)
        duration_seconds = total_samples / self.SAMPLE_RATE
        duration_ns = int(duration_seconds * 1_000_000_000)

        # Write WAV file
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(self.NUM_CHANNELS)
            wav_file.setsampwidth(self.SAMPLE_WIDTH)
            wav_file.setframerate(self.SAMPLE_RATE)

            for frame_data in frames:
                wav_file.writeframes(frame_data)

        # Get file size
        file_size = output_path.stat().st_size

        return {
            "filename": output_path.name,
            "location": str(output_path.absolute()),
            "duration": duration_ns,
            "size": file_size,
        }

    async def close(self) -> None:
        """Clean up resources and mark recorder as closed."""
        logger.debug(f"Closing LocalAudioRecorder instance={self._instance_id}")

        # Mark as closed first to prevent any new track subscriptions
        self._closed = True

        if self._recording_id:
            await self.stop_recording()

        for stream in self._audio_streams:
            await stream.aclose()
        self._audio_streams = []

        # Clear all pending state
        self._pending_user_tracks.clear()
        self._pending_agent_tracks.clear()
        self._agent_frames = []
        self._user_frames = []

        logger.debug(f"LocalAudioRecorder instance={self._instance_id} closed")
