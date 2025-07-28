import logging
import os
import asyncio
import json
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    RoomOutputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
)
from livekit.agents.llm import function_tool
from livekit.agents.voice import MetricsCollectedEvent
from livekit.plugins import cartesia, deepgram, noise_cancellation, openai, silero, anthropic, google, elevenlabs
from livekit.plugins.turn_detector.english import EnglishModel
from prompt import ffam


logger = logging.getLogger("agent")

if os.path.exists(".env.local"):
    load_dotenv(".env.local")

class Assistant(Agent):
    def __init__(self, prompt: str) -> None:
        super().__init__(
            instructions=prompt,
        )


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


def get_stt():
    on_prem_deepgram_link = os.getenv("DEEPGRAM_URL", "https://deepgram-proagent.service.internal.usea2.aws.prodigaltech.com/v1/listen")

    should_use_on_prem_deepgram = os.getenv("SHOULD_USE_ON_PREM_DEEPGRAM", "false").lower() == "true"
    deepgram_model = os.getenv("DEEPGRAM_MODEL", "nova-2-phonecall")
    logger.info(f"Using STT: {should_use_on_prem_deepgram} {deepgram_model}")
    if should_use_on_prem_deepgram:
        stt = deepgram.STT(model=deepgram_model, smart_format=False, base_url=on_prem_deepgram_link)
    else:
        stt = deepgram.STT(model=deepgram_model, smart_format=False)
    return stt


def get_llm():
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    llm_model = os.getenv("LLM_MODEL", "gpt-4o")
    logger.info(f"Using LLM: {llm_provider} {llm_model}")
    if llm_provider == "openai":
        return openai.LLM(model=llm_model)
    elif llm_provider == "anthropic":
        return anthropic.LLM(model=llm_model)

def get_tts():
    tts_provider = os.getenv("TTS_PROVIDER", "cartesia")
    tts_voice = os.getenv("TTS_VOICE", "78ab82d5-25be-4f7d-82b3-7ad64e5b85b2")
    elevenlabs_model = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
    logger.info(f"Using TTS: {tts_provider} {tts_voice}")
    if tts_provider == "cartesia":
        return cartesia.TTS(voice=tts_voice)
    elif tts_provider == "google":
        creds = json.loads(os.environ.get("GOOGLE_TTS_SERVICE_ACCOUNT", "{}"))
        return google.TTS(voice_name=tts_voice, credentials_info=creds)
    elif tts_provider == "elevenlabs":
        return elevenlabs.TTS(voice_id=tts_voice, model=elevenlabs_model)

async def entrypoint(ctx: JobContext):
    # each log entry will include these fields
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    stt = get_stt()
    llm = get_llm()
    tts = get_tts()
    turn_detection = EnglishModel()

    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=ctx.proc.userdata["vad"],
        turn_detection=turn_detection,
    )

    # To use the OpenAI Realtime API, use the following session setup instead:
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel()
    # )

    # log metrics as they are emitted, and total usage after session is over
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")
        logger.info(session.history.to_dict())

    # shutdown callbacks are triggered when the session is over
    ctx.add_shutdown_callback(log_usage)

    if os.getenv("SHOULD_LOG_PROMPT", "false").lower() == "true":
        logger.info(f"Using prompt: {ffam}")

    await session.start(
        agent=Assistant(ffam),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
        room_output_options=RoomOutputOptions(transcription_enabled=True),
    )

    # join the room when agent is ready
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name="lk_starter_agent"))
