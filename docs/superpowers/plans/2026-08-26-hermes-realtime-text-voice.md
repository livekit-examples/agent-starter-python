# Hermes Realtime Text + Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the installed Hermes Android voice client into an auto-connected, low-latency text-and-voice application that keeps one Hermes Main conversation and preserves the existing safety boundary.

**Architecture:** Restore LiveKit's native Session Messages path inside the existing room and AgentSession. Add only narrow, reliable control/status messages around the current localhost Hermes SSE bridge, then normalize typed messages and voice transcripts into one Android timeline with local persistence and latency spans.

**Tech Stack:** Python 3.13, `livekit-agents` 1.7, `aiohttp`, pytest, Ruff, Kotlin 2.2, Jetpack Compose, LiveKit Android 2.28.0, LiveKit Compose Components 2.4.2, JUnit 4, Gradle 8/AGP 8.13, Android 16 device via ADB.

**Spec:** `docs/superpowers/specs/2026-08-26-hermes-realtime-text-voice-design.md`

## Global Constraints

- Hermes API remains loopback-only at `127.0.0.1`; do not add a public listener, tunnel, proxy, or Android credential.
- Android continues to authenticate through the existing LiveKit Development Token Server and must contain no LiveKit API key, LiveKit API secret, or Hermes API key.
- Hermes Main remains the only commander; mentions become routing instructions to Hermes Main, not direct specialist calls.
- Interim STT is display-only; only LiveKit's committed/final user turn may start Hermes.
- No `/approve` command and no spoken or typed affirmative may resolve a destructive approval.
- Approval responses remain run-scoped and participant-scoped choices of `once` or `deny`.
- The microphone is off by default; text auto-connects on app launch; voice toggles inside the same room.
- Keep persistent LiveKit and Hermes HTTP connections warm and use streaming/callbacks instead of polling.
- Preserve every pre-existing dirty-worktree change and stage only task-owned files.
- Do not re-run the prior broad acceptance suite; verify only behavior touched by this upgrade.

## File Structure

### Windows worker repository

- Create `src/realtime_protocol.py`: validated control packets, mention routing, conversation IDs, and safe status projection.
- Create `src/realtime_status.py`: participant-targeted reliable status publishing and content-free latency spans.
- Modify `src/hermes_llm.py`: dynamic shared session ID, mention-aware input, SSE status callbacks, and first-delta timing.
- Modify `src/agent.py`: text output streaming, responsive turn settings, session/control wiring, and SDK metric hooks.
- Modify `tests/test_hermes_llm.py`: streaming/status/session assertions.
- Create `tests/test_realtime_protocol.py`: pure protocol and routing tests.
- Create `tests/test_realtime_status.py`: publisher and timing tests.
- Modify `tests/test_agent.py`: room options, control handling, and event-hook tests.

### Android repository

- Create `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/HermesInput.kt`: slash and mention parsing/autocomplete.
- Create `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/RealtimeProtocol.kt`: reliable control/status JSON contracts.
- Create `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/Timeline.kt`: normalized timeline models and reducer.
- Create `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/HistoryRepository.kt`: capped private history and credential redaction.
- Create `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/LatencyTracker.kt`: content-free local spans.
- Create `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/SessionIdentity.kt`: stable installation and rotatable conversation IDs.
- Modify `app/src/main/java/io/livekit/android/example/voiceassistant/MainActivity.kt`: start directly in the unified HERMES screen.
- Modify `app/src/main/java/io/livekit/android/example/voiceassistant/viewmodel/VoiceAssistantViewModel.kt`: identity, history, and token attributes.
- Modify `app/src/main/java/io/livekit/android/example/voiceassistant/screen/VoiceAssistantScreen.kt`: auto-connect, mic-off lifecycle, message integration, commands, status, and approval dialog.
- Modify `app/src/main/java/io/livekit/android/example/voiceassistant/ui/ChatBar.kt`: immediate send and autocomplete UI.
- Modify `app/src/main/java/io/livekit/android/example/voiceassistant/ui/ChatLog.kt`: unified bubbles, streaming updates, source badges, and statuses.
- Modify `app/src/main/java/io/livekit/android/example/voiceassistant/ApprovalProtocol.kt`: optional agent label while retaining `once`/`deny` only.
- Add focused JUnit tests under `app/src/test/java/io/livekit/android/example/voiceassistant/realtime/`.
- Add focused Compose tests under `app/src/androidTest/java/io/livekit/android/example/voiceassistant/`.

---

### Task 1: Worker protocol, session identity, and mention routing

**Files:**
- Create: `src/realtime_protocol.py`
- Test: `tests/test_realtime_protocol.py`

**Interfaces:**
- Produces: `ControlMessage`, `ConversationState`, `MentionRoute`, `parse_control_packet(data: bytes) -> ControlMessage | None`, `parse_conversation_id(value: str | None, fallback: str) -> str`, `route_mention(text: str) -> MentionRoute`.
- Consumes: no production interfaces beyond Python standard-library JSON, dataclasses, and regular expressions.

- [ ] **Step 1: Write failing protocol tests**

