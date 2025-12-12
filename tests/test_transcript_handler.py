"""Tests for the transcript handler module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from livekit_recording import (
    LocalTranscriptStorage,
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
        assert handler.storage is None

    def test_init_with_storage(self):
        """Test initializing transcript handler with storage."""
        mock_storage = MagicMock()
        handler = TranscriptHandler(room_name="test-room", storage=mock_storage)
        assert handler.storage is mock_storage

    def test_init_with_s3_uploader_backward_compat(self):
        """Test initializing with deprecated s3_uploader parameter."""
        mock_uploader = MagicMock()
        handler = TranscriptHandler(room_name="test-room", s3_uploader=mock_uploader)
        # Both storage and s3_uploader should reference the same object
        assert handler.storage is mock_uploader
        assert handler.s3_uploader is mock_uploader

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
    async def test_finalize_and_save_no_storage(self):
        """Test finalize without storage configured."""
        handler = TranscriptHandler(room_name="test-room")
        handler.add_user_transcript("Test message")

        result = await handler.finalize_and_save()

        assert result is True
        assert handler.transcript.session_end is not None

    @pytest.mark.asyncio
    async def test_finalize_and_upload_no_storage(self):
        """Test finalize_and_upload (backward compat) without storage configured."""
        handler = TranscriptHandler(room_name="test-room")
        handler.add_user_transcript("Test message")

        result = await handler.finalize_and_upload()

        assert result is True
        assert handler.transcript.session_end is not None

    @pytest.mark.asyncio
    async def test_finalize_and_save_with_mock_storage(self):
        """Test finalize with mock storage."""
        mock_storage = MagicMock()
        mock_storage.save_transcript.return_value = True

        handler = TranscriptHandler(room_name="test-room", storage=mock_storage)
        handler.add_user_transcript("Test message")

        result = await handler.finalize_and_save()

        assert result is True
        mock_storage.save_transcript.assert_called_once()

        # Verify the transcript was passed correctly
        call_args = mock_storage.save_transcript.call_args
        transcript_arg = call_args[0][0]
        assert transcript_arg.room_name == "test-room"
        assert len(transcript_arg.entries) == 1

        # Verify the key format
        key_arg = call_args[0][1]
        assert key_arg.startswith("transcripts/test-room-")
        assert key_arg.endswith(".json")

    @pytest.mark.asyncio
    async def test_finalize_and_upload_with_mock_uploader(self):
        """Test finalize with a mock uploader (backward compatibility)."""
        mock_uploader = MagicMock()
        mock_uploader.save_transcript.return_value = True

        handler = TranscriptHandler(room_name="test-room", s3_uploader=mock_uploader)
        handler.add_user_transcript("Test message")

        result = await handler.finalize_and_upload()

        assert result is True
        mock_uploader.save_transcript.assert_called_once()

        # Verify the transcript was passed correctly
        call_args = mock_uploader.save_transcript.call_args
        transcript_arg = call_args[0][0]
        assert transcript_arg.room_name == "test-room"
        assert len(transcript_arg.entries) == 1

        # Verify the key format
        key_arg = call_args[0][1]
        assert key_arg.startswith("transcripts/test-room-")
        assert key_arg.endswith(".json")


class TestLocalTranscriptStorage:
    """Tests for LocalTranscriptStorage class."""

    def test_init(self, tmp_path):
        """Test initializing local transcript storage."""
        storage = LocalTranscriptStorage(output_dir=tmp_path)
        assert storage.output_dir == tmp_path

    def test_init_default_dir(self):
        """Test initializing with default output directory."""
        storage = LocalTranscriptStorage()
        assert storage.output_dir == Path("temp")

    def test_save_transcript_creates_directory(self, tmp_path):
        """Test that save_transcript creates the transcripts directory."""
        storage = LocalTranscriptStorage(output_dir=tmp_path)
        transcript = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
        )

        result = storage.save_transcript(transcript, "transcripts/test.json")

        assert result is True
        assert (tmp_path / "transcripts").exists()
        assert (tmp_path / "transcripts" / "test.json").exists()

    def test_save_transcript_content(self, tmp_path):
        """Test that saved transcript has correct JSON content."""
        storage = LocalTranscriptStorage(output_dir=tmp_path)
        transcript = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
            session_end="2024-01-01T00:05:00+00:00",
        )
        transcript.entries.append(
            TranscriptEntry(
                timestamp="2024-01-01T00:01:00+00:00",
                speaker="user",
                text="Hello",
                is_final=True,
            )
        )
        transcript.entries.append(
            TranscriptEntry(
                timestamp="2024-01-01T00:02:00+00:00",
                speaker="agent",
                text="Hi there!",
                is_final=True,
            )
        )

        result = storage.save_transcript(transcript, "transcripts/test.json")

        assert result is True

        # Read and verify the saved content
        saved_path = tmp_path / "transcripts" / "test.json"
        saved_content = json.loads(saved_path.read_text(encoding="utf-8"))

        assert saved_content["room_name"] == "test-room"
        assert saved_content["session_start"] == "2024-01-01T00:00:00+00:00"
        assert saved_content["session_end"] == "2024-01-01T00:05:00+00:00"
        assert len(saved_content["entries"]) == 2
        assert saved_content["entries"][0]["speaker"] == "user"
        assert saved_content["entries"][0]["text"] == "Hello"
        assert saved_content["entries"][1]["speaker"] == "agent"
        assert saved_content["entries"][1]["text"] == "Hi there!"

    def test_save_transcript_nested_path(self, tmp_path):
        """Test saving transcript with nested path."""
        storage = LocalTranscriptStorage(output_dir=tmp_path)
        transcript = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
        )

        result = storage.save_transcript(
            transcript, "transcripts/2024/01/test-room-session.json"
        )

        assert result is True
        assert (
            tmp_path / "transcripts" / "2024" / "01" / "test-room-session.json"
        ).exists()

    def test_upload_transcript_alias(self, tmp_path):
        """Test upload_transcript is an alias for save_transcript."""
        storage = LocalTranscriptStorage(output_dir=tmp_path)
        transcript = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
        )

        # Use upload_transcript (backward compat alias)
        result = storage.upload_transcript(transcript, "transcripts/test.json")

        assert result is True
        assert (tmp_path / "transcripts" / "test.json").exists()

    def test_save_transcript_handles_error(self, tmp_path):
        """Test that save_transcript returns False on error."""
        storage = LocalTranscriptStorage(output_dir=tmp_path)
        transcript = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
        )

        # Try to save to an invalid path (parent is a file, not directory)
        # Create a file that will block directory creation
        blocking_file = tmp_path / "transcripts"
        blocking_file.write_text("blocking")

        result = storage.save_transcript(transcript, "transcripts/subdir/test.json")

        assert result is False


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

    @patch("livekit_recording.transcript.boto3.client")
    def test_save_transcript_alias(self, mock_boto3_client):
        """Test save_transcript is an alias for upload_transcript."""
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        uploader = S3Uploader(
            bucket="test-bucket",
            prefix="test-prefix",
            access_key="test-key",
            secret_key="test-secret",
        )

        transcript = TranscriptData(
            room_name="test-room",
            session_start="2024-01-01T00:00:00+00:00",
        )

        # Use save_transcript (TranscriptStorageProtocol method)
        result = uploader.save_transcript(transcript, "transcripts/test.json")

        assert result is True
        mock_s3.put_object.assert_called_once()


class TestSettingsCreateTranscriptStorage:
    """Tests for Settings.create_transcript_storage method."""

    def test_create_local_storage(self, tmp_path):
        """Test creating local transcript storage."""
        from livekit_recording import Settings, StorageMode, StorageSettings

        settings = Settings(
            storage=StorageSettings(
                mode=StorageMode.LOCAL, local_output_dir=str(tmp_path)
            )
        )

        storage = settings.create_transcript_storage()

        assert isinstance(storage, LocalTranscriptStorage)
        assert storage.output_dir == tmp_path

    def test_create_s3_storage(self):
        """Test creating S3 transcript storage."""
        from livekit_recording import (
            AWSSettings,
            S3Settings,
            Settings,
            StorageMode,
            StorageSettings,
        )

        settings = Settings(
            aws=AWSSettings(
                access_key_id="test-key",
                secret_access_key="test-secret",
                region="us-west-2",
            ),
            s3=S3Settings(bucket="test-bucket", prefix="test-prefix"),
            storage=StorageSettings(mode=StorageMode.S3),
        )

        storage = settings.create_transcript_storage()

        assert isinstance(storage, S3Uploader)
        assert storage.bucket == "test-bucket"
        assert storage.prefix == "test-prefix"
        assert storage.region == "us-west-2"

    def test_create_s3_storage_with_override(self):
        """Test creating S3 storage with bucket/prefix override."""
        from livekit_recording import (
            AWSSettings,
            S3Settings,
            Settings,
            StorageMode,
            StorageSettings,
        )

        settings = Settings(
            aws=AWSSettings(
                access_key_id="test-key",
                secret_access_key="test-secret",
            ),
            s3=S3Settings(bucket="default-bucket", prefix="default-prefix"),
            storage=StorageSettings(mode=StorageMode.S3),
        )

        storage = settings.create_transcript_storage(
            bucket="override-bucket", prefix="override-prefix"
        )

        assert isinstance(storage, S3Uploader)
        assert storage.bucket == "override-bucket"
        assert storage.prefix == "override-prefix"

    def test_create_s3_storage_missing_bucket(self):
        """Test that missing S3 bucket raises ValueError."""
        from livekit_recording import Settings, StorageMode, StorageSettings

        settings = Settings(storage=StorageSettings(mode=StorageMode.S3))

        with pytest.raises(ValueError, match="S3 bucket is required"):
            settings.create_transcript_storage()
