"""
Metrics Collector - Captures detailed conversation metrics and quality indicators
"""
import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import statistics

logger = logging.getLogger("metrics_collector")


@dataclass
class TranscriptEntry:
    """Single entry in conversation transcript"""
    timestamp: float
    speaker: str  # "customer" or "support"
    text: str
    confidence: float = 1.0
    duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InterruptionEvent:
    """Tracks when one speaker interrupts another"""
    timestamp: float
    interrupter: str
    interrupted: str
    interrupted_text: str
    overlap_duration: float = 0.0


@dataclass
class AudioQualityEvent:
    """Tracks audio quality issues"""
    timestamp: float
    event_type: str  # "gibberish", "silence", "noise", "unclear"
    speaker: str
    duration: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResponseMetrics:
    """Metrics for a single response"""
    speaker: str
    response_time: float  # Time from end of previous speaker to start of response
    first_word_latency: float  # Time to first word
    total_duration: float
    word_count: int
    speech_rate: float  # words per minute


class ConversationAnalyzer:
    """Analyzes conversation quality and collects detailed metrics"""

    def __init__(self):
        self.start_time = time.time()
        self.transcript: List[TranscriptEntry] = []
        self.interruptions: List[InterruptionEvent] = []
        self.audio_quality_events: List[AudioQualityEvent] = []
        self.response_metrics: List[ResponseMetrics] = []

        # State tracking
        self.last_speaker = None
        self.last_speech_end = None
        self.current_speaker_start = None
        self.conversation_turns = 0

        # Quality thresholds
        self.silence_threshold = 3.0  # seconds
        self.gibberish_confidence_threshold = 0.5
        self.overlap_threshold = 0.5  # seconds to count as interruption

        # Metrics aggregation
        self.customer_metrics = {
            "total_speaking_time": 0.0,
            "total_words": 0,
            "interruption_count": 0,
            "average_response_time": [],
            "sentiment_scores": []
        }

        self.support_metrics = {
            "total_speaking_time": 0.0,
            "total_words": 0,
            "interruption_count": 0,
            "average_response_time": [],
            "first_response_time": None,
            "resolution_time": None
        }

    def on_speech_started(self, speaker: str, timestamp: Optional[float] = None):
        """Called when a speaker starts talking"""
        timestamp = timestamp or time.time()

        # Check for interruption
        if self.last_speaker and self.last_speaker != speaker:
            if self.last_speech_end and (timestamp - self.last_speech_end) < self.overlap_threshold:
                interruption = InterruptionEvent(
                    timestamp=timestamp,
                    interrupter=speaker,
                    interrupted=self.last_speaker,
                    interrupted_text="[speech cut off]",
                    overlap_duration=self.last_speech_end - timestamp
                )
                self.interruptions.append(interruption)
                logger.info(f"Interruption detected: {speaker} interrupted {self.last_speaker}")

        self.current_speaker_start = timestamp
        self.last_speaker = speaker

    def on_speech_ended(self, speaker: str, text: str, confidence: float = 1.0,
                       timestamp: Optional[float] = None):
        """Called when a speaker stops talking"""
        timestamp = timestamp or time.time()

        # Calculate speech duration
        duration = timestamp - self.current_speaker_start if self.current_speaker_start else 0

        # Add to transcript
        entry = TranscriptEntry(
            timestamp=self.current_speaker_start or timestamp,
            speaker=speaker,
            text=text,
            confidence=confidence,
            duration=duration
        )
        self.transcript.append(entry)

        # Check for gibberish (low confidence)
        if confidence < self.gibberish_confidence_threshold:
            self.audio_quality_events.append(AudioQualityEvent(
                timestamp=timestamp,
                event_type="gibberish",
                speaker=speaker,
                duration=duration,
                details={"confidence": confidence, "text": text}
            ))

        # Update metrics
        word_count = len(text.split())
        if speaker == "customer":
            self.customer_metrics["total_speaking_time"] += duration
            self.customer_metrics["total_words"] += word_count
        else:
            self.support_metrics["total_speaking_time"] += duration
            self.support_metrics["total_words"] += word_count
            if self.support_metrics["first_response_time"] is None:
                self.support_metrics["first_response_time"] = timestamp - self.start_time

        # Track response time
        if self.last_speech_end and self.last_speaker != speaker:
            response_time = self.current_speaker_start - self.last_speech_end
            metrics = ResponseMetrics(
                speaker=speaker,
                response_time=response_time,
                first_word_latency=response_time,  # Simplified for now
                total_duration=duration,
                word_count=word_count,
                speech_rate=(word_count / duration * 60) if duration > 0 else 0
            )
            self.response_metrics.append(metrics)

            # Check for long silence
            if response_time > self.silence_threshold:
                self.audio_quality_events.append(AudioQualityEvent(
                    timestamp=self.last_speech_end,
                    event_type="silence",
                    speaker="both",
                    duration=response_time,
                    details={"gap_between": f"{self.last_speaker} -> {speaker}"}
                ))

        self.last_speech_end = timestamp
        self.conversation_turns += 1

    def on_sentiment_detected(self, speaker: str, sentiment: str, score: float):
        """Track sentiment changes during conversation"""
        if speaker == "customer":
            self.customer_metrics["sentiment_scores"].append({
                "timestamp": time.time(),
                "sentiment": sentiment,
                "score": score
            })

    def get_summary(self) -> Dict[str, Any]:
        """Generate comprehensive conversation summary"""
        total_duration = time.time() - self.start_time

        # Calculate aggregate metrics
        customer_response_times = [m.response_time for m in self.response_metrics if m.speaker == "customer"]
        support_response_times = [m.response_time for m in self.response_metrics if m.speaker == "support"]

        summary = {
            "conversation_id": f"conv_{int(self.start_time)}",
            "duration": total_duration,
            "turns": self.conversation_turns,

            # Transcript with metadata
            "transcript": [asdict(entry) for entry in self.transcript],

            # Quality issues
            "quality_metrics": {
                "interruptions": {
                    "count": len(self.interruptions),
                    "details": [asdict(i) for i in self.interruptions]
                },
                "audio_quality_events": {
                    "count": len(self.audio_quality_events),
                    "gibberish_count": sum(1 for e in self.audio_quality_events if e.event_type == "gibberish"),
                    "silence_gaps": sum(1 for e in self.audio_quality_events if e.event_type == "silence"),
                    "details": [asdict(e) for e in self.audio_quality_events]
                }
            },

            # Performance metrics
            "performance": {
                "customer": {
                    "total_speaking_time": self.customer_metrics["total_speaking_time"],
                    "total_words": self.customer_metrics["total_words"],
                    "avg_response_time": statistics.mean(customer_response_times) if customer_response_times else 0,
                    "speech_rate": self._calculate_speech_rate("customer")
                },
                "support": {
                    "total_speaking_time": self.support_metrics["total_speaking_time"],
                    "total_words": self.support_metrics["total_words"],
                    "avg_response_time": statistics.mean(support_response_times) if support_response_times else 0,
                    "first_response_time": self.support_metrics["first_response_time"],
                    "speech_rate": self._calculate_speech_rate("support")
                }
            },

            # Conversation flow
            "conversation_flow": {
                "speaking_time_ratio": self._calculate_speaking_ratio(),
                "turn_distribution": self._analyze_turn_distribution(),
                "longest_silence": max([e.duration for e in self.audio_quality_events
                                       if e.event_type == "silence"], default=0),
                "interruption_rate": len(self.interruptions) / self.conversation_turns if self.conversation_turns > 0 else 0
            },

            # Sentiment progression (if available)
            "sentiment_analysis": {
                "customer_sentiment": self.customer_metrics["sentiment_scores"]
            }
        }

        return summary

    def _calculate_speech_rate(self, speaker: str) -> float:
        """Calculate average speech rate for a speaker"""
        metrics = self.customer_metrics if speaker == "customer" else self.support_metrics
        if metrics["total_speaking_time"] > 0:
            return (metrics["total_words"] / metrics["total_speaking_time"]) * 60
        return 0

    def _calculate_speaking_ratio(self) -> float:
        """Calculate ratio of customer vs support speaking time"""
        total = self.customer_metrics["total_speaking_time"] + self.support_metrics["total_speaking_time"]
        if total > 0:
            return self.customer_metrics["total_speaking_time"] / total
        return 0.5

    def _analyze_turn_distribution(self) -> Dict[str, int]:
        """Analyze how turns are distributed"""
        customer_turns = sum(1 for entry in self.transcript if entry.speaker == "customer")
        support_turns = sum(1 for entry in self.transcript if entry.speaker == "support")
        return {
            "customer_turns": customer_turns,
            "support_turns": support_turns,
            "ratio": customer_turns / support_turns if support_turns > 0 else 0
        }

    def export_metrics(self, filepath: str):
        """Export metrics to JSON file"""
        summary = self.get_summary()
        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Metrics exported to {filepath}")


