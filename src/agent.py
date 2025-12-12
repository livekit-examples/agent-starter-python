import asyncio
from datetime import UTC, datetime

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
from livekit_recording import (
    AudioRecorderProtocol,
    S3Uploader,
    Settings,
    StorageMode,
    TranscriptHandler,
)
from loguru import logger

# Load settings from .env.local (auto-discovers file in project root)
settings = Settings.load()

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
    session_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    logger.info(
        f"=== Agent session handler called for room: {room_name}, session_id: {session_id} ==="
    )
    logger.info(f"Storage mode: {settings.storage.mode.value}")

    # Initialize audio recorder based on storage mode
    # LocalAudioRecorder needs the room to subscribe to tracks
    # S3AudioRecorder (via egress) doesn't need the room directly
    audio_recorder: AudioRecorderProtocol | None = None
    try:
        logger.info("Initializing audio recorder...")
        # Configure S3 settings for S3 mode
        settings.configure_s3(bucket=S3_BUCKET, prefix=S3_PREFIX)
        # Create recorder - room will be set later for local mode
        audio_recorder = settings.create_audio_recorder(
            bucket=S3_BUCKET,
            prefix=S3_PREFIX,
            room=ctx.room,  # Used by LocalAudioRecorder
        )
        logger.info(
            f"Audio recorder initialized successfully (mode={settings.storage.mode.value})"
        )
    except Exception as e:
        logger.error(f"Failed to initialize audio recorder: {e}")

    # Initialize transcript handler for saving STT output
    transcript_handler = None
    try:
        logger.info("Initializing transcript handler...")
        s3_uploader = S3Uploader.from_settings(
            settings, bucket=S3_BUCKET, prefix=S3_PREFIX
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

    # Register shutdown callback for cleanup - this runs after session ends and
    # waits for completion before the process exits (unlike session.on("close"))
    async def shutdown_cleanup():
        """Clean up audio recorder and upload transcript when session ends."""
        logger.info(f"Shutdown callback running for room {room_name}...")

        # Stop audio recording and wait for file to be saved/uploaded
        if audio_recorder is not None:
            try:
                logger.info("Stopping audio recording...")
                file_info = await audio_recorder.stop_recording()
                if file_info:
                    logger.info(
                        f"Audio recording saved for room {room_name}: "
                        f"location={file_info.location}, "
                        f"filename={file_info.filename}, "
                        f"size={file_info.size} bytes"
                    )
                else:
                    logger.warning(
                        f"No audio file info returned for room {room_name} "
                        "(recording may have failed or no audio was captured)"
                    )
            except Exception as e:
                logger.error(f"Error stopping audio recording: {e}")

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

        # Clean up audio recorder resources
        if audio_recorder is not None:
            try:
                await audio_recorder.close()
            except Exception as e:
                logger.error(f"Error closing audio recorder: {e}")

        logger.info(f"Shutdown cleanup complete for room {room_name}")

    ctx.add_shutdown_callback(shutdown_cleanup)
    logger.info("Shutdown callback registered")

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

    # Start audio recording (non-blocking, after room is active)
    # NOTE: S3/Egress mode only works in 'dev' mode with a real LiveKit server, not in 'console' mode
    # Local mode works in all modes
    async def start_recording_background():
        """Start audio recording in background so it doesn't block the agent."""
        if audio_recorder is None:
            logger.warning("Audio recorder not initialized, skipping recording")
            return

        # Check if this is a mock room (console mode) - only skip for S3 mode
        if room_name == "mock_room" or room_name.startswith("FAKE_"):
            if settings.storage.mode == StorageMode.S3:
                logger.warning(
                    "Skipping S3/egress recording - console mode uses a mock room. "
                    "Run with 'dev' mode to enable S3 recording, or set STORAGE_MODE=local."
                )
                return
            # Local mode can still work in mock rooms (though no real audio will be captured)
            logger.info("Local recording mode enabled for mock room (testing)")

        try:
            logger.info(
                f"Starting audio recording for room {room_name}, "
                f"session_id={session_id}, mode={settings.storage.mode.value}..."
            )
            recording_id = await audio_recorder.start_recording(room_name, session_id)
            if recording_id:
                logger.info(
                    f"Audio recording started for room {room_name}, "
                    f"recording_id={recording_id}, session_id={session_id}"
                )
            else:
                logger.warning(
                    f"Failed to start audio recording for room {room_name}, "
                    "continuing without recording."
                )
        except Exception as e:
            logger.error(f"Error starting audio recording: {e}")

    # Run recording start in background task so it doesn't block
    _recording_task = asyncio.create_task(start_recording_background())  # noqa: RUF006

    logger.info(f"=== Agent setup complete for room: {room_name} ===")


if __name__ == "__main__":
    cli.run_app(server)
