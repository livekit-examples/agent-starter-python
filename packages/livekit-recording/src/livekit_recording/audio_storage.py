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

    This implementation subscribes to audio tracks in the room and
    saves them to the local filesystem.
    """

    # Audio configuration
    SAMPLE_RATE = 48000
    NUM_CHANNELS = 1
    SAMPLE_WIDTH = 2  # 16-bit audio

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
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._room = room
        self._recording_id: str | None = None
        self._session_id: str | None = None
        self._room_name: str | None = None
        self._audio_frames: list[bytes] = []
        self._recording_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._start_time: datetime | None = None
        self._output_path: Path | None = None
        self._audio_streams: list[rtc.AudioStream] = []

        logger.debug(f"LocalAudioRecorder initialized with output_dir={output_dir}")

    def set_room(self, room: rtc.Room) -> None:
        """Set the LiveKit room to record from.

        Args:
            room: LiveKit room instance
        """
        self._room = room

    @property
    def recording_id(self) -> str | None:
        """Get the current recording ID if recording is active."""
        return self._recording_id

    async def start_recording(
        self, room_name: str, session_id: str | None = None
    ) -> str | None:
        """Start recording audio from all tracks in the room.

        Args:
            room_name: Name of the LiveKit room
            session_id: Unique session identifier for the filename

        Returns:
            Recording ID if started successfully, None on failure
        """
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
            self._audio_frames = []
            self._start_time = datetime.now(UTC)
            self._stop_event = asyncio.Event()

            # Build output path
            filename = f"{room_name}-{self._session_id}.wav"
            self._output_path = self.output_dir / "audio" / filename
            self._output_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info(
                f"Starting local audio recording for room {room_name}, "
                f"recording_id={self._recording_id}, "
                f"output_path={self._output_path}"
            )

            # Start background task to capture audio
            self._recording_task = asyncio.create_task(self._capture_audio())

            return self._recording_id

        except Exception as e:
            logger.error(f"Failed to start local audio recording: {e}")
            self._recording_id = None
            return None

    async def _capture_audio(self) -> None:
        """Background task to capture audio from all tracks."""
        if self._room is None or self._stop_event is None:
            return

        try:
            # Subscribe to existing audio tracks
            for participant in self._room.remote_participants.values():
                for publication in participant.track_publications.values():
                    if (
                        publication.track
                        and publication.kind == rtc.TrackKind.KIND_AUDIO
                    ):
                        await self._subscribe_to_track(publication.track)

            # Set up listener for new tracks
            @self._room.on("track_subscribed")
            def on_track_subscribed(
                track: rtc.Track,
                publication: rtc.RemoteTrackPublication,
                participant: rtc.RemoteParticipant,
            ):
                if track.kind == rtc.TrackKind.KIND_AUDIO:
                    _task = asyncio.create_task(self._subscribe_to_track(track))  # noqa: RUF006

            # Wait for stop signal
            await self._stop_event.wait()

        except asyncio.CancelledError:
            logger.debug("Audio capture task cancelled")
        except Exception as e:
            logger.error(f"Error in audio capture: {e}")

    async def _subscribe_to_track(self, track: rtc.Track) -> None:
        """Subscribe to an audio track and capture frames."""
        if self._stop_event is None:
            return

        try:
            audio_stream = rtc.AudioStream(
                track,
                sample_rate=self.SAMPLE_RATE,
                num_channels=self.NUM_CHANNELS,
            )
            self._audio_streams.append(audio_stream)

            logger.debug(f"Subscribed to audio track: {track.sid}")

            async for frame_event in audio_stream:
                if self._stop_event.is_set():
                    break
                # Capture raw audio data
                frame = frame_event.frame
                self._audio_frames.append(bytes(frame.data))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error capturing audio from track: {e}")

    async def stop_recording(self) -> AudioFileInfo | None:
        """Stop recording and save to WAV file.

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

            # Write WAV file
            if self._output_path and self._audio_frames:
                file_info = await self._write_wav_file()
                logger.info(
                    f"Local audio recording saved: "
                    f"location={file_info.location}, "
                    f"duration={file_info.duration}ns, "
                    f"size={file_info.size} bytes"
                )
                return file_info
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
            self._audio_frames = []

    async def _write_wav_file(self) -> AudioFileInfo:
        """Write captured audio frames to a WAV file."""
        if not self._output_path:
            raise ValueError("No output path set")

        # Calculate duration
        total_samples = sum(
            len(frame) // self.SAMPLE_WIDTH for frame in self._audio_frames
        )
        duration_seconds = total_samples / self.SAMPLE_RATE
        duration_ns = int(duration_seconds * 1_000_000_000)

        # Write WAV file
        with wave.open(str(self._output_path), "wb") as wav_file:
            wav_file.setnchannels(self.NUM_CHANNELS)
            wav_file.setsampwidth(self.SAMPLE_WIDTH)
            wav_file.setframerate(self.SAMPLE_RATE)

            for frame_data in self._audio_frames:
                wav_file.writeframes(frame_data)

        # Get file size
        file_size = self._output_path.stat().st_size

        return AudioFileInfo(
            filename=self._output_path.name,
            location=str(self._output_path.absolute()),
            duration=duration_ns,
            size=file_size,
        )

    async def close(self) -> None:
        """Clean up resources."""
        if self._recording_id:
            await self.stop_recording()

        for stream in self._audio_streams:
            await stream.aclose()
        self._audio_streams = []
