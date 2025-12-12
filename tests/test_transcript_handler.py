"""Tests for the transcript handler module."""

import json
from unittest.mock import MagicMock, patch

import pytest
from livekit_recording import (
    S3Uploader,
    TranscriptData,
    TranscriptEntry,
    TranscriptHandler,
)


class TestTranscriptEntry:
    """Tests for TranscriptEntry dataclass."""

    def test_create_entry(self):
        """Test creating a transcript entry."""
        entry = TranscriptEntry(
            timestamp="2024-01-01T00:00:00+00:00",
            speaker="user",
            text="Hello, world!",
            is_final=True,
        )
        assert entry.speaker == "user"
        assert entry.text == "Hello, world!"
        assert entry.is_final is True


class TestTranscriptData:
    """Tests for TranscriptData dataclass."""

    def test_create_transcript_data(self):
        """Test creating transcript data."""
        data = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
        )
        assert data.room_name == "test-room"
        assert data.entries == []
        assert data.session_end is None

    def test_to_dict(self):
        """Test converting transcript data to dictionary."""
        data = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
            session_end="2024-01-01T00:05:00+00:00",
        )
        data.entries.append(
            TranscriptEntry(
                timestamp="2024-01-01T00:01:00+00:00",
                speaker="user",
                text="Hello",
                is_final=True,
            )
        )
        data.entries.append(
            TranscriptEntry(
                timestamp="2024-01-01T00:02:00+00:00",
                speaker="agent",
                text="Hi there!",
                is_final=True,
            )
        )

        result = data.to_dict()

        assert result["room_name"] == "test-room"
        assert result["session_start"] == "2024-01-01T00:00:00+00:00"
        assert result["session_end"] == "2024-01-01T00:05:00+00:00"
        assert len(result["entries"]) == 2
        assert result["entries"][0]["speaker"] == "user"
        assert result["entries"][0]["text"] == "Hello"
        assert result["entries"][1]["speaker"] == "agent"
        assert result["entries"][1]["text"] == "Hi there!"


class TestTranscriptHandler:
    """Tests for TranscriptHandler class."""

    def test_init(self):
        """Test initializing transcript handler."""
        handler = TranscriptHandler(room_name="test-room")
        assert handler.transcript.room_name == "test-room"
        assert handler.transcript.session_start is not None
        assert handler.s3_uploader is None

    def test_add_user_transcript(self):
        """Test adding user transcript entries."""
        handler = TranscriptHandler(room_name="test-room")

        handler.add_user_transcript("Hello, how are you?")

        assert len(handler.transcript.entries) == 1
        entry = handler.transcript.entries[0]
        assert entry.speaker == "user"
        assert entry.text == "Hello, how are you?"
        assert entry.is_final is True

    def test_add_agent_transcript(self):
        """Test adding agent transcript entries."""
        handler = TranscriptHandler(room_name="test-room")

        handler.add_agent_transcript("I'm doing well, thank you!")

        assert len(handler.transcript.entries) == 1
        entry = handler.transcript.entries[0]
        assert entry.speaker == "agent"
        assert entry.text == "I'm doing well, thank you!"
        assert entry.is_final is True

    def test_add_empty_transcript_ignored(self):
        """Test that empty transcripts are ignored."""
        handler = TranscriptHandler(room_name="test-room")

        handler.add_user_transcript("")
        handler.add_user_transcript("   ")
        handler.add_agent_transcript("")

        assert len(handler.transcript.entries) == 0

    def test_conversation_flow(self):
        """Test a typical conversation flow."""
        handler = TranscriptHandler(room_name="test-room")

        handler.add_user_transcript("What's the weather like?")
        handler.add_agent_transcript("It's sunny and 72 degrees.")
        handler.add_user_transcript("Thanks!")
        handler.add_agent_transcript("You're welcome!")

        assert len(handler.transcript.entries) == 4
        assert handler.transcript.entries[0].speaker == "user"
        assert handler.transcript.entries[1].speaker == "agent"
        assert handler.transcript.entries[2].speaker == "user"
        assert handler.transcript.entries[3].speaker == "agent"

    def test_get_transcript_text(self):
        """Test getting transcript as plain text."""
        handler = TranscriptHandler(room_name="test-room")

        handler.add_user_transcript("Hello")
        handler.add_agent_transcript("Hi there!")

        text = handler.get_transcript_text()

        assert "User: Hello" in text
        assert "Agent: Hi there!" in text

    @pytest.mark.asyncio
    async def test_finalize_and_upload_no_uploader(self):
        """Test finalize without an uploader configured."""
        handler = TranscriptHandler(room_name="test-room")
        handler.add_user_transcript("Test message")

        result = await handler.finalize_and_upload()

        assert result is True
        assert handler.transcript.session_end is not None

    @pytest.mark.asyncio
    async def test_finalize_and_upload_with_mock_uploader(self):
        """Test finalize with a mock uploader."""
        mock_uploader = MagicMock()
        mock_uploader.upload_transcript.return_value = True

        handler = TranscriptHandler(room_name="test-room", s3_uploader=mock_uploader)
        handler.add_user_transcript("Test message")

        result = await handler.finalize_and_upload()

        assert result is True
        mock_uploader.upload_transcript.assert_called_once()

        # Verify the transcript was passed correctly
        call_args = mock_uploader.upload_transcript.call_args
        transcript_arg = call_args[0][0]
        assert transcript_arg.room_name == "test-room"
        assert len(transcript_arg.entries) == 1

        # Verify the key format
        key_arg = call_args[0][1]
        assert key_arg.startswith("transcripts/test-room-")
        assert key_arg.endswith(".json")


