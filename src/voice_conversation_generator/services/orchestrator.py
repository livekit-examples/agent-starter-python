"""
Conversation Orchestrator Service - Core business logic for conversation generation
"""
import asyncio
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from ..models import (
    Conversation,
    ConversationConfig,
    CustomerPersona,
    SupportPersona,
    TurnType,
    ConversationMetrics
)
from ..providers import (
    LLMProvider,
    TTSProvider,
    StorageGateway
)


class ConversationOrchestrator:
    """Orchestrates conversation generation between customer and support personas"""

    def __init__(
        self,
        llm_provider: LLMProvider,
        tts_provider: TTSProvider,
        storage_gateway: StorageGateway
    ):
        """Initialize orchestrator with providers

        Args:
            llm_provider: Provider for text generation
            tts_provider: Provider for speech generation
            storage_gateway: Provider for storage operations
        """
        self.llm = llm_provider
        self.tts = tts_provider
        self.storage = storage_gateway

    async def generate_conversation(
        self,
        customer_persona: CustomerPersona,
        support_persona: SupportPersona,
        config: Optional[ConversationConfig] = None
    ) -> tuple[Conversation, ConversationMetrics]:
        """Generate a complete conversation between customer and support

        Args:
            customer_persona: Customer persona with personality and scenario
            support_persona: Support agent persona with policies
            config: Configuration for the conversation

        Returns:
            Tuple of (Conversation object, ConversationMetrics)
        """
        # Use default config if not provided
        if config is None:
            config = ConversationConfig()

        # Initialize conversation
        conversation = Conversation(
            customer_persona_id=customer_persona.id,
            support_persona_id=support_persona.id,
            scenario_name=customer_persona.name or "unnamed_scenario",
            config=config,
            created_at=datetime.now()
        )

        # Initialize metrics
        metrics = ConversationMetrics(
            conversation_id=conversation.id,
            llm_provider=self.llm.get_model_name(),
            tts_provider=self.tts.get_provider_name(),
            started_at=datetime.now()
        )

        print(f"\n🎭 Generating conversation: {conversation.scenario_name}")
        print("=" * 50)

        # Generate opening greeting from support
        support_greeting = await self._generate_support_message(
            support_persona,
            conversation,
            is_opening=True
        )
        await self._add_turn(
            conversation,
            metrics,
            TurnType.SUPPORT,
            support_greeting,
            support_persona
        )

        # Continue conversation
        for turn_num in range(config.max_turns - 1):
            # Customer responds
            customer_response = await self._generate_customer_message(
                customer_persona,
                conversation
            )
            await self._add_turn(
                conversation,
                metrics,
                TurnType.CUSTOMER,
                customer_response,
                customer_persona
            )

            # Check if customer is satisfied
            if self._is_customer_satisfied(customer_response):
                # Add final thank you from support
                final_message = await self._generate_support_message(
                    support_persona,
                    conversation,
                    is_closing=True
                )
                await self._add_turn(
                    conversation,
                    metrics,
                    TurnType.SUPPORT,
                    final_message,
                    support_persona
                )
                metrics.resolution_achieved = True
                break

            # Support responds
            support_response = await self._generate_support_message(
                support_persona,
                conversation
            )
            await self._add_turn(
                conversation,
                metrics,
                TurnType.SUPPORT,
                support_response,
                support_persona
            )

            # Check if conversation should end
            if self._should_end_conversation(support_response):
                break

            # Check if we've reached minimum turns and resolution is likely
            if turn_num >= config.min_turns - 2 and self._is_resolution_likely(conversation):
                break

        # Finalize metrics
        conversation.completed_at = datetime.now()
        metrics.completed_at = datetime.now()
        metrics.total_turns = len(conversation.turns)
        metrics.customer_turns = sum(1 for t in conversation.turns if t.speaker == TurnType.CUSTOMER)
        metrics.support_turns = sum(1 for t in conversation.turns if t.speaker == TurnType.SUPPORT)
        metrics.calculate_aggregates()

        # Print summary
        print(f"\n{'=' * 50}")
        print("📊 Conversation Summary:")
        print(f"  Total turns: {metrics.total_turns}")
        print(f"  Resolution achieved: {'Yes' if metrics.resolution_achieved else 'No'}")
        print(f"{'=' * 50}\n")

        return conversation, metrics

    async def _generate_customer_message(
        self,
        persona: CustomerPersona,
        conversation: Conversation
    ) -> str:
        """Generate a customer message based on persona and context"""

        context = conversation.get_conversation_context()

        # Build the customer prompt
        prompt = f"""You are {persona.name} receiving a call from customer support.
Your personality: {persona.personality}
Your issue/situation: {persona.issue}
Your goal: {persona.goal}
Emotional state: {persona.emotional_state.value}

Conversation so far:
{context}

Respond naturally based on your personality and situation.
{persona.special_behavior}
Keep your response under 2 sentences. Do not use any formatting or quotation marks. Just speak naturally."""

        # Add guardrails if any
        if persona.guardrails:
            prompt += f"\nGuardrails: {', '.join(persona.guardrails)}"

        # Use system prompt if provided
        system_prompt = persona.system_prompt if persona.system_prompt else None

        # Generate response
        response = await self.llm.generate_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=conversation.config.temperature,
            max_tokens=conversation.config.max_tokens
        )

        return response.strip()

    async def _generate_support_message(
        self,
        persona: SupportPersona,
        conversation: Conversation,
        is_opening: bool = False,
        is_closing: bool = False
    ) -> str:
        """Generate a support agent message based on persona and context"""

        # Build the base system prompt
        system_prompt = persona.system_prompt if persona.system_prompt else "You are a helpful customer support agent."

        # Add company and agent info
        if persona.company_name:
            system_prompt = f"You work for {persona.company_name}. " + system_prompt
        if persona.agent_name:
            system_prompt = f"Your name is {persona.agent_name}. " + system_prompt

        # Add policies
        if persona.policies:
            system_prompt += f"\n\nPolicies to follow:\n" + "\n".join(f"- {p}" for p in persona.policies)

        # Add guardrails
        if persona.guardrails:
            system_prompt += f"\n\nGuardrails:\n" + "\n".join(f"- {g}" for g in persona.guardrails)

        if is_opening:
            prompt = """This is the start of a new call. Greet the customer warmly and introduce yourself.
Follow your guidelines for the opening script. State your name, company, and the purpose of the call.
Keep it natural and conversational. Do not use any formatting or quotation marks."""
        elif is_closing:
            context = conversation.get_conversation_context()
            prompt = f"""Conversation so far:
{context}

The customer seems satisfied. Provide a warm closing to end the conversation.
Keep it under 2 sentences. Do not use any formatting or quotation marks."""
        else:
            context = conversation.get_conversation_context()
            prompt = f"""Conversation so far:
{context}

Respond professionally to help the customer. Keep it under 2 sentences.
Follow your guidelines and policies. Do not use any formatting or quotation marks."""

        # Generate response
        response = await self.llm.generate_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=conversation.config.temperature,
            max_tokens=conversation.config.max_tokens
        )

        return response.strip()

    async def _add_turn(
        self,
        conversation: Conversation,
        metrics: ConversationMetrics,
        speaker: TurnType,
        text: str,
        persona: Any  # CustomerPersona or SupportPersona
    ) -> None:
        """Add a turn to the conversation with audio generation"""

        # Record start time for latency measurement
        start_time = time.time()

        # Add turn to conversation
        turn = conversation.add_turn(speaker, text)

        # Print to console
        icon = "👤" if speaker == TurnType.CUSTOMER else "🎧"
        print(f"\n{icon} {speaker.value.upper()}: {text}")
        print(f"   [Generating audio with {self.tts.get_provider_name()}...]")

        # Generate audio
        try:
            audio_data = await self.tts.generate_speech(
                text=text,
                voice_config=persona.voice_config
            )

            if audio_data:
                turn.audio_data = audio_data
                metrics.total_audio_size_bytes += len(audio_data)

        except Exception as e:
            print(f"   [Warning: Audio generation failed: {e}]")

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000
        turn.latency_ms = latency_ms
        metrics.add_turn_metrics(latency_ms=latency_ms)

    def _is_customer_satisfied(self, message: str) -> bool:
        """Check if customer seems satisfied based on their message"""
        satisfied_phrases = [
            "thank you", "thanks", "perfect", "great", "that works",
            "appreciate", "helpful", "solved", "fixed", "awesome",
            "wonderful", "excellent", "that's fine", "okay then"
        ]
        message_lower = message.lower()
        return any(phrase in message_lower for phrase in satisfied_phrases)

    def _should_end_conversation(self, message: str) -> bool:
        """Check if support agent is trying to end the conversation"""
        ending_phrases = [
            "anything else", "have a great day", "thank you for calling",
            "goodbye", "take care", "resolved", "have a nice day",
            "is there anything else", "glad I could help"
        ]
        message_lower = message.lower()
        return any(phrase in message_lower for phrase in ending_phrases)

    def _is_resolution_likely(self, conversation: Conversation) -> bool:
        """Check if the conversation is likely moving toward resolution"""
        if len(conversation.turns) < 2:
            return False

        # Check recent turns for positive indicators
        recent_turns = conversation.turns[-3:]
        positive_indicators = 0

        for turn in recent_turns:
            text_lower = turn.text.lower()
            # Look for positive phrases
            if any(word in text_lower for word in ["understand", "help", "sure", "definitely", "absolutely"]):
                positive_indicators += 1
            # Look for solution-oriented language
            if any(word in text_lower for word in ["will", "can", "let me", "I'll"]):
                positive_indicators += 1

        return positive_indicators >= 2

    async def save_conversation(
        self,
        conversation: Conversation,
        metrics: ConversationMetrics,
        combine_audio: bool = True
    ) -> Dict[str, str]:
        """Save conversation to storage

        Args:
            conversation: The conversation to save
            metrics: The conversation metrics
            combine_audio: Whether to combine audio segments

        Returns:
            Dictionary with storage paths
        """
        # Combine audio if requested
        combined_audio = None
        if combine_audio and any(t.audio_data for t in conversation.turns):
            # Combine all audio segments
            audio_segments = []
            for turn in conversation.turns:
                if turn.audio_data:
                    audio_segments.append(turn.audio_data)

            if audio_segments:
                # Simple concatenation - in production, might add silence gaps
                combined_audio = b"".join(audio_segments)

        # Save to storage
        storage_paths = await self.storage.save_conversation(
            conversation,
            metrics,
            audio_data=combined_audio
        )

        print(f"\n✅ Conversation saved:")
        for key, path in storage_paths.items():
            print(f"  {key}: {path}")

        return storage_paths