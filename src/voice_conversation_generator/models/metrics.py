"""
Metrics Model - Defines conversation quality metrics
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ConversationMetrics:
    """Metrics for conversation quality and performance"""
    conversation_id: Optional[str] = None

    # Basic metrics
    total_turns: int = 0
    total_duration_seconds: float = 0
    customer_turns: int = 0
    support_turns: int = 0

    # Latency metrics
    average_latency_ms: float = 0
    max_latency_ms: float = 0
    min_latency_ms: float = 0
    latency_percentile_95: float = 0

    # Speech metrics
    average_speech_rate_wpm: float = 0
    interruption_count: int = 0
    silence_duration_seconds: float = 0

    # Quality metrics
    customer_satisfaction_score: Optional[float] = None
    resolution_achieved: bool = False
    escalation_triggered: bool = False
    handoff_triggered: bool = False

    # Audio metrics
    total_audio_size_bytes: int = 0
    audio_codec: str = "mp3"
    audio_sample_rate: int = 16000

    # TTS/STT metrics
    tts_provider: str = ""
    stt_provider: Optional[str] = None
    llm_provider: str = ""
    llm_model: str = ""

    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Per-turn metrics storage
    turn_latencies: List[float] = field(default_factory=list)
    turn_speech_rates: List[float] = field(default_factory=list)

    def calculate_aggregates(self):
        """Calculate aggregate metrics from turn data"""
        if self.turn_latencies:
            self.average_latency_ms = sum(self.turn_latencies) / len(self.turn_latencies)
            self.max_latency_ms = max(self.turn_latencies)
            self.min_latency_ms = min(self.turn_latencies)

            # Calculate 95th percentile
            sorted_latencies = sorted(self.turn_latencies)
            idx = int(len(sorted_latencies) * 0.95)
            self.latency_percentile_95 = sorted_latencies[idx] if idx < len(sorted_latencies) else self.max_latency_ms

        if self.turn_speech_rates:
            self.average_speech_rate_wpm = sum(self.turn_speech_rates) / len(self.turn_speech_rates)

        if self.started_at and self.completed_at:
            self.total_duration_seconds = (self.completed_at - self.started_at).total_seconds()

    def add_turn_metrics(self, latency_ms: float = None, speech_rate_wpm: float = None, is_interruption: bool = False):
        """Add metrics for a single turn"""
        if latency_ms is not None:
            self.turn_latencies.append(latency_ms)

        if speech_rate_wpm is not None:
            self.turn_speech_rates.append(speech_rate_wpm)

        if is_interruption:
            self.interruption_count += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "conversation_id": self.conversation_id,
            "total_turns": self.total_turns,
            "total_duration_seconds": self.total_duration_seconds,
            "customer_turns": self.customer_turns,
            "support_turns": self.support_turns,
            "average_latency_ms": self.average_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "min_latency_ms": self.min_latency_ms,
            "latency_percentile_95": self.latency_percentile_95,
            "average_speech_rate_wpm": self.average_speech_rate_wpm,
            "interruption_count": self.interruption_count,
            "silence_duration_seconds": self.silence_duration_seconds,
            "customer_satisfaction_score": self.customer_satisfaction_score,
            "resolution_achieved": self.resolution_achieved,
            "escalation_triggered": self.escalation_triggered,
            "handoff_triggered": self.handoff_triggered,
            "total_audio_size_bytes": self.total_audio_size_bytes,
            "audio_codec": self.audio_codec,
            "audio_sample_rate": self.audio_sample_rate,
            "tts_provider": self.tts_provider,
            "stt_provider": self.stt_provider,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "turn_latencies": self.turn_latencies,
            "turn_speech_rates": self.turn_speech_rates
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationMetrics':
        """Create from dictionary"""
        # Handle datetime fields
        started_at = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
        completed_at = datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None

        metrics = cls(
            conversation_id=data.get("conversation_id"),
            total_turns=data.get("total_turns", 0),
            total_duration_seconds=data.get("total_duration_seconds", 0),
            customer_turns=data.get("customer_turns", 0),
            support_turns=data.get("support_turns", 0),
            average_latency_ms=data.get("average_latency_ms", 0),
            max_latency_ms=data.get("max_latency_ms", 0),
            min_latency_ms=data.get("min_latency_ms", 0),
            latency_percentile_95=data.get("latency_percentile_95", 0),
            average_speech_rate_wpm=data.get("average_speech_rate_wpm", 0),
            interruption_count=data.get("interruption_count", 0),
            silence_duration_seconds=data.get("silence_duration_seconds", 0),
            customer_satisfaction_score=data.get("customer_satisfaction_score"),
            resolution_achieved=data.get("resolution_achieved", False),
            escalation_triggered=data.get("escalation_triggered", False),
            handoff_triggered=data.get("handoff_triggered", False),
            total_audio_size_bytes=data.get("total_audio_size_bytes", 0),
            audio_codec=data.get("audio_codec", "mp3"),
            audio_sample_rate=data.get("audio_sample_rate", 16000),
            tts_provider=data.get("tts_provider", ""),
            stt_provider=data.get("stt_provider"),
            llm_provider=data.get("llm_provider", ""),
            llm_model=data.get("llm_model", ""),
            started_at=started_at,
            completed_at=completed_at,
            turn_latencies=data.get("turn_latencies", []),
            turn_speech_rates=data.get("turn_speech_rates", [])
        )

        return metrics

    def generate_summary(self) -> str:
        """Generate a human-readable summary of metrics"""
        lines = [
            f"Conversation Metrics Summary",
            f"=" * 40,
            f"Total turns: {self.total_turns} ({self.customer_turns} customer, {self.support_turns} support)",
            f"Duration: {self.total_duration_seconds:.1f} seconds"
        ]

        if self.turn_latencies:
            lines.extend([
                f"",
                f"Latency:",
                f"  Average: {self.average_latency_ms:.1f}ms",
                f"  Min/Max: {self.min_latency_ms:.1f}ms / {self.max_latency_ms:.1f}ms",
                f"  95th percentile: {self.latency_percentile_95:.1f}ms"
            ])

        if self.turn_speech_rates:
            lines.append(f"")
            lines.append(f"Average speech rate: {self.average_speech_rate_wpm:.1f} WPM")

        if self.interruption_count > 0:
            lines.append(f"Interruptions: {self.interruption_count}")

        lines.extend([
            f"",
            f"Outcomes:",
            f"  Resolution achieved: {'Yes' if self.resolution_achieved else 'No'}",
            f"  Escalation triggered: {'Yes' if self.escalation_triggered else 'No'}"
        ])

        if self.customer_satisfaction_score is not None:
            lines.append(f"  Customer satisfaction: {self.customer_satisfaction_score:.2f}")

        lines.extend([
            f"",
            f"Providers:",
            f"  LLM: {self.llm_provider}/{self.llm_model}",
            f"  TTS: {self.tts_provider}"
        ])

        if self.stt_provider:
            lines.append(f"  STT: {self.stt_provider}")

        return "\n".join(lines)