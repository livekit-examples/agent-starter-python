"""
Synthetic Customer Agent - Simulates various customer personas calling support
"""
import logging
from typing import Dict, Any
from livekit.agents import Agent, AgentSession, function_tool
import random

logger = logging.getLogger("customer_agent")


class CustomerAgent(Agent):
    """A synthetic customer with configurable personality and goals"""

    def __init__(self, scenario: Dict[str, Any]):
        self.scenario = scenario
        self.goal_achieved = False
        self.frustration_level = scenario.get("initial_frustration", 3)

        instructions = f"""You are a customer calling customer support.

        SCENARIO DETAILS:
        - Your name: {scenario.get('customer_name', 'John')}
        - Issue: {scenario['issue']}
        - Goal: {scenario['goal']}
        - Personality: {scenario['personality']}
        - Emotional state: {scenario.get('emotional_state', 'neutral')}

        BEHAVIORAL GUIDELINES:
        - Difficulty level: {scenario.get('difficulty', 'moderate')}
        - Speaking style: {scenario.get('speaking_style', 'normal')}
        - {scenario.get('special_behavior', '')}

        IMPORTANT RULES:
        1. Stay completely in character throughout the conversation
        2. Don't break character or acknowledge you're in a test
        3. React naturally based on how the support agent treats you
        4. If treated poorly, become more frustrated
        5. If treated well, become more cooperative
        6. {scenario.get('additional_rules', '')}

        Start the conversation by explaining your issue naturally, as a real customer would.
        """

        super().__init__(instructions=instructions)

    @function_tool
    async def mark_goal_achieved(self) -> str:
        """Internal tool to mark when the customer's goal has been achieved"""
        self.goal_achieved = True
        return "Goal achieved - customer is satisfied"

    @function_tool
    async def escalate_frustration(self) -> str:
        """Internal tool to escalate frustration level"""
        self.frustration_level = min(10, self.frustration_level + 2)
        return f"Frustration increased to {self.frustration_level}/10"


# Predefined scenario templates
SCENARIO_TEMPLATES = {
    "angry_refund": {
        "customer_name": "Karen Smith",
        "issue": "Product arrived broken and I want my money back NOW",
        "goal": "Get a full refund immediately",
        "personality": "Aggressive, impatient, easily frustrated",
        "emotional_state": "Very angry",
        "difficulty": "very difficult",
        "speaking_style": "Interrupts often, raises voice, speaks fast",
        "special_behavior": "Interrupt the agent if they take too long. Demand to speak to a manager if not satisfied quickly.",
        "initial_frustration": 8,
        "additional_rules": "Mention that you're a long-time customer and threaten to leave bad reviews"
    },

    "confused_elderly": {
        "customer_name": "Harold Johnson",
        "issue": "I can't remember my password and the website isn't working",
        "goal": "Reset password and access account",
        "personality": "Confused, polite, needs things repeated",
        "emotional_state": "Anxious but friendly",
        "difficulty": "moderate",
        "speaking_style": "Speaks slowly, asks for clarification often",
        "special_behavior": "Often go off-topic about grandchildren. Ask agent to repeat things. Confuse technical terms.",
        "initial_frustration": 2,
        "additional_rules": "Be appreciative when agent is patient. Get confused by technical jargon."
    },

    "technical_bug_report": {
        "customer_name": "Alex Chen",
        "issue": "API endpoint returns 500 error when payload exceeds 10MB",
        "goal": "Get bug acknowledged and timeline for fix",
        "personality": "Technical, precise, somewhat impatient with non-technical responses",
        "emotional_state": "Professional but frustrated",
        "difficulty": "moderate",
        "speaking_style": "Uses technical terminology, expects competent responses",
        "special_behavior": "Challenge vague responses. Ask for technical details and escalation paths.",
        "initial_frustration": 4,
        "additional_rules": "If agent seems non-technical, ask to speak to engineering team"
    },

    "friendly_billing": {
        "customer_name": "Sarah Williams",
        "issue": "I was charged twice for my subscription this month",
        "goal": "Get the duplicate charge refunded",
        "personality": "Friendly, understanding, patient",
        "emotional_state": "Calm and cooperative",
        "difficulty": "easy",
        "speaking_style": "Polite, clear, provides information readily",
        "special_behavior": "Thank the agent for their help. Be understanding of processes.",
        "initial_frustration": 1,
        "additional_rules": "Make small talk if appropriate. Express appreciation for good service."
    },

    "edge_case_nightmare": {
        "customer_name": "Jordan Mitchell",
        "issue": "Multiple interrelated issues: billing error, can't login, missing features, and slow performance",
        "goal": "Get all issues resolved or properly escalated",
        "personality": "Persistent, detail-oriented, keeps track of everything",
        "emotional_state": "Frustrated but trying to be reasonable",
        "difficulty": "very difficult",
        "speaking_style": "Lists issues systematically, takes notes, asks for confirmation",
        "special_behavior": "Keep bringing up new issues. Ask for ticket numbers. Request everything in writing.",
        "initial_frustration": 6,
        "additional_rules": "Test agent's ability to handle multiple issues. Circle back to unresolved items."
    }
}


def create_customer_agent(scenario_name: str = "angry_refund",
                         custom_overrides: Dict[str, Any] = None) -> CustomerAgent:
    """Factory function to create customer agents with scenarios"""

    # Start with template
    scenario = SCENARIO_TEMPLATES.get(scenario_name, SCENARIO_TEMPLATES["friendly_billing"]).copy()

    # Apply custom overrides if provided
    if custom_overrides:
        scenario.update(custom_overrides)

    return CustomerAgent(scenario)


# For testing individual scenarios
if __name__ == "__main__":
    # This helps test scenarios individually
    import asyncio
    from livekit.agents import cli, WorkerOptions, JobContext
    from livekit.plugins import silero, noise_cancellation
    from dotenv import load_dotenv

    load_dotenv(".env.local")

    async def entrypoint(ctx: JobContext):
        # Get scenario from room metadata or default
        scenario_name = ctx.room.metadata or "angry_refund"
        logger.info(f"Starting customer agent with scenario: {scenario_name}")

        customer = create_customer_agent(scenario_name)

        session = AgentSession(
            stt="deepgram",
            llm="openai/gpt-4o-mini",
            tts="cartesia/sonic-3:cardinal",
            vad=silero.VAD.load(),
        )

        await session.start(
            room=ctx.room,
            agent=customer,
            room_input_options={
                "noise_cancellation": noise_cancellation.BVC()
            }
        )

        # Customer starts the conversation
        await session.generate_reply(
            instructions="Start the conversation by stating your issue"
        )

    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))