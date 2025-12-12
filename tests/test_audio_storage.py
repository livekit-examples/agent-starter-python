"""Tests for the audio storage module."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from livekit_recording import (
    AudioFileInfo,
    LocalAudioRecorder,
    S3AudioRecorder,
    Settings,
    StorageMode,
)
from livekit_recording.egress import EgressConfig


class TestAudioFileInfo:
    """Tests for AudioFileInfo dataclass."""

    def test_create_audio_file_info(self):
        """Test creating AudioFileInfo with all fields."""
        info = AudioFileInfo(
            filename="test-room-20251212-120000.wav",
            location="/tmp/audio/test-room-20251212-120000.wav",
            duration=60_000_000_000,  # 60 seconds in nanoseconds
            size=1024000,
        )

        assert info.filename == "test-room-20251212-120000.wav"
        assert info.location == "/tmp/audio/test-room-20251212-120000.wav"
        assert info.duration == 60_000_000_000
        assert info.size == 1024000


class TestLocalAudioRecorder:
    """Tests for LocalAudioRecorder class."""

    def test_init_default_output_dir(self):
        """Test initializing with default output directory."""
        recorder = LocalAudioRecorder()

        assert recorder.output_dir == Path("temp")
        assert recorder.recording_id is None

    def test_init_custom_output_dir(self):
        """Test initializing with custom output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = LocalAudioRecorder(output_dir=tmpdir)

            assert recorder.output_dir == Path(tmpdir)
            assert recorder.recording_id is None

    def test_set_room(self):
        """Test setting the room."""
        recorder = LocalAudioRecorder()
        mock_room = MagicMock()

        recorder.set_room(mock_room)

        assert recorder._room == mock_room

    @pytest.mark.asyncio
    async def test_start_recording_no_room(self):
        """Test starting recording without a room set."""
        recorder = LocalAudioRecorder()

        result = await recorder.start_recording("test-room")

        assert result is None
        assert recorder.recording_id is None

    @pytest.mark.asyncio
    async def test_start_recording_already_active(self):
        """Test starting recording when one is already active."""
        recorder = LocalAudioRecorder()
        recorder._recording_id = "LOCAL_existing"

        result = await recorder.start_recording("test-room")

        assert result == "LOCAL_existing"

    @pytest.mark.asyncio
    async def test_stop_recording_no_active_recording(self):
        """Test stopping when no recording is active."""
        recorder = LocalAudioRecorder()

        result = await recorder.stop_recording()

        assert result is None

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the recorder."""
        recorder = LocalAudioRecorder()

        # Should not raise
        await recorder.close()


class TestS3AudioRecorder:
    """Tests for S3AudioRecorder class."""

    def test_init(self):
        """Test initializing S3 audio recorder."""
        config = EgressConfig(
            s3_bucket="test-bucket",
            s3_prefix="test-prefix",
        )
        recorder = S3AudioRecorder(config)

        assert recorder.config == config
        assert recorder.egress_id is None
        assert recorder.recording_id is None

    def test_recording_id_alias(self):
        """Test that recording_id is an alias for egress_id."""
        config = EgressConfig(s3_bucket="test-bucket")
        recorder = S3AudioRecorder(config)
        recorder._egress_id = "EG_TEST123"

        assert recorder.recording_id == "EG_TEST123"
        assert recorder.egress_id == "EG_TEST123"

    @pytest.mark.asyncio
    async def test_start_recording_calls_start_dual_channel(self):
        """Test that start_recording delegates to start_dual_channel_recording."""
        config = EgressConfig(
            s3_bucket="test-bucket",
            livekit_url="https://test.livekit.cloud",
            livekit_api_key="api-key",
            livekit_api_secret="api-secret",
        )
        recorder = S3AudioRecorder(config)

        # Mock the underlying method
        mock_egress_info = MagicMock()
        mock_egress_info.egress_id = "EG_TEST123"

        mock_egress_service = AsyncMock()
        mock_egress_service.start_room_composite_egress = AsyncMock(
            return_value=mock_egress_info
        )

        mock_api = MagicMock()
        mock_api.egress = mock_egress_service

        recorder._api = mock_api

        # Call start_recording (protocol method)
        result = await recorder.start_recording("test-room", "session-123")

        assert result == "EG_TEST123"
        assert recorder.recording_id == "EG_TEST123"


class TestAudioRecorderProtocol:
    """Tests for protocol compliance."""

    def test_local_recorder_implements_protocol(self):
        """Test that LocalAudioRecorder implements AudioRecorderProtocol."""
        recorder = LocalAudioRecorder()

        # Check that all protocol methods exist and are callable
        assert callable(recorder.start_recording)
        assert callable(recorder.stop_recording)
        assert callable(recorder.close)

    def test_s3_recorder_implements_protocol(self):
        """Test that S3AudioRecorder implements AudioRecorderProtocol."""
        config = EgressConfig(s3_bucket="test-bucket")
        recorder = S3AudioRecorder(config)

        # Check that all protocol methods exist and are callable
        assert callable(recorder.start_recording)
        assert callable(recorder.stop_recording)
        assert callable(recorder.close)


class TestSettingsStorageMode:
    """Tests for storage mode configuration."""

    def test_storage_mode_default(self):
        """Test default storage mode is local."""
        with patch.dict("os.environ", {}, clear=True):
            from livekit_recording.settings import StorageSettings

            settings = StorageSettings.from_env()

            assert settings.mode == StorageMode.LOCAL

    def test_storage_mode_from_env_local(self):
        """Test loading local storage mode from environment."""
        with patch.dict("os.environ", {"STORAGE_MODE": "local"}):
            from livekit_recording.settings import StorageSettings

            settings = StorageSettings.from_env()

            assert settings.mode == StorageMode.LOCAL

    def test_storage_mode_from_env_s3(self):
        """Test loading S3 storage mode from environment."""
        with patch.dict("os.environ", {"STORAGE_MODE": "s3"}):
            from livekit_recording.settings import StorageSettings

            settings = StorageSettings.from_env()

            assert settings.mode == StorageMode.S3

    def test_storage_mode_invalid_defaults_to_local(self):
        """Test that invalid storage mode defaults to local."""
        with patch.dict("os.environ", {"STORAGE_MODE": "invalid"}):
            from livekit_recording.settings import StorageSettings

            settings = StorageSettings.from_env()

            assert settings.mode == StorageMode.LOCAL

    def test_local_output_dir_from_env(self):
        """Test loading local output directory from environment."""
        with patch.dict("os.environ", {"LOCAL_OUTPUT_DIR": "/custom/path"}):
            from livekit_recording.settings import StorageSettings

            settings = StorageSettings.from_env()

            assert settings.local_output_dir == "/custom/path"


class TestSettingsCreateAudioRecorder:
    """Tests for Settings.create_audio_recorder factory method."""

    def test_create_local_recorder(self):
        """Test creating local audio recorder from settings."""
        settings = Settings()
        settings.storage.mode = StorageMode.LOCAL
        settings.storage.local_output_dir = "test_output"

        recorder = settings.create_audio_recorder()

        assert isinstance(recorder, LocalAudioRecorder)
        assert recorder.output_dir == Path("test_output")

    def test_create_s3_recorder(self):
        """Test creating S3 audio recorder from settings."""
        settings = Settings()
        settings.storage.mode = StorageMode.S3
        settings.s3.bucket = "test-bucket"
        settings.s3.prefix = "test-prefix"
        settings.livekit.url = "https://test.livekit.cloud"
        settings.livekit.api_key = "api-key"
        settings.livekit.api_secret = "api-secret"

        recorder = settings.create_audio_recorder()

        assert isinstance(recorder, S3AudioRecorder)
        assert recorder.config.s3_bucket == "test-bucket"
        assert recorder.config.s3_prefix == "test-prefix"

    def test_create_s3_recorder_with_explicit_bucket(self):
        """Test creating S3 recorder with explicit bucket parameter."""
        settings = Settings()
        settings.storage.mode = StorageMode.S3
        settings.livekit.url = "https://test.livekit.cloud"
        settings.livekit.api_key = "api-key"
        settings.livekit.api_secret = "api-secret"

        recorder = settings.create_audio_recorder(
            bucket="explicit-bucket", prefix="explicit-prefix"
        )

        assert isinstance(recorder, S3AudioRecorder)
        assert recorder.config.s3_bucket == "explicit-bucket"
        assert recorder.config.s3_prefix == "explicit-prefix"

    def test_create_s3_recorder_missing_bucket_raises(self):
        """Test that creating S3 recorder without bucket raises ValueError."""
        settings = Settings()
        settings.storage.mode = StorageMode.S3
        settings.s3.bucket = ""  # No bucket configured

        with pytest.raises(ValueError, match="S3 bucket is required"):
            settings.create_audio_recorder()

    def test_create_local_recorder_with_room(self):
        """Test creating local recorder with room."""
        settings = Settings()
        settings.storage.mode = StorageMode.LOCAL

        mock_room = MagicMock()
        recorder = settings.create_audio_recorder(room=mock_room)

        assert isinstance(recorder, LocalAudioRecorder)
        assert recorder._room == mock_room