```python
def test_control_parser_accepts_versioned_stop():
    message = parse_control_packet(
        b'{"version":1,"op_id":"op-17","command":"stop"}'
    )
    assert message == ControlMessage(1, "op-17", "stop", None)

def test_control_parser_rejects_approve_and_unknown_fields():
    assert parse_control_packet(
        b'{"version":1,"op_id":"x","command":"approve"}'
    ) is None
    assert parse_control_packet(
        b'{"version":1,"op_id":"x","command":"stop","secret":"x"}'
    ) is None

def test_conversation_state_rotates_only_to_valid_identifier():
    state = ConversationState("conv-original")
    assert state.reset("conv-next") is True
    assert state.current == "conv-next"
    assert state.reset("../../bad") is False
    assert state.current == "conv-next"

def test_coder_mention_routes_through_hermes_main():
    route = route_mention("@coder backendটা check করো")
    assert route.mention == "coder"
    assert "Hermes Main" in route.hermes_input
    assert "delegate" in route.hermes_input
    assert route.status == "Coder assigned"
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `uv run pytest tests/test_realtime_protocol.py -q`

Expected: collection fails because `realtime_protocol` does not exist.

- [ ] **Step 3: Implement the minimal pure protocol module**

```python
CONTROL_TOPIC = "hermes.control"
STATUS_TOPIC = "hermes.status"
PROTOCOL_VERSION = 1
SUPPORTED_COMMANDS = {"new", "stop", "status"}
SUPPORTED_MENTIONS = {
    "main", "architect", "researcher", "coder", "browser",
    "computer-operator", "qa", "reviewer", "security", "ops",
}

@dataclass(frozen=True)
class ControlMessage:
    version: int
    op_id: str
    command: str
    conversation_id: str | None = None

@dataclass
class ConversationState:
    current: str

    def reset(self, value: str) -> bool:
        parsed = parse_conversation_id(value, "")
        if not parsed:
            return False
        self.current = parsed
        return True
```

`parse_control_packet` must require exactly `version`, `op_id`, `command`, and optional `conversation_id`; cap payloads at 4096 bytes; reject invalid UTF-8, non-object JSON, unknown fields, unknown commands, `/approve`, and identifiers outside `[A-Za-z0-9_.:-]{1,128}`. `route_mention` must preserve unmentioned text and produce a Hermes Main orchestration instruction for supported leading mentions.

- [ ] **Step 4: Run protocol tests and verify GREEN**

Run: `uv run pytest tests/test_realtime_protocol.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the isolated worker protocol change**

```powershell
git add -- src/realtime_protocol.py tests/test_realtime_protocol.py
git commit -m "feat: add Hermes realtime protocol"
```

### Task 2: Safe worker status projection and latency spans

**Files:**
- Create: `src/realtime_status.py`
- Test: `tests/test_realtime_status.py`

**Interfaces:**
- Consumes: `STATUS_TOPIC` from Task 1 and LiveKit room/local participant APIs.
- Produces: `safe_status_from_hermes(event: dict[str, Any]) -> dict[str, Any] | None`, `LatencySpan`, and `StatusPublisher.publish(event: dict[str, Any]) -> None`.

- [ ] **Step 1: Write failing status tests**

```python
def test_tool_status_drops_preview_and_arguments():
    status = safe_status_from_hermes({
        "event": "tool.started",
        "tool": "computer",
        "preview": "contains private command",
        "args": {"token": "secret"},
    })
    assert status == {"type": "tool.started", "tool": "computer"}

def test_message_delta_is_not_republished_as_status():
    assert safe_status_from_hermes({
        "event": "message.delta", "delta": "private answer"
    }) is None

def test_latency_span_contains_durations_not_transcripts():
    span = LatencySpan("turn-1")
    span.mark("worker_received", 10.0)
    span.mark("first_hermes_delta", 10.25)
    payload = span.payload()
    assert payload["durations_ms"]["worker_received_to_first_hermes_delta"] == 250
    assert "text" not in repr(payload).lower()
```

- [ ] **Step 2: Run status tests and verify RED**

Run: `uv run pytest tests/test_realtime_status.py -q`

Expected: collection fails because `realtime_status` does not exist.

- [ ] **Step 3: Implement whitelist-only status and targeted publishing**

```python
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

class StatusPublisher:
    def __init__(self, room: rtc.Room, destination_identity: str) -> None:
        self._room = room
        self._destination_identity = destination_identity

    async def publish(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
        await self._room.local_participant.send_text(
            payload,
            topic=STATUS_TOPIC,
            destination_identities=[self._destination_identity],
        )
```

Publisher errors are logged by type only and do not terminate the voice session. Status payloads never include message deltas, reasoning, previews, command bodies, arguments, paths, or credentials. A `session.ready` event may contain only the first 12 hexadecimal characters of `sha256(conversation_id)` so focused tests can prove session continuity without exposing the identifier.

- [ ] **Step 4: Run status tests and Ruff**

Run: `uv run pytest tests/test_realtime_status.py -q && uv run ruff check src/realtime_status.py tests/test_realtime_status.py`

Expected: tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit the status module**

```powershell
git add -- src/realtime_status.py tests/test_realtime_status.py
git commit -m "feat: publish safe Hermes realtime status"
```

### Task 3: Stream Hermes events through the shared session

**Files:**
- Modify: `src/hermes_llm.py`
- Modify: `tests/test_hermes_llm.py`

