"""
Support Agent - Mock version of Acme's customer support agent
"""
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from livekit.agents import Agent, AgentSession, function_tool
import json

logger = logging.getLogger("support_agent")


class SupportAgent(Agent):
    """Mock customer support agent using Acme's actual prompts"""

    def __init__(self, system_prompt: Optional[str] = None,
                 company_info: Optional[Dict[str, Any]] = None):

        # Use provided prompt or load default
        if system_prompt is None:
            prompt_file = Path("prompts/support_agent_system_prompt.txt")
            if prompt_file.exists():
                system_prompt = prompt_file.read_text()
            else:
                # Default prompt if file doesn't exist yet
                system_prompt = self._get_default_prompt()

        # Add any company-specific context
        if company_info:
            system_prompt += f"\n\nCOMPANY INFORMATION:\n"
            for key, value in company_info.items():
                system_prompt += f"- {key}: {value}\n"

        super().__init__(instructions=system_prompt)
        self.tickets_created = []
        self.escalations = []

    def _get_default_prompt(self) -> str:
        """Default support agent prompt for testing"""
        return """You are a helpful customer support agent for Acme Corp.

        YOUR ROLE:
        - Assist customers with their issues professionally and efficiently
        - Show empathy and understanding
        - Follow company policies and procedures
        - Escalate when necessary

        GUIDELINES:
        1. Always greet the customer warmly
        2. Listen carefully to understand their issue
        3. Acknowledge their concerns with empathy
        4. Provide clear solutions or next steps
        5. Confirm resolution before ending the call

        POLICIES:
        - Refunds: Authorized for amounts under $100, escalate otherwise
        - Technical issues: Gather details, create ticket if cannot resolve
        - Billing: Can adjust current month, escalate for historical changes
        - Passwords: Can reset with proper verification
        - Complaints: Document thoroughly, offer solutions within policy

        TONE:
        - Professional yet friendly
        - Patient and understanding
        - Clear and concise
        - Avoid technical jargon unless customer uses it

        Remember: Customer satisfaction is our top priority.
        """

    @function_tool
    async def create_support_ticket(self,
                                   issue_description: str,
                                   priority: str = "normal") -> str:
        """Create a support ticket for issues that need follow-up"""
        ticket_id = f"TICKET-{len(self.tickets_created) + 1001}"
        self.tickets_created.append({
            "id": ticket_id,
            "issue": issue_description,
            "priority": priority
        })
        return f"Created ticket {ticket_id} with {priority} priority"

    @function_tool
    async def process_refund(self,
                            amount: float,
                            reason: str) -> str:
        """Process a refund request"""
        if amount > 100:
            return "Refund amount exceeds my authorization. Let me escalate this to a supervisor."
        return f"Refund of ${amount} has been processed. It will appear in 3-5 business days."

    @function_tool
    async def check_account_status(self,
                                  account_id: Optional[str] = None) -> str:
        """Check customer account status"""
        # Mock account lookup
        return json.dumps({
            "status": "active",
            "balance": "$0.00",
            "last_payment": "2024-01-15",
            "member_since": "2021-03-20"
        })

    @function_tool
    async def escalate_to_supervisor(self,
                                    reason: str) -> str:
        """Escalate the issue to a supervisor"""
        self.escalations.append(reason)
        return "I'm escalating this to my supervisor who will be with you shortly."


def create_support_agent(prompt_file: Optional[str] = None,
                        company_info: Optional[Dict[str, Any]] = None) -> SupportAgent:
    """Factory function to create support agents"""

    system_prompt = None
    if prompt_file:
        prompt_path = Path(prompt_file)
        if prompt_path.exists():
            system_prompt = prompt_path.read_text()

    return SupportAgent(system_prompt, company_info)


# For testing the support agent individually
if __name__ == "__main__":
    import asyncio
    from livekit.agents import cli, WorkerOptions, JobContext
    from livekit.plugins import silero, noise_cancellation
    from dotenv import load_dotenv

    load_dotenv(".env.local")

    async def entrypoint(ctx: JobContext):
        logger.info("Starting support agent")

        support = create_support_agent()

        session = AgentSession(
            stt="deepgram",
            llm="openai/gpt-4o-mini",
            tts="cartesia/sonic-3:asheville",
            vad=silero.VAD.load(),
        )

        await session.start(
            room=ctx.room,
            agent=support,
            room_input_options={
                "noise_cancellation": noise_cancellation.BVC()
            }
        )

        # Support agent waits for customer to speak first
        logger.info("Support agent ready, waiting for customer...")

    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))