"""S3 audio recorder using LiveKit egress for recording audio to S3."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from livekit import api
from livekit.protocol import egress as egress_proto
from loguru import logger

from livekit_recording.audio_storage import AudioFileInfo

if TYPE_CHECKING:
    from livekit_recording.settings import Settings

# Backward compatibility alias
EgressFileInfo = AudioFileInfo


class EgressConfig:
    """Configuration for S3 egress recordings."""

    def __init__(
        self,
        s3_bucket: str,
        s3_prefix: str = "",
        aws_access_key: str = "",
        aws_secret_key: str = "",
        aws_region: str = "us-east-1",
        livekit_url: str = "",
        livekit_api_key: str = "",
        livekit_api_secret: str = "",
    ):
        """Initialize egress configuration.

        Args:
            s3_bucket: S3 bucket name for recordings
            s3_prefix: Prefix/path within the bucket
            aws_access_key: AWS access key
            aws_secret_key: AWS secret key
            aws_region: AWS region
            livekit_url: LiveKit server URL
            livekit_api_key: LiveKit API key
            livekit_api_secret: LiveKit API secret
        """
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix.rstrip("/")
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.aws_region = aws_region
        self.livekit_url = livekit_url
        self.livekit_api_key = livekit_api_key
        self.livekit_api_secret = livekit_api_secret

    @classmethod
    def from_settings(
        cls, settings: Settings, bucket: str, prefix: str = ""
    ) -> EgressConfig:
        """Create EgressConfig from Settings object.

        Args:
            settings: Settings object with AWS and LiveKit credentials
            bucket: S3 bucket name for recordings
            prefix: Prefix/path within the bucket

        Returns:
            Configured EgressConfig instance
        """
        return cls(
            s3_bucket=bucket,
            s3_prefix=prefix,
            aws_access_key=settings.aws.access_key_id,
            aws_secret_key=settings.aws.secret_access_key,
            aws_region=settings.aws.region,
            livekit_url=settings.livekit.url,
            livekit_api_key=settings.livekit.api_key,
            livekit_api_secret=settings.livekit.api_secret,
        )


class S3AudioRecorder:
    """Records audio to S3 using LiveKit egress service.

    This implementation uses LiveKit Cloud's egress service to record
    room audio and upload directly to S3.

    Implements AudioRecorderProtocol.
    """

    def __init__(self, config: EgressConfig):
        """Initialize the S3 audio recorder.

        Args:
            config: Egress configuration
        """
        self.config = config
        self._api: api.LiveKitAPI | None = None
        self._egress_id: str | None = None
        self._expected_filepath: str | None = None
        logger.debug(
            f"S3AudioRecorder initialized with bucket={config.s3_bucket}, "
            f"region={config.aws_region}, prefix={config.s3_prefix}"
        )

    @property
    def livekit_api(self) -> api.LiveKitAPI:
        """Lazily initialize LiveKit API client."""
        if self._api is None:
            self._api = api.LiveKitAPI(
                url=self.config.livekit_url,
                api_key=self.config.livekit_api_key,
                api_secret=self.config.livekit_api_secret,
            )
        return self._api

    @property
    def egress_id(self) -> str | None:
        """Get the current egress ID if recording is active."""
        return self._egress_id

    @property
    def recording_id(self) -> str | None:
        """Get the current recording ID (alias for egress_id)."""
        return self._egress_id

    def _create_s3_upload(self) -> egress_proto.S3Upload:
        """Create S3 upload configuration."""
        logger.debug(
            f"Creating S3Upload with bucket={self.config.s3_bucket}, "
            f"region={self.config.aws_region}"
        )
        return egress_proto.S3Upload(
            access_key=self.config.aws_access_key,
            secret=self.config.aws_secret_key,
            bucket=self.config.s3_bucket,
            region=self.config.aws_region,
        )

    async def start_recording(
        self, room_name: str, session_id: str | None = None
    ) -> str | None:
        """Start audio recording for a room.

        This is the AudioRecorderProtocol-compliant method.

        Args:
            room_name: Name of the LiveKit room to record
            session_id: Unique session identifier for matching audio/transcript files

        Returns:
            Egress ID if started successfully, None on failure
        """
        return await self.start_dual_channel_recording(room_name, session_id)

    async def start_dual_channel_recording(
        self, room_name: str, session_id: str | None = None
    ) -> str | None:
        """Start audio recording for a room.

        Args:
            room_name: Name of the LiveKit room to record
            session_id: Unique session identifier for matching audio/transcript files

        Returns:
            Egress ID if started successfully, None on failure
        """
        if self._egress_id:
            logger.warning(
                f"Egress already active with ID {self._egress_id}, skipping start"
            )
            return self._egress_id

        try:
            s3_upload = self._create_s3_upload()

            # Build the filepath with prefix
            # Use session_id if provided for matching with transcript, otherwise use LiveKit's {time} placeholder
            filepath_prefix = (
                f"{self.config.s3_prefix}/audio" if self.config.s3_prefix else "audio"
            )
            if session_id:
                filepath = f"{filepath_prefix}/{room_name}-{session_id}.ogg"
            else:
                filepath = f"{filepath_prefix}/{{room_name}}-{{time}}.ogg"

            # Store expected filepath for logging
            self._expected_filepath = filepath
            expected_s3_path = f"s3://{self.config.s3_bucket}/{filepath}"
            logger.info(f"Expected audio file path: {expected_s3_path}")

            file_output = egress_proto.EncodedFileOutput(
                filepath=filepath,
                s3=s3_upload,
            )

            # Start room composite egress with audio recording
            # Using DEFAULT_MIXING (all users mixed together) for now
            # To enable dual-channel: audio_mixing=egress_proto.AudioMixing.DUAL_CHANNEL_AGENT
            info = await self.livekit_api.egress.start_room_composite_egress(
                egress_proto.RoomCompositeEgressRequest(
                    room_name=room_name,
                    audio_only=True,
                    file_outputs=[file_output],
                )
            )

            self._egress_id = info.egress_id
            logger.info(
                f"Started egress recording for room {room_name}, "
                f"egress_id={self._egress_id}, "
                f"expected_file={expected_s3_path}"
            )
            return self._egress_id

        except Exception as e:
            logger.error(f"Failed to start egress recording: {e}")
            return None

    async def stop_recording(self) -> AudioFileInfo | None:
        """Stop the active egress recording and wait for upload to complete.

        Returns:
            AudioFileInfo with file details if successful, None on error
        """
        if not self._egress_id:
            logger.debug("No active egress to stop")
            return None

        egress_id = self._egress_id
        try:
            logger.info(f"Stopping egress recording, egress_id={egress_id}...")
            await self.livekit_api.egress.stop_egress(
                egress_proto.StopEgressRequest(egress_id=egress_id)
            )
            logger.info(
                f"Stop request sent for egress_id={egress_id}, waiting for upload to complete..."
            )

            # Wait for the egress to complete and get file info
            file_info = await self._wait_for_completion(egress_id)
            self._egress_id = None
            self._expected_filepath = None
            return file_info

        except Exception as e:
            logger.error(f"Failed to stop egress recording: {e}")
            return None

    async def _wait_for_completion(
        self,
        egress_id: str,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
        file_results_timeout: float = 10.0,
    ) -> AudioFileInfo | None:
        """Wait for egress to complete and return file info.

        Args:
            egress_id: The egress ID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
            file_results_timeout: Additional time to wait for file_results after
                EGRESS_COMPLETE status (handles S3 upload delay on LiveKit Cloud)

        Returns:
            AudioFileInfo with file details if successful, None on error/timeout
        """
        start_time = asyncio.get_event_loop().time()
        last_status = None
        complete_time: float | None = None  # Track when EGRESS_COMPLETE was first seen

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                logger.error(
                    f"Timeout waiting for egress completion after {timeout}s, "
                    f"egress_id={egress_id}, last_status={last_status}"
                )
                return None

            try:
                # List egress by ID to get current status
                response = await self.livekit_api.egress.list_egress(
                    egress_proto.ListEgressRequest(egress_id=egress_id)
                )

                if not response.items:
                    logger.warning(f"Egress {egress_id} not found in list response")
                    await asyncio.sleep(poll_interval)
                    continue

                egress_info = response.items[0]
                status = egress_info.status
                last_status = egress_proto.EgressStatus.Name(status)

                logger.debug(
                    f"Egress status: {last_status}, egress_id={egress_id}, "
                    f"elapsed={elapsed:.1f}s"
                )

                # Check terminal states
                if status == egress_proto.EgressStatus.EGRESS_COMPLETE:
                    # Extract file info from results
                    if egress_info.file_results:
                        file_result = egress_info.file_results[0]
                        file_info = AudioFileInfo(
                            filename=file_result.filename,
                            location=file_result.location,
                            duration=file_result.duration,
                            size=file_result.size,
                        )
                        logger.info(
                            f"Egress completed successfully! "
                            f"File uploaded to: {file_info.location}, "
                            f"filename={file_info.filename}, "
                            f"duration={file_info.duration}ns, "
                            f"size={file_info.size} bytes"
                        )
                        return file_info
                    else:
                        # file_results may not be populated immediately on LiveKit Cloud
                        # Continue polling for a short time to allow S3 upload to complete
                        current_time = asyncio.get_event_loop().time()
                        if complete_time is None:
                            complete_time = current_time
                            logger.debug(
                                f"Egress completed but file_results not yet available, "
                                f"waiting up to {file_results_timeout}s for upload, "
                                f"egress_id={egress_id}"
                            )

                        time_since_complete = current_time - complete_time
                        if time_since_complete >= file_results_timeout:
                            logger.warning(
                                f"Egress completed but no file_results found after "
                                f"{file_results_timeout}s wait, egress_id={egress_id}"
                            )
                            return None

                        # Continue polling for file_results
                        await asyncio.sleep(poll_interval)
                        continue

                elif status == egress_proto.EgressStatus.EGRESS_FAILED:
                    error_msg = egress_info.error or "Unknown error"
                    logger.error(f"Egress failed: {error_msg}, egress_id={egress_id}")
                    return None

                elif status == egress_proto.EgressStatus.EGRESS_ABORTED:
                    logger.warning(f"Egress was aborted, egress_id={egress_id}")
                    return None

                elif status == egress_proto.EgressStatus.EGRESS_LIMIT_REACHED:
                    logger.warning(f"Egress limit reached, egress_id={egress_id}")
                    # Still try to get file info as partial recording may exist
                    if egress_info.file_results:
                        file_result = egress_info.file_results[0]
                        return AudioFileInfo(
                            filename=file_result.filename,
                            location=file_result.location,
                            duration=file_result.duration,
                            size=file_result.size,
                        )
                    return None

                # Still in progress, wait and poll again
                await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Error polling egress status: {e}")
                await asyncio.sleep(poll_interval)

    async def close(self) -> None:
        """Clean up resources."""
        if self._api:
            await self._api.aclose()
            self._api = None


# Backward compatibility aliases
EgressManager = S3AudioRecorder


def create_default_egress_manager() -> S3AudioRecorder:
    """Create an S3 audio recorder with default configuration.

    Returns:
        Configured S3AudioRecorder instance
    """
    config = EgressConfig(
        s3_bucket="audivi-audio-recordings",
        s3_prefix="livekit-demos",
    )
    return S3AudioRecorder(config)


def create_default_s3_recorder() -> S3AudioRecorder:
    """Create an S3 audio recorder with default configuration.

    Returns:
        Configured S3AudioRecorder instance
    """
    return create_default_egress_manager()
