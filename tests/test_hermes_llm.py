import asyncio

import pytest
from livekit.agents import llm

from hermes_llm import HermesLLM
from realtime_protocol import ConversationState


class _Client:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.started: list[dict] = []
        self.stopped: list[str] = []
        self.approvals: list[tuple[str, str]] = []

    async def start_run(self, **kwargs):
        self.started.append(kwargs)
        return "run_1"

    async def stream_events(self, run_id: str):
        for event in self.events:
            yield event

    async def stop_run(self, run_id: str):
        self.stopped.append(run_id)

    async def resolve_approval(self, run_id: str, choice: str):
        self.approvals.append((run_id, choice))


class _Broker:
    async def request_decision(self, event: dict, *, run_id: str) -> str:
        return "deny"


@pytest.mark.asyncio
async def test_stream_forwards_hermes_delta_without_duplicate_final() -> None:
    client = _Client(
        [
            {"event": "tool.started", "tool": "computer"},
            {"event": "message.delta", "delta": "কাজটি "},
            {"event": "message.delta", "delta": "হয়ে গেছে।"},
            {"event": "run.completed", "output": "কাজটি হয়ে গেছে।"},
        ]
    )
    model = HermesLLM(client=client, approval_broker=_Broker(), session_id="voice-room")
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="user", content="Calculator খোলো")

    result = await model.chat(chat_ctx=chat_ctx).collect()

    assert result.text.count("কাজটি হয়ে গেছে।") == 1
    assert client.started[0]["input"] == "Calculator খোলো"
    assert client.started[0]["session_id"] == "voice-room"


@pytest.mark.asyncio
async def test_stream_resolves_approval_only_from_broker() -> None:
    client = _Client(
        [
            {
                "event": "approval.request",
                "run_id": "run_1",
                "command": "Remove-Item safe-test.txt",
                "description": "Delete file",
            },
            {"event": "run.completed", "output": "অনুমোদন পাওয়া যায়নি।"},
        ]
    )
    model = HermesLLM(client=client, approval_broker=_Broker(), session_id="voice-room")
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="user", content="ফাইলটি মুছে দাও")

    await model.chat(chat_ctx=chat_ctx).collect()

    assert client.approvals == [("run_1", "deny")]


@pytest.mark.asyncio
async def test_cancelling_livekit_stream_stops_hermes_run() -> None:
    class _BlockingClient(_Client):
        async def stream_events(self, run_id: str):
            await asyncio.Event().wait()
            yield {}

    client = _BlockingClient([])
    model = HermesLLM(client=client, approval_broker=_Broker(), session_id="voice-room")
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="user", content="একটি লম্বা কাজ করো")

    stream = model.chat(chat_ctx=chat_ctx)
    await asyncio.sleep(0.05)
    await stream.aclose()

    assert client.stopped == ["run_1"]


@pytest.mark.asyncio
async def test_stream_uses_current_conversation_id_and_routes_mention() -> None:
    client = _Client([{"event": "run.completed", "output": "done"}])
    state = ConversationState("conv-1")
    statuses: list[dict] = []

    async def collect_status(status: dict) -> None:
        statuses.append(status)

    model = HermesLLM(
        client=client,
        approval_broker=_Broker(),
        conversation_state=state,
        status_callback=collect_status,
    )
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="user", content="@coder inspect backend")

    await model.chat(chat_ctx=chat_ctx).collect()

    assert client.started[0]["session_id"] == "conv-1"
    assert "Hermes Main" in client.started[0]["input"]
    assert "delegate" in client.started[0]["input"]
    assert statuses[0] == {
        "type": "delegation.requested",
        "mention": "coder",
        "status": "Coder assigned",
    }

    assert state.reset("conv-2") is True
    second_ctx = llm.ChatContext.empty()
    second_ctx.add_message(role="user", content="plain request")
    await model.chat(chat_ctx=second_ctx).collect()
    assert client.started[1]["session_id"] == "conv-2"


@pytest.mark.asyncio
async def test_stream_publishes_first_delta_once_and_safe_status() -> None:
    client = _Client(
        [
            {
                "event": "tool.started",
                "tool": "computer",
                "preview": "private command",
            },
            {"event": "message.delta", "delta": "আমি "},
            {"event": "message.delta", "delta": "দেখছি"},
            {"event": "run.completed", "output": "আমি দেখছি"},
        ]
    )
    statuses: list[dict] = []

    async def collect_status(status: dict) -> None:
        statuses.append(status)

    model = HermesLLM(
        client=client,
        approval_broker=_Broker(),
        conversation_state=ConversationState("conv-1"),
        status_callback=collect_status,
    )
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="user", content="check")

    result = await model.chat(chat_ctx=chat_ctx).collect()

    assert result.text == "আমি দেখছি"
    assert statuses[0] == {"type": "tool.started", "tool": "computer"}
    first_delta = [
        status for status in statuses if status["type"] == "first_hermes_delta"
    ]
    assert len(first_delta) == 1
    assert first_delta[0]["duration_ms"] >= 0
    assert {"type": "run.completed"} in statuses
    assert "private command" not in repr(statuses)
