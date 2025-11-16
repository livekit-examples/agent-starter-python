"""
Provider Factory - Creates provider instances based on configuration
"""
from typing import Dict, Any
from ..config.config import Config
from ..providers import (
    LLMProvider,
    TTSProvider,
    StorageGateway,
    OpenAILLMProvider,
    OpenAITTSProvider,
    ElevenLabsTTSProvider,
    LocalStorageProvider
)


class ProviderFactory:
    """Factory class for creating provider instances"""

    @staticmethod
    def create_llm_provider(config: Config) -> LLMProvider:
        """Create LLM provider based on configuration

        Args:
            config: Application configuration

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If provider type is not supported
        """
        provider_config = config.providers.llm
        provider_type = provider_config.get('type', 'openai').lower()

        if provider_type == 'openai':
            return OpenAILLMProvider(provider_config)
        # Future: Add Anthropic, etc.
        # elif provider_type == 'anthropic':
        #     return AnthropicLLMProvider(provider_config)
        else:
            raise ValueError(f"Unsupported LLM provider type: {provider_type}")

    @staticmethod
    def create_tts_provider(config: Config) -> TTSProvider:
        """Create TTS provider based on configuration

        Args:
            config: Application configuration

        Returns:
            TTSProvider instance

        Raises:
            ValueError: If provider type is not supported
        """
        provider_config = config.providers.tts
        provider_type = provider_config.get('type', 'openai').lower()

        if provider_type == 'openai':
            return OpenAITTSProvider(provider_config)
        elif provider_type == 'elevenlabs':
            return ElevenLabsTTSProvider(provider_config)
        else:
            raise ValueError(f"Unsupported TTS provider type: {provider_type}")

    @staticmethod
    def create_storage_gateway(config: Config) -> StorageGateway:
        """Create storage gateway based on configuration

        Args:
            config: Application configuration

        Returns:
            StorageGateway instance

        Raises:
            ValueError: If storage type is not supported
        """
        storage_type = config.storage.type.lower()

        if storage_type == 'local':
            return LocalStorageProvider(config.storage.local)
        # Future: Add GCS and S3
        # elif storage_type == 'gcs':
        #     return GCSStorageProvider(config.storage.gcs)
        # elif storage_type == 's3':
        #     return S3StorageProvider(config.storage.s3)
        else:
            raise ValueError(f"Unsupported storage type: {storage_type}")

    @staticmethod
    def create_all_providers(config: Config) -> Dict[str, Any]:
        """Create all providers based on configuration

        Args:
            config: Application configuration

        Returns:
            Dictionary with all provider instances
        """
        return {
            'llm': ProviderFactory.create_llm_provider(config),
            'tts': ProviderFactory.create_tts_provider(config),
            'storage': ProviderFactory.create_storage_gateway(config)
        }