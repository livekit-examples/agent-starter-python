"""
Base provider classes - Abstract interfaces for all providers
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from ..models import VoiceConfig, Conversation, ConversationMetrics


class LLMProvider(ABC):
    """Abstract base class for LLM providers (OpenAI, Anthropic, etc.)"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize with provider configuration"""
        self.config = config

    @abstractmethod
    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 150,
        **kwargs
    ) -> str:
        """Generate text completion from the LLM

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Temperature for sampling
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int = 150,
        **kwargs
    ) -> str:
        """Generate chat completion from the LLM

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Temperature for sampling
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the name of the model being used"""
        pass


class TTSProvider(ABC):
    """Abstract base class for Text-to-Speech providers"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize with provider configuration"""
        self.config = config

    @abstractmethod
    async def generate_speech(
        self,
        text: str,
        voice_config: VoiceConfig,
        **kwargs
    ) -> bytes:
        """Generate speech audio from text

        Args:
            text: Text to convert to speech
            voice_config: Voice configuration settings
            **kwargs: Provider-specific parameters

        Returns:
            Audio data as bytes
        """
        pass

    @abstractmethod
    def get_supported_voices(self) -> List[str]:
        """Get list of supported voice IDs"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of the TTS provider"""
        pass


class STTProvider(ABC):
    """Abstract base class for Speech-to-Text providers"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize with provider configuration"""
        self.config = config

    @abstractmethod
    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "en",
        **kwargs
    ) -> str:
        """Transcribe audio to text

        Args:
            audio_data: Audio data as bytes
            language: Language code for transcription
            **kwargs: Provider-specific parameters

        Returns:
            Transcribed text
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of the STT provider"""
        pass


class StorageGateway(ABC):
    """Abstract base class for storage providers (local, GCS, S3)"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize with storage configuration"""
        self.config = config

    @abstractmethod
    async def save_audio(
        self,
        data: bytes,
        key: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save audio data to storage

        Args:
            data: Audio data as bytes
            key: Storage key/path for the file
            metadata: Optional metadata to store with the file

        Returns:
            URL or path to the stored file
        """
        pass

    @abstractmethod
    async def save_transcript(
        self,
        data: Dict[str, Any],
        key: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save transcript data to storage

        Args:
            data: Transcript data as dictionary
            key: Storage key/path for the file
            metadata: Optional metadata to store with the file

        Returns:
            URL or path to the stored file
        """
        pass

    @abstractmethod
    async def save_conversation(
        self,
        conversation: Conversation,
        metrics: ConversationMetrics,
        audio_data: Optional[bytes] = None
    ) -> Dict[str, str]:
        """Save a complete conversation with all artifacts

        Args:
            conversation: Conversation object
            metrics: Conversation metrics
            audio_data: Optional combined audio data

        Returns:
            Dictionary with URLs/paths to stored files
            {
                'transcript': 'path/to/transcript.json',
                'audio': 'path/to/audio.mp3',
                'metrics': 'path/to/metrics.json'
            }
        """
        pass

    @abstractmethod
    async def load_audio(self, key: str) -> bytes:
        """Load audio data from storage

        Args:
            key: Storage key/path for the file

        Returns:
            Audio data as bytes
        """
        pass

    @abstractmethod
    async def load_transcript(self, key: str) -> Dict[str, Any]:
        """Load transcript data from storage

        Args:
            key: Storage key/path for the file

        Returns:
            Transcript data as dictionary
        """
        pass

    @abstractmethod
    async def list_conversations(
        self,
        prefix: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List available conversations

        Args:
            prefix: Optional prefix to filter conversations
            limit: Maximum number of conversations to return

        Returns:
            List of conversation metadata
        """
        pass

    @abstractmethod
    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its artifacts

        Args:
            conversation_id: ID of the conversation to delete

        Returns:
            True if deletion was successful
        """
        pass

    @abstractmethod
    def get_storage_type(self) -> str:
        """Get the type of storage (local, gcs, s3)"""
        pass