"""
Conversation Simulator - Generates synthetic conversations with audio
This actually creates conversations you can hear!
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import os

# We'll use OpenAI for both conversation generation and TTS
import openai
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(".env.local")

# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class ConversationSimulator:
    """Simulates realistic customer support conversations with audio"""

    def __init__(self, scenario: Dict[str, Any], support_prompt: str):
        self.scenario = scenario
        self.support_prompt = support_prompt
        self.conversation_history = []
        self.audio_segments = []
        self.transcript = []

    async def generate_conversation(self, max_turns: int = 10) -> Dict[str, Any]:
        """Generate a complete conversation between customer and support"""

        print(f"\n🎭 Generating conversation: {self.scenario['name']}")
        print("="*50)

        # Initialize conversation with customer's opening
        customer_opening = await self._generate_customer_message(is_opening=True)
        await self._add_turn("customer", customer_opening)

        # Continue conversation
        for turn in range(max_turns - 1):
            # Support responds
            support_response = await self._generate_support_message()
            await self._add_turn("support", support_response)

            # Check if conversation should end
            if self._should_end_conversation(support_response):
                break

            # Customer responds
            customer_response = await self._generate_customer_message()
            await self._add_turn("customer", customer_response)

            # Check if customer is satisfied
            if self._customer_satisfied(customer_response):
                # Add final thank you from support
                final_message = await self._generate_support_message(is_closing=True)
                await self._add_turn("support", final_message)
                break

        return {
            "scenario": self.scenario['name'],
            "transcript": self.transcript,
            "audio_segments": self.audio_segments,
            "metrics": self._calculate_metrics()
        }

    async def _generate_customer_message(self, is_opening: bool = False, is_closing: bool = False) -> str:
        """Generate a customer message using GPT"""

        if is_opening:
            prompt = f"""You are a customer calling support with the following profile:
Name: {self.scenario['customer_name']}
Issue: {self.scenario['issue']}
Personality: {self.scenario['personality']}
Emotional state: {self.scenario.get('emotional_state', 'neutral')}

Start the conversation by explaining your issue. Be {self.scenario['difficulty']} to deal with.
Speak naturally as this person would speak. Keep it under 2 sentences.
Do not use any formatting or quotation marks. Just speak."""
        else:
            context = self._get_conversation_context()
            prompt = f"""You are {self.scenario['customer_name']}, continuing a support conversation.
Your personality: {self.scenario['personality']}
Your goal: {self.scenario['goal']}

Conversation so far:
{context}

Respond naturally to the support agent. Keep it under 2 sentences.
{self.scenario.get('special_behavior', '')}
Do not use any formatting or quotation marks. Just speak."""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.8,
            max_tokens=100
        )

        return response.choices[0].message.content.strip()

    async def _generate_support_message(self, is_closing: bool = False) -> str:
        """Generate a support agent message using GPT"""

        context = self._get_conversation_context()

        if is_closing:
            prompt = f"""{self.support_prompt}

Conversation so far:
{context}

The customer seems satisfied. Provide a warm closing to end the conversation.
Keep it under 2 sentences. Do not use any formatting or quotation marks."""
        else:
            prompt = f"""{self.support_prompt}

Conversation so far:
{context}

