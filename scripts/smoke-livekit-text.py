"""Headless Hermes text smoke test that never prints content or credentials."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from livekit import api, rtc

AGENT_NAME = "hermes-voice"
STATUS_TOPIC = "hermes.status"
TRANSCRIPTION_TOPIC = "lk.transcription"
PROTOCOL_VERSION = 1
MAX_PACKET_BYTES = 4096


def _participant_token(
    *,
    api_key: str,
    api_secret: str,
    room_name: str,
    identity: str,
    conversation_id: str,
) -> str:
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_attributes({"hermes.conversation_id": conversation_id})
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .with_room_config(
            api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)])
        )
        .with_ttl(timedelta(minutes=10))
        .to_jwt()
    )


async def run_smoke() -> dict[str, int]:
    load_dotenv(".env.local")
    url = os.environ.get("LIVEKIT_URL", "").strip()
    api_key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()
    if not all((url, api_key, api_secret)):
        raise RuntimeError("environment")

    suffix = uuid.uuid4().hex
    room_name = f"hermes-text-smoke-{suffix[:12]}"
    identity = f"hermes-android-smoke-{suffix[:12]}"
    conversation_id = f"smoke:{suffix}"
    expected_fingerprint = hashlib.sha256(conversation_id.encode()).hexdigest()[:12]
    token = _participant_token(
        api_key=api_key,
        api_secret=api_secret,
        room_name=room_name,
        identity=identity,
        conversation_id=conversation_id,
    )

    room = rtc.Room()
    reader_tasks: set[asyncio.Task[None]] = set()
    status_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    session_ready = asyncio.Event()
    first_chunk = asyncio.Event()
    transcript_complete = asyncio.Event()
    transcript_chunk_count = 0
    first_chunk_char_count = 0
    first_chunk_at: float | None = None

    def track(coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        reader_tasks.add(task)
        task.add_done_callback(reader_tasks.discard)

    def on_status(reader: rtc.TextStreamReader, _identity: str) -> None:
        async def consume() -> None:
            raw = await reader.read_all()
            if not raw or len(raw.encode("utf-8")) > MAX_PACKET_BYTES:
                return
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return
            if (
                not isinstance(payload, dict)
                or payload.get("version") != PROTOCOL_VERSION
                or not isinstance(payload.get("type"), str)
            ):
                return
            event_type = payload["type"]
            status_events[event_type].append(payload)
            if (
                event_type == "session.ready"
                and payload.get("conversation_fingerprint") == expected_fingerprint
            ):
                session_ready.set()

        track(consume())

    def on_transcription(reader: rtc.TextStreamReader, _identity: str) -> None:
        async def consume() -> None:
            nonlocal transcript_chunk_count, first_chunk_char_count, first_chunk_at
            async for chunk in reader:
                if not chunk:
                    continue
                transcript_chunk_count += 1
                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                    first_chunk_char_count = len(chunk)
                    first_chunk.set()
            if transcript_chunk_count:
                transcript_complete.set()

        track(consume())

    room.register_text_stream_handler(STATUS_TOPIC, on_status)
    room.register_text_stream_handler(TRANSCRIPTION_TOPIC, on_transcription)

    try:
        await room.connect(url, token)
        print("ROOM_CONNECTED=true")
        await asyncio.wait_for(session_ready.wait(), timeout=45)
        print("SESSION_FINGERPRINT_MATCH=true")

        send_started = time.perf_counter()
        await room.local_participant.send_text(
            "কোনো টুল ব্যবহার করবেন না। এক বাক্যে বলুন যে টেক্সট সংযোগ কাজ করছে।",
            topic="lk.chat",
        )
        packet_sent = time.perf_counter()
        print("CHAT_PACKET_SENT=true")

        await asyncio.wait_for(first_chunk.wait(), timeout=90)
        await asyncio.wait_for(transcript_complete.wait(), timeout=90)
        progressive = transcript_chunk_count >= 2 or first_chunk_char_count >= 8
        if not progressive:
            raise RuntimeError("incremental_transcription")
        print("INCREMENTAL_TRANSCRIPTION=true")

        async with asyncio.timeout(30):
            while "first_hermes_delta" not in status_events:
                await asyncio.sleep(0.05)

        assert first_chunk_at is not None
        latencies = {
            "text_send_to_packet_ms": round((packet_sent - send_started) * 1000),
            "text_send_to_first_ui_stream_ms": round(
                (first_chunk_at - send_started) * 1000
            ),
            "hermes_request_to_first_delta_ms": int(
                status_events["first_hermes_delta"][0].get("duration_ms", 0)
            ),
        }
        if status_events.get("metrics.tts"):
            latencies["tts_ttfb_ms"] = int(
                status_events["metrics.tts"][-1].get("ttfb_ms", 0)
            )

        log_directory = Path("logs")
        log_directory.mkdir(exist_ok=True)
        (log_directory / "realtime-latency-latest.json").write_text(
            json.dumps(latencies, separators=(",", ":")),
            encoding="utf-8",
        )
        return latencies
    finally:
        await room.disconnect()
        if reader_tasks:
            await asyncio.gather(*reader_tasks, return_exceptions=True)


def main() -> int:
    try:
        latencies = asyncio.run(run_smoke())
    except Exception as exc:
        print("TEXT_SMOKE_PASS=false")
        print(f"FAILURE_TYPE={type(exc).__name__}")
        return 1

    print("TEXT_SMOKE_PASS=true")
    for name, duration in sorted(latencies.items()):
        print(f"LATENCY_{name.upper()}={duration}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