**Interfaces:**
- Consumes: `ConversationState`, `route_mention`, `safe_status_from_hermes`, and an async `status_callback(dict) -> None`.
- Produces: `HermesLLM(..., conversation_state, status_callback)` with unchanged LiveKit `llm.LLM` behavior and an SSE first-delta timing event.

- [ ] **Step 1: Add failing streaming/session tests**

```python
async def test_stream_uses_current_conversation_id_and_routes_mention():
    state = ConversationState("conv-1")
    stream = make_stream("@coder inspect backend", state=state)
    await consume(stream)
    assert fake_client.start_calls[0]["session_id"] == "conv-1"
    assert "Hermes Main" in fake_client.start_calls[0]["input"]

async def test_stream_publishes_first_delta_and_safe_tool_status():
    fake_client.events = [
        {"event": "tool.started", "tool": "computer", "preview": "private"},
        {"event": "message.delta", "delta": "আমি "},
        {"event": "message.delta", "delta": "দেখছি"},
        {"event": "run.completed", "output": "আমি দেখছি"},
    ]
    await consume(make_stream("check", status_callback=statuses.append))
    assert statuses[0] == {"type": "tool.started", "tool": "computer"}
    assert sum(s.get("type") == "first_hermes_delta" for s in statuses) == 1
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `uv run pytest tests/test_hermes_llm.py -q`

Expected: constructor/signature assertions fail because dynamic state and status callbacks are absent.

- [ ] **Step 3: Implement dynamic session and status callbacks**

At the start of each `_HermesLLMStream._run`, call `route_mention(user_input)`, read `conversation_state.current`, mark `hermes_request_sent`, and then call the unchanged persistent `HermesClient.start_run`. For each SSE event, publish only `safe_status_from_hermes(event)`. Publish `first_hermes_delta` once before emitting the first `message.delta`. Preserve the current `CancelledError` path that calls `stop_run`.

- [ ] **Step 4: Run all Hermes LLM tests**

Run: `uv run pytest tests/test_hermes_llm.py -q`

Expected: all tests pass, including prior streaming and cancellation tests.

- [ ] **Step 5: Commit the LLM bridge change**

```powershell
git add -- src/hermes_llm.py tests/test_hermes_llm.py
git commit -m "feat: stream shared-session Hermes events"
```

### Task 4: Integrate realtime control, transcription output, and metrics in the worker

**Files:**
- Modify: `src/agent.py`
- Modify: `tests/test_agent.py`
- Modify: `tests/test_approval.py`

**Interfaces:**
- Consumes: protocol/state/status interfaces from Tasks 1–3 and existing `ApprovalBroker`.
- Produces: `resolve_linked_identity(room)`, `build_room_options()`, `handle_control_message(...)`, and a configured `AgentSession` with immediate text output and content-free metric publishing.

- [ ] **Step 1: Add failing worker integration tests**

```python
def test_room_options_stream_text_without_waiting_for_audio():
    options = build_room_options()
    assert options.text_output.sync_transcription is False

async def test_new_control_resets_context_after_exact_identity_check():
    result = await handle_control_message(
        packet("new", identity="phone", conversation_id="conv-2"),
        allowed_identity="phone",
        session=fake_session,
        assistant=fake_assistant,
        conversation_state=ConversationState("conv-1"),
        publisher=fake_publisher,
    )
    assert result is True
    assert fake_session.interrupt_calls == [True]
    assert fake_assistant.chat_context.items == []

async def test_control_from_other_participant_is_ignored():
    assert await handle_control_message(
        packet("stop", identity="intruder"), allowed_identity="phone", **fixtures
    ) is False
    assert fake_session.interrupt_calls == []
