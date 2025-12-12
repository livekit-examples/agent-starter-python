"""Tests for the egress manager module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from egress_manager import EgressConfig, EgressManager, create_default_egress_manager


class TestEgressConfig:
    """Tests for EgressConfig class."""

    def test_init_with_explicit_values(self):
        """Test initializing with explicit values."""
        config = EgressConfig(
            s3_bucket="test-bucket",
            s3_prefix="test-prefix/",
            aws_access_key="test-access-key",
            aws_secret_key="test-secret-key",
            aws_region="us-west-2",
            livekit_url="https://test.livekit.cloud",
            livekit_api_key="test-api-key",
            livekit_api_secret="test-api-secret",
        )

        assert config.s3_bucket == "test-bucket"
        assert config.s3_prefix == "test-prefix"  # Trailing slash removed
        assert config.aws_access_key == "test-access-key"
        assert config.aws_secret_key == "test-secret-key"
        assert config.aws_region == "us-west-2"
        assert config.livekit_url == "https://test.livekit.cloud"
        assert config.livekit_api_key == "test-api-key"
        assert config.livekit_api_secret == "test-api-secret"

    def test_init_with_env_vars(self):
        """Test initializing with environment variables."""
        with patch.dict(
            "os.environ",
            {
                "AWS_ACCESS_KEY_ID": "env-access-key",
                "AWS_SECRET_ACCESS_KEY": "env-secret-key",
                "AWS_REGION": "eu-west-1",
                "LIVEKIT_URL": "https://env.livekit.cloud",
                "LIVEKIT_API_KEY": "env-api-key",
                "LIVEKIT_API_SECRET": "env-api-secret",
            },
        ):
            config = EgressConfig(
                s3_bucket="test-bucket",
            )

            assert config.aws_access_key == "env-access-key"
            assert config.aws_secret_key == "env-secret-key"
            assert config.aws_region == "eu-west-1"
            assert config.livekit_url == "https://env.livekit.cloud"
            assert config.livekit_api_key == "env-api-key"
            assert config.livekit_api_secret == "env-api-secret"


class TestEgressManager:
    """Tests for EgressManager class."""

    def test_init(self):
        """Test initializing egress manager."""
        config = EgressConfig(
            s3_bucket="test-bucket",
            s3_prefix="test-prefix",
        )
        manager = EgressManager(config)

        assert manager.config == config
        assert manager.egress_id is None

    @pytest.mark.asyncio
    async def test_start_dual_channel_recording_success(self):
        """Test successful dual-channel recording start."""
        config = EgressConfig(
            s3_bucket="test-bucket",
            s3_prefix="test-prefix",
            aws_access_key="test-key",
            aws_secret_key="test-secret",
            aws_region="us-east-1",
            livekit_url="https://test.livekit.cloud",
            livekit_api_key="api-key",
            livekit_api_secret="api-secret",
        )
        manager = EgressManager(config)

        # Mock the LiveKit API
        mock_egress_info = MagicMock()
        mock_egress_info.egress_id = "EG_TEST123456"

        mock_egress_service = AsyncMock()
        mock_egress_service.start_room_composite_egress = AsyncMock(
            return_value=mock_egress_info
        )

        mock_api = MagicMock()
        mock_api.egress = mock_egress_service

        manager._api = mock_api

        result = await manager.start_dual_channel_recording("test-room")

        assert result == "EG_TEST123456"
        assert manager.egress_id == "EG_TEST123456"

        # Verify the egress request
        mock_egress_service.start_room_composite_egress.assert_called_once()
        call_args = mock_egress_service.start_room_composite_egress.call_args[0][0]
        assert call_args.room_name == "test-room"
        assert call_args.audio_only is True

    @pytest.mark.asyncio
    async def test_start_dual_channel_recording_already_active(self):
        """Test starting recording when one is already active."""
        config = EgressConfig(
            s3_bucket="test-bucket",
        )
        manager = EgressManager(config)
        manager._egress_id = "EG_EXISTING123"

        result = await manager.start_dual_channel_recording("test-room")

        assert result == "EG_EXISTING123"

    @pytest.mark.asyncio
    async def test_start_dual_channel_recording_failure(self):
        """Test handling recording start failure."""
        config = EgressConfig(
            s3_bucket="test-bucket",
            livekit_url="https://test.livekit.cloud",
            livekit_api_key="api-key",
            livekit_api_secret="api-secret",
        )
        manager = EgressManager(config)

        # Mock the LiveKit API to raise an exception
        mock_egress_service = AsyncMock()
        mock_egress_service.start_room_composite_egress = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        mock_api = MagicMock()
        mock_api.egress = mock_egress_service

        manager._api = mock_api

        result = await manager.start_dual_channel_recording("test-room")

        assert result is None
        assert manager.egress_id is None

    @pytest.mark.asyncio
    async def test_stop_recording_success(self):
        """Test successful recording stop."""
        config = EgressConfig(
            s3_bucket="test-bucket",
        )
        manager = EgressManager(config)
        manager._egress_id = "EG_TEST123456"

        # Mock the LiveKit API
        mock_egress_service = AsyncMock()
        mock_egress_service.stop_egress = AsyncMock()

        mock_api = MagicMock()
        mock_api.egress = mock_egress_service

        manager._api = mock_api

        result = await manager.stop_recording()

        assert result is True
        assert manager.egress_id is None
        mock_egress_service.stop_egress.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_recording_no_active_egress(self):
        """Test stopping when no egress is active."""
        config = EgressConfig(
            s3_bucket="test-bucket",
        )
        manager = EgressManager(config)

        result = await manager.stop_recording()

        assert result is True

    @pytest.mark.asyncio
    async def test_stop_recording_failure(self):
        """Test handling stop failure."""
        config = EgressConfig(
            s3_bucket="test-bucket",
        )
        manager = EgressManager(config)
        manager._egress_id = "EG_TEST123456"

        # Mock the LiveKit API to raise an exception
        mock_egress_service = AsyncMock()
        mock_egress_service.stop_egress = AsyncMock(
            side_effect=Exception("Stop failed")
        )

        mock_api = MagicMock()
        mock_api.egress = mock_egress_service

        manager._api = mock_api

        result = await manager.stop_recording()

        assert result is False

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the egress manager."""
        config = EgressConfig(
            s3_bucket="test-bucket",
        )
        manager = EgressManager(config)

        mock_api = AsyncMock()
        manager._api = mock_api

        await manager.close()

        mock_api.aclose.assert_called_once()
        assert manager._api is None


class TestCreateDefaultEgressManager:
    """Tests for the create_default_egress_manager function."""

    def test_creates_manager_with_correct_bucket(self):
        """Test that default manager uses correct S3 bucket."""
        manager = create_default_egress_manager()

        assert manager.config.s3_bucket == "audivi-audio-recordings"
        assert manager.config.s3_prefix == "livekit-demos"
