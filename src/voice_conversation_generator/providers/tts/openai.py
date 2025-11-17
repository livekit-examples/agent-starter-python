"""
OpenAI TTS Provider Implementation
"""
import os
from typing import Dict, Any, List
from openai import AsyncOpenAI
from ...models import VoiceConfig
from ..base import TTSProvider


class OpenAITTSProvider(TTSProvider):
    """OpenAI Text-to-Speech provider"""

    SUPPORTED_VOICES = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
    SUPPORTED_MODELS = ['tts-1', 'tts-1-hd']

    def __init__(self, config: Dict[str, Any]):
        """Initialize OpenAI TTS client

        Config should include:
        - api_key: OpenAI API key (or from env OPENAI_API_KEY)
        - model: TTS model ('tts-1' or 'tts-1-hd')
        - default_voice: Default voice to use
        """
        super().__init__(config)

        # Get API key from config or environment
        api_key = config.get('api_key') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OpenAI API key not found in config or environment")

        # Initialize client
        self.client = AsyncOpenAI(api_key=api_key)

        # Set defaults
        self.default_model = config.get('model', 'tts-1')
        self.default_voice = config.get('default_voice', 'onyx')

    async def generate_speech(
        self,
        text: str,
        voice_config: VoiceConfig,
        **kwargs
    ) -> bytes:
        """Generate speech audio from text using OpenAI TTS

        Args:
            text: Text to convert to speech
            voice_config: Voice configuration settings
            **kwargs: Additional OpenAI TTS parameters

        Returns:
            Audio data as bytes (MP3 format)
        """
        # Use voice config or defaults
        # Voice selection is handled by PersonaService via VoiceCatalog
        # For OpenAI, voice_id and voice_name are the same (e.g., 'onyx', 'echo')
        model = voice_config.model or self.default_model
        voice = voice_config.voice_id or voice_config.voice_name or self.default_voice
        speed = voice_config.speed

        # OpenAI TTS doesn't support language parameter - it auto-detects
        # Remove it from kwargs if present
        kwargs.pop('language', None)

        # Validate voice
        if voice not in self.SUPPORTED_VOICES:
            voice = self.default_voice

        # Validate model
        if model not in self.SUPPORTED_MODELS:
            model = self.default_model

        # Clamp speed to valid range (0.25 to 4.0)
        speed = max(0.25, min(4.0, speed))

        try:
            # Generate audio
            response = await self.client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                speed=speed,
                **kwargs
            )

            # Return audio bytes
            return response.content

        except Exception as e:
            raise RuntimeError(f"OpenAI TTS generation failed: {e}")

    def get_supported_voices(self) -> List[str]:
        """Get list of supported voice IDs"""
        return self.SUPPORTED_VOICES

    def get_provider_name(self) -> str:
        """Get the name of the TTS provider"""
        return "OpenAI TTS"