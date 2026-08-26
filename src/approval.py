from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

APPROVAL_REQUEST_TOPIC = "hermes.approval.request"
APPROVAL_RESPONSE_TOPIC = "hermes.approval.response"
ALLOWED_CHOICES = {"once", "deny"}


@dataclass(frozen=True)
class ApprovalRequest:
    run_id: str
    target: str
    action: str
    reason: str
    agent: str = "Hermes Main"

    @classmethod
    def from_event(cls, event: dict[str, Any], *, run_id: str) -> ApprovalRequest:
        command = str(event.get("command") or event.get("target") or "")
        description = str(
            event.get("description") or event.get("action") or "Sensitive action"
        )
        reason = str(
            event.get("reason")
            or event.get("explanation")
            or "Hermes requires explicit confirmation before continuing."
        )
        raw_agent = str(event.get("agent") or event.get("specialist") or "").strip()
        agent = (
            raw_agent
            if re.fullmatch(r"[A-Za-z0-9 _.-]{1,80}", raw_agent)
            else "Hermes Main"
        )
        return cls(
            run_id=run_id,
            target=command,
            action=description,
            reason=reason,
            agent=agent,
        )

    def to_wire(self) -> dict[str, str]:
        payload = asdict(self)
        payload["runId"] = payload.pop("run_id")
        return payload


@dataclass
class _PendingApproval:
    allowed_identity: str
    decision: asyncio.Future[str]


def _identity_value(participant: Any) -> str:
    identity = getattr(participant, "identity", "")
    return str(getattr(identity, "value", identity) or "")


class ApprovalBroker:
    """Binds one-shot approvals to the Android participant that received them."""

    def __init__(self, room: Any) -> None:
        self._room = room
        self._pending: dict[str, _PendingApproval] = {}

    def create_pending(
        self, request: ApprovalRequest, *, allowed_identity: str
    ) -> asyncio.Future[str]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        previous = self._pending.pop(request.run_id, None)
        if previous is not None and not previous.decision.done():
            previous.decision.set_result("deny")
        self._pending[request.run_id] = _PendingApproval(allowed_identity, future)
        return future

    async def publish(self, request: ApprovalRequest, *, allowed_identity: str) -> None:
        await self._room.local_participant.publish_data(
            json.dumps(request.to_wire(), ensure_ascii=False),
            reliable=True,
            topic=APPROVAL_REQUEST_TOPIC,
            destination_identities=[allowed_identity],
        )

    async def request_decision(self, event: dict[str, Any], *, run_id: str) -> str:
        identity = self._select_android_identity()
        if not identity:
            return "deny"
        request = ApprovalRequest.from_event(event, run_id=run_id)
        pending = self.create_pending(request, allowed_identity=identity)
        await self.publish(request, allowed_identity=identity)
        try:
            return await pending
        finally:
            self._pending.pop(run_id, None)

    def _select_android_identity(self) -> str:
        participants = getattr(self._room, "remote_participants", {})
        values = (
            participants.values() if hasattr(participants, "values") else participants
        )
        for participant in values:
            identity = _identity_value(participant)
            if identity:
                return identity
        return ""

    def handle_data_packet(self, packet: Any) -> bool:
        if getattr(packet, "topic", None) != APPROVAL_RESPONSE_TOPIC:
            return False
        try:
            raw_data = packet.data
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            payload = json.loads(raw_data)
            run_id = str(payload.get("runId", ""))
            choice = str(payload.get("choice", "")).lower()
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return False

        pending = self._pending.get(run_id)
        if (
            pending is None
            or pending.decision.done()
            or choice not in ALLOWED_CHOICES
            or _identity_value(getattr(packet, "participant", None))
            != pending.allowed_identity
        ):
            return False

        pending.decision.set_result(choice)
        return True

    def deny_all(self) -> None:
        for pending in self._pending.values():
            if not pending.decision.done():
                pending.decision.set_result("deny")
        self._pending.clear()