```

Retain the existing approval tests and add an assertion that a control packet can never resolve an approval.

The test module defines local `packet(...)` and `control_fixtures()` helpers that construct byte payloads, sender identities, a fake session, a fake assistant, a `ConversationState`, and a collecting publisher. These fakes assert calls at component boundaries and contain no production behavior.

- [ ] **Step 2: Run focused worker tests and verify RED**

Run: `uv run pytest tests/test_agent.py tests/test_approval.py -q`

Expected: failures identify missing text-output options and control handler.

- [ ] **Step 3: Wire the worker incrementally**

Use `room_io.TextOutputOptions(sync_transcription=False)`. Keep Deepgram Nova-3 Bengali streaming. Set VAD endpointing to dynamic mode with `min_delay=0.35` and `max_delay=1.2`. Configure interruption mode `adaptive`, `min_duration=0.3`, `min_words=0`, false-interruption resume, and a Bengali-safe boundary cooldown; retain `preemptive_generation.enabled=False`.

Resolve the linked Android identity once available. Initialize `ConversationState` from validated participant attribute `hermes.conversation_id`, falling back to `_safe_session_id(room.name)`. Process `hermes.control` only from that identity. `new` force-interrupts the current speech/run, rotates state, and calls `assistant.update_chat_ctx(llm.ChatContext.empty())`; `stop` force-interrupts; `status` publishes a snapshot. Approval packets continue through `ApprovalBroker` unchanged.

Add `user_state_changed`, `user_input_transcribed`, `agent_state_changed`, `metrics_collected`, and `overlapping_speech` listeners. Publish only timestamps/durations, `EOUMetrics`, `TTSMetrics.ttfb`, connection reuse flags, and interruption delays—never transcripts.

- [ ] **Step 4: Run the complete worker verification affected by the change**

Run: `uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests`

Expected: all tests pass and formatting/lint are clean.

- [ ] **Step 5: Commit worker integration**

```powershell
git add -- src/agent.py tests/test_agent.py tests/test_approval.py
git commit -m "feat: integrate realtime Hermes session controls"
```

### Task 5: Android input parsing and reliable protocol contracts

**Files:**
- Create: `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/HermesInput.kt`
- Create: `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/RealtimeProtocol.kt`
- Test: `app/src/test/java/io/livekit/android/example/voiceassistant/realtime/HermesInputTest.kt`
- Test: `app/src/test/java/io/livekit/android/example/voiceassistant/realtime/RealtimeProtocolTest.kt`

**Interfaces:**
- Produces: `HermesCommand`, `InputIntent`, `parseInput(String)`, `suggestInputs(String)`, `ControlPacket`, `StatusPacket`, `controlPacketJson`, and `parseStatusPacket`.
- Consumes: Gson already present in the Android project.

- [ ] **Step 1: Write failing Kotlin tests**

```kotlin
@Test fun muteIsLocalAndApproveDoesNotExist() {
    assertEquals(InputIntent.Local(HermesCommand.MUTE), parseInput("/mute"))
    assertEquals(InputIntent.Message("/approve"), parseInput("/approve"))
}

@Test fun atSignSuggestsSupportedHermesRoutes() {
    assertTrue(suggestInputs("@c").containsAll(listOf("@coder", "@computer-operator")))
}

@Test fun stopPacketContainsOnlyVersionOperationAndCommand() {
    val json = controlPacketJson(ControlPacket(1, "op-1", "stop", null))
    assertEquals(setOf("version", "op_id", "command"), jsonObject(json).keySet())
}
```

- [ ] **Step 2: Run Android unit tests and verify RED**

Run: `./gradlew.bat testDebugUnitTest --tests "*HermesInputTest" --tests "*RealtimeProtocolTest"`

Expected: compilation fails because the realtime package does not exist.

- [ ] **Step 3: Implement parsers and JSON contracts**

Use exact command and mention lists from the specification. Classify `/mute`, `/unmute`, `/voice`, `/call`, `/endcall`, and `/help` as local. Classify `/new`, `/stop`, and `/status` as control. Route `/agents`, `/tasks`, and `/memory` as normal Hermes messages. Treat `/approve` as plain text so it has no privileged path. Limit control/status JSON to versioned, explicit fields and reject payloads over 4096 bytes.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `./gradlew.bat testDebugUnitTest --tests "*HermesInputTest" --tests "*RealtimeProtocolTest"`

Expected: tests pass.

- [ ] **Step 5: Commit Android protocol code**

```powershell
git add -- app/src/main/java/io/livekit/android/example/voiceassistant/realtime/HermesInput.kt app/src/main/java/io/livekit/android/example/voiceassistant/realtime/RealtimeProtocol.kt app/src/test/java/io/livekit/android/example/voiceassistant/realtime/HermesInputTest.kt app/src/test/java/io/livekit/android/example/voiceassistant/realtime/RealtimeProtocolTest.kt
git commit -m "feat: add Hermes Android realtime protocol"
```

### Task 6: Android unified timeline reducer

**Files:**
- Create: `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/Timeline.kt`
- Test: `app/src/test/java/io/livekit/android/example/voiceassistant/realtime/TimelineTest.kt`

**Interfaces:**
- Consumes: normalized events from LiveKit Session Messages and `StatusPacket`.
- Produces: `TimelineMessage`, `MessageRole`, `MessageSource`, `DeliveryState`, `TimelineUpdate`, and `reduceTimeline(current, update)`.

- [ ] **Step 1: Write failing reducer tests**

```kotlin
@Test fun optimisticTextReconcilesWithoutDuplicate() {
    val optimistic = reduceTimeline(emptyList(), TimelineUpdate.LocalText("local-1", "hello", 10))
    val sent = reduceTimeline(optimistic, TimelineUpdate.TextSent("local-1", "stream-7", 12))
    assertEquals(1, sent.size)
    assertEquals(DeliveryState.SENT, sent.single().delivery)
    assertEquals("stream-7", sent.single().transportId)
}

@Test fun finalVoiceTranscriptReplacesInterimSegment() {
    val interim = reduceTimeline(emptyList(), TimelineUpdate.Transcript("seg-1", "হারমিস", false, true, 20))
    val final = reduceTimeline(interim, TimelineUpdate.Transcript("seg-1", "হারমিস শুনো", true, true, 25))
    assertEquals(1, final.size)
    assertEquals("হারমিস শুনো", final.single().text)
    assertTrue(final.single().isFinal)
}