Respond professionally to help the customer. Keep it under 2 sentences.
Follow your guidelines and policies. Do not use any formatting or quotation marks."""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7,
            max_tokens=100
        )

        return response.choices[0].message.content.strip()

    async def _add_turn(self, speaker: str, text: str):
        """Add a turn to the conversation with audio generation"""

        # Add to transcript
        self.transcript.append({
            "speaker": speaker,
            "text": text,
            "timestamp": time.time()
        })

        # Print to console
        icon = "👤" if speaker == "customer" else "🎧"
        print(f"\n{icon} {speaker.upper()}: {text}")

        # Generate audio
        voice = "echo" if speaker == "customer" else "nova"  # Different voices

        try:
            audio_response = await client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text
            )

            # Store audio data
            self.audio_segments.append({
                "speaker": speaker,
                "audio_data": audio_response.content,
                "text": text
            })

        except Exception as e:
            print(f"Warning: Could not generate audio: {e}")

        # Add to conversation history for context
        self.conversation_history.append(f"{speaker}: {text}")

    def _get_conversation_context(self) -> str:
        """Get the last few turns of conversation for context"""
        return "\n".join(self.conversation_history[-6:])  # Last 3 exchanges

    def _should_end_conversation(self, message: str) -> bool:
        """Check if support agent is trying to end the conversation"""
        ending_phrases = [
            "anything else", "have a great day", "thank you for calling",
            "goodbye", "take care", "resolved"
        ]
        return any(phrase in message.lower() for phrase in ending_phrases)

    def _customer_satisfied(self, message: str) -> bool:
        """Check if customer seems satisfied"""
        satisfied_phrases = [
            "thank you", "thanks", "perfect", "great", "that works",
            "appreciate", "helpful", "solved", "fixed"
        ]
        return any(phrase in message.lower() for phrase in satisfied_phrases)

    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate conversation metrics"""
        return {
            "total_turns": len(self.transcript),
            "total_duration": len(self.transcript) * 3,  # Estimate 3 seconds per turn
            "customer_turns": sum(1 for t in self.transcript if t['speaker'] == 'customer'),
            "support_turns": sum(1 for t in self.transcript if t['speaker'] == 'support')
        }

    async def export_conversation(self, output_dir: str = "conversations"):
        """Export conversation as audio file and transcript"""

        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{self.scenario['name']}_{timestamp}"

        # Save transcript
        transcript_file = output_path / f"{base_name}_transcript.json"
        with open(transcript_file, 'w') as f:
            json.dump({
                "scenario": self.scenario,
                "transcript": self.transcript,
                "metrics": self._calculate_metrics()
            }, f, indent=2)

        # Combine audio segments with silence gaps
        if self.audio_segments:
            audio_file = output_path / f"{base_name}_conversation.mp3"

            # For now, save the first segment as a sample
            # In production, you'd combine all segments with proper gaps
            with open(audio_file, 'wb') as f:
                # Write all audio segments sequentially
                for segment in self.audio_segments:
                    f.write(segment['audio_data'])

            print(f"\n✅ Audio saved: {audio_file}")

        print(f"📄 Transcript saved: {transcript_file}")

        return {
            "audio_file": str(audio_file) if self.audio_segments else None,
            "transcript_file": str(transcript_file)
        }


# Predefined scenarios (simplified version)
SCENARIOS = {
    "angry_refund": {
        "name": "angry_refund",
        "customer_name": "Karen Smith",
        "issue": "My product arrived completely broken and I want my money back immediately",
        "goal": "Get a full refund",
        "personality": "Aggressive, impatient, easily frustrated",
        "emotional_state": "Very angry",
        "difficulty": "very difficult",
        "special_behavior": "Interrupt if the agent takes too long. Demand to speak to a manager."
    },
    "friendly_billing": {
        "name": "friendly_billing",
        "customer_name": "Sarah Williams",
        "issue": "I noticed I was charged twice for my subscription this month",
        "goal": "Get the duplicate charge refunded",
        "personality": "Friendly, understanding, patient",
        "emotional_state": "Calm",
        "difficulty": "easy",
        "special_behavior": "Be cooperative and thank the agent for their help."
    },
    "confused_elderly": {
        "name": "confused_elderly",
        "customer_name": "Harold Johnson",
        "issue": "I can't remember my password and the website isn't working",
        "goal": "Reset password and access account",
        "personality": "Confused but polite, needs repetition",
        "emotional_state": "Anxious but friendly",
        "difficulty": "moderate",
        "special_behavior": "Ask for things to be repeated. Get confused by technical terms."
    }
}

# Default support prompt
DEFAULT_SUPPORT_PROMPT = """You are a helpful customer support agent.
Be professional, empathetic, and solution-focused.
Follow these guidelines:
- Greet warmly and acknowledge concerns
- Provide clear solutions
- Be patient with difficult customers
- Offer refunds under $100 if needed
- Escalate if necessary"""


async def simulate_conversation(scenario_name: str = "friendly_billing"):
    """Main function to simulate a conversation"""

    scenario = SCENARIOS.get(scenario_name, SCENARIOS["friendly_billing"])

    # Load support prompt
    prompt_file = Path("prompts/acme_system_prompt.txt")
    if prompt_file.exists():
        support_prompt = prompt_file.read_text()
    else:
        support_prompt = DEFAULT_SUPPORT_PROMPT

    # Create simulator
    simulator = ConversationSimulator(scenario, support_prompt)

    # Generate conversation
    result = await simulator.generate_conversation(max_turns=8)

    # Export files
    files = await simulator.export_conversation()

    print(f"\n{'='*50}")
    print("📊 Conversation Summary:")
    print(f"  Scenario: {scenario_name}")
    print(f"  Total turns: {result['metrics']['total_turns']}")
    print(f"  Files saved: {files['transcript_file']}")
    if files['audio_file']:
        print(f"  Audio file: {files['audio_file']}")
    print(f"{'='*50}\n")

    return result


if __name__ == "__main__":
    import sys

    scenario = sys.argv[1] if len(sys.argv) > 1 else "friendly_billing"

    if scenario not in SCENARIOS:
        print(f"Available scenarios: {', '.join(SCENARIOS.keys())}")
        sys.exit(1)

    asyncio.run(simulate_conversation(scenario))