class TestS3Uploader:
    """Tests for S3Uploader class."""

    def test_init_with_explicit_credentials(self):
        """Test initializing with explicit credentials."""
        uploader = S3Uploader(
            bucket="test-bucket",
            prefix="test-prefix",
            access_key="test-access-key",
            secret_key="test-secret-key",
            region="us-west-2",
        )

        assert uploader.bucket == "test-bucket"
        assert uploader.prefix == "test-prefix"
        assert uploader.access_key == "test-access-key"
        assert uploader.secret_key == "test-secret-key"
        assert uploader.region == "us-west-2"

    def test_prefix_trailing_slash_removed(self):
        """Test that trailing slashes are removed from prefix."""
        uploader = S3Uploader(
            bucket="test-bucket",
            prefix="test-prefix/",
        )

        assert uploader.prefix == "test-prefix"

    @patch("livekit_recording.transcript.boto3.client")
    def test_upload_transcript_success(self, mock_boto3_client):
        """Test successful transcript upload."""
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        uploader = S3Uploader(
            bucket="test-bucket",
            prefix="test-prefix",
            access_key="test-key",
            secret_key="test-secret",
            region="us-east-1",
        )

        transcript = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
        )
        transcript.entries.append(
            TranscriptEntry(
                timestamp="2024-01-01T00:01:00+00:00",
                speaker="user",
                text="Hello",
                is_final=True,
            )
        )

        result = uploader.upload_transcript(transcript, "transcripts/test.json")

        assert result is True
        mock_s3.put_object.assert_called_once()

        # Verify the call arguments
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "test-prefix/transcripts/test.json"
        assert call_kwargs["ContentType"] == "application/json"

        # Verify the body is valid JSON
        body = call_kwargs["Body"].decode("utf-8")
        parsed = json.loads(body)
        assert parsed["room_name"] == "test-room"

    @patch("livekit_recording.transcript.boto3.client")
    def test_upload_transcript_failure(self, mock_boto3_client):
        """Test transcript upload failure handling."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutObject",
        )
        mock_boto3_client.return_value = mock_s3

        uploader = S3Uploader(
            bucket="test-bucket",
            access_key="test-key",
            secret_key="test-secret",
        )

        transcript = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
        )

        result = uploader.upload_transcript(transcript, "transcripts/test.json")

        assert result is False
