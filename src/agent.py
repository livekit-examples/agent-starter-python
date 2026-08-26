from __future__ import annotations

import asyncio
import logging
import re
import textwrap
from typing import Any

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    cli,
    inference,
    llm,
    room_io,
)
from livekit.plugins import ai_coustics

from approval import ApprovalBroker
from hermes_client import HermesClient, HermesConfig
from hermes_llm import HermesLLM
from realtime_protocol import (
    CONTROL_TOPIC,
    ConversationState,
    parse_control_packet,
    parse_conversation_id,
)
from realtime_status import StatusPublisher, conversation_fingerprint

logger = logging.getLogger("hermes-voice")

load_dotenv(".env.local")

AGENT_NAME = "hermes-voice"
CARTESIA_BENGALI_VOICE = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
BENGALI_KEYTERMS = [
    "Hermes",
    "OmniRoute",
    "VS Code",
    "Chrome",
    "GitHub",
    "API",
    "backend",
    "frontend",
    "Calculator",
]


class Assistant(Agent):
    def __init__(self, model: llm.LLM) -> None:
        super().__init__(
            llm=model,
            instructions=textwrap.dedent(
                """\
                You are Hermes Main/Commander, the user's existing local Windows agent.
                Speak in concise, natural Bengali unless the user requests another language.
                Complete tasks using Hermes' existing tools, memory, skills, CUA, and OmniRoute.
                A spoken yes never approves a destructive or sensitive action. Wait for the
                explicit Confirm button in the Android app or decline the action.
                """
            ),
        )


