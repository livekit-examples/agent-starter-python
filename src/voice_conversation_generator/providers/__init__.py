"""
Provider implementations for voice conversation generator
"""
from .base import (
    LLMProvider,
    TTSProvider,
    STTProvider,
    StorageGateway
)

# LLM Providers
from .llm.openai import OpenAILLMProvider

# TTS Providers
from .tts.openai import OpenAITTSProvider
from .tts.elevenlabs import ElevenLabsTTSProvider

# Storage Providers
from .storage.local import LocalStorageProvider

__all__ = [
    # Base classes
    "LLMProvider",
    "TTSProvider",
    "STTProvider",
    "StorageGateway",

    # LLM implementations
    "OpenAILLMProvider",

    # TTS implementations
    "OpenAITTSProvider",
    "ElevenLabsTTSProvider",

    # Storage implementations
    "LocalStorageProvider",
]