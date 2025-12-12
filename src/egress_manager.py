"""Egress manager for recording dual-channel audio to S3."""

import asyncio
import os
from dataclasses import dataclass

from livekit import api
from livekit.protocol import egress as egress_proto
from loguru import logger


@dataclass
class EgressFileInfo:
    """Information about an uploaded egress file."""

    filename: str
    location: str
    duration: int
    size: int


class EgressConfig:
    """Configuration for egress recordings."""

    def __init__(
        self,
        s3_bucket: str,
        s3_prefix: str = "",
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_region: str | None = None,
        livekit_url: str | None = None,
        livekit_api_key: str | None = None,
        livekit_api_secret: str | None = None,
    ):
        """Initialize egress configuration.

        Args:
            s3_bucket: S3 bucket name for recordings
            s3_prefix: Prefix/path within the bucket
            aws_access_key: AWS access key (defaults to env var)
            aws_secret_key: AWS secret key (defaults to env var)
            aws_region: AWS region (defaults to env var or us-east-1)
            livekit_url: LiveKit server URL (defaults to env var)
            livekit_api_key: LiveKit API key (defaults to env var)
            livekit_api_secret: LiveKit API secret (defaults to env var)
        """
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix.rstrip("/")

        # AWS credentials
        self.aws_access_key = aws_access_key or os.environ.get("AWS_ACCESS_KEY_ID", "")
        self.aws_secret_key = aws_secret_key or os.environ.get(
            "AWS_SECRET_ACCESS_KEY", ""
        )
        self.aws_region = aws_region or os.environ.get("AWS_REGION", "us-east-1")

        # LiveKit credentials
        self.livekit_url = livekit_url or os.environ.get("LIVEKIT_URL", "")
        self.livekit_api_key = livekit_api_key or os.environ.get("LIVEKIT_API_KEY", "")
        self.livekit_api_secret = livekit_api_secret or os.environ.get(
            "LIVEKIT_API_SECRET", ""
        )


class EgressManager:
    """Manages LiveKit egress for dual-channel audio recording to S3."""

    def __init__(self, config: EgressConfig):
        """Initialize the egress manager.

        Args:
            config: Egress configuration
        """
        self.config = config
        self._api: api.LiveKitAPI | None = None
        self._egress_id: str | None = None
        self._expected_filepath: str | None = None

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

    def _create_s3_upload(self) -> egress_proto.S3Upload:
        """Create S3 upload configuration."""
        return egress_proto.S3Upload(
            access_key=self.config.aws_access_key,
            secret=self.config.aws_secret_key,
            bucket=self.config.s3_bucket,
            region=self.config.aws_region,
        )

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

    async def stop_recording(self) -> EgressFileInfo | None:
        """Stop the active egress recording and wait for upload to complete.

        Returns:
            EgressFileInfo with file details if successful, None on error
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
        self, egress_id: str, timeout: float = 60.0, poll_interval: float = 1.0
    ) -> EgressFileInfo | None:
        """Wait for egress to complete and return file info.

        Args:
            egress_id: The egress ID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Returns:
            EgressFileInfo with file details if successful, None on error/timeout
        """
        start_time = asyncio.get_event_loop().time()
        last_status = None

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
                        file_info = EgressFileInfo(
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
                        logger.warning(
                            f"Egress completed but no file_results found, "
                            f"egress_id={egress_id}"
                        )
                        return None

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
                        return EgressFileInfo(
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


def create_default_egress_manager() -> EgressManager:
    """Create an egress manager with default configuration for the target S3 bucket.

    Returns:
        Configured EgressManager instance
    """
    config = EgressConfig(
        s3_bucket="audivi-audio-recordings",
        s3_prefix="livekit-demos",
    )
    return EgressManager(config)