@Test fun voiceAndTextShareTimestampOrderedTimeline() {
    val updates = listOf(
        TimelineUpdate.Transcript("v1", "voice", true, true, 30),
        TimelineUpdate.LocalText("t1", "text", 40),
        TimelineUpdate.Transcript("a1", "reply", true, false, 50),
    )
    val result = updates.fold(emptyList<TimelineMessage>(), ::reduceTimeline)
    assertEquals(listOf(MessageSource.VOICE, MessageSource.TEXT, MessageSource.HERMES), result.map { it.source })
}
```

- [ ] **Step 2: Run reducer tests and verify RED**

Run: `./gradlew.bat testDebugUnitTest --tests "*TimelineTest"`

Expected: compilation fails because timeline models are absent.

- [ ] **Step 3: Implement an immutable reducer**

Use `segmentId` as the key for interim/final transcripts and `localId`/`transportId` for typed messages. Status messages are keyed by operation/event ID. Sort only when timestamps differ; update in place for matching keys. Persistability is true only for final user/Hermes text and excludes pending, failed, interim, approval, and telemetry items.

- [ ] **Step 4: Run reducer tests and verify GREEN**

Run: `./gradlew.bat testDebugUnitTest --tests "*TimelineTest"`

Expected: tests pass.

- [ ] **Step 5: Commit timeline reducer**

```powershell
git add -- app/src/main/java/io/livekit/android/example/voiceassistant/realtime/Timeline.kt app/src/test/java/io/livekit/android/example/voiceassistant/realtime/TimelineTest.kt
git commit -m "feat: add unified Hermes conversation timeline"
```

### Task 7: Android private history, identity, and latency tracking

**Files:**
- Create: `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/HistoryRepository.kt`
- Create: `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/LatencyTracker.kt`
- Create: `app/src/main/java/io/livekit/android/example/voiceassistant/realtime/SessionIdentity.kt`
- Test: `app/src/test/java/io/livekit/android/example/voiceassistant/realtime/HistoryRepositoryTest.kt`
- Test: `app/src/test/java/io/livekit/android/example/voiceassistant/realtime/LatencyTrackerTest.kt`
- Test: `app/src/test/java/io/livekit/android/example/voiceassistant/realtime/SessionIdentityTest.kt`

**Interfaces:**
- Consumes: `TimelineMessage` from Task 6.
- Produces: `HistoryRepository`, `HistoryStorage`, `redactForHistory`, `LatencyTracker`, and `SessionIdentityStore`.

- [ ] **Step 1: Write failing storage and timing tests**

```kotlin
@Test fun historyRedactsCredentialsAndCapsFinalMessages() {
    val messages = (1..210).map { finalText("m$it", "Bearer secret-$it") }
    repository.save("conv-1", messages)
    val restored = repository.load("conv-1")
    assertEquals(200, restored.size)
    assertTrue(restored.all { "secret-" !in it.text })
}

@Test fun interimAndApprovalMessagesAreNotPersisted() {
    repository.save("conv-1", listOf(interimVoice(), approvalStatus(), finalText("f", "safe")))
    assertEquals(listOf("f"), repository.load("conv-1").map { it.id })
}

@Test fun textFirstRenderLatencyUsesMonotonicMarks() {
    val tracker = LatencyTracker("op-1")
    tracker.mark("send_pressed", 1_000_000_000)
    tracker.mark("first_ui_delta", 1_240_000_000)
    assertEquals(240, tracker.durationMs("send_pressed", "first_ui_delta"))
}

@Test fun conversationRotationPreservesInstallationIdentity() {
    val before = identities.current()
    val after = identities.rotateConversation()
    assertEquals(before.installationId, after.installationId)
    assertNotEquals(before.conversationId, after.conversationId)
}
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `./gradlew.bat testDebugUnitTest --tests "*HistoryRepositoryTest" --tests "*LatencyTrackerTest" --tests "*SessionIdentityTest"`

Expected: compilation fails because persistence/timing/identity classes are absent.

- [ ] **Step 3: Implement private storage policies**

Define `HistoryStorage` as `read(key): String?` and `write(key, value)`. The production adapter uses app-private `SharedPreferences`; tests use an in-memory map. Store at most 200 finalized messages per conversation. Redact bearer tokens, API-key/secret assignments, JWT-shaped values, and long credential-like base64/hex strings. Do not persist interim messages, approval/status packets, telemetry, tool arguments, or delivery errors. UUID-derived installation and conversation IDs are normalized to the protocol identifier grammar.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `./gradlew.bat testDebugUnitTest --tests "*HistoryRepositoryTest" --tests "*LatencyTrackerTest" --tests "*SessionIdentityTest"`

Expected: tests pass.

- [ ] **Step 5: Commit storage and telemetry code**

```powershell
git add -- app/src/main/java/io/livekit/android/example/voiceassistant/realtime/HistoryRepository.kt app/src/main/java/io/livekit/android/example/voiceassistant/realtime/LatencyTracker.kt app/src/main/java/io/livekit/android/example/voiceassistant/realtime/SessionIdentity.kt app/src/test/java/io/livekit/android/example/voiceassistant/realtime/HistoryRepositoryTest.kt app/src/test/java/io/livekit/android/example/voiceassistant/realtime/LatencyTrackerTest.kt app/src/test/java/io/livekit/android/example/voiceassistant/realtime/SessionIdentityTest.kt
git commit -m "feat: persist safe Hermes conversation state"
```

### Task 8: Auto-connect lifecycle and shared LiveKit session

