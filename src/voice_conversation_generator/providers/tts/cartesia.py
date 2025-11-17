"""
Cartesia TTS Provider Implementation
"""
import os
from typing import Dict, Any, List
from cartesia import AsyncCartesia
from ...models import VoiceConfig
from ..base import TTSProvider


class CartesiaTTSProvider(TTSProvider):
    """Cartesia Text-to-Speech provider using Sonic models"""

    # Default voice IDs for different personas
    DEFAULT_VOICES = {
        # English voices
        'support_male_en': 'a0e99841-438c-4a64-b679-ae501e7d6091',  # Professional male (English)
        'support_female_en': 'f9836c6e-a0bd-460e-9d3c-f7299fa60f94',  # Professional female (English)
        'customer_male_en': 'a167e0f3-df7e-4d52-a9c3-f949145efdab',  # Customer support man (English)
        'customer_female_en': '6ccbfb76-1fc6-48f7-b71d-91ac6298247b',  # Natural female (English)

        # Hindi/Hinglish voices
        'support_male_hi': 'fd2ada67-c2d9-4afe-b474-6386b87d8fc3',  # Ishan - Conversational male for Hinglish sales and customer support
        'support_male_hinglish': 'fd2ada67-c2d9-4afe-b474-6386b87d8fc3',  # Ishan (alias)
        'customer_male_hi': '1259b7e3-cb8a-43df-9446-30971a46b8b0',  # Devansh - Warm, conversational Indian male
        'customer_male_hinglish': '1259b7e3-cb8a-43df-9446-30971a46b8b0',  # Devansh (alias)

        # Generic defaults (use Hinglish for Indian context)
        'support_male': 'fd2ada67-c2d9-4afe-b474-6386b87d8fc3',  # Ishan
        'customer_male': '1259b7e3-cb8a-43df-9446-30971a46b8b0',  # Devansh
        'default': 'fd2ada67-c2d9-4afe-b474-6386b87d8fc3'  # Ishan for default
    }

    SUPPORTED_MODELS = ['sonic-3', 'sonic-2', 'sonic-turbo']
    SUPPORTED_LANGUAGES = [
        'en', 'fr', 'de', 'es', 'pt', 'zh', 'ja', 'hi', 'it', 'ko',
        'nl', 'pl', 'ru', 'sv', 'tr'
    ]

    def __init__(self, config: Dict[str, Any]):
        """Initialize Cartesia TTS client

        Config should include:
        - api_key: Cartesia API key (or from env CARTESIA_API_KEY)
        - model: Sonic model ('sonic-3', 'sonic-2', or 'sonic-turbo')
        - default_voice: Default voice ID to use
        - language: Default language code (default: 'en')
        - output_format: Output audio format configuration
        """
        super().__init__(config)

        # Get API key from config or environment
        api_key = config.get('api_key') or os.getenv('CARTESIA_API_KEY')
        if not api_key:
            raise ValueError("Cartesia API key not found in config or environment")

        # Initialize async client
        self.client = AsyncCartesia(api_key=api_key)

        # Set defaults - validate model is a Cartesia model, not from another provider
        config_model = config.get('model', 'sonic-3')
        if config_model not in self.SUPPORTED_MODELS:
            # Config contains non-Cartesia model (e.g., "tts-1" from OpenAI), use default
            self.default_model = 'sonic-3'
        else:
            self.default_model = config_model

        self.default_voice = config.get('default_voice', self.DEFAULT_VOICES['default'])
        self.default_language = config.get('language', 'en')

        # Output format configuration
        self.output_format = config.get('output_format', {
            'container': 'raw',  # Use raw for better compatibility
            'encoding': 'pcm_s16le',  # 16-bit PCM for MP3 conversion
            'sample_rate': 44100
        })

    async def generate_speech(
        self,
        text: str,
        voice_config: VoiceConfig,
        **kwargs
    ) -> bytes:
        """Generate speech audio from text using Cartesia TTS

        Args:
            text: Text to convert to speech
            voice_config: Voice configuration settings
            **kwargs: Additional Cartesia TTS parameters

        Returns:
            Audio data as bytes (PCM format)
        """
        # Use voice config or defaults
        # Note: Always use Cartesia's default_model, not voice_config.model
        # voice_config.model may contain provider-specific model names (e.g., "tts-1" for OpenAI)
        model = self.default_model
        voice_id = voice_config.voice_id or voice_config.voice_name or self.default_voice
        language = kwargs.pop('language', self.default_language)  # Use pop() to remove from kwargs

        # Validate model
        if model not in self.SUPPORTED_MODELS:
            model = self.default_model

        # Validate language
        if language not in self.SUPPORTED_LANGUAGES:
            language = self.default_language

        # Map common voice names to Cartesia voice IDs
        # For Hindi/Hinglish (hi language), use Indian voices
        # For English/other languages, use default English voices
        is_hindi = language in ['hi', 'hindi', 'hinglish']

        voice_name_mapping_hi = {
            # Hindi/Hinglish mappings (use Indian voices)
            'onyx': 'fd2ada67-c2d9-4afe-b474-6386b87d8fc3',  # Ishan for support
            'alloy': '1259b7e3-cb8a-43df-9446-30971a46b8b0',  # Devansh for customer
            'echo': '1259b7e3-cb8a-43df-9446-30971a46b8b0',  # Devansh for male customer
            'fable': '1259b7e3-cb8a-43df-9446-30971a46b8b0',  # Devansh for elderly male
            'nova': '6ccbfb76-1fc6-48f7-b71d-91ac6298247b',  # Fallback to English female (TODO: add Hindi female)
            'shimmer': '6ccbfb76-1fc6-48f7-b71d-91ac6298247b',  # Fallback to English female (TODO: add Hindi female)
        }

        voice_name_mapping_en = {
            # English mappings
            'onyx': 'a0e99841-438c-4a64-b679-ae501e7d6091',  # Professional male
            'alloy': 'a0e99841-438c-4a64-b679-ae501e7d6091',  # Professional male
            'echo': 'a167e0f3-df7e-4d52-a9c3-f949145efdab',  # Customer support man
            'fable': 'a0e99841-438c-4a64-b679-ae501e7d6091',  # Professional male
            'nova': 'f9836c6e-a0bd-460e-9d3c-f7299fa60f94',  # Professional female
            'shimmer': '6ccbfb76-1fc6-48f7-b71d-91ac6298247b',  # Natural female
        }

        # Choose mapping based on language
        voice_name_mapping = voice_name_mapping_hi if is_hindi else voice_name_mapping_en

        # If voice_id is a name from our defaults or OpenAI mapping, resolve it
        if voice_id in self.DEFAULT_VOICES:
            voice_id = self.DEFAULT_VOICES[voice_id]
        elif voice_id in voice_name_mapping:
            voice_id = voice_name_mapping[voice_id]

        try:
            # Generate audio using bytes streaming method
            bytes_iter = self.client.tts.bytes(
                model_id=model,
                transcript=text,
                voice={
                    "mode": "id",
                    "id": voice_id,
                },
                language=language,
                output_format=self.output_format,
                **kwargs
            )

            # Collect all audio chunks
            audio_chunks = []
            async for chunk in bytes_iter:
                audio_chunks.append(chunk)

            # Combine all chunks into single bytes object
            audio_data = b''.join(audio_chunks)

            # Convert PCM to MP3 if needed (for consistency with other providers)
            if self.output_format.get('container') == 'raw':
                audio_data = self._convert_pcm_to_mp3(audio_data)

            return audio_data

        except Exception as e:
            raise RuntimeError(f"Cartesia TTS generation failed: {e}")

    def _convert_pcm_to_mp3(self, pcm_data: bytes) -> bytes:
        """Convert PCM audio data to MP3 format

        Args:
            pcm_data: Raw PCM audio bytes

        Returns:
            MP3 encoded audio bytes
        """
        try:
            # Try to use pydub for conversion
            from pydub import AudioSegment
            import io

            # Create audio segment from raw PCM
            audio = AudioSegment(
                data=pcm_data,
                sample_width=2,  # 16-bit = 2 bytes
                frame_rate=self.output_format.get('sample_rate', 44100),
                channels=1  # Mono
            )

            # Export as MP3
            mp3_buffer = io.BytesIO()
            audio.export(mp3_buffer, format='mp3', bitrate='128k')
            return mp3_buffer.getvalue()

        except ImportError:
            # If pydub is not available, return raw PCM
            # User should install: pip install pydub
            print("Warning: pydub not installed. Returning raw PCM audio. Install with: pip install pydub")
            return pcm_data
        except Exception as e:
            print(f"Warning: PCM to MP3 conversion failed: {e}. Returning raw PCM.")
            return pcm_data

    def get_supported_voices(self) -> List[str]:
        """Get list of default voice IDs"""
        return list(self.DEFAULT_VOICES.keys())

    def get_provider_name(self) -> str:
        """Get the name of the TTS provider"""
        return f"Cartesia TTS ({self.default_model})"
