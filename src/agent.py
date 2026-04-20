import asyncio
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ChatContext,
    JobContext,
    JobProcess,
    ToolError,
    TurnHandlingOptions,
    cli,
    room_io,
    utils,
)
from livekit.agents.beta.tools import EndCallTool
from livekit.plugins import ai_coustics, cartesia, deepgram, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent-Morgan-1f1e")

load_dotenv(".env.local")

AGENT_NAME = "Morgan-1f1e"
AGENT_MODEL = "gpt-5.3-chat-latest"
PROMPT_FILE = Path(__file__).with_name("prompt.txt")
SESSION_SUMMARY_MODEL = "gpt-5.2-chat-latest"
SUMMARY_WEBHOOK_URL = (
    "https://brittani.aaagency.cloud/webhook/122443dd-c357-4879-96b6-24ca7e5be0b2"
)
PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
DEBUG_LOG_PATH = Path("debug-30eba1.log")
DEBUG_SESSION_ID = "30eba1"


def _debug_log(
    hypothesis_id: str, location: str, message: str, data: dict[str, Any]
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": DEBUG_SESSION_ID,
            "runId": "pre-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        }
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass
    # #endregion


def load_prompt_template() -> str:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_FILE}")
    prompt = PROMPT_FILE.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Prompt file is empty: {PROMPT_FILE}")
    return prompt


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def render_prompt(template: str, variables: dict[str, Any]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return _stringify(variables.get(key)) if key in variables else match.group(0)

    return PLACEHOLDER_PATTERN.sub(_replace, template)


def _build_prompt_variables(ctx: JobContext) -> dict[str, Any]:
    now_str = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    base = {
        "first_name": "there",
        "last_name": "",
        "phone": "",
        "schedular_id": "",
        "now": now_str,
        "order_details": [],
        "email": "",
    }
    metadata_raw = getattr(ctx.room, "metadata", "") or "{}"
    try:
        metadata = json.loads(metadata_raw) if metadata_raw else {}
    except json.JSONDecodeError:
        logger.warning("room metadata is not valid json")
        metadata = {}

    for key in base:
        if key in metadata:
            base[key] = metadata[key]

    return base


class DefaultAgent(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(
            instructions=instructions,
            tools=[
                EndCallTool(
                    extra_description=(
                        'Customer gives a clear end signal: "no that\'s everything", '
                        '"nope", "I\'m good", "cheers", "bye", "ta", "got it", '
                        '"alright" - AND main prompt indicates towards call ending.'
                    ),
                    end_instructions=(
                        "Use only the correct situation-based closing line from "
                        "Section 11 of the prompt - already spoken before end_call "
                        "was triggered. Execute the call end silently. No additional "
                        "words after the closing line."
                    ),
                    delete_room=True,
                )
            ],
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Hi, Am I talking to John ?",
            allow_interruptions=False,
        )


Assistant = DefaultAgent
server = AgentServer(shutdown_process_timeout=60.0)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


async def _summarize_session(
    summarizer: openai.LLM, chat_ctx: ChatContext
) -> str | None:
    summary_ctx = ChatContext()
    summary_ctx.add_message(
        role="system",
        content=(
            "Summarize the following conversation in a concise manner. "
            "Use this format:\n"
            "CUSTOMER: [First name, last name]\n"
            "OUTCOME: [SMS sent / Callback booked / Sample not arrived / "
            "Not interested / Escalated to sales]\n"
            "SAMPLE FEEDBACK: products, reaction\n"
            "ROOM PROFILE: room type, size, underfloor heating, kids/pets, "
            "style preference, budget, timeline\n"
            'RECOMMENDATION GIVEN: [exact product name recommended, or "none"]\n'
            "NEXT ACTION: [what happens next]\n"
            "NOTES: [anything unusual]"
        ),
    )

    n_summarized = 0
    for item in chat_ctx.items:
        if item.type != "message":
            continue
        if item.role not in ("user", "assistant"):
            continue
        if item.extra.get("is_summary") is True:
            continue

        text = (item.text_content or "").strip()
        if text:
            summary_ctx.add_message(role="user", content=f"{item.role}: {text}")
            n_summarized += 1

    if n_summarized == 0:
        logger.debug("no chat messages to summarize")
        return None

    response = await summarizer.chat(
        chat_ctx=summary_ctx,
        extra_kwargs={"reasoning_effort": "medium"},
    ).collect()
    return response.text.strip() if response.text else None


async def _on_session_end_func(ctx: JobContext) -> None:
    ended_at = datetime.now(UTC)
    session = ctx._primary_agent_session
    if not session:
        logger.error("no primary agent session found for end_of_call processing")
        return

    report = ctx.make_session_report()
    summarizer = openai.LLM(model=SESSION_SUMMARY_MODEL)
    summary = await _summarize_session(summarizer, report.chat_history)
    if not summary:
        logger.info("no summary generated for end_of_call processing")
        return

    body = {
        "job_id": report.job_id,
        "room_id": report.room_id,
        "room": report.room,
        "started_at": (
            datetime.fromtimestamp(report.started_at, UTC)
            .isoformat()
            .replace("+00:00", "Z")
            if report.started_at
            else None
        ),
        "ended_at": ended_at.isoformat().replace("+00:00", "Z"),
        "summary": summary,
    }

    try:
        http_session = utils.http_context.http_session()
        timeout = aiohttp.ClientTimeout(total=10)
        resp = await asyncio.shield(
            http_session.post(SUMMARY_WEBHOOK_URL, timeout=timeout, json=body, headers={})
        )
        if resp.status >= 400:
            raise ToolError(f"error: HTTP {resp.status}: {resp.reason}")
        await resp.release()
    except ToolError:
        raise
    except (TimeoutError, aiohttp.ClientError) as e:
        raise ToolError(f"error: {e!s}") from e


@server.rtc_session(agent_name=AGENT_NAME, on_session_end=_on_session_end_func)
async def entrypoint(ctx: JobContext) -> None:
    _debug_log(
        hypothesis_id="H1",
        location="src/agent.py:entrypoint",
        message="provider_key_presence",
        data={
            "openai_api_key_present": bool(os.getenv("OPENAI_API_KEY")),
            "deepgram_api_key_present": bool(os.getenv("DEEPGRAM_API_KEY")),
            "cartesia_api_key_present": bool(os.getenv("CARTESIA_API_KEY")),
            "deepgram_api_key_length": len(os.getenv("DEEPGRAM_API_KEY", "")),
            "env_file_exists": Path(".env.local").exists(),
        },
    )
    prompt = render_prompt(load_prompt_template(), _build_prompt_variables(ctx))

    _debug_log(
        hypothesis_id="H2",
        location="src/agent.py:entrypoint",
        message="selected_models",
        data={
            "stt_provider": "deepgram",
            "stt_model": "nova-3",
            "stt_language": "en-US",
            "llm_provider": "openai",
            "llm_model": AGENT_MODEL,
            "tts_provider": "cartesia",
            "tts_model": "sonic-3",
        },
    )

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="en-US"),
        llm=openai.LLM(model=AGENT_MODEL),
        tts=cartesia.TTS(
            model="sonic-3",
            voice="ee7ea9f8-c0c1-498c-9279-764d6b56d189",
            language="en",
        ),
        turn_handling=TurnHandlingOptions(turn_detection=MultilingualModel()),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    try:
        await session.start(
            agent=DefaultAgent(instructions=prompt),
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    noise_cancellation=lambda params: (
                        ai_coustics.audio_enhancement(
                            model=ai_coustics.EnhancerModel.QUAIL_VF_L_TELEPHONY
                        )
                        if params.participant.kind
                        == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                        else ai_coustics.audio_enhancement(
                            model=ai_coustics.EnhancerModel.QUAIL_VF_L
                        )
                    ),
                ),
            ),
        )
    except Exception as e:
        _debug_log(
            hypothesis_id="H3",
            location="src/agent.py:entrypoint",
            message="session_start_error",
            data={
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        ),
        raise


if __name__ == "__main__":
    cli.run_app(server)
