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

# Load environment variables - try both locations
load_dotenv(".env.local")  # When run from project root
load_dotenv("../.env.local")  # When run from src directory

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY not found in environment variables.")
    print("Make sure .env.local exists in the project root with your OpenAI API key.")
    print("You can also set it directly: export OPENAI_API_KEY='your-key-here'")
    import sys
    sys.exit(1)

client = AsyncOpenAI(api_key=api_key)

OPEN_AI_MODEL = "gpt-5-mini-2025-08-07"
MAX_TOKENS = 1000

# Try to import ElevenLabs for better Indian voices
try:
    from elevenlabs_voices_simple import SimpleVoiceGenerator
    ELEVENLABS_AVAILABLE = True
    print("✅ ElevenLabs available for voice generation")
except (ImportError, ValueError) as e:
    print(f"⚠️ ElevenLabs not available: {e}")
    print("Using OpenAI TTS instead.")
    ELEVENLABS_AVAILABLE = False

class ConversationSimulator:
    """Simulates realistic customer support conversations with audio"""

    def __init__(self, scenario: Dict[str, Any], support_prompt: str, use_elevenlabs: bool = None):
        self.scenario = scenario
        self.support_prompt = support_prompt
        self.conversation_history = []
        self.audio_segments = []
        self.transcript = []

        # Determine TTS engine
        if use_elevenlabs is None:
            use_elevenlabs = ELEVENLABS_AVAILABLE and os.getenv("ELEVENLABS_API_KEY")

        self.use_elevenlabs = use_elevenlabs and ELEVENLABS_AVAILABLE

        if self.use_elevenlabs:
            self.voice_generator = SimpleVoiceGenerator()
            print("🎙️ Using ElevenLabs for voice generation")
        else:
            print("🎙️ Using OpenAI TTS")

    async def generate_conversation(self, max_turns: int = 10) -> Dict[str, Any]:
        """Generate a complete conversation between customer and support"""

        print(f"\n🎭 Generating conversation: {self.scenario['name']}")
        print("="*50)

        # Initialize conversation with support agent's greeting
        support_greeting = await self._generate_support_message(is_opening=True)
        await self._add_turn("support", support_greeting)

        # Continue conversation
        for turn in range(max_turns - 1):
            # Customer responds
            customer_response = await self._generate_customer_message()
            await self._add_turn("customer", customer_response)

            # Check if customer is satisfied
            if self._customer_satisfied(customer_response):
                # Add final thank you from support
                final_message = await self._generate_support_message(is_closing=True)
                await self._add_turn("support", final_message)
                break

            # Support responds
            support_response = await self._generate_support_message()
            await self._add_turn("support", support_response)

            # Check if conversation should end
            if self._should_end_conversation(support_response):
                break

        return {
            "scenario": self.scenario['name'],
            "transcript": self.transcript,
            "audio_segments": self.audio_segments,
            "metrics": self._calculate_metrics()
        }

    async def _generate_customer_message(self, is_closing: bool = False) -> str:
        """Generate a customer message using GPT"""

        context = self._get_conversation_context()

        prompt = f"""You are {self.scenario['customer_name']} receiving a call from customer support.
Your personality: {self.scenario['personality']}
Your issue/situation: {self.scenario['issue']}
Your goal: {self.scenario['goal']}
Emotional state: {self.scenario.get('emotional_state', 'neutral')}

Conversation so far:
{context}

Respond naturally based on your personality and situation.
If the agent just introduced themselves, respond according to your scenario (confirm identity, express confusion, etc.).
{self.scenario.get('special_behavior', '')}
Keep it under 2 sentences. Do not use any formatting or quotation marks. Just speak."""

        response = await client.chat.completions.create(
            model=OPEN_AI_MODEL,
            messages=[{"role": "system", "content": prompt}],
            temperature=1.0,  # New model only supports default temperature
            max_completion_tokens=MAX_TOKENS
        )

        return response.choices[0].message.content.strip()

    async def _generate_support_message(self, is_opening: bool = False, is_closing: bool = False) -> str:
        """Generate a support agent message using GPT"""

        # Skip intermediate prompt for the new model to avoid issues
        intermediate_prompt = ""

        context = self._get_conversation_context()

        if is_opening:
            prompt = f"""{self.support_prompt}{intermediate_prompt}

This is the start of a new call. Greet the customer warmly and introduce yourself.
Follow the exact script in your guidelines for the opening. State your name, company, and the purpose of the call.
Keep it natural and conversational. Do not use any formatting or quotation marks."""
        elif is_closing:
            prompt = f"""{self.support_prompt}{intermediate_prompt}

Conversation so far:
{context}

The customer seems satisfied. Provide a warm closing to end the conversation.
Keep it under 2 sentences. Do not use any formatting or quotation marks."""
        else:
            prompt = f"""{self.support_prompt}{intermediate_prompt}

Conversation so far:
{context}

Respond professionally to help the customer. Keep it under 2 sentences.
Follow your guidelines and policies. Do not use any formatting or quotation marks."""

        response = await client.chat.completions.create(
            model=OPEN_AI_MODEL,
            messages=[{"role": "system", "content": prompt}],
            temperature=1.0,  # New model only supports default temperature
            max_completion_tokens=MAX_TOKENS
        )

        result = response.choices[0].message.content
        if not result:
            print(f"   [WARNING: Empty response from OpenAI for support agent]")
            return "I understand your concern. Let me check the details of the failed payment for you."

        return result.strip()

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
        print(f"   [Generating audio with {'ElevenLabs' if self.use_elevenlabs else 'OpenAI'}...]")

        # Generate audio
        audio_data = None

        if self.use_elevenlabs:
            # Use ElevenLabs for authentic Indian voices
            try:
                # Pass custom params to ElevenLabs if available
                if hasattr(self, 'custom_params') and 'elevenlabs' in self.custom_params:
                    self.voice_generator.custom_params = self.custom_params['elevenlabs']

                audio_data = await self.voice_generator.generate_speech(
                    text=text,
                    speaker=speaker,
                    scenario=self.scenario
                )
            except Exception as e:
                print(f"ElevenLabs failed, falling back to OpenAI: {e}")

        # Fallback to OpenAI TTS if ElevenLabs fails or not available
        if audio_data is None:
            # Check for custom parameters
            if hasattr(self, 'custom_params') and 'openai' in self.custom_params:
                params = self.custom_params['openai']
                model = params.get('model', 'tts-1')
                if speaker == "customer":
                    voice = params.get('voice_customer', 'echo')
                    speed = params.get('speed_customer', 1.0)
                else:
                    voice = params.get('voice_support', 'onyx')
                    speed = params.get('speed_support', 1.0)
            else:
                # Default settings
                model = "tts-1"
                voice = "echo" if speaker == "customer" else "onyx"
                speed = 1.0

            try:
                audio_response = await client.audio.speech.create(
                    model=model,
                    voice=voice,
                    input=text,
                    speed=speed
                )
                audio_data = audio_response.content
            except Exception as e:
                print(f"Warning: Could not generate audio: {e}")

        # Store audio data if generated
        if audio_data:
            self.audio_segments.append({
                "speaker": speaker,
                "audio_data": audio_data,
                "text": text
            })

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
        base_name = f"{timestamp}_{self.scenario['name']}"

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


