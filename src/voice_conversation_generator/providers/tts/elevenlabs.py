"""
ElevenLabs TTS Provider Implementation
"""
import os
import asyncio
from typing import Dict, Any, List, Optional
from ...models import VoiceConfig
from ..base import TTSProvider


class ElevenLabsTTSProvider(TTSProvider):
    """ElevenLabs Text-to-Speech provider"""

    # Default voice IDs for different personas
    DEFAULT_VOICES = {
        'support': '2EiwWnXFnvU5JabPnv8n',  # Clyde - mature male
        'customer_female': 'EXAVITQu4vr4xnSDxMaL',  # Sarah
        'customer_male': 'CwhRBWXzGAHq8TQ4Fs17',  # Roger
    }

    def __init__(self, config: Dict[str, Any]):
        """Initialize ElevenLabs TTS client

        Config should include:
        - api_key: ElevenLabs API key (or from env ELEVENLABS_API_KEY)
        - model: TTS model (default: 'eleven_turbo_v2_5')
        - default_voice_id: Default voice ID
        """
        super().__init__(config)

        # Get API key from config or environment
        api_key = config.get('api_key') or os.getenv('ELEVENLABS_API_KEY')
        if not api_key:
            raise ValueError("ElevenLabs API key not found in config or environment")

        # Try to import ElevenLabs
        try:
            from elevenlabs import ElevenLabs
            self.client = ElevenLabs(api_key=api_key)
            self.available = True
        except ImportError:
            self.available = False
            raise ImportError("ElevenLabs package not installed. Run: uv add elevenlabs")

        # Set defaults
        self.default_model = config.get('model', 'eleven_turbo_v2_5')
        self.default_voice_id = config.get('default_voice_id', self.DEFAULT_VOICES['support'])

    async def generate_speech(
        self,
        text: str,
        voice_config: VoiceConfig,
        **kwargs
    ) -> bytes:
        """Generate speech audio from text using ElevenLabs

        Args:
            text: Text to convert to speech
            voice_config: Voice configuration settings
            **kwargs: Additional ElevenLabs parameters (e.g., speaker_type)

        Returns:
            Audio data as bytes (MP3 format)
        """
        if not self.available:
            raise RuntimeError("ElevenLabs client not available")

        # Voice selection is handled by PersonaService via VoiceCatalog
        # The voice_id should already be a valid ElevenLabs voice ID
        voice_id = voice_config.voice_id or self.default_voice_id

        # Build voice settings
        voice_settings = {
            "stability": voice_config.stability,
            "similarity_boost": voice_config.similarity_boost
        }

        # Add optional settings if supported by the model
        if hasattr(voice_config, 'style'):
            voice_settings["style"] = voice_config.style
        if hasattr(voice_config, 'use_speaker_boost'):
            voice_settings["use_speaker_boost"] = voice_config.use_speaker_boost

        try:
            # Run synchronous ElevenLabs in executor to avoid blocking
            loop = asyncio.get_event_loop()

            def _generate():
                """Synchronous generation function"""
                audio_response = self.client.text_to_speech.convert(
                    text=text,
                    voice_id=voice_id,
                    model_id=self.default_model,
                    voice_settings=voice_settings
                )

                # Collect all chunks into bytes
                audio_bytes = b""
                for chunk in audio_response:
                    if chunk:
                        audio_bytes += chunk
                return audio_bytes

            # Run in executor
            audio_bytes = await loop.run_in_executor(None, _generate)
            return audio_bytes

        except Exception as e:
            raise RuntimeError(f"ElevenLabs TTS generation failed: {e}")

    def get_supported_voices(self) -> List[str]:
        """Get list of supported voice IDs"""
        # Return default voice IDs
        # In production, could fetch from ElevenLabs API
        return list(self.DEFAULT_VOICES.values())

    def get_provider_name(self) -> str:
        """Get the name of the TTS provider"""
        return "ElevenLabs"