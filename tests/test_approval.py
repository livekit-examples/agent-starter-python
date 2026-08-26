from dataclasses import dataclass

import pytest

from approval import ApprovalBroker, ApprovalRequest


@dataclass
class _Identity:
    value: str


@dataclass
class _Participant:
    identity: _Identity


@dataclass
class _Packet:
    data: bytes
    topic: str
    participant: _Participant


class _LocalParticipant:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, bool, list[str]]] = []

    async def publish_data(
        self,
        payload: str,
        *,
        reliable: bool,
        topic: str,
        destination_identities: list[str],
    ) -> None:
        self.published.append((payload, topic, reliable, destination_identities))


class _Room:
    def __init__(self) -> None:
        self.local_participant = _LocalParticipant()


@pytest.mark.asyncio
async def test_approval_requires_matching_android_identity() -> None:
    room = _Room()
    broker = ApprovalBroker(room)
    request = ApprovalRequest(
        run_id="run_1",
        target="C:\\safe-test.txt",
        action="Delete file",
        reason="User requested deletion",
    )

    pending = broker.create_pending(request, allowed_identity="android-user")
    await broker.publish(request, allowed_identity="android-user")

    assert room.local_participant.published[0][1] == "hermes.approval.request"
    assert room.local_participant.published[0][3] == ["android-user"]

    rejected = broker.handle_data_packet(
        _Packet(
            data=b'{"runId":"run_1","choice":"once"}',
            topic="hermes.approval.response",
            participant=_Participant(_Identity("attacker")),
        )
    )
    assert rejected is False
    assert not pending.done()

    accepted = broker.handle_data_packet(
        _Packet(
            data=b'{"runId":"run_1","choice":"once"}',
            topic="hermes.approval.response",
            participant=_Participant(_Identity("android-user")),
        )
    )
    assert accepted is True
    assert await pending == "once"


@pytest.mark.asyncio
async def test_approval_rejects_voice_or_persistent_choices() -> None:
    broker = ApprovalBroker(_Room())
    pending = broker.create_pending(
        ApprovalRequest("run_2", "target", "action", "reason"),
        allowed_identity="android-user",
    )

    for choice in ("yes", "approve", "session", "always"):
        assert (
            broker.handle_data_packet(
                _Packet(
                    data=(f'{{"runId":"run_2","choice":"{choice}"}}').encode(),
                    topic="hermes.approval.response",
                    participant=_Participant(_Identity("android-user")),
                )
            )
            is False
        )

    assert not pending.done()

    assert (
        broker.handle_data_packet(
            _Packet(
                data=b'{"runId":"run_2","choice":"deny"}',
                topic="hermes.approval.response",
                participant=_Participant(_Identity("android-user")),
            )
        )
        is True
    )
    assert await pending == "deny"


@pytest.mark.asyncio
async def test_control_packet_cannot_resolve_approval() -> None:
    broker = ApprovalBroker(_Room())
    pending = broker.create_pending(
        ApprovalRequest("run_3", "target", "action", "reason"),
        allowed_identity="android-user",
    )

    assert (
        broker.handle_data_packet(
            _Packet(
                data=b'{"version":1,"op_id":"x","command":"approve"}',
                topic="hermes.control",
                participant=_Participant(_Identity("android-user")),
            )
        )
        is False
    )
    assert not pending.done()

    broker.deny_all()
    assert await pending == "deny"