def _safe_session_id(room_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", room_name).strip("-")
    return f"voice:{cleaned or 'room'}"[:128]


def build_turn_handling_options() -> TurnHandlingOptions:
    return TurnHandlingOptions(
        turn_detection="vad",
        endpointing={"mode": "dynamic", "min_delay": 0.35, "max_delay": 1.2},
        interruption={
            "enabled": True,
            "mode": "adaptive",
            "min_duration": 0.3,
            "min_words": 0,
            "resume_false_interruption": True,
            "false_interruption_timeout": 1.0,
            "backchannel_boundary": (1.0, 1.2),
        },
        preemptive_generation={"enabled": False},
    )


def build_room_options() -> room_io.RoomOptions:
    return room_io.RoomOptions(
        close_on_disconnect=False,
        text_input=room_io.TextInputOptions(text_input_cb=_logged_text_input),
        text_output=room_io.TextOutputOptions(sync_transcription=False),
        audio_input=room_io.AudioInputOptions(
            noise_cancellation=ai_coustics.audio_enhancement(
                model=ai_coustics.EnhancerModel.QUAIL_VF_S
            ),
        ),
    )


def build_session(model: llm.LLM) -> AgentSession:
    return AgentSession(
        llm=model,
        stt=inference.STT(
            model="deepgram/nova-3",
            language="bn",
            extra_kwargs={
                "interim_results": True,
                "smart_format": True,
                "keyterm": BENGALI_KEYTERMS,
            },
        ),
        tts=inference.TTS(
            model="cartesia/sonic-3.5",
            voice=CARTESIA_BENGALI_VOICE,
            language="bn",
        ),
        turn_handling=build_turn_handling_options(),
        use_tts_aligned_transcript=True,
        user_away_timeout=None,
    )


def _identity_value(participant: Any) -> str:
    identity = getattr(participant, "identity", "")
    return str(getattr(identity, "value", identity) or "")


def resolve_linked_identity(room: Any) -> str:
    participants = getattr(room, "remote_participants", {})
    values = participants.values() if hasattr(participants, "values") else participants
    identities = [identity for item in values if (identity := _identity_value(item))]
    return next(
        (identity for identity in identities if identity.startswith("hermes-android-")),
        identities[0] if identities else "",
    )


def _participant_attribute(room: Any, identity: str, key: str) -> str | None:
    participants = getattr(room, "remote_participants", {})
    values = participants.values() if hasattr(participants, "values") else participants
    for participant in values:
        if _identity_value(participant) != identity:
            continue
        attributes = getattr(participant, "attributes", {}) or {}
        value = attributes.get(key) if hasattr(attributes, "get") else None
        return str(value) if value is not None else None
    return None


async def _wait_for_linked_identity(room: Any, *, timeout: float = 5.0) -> str:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        identity = resolve_linked_identity(room)
        if identity:
            return identity
        await asyncio.sleep(0.05)
    return ""


def _milliseconds(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return round(value * 1000)


def safe_metric_status(metric: Any) -> dict[str, Any] | None:
    """Project SDK metrics without IDs, transcript content, or model input."""
    metric_type = getattr(metric, "type", "")
    if metric_type == "eou_metrics":
        status: dict[str, Any] = {"type": "metrics.eou"}
        for field_name in (
            "end_of_utterance_delay",
            "transcription_delay",
            "on_user_turn_completed_delay",
        ):
            duration = _milliseconds(getattr(metric, field_name, None))
            if duration is not None:
                status[f"{field_name}_ms"] = duration
        return status
    if metric_type == "tts_metrics":
        status = {"type": "metrics.tts"}
        ttfb = _milliseconds(getattr(metric, "ttfb", None))
        if ttfb is not None:
            status["ttfb_ms"] = ttfb
        status["streamed"] = bool(getattr(metric, "streamed", False))
        status["connection_reused"] = bool(getattr(metric, "connection_reused", False))
        return status
    if metric_type == "stt_metrics":
        status = {"type": "metrics.stt"}
        for field_name in ("duration", "audio_duration"):
            duration = _milliseconds(getattr(metric, field_name, None))
            if duration is not None:
                status[f"{field_name}_ms"] = duration
        status["streamed"] = bool(getattr(metric, "streamed", False))
        status["connection_reused"] = bool(getattr(metric, "connection_reused", False))
        return status
    if metric_type == "interruption_metrics":
        status = {"type": "metrics.interruption"}
        for field_name in ("total_duration", "prediction_duration", "detection_delay"):
            duration = _milliseconds(getattr(metric, field_name, None))
            if duration is not None:
                status[f"{field_name}_ms"] = duration
        return status
    return None


async def handle_control_message(
    packet: Any,
    *,
    allowed_identity: str,
    session: Any,
    assistant: Any,
    conversation_state: ConversationState,
    publisher: Any,
) -> bool:
    if getattr(packet, "topic", None) != CONTROL_TOPIC:
        return False
    if (
        not allowed_identity
        or _identity_value(getattr(packet, "participant", None)) != allowed_identity
    ):
        return False

    message = parse_control_packet(getattr(packet, "data", b""))
    if message is None:
        return False

    if message.command == "new":
        if message.conversation_id is None or not conversation_state.reset(
            message.conversation_id
        ):
            return False
        await session.interrupt(force=True)
        await assistant.update_chat_ctx(llm.ChatContext.empty())
        await publisher.publish(
            {
                "type": "session.ready",
                "conversation_fingerprint": conversation_fingerprint(
                    conversation_state.current
                ),
            }
        )
    elif message.command == "stop":
        await session.interrupt(force=True)
        await publisher.publish({"type": "run.cancelled"})
    elif message.command == "status":
        await publisher.publish(
            {
                "type": "session.ready",
                "conversation_fingerprint": conversation_fingerprint(
                    conversation_state.current
                ),
            }
        )
    return True


async def _logged_text_input(
    session: AgentSession, event: room_io.TextInputEvent
) -> None:
    logger.info(
        "LiveKit text input received",
        extra={
            "chars": len(event.text),
            "participant": (
                event.participant.identity if event.participant else "unknown"
            ),
        },
    )
    async with session._claim_user_turn():
        await session.interrupt()
        session.generate_reply(user_input=event.text)


server = AgentServer(
    num_idle_processes=1,
    drain_timeout=30,
    session_end_timeout=20,
)


@server.rtc_session(agent_name=AGENT_NAME)
async def hermes_voice_agent(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    await ctx.connect()
    linked_identity = await _wait_for_linked_identity(ctx.room)
    fallback_conversation_id = _safe_session_id(ctx.room.name)
    conversation_state = ConversationState(
        parse_conversation_id(
            _participant_attribute(ctx.room, linked_identity, "hermes.conversation_id"),
            fallback_conversation_id,
        )
    )

    client = HermesClient(HermesConfig.from_environment())
    approval_broker = ApprovalBroker(ctx.room)
    status_publisher = StatusPublisher(ctx.room, linked_identity)
    model = HermesLLM(
        client=client,
        approval_broker=approval_broker,
        conversation_state=conversation_state,
        status_callback=status_publisher.publish,
    )
    session = build_session(model)
    assistant = Assistant(model)
    background_tasks: set[asyncio.Task[Any]] = set()

    def publish_status(status: dict[str, Any] | None) -> None:
        if status is None:
            return
        task = asyncio.create_task(status_publisher.publish(status))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    @session.on("agent_state_changed")
    def on_agent_state_changed(event: Any) -> None:
        state = str(event.new_state)
        logger.info(
            "LiveKit agent state changed",
            extra={"state": state},
        )
        publish_status({"type": "agent.state", "state": state})

    @session.on("user_state_changed")
    def on_user_state_changed(event: Any) -> None:
        publish_status({"type": "user.state", "state": str(event.new_state)})

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event: Any) -> None:
        publish_status({"type": "user.transcription", "is_final": bool(event.is_final)})

    @session.on("metrics_collected")
    def on_metrics_collected(event: Any) -> None:
        publish_status(safe_metric_status(event.metrics))

    @session.on("overlapping_speech")
    def on_overlapping_speech(event: Any) -> None:
        publish_status(
            {
                "type": "speech.overlap",
                "is_interruption": bool(event.is_interruption),
                "detection_delay_ms": _milliseconds(event.detection_delay) or 0,
                "prediction_duration_ms": _milliseconds(event.prediction_duration) or 0,
            }
        )

    @session.on("conversation_item_added")
    def on_conversation_item_added(event: Any) -> None:
        item = event.item
        logger.info(
            "LiveKit conversation item added",
            extra={"role": str(getattr(item, "role", "unknown"))},
        )

    @session.on("error")
    def on_session_error(event: Any) -> None:
        logger.error(
            "LiveKit session error",
            extra={
                "error_type": type(event.error).__name__,
                "source_type": type(event.source).__name__,
            },
        )

    def on_data_received(packet: rtc.DataPacket) -> None:
        if approval_broker.handle_data_packet(packet):
            return
        if getattr(packet, "topic", None) != CONTROL_TOPIC:
            return
        task = asyncio.create_task(
            handle_control_message(
                packet,
                allowed_identity=linked_identity,
                session=session,
                assistant=assistant,
                conversation_state=conversation_state,
                publisher=status_publisher,
            )
        )
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    ctx.room.on("data_received", on_data_received)

    async def shutdown() -> None:
        approval_broker.deny_all()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        await client.close()

    ctx.add_shutdown_callback(shutdown)

    await session.start(
        agent=assistant,
        room=ctx.room,
        room_options=build_room_options(),
    )
    await status_publisher.publish(
        {
            "type": "session.ready",
            "conversation_fingerprint": conversation_fingerprint(
                conversation_state.current
            ),
        }
    )
    logger.info("Hermes Bengali voice session connected")


if __name__ == "__main__":
    cli.run_app(server)
