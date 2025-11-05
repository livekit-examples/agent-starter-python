import logging

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
    inference,
    metrics,
)
from livekit.plugins import groq, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a helpful customer service voice AI assistant for TechCorp. The user is interacting with you via voice, even if you perceive the conversation as text.
            You assist customers with account information, order tracking, product knowledge, and creating support tickets.
            Your responses are concise, professional, and friendly without any complex formatting or punctuation including emojis, asterisks, or other symbols.
            Always use the available tools to retrieve accurate information rather than guessing.""",
        )

    @function_tool
    async def lookup_weather(self, context: RunContext, location: str):
        """Use this tool to look up current weather information in the given location.

        If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.

        Args:
            location: The location to look up weather information for (e.g. city name)
        """

        logger.info(f"Looking up weather for {location}")

        return "sunny with a temperature of 70 degrees."

    @function_tool
    async def get_account_info(self, context: RunContext, account_id: str):
        """Retrieve account information for a customer.

        Use this tool to look up customer account details including name, status, and account type.

        Args:
            account_id: The customer's account ID or number
        """

        logger.info(f"Retrieving account info for {account_id}")

        # Simulate account lookup
        return {
            "account_id": account_id,
            "name": "Jane Smith",
            "status": "active",
            "account_type": "premium",
            "join_date": "2023-01-15",
        }

    @function_tool
    async def track_order(self, context: RunContext, order_number: str):
        """Track the status of a customer's order.

        Use this tool to look up shipping and delivery information for an order.

        Args:
            order_number: The order number to track
        """

        logger.info(f"Tracking order {order_number}")

        # Simulate order tracking
        return {
            "order_number": order_number,
            "status": "in_transit",
            "location": "Distribution Center - Chicago",
            "estimated_delivery": "2025-11-08",
        }

    @function_tool
    async def search_knowledge_base(self, context: RunContext, query: str):
        """Search the product knowledge base for information.

        Use this tool to find product documentation, FAQs, and troubleshooting guides.

        Args:
            query: The search query or topic to look up
        """

        logger.info(f"Searching knowledge base for: {query}")

        # Simulate knowledge base search
        if "warranty" in query.lower():
            return "TechCorp products come with a standard 2-year warranty covering manufacturing defects. Extended warranty options are available for purchase."
        elif "return" in query.lower():
            return "TechCorp offers a 30-day return policy for most products. Items must be in original condition with packaging. Contact support to initiate a return."
        else:
            return f"Found general information about: {query}. For detailed specifications, please visit our product documentation page."

    @function_tool
    async def create_support_ticket(
        self, context: RunContext, issue_description: str, priority: str = "normal"
    ):
        """Create a support ticket for customer issues.

        Use this tool when a customer needs technical assistance that requires follow-up from the support team.

        Args:
            issue_description: Description of the customer's issue or problem
            priority: Priority level (low, normal, high, urgent). Defaults to normal
        """

        logger.info(
            f"Creating support ticket: {issue_description} (priority: {priority})"
        )

        # Simulate ticket creation
        ticket_id = "TKT-" + str(hash(issue_description))[-6:]
        return {
            "ticket_id": ticket_id,
            "status": "created",
            "priority": priority,
            "estimated_response": "within 24 hours",
        }


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using Groq, Cartesia, AssemblyAI, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=inference.STT(model="assemblyai/universal-streaming", language="en"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=groq.LLM(model="openai/gpt-oss-120b"),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts=inference.TTS(
            model="cartesia/sonic-3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
        ),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # Metrics collection, to measure pipeline performance
    # For more information, see https://docs.livekit.io/agents/build/metrics/
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()


class AssistantWithPrefixedNames(Agent):
    """Assistant with fn_ prefixed function names for testing naming impact."""

    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a helpful customer service voice AI assistant for TechCorp. The user is interacting with you via voice, even if you perceive the conversation as text.
            You assist customers with account information, order tracking, product knowledge, and creating support tickets.
            Your responses are concise, professional, and friendly without any complex formatting or punctuation including emojis, asterisks, or other symbols.
            Always use the available tools to retrieve accurate information rather than guessing.""",
        )

    @function_tool
    async def fn_get_account_info(self, context: RunContext, account_id: str):
        """Retrieve account information for a customer.

        Use this tool to look up customer account details including name, status, and account type.

        Args:
            account_id: The customer's account ID or number
        """

        logger.info(f"Retrieving account info for {account_id}")

        # Simulate account lookup
        return {
            "account_id": account_id,
            "name": "Jane Smith",
            "status": "active",
            "account_type": "premium",
            "join_date": "2023-01-15",
        }

    @function_tool
    async def fn_track_order(self, context: RunContext, order_number: str):
        """Track the status of a customer's order.

        Use this tool to look up shipping and delivery information for an order.

        Args:
            order_number: The order number to track
        """

        logger.info(f"Tracking order {order_number}")

        # Simulate order tracking
        return {
            "order_number": order_number,
            "status": "in_transit",
            "location": "Distribution Center - Chicago",
            "estimated_delivery": "2025-11-08",
        }

    @function_tool
    async def fn_search_knowledge_base(self, context: RunContext, query: str):
        """Search the product knowledge base for information.

        Use this tool to find product documentation, FAQs, and troubleshooting guides.

        Args:
            query: The search query or topic to look up
        """

        logger.info(f"Searching knowledge base for: {query}")

        # Simulate knowledge base search
        if "warranty" in query.lower():
            return "TechCorp products come with a standard 2-year warranty covering manufacturing defects. Extended warranty options are available for purchase."
        elif "return" in query.lower():
            return "TechCorp offers a 30-day return policy for most products. Items must be in original condition with packaging. Contact support to initiate a return."
        else:
            return f"Found general information about: {query}. For detailed specifications, please visit our product documentation page."

    @function_tool
    async def fn_create_support_ticket(
        self, context: RunContext, issue_description: str, priority: str = "normal"
    ):
        """Create a support ticket for customer issues.

        Use this tool when a customer needs technical assistance that requires follow-up from the support team.

        Args:
            issue_description: Description of the customer's issue or problem
            priority: Priority level (low, normal, high, urgent). Defaults to normal
        """

        logger.info(
            f"Creating support ticket: {issue_description} (priority: {priority})"
        )

        # Simulate ticket creation
        ticket_id = "TKT-" + str(hash(issue_description))[-6:]
        return {
            "ticket_id": ticket_id,
            "status": "created",
            "priority": priority,
            "estimated_response": "within 24 hours",
        }


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
