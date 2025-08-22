import logging
import os
import random
import time

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentFalseInterruptionEvent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
)
from livekit.plugins import noise_cancellation
from livekit.plugins import openai as openai_plugins

logger = logging.getLogger("agent")

# Načítaj projektové premenné prostredia (.env je náš hlavný zdroj),
# a kvôli spätnému súladu aj .env.local zo šablóny
load_dotenv()
load_dotenv(".env.local")


class Assistant(Agent):
    """
    Minimalistický agent - držíme len základné hooky.
    """

    async def on_start(self, ctx: RunContext) -> None:
        logger.info("Assistant started")

    async def on_agent_interrupted(self, ev: AgentFalseInterruptionEvent, ctx: RunContext):
        # Žiadne špeciálne správanie
        pass


def prewarm(proc: JobProcess):
    """
    Realtime model nepotrebuje externý VAD ani turn-detector; ponecháme no-op.
    """
    return


async def entrypoint(ctx: JobContext):
    """
    Inicializácia Realtime session s OpenAI a pripojenie do LiveKit miestnosti.
    """
    # OpenAI Realtime model (audio + text). Model striktne bez dátumu:
    rt_model = openai_plugins.realtime.RealtimeModel(
        model="gpt-4o-realtime-preview",
        voice="alloy",
        modalities=["audio", "text"],
        # API kľúč sa číta z OPENAI_API_KEY; parametre nechávame default.
    )

    session = AgentSession(
        llm=rt_model,
    )

    # Konfigurovateľná BVC noise cancellation - default zapnutá, ale vypínateľná ENV premennou.
    enable_bvc = os.getenv("ENABLE_BVC", "true").lower() in ("1", "true", "yes")

    room_input = RoomInputOptions(
        noise_cancellation=noise_cancellation.BVC() if enable_bvc else None
    )

    # Spusti session a pripoj agenta do miestnosti
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=room_input,
    )
    logger.info("Realtime session started")


def _on_metrics_collected(ev: MetricsCollectedEvent):
    metrics.log_metrics(ev.metrics)


if __name__ == "__main__":
    # Exponenciálny backoff okolo spustenia aplikácie
    max_retries = int(os.getenv("AGENT_MAX_RETRIES", "5"))
    base_delay = float(os.getenv("AGENT_BACKOFF_BASE", "1.0"))
    attempt = 0

    while True:
        try:
            cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
            break
        except KeyboardInterrupt:
            raise
        except (ConnectionError, TimeoutError, OSError) as e:
            attempt += 1
            if attempt >= max_retries:
                logger.error("Failed to start after %d attempts: %s", attempt, e)
                raise
            jitter = random.uniform(0, base_delay * 0.25)
            delay = base_delay * (2 ** (attempt - 1)) + jitter
            logger.info(
                "Startup failed (%s). Retrying in %.1fs (%d/%d)...",
                type(e).__name__,
                delay,
                attempt,
                max_retries,
            )
            time.sleep(delay)
