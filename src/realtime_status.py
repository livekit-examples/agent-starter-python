"""Content-free status projection and latency reporting for Hermes sessions."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from numbers import Real
from typing import Any

from livekit import rtc

from realtime_protocol import PROTOCOL_VERSION, STATUS_TOPIC

logger = logging.getLogger("hermes-voice")

SAFE_EVENT_FIELDS = {
    "session.ready": ("conversation_fingerprint",),
    "tool.started": ("tool",),
    "tool.completed": ("tool", "duration", "error"),
    "subagent.start": ("status",),
    "subagent.complete": ("status", "duration_seconds"),
    "approval.request": (),
    "run.completed": (),
    "run.failed": (),
    "run.cancelled": (),
}

_SAFE_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
_SAFE_SUBAGENT_STATUS = frozenset(
    {"assigned", "running", "completed", "failed", "cancelled"}
)
_FINGERPRINT = re.compile(r"[0-9a-f]{12}\Z")


def conversation_fingerprint(conversation_id: str) -> str:
    """Return a short one-way identifier used only to prove session continuity."""
    return hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:12]


def _safe_duration(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    if value < 0:
        return None
    return value


def safe_status_from_hermes(event: dict[str, Any]) -> dict[str, Any] | None:
    """Project a Hermes SSE event into a strict, content-free status packet."""
    event_type = event.get("event")
    if not isinstance(event_type, str) or event_type not in SAFE_EVENT_FIELDS:
        return None

    status: dict[str, Any] = {"type": event_type}
    if event_type == "session.ready":
        fingerprint = event.get("conversation_fingerprint")
        if isinstance(fingerprint, str) and _FINGERPRINT.fullmatch(fingerprint):
            status["conversation_fingerprint"] = fingerprint
    elif event_type.startswith("tool."):
        tool = event.get("tool")
        if isinstance(tool, str) and _SAFE_NAME.fullmatch(tool):
            status["tool"] = tool
        if event_type == "tool.completed":
            duration = _safe_duration(event.get("duration"))
            if duration is not None:
                status["duration"] = duration
            if "error" in event:
                status["error"] = bool(event["error"])
    elif event_type.startswith("subagent."):
        subagent_status = event.get("status")
        if subagent_status in _SAFE_SUBAGENT_STATUS:
            status["status"] = subagent_status
        duration = _safe_duration(event.get("duration_seconds"))
        if event_type == "subagent.complete" and duration is not None:
            status["duration_seconds"] = duration

    return status


@dataclass
class LatencySpan:
    """Collect monotonic timestamps and publish durations without user content."""

    op_id: str
    _marks: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    def mark(self, name: str, timestamp: float) -> None:
        if not _SAFE_NAME.fullmatch(name):
            raise ValueError("latency mark name is invalid")
        if not isinstance(timestamp, Real) or isinstance(timestamp, bool):
            raise TypeError("latency timestamp must be numeric")
        self._marks.setdefault(name, float(timestamp))

    def payload(self) -> dict[str, Any]:
        durations: dict[str, int] = {}
        ordered_marks = list(self._marks.items())
        for (start_name, start), (end_name, end) in zip(
            ordered_marks, ordered_marks[1:], strict=False
        ):
            durations[f"{start_name}_to_{end_name}"] = max(
                0, round((end - start) * 1000)
            )
        return {"type": "latency", "op_id": self.op_id, "durations_ms": durations}


class StatusPublisher:
    def __init__(self, room: rtc.Room, destination_identity: str) -> None:
        self._room = room
        self._destination_identity = destination_identity

    async def publish(self, event: dict[str, Any]) -> bool:
        wire_event = {
            "version": PROTOCOL_VERSION,
            **{key: value for key, value in event.items() if key != "version"},
        }
        payload = json.dumps(wire_event, separators=(",", ":"), ensure_ascii=False)
        try:
            await self._room.local_participant.send_text(
                payload,
                topic=STATUS_TOPIC,
                destination_identities=[self._destination_identity],
            )
        except Exception as exc:
            logger.warning(
                "status publish failed",
                extra={"error_type": type(exc).__name__},
            )
            return False
        return True
