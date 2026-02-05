"""
Conversation Model - Defines the structure for conversations and turns
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TurnType(Enum):
    """Types of conversation turns"""
    CUSTOMER = "customer"
    SUPPORT = "support"
    SYSTEM = "system"


@dataclass
class Turn:
    """Represents a single turn in a conversation"""
    id: Optional[str] = None
    conversation_id: Optional[str] = None
    speaker: TurnType = TurnType.CUSTOMER
    text: str = ""
    audio_data: Optional[bytes] = None
    audio_url: Optional[str] = None
    turn_number: int = 0
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Metrics for this turn
    latency_ms: Optional[float] = None
    interruption: bool = False
    speech_rate_wpm: Optional[float] = None

    def to_dict(self, include_audio: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "speaker": self.speaker.value,
            "text": self.text,
            "audio_url": self.audio_url,
            "turn_number": self.turn_number,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata,
            "latency_ms": self.latency_ms,
            "interruption": self.interruption,
            "speech_rate_wpm": self.speech_rate_wpm
        }

        # Optionally include audio data (usually not for JSON)
        if include_audio and self.audio_data:
            result["audio_data_size"] = len(self.audio_data)

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Turn':
        """Create from dictionary"""
        speaker = TurnType(data.get("speaker", "customer"))
        timestamp = datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else None

        return cls(
            id=data.get("id"),
            conversation_id=data.get("conversation_id"),
            speaker=speaker,
            text=data.get("text", ""),
            audio_url=data.get("audio_url"),
            turn_number=data.get("turn_number", 0),
            timestamp=timestamp,
            metadata=data.get("metadata", {}),
            latency_ms=data.get("latency_ms"),
            interruption=data.get("interruption", False),
            speech_rate_wpm=data.get("speech_rate_wpm")
        )


@dataclass
class ConversationConfig:
    """Configuration for conversation generation"""
    max_turns: int = 10
    min_turns: int = 3
    llm_provider: str = "openai"
    llm_model: str = "gpt-4"
    tts_provider: str = "openai"
    stt_provider: Optional[str] = None
    temperature: float = 0.8
    max_tokens: int = 150

    # LiveKit simulation settings
    simulate_livekit: bool = False
    add_network_latency: bool = False
    min_latency_ms: float = 50
    max_latency_ms: float = 200

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "max_turns": self.max_turns,
            "min_turns": self.min_turns,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "tts_provider": self.tts_provider,
            "stt_provider": self.stt_provider,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "simulate_livekit": self.simulate_livekit,
            "add_network_latency": self.add_network_latency,
            "min_latency_ms": self.min_latency_ms,
            "max_latency_ms": self.max_latency_ms
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationConfig':
        """Create from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Conversation:
    """Represents a complete conversation between customer and support"""
    id: Optional[str] = None
    customer_persona_id: Optional[str] = None
    support_persona_id: Optional[str] = None
    scenario_name: str = ""
    turns: List[Turn] = field(default_factory=list)
    config: ConversationConfig = field(default_factory=ConversationConfig)

    # File storage
    audio_url: Optional[str] = None
    transcript_url: Optional[str] = None

    # Timestamps
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_turn(self, speaker: TurnType, text: str, audio_data: Optional[bytes] = None) -> Turn:
        """Add a turn to the conversation"""
        turn = Turn(
            conversation_id=self.id,
            speaker=speaker,
            text=text,
            audio_data=audio_data,
            turn_number=len(self.turns) + 1,
            timestamp=datetime.now()
        )
        self.turns.append(turn)
        return turn

    def get_transcript(self) -> List[Dict[str, str]]:
        """Get transcript as a list of speaker/text pairs"""
        return [
            {
                "speaker": turn.speaker.value,
                "text": turn.text,
                "turn_number": turn.turn_number
            }
            for turn in self.turns
        ]

    def get_conversation_context(self, last_n: int = 6) -> str:
        """Get the last N turns as formatted context"""
        recent_turns = self.turns[-last_n:] if len(self.turns) > last_n else self.turns
        return "\n".join([f"{turn.speaker.value}: {turn.text}" for turn in recent_turns])

    def to_dict(self, include_turns: bool = True) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "id": self.id,
            "customer_persona_id": self.customer_persona_id,
            "support_persona_id": self.support_persona_id,
            "scenario_name": self.scenario_name,
            "config": self.config.to_dict(),
            "audio_url": self.audio_url,
            "transcript_url": self.transcript_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata
        }

        if include_turns:
            result["turns"] = [turn.to_dict() for turn in self.turns]
            result["total_turns"] = len(self.turns)

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        """Create from dictionary"""
        # Handle config
        config_data = data.get("config", {})
        config = ConversationConfig.from_dict(config_data) if config_data else ConversationConfig()

        # Handle turns
        turns = []
        if "turns" in data:
            turns = [Turn.from_dict(turn_data) for turn_data in data["turns"]]

        # Handle datetime fields
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        completed_at = datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None

        return cls(
            id=data.get("id"),
            customer_persona_id=data.get("customer_persona_id"),
            support_persona_id=data.get("support_persona_id"),
            scenario_name=data.get("scenario_name", ""),
            turns=turns,
            config=config,
            audio_url=data.get("audio_url"),
            transcript_url=data.get("transcript_url"),
            created_at=created_at,
            completed_at=completed_at,
            metadata=data.get("metadata", {})
        )