**Files:**
- Modify: `app/src/main/java/io/livekit/android/example/voiceassistant/MainActivity.kt`
- Modify: `app/src/main/java/io/livekit/android/example/voiceassistant/viewmodel/VoiceAssistantViewModel.kt`
- Modify: `app/src/main/java/io/livekit/android/example/voiceassistant/screen/VoiceAssistantScreen.kt`
- Test: `app/src/androidTest/java/io/livekit/android/example/voiceassistant/HermesLifecycleTest.kt`

**Interfaces:**
- Consumes: `SessionIdentityStore`, LiveKit `TokenRequestOptions`, `rememberSession`, `rememberLocalMedia`, and `rememberAgent`.
- Produces: `HermesSessionController`, direct HERMES launch, warm text session, mic-off default, local call/end-call controls, and reconnect UI.

- [ ] **Step 1: Add a failing Compose lifecycle test**

```kotlin
@Test fun launchShowsChatAndCallWithMicOff() {
    composeRule.setContent { HermesScreen(fakeSessionController) }
    composeRule.onNodeWithTag("conversation_timeline").assertExists()
    composeRule.onNodeWithText("CALL HERMES").assertExists()
    composeRule.onNodeWithText("মাইক্রোফোন বন্ধ").assertExists()
    assertEquals(1, fakeSessionController.startCalls)
    assertEquals(0, fakeSessionController.enableMicCalls)
}
```

- [ ] **Step 2: Run the instrumented test and verify RED**

Run: `./gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=io.livekit.android.example.voiceassistant.HermesLifecycleTest`

Expected: compilation fails because the injectable `HermesScreen` lifecycle surface does not exist.

- [ ] **Step 3: Implement auto-connect without requesting microphone permission**

Define `HermesSessionController` as the small UI-facing interface with `start()`, `setMicrophoneEnabled(Boolean)`, `setAgentVolume(Double)`, `isConnected`, and `isReconnecting`; the production adapter delegates to the existing LiveKit Session/LocalMedia/agent track, while the Compose test uses `FakeHermesSessionController` declared in the test file. Start `VoiceAssistantRoute` directly from `MainActivity`. Construct `TokenRequestOptions` with `agentName="hermes-voice"`, participant identity `hermes-android-<installationId>`, and participant attributes `hermes.conversation_id=<conversationId>`. Start the session in `LaunchedEffect(Unit)` independently of microphone permission. Set `requestedAudio=false`. Request permission only from Call/Unmute. On Call, enable the existing local microphone track and set the agent remote audio track volume to `1.0`; on End Call, disable the microphone and set remote audio volume to `0.0` while keeping the room connected. Display `Reconnecting...` from `session.isReconnecting` without clearing timeline state.

- [ ] **Step 4: Run lifecycle test and Android unit tests**

Run: `./gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=io.livekit.android.example.voiceassistant.HermesLifecycleTest && ./gradlew.bat testDebugUnitTest`

Expected: lifecycle and unit tests pass.

- [ ] **Step 5: Commit lifecycle changes**

```powershell
git add -- app/src/main/java/io/livekit/android/example/voiceassistant/MainActivity.kt app/src/main/java/io/livekit/android/example/voiceassistant/viewmodel/VoiceAssistantViewModel.kt app/src/main/java/io/livekit/android/example/voiceassistant/screen/VoiceAssistantScreen.kt app/src/androidTest/java/io/livekit/android/example/voiceassistant/HermesLifecycleTest.kt
git commit -m "feat: auto-connect Hermes text session"
```

### Task 9: Unified chat UI, autocomplete, statuses, and local commands

**Files:**
- Modify: `app/src/main/java/io/livekit/android/example/voiceassistant/screen/VoiceAssistantScreen.kt`
- Modify: `app/src/main/java/io/livekit/android/example/voiceassistant/ui/ChatBar.kt`
- Modify: `app/src/main/java/io/livekit/android/example/voiceassistant/ui/ChatLog.kt`
- Test: `app/src/androidTest/java/io/livekit/android/example/voiceassistant/HermesChatUiTest.kt`

**Interfaces:**
- Consumes: Tasks 5–8, `rememberSessionMessages()`, LiveKit `Room.registerTextStreamHandler`, and reliable data publishing.
- Produces: optimistic text, progressive Hermes bubble, interim/final voice replacement, suggestions, safe statuses, local commands, and latency display/logging.

- [ ] **Step 1: Write failing Compose interaction tests**

```kotlin
@Test fun sendAddsBubbleBeforeTransportCompletes() {
    composeRule.onNodeWithTag("message_input").performTextInput("hello")
    composeRule.onNodeWithTag("send_button").performClick()
    composeRule.onNodeWithText("hello").assertExists()
    assertFalse(fakeTransport.completion.isCompleted)
}

@Test fun slashAndMentionSuggestionsAppearImmediately() {
    composeRule.onNodeWithTag("message_input").performTextInput("@c")
    composeRule.onNodeWithText("@coder").assertExists()
    composeRule.onNodeWithText("@computer-operator").assertExists()
    composeRule.onNodeWithTag("message_input").performTextClearance()
    composeRule.onNodeWithTag("message_input").performTextInput("/m")
    composeRule.onNodeWithText("/mute").assertExists()
}

@Test fun muteAndEndCallDoNotSendChat() {
    submit("/mute")
    submit("/endcall")
    assertEquals(0, fakeTransport.chatSends)
    assertEquals(listOf(false, false), fakeVoiceController.micStates)
}
```

