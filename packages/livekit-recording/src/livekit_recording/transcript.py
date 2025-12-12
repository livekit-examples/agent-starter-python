"""Transcript handler for capturing and storing STT output to S3 or local files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.exceptions import ClientError
from loguru import logger

if TYPE_CHECKING:
    from livekit_recording.settings import Settings


@dataclass
class TranscriptEntry:
    """A single entry in the transcript."""

    timestamp: str
    speaker: str  # "user" or "agent"
    text: str
    is_final: bool = True


@dataclass
class TranscriptData:
    """Complete transcript data for a session."""

    room_name: str
    session_start: str
    entries: list[TranscriptEntry] = field(default_factory=list)
    session_end: str | None = None

    def to_dict(self) -> dict:
        """Convert transcript to dictionary for JSON serialization."""
        return {
            "room_name": self.room_name,
            "session_start": self.session_start,
            "session_end": self.session_end,
            "entries": [
                {
                    "timestamp": e.timestamp,
                    "speaker": e.speaker,
                    "text": e.text,
                    "is_final": e.is_final,
                }
                for e in self.entries
            ],
        }


class TranscriptStorageProtocol(Protocol):
    """Protocol for transcript storage operations.

    Implementations can save transcripts to various backends (local files, S3, etc.).
    """

    def save_transcript(self, transcript: TranscriptData, key: str) -> bool:
        """Save a transcript to storage.

        Args:
            transcript: The transcript data to save
            key: The storage key/path for the transcript

        Returns:
            True if save succeeded, False otherwise
        """
        ...


# Keep S3UploaderProtocol for backward compatibility
S3UploaderProtocol = TranscriptStorageProtocol


class S3Uploader:
    """Handles uploading transcripts to S3."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1",
    ):
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self._client: boto3.client | None = None

    @classmethod
    def from_settings(
        cls, settings: Settings, bucket: str, prefix: str = ""
    ) -> S3Uploader:
        """Create S3Uploader from Settings object.

        Args:
            settings: Settings object with AWS credentials
            bucket: S3 bucket name
            prefix: Prefix/path within the bucket

        Returns:
            Configured S3Uploader instance
        """
        return cls(
            bucket=bucket,
            prefix=prefix,
            access_key=settings.aws.access_key_id,
            secret_key=settings.aws.secret_access_key,
            region=settings.aws.region,
        )

    @property
    def client(self) -> boto3.client:
        """Lazily initialize S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
            )
        return self._client

    def upload_transcript(self, transcript: TranscriptData, key: str) -> bool:
        """Upload transcript JSON to S3.

        Args:
            transcript: The transcript data to upload
            key: The S3 object key (path within bucket)

        Returns:
            True if upload succeeded, False otherwise
        """
        full_key = f"{self.prefix}/{key}" if self.prefix else key

        try:
            json_content = json.dumps(transcript.to_dict(), indent=2)
            self.client.put_object(
                Bucket=self.bucket,
                Key=full_key,
                Body=json_content.encode("utf-8"),
                ContentType="application/json",
            )
            logger.info(f"Uploaded transcript to s3://{self.bucket}/{full_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to upload transcript to S3: {e}")
            return False

    def save_transcript(self, transcript: TranscriptData, key: str) -> bool:
        """Save transcript JSON to S3 (alias for upload_transcript).

        Args:
            transcript: The transcript data to save
            key: The S3 object key (path within bucket)

        Returns:
            True if save succeeded, False otherwise
        """
        return self.upload_transcript(transcript, key)


class LocalTranscriptStorage:
    """Handles saving transcripts to local filesystem."""

    def __init__(self, output_dir: str | Path = "temp"):
        """Initialize the local transcript storage.

        Args:
            output_dir: Directory to save transcript files (default: temp/)
        """
        self.output_dir = Path(output_dir)
        logger.debug(f"LocalTranscriptStorage initialized with output_dir={output_dir}")

    def save_transcript(self, transcript: TranscriptData, key: str) -> bool:
        """Save transcript JSON to local filesystem.

        Args:
            transcript: The transcript data to save
            key: The file path relative to output_dir (e.g., transcripts/room-session.json)

        Returns:
            True if save succeeded, False otherwise
        """
        # Build full path
        output_path = self.output_dir / key

        try:
            # Create parent directories if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON file
            json_content = json.dumps(transcript.to_dict(), indent=2)
            output_path.write_text(json_content, encoding="utf-8")

            logger.info(f"Saved transcript to {output_path.absolute()}")
            return True
        except OSError as e:
            logger.error(f"Failed to save transcript to local file: {e}")
            return False

    # Alias for backward compatibility
    def upload_transcript(self, transcript: TranscriptData, key: str) -> bool:
        """Alias for save_transcript for backward compatibility."""
        return self.save_transcript(transcript, key)


class TranscriptHandler:
    """Handles capturing and storing conversation transcripts."""

    def __init__(
        self,
        room_name: str,
        storage: TranscriptStorageProtocol | None = None,
        session_id: str | None = None,
        *,
        # Backward compatibility alias
        s3_uploader: TranscriptStorageProtocol | None = None,
    ):
        """Initialize the transcript handler.

        Args:
            room_name: Name of the LiveKit room
            storage: Storage instance for saving transcripts (local or S3)
            session_id: Unique session identifier for matching audio/transcript files
            s3_uploader: Deprecated alias for storage parameter (backward compatibility)
        """
        self.transcript = TranscriptData(
            room_name=room_name,
            session_start=datetime.now(UTC).isoformat(),
        )
        # Support both 'storage' and deprecated 's3_uploader' parameter
        self.storage = storage or s3_uploader
        # Keep s3_uploader as alias for backward compatibility
        self.s3_uploader = self.storage
        # Use provided session_id or generate one
        self.session_id = session_id or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    def add_user_transcript(self, text: str, is_final: bool = True) -> None:
        """Add a user speech transcript entry.

        Args:
            text: The transcribed text
            is_final: Whether this is a final transcript (vs interim)
        """
        if not text.strip():
            return

        entry = TranscriptEntry(
            timestamp=datetime.now(UTC).isoformat(),
            speaker="user",
            text=text.strip(),
            is_final=is_final,
        )
        self.transcript.entries.append(entry)
        logger.debug(f"User transcript: {text}")

    def add_agent_transcript(self, text: str, is_final: bool = True) -> None:
        """Add an agent speech transcript entry.

        Args:
            text: The agent's response text
            is_final: Whether this is a final transcript
        """
        if not text.strip():
            return

        entry = TranscriptEntry(
            timestamp=datetime.now(UTC).isoformat(),
            speaker="agent",
            text=text.strip(),
            is_final=is_final,
        )
        self.transcript.entries.append(entry)
        logger.debug(f"Agent transcript: {text}")

    async def finalize_and_save(self) -> bool:
        """Finalize the transcript and save to storage (local or S3).

        Returns:
            True if save succeeded or no storage configured, False on failure
        """
        self.transcript.session_end = datetime.now(UTC).isoformat()

        if not self.storage:
            logger.warning("No transcript storage configured, transcript not saved")
            return True

        # Use session_id for filename to match audio recording
        key = f"transcripts/{self.transcript.room_name}-{self.session_id}.json"

        return self.storage.save_transcript(self.transcript, key)

    async def finalize_and_upload(self) -> bool:
        """Alias for finalize_and_save (backward compatibility).

        Returns:
            True if save succeeded or no storage configured, False on failure
        """
        return await self.finalize_and_save()

    def get_transcript_text(self) -> str:
        """Get the transcript as plain text.

        Returns:
            Formatted transcript text
        """
        lines = []
        for entry in self.transcript.entries:
            speaker = "User" if entry.speaker == "user" else "Agent"
            lines.append(f"[{entry.timestamp}] {speaker}: {entry.text}")
        return "\n".join(lines)
