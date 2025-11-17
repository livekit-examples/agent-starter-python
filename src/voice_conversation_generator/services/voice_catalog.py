"""
Voice Catalog Service - Centralized voice mapping for all TTS providers
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Union


@dataclass
class VoiceEntry:
    """Single voice entry in the catalog"""
    voice_id: str              # Provider-specific voice ID
    provider: str              # 'cartesia', 'openai', 'elevenlabs'
    name: str                  # Human-readable name (e.g., "Ishan", "Aarti")
    gender: str                # 'male', 'female'
    languages: Set[str]        # e.g., {'hi', 'en'} for multi-language voices
    accents: Set[str]          # e.g., {'india', 'us', 'uk', 'canada'}
    persona_types: Set[str]    # e.g., {'support_agent', 'customer'}
    description: str           # Brief description of the voice
    priority: int = 0          # Higher number = higher priority for tie-breaking


class VoiceCatalog:
    """Centralized catalog for managing voices across all TTS providers"""

    def __init__(self):
        """Initialize the voice catalog with all available voices"""
        self._voices: List[VoiceEntry] = []
        self._initialize_catalog()

    def _initialize_catalog(self):
        """Populate catalog with all voices from all providers"""

        # ============================================================
        # CARTESIA VOICES
        # ============================================================

        # Hindi/Hinglish voices
        self._voices.extend([
            # Ishan - Multi-language Hinglish support agent (BEST for support)
            VoiceEntry(
                voice_id='fd2ada67-c2d9-4afe-b474-6386b87d8fc3',
                provider='cartesia',
                name='Ishan',
                gender='male',
                languages={'hi', 'en'},  # Speaks BOTH Hindi and English fluently
                accents={'india'},
                persona_types={'support_agent'},  # SUPPORT ONLY - never customer
                description='Conversational male for Hinglish sales and customer support',
                priority=8  # Good for Hinglish/English support
            ),

            # Devansh - Hindi-only support agent
            VoiceEntry(
                voice_id='1259b7e3-cb8a-43df-9446-30971a46b8b0',
                provider='cartesia',
                name='Devansh',
                gender='male',
                languages={'hi'},
                accents={'india'},
                persona_types={'support_agent'},  # SUPPORT ONLY - never customer
                description='Warm, conversational Indian male adult voice for Hindi support',
                priority=10  # Preferred for Hindi-only support (higher than Ishan)
            ),

            # Ayush - Hindi male customer
            VoiceEntry(
                voice_id='791d5162-d5eb-40f0-8189-f19db44611d8',
                provider='cartesia',
                name='Ayush',
                gender='male',
                languages={'hi'},
                accents={'india'},
                persona_types={'customer'},  # CUSTOMER ONLY - never support
                description='Conversation Hindi male voice',
                priority=10  # Preferred for Hindi male customers
            ),

            # Aarti - Hindi female customer
            VoiceEntry(
                voice_id='9cebb910-d4b7-4a4a-85a4-12c79137724c',
                provider='cartesia',
                name='Aarti',
                gender='female',
                languages={'hi'},
                accents={'india'},
                persona_types={'customer'},  # CUSTOMER ONLY - never support
                description='Conversations Hindi female voice',
                priority=10  # Preferred for Hindi female customers
            ),

            # Aarav - English with Indian accent (customer)
            VoiceEntry(
                voice_id='39c3388d-6b3f-4cec-88d7-900bd0899e00',
                provider='cartesia',
                name='Aarav',
                gender='male',
                languages={'en'},
                accents={'india'},
                persona_types={'customer'},  # CUSTOMER ONLY - never support
                description='Conversation English male with Indian accent',
                priority=10  # Preferred for English male customers
            ),
        ])

        # English US voices for Cartesia
        self._voices.extend([
            # Professional male voices
            VoiceEntry(
                voice_id='a0e99841-438c-4a64-b679-ae501e7d6091',
                provider='cartesia',
                name='Professional Male',
                gender='male',
                languages={'en'},
                accents={'us'},
                persona_types={'support_agent'},
                description='Professional US English male voice'
            ),

            VoiceEntry(
                voice_id='a167e0f3-df7e-4d52-a9c3-f949145efdab',
                provider='cartesia',
                name='Customer Support Male',
                gender='male',
                languages={'en'},
                accents={'us'},
                persona_types={'customer', 'support_agent'},
                description='Customer support US English male voice'
            ),

            # Female voices
            VoiceEntry(
                voice_id='f9836c6e-a0bd-460e-9d3c-f7299fa60f94',
                provider='cartesia',
                name='Professional Female',
                gender='female',
                languages={'en'},
                accents={'us'},
                persona_types={'support_agent'},
                description='Professional US English female voice'
            ),

            VoiceEntry(
                voice_id='6ccbfb76-1fc6-48f7-b71d-91ac6298247b',
                provider='cartesia',
                name='Natural Female',
                gender='female',
                languages={'en'},
                accents={'us'},
                persona_types={'customer'},
                description='Natural US English female voice'
            ),
        ])

        # ============================================================
        # OPENAI VOICES (All US English only)
        # ============================================================

        self._voices.extend([
            # Male voices
            VoiceEntry(
                voice_id='onyx',
                provider='openai',
                name='Onyx',
                gender='male',
                languages={'en'},
                accents={'us'},
                persona_types={'support_agent'},
                description='Deep, authoritative male voice'
            ),

            VoiceEntry(
                voice_id='echo',
                provider='openai',
                name='Echo',
                gender='male',
                languages={'en'},
                accents={'us'},
                persona_types={'customer'},
                description='Clear, friendly male voice'
            ),

            VoiceEntry(
                voice_id='fable',
                provider='openai',
                name='Fable',
                gender='male',
                languages={'en'},
                accents={'us'},
                persona_types={'customer'},
                description='Warm, older-sounding male voice'
            ),

            VoiceEntry(
                voice_id='alloy',
                provider='openai',
                name='Alloy',
                gender='male',
                languages={'en'},
                accents={'us'},
                persona_types={'support_agent', 'customer'},
                description='Neutral, versatile male voice'
            ),

            # Female voices
            VoiceEntry(
                voice_id='nova',
                provider='openai',
                name='Nova',
                gender='female',
                languages={'en'},
                accents={'us'},
                persona_types={'customer'},
                description='Bright, energetic female voice'
            ),

            VoiceEntry(
                voice_id='shimmer',
                provider='openai',
                name='Shimmer',
                gender='female',
                languages={'en'},
                accents={'us'},
                persona_types={'customer'},
                description='Soft, gentle female voice'
            ),
        ])

        # ============================================================
        # ELEVENLABS VOICES (All US English only)
        # ============================================================

        self._voices.extend([
            VoiceEntry(
                voice_id='2EiwWnXFnvU5JabPnv8n',  # Clyde
                provider='elevenlabs',
                name='Clyde',
                gender='male',
                languages={'en'},
                accents={'us'},
                persona_types={'support_agent'},
                description='Mature, authoritative male voice'
            ),

            VoiceEntry(
                voice_id='EXAVITQu4vr4xnSDxMaL',  # Sarah
                provider='elevenlabs',
                name='Sarah',
                gender='female',
                languages={'en'},
                accents={'us'},
                persona_types={'customer'},
                description='Friendly female voice'
            ),

            VoiceEntry(
                voice_id='CYw3kZ02Hs0563khs1Fj',  # Roger
                provider='elevenlabs',
                name='Roger',
                gender='male',
                languages={'en'},
                accents={'us'},
                persona_types={'customer'},
                description='Confident male voice'
            ),
        ])

    def get_voice(
        self,
        provider: str,
        languages: Union[str, List[str]],
        accent: str = 'india',
        gender: str = 'male',
        persona_type: str = 'customer'
    ) -> Optional[VoiceEntry]:
        """
        Get the best matching voice with tiered fallback strategy

        Tier 1: Exact match - ALL criteria must match including ALL languages
        Tier 2: Flexible match - voice must support AT LEAST ONE requested language
        Tier 3: Provider default - return default voice for the provider

        Args:
            provider: TTS provider ('cartesia', 'openai', 'elevenlabs')
            languages: Single language string or list of languages (e.g., 'hi' or ['hi', 'en'])
            accent: Preferred accent (default: 'india')
            gender: Voice gender (default: 'male')
            persona_type: Persona type (default: 'customer')

        Returns:
            VoiceEntry or None if no default available
        """
        # Normalize languages to set
        if isinstance(languages, str):
            required_langs = {languages}
        else:
            required_langs = set(languages)

        # TIER 1: Strict match - voice must support ALL requested languages
        voice = self._find_exact_match(provider, required_langs, accent, gender, persona_type)
        if voice:
            return voice

        # TIER 2: Flexible match - voice supports ANY requested language
        voice = self._find_flexible_match(provider, required_langs, accent, gender, persona_type)
        if voice:
            return voice

        # TIER 3: Provider default
        return self._get_default_voice(provider)

    def _find_exact_match(
        self,
        provider: str,
        required_langs: Set[str],
        accent: str,
        gender: str,
        persona_type: str
    ) -> Optional[VoiceEntry]:
        """Find voice that matches ALL criteria including ALL languages"""
        matches = []
        for voice in self._voices:
            if voice.provider != provider:
                continue

            # Voice must support ALL requested languages (subset check)
            if not required_langs.issubset(voice.languages):
                continue

            # All other criteria must match exactly
            if accent not in voice.accents:
                continue
            if gender != voice.gender:
                continue
            if persona_type not in voice.persona_types:
                continue

            matches.append(voice)

        # Sort by priority (highest first) and return best match
        if matches:
            return sorted(matches, key=lambda v: v.priority, reverse=True)[0]

        return None

    def _find_flexible_match(
        self,
        provider: str,
        required_langs: Set[str],
        accent: str,
        gender: str,
        persona_type: str
    ) -> Optional[VoiceEntry]:
        """Find voice that matches most criteria, relaxing language requirement"""
        # Try progressively relaxing requirements

        # First try: Match accent, gender, persona, ANY language
        matches = []
        for voice in self._voices:
            if voice.provider != provider:
                continue
            if not voice.languages.intersection(required_langs):  # ANY language match
                continue
            if accent not in voice.accents:
                continue
            if gender != voice.gender:
                continue
            if persona_type not in voice.persona_types:
                continue

            matches.append(voice)

        if matches:
            return sorted(matches, key=lambda v: v.priority, reverse=True)[0]

        # Second try: Match gender, persona, ANY language (relax accent)
        matches = []
        for voice in self._voices:
            if voice.provider != provider:
                continue
            if not voice.languages.intersection(required_langs):
                continue
            if gender != voice.gender:
                continue
            if persona_type not in voice.persona_types:
                continue

            matches.append(voice)

        if matches:
            return sorted(matches, key=lambda v: v.priority, reverse=True)[0]

        # Third try: Match persona, ANY language (relax accent and gender)
        matches = []
        for voice in self._voices:
            if voice.provider != provider:
                continue
            if not voice.languages.intersection(required_langs):
                continue
            if persona_type not in voice.persona_types:
                continue

            matches.append(voice)

        if matches:
            return sorted(matches, key=lambda v: v.priority, reverse=True)[0]

        return None

    def _get_default_voice(self, provider: str) -> Optional[VoiceEntry]:
        """Get default voice for the provider"""
        # Default priorities by provider
        if provider == 'cartesia':
            # Prefer Ishan (multi-language) for Indian context
            for voice in self._voices:
                if voice.provider == 'cartesia' and voice.name == 'Ishan':
                    return voice

        elif provider == 'openai':
            # Prefer Onyx for OpenAI
            for voice in self._voices:
                if voice.provider == 'openai' and voice.voice_id == 'onyx':
                    return voice

        elif provider == 'elevenlabs':
            # Prefer Clyde for ElevenLabs
            for voice in self._voices:
                if voice.provider == 'elevenlabs' and voice.name == 'Clyde':
                    return voice

        # Fallback: return first voice for provider
        for voice in self._voices:
            if voice.provider == provider:
                return voice

        return None

    def get_all_voices(self, provider: Optional[str] = None) -> List[VoiceEntry]:
        """
        Get all voices, optionally filtered by provider

        Args:
            provider: Optional provider filter

        Returns:
            List of VoiceEntry objects
        """
        if provider:
            return [v for v in self._voices if v.provider == provider]
        return self._voices.copy()

    def get_voice_by_id(self, provider: str, voice_id: str) -> Optional[VoiceEntry]:
        """
        Get a specific voice by provider and voice_id

        Args:
            provider: TTS provider
            voice_id: Voice ID

        Returns:
            VoiceEntry or None
        """
        for voice in self._voices:
            if voice.provider == provider and voice.voice_id == voice_id:
                return voice
        return None


# Global catalog instance
_catalog_instance: Optional[VoiceCatalog] = None


def get_voice_catalog() -> VoiceCatalog:
    """Get the global voice catalog instance (singleton)"""
    global _catalog_instance
    if _catalog_instance is None:
        _catalog_instance = VoiceCatalog()
    return _catalog_instance
