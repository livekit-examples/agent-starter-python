"""
Simple ElevenLabs Voice Generator for Testing
Uses the new ElevenLabs v2 API
"""
import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables - try both locations
load_dotenv(".env.local")  # When run from project root
load_dotenv("../.env.local")  # When run from src directory

logger = logging.getLogger(__name__)

# Try to import ElevenLabs
try:
    from elevenlabs import ElevenLabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    logger.warning("ElevenLabs not installed. Install with: pip install elevenlabs")


class SimpleVoiceGenerator:
    """Simple ElevenLabs voice generator"""

    def __init__(self, api_key: Optional[str] = None):
        if not ELEVENLABS_AVAILABLE:
            raise ImportError("ElevenLabs not installed. Run: uv add elevenlabs")

        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY not found in environment")

        # Initialize client
        self.client = ElevenLabs(api_key=self.api_key)

    def get_voice_for_speaker(self, speaker: str, scenario: Dict[str, Any]) -> str:
        """Get appropriate voice ID based on speaker and scenario"""

        # Use built-in ElevenLabs voices (these are actual voice IDs)
        if speaker == "support":
            # Male support agent voice (Clyde - mature male)
            return "2EiwWnXFnvU5JabPnv8n"
        else:
            # Customer voices based on scenario
            emotion = scenario.get('emotional_state', 'neutral')
            customer_name = scenario.get('customer_name', '')

            if 'Priya' in customer_name or 'female' in scenario.get('personality', '').lower():
                # Female voice (Sarah)
                return "EXAVITQu4vr4xnSDxMaL"
            elif 'angry' in emotion.lower():
                # Assertive male (Roger)
                return "CwhRBWXzGAHq8TQ4Fs17"
            elif 'elderly' in scenario.get('name', ''):
                # Older voice (Clyde also works for elderly)
                return "2EiwWnXFnvU5JabPnv8n"
            else:
                # Default customer voice (Roger)
                return "CwhRBWXzGAHq8TQ4Fs17"

    async def generate_speech(
        self,
        text: str,
        speaker: str,
        scenario: Dict[str, Any]
    ) -> bytes:
        """Generate speech using ElevenLabs"""

        voice_id = self.get_voice_for_speaker(speaker, scenario)

        try:
            # Use the text_to_speech.convert method (synchronous)
            # Run in executor to avoid blocking
            import asyncio
            loop = asyncio.get_event_loop()

            def _generate():
                # Check for custom parameters from parent simulator
                voice_settings = {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }

                # Use speaker-specific parameters if available
                if hasattr(self, 'custom_params'):
                    if speaker == "customer" and 'customer' in self.custom_params:
                        voice_settings.update(self.custom_params['customer'])
                    elif speaker == "support" and 'support' in self.custom_params:
                        voice_settings.update(self.custom_params['support'])
                    else:
                        voice_settings.update(self.custom_params)

                audio_response = self.client.text_to_speech.convert(
                    text=text,
                    voice_id=voice_id,
                    model_id="eleven_turbo_v2_5",  # Turbo model works on free tier
                    voice_settings=voice_settings
                )

                # Collect all chunks into bytes
                audio_bytes = b""
                for chunk in audio_response:
                    if chunk:
                        audio_bytes += chunk
                return audio_bytes

            # Run synchronous method in thread pool
            audio_bytes = await loop.run_in_executor(None, _generate)
            return audio_bytes

        except Exception as e:
            logger.error(f"ElevenLabs generation failed: {e}")
            return None


# Test function
if __name__ == "__main__":
    import asyncio

    async def test():
        generator = SimpleVoiceGenerator()

        test_scenario = {"name": "test", "emotional_state": "neutral"}

        # Test support voice
        audio = await generator.generate_speech(
            "Hello, this is support speaking.",
            "support",
            test_scenario
        )

        if audio:
            with open("test_elevenlabs.mp3", "wb") as f:
                f.write(audio)
            print("Generated test_elevenlabs.mp3")
        else:
            print("Generation failed")

    asyncio.run(test())