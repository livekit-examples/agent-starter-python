"""Settings management for livekit-recording package."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from livekit import rtc

    from livekit_recording.audio_storage import AudioRecorderProtocol


class StorageMode(str, Enum):
    """Storage mode for audio recordings."""

    LOCAL = "local"  # Save to local filesystem
    S3 = "s3"  # Upload to S3 via LiveKit egress


def _find_env_file(filename: str = ".env.local") -> Path | None:
    """Find an env file by walking up from the current working directory.

    Args:
        filename: Name of the env file to find

    Returns:
        Path to the env file if found, None otherwise
    """
    current = Path.cwd()
    for parent in [current, *current.parents]:
        env_file = parent / filename
        if env_file.exists():
            return env_file
    return None


def _load_env_file(env_file: Path | None = None) -> bool:
    """Load environment variables from a .env file.

    Args:
        env_file: Path to the env file, or None to auto-discover

    Returns:
        True if file was loaded, False otherwise
    """
    try:
        from dotenv import load_dotenv

        if env_file is None:
            env_file = _find_env_file()

        if env_file and env_file.exists():
            loaded = load_dotenv(env_file, override=True)
            if loaded:
                logger.debug(f"Loaded environment from {env_file}")
            return loaded
        return False
    except ImportError:
        logger.warning("python-dotenv not installed, skipping .env file loading")
        return False


@dataclass
class AWSSettings:
    """AWS configuration settings."""

    access_key_id: str = ""
    secret_access_key: str = ""
    region: str = "us-east-1"

    @classmethod
    def from_env(cls) -> AWSSettings:
        """Load AWS settings from environment variables."""
        return cls(
            access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
            secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
            region=os.environ.get("AWS_REGION", "us-east-1"),
        )


@dataclass
class LiveKitSettings:
    """LiveKit configuration settings."""

    url: str = ""
    api_key: str = ""
    api_secret: str = ""

    @classmethod
    def from_env(cls) -> LiveKitSettings:
        """Load LiveKit settings from environment variables."""
        return cls(
            url=os.environ.get("LIVEKIT_URL", ""),
            api_key=os.environ.get("LIVEKIT_API_KEY", ""),
            api_secret=os.environ.get("LIVEKIT_API_SECRET", ""),
        )


@dataclass
class S3Settings:
    """S3 bucket configuration settings."""

    bucket: str = ""
    prefix: str = ""

    def __post_init__(self):
        # Remove trailing slash from prefix
        self.prefix = self.prefix.rstrip("/")


@dataclass
class StorageSettings:
    """Storage configuration settings."""

    mode: StorageMode = StorageMode.LOCAL
    local_output_dir: str = "temp"

    @classmethod
    def from_env(cls) -> StorageSettings:
        """Load storage settings from environment variables."""
        mode_str = os.environ.get("STORAGE_MODE", "local").lower()
        try:
            mode = StorageMode(mode_str)
        except ValueError:
            logger.warning(f"Invalid STORAGE_MODE '{mode_str}', defaulting to 'local'")
            mode = StorageMode.LOCAL

        return cls(
            mode=mode,
            local_output_dir=os.environ.get("LOCAL_OUTPUT_DIR", "temp"),
        )


@dataclass
class Settings:
    """Application settings loaded from environment variables.

    Usage:
        # Load settings (will auto-discover .env.local)
        settings = Settings.load()

        # Access settings
        print(settings.aws.region)
        print(settings.livekit.url)
        print(settings.storage.mode)

        # Create an audio recorder based on settings
        recorder = settings.create_audio_recorder(room=ctx.room)

        # Or create with explicit values
        settings = Settings(
            aws=AWSSettings(region="us-west-1"),
            s3=S3Settings(bucket="my-bucket"),
            storage=StorageSettings(mode=StorageMode.S3),
        )
    """

    aws: AWSSettings = field(default_factory=AWSSettings)
    livekit: LiveKitSettings = field(default_factory=LiveKitSettings)
    s3: S3Settings = field(default_factory=S3Settings)
    storage: StorageSettings = field(default_factory=StorageSettings)

    @classmethod
    def load(cls, env_file: Path | str | None = None) -> Settings:
        """Load settings from environment variables.

        Optionally loads a .env file first. If env_file is None, will
        auto-discover .env.local by walking up from cwd.

        Args:
            env_file: Path to .env file, or None to auto-discover

        Returns:
            Settings instance with values from environment
        """
        # Convert string to Path if needed
        if isinstance(env_file, str):
            env_file = Path(env_file)

        # Load .env file if available
        loaded = _load_env_file(env_file)

        # Create settings from environment
        settings = cls(
            aws=AWSSettings.from_env(),
            livekit=LiveKitSettings.from_env(),
            s3=S3Settings(),
            storage=StorageSettings.from_env(),
        )

        # Log the loaded configuration (redacting secrets)
        logger.info("Settings loaded:")
        logger.info(f"  Storage Mode: {settings.storage.mode.value}")
        logger.info(f"  AWS Region: {settings.aws.region}")
        logger.info(
            f"  AWS Access Key: {'***' + settings.aws.access_key_id[-4:] if settings.aws.access_key_id else 'NOT SET'}"
        )
        logger.info(f"  LiveKit URL: {settings.livekit.url or 'NOT SET'}")
        if settings.storage.mode == StorageMode.LOCAL:
            logger.info(f"  Local Output Dir: {settings.storage.local_output_dir}")
        if not loaded:
            logger.warning("No .env file was loaded - using system environment only")

        return settings

    def configure_s3(self, bucket: str, prefix: str = "") -> Settings:
        """Configure S3 bucket settings.

        Args:
            bucket: S3 bucket name
            prefix: Optional prefix/path within the bucket

        Returns:
            Self for method chaining
        """
        self.s3 = S3Settings(bucket=bucket, prefix=prefix)
        return self

    def create_audio_recorder(
        self,
        bucket: str | None = None,
        prefix: str | None = None,
        room: rtc.Room | None = None,
    ) -> AudioRecorderProtocol:
        """Create an audio recorder based on the current storage mode.

        Args:
            bucket: S3 bucket name (required for S3 mode, uses settings.s3.bucket if not provided)
            prefix: S3 prefix (uses settings.s3.prefix if not provided)
            room: LiveKit room (required for local mode)

        Returns:
            An AudioRecorderProtocol implementation (LocalAudioRecorder or S3AudioRecorder)

        Raises:
            ValueError: If required configuration is missing
        """
        # Import here to avoid circular imports
        from livekit_recording.audio_storage import LocalAudioRecorder
        from livekit_recording.egress import EgressConfig, S3AudioRecorder

        if self.storage.mode == StorageMode.LOCAL:
            logger.info(
                f"Creating LocalAudioRecorder with output_dir={self.storage.local_output_dir}"
            )
            recorder = LocalAudioRecorder(
                output_dir=self.storage.local_output_dir,
                room=room,
            )
            return recorder

        elif self.storage.mode == StorageMode.S3:
            # Use provided bucket/prefix or fall back to settings
            s3_bucket = bucket or self.s3.bucket
            s3_prefix = prefix if prefix is not None else self.s3.prefix

            if not s3_bucket:
                raise ValueError(
                    "S3 bucket is required for S3 storage mode. "
                    "Set STORAGE_MODE=local or provide bucket parameter."
                )

            logger.info(
                f"Creating S3AudioRecorder with bucket={s3_bucket}, prefix={s3_prefix}"
            )
            config = EgressConfig.from_settings(
                self, bucket=s3_bucket, prefix=s3_prefix
            )
            return S3AudioRecorder(config)

        else:
            raise ValueError(f"Unknown storage mode: {self.storage.mode}")