- [ ] **Step 2: Run chat UI tests and verify RED**

Run: `./gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=io.livekit.android.example.voiceassistant.HermesChatUiTest`

Expected: assertions fail because the current screen has no composer, unified timeline, or suggestions.

The UI test declares `FakeChatTransport` with a suspended send completion, `FakeVoiceController` that records requested microphone states, and a `submit(text)` helper that fills the tagged input and taps the tagged Send button.

- [ ] **Step 3: Implement the responsive conversation screen**

Use `rememberSessionMessages()` for `lk.chat` and LiveKit transcription messages. Convert each message to a `TimelineUpdate`; use `lk.segment_id` and `lk.transcription_final` attributes for voice deduplication. At Send press, add an optimistic text update and mark latency before launching `sessionMessages.send(message, StreamTextOptions(topic="lk.chat", attributes=...))`. Clear input immediately. Mark send completion or failure and reconcile with the returned stream ID.

Register `hermes.status` and consume each text stream incrementally. Parse only complete JSON status messages and insert safe status chips. For `/new`, publish `hermes.control`, rotate identity state, update participant attributes, and clear the timeline/history. For `/stop` and `/status`, publish a reliable data/control packet. Execute remaining local commands without chat or LLM roundtrip.

Build a lightweight Compose layout: connection/status header, scrolling unified timeline, working indicator, autocomplete row, three-line text field, Send button, and compact Call/Mute/End Call controls. Assign stable test tags. Never display reasoning, tool arguments, or raw status JSON.

- [ ] **Step 4: Run chat UI tests and unit tests**

Run: `./gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=io.livekit.android.example.voiceassistant.HermesChatUiTest && ./gradlew.bat testDebugUnitTest`

Expected: UI and unit tests pass.

- [ ] **Step 5: Commit chat UI integration**

```powershell
git add -- app/src/main/java/io/livekit/android/example/voiceassistant/screen/VoiceAssistantScreen.kt app/src/main/java/io/livekit/android/example/voiceassistant/ui/ChatBar.kt app/src/main/java/io/livekit/android/example/voiceassistant/ui/ChatLog.kt app/src/androidTest/java/io/livekit/android/example/voiceassistant/HermesChatUiTest.kt
git commit -m "feat: add realtime Hermes text conversation"
```

### Task 10: Destructive dialog regression and safety copy

**Files:**
- Modify: `app/src/main/java/io/livekit/android/example/voiceassistant/ApprovalProtocol.kt`
- Modify: `app/src/main/java/io/livekit/android/example/voiceassistant/screen/VoiceAssistantScreen.kt`
- Modify: `app/src/test/java/io/livekit/android/example/voiceassistant/ApprovalProtocolTest.kt`
- Test: `app/src/androidTest/java/io/livekit/android/example/voiceassistant/HermesApprovalUiTest.kt`

**Interfaces:**
- Consumes: existing `hermes.approval.request` and `hermes.approval.response` topics.
- Produces: optional `agent` display field and unchanged `approvalResponseJson(runId, choice)` restricted to `once`/`deny`.

- [ ] **Step 1: Add failing protocol and UI assertions**

```kotlin
@Test fun approveAliasesRemainRejected() {
    assertNull(approvalResponseJson("run-1", "approve"))
    assertNull(approvalResponseJson("run-1", "yes"))
    assertNull(approvalResponseJson("run-1", "হ্যাঁ"))
}

@Test fun destructiveDialogHasOnlyPhysicalConfirmAndCancel() {
    showApproval(agent = "Computer Operator", action = "Delete", target = "fixture")
    composeRule.onNodeWithText("⚠ DESTRUCTIVE ACTION").assertExists()
    composeRule.onNodeWithText("Agent: Computer Operator").assertExists()
    composeRule.onNodeWithText("CANCEL").assertExists()
    composeRule.onNodeWithText("CONFIRM").assertExists()
    composeRule.onNodeWithText("APPROVE").assertDoesNotExist()
}
```

- [ ] **Step 2: Run approval tests and verify RED**

Run: `./gradlew.bat testDebugUnitTest --tests "*ApprovalProtocolTest" && ./gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=io.livekit.android.example.voiceassistant.HermesApprovalUiTest`

Expected: the new warning title/agent assertions fail.

- [ ] **Step 3: Update display data without changing authorization semantics**

Accept an optional nonblank `agent` field for display, defaulting to `Hermes Main`. Render the exact warning title and labeled fields. Keep dismiss/CANCEL=`deny` and CONFIRM=`once`. Do not add handlers for chat, slash commands, mentions, voice, or generic affirmatives.

- [ ] **Step 4: Run approval regression tests**

Run: `./gradlew.bat testDebugUnitTest --tests "*ApprovalProtocolTest" && ./gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=io.livekit.android.example.voiceassistant.HermesApprovalUiTest`

Expected: protocol and UI tests pass.

- [ ] **Step 5: Commit the approval UI refinement**

