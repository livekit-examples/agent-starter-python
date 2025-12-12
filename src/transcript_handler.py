"""Transcript handler for capturing and storing STT output to S3."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import boto3
from botocore.exceptions import ClientError
from loguru import logger


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


class S3UploaderProtocol(Protocol):
    """Protocol for S3 upload operations."""

    def upload_transcript(self, transcript: TranscriptData, key: str) -> bool: ...


class S3Uploader:
    """Handles uploading transcripts to S3."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
    ):
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")

        # Use provided credentials or fall back to environment variables
        self.access_key = access_key or os.environ.get("AWS_ACCESS_KEY_ID")
        self.secret_key = secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY")
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")

        self._client: boto3.client | None = None

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


class TranscriptHandler:
    """Handles capturing and storing conversation transcripts."""

    def __init__(
        self,
        room_name: str,
        s3_uploader: S3UploaderProtocol | None = None,
        session_id: str | None = None,
    ):
        """Initialize the transcript handler.

        Args:
            room_name: Name of the LiveKit room
            s3_uploader: S3 uploader instance for storing transcripts
            session_id: Unique session identifier for matching audio/transcript files
        """
        self.transcript = TranscriptData(
            room_name=room_name,
            session_start=datetime.now(timezone.utc).isoformat(),
        )
        self.s3_uploader = s3_uploader
        # Use provided session_id or generate one
        self.session_id = session_id or datetime.now(timezone.utc).strftime(
            "%Y%m%d-%H%M%S"
        )

    def add_user_transcript(self, text: str, is_final: bool = True) -> None:
        """Add a user speech transcript entry.

        Args:
            text: The transcribed text
            is_final: Whether this is a final transcript (vs interim)
        """
        if not text.strip():
            return

        entry = TranscriptEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
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
            timestamp=datetime.now(timezone.utc).isoformat(),
            speaker="agent",
            text=text.strip(),
            is_final=is_final,
        )
        self.transcript.entries.append(entry)
        logger.debug(f"Agent transcript: {text}")

    async def finalize_and_upload(self) -> bool:
        """Finalize the transcript and upload to S3.

        Returns:
            True if upload succeeded or no uploader configured, False on failure
        """
        self.transcript.session_end = datetime.now(timezone.utc).isoformat()

        if not self.s3_uploader:
            logger.warning("No S3 uploader configured, transcript not saved")
            return True

        # Use session_id for filename to match audio recording
        key = f"transcripts/{self.transcript.room_name}-{self.session_id}.json"

        return self.s3_uploader.upload_transcript(self.transcript, key)

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
