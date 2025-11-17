"""
Persona Model - Defines the structure for customer and support agent personas
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class PersonaType(Enum):
    """Types of personas in the system"""
    CUSTOMER = "customer"
    SUPPORT = "support"


class EmotionalState(Enum):
    """Emotional states for customer personas"""
    NEUTRAL = "neutral"
    ANGRY = "angry"
    CONFUSED = "confused"
    HAPPY = "happy"
    FRUSTRATED = "frustrated"
    ANXIOUS = "anxious"


@dataclass
class VoiceConfig:
    """Voice configuration for TTS generation"""
    provider: str = "openai"  # openai, elevenlabs
    voice_id: Optional[str] = None
    model: Optional[str] = None
    speed: float = 1.0

    # ElevenLabs specific
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.2
    use_speaker_boost: bool = False

    # OpenAI specific
    voice_name: Optional[str] = None  # onyx, echo, etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "provider": self.provider,
            "voice_id": self.voice_id,
            "model": self.model,
            "speed": self.speed,
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
            "style": self.style,
            "use_speaker_boost": self.use_speaker_boost,
            "voice_name": self.voice_name
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VoiceConfig':
        """Create from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Persona:
    """Base persona class for both customer and support agents"""
    id: Optional[str] = None
    name: str = ""
    type: PersonaType = PersonaType.CUSTOMER
    personality: str = ""
    system_prompt: str = ""
    guardrails: List[str] = field(default_factory=list)
    voice_config: VoiceConfig = field(default_factory=VoiceConfig)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "personality": self.personality,
            "system_prompt": self.system_prompt,
            "guardrails": self.guardrails,
            "voice_config": self.voice_config.to_dict(),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Persona':
        """Create from dictionary"""
        # Handle voice config
        voice_config_data = data.get("voice_config", {})
        voice_config = VoiceConfig.from_dict(voice_config_data) if voice_config_data else VoiceConfig()

        # Handle persona type
        persona_type = PersonaType(data.get("type", "customer"))

        # Handle datetime fields
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None

        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            type=persona_type,
            personality=data.get("personality", ""),
            system_prompt=data.get("system_prompt", ""),
            guardrails=data.get("guardrails", []),
            voice_config=voice_config,
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at
        )


@dataclass
class CustomerPersona(Persona):
    """Customer-specific persona with scenario details"""
    emotional_state: EmotionalState = EmotionalState.NEUTRAL
    issue: str = ""
    goal: str = ""
    special_behavior: str = ""
    difficulty: str = "medium"  # easy, medium, hard
    languages: List[str] = field(default_factory=lambda: ['en'])  # Languages spoken by this persona

    def __post_init__(self):
        """Ensure type is set to CUSTOMER"""
        self.type = PersonaType.CUSTOMER

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        base_dict = super().to_dict()
        base_dict.update({
            "emotional_state": self.emotional_state.value,
            "issue": self.issue,
            "goal": self.goal,
            "special_behavior": self.special_behavior,
            "difficulty": self.difficulty,
            "languages": self.languages
        })
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CustomerPersona':
        """Create from dictionary"""
        # Get base persona fields
        base_persona = Persona.from_dict(data)

        # Handle emotional state
        emotional_state = EmotionalState(data.get("emotional_state", "neutral"))

        return cls(
            id=base_persona.id,
            name=base_persona.name,
            type=base_persona.type,
            personality=base_persona.personality,
            system_prompt=base_persona.system_prompt,
            guardrails=base_persona.guardrails,
            voice_config=base_persona.voice_config,
            metadata=base_persona.metadata,
            created_at=base_persona.created_at,
            updated_at=base_persona.updated_at,
            emotional_state=emotional_state,
            issue=data.get("issue", ""),
            goal=data.get("goal", ""),
            special_behavior=data.get("special_behavior", ""),
            difficulty=data.get("difficulty", "medium"),
            languages=data.get("languages", ["en"])
        )


@dataclass
class SupportPersona(Persona):
    """Support agent-specific persona"""
    company_name: str = ""
    agent_name: str = ""
    policies: List[str] = field(default_factory=list)
    escalation_triggers: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Ensure type is set to SUPPORT"""
        self.type = PersonaType.SUPPORT

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        base_dict = super().to_dict()
        base_dict.update({
            "company_name": self.company_name,
            "agent_name": self.agent_name,
            "policies": self.policies,
            "escalation_triggers": self.escalation_triggers
        })
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SupportPersona':
        """Create from dictionary"""
        # Get base persona fields
        base_persona = Persona.from_dict(data)

        return cls(
            id=base_persona.id,
            name=base_persona.name,
            type=base_persona.type,
            personality=base_persona.personality,
            system_prompt=base_persona.system_prompt,
            guardrails=base_persona.guardrails,
            voice_config=base_persona.voice_config,
            metadata=base_persona.metadata,
            created_at=base_persona.created_at,
            updated_at=base_persona.updated_at,
            company_name=data.get("company_name", ""),
            agent_name=data.get("agent_name", ""),
            policies=data.get("policies", []),
            escalation_triggers=data.get("escalation_triggers", [])
        )