```powershell
git add -- app/src/main/java/io/livekit/android/example/voiceassistant/ApprovalProtocol.kt app/src/main/java/io/livekit/android/example/voiceassistant/screen/VoiceAssistantScreen.kt app/src/test/java/io/livekit/android/example/voiceassistant/ApprovalProtocolTest.kt app/src/androidTest/java/io/livekit/android/example/voiceassistant/HermesApprovalUiTest.kt
git commit -m "feat: clarify destructive Android confirmation"
```

### Task 11: Focused build, install, and end-to-end verification

**Files:**
- Modify if required by observed failures: `scripts/smoke-livekit-room.py`
- Create: `scripts/smoke-livekit-text.py`
- Create: `scripts/report-latency.py`
- Test: `tests/test_realtime_protocol.py`, `tests/test_realtime_status.py`, Android unit/instrumented tests from prior tasks.

**Interfaces:**
- Consumes: the installed worker, LiveKit project, authorized Android device, and the unchanged local Hermes endpoint.
- Produces: updated installed APK, focused PASS/FAIL evidence, and actual latency measurements.

- [ ] **Step 1: Write a failing headless text smoke test before any smoke-only support change**

The script must join the existing LiveKit project, send one `lk.chat` message, collect incremental `lk.transcription` chunks, assert at least two incremental updates or one provider-sized first chunk plus a final stream, capture first-delta timing, and compare the worker's `session.ready.conversation_fingerprint` with the script's local SHA-256 fingerprint. It must not print message content, room credentials, tokens, conversation identifiers, or transcript text.

- [ ] **Step 2: Run the text smoke and verify the expected initial failure**

Run: `uv run python scripts/smoke-livekit-text.py`

Expected before integration completion: failure naming the first missing protocol/status/session behavior, not an authentication or syntax error.

- [ ] **Step 3: Run fresh worker verification and restart only the changed worker**

```powershell
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-worker.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-worker.ps1
```

Expected: zero test/lint failures; scheduled worker returns to `Running`; exactly one background worker owns the lock.

- [ ] **Step 4: Build the affected Android application**

Run: `./gradlew.bat testDebugUnitTest lintDebug assembleDebug`

Expected: `BUILD SUCCESSFUL`, zero unit failures, and APK at `app/build/outputs/apk/debug/app-debug.apk`.

- [ ] **Step 5: Scan the final APK and configuration boundary**

Run the existing `scripts/scan-apk-secrets.py` against the new APK. Confirm `HERMES_API_URL` remains loopback-only through the worker tests and current process listener inspection. Expected: zero APK secret findings and no non-loopback Hermes listener.

- [ ] **Step 6: Install without clearing Android data and launch**

```powershell
& 'C:\Android\Sdk\platform-tools\adb.exe' install -r 'C:\Users\MuniR\Desktop\New folder\Hermes-Voice-Android\app\build\outputs\apk\debug\app-debug.apk'
& 'C:\Android\Sdk\platform-tools\adb.exe' shell am force-stop com.hermes.voice
& 'C:\Android\Sdk\platform-tools\adb.exe' shell monkey -p com.hermes.voice -c android.intent.category.LAUNCHER 1
```

Expected: install succeeds, app launches into the timeline, connection becomes ready, microphone remains off, and recent safe history remains.

- [ ] **Step 7: Execute focused device checks**

Use ADB UI automation and worker telemetry to verify:

- normal text produces one optimistic bubble and a progressively rendered Hermes response;
- text sends while Call is active;
- `@coder` produces Hermes Main delegation status;
- `@computer-operator` performs one harmless action such as opening Calculator and calculating `7 × 8`, using on-screen confirmation if Hermes requests it;
- `/status` produces a local/status response;
- `/mute` and `/endcall` change device state immediately without a Hermes run;
- voice transcript appears once in the same timeline;
- voice interruption still cancels/yields after the changed turn settings; and
- a no-op targeted approval probe displays the destructive dialog and is cancelled without executing an action.

Human speech/hearing or an explicit harmless confirmation tap is requested only for checks that cannot be injected or observed safely through ADB.

- [ ] **Step 8: Measure and report actual latency**

Correlate anonymous operation IDs and monotonic spans to report median/observed values for text Send→packet, worker receive→Hermes request, Hermes request→first delta, Send→first UI delta, speech detected→final STT, final STT→Hermes request, Hermes request→first delta, TTS TTFB, and speech detected→first speaking state. Identify the largest measured stage. Do not report transcript contents or claim zero latency.

- [ ] **Step 9: Submit constructive LiveKit documentation feedback if a verified gap remains**

Use `lk docs submit-feedback --help`, then submit only a concrete discrepancy encountered during implementation, such as missing Android Session Messages import/detail or a CLI/docs version mismatch. Skip submission if no documentation gap affected the work.

- [ ] **Step 10: Commit only new verification scripts**

```powershell
git add -- scripts/smoke-livekit-text.py scripts/report-latency.py
git commit -m "test: verify Hermes realtime text path"
```

## Completion Gate

Before claiming completion, run fresh full changed-scope verification, inspect both repository diffs, confirm the installed APK hash/path/package/version, and map every final report field to a command, test, device observation, or explicit human confirmation from the current build.
