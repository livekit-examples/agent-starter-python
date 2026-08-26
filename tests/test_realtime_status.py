import json

import pytest

from realtime_status import (
    LatencySpan,
    StatusPublisher,
    conversation_fingerprint,
    safe_status_from_hermes,
)


def test_tool_status_drops_preview_arguments_and_paths():
    status = safe_status_from_hermes(
        {
            "event": "tool.started",
            "tool": "computer",
            "preview": "contains private command",
            "args": {"token": "secret"},
            "path": "C:/private",
        }
    )

    assert status == {"type": "tool.started", "tool": "computer"}


def test_message_delta_and_unknown_events_are_not_republished_as_status():
    assert (
        safe_status_from_hermes({"event": "message.delta", "delta": "private answer"})
        is None
    )
    assert safe_status_from_hermes({"event": "reasoning", "text": "private"}) is None


def test_failure_status_does_not_expose_error_text():
    assert safe_status_from_hermes(
        {"event": "run.failed", "error": "Bearer private-secret"}
    ) == {"type": "run.failed"}


def test_session_fingerprint_is_short_and_irreversible():
    fingerprint = conversation_fingerprint("conversation-private")

    assert len(fingerprint) == 12
    assert all(character in "0123456789abcdef" for character in fingerprint)
    assert "conversation-private" not in fingerprint


def test_latency_span_contains_durations_not_transcripts():
    span = LatencySpan("turn-1")
    span.mark("worker_received", 10.0)
    span.mark("first_hermes_delta", 10.25)

    payload = span.payload()

    assert payload["type"] == "latency"
    assert payload["op_id"] == "turn-1"
    assert payload["durations_ms"]["worker_received_to_first_hermes_delta"] == 250
    assert "text" not in repr(payload).lower()


class _LocalParticipant:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    async def send_text(self, text: str, **kwargs) -> None:
        if self.fail:
            raise RuntimeError("private transport detail")
        self.calls.append({"text": text, **kwargs})


class _Room:
    def __init__(self, *, fail: bool = False) -> None:
        self.local_participant = _LocalParticipant(fail=fail)


@pytest.mark.asyncio
async def test_status_publisher_targets_only_linked_identity():
    room = _Room()
    publisher = StatusPublisher(room, "phone-1")

    assert await publisher.publish({"type": "run.completed"}) is True

    assert len(room.local_participant.calls) == 1
    call = room.local_participant.calls[0]
    assert json.loads(call["text"]) == {"type": "run.completed"}
    assert call["topic"] == "hermes.status"
    assert call["destination_identities"] == ["phone-1"]


@pytest.mark.asyncio
async def test_status_publisher_failure_does_not_terminate_session():
    publisher = StatusPublisher(_Room(fail=True), "phone-1")

    assert await publisher.publish({"type": "run.completed"}) is False
