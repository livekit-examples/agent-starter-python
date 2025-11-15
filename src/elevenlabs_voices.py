"""
ElevenLabs Voice Generator for Indian Accents
Provides authentic Indian voices for the testing framework
"""
import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import ElevenLabs, but make it optional
try:
    from elevenlabs import generate, Voice, VoiceSettings, save, set_api_key
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    logger.warning("ElevenLabs not installed. Install with: pip install elevenlabs")


class IndianVoiceGenerator:
    """Generate authentic Indian voices using ElevenLabs"""

    def __init__(self, api_key: Optional[str] = None):
        if not ELEVENLABS_AVAILABLE:
            raise ImportError("ElevenLabs not installed. Run: pip install elevenlabs")

        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY not found in environment")

        # Set the API key for ElevenLabs
        set_api_key(self.api_key)

        # Default voice IDs - use ElevenLabs voice library
        # These would be replaced with cloned Indian voices in production
        self.default_voices = {
            # Male voices
            "support_male": "Antoni",  # Professional male (well-rounded)
            "customer_elderly_male": "Clyde",  # Older male
            "customer_young_male": "Adam",  # Young male

            # Female voices
            "customer_angry_female": "Nicole",  # Assertive female
            "customer_professional_female": "Rachel",  # Professional female
            "customer_elderly_female": "Domi",  # Mature female
        }

        # In production, these would be custom cloned Indian voices
        self.indian_voices = {
            # Support agents
            "faizan_support": None,  # Clone from actual Faizan recording
            "priya_support": None,   # Female support agent

            # Customer personas
            "yash_cooperative": None,  # Cooperative male customer
            "angry_parent": None,     # Frustrated parent
            "elderly_hindi": None,    # Elderly Hindi speaker
            "young_professional": None,  # English-dominant professional
        }

        # Load custom voice mappings if available
        self._load_custom_voices()

    def _load_custom_voices(self):
        """Load custom cloned voice IDs from config file"""
        config_path = Path(".elevenlabs_voices.json")
        if config_path.exists():
            import json
            with open(config_path) as f:
                custom = json.load(f)
                self.indian_voices.update(custom.get("voices", {}))
                logger.info(f"Loaded {len(custom['voices'])} custom voices")

    def get_voice_for_scenario(self, speaker: str, scenario: Dict[str, Any]) -> tuple[str, Dict]:
        """Determine appropriate voice and settings based on speaker and scenario"""

        voice_id = None
        settings = {}

        if speaker == "support":
            # Support agent - professional male (Faizan)
            voice_id = self.indian_voices.get("faizan_support") or "Antoni"
            settings = {
                "stability": 0.7,  # Consistent professional tone
                "similarity_boost": 0.8,
                "style": 0.3,  # Slightly formal
                "use_speaker_boost": True
            }

        else:  # Customer
            # Map scenario to appropriate voice
            scenario_name = scenario.get('name', '')
            emotional_state = scenario.get('emotional_state', 'neutral')

            if "angry" in scenario_name or "angry" in emotional_state.lower():
                voice_id = self.indian_voices.get("angry_parent") or "Nicole"
                settings = {
                    "stability": 0.4,  # More variation for anger
                    "similarity_boost": 0.9,
                    "style": 0.7,  # More expressive
                    "use_speaker_boost": True
                }

            elif "elderly" in scenario_name:
                if "Priya" in scenario.get('customer_name', ''):
                    voice_id = self.indian_voices.get("elderly_hindi") or "Domi"
                else:
                    voice_id = self.indian_voices.get("elderly_hindi") or "Clyde"
                settings = {
                    "stability": 0.6,
                    "similarity_boost": 0.7,
                    "style": 0.2,  # Slower, more deliberate
                    "use_speaker_boost": True
                }

            elif "cooperative" in scenario_name:
                voice_id = self.indian_voices.get("yash_cooperative") or "Adam"
                settings = {
                    "stability": 0.7,
                    "similarity_boost": 0.8,
                    "style": 0.5,  # Natural conversation
                    "use_speaker_boost": True
                }

            elif "professional" in scenario.get('personality', '').lower():
                voice_id = self.indian_voices.get("young_professional") or "Rachel"
                settings = {
                    "stability": 0.8,
                    "similarity_boost": 0.8,
                    "style": 0.4,  # Clear and articulate
                    "use_speaker_boost": True
                }

            else:
                # Default customer voice
                voice_id = "Adam"
                settings = {
                    "stability": 0.6,
                    "similarity_boost": 0.75,
                    "style": 0.5,
                    "use_speaker_boost": True
                }

        return voice_id, settings

    async def generate_speech(
        self,
        text: str,
        speaker: str,
        scenario: Dict[str, Any],
        output_format: str = "mp3_44100_128"
    ) -> bytes:
        """Generate speech with appropriate Indian voice"""

        voice_id, voice_settings = self.get_voice_for_scenario(speaker, scenario)

        # Add emotion cues to text for better synthesis
        emotion = scenario.get('emotional_state', 'neutral')
        if emotion == 'angry' and '!' not in text:
            text = text.rstrip('.') + '!'  # Add emphasis
        elif emotion == 'confused' and '?' not in text:
            text = text.rstrip('.') + '?'  # Add questioning tone

        try:
            # Use the simple generate API
            # Note: Using voice names instead of IDs for default voices
            voice_name = voice_id  # For now, use the name directly

            audio = generate(
                text=text,
                voice=voice_name,  # Can be name like "Adam" or voice_id
                model="eleven_turbo_v2_5"  # Fast model for demos
            )

            # Convert generator to bytes if needed
            if hasattr(audio, '__iter__') and not isinstance(audio, bytes):
                audio = b"".join(audio)

            return audio

        except Exception as e:
            logger.error(f"ElevenLabs generation failed: {e}")
            # Fallback to OpenAI TTS
            return None

    def clone_voice(self, name: str, audio_file: str, description: str = "") -> str:
        """Clone a voice from audio sample (requires Creator plan)"""
        # Note: Voice cloning requires paid plan
        logger.warning("Voice cloning requires Creator plan or higher")
        return None

    def list_available_voices(self) -> list:
        """List available default voices"""
        # Return default ElevenLabs voices
        return [
            {"name": "Adam", "description": "Middle-aged American male"},
            {"name": "Antoni", "description": "Well-rounded American male"},
            {"name": "Arnold", "description": "Crisp American male"},
            {"name": "Callum", "description": "Hoarse American male"},
            {"name": "Charlie", "description": "Casual American male"},
            {"name": "Charlotte", "description": "Seductive American female"},
            {"name": "Clyde", "description": "War veteran American male"},
            {"name": "Daniel", "description": "Deep British male"},
            {"name": "Dave", "description": "Young British-Essex male"},
            {"name": "Domi", "description": "Strong American female"},
            {"name": "Dorothy", "description": "Pleasant British female"},
            {"name": "Elli", "description": "Emotional American female"},
            {"name": "Emily", "description": "Calm American female"},
            {"name": "Ethan", "description": "Soft American male"},
            {"name": "Freya", "description": "Overhyped American female"},
            {"name": "Gigi", "description": "Childish American female"},
            {"name": "Giovanni", "description": "Foreigner English-Italian male"},
            {"name": "Glinda", "description": "Witch American female"},
            {"name": "Grace", "description": "Gentle Southern American female"},
            {"name": "Harry", "description": "Anxious American male"},
            {"name": "James", "description": "Calm Australian male"},
            {"name": "Jeremy", "description": "Excited American-Irish male"},
            {"name": "Jessie", "description": "Raspy American male"},
            {"name": "Joseph", "description": "Ground British male"},
            {"name": "Josh", "description": "Young American male"},
            {"name": "Liam", "description": "Articulate American male"},
            {"name": "Matilda", "description": "Warm American female"},
            {"name": "Matthew", "description": "AudioBook British male"},
            {"name": "Michael", "description": "Orotund American male"},
            {"name": "Mimi", "description": "Childish British female"},
            {"name": "Nicole", "description": "Whisper American female"},
            {"name": "Patrick", "description": "Shouty American male"},
            {"name": "Rachel", "description": "Calm American female"},
            {"name": "Ryan", "description": "Soldier American male"},
            {"name": "Sam", "description": "Raspy American male"},
            {"name": "Serena", "description": "Pleasant American female"},
            {"name": "Thomas", "description": "Calm American male"},
        ]


# Helper function for testing
async def test_elevenlabs():
    """Test ElevenLabs with Hindi-English text"""
    generator = IndianVoiceGenerator()

    test_scenario = {
        "name": "test",
        "customer_name": "Yash",
        "emotional_state": "neutral"
    }

    # Test support agent voice
    support_text = "Namaste, main Faizan bol raha hun Jodo se. Kya main Yash se baat kar raha hun?"
    audio = await generator.generate_speech(support_text, "support", test_scenario)

    if audio:
        with open("test_support_elevenlabs.mp3", "wb") as f:
            f.write(audio)
        print("Generated: test_support_elevenlabs.mp3")

    # Test customer voice
    customer_text = "Ji haan, main Yash hun. Kya baat hai?"
    audio = await generator.generate_speech(customer_text, "customer", test_scenario)

    if audio:
        with open("test_customer_elevenlabs.mp3", "wb") as f:
            f.write(audio)
        print("Generated: test_customer_elevenlabs.mp3")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_elevenlabs())