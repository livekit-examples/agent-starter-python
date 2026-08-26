from dataclasses import dataclass

import pytest

from agent import (
    AGENT_NAME,
    BENGALI_KEYTERMS,
    _safe_session_id,
    build_room_options,
    build_turn_handling_options,
    handle_control_message,
    resolve_linked_identity,
    safe_metric_status,
)
from realtime_protocol import ConversationState


def test_agent_name_matches_android_dispatch_name() -> None:
    assert AGENT_NAME == "hermes-voice"


def test_session_id_is_stable_and_safe() -> None:
    assert _safe_session_id("বাংলা room / one") == "voice:room---one"


def test_bengali_stt_has_product_keyterms() -> None:
    assert {"Hermes", "OmniRoute", "Chrome", "GitHub"} <= set(BENGALI_KEYTERMS)


def test_room_options_stream_text_without_waiting_for_audio() -> None:
    options = build_room_options()

    assert options.close_on_disconnect is False
    assert options.text_output.sync_transcription is False


def test_turn_options_use_dynamic_endpointing_and_adaptive_interruption() -> None:
    options = build_turn_handling_options()

    assert options["endpointing"] == {
        "mode": "dynamic",
        "min_delay": 0.35,
        "max_delay": 1.2,
    }
    assert options["interruption"]["mode"] == "adaptive"
    assert options["interruption"]["min_duration"] == 0.3
    assert options["interruption"]["min_words"] == 0
    assert options["preemptive_generation"] == {"enabled": False}


@dataclass
class _Identity:
    value: str


@dataclass
class _Participant:
    identity: _Identity
    attributes: dict[str, str] | None = None


@dataclass
class _Packet:
    data: bytes
    topic: str
    participant: _Participant


class _Session:
    def __init__(self) -> None:
        self.interrupt_calls: list[bool] = []

    async def interrupt(self, *, force: bool = False) -> None:
        self.interrupt_calls.append(force)


class _Assistant:
    def __init__(self) -> None:
        self.chat_context = None

    async def update_chat_ctx(self, chat_context) -> None:
        self.chat_context = chat_context


class _Publisher:
    def __init__(self) -> None:
        self.statuses: list[dict] = []

    async def publish(self, status: dict) -> bool:
        self.statuses.append(status)
        return True


def _packet(
    command: str,
    *,
    identity: str = "phone",
    conversation_id: str | None = None,
) -> _Packet:
    conversation = f',"conversation_id":"{conversation_id}"' if conversation_id else ""
    return _Packet(
        data=(
            f'{{"version":1,"op_id":"op-1","command":"{command}"{conversation}}}'
        ).encode(),
        topic="hermes.control",
        participant=_Participant(_Identity(identity)),
    )


@pytest.mark.asyncio
async def test_new_control_resets_context_after_exact_identity_check() -> None:
    session = _Session()
    assistant = _Assistant()
    state = ConversationState("conv-1")
    publisher = _Publisher()

    result = await handle_control_message(
        _packet("new", conversation_id="conv-2"),
        allowed_identity="phone",
        session=session,
        assistant=assistant,
        conversation_state=state,
        publisher=publisher,
    )

    assert result is True
    assert state.current == "conv-2"
    assert session.interrupt_calls == [True]
    assert assistant.chat_context.items == []
    assert publisher.statuses[0]["type"] == "session.ready"


@pytest.mark.asyncio
async def test_control_from_other_participant_is_ignored() -> None:
    session = _Session()
    assistant = _Assistant()
    state = ConversationState("conv-1")
    publisher = _Publisher()

    result = await handle_control_message(
        _packet("stop", identity="intruder"),
        allowed_identity="phone",
        session=session,
        assistant=assistant,
        conversation_state=state,
        publisher=publisher,
    )

    assert result is False
    assert session.interrupt_calls == []
    assert publisher.statuses == []


@pytest.mark.asyncio
async def test_stop_and_status_controls_are_content_free() -> None:
    session = _Session()
    assistant = _Assistant()
    state = ConversationState("conv-1")
    publisher = _Publisher()

    assert await handle_control_message(
        _packet("stop"),
        allowed_identity="phone",
        session=session,
        assistant=assistant,
        conversation_state=state,
        publisher=publisher,
    )
    assert await handle_control_message(
        _packet("status"),
        allowed_identity="phone",
        session=session,
        assistant=assistant,
        conversation_state=state,
        publisher=publisher,
    )

    assert session.interrupt_calls == [True]
    assert publisher.statuses[0] == {"type": "run.cancelled"}
    assert publisher.statuses[1]["type"] == "session.ready"
    assert "conv-1" not in repr(publisher.statuses)


def test_linked_identity_prefers_android_participant() -> None:
    class _Room:
        def __init__(self) -> None:
            self.remote_participants = {
                "observer": _Participant(_Identity("observer")),
                "android": _Participant(_Identity("hermes-android-installation")),
            }

    assert resolve_linked_identity(_Room()) == "hermes-android-installation"


def test_metric_projection_never_includes_transcript_or_request_id() -> None:
    class _Metric:
        type = "tts_metrics"
        ttfb = 0.125
        streamed = True
        connection_reused = True
        request_id = "secret-request"
        text = "private transcript"

    status = safe_metric_status(_Metric())

    assert status == {
        "type": "metrics.tts",
        "ttfb_ms": 125,
        "streamed": True,
        "connection_reused": True,
    }
    assert "private" not in repr(status)
