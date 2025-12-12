import asyncio
from datetime import datetime, timezone

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    ConversationItemAddedEvent,
    JobContext,
    JobProcess,
    cli,
    inference,
    room_io,
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from loguru import logger

from egress_manager import EgressConfig, EgressManager
from transcript_handler import S3Uploader, TranscriptHandler

load_dotenv(".env.local")

# S3 bucket configuration for recordings and transcripts
S3_BUCKET = "audivi-audio-recordings"
S3_PREFIX = "livekit-demos"


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a helpful voice AI assistant. The user is interacting with you via voice, even if you perceive the conversation as text.
            You eagerly assist users with their questions by providing information from your extensive knowledge.
            Your responses are concise, to the point, and without any complex formatting or punctuation including emojis, asterisks, or other symbols.
            You are curious, friendly, and have a sense of humor.""",
        )

    # To add tools, use the @function_tool decorator.
    # Here's an example that adds a simple weather tool.
    # You also have to add `from livekit.agents import function_tool, RunContext` to the top of this file
    # @function_tool
    # async def lookup_weather(self, context: RunContext, location: str):
    #     """Use this tool to look up current weather information in the given location.
    #
    #     If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.
    #
    #     Args:
    #         location: The location to look up weather information for (e.g. city name)
    #     """
    #
    #     logger.info(f"Looking up weather for {location}")
    #
    #     return "sunny with a temperature of 70 degrees."


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session()
async def my_agent(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    room_name = ctx.room.name
    # Generate a unique session ID for matching audio and transcript files
    session_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    logger.info(
        f"=== Agent session handler called for room: {room_name}, session_id: {session_id} ==="
    )

    # Initialize egress manager for audio recording
    egress_manager = None
    try:
        logger.info("Initializing egress manager...")
        egress_config = EgressConfig(
            s3_bucket=S3_BUCKET,
            s3_prefix=S3_PREFIX,
        )
        egress_manager = EgressManager(egress_config)
        logger.info("Egress manager initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize egress manager: {e}")

    # Initialize transcript handler for saving STT output
    transcript_handler = None
    try:
        logger.info("Initializing transcript handler...")
        s3_uploader = S3Uploader(
            bucket=S3_BUCKET,
            prefix=S3_PREFIX,
        )
        transcript_handler = TranscriptHandler(
            room_name=room_name,
            s3_uploader=s3_uploader,
            session_id=session_id,
        )
        logger.info("Transcript handler initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize transcript handler: {e}")

    # Set up a voice AI pipeline using OpenAI, Cartesia, AssemblyAI, and the LiveKit turn detector
    logger.info("Creating AgentSession...")
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=inference.STT(model="assemblyai/universal-streaming", language="en"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=inference.LLM(model="openai/gpt-4.1-mini"),
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
    logger.info("AgentSession created successfully")

    # Subscribe to conversation events to capture transcripts
    logger.info("Registering event handlers...")

    @session.on("conversation_item_added")
    def on_conversation_item_added(event: ConversationItemAddedEvent):
        """Capture user and agent transcripts from conversation events."""
        if transcript_handler is None:
            return
        item = event.item
        text = item.text_content
        if not text:
            return

        if item.role == "user":
            transcript_handler.add_user_transcript(text, is_final=True)
        elif item.role == "assistant":
            transcript_handler.add_agent_transcript(text, is_final=True)

    # Handle session close to finalize and upload transcript
    @session.on("close")
    def on_session_close(_event):
        """Finalize transcript and clean up egress when session ends."""
        logger.info(f"Session closing for room {room_name}, saving transcript...")

        async def cleanup():
            # Stop egress recording - this triggers S3 upload of the audio file
            if egress_manager is not None:
                try:
                    logger.info("Stopping egress recording...")
                    stopped = await egress_manager.stop_recording()
                    if stopped:
                        logger.info(
                            f"Egress recording stopped for room {room_name}, "
                            f"audio uploaded to s3://{S3_BUCKET}/{S3_PREFIX}/"
                        )
                    else:
                        logger.warning(
                            f"Failed to stop egress recording for room {room_name}"
                        )
                except Exception as e:
                    logger.error(f"Error stopping egress recording: {e}")

            # Upload transcript to S3
            if transcript_handler is not None:
                try:
                    success = await transcript_handler.finalize_and_upload()
                    if success:
                        logger.info(f"Transcript saved for room {room_name}")
                    else:
                        logger.error(f"Failed to save transcript for room {room_name}")
                except Exception as e:
                    logger.error(f"Error saving transcript: {e}")

            # Clean up egress manager API client
            if egress_manager is not None:
                try:
                    await egress_manager.close()
                except Exception as e:
                    logger.error(f"Error closing egress manager: {e}")

        asyncio.create_task(cleanup())  # noqa: RUF006

    logger.info("Event handlers registered")

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    logger.info("Starting session...")
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            # Audio only - disable video input
            video_input=False,
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: noise_cancellation.BVCTelephony()
                if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                else noise_cancellation.BVC(),
            ),
        ),
    )
    logger.info("Session started successfully")

    # Join the room and connect to the user (audio only, no video)
    logger.info("Connecting to room...")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Connected to room successfully")

    # Greet the user
    await session.say("Hello, how can I assist you?")

    # Start audio recording via egress (non-blocking, after room is active)
    # NOTE: Egress only works in 'dev' mode with a real LiveKit server, not in 'console' mode
    async def start_egress_background():
        """Start egress recording in background so it doesn't block the agent."""
        if egress_manager is None:
            logger.warning("Egress manager not initialized, skipping recording")
            return

        # Check if this is a mock room (console mode)
        if room_name == "mock_room" or room_name.startswith("FAKE_"):
            logger.warning(
                "Skipping egress recording - console mode uses a mock room. "
                "Run with 'dev' mode to enable audio recording."
            )
            return

        try:
            logger.info(
                f"Starting egress recording for room {room_name}, session_id={session_id}..."
            )
            egress_id = await egress_manager.start_dual_channel_recording(
                room_name, session_id
            )
            if egress_id:
                logger.info(
                    f"Egress recording started for room {room_name}, "
                    f"egress_id={egress_id}, session_id={session_id}"
                )
            else:
                logger.warning(
                    f"Failed to start egress recording for room {room_name}, "
                    "continuing without recording. Check AWS credentials and LiveKit egress config."
                )
        except Exception as e:
            logger.error(f"Error starting egress recording: {e}")

    # Run egress start in background task so it doesn't block
    _egress_task = asyncio.create_task(start_egress_background())  # noqa: RUF006

    logger.info(f"=== Agent setup complete for room: {room_name} ===")


if __name__ == "__main__":
    cli.run_app(server)
