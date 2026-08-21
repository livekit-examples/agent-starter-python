"""Shared fixtures and a scriptable fake LiveKit Inference server."""

import asyncio
import json
from collections.abc import Callable

import pytest
from websockets.protocol import State


@pytest.fixture(autouse=True)
def fake_livekit_credentials(monkeypatch):
    """Give the token minter local-only credentials.

    Tokens are signed locally, so these never leave the process and never reach
    real LiveKit Inference.
    """
    monkeypatch.setenv("LIVEKIT_API_KEY", "APItestkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-not-a-real-one")


class FakeInferenceWebsocket:
    """A scripted stand-in for a LiveKit Inference WebSocket.

    Records every JSON frame the service sends, and replies according to
    ``script``: a callable taking the received message and returning a list of
    server messages to push back. ``session.create`` is acked automatically
    unless ``ack`` says otherwise, since every session depends on it.
    """

    def __init__(
        self,
        *,
        ack: dict | None = None,
        script: Callable[[dict], list[dict]] | None = None,
        response_delay: float = 0.01,
    ):
        self.sent: list[dict] = []
        self.state = State.OPEN
        self.close_calls = 0
        self._ack = ack if ack is not None else {"type": "session.created"}
        self._script = script
        self._response_delay = response_delay
        self._incoming: asyncio.Queue = asyncio.Queue()
        self._pending: set[asyncio.Task] = set()

    # -- client -> server ----------------------------------------------------

    async def send(self, message: str):
        """Record a frame from the service and run the script over it."""
        data = json.loads(message)
        self.sent.append(data)

        if data.get("type") == "session.create":
            # The connect path awaits this ack directly, so answer immediately.
            self.push(self._ack)
            return

        if self._script:
            responses = self._script(data)
            if responses:
                # Deliver over a turn of the event loop rather than inline. A
                # real LiveKit Inference's reply always lands after the caller returns,
                # and answering synchronously would let a turn terminator
                # overtake the pipeline's own bookkeeping.
                task = asyncio.create_task(self._deliver(responses))
                self._pending.add(task)
                task.add_done_callback(self._pending.discard)

    async def _deliver(self, responses: list[dict]):
        await asyncio.sleep(self._response_delay)
        for response in responses:
            self.push(response)

    def sent_of_type(self, mtype: str) -> list[dict]:
        """Every recorded frame of the given type."""
        return [m for m in self.sent if m.get("type") == mtype]

    # -- server -> client ----------------------------------------------------

    def push(self, message: dict):
        """Queue a server message for the service to read."""
        self._incoming.put_nowait(json.dumps(message))

    async def recv(self) -> str:
        """Read one server message (used for the session.create ack)."""
        return await self._incoming.get()

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        message = await self._incoming.get()
        if message is None:  # sentinel from close()
            raise StopAsyncIteration
        return message

    # -- lifecycle -----------------------------------------------------------

    async def close(self, code: int = 1000, reason: str = ""):
        """Close the socket and unblock the receive loop."""
        self.close_calls += 1
        self.state = State.CLOSED
        self._incoming.put_nowait(None)

    async def ping(self):
        """No-op: the base class pings to verify a reconnect."""


def attach_fake_inference(service, **kwargs) -> list[FakeInferenceWebsocket]:
    """Point a service's dialer at fake sockets.

    Returns the list the sockets are appended to, one per connect, so tests can
    assert across reconnects.

    Args:
        service: The STT or TTS service to patch.
        **kwargs: Passed through to each ``FakeInferenceWebsocket``.

    Returns:
        A list that accumulates every socket handed to the service.
    """
    sockets: list[FakeInferenceWebsocket] = []

    async def fake_websocket_connect(uri: str, **connect_kwargs):
        socket = FakeInferenceWebsocket(**kwargs)
        socket.uri = uri
        socket.connect_kwargs = connect_kwargs
        sockets.append(socket)
        return socket

    service._websocket_connect = fake_websocket_connect
    return sockets