class LiveKitMetricsAdapter:
    """Adapts LiveKit metrics events to our analyzer"""

    def __init__(self, analyzer: ConversationAnalyzer):
        self.analyzer = analyzer
        self.pending_speech = {}

    def on_user_speech_started(self, event):
        """Handle user (customer) starting to speak"""
        self.analyzer.on_speech_started("customer", event.timestamp)
        self.pending_speech["customer"] = time.time()

    def on_agent_speech_started(self, event):
        """Handle agent (support) starting to speak"""
        self.analyzer.on_speech_started("support", event.timestamp)
        self.pending_speech["support"] = time.time()

    def on_user_speech_ended(self, event):
        """Handle user (customer) finishing speech"""
        self.analyzer.on_speech_ended(
            "customer",
            event.text,
            event.confidence if hasattr(event, 'confidence') else 1.0,
            event.timestamp
        )

    def on_agent_speech_ended(self, event):
        """Handle agent (support) finishing speech"""
        self.analyzer.on_speech_ended(
            "support",
            event.text,
            1.0,  # Agent speech typically has high confidence
            event.timestamp
        )

    def on_metrics_collected(self, event):
        """Process LiveKit metrics events"""
        # Extract relevant metrics from LiveKit events
        if hasattr(event, 'metrics'):
            metrics = event.metrics
            # Process STT, TTS, LLM metrics as needed
            logger.debug(f"LiveKit metrics received: {metrics}")


# Utility function for quick analysis
def analyze_conversation_file(filepath: str) -> Dict[str, Any]:
    """Analyze a saved conversation transcript"""
    with open(filepath, 'r') as f:
        data = json.load(f)

    analyzer = ConversationAnalyzer()

    # Replay the conversation through the analyzer
    for entry in data.get('transcript', []):
        analyzer.transcript.append(TranscriptEntry(**entry))

    # Recalculate metrics
    return analyzer.get_summary()


if __name__ == "__main__":
    # Test the analyzer with mock data
    analyzer = ConversationAnalyzer()

    # Simulate a conversation
    analyzer.on_speech_started("customer", 1.0)
    analyzer.on_speech_ended("customer", "I need help with my order", 0.95, 3.0)

    analyzer.on_speech_started("support", 3.5)
    analyzer.on_speech_ended("support", "I'd be happy to help you with that", 1.0, 5.5)

    # Get summary
    summary = analyzer.get_summary()
    print(json.dumps(summary, indent=2))