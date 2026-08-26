from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from livekit.agents import APIConnectOptions, llm
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from approval import ApprovalBroker
from hermes_client import HermesClient
from realtime_protocol import ConversationState, route_mention
from realtime_status import safe_status_from_hermes

logger = logging.getLogger("hermes-voice")

StatusCallback = Callable[[dict[str, Any]], Awaitable[object]]

VOICE_INSTRUCTIONS = """You are Hermes Main/Commander speaking through a phone.
Reply in natural, concise Bengali unless the user asks for another language.
Use the existing Hermes tools, memory, skills and routing normally.
Keep spoken progress updates short and never read raw logs, JSON, credentials, or long paths.
Never treat spoken consent as approval for a destructive or sensitive action. Such approval
must arrive only through the Android confirmation UI; if it does not, do not perform it.
"""


def _messages_for_hermes(
    chat_ctx: llm.ChatContext,
) -> tuple[str, list[dict[str, str]]]:
    messages: list[dict[str, str]] = []
    for item in chat_ctx.items:
        if not isinstance(item, llm.ChatMessage):
            continue
        if item.role not in {"user", "assistant"}:
            continue
        text = (item.text_content or "").strip()
        if text:
            messages.append({"role": item.role, "content": text})

    for index in range(len(messages) - 1, -1, -1):
        if messages[index]["role"] == "user":
            user_input = messages[index]["content"]
            return user_input, messages[:index]
    raise ValueError("Hermes requires a user message")


class HermesLLM(llm.LLM):
    def __init__(
        self,
        *,
        client: HermesClient,
        approval_broker: ApprovalBroker,
        conversation_state: ConversationState | None = None,
        status_callback: StatusCallback | None = None,
        session_id: str | None = None,
    ) -> None:
        super().__init__()
        if conversation_state is None:
            if session_id is None:
                raise ValueError("a conversation state is required")
            conversation_state = ConversationState(session_id)
        self._client = client
        self._approval_broker = approval_broker
        self._conversation_state = conversation_state
        self._status_callback = status_callback

    @property
    def model(self) -> str:
        return "hermes-main"

    @property
    def provider(self) -> str:
        return "local-hermes"

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: Any = None,
        tool_choice: Any = None,
        extra_kwargs: Any = None,
    ) -> llm.LLMStream:
        del parallel_tool_calls, tool_choice, extra_kwargs
        return _HermesLLMStream(
            self,
            client=self._client,
            approval_broker=self._approval_broker,
            conversation_state=self._conversation_state,
            status_callback=self._status_callback,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )


class _HermesLLMStream(llm.LLMStream):
    def __init__(
        self,
        model: HermesLLM,
        *,
        client: HermesClient,
        approval_broker: ApprovalBroker,
        conversation_state: ConversationState,
        status_callback: StatusCallback | None,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        conn_options: APIConnectOptions,
    ) -> None:
        self._client = client
        self._approval_broker = approval_broker
        self._conversation_state = conversation_state
        self._status_callback = status_callback
        self._run_id: str | None = None
        super().__init__(
            model,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
        )

    def _emit_text(self, text: str) -> None:
        if not text:
            return
        self._event_ch.send_nowait(
            llm.ChatChunk(
                id=self._run_id or "hermes",
                delta=llm.ChoiceDelta(role="assistant", content=text),
            )
        )

    async def _publish_status(self, status: dict[str, Any] | None) -> None:
        if status is None or self._status_callback is None:
            return
        try:
            await self._status_callback(status)
        except Exception as exc:
            logger.warning(
                "Hermes status callback failed",
                extra={"error_type": type(exc).__name__},
            )

    async def _run(self) -> None:
        user_input, history = _messages_for_hermes(self._chat_ctx)
        route = route_mention(user_input)
        if route.mention is not None and route.status is not None:
            await self._publish_status(
                {
                    "type": "delegation.requested",
                    "mention": route.mention,
                    "status": route.status,
                }
            )
        emitted = ""
        first_delta_sent = False
        logger.info(
            "starting Hermes LLM run",
            extra={"input_chars": len(user_input), "history_items": len(history)},
        )
        try:
            hermes_request_started = time.monotonic()
            self._run_id = await self._client.start_run(
                input=route.hermes_input,
                session_id=self._conversation_state.current,
                conversation_history=history,
                instructions=VOICE_INSTRUCTIONS,
            )
            logger.info("Hermes LLM run created")
            async for event in self._client.stream_events(self._run_id):
                event_type = event.get("event")
                logger.info(
                    "Hermes LLM event received",
                    extra={"event_type": str(event_type)},
                )
                await self._publish_status(safe_status_from_hermes(event))
                if event_type == "message.delta":
                    if not first_delta_sent:
                        first_delta_sent = True
                        await self._publish_status(
                            {
                                "type": "first_hermes_delta",
                                "duration_ms": max(
                                    0,
                                    round(
                                        (time.monotonic() - hermes_request_started)
                                        * 1000
                                    ),
                                ),
                            }
                        )
                    delta = str(event.get("delta") or "")
                    emitted += delta
                    self._emit_text(delta)
                elif event_type == "approval.request":
                    choice = await self._approval_broker.request_decision(
                        event, run_id=self._run_id
                    )
                    await self._client.resolve_approval(self._run_id, choice)
                elif event_type == "run.completed":
                    output = str(event.get("output") or "")
                    if not emitted:
                        self._emit_text(output)
                    elif output and output.startswith(emitted):
                        self._emit_text(output[len(emitted) :])
                elif event_type == "run.failed":
                    raise RuntimeError(str(event.get("error") or "Hermes run failed"))
                elif event_type == "run.cancelled":
                    break
        except asyncio.CancelledError:
            if self._run_id is not None:
                with suppress(Exception):
                    await asyncio.shield(self._client.stop_run(self._run_id))
            raise
        except Exception:
            logger.exception("Hermes LLM run failed")
            raise