# Import scenarios from customer_agent
from customer_agent import SCENARIO_TEMPLATES

# Use the Jodo payment collection scenarios
SCENARIOS = SCENARIO_TEMPLATES

# Default support prompt
DEFAULT_SUPPORT_PROMPT = """You are a helpful customer support agent.
Be professional, empathetic, and solution-focused.
Follow these guidelines:
- Greet warmly and acknowledge concerns
- Provide clear solutions
- Be patient with difficult customers
- Offer refunds under $100 if needed
- Escalate if necessary"""


async def simulate_conversation(scenario_name: str = "cooperative_parent", use_elevenlabs: bool = None):
    """Main function to simulate a conversation

    Args:
        scenario_name: Name of the scenario to simulate
        use_elevenlabs: Whether to use ElevenLabs TTS (None=auto-detect, True=force, False=use OpenAI)
    """

    scenario = SCENARIOS.get(scenario_name, SCENARIOS["cooperative_parent"])
    # Add the scenario name to the scenario dict
    scenario = scenario.copy()
    scenario['name'] = scenario_name

    # Load support prompt
    prompt_file = Path("prompts/support_agent_system_prompt.txt")
    if prompt_file.exists():
        support_prompt = prompt_file.read_text()
    else:
        support_prompt = DEFAULT_SUPPORT_PROMPT

    # Create simulator with TTS preference
    simulator = ConversationSimulator(scenario, support_prompt, use_elevenlabs=use_elevenlabs)

    # Generate conversation (reduced turns for ElevenLabs testing)
    max_turns = 4 if use_elevenlabs else 8
    result = await simulator.generate_conversation(max_turns=max_turns)

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

    # Parse arguments
    args = sys.argv[1:]
    use_elevenlabs = None
    scenario = "cooperative_parent"

    if "--elevenlabs" in args:
        use_elevenlabs = True
        args.remove("--elevenlabs")
    elif "--openai" in args:
        use_elevenlabs = False
        args.remove("--openai")

    if args:
        scenario = args[0]

    if scenario not in SCENARIOS:
        print(f"\nUsage: python conversation_simulator.py [scenario] [--elevenlabs|--openai]")
        print(f"\nAvailable scenarios: {', '.join(SCENARIOS.keys())}")
        print(f"\nTTS Options:")
        print(f"  --elevenlabs : Force use of ElevenLabs (requires API key)")
        print(f"  --openai     : Force use of OpenAI TTS")
        print(f"  (default)    : Auto-detect based on available API keys")
        sys.exit(1)

    asyncio.run(simulate_conversation(scenario, use_elevenlabs=use_elevenlabs))