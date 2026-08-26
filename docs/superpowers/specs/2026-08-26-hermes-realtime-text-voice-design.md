# Hermes Realtime Text + Voice Design

**Date:** 2026-08-26

**Status:** Approved in chat; awaiting written-spec review

**Repositories:** `Hermes-LiveKit-Voice`, `Hermes-Voice-Android`

## Objective

Upgrade the existing Android voice client into a single realtime Hermes application that supports persistent text chat and voice in one conversation. Preserve Hermes Main as the sole commander, the current LiveKit Cloud project, the local Windows worker, OmniRoute, CUA, Kanban, memory, specialist profiles, Gateway, silent startup, and the existing destructive-action approval boundary.

The implementation must minimize practical latency without exposing the localhost Hermes API, executing unstable partial speech, bypassing Hermes Main, or weakening one-shot Android confirmation.

## Constraints

- Hermes remains reachable only at a loopback URL on Windows.
- Android contains no Hermes or LiveKit API secret. It continues to use the configured LiveKit Development Token Server.
- The Windows worker remains the only bridge from LiveKit Cloud to Hermes Main.
- Voice and text reuse one LiveKit room, one LiveKit `AgentSession`, one Hermes conversation identifier, and one conversation timeline.
- Important commands, approvals, status control, and chat use reliable LiveKit delivery.
- Partial STT is display-only. Only a committed/final user turn can start a Hermes run.
- Destructive operations require a physical tap on the Android confirmation button. Spoken or typed consent is insufficient.
- Existing user changes in both dirty repositories are preserved.
- Only functionality affected by this upgrade is retested.

## Chosen Architecture

Use LiveKit's native Session Messages and text-stream path rather than creating a second chat backend.

```text
Android HERMES
  ├─ microphone / WebRTC audio
  ├─ lk.chat reliable text streams
  ├─ lk.transcription streams (interim + final)
  └─ small reliable control/status topics
                │
                ▼
LiveKit Cloud — existing project and warm room
                │
                ▼
Existing local Windows AgentSession
  ├─ streaming Bengali STT
  ├─ final-turn gate
  ├─ Hermes Main LLM adapter
  ├─ streaming Bengali TTS
  └─ approval broker
                │
                ▼
Hermes API on 127.0.0.1
  └─ /v1/runs + SSE events + approve/steer/stop
```

LiveKit already supports the necessary transport:

- Android `rememberSessionMessages()` combines `lk.chat` with user and agent transcriptions.
- `lk.chat` is the standard linked-participant text input for `AgentSession`.
- `lk.transcription` publishes interim and final STT streams and streamed agent text.
- Hermes `/v1/runs/{run_id}/events` already emits `message.delta`, tool lifecycle, subagent lifecycle, approval, completion, failure, steer, and cancellation events.

No new LLM, public API, polling service, or parallel conversation backend is introduced.

## Android Lifecycle and Session Identity

The app opens directly into the HERMES conversation screen and starts a LiveKit session immediately with the microphone disabled. Text chat becomes available as soon as the room and agent are connected. **Call Hermes** and `/call` request microphone permission if needed and enable the microphone in the existing room. **End Call** and `/endcall` disable voice but leave the warm text session connected. Closing the app ends the LiveKit session normally.

Android generates and privately stores:

- a stable installation identifier used as the LiveKit participant identity; and
- an active conversation identifier used as a participant attribute and Hermes session identifier.

The worker reads the validated conversation identifier from the linked participant. It falls back to the existing room-derived identifier if the attribute is absent or invalid. `/new` creates a new conversation identifier, clears the visible timeline, reliably tells the worker to cancel the active run and reset its Hermes/AgentSession chat context, and does not reconnect the room.

## Unified Conversation Timeline

The timeline normalizes four LiveKit message classes:

- typed user messages;
- user voice transcriptions;
- streamed Hermes text; and
- safe operational status events.

Typed messages are added optimistically at Send press, then transmitted with `rememberSessionMessages().send()` on `lk.chat`. The local optimistic item is reconciled with the returned LiveKit stream ID so it is not duplicated.

Voice transcription streams are keyed by `lk.segment_id`. Interim text replaces the same temporary item. A final stream with `lk.transcription_final=true` replaces the interim item and becomes persistable. Interim speech never enters an execution path in the Android app or worker.

Agent output uses `TextOutputOptions(sync_transcription=False)` so Hermes deltas reach the timeline as generation occurs rather than waiting for audio playback alignment. The same deltas continue into the existing streaming TTS pipeline. Interrupted agent output is marked interrupted in the active timeline; it is not presented as a completed response.

Messages are visually marked as voice, text, Hermes, or status without splitting the conversation.

## Text and Voice Flow

### Typed text

1. User presses Send.
2. Android adds the local bubble and records `send_pressed` immediately.
3. Android sends a reliable `lk.chat` text stream with a message identifier and non-sensitive timing metadata.
4. The existing worker text callback receives the completed stream and records `worker_received`.
5. Local slash commands are never sent. Other input is handed to the same `AgentSession` used by voice.
6. The Hermes LLM adapter opens `/v1/runs` using the existing persistent `aiohttp.ClientSession` and the shared conversation identifier.
7. SSE `message.delta` events are emitted into the LiveKit LLM stream immediately.
8. Android progressively updates one Hermes bubble.
9. TTS may speak the same response only when voice output is enabled.

### Voice

1. LiveKit WebRTC keeps the microphone track in the existing room once voice is enabled.
2. Streaming Deepgram Nova-3 Bengali STT emits interim transcriptions for display.
3. `AgentSession` commits a stable final turn after VAD endpointing.
4. Only that committed turn starts Hermes.
5. Hermes deltas stream to Android and streaming Cartesia TTS concurrently.
6. Barge-in interrupts audio promptly and cancels the superseded Hermes run through the existing stop mechanism.

The Bengali language is not supported by LiveKit's semantic audio end-of-turn detector, so the design retains VAD-based turn completion and tunes dynamic endpointing conservatively. Adaptive acoustic interruption may be enabled because it is language-agnostic; it must fall back to VAD behavior if unavailable. Preemptive Hermes generation remains disabled because this agent can execute tools and must not act on a turn before it is committed.

## Mentions and Commands

Supported mention suggestions:

`@main`, `@architect`, `@researcher`, `@coder`, `@browser`, `@computer-operator`, `@qa`, `@reviewer`, `@security`, `@ops`

Android provides instant local autocomplete. The raw mention is sent to the worker. The worker validates it and turns it into an explicit instruction for Hermes Main to route or delegate through the existing Hermes mechanisms. It never calls a specialist directly. The worker publishes a safe `delegation.requested` status immediately, followed by actual Hermes `subagent.start` and `subagent.complete` events when available.

Supported slash suggestions:

`/new`, `/status`, `/agents`, `/tasks`, `/stop`, `/voice`, `/call`, `/endcall`, `/mute`, `/unmute`, `/memory`, `/help`

Local commands:

- `/mute`, `/unmute`, `/voice`, `/call`, `/endcall`, and `/help` execute entirely on Android.
- `/status` immediately shows connection, voice, and agent state. It may also request a fresh worker status packet.
- `/new` and `/stop` use a reliable `hermes.control` packet.
- `/agents`, `/tasks`, and `/memory` remain Hermes Main requests so existing authorization and orchestration apply.
- No `/approve` command exists.

## Status and Control Protocol

The current approval topics remain unchanged. Two narrow additions are allowed:

- `hermes.control`: reliable JSON packets for `new`, `stop`, and status request operations.
- `hermes.status`: reliable text/data events containing only safe high-level state.

Status examples include `connected`, `thinking`, `tool.started`, `tool.completed`, `delegation.requested`, `subagent.start`, `subagent.complete`, `waiting_for_approval`, `completed`, `failed`, and `cancelled`. Tool previews, reasoning text, command bodies, credentials, and chain-of-thought are not sent as status.

Each control packet includes a protocol version, operation ID, and target conversation identifier. The worker accepts it only from the linked Android participant and rejects malformed, unsupported, stale, or cross-participant packets.

## Destructive Approval

The existing targeted approval broker remains the enforcement point. The Android request UI is refined to show:

```text
⚠ DESTRUCTIVE ACTION
Agent: ...
Action: ...
Target: ...
Reason: ...
[CANCEL] [CONFIRM]
```

Protocol responses remain only `deny` and `once`. `CONFIRM` maps to one-shot approval for the displayed run only. Dismissal and `CANCEL` map to denial. No voice input, text message, mention, slash command, or generic affirmative can resolve an approval. The worker continues to bind the response to the exact participant identity and run ID.

## Persistence and Privacy

Recent finalized conversation items are stored in app-private preferences as a capped JSON history. Android backup remains disabled. Interim transcriptions, approval payloads, raw status payloads, latency identifiers, tool arguments, and messages matching strict credential/token patterns are not persisted. Credential-like substrings are replaced with a local redaction marker before storage. No LiveKit or Hermes secret is added to source, resources, preferences, logs, or the APK.

History restoration is a UI convenience. Hermes continuity is governed by the stable conversation identifier, not by replaying every restored message to the model. `/new` rotates the identifier and starts a fresh persisted timeline.

## Latency and Streaming

The design preserves warm connections:

- one LiveKit room for text and voice;
- one worker process and AgentSession;
- one reusable Hermes `aiohttp.ClientSession`;
- streaming STT and TTS connections managed by LiveKit; and
- one Hermes SSE stream per active run, with no polling.

Worker voice timing points:

- speech detected;
- final STT ready;
- Hermes request sent;
- first Hermes delta;
- first TTS audio available;
- agent enters speaking state; and
- interruption detection/cancellation.

Android text timing points:

- Send pressed;
- LiveKit send completed;
- first assistant text rendered; and
- final response rendered.

Only durations, event names, anonymous operation IDs, connection reuse flags, and model-stage metrics are logged or displayed. Audio and transcript contents are not emitted as telemetry.

## Error Handling and Reconnection

- Session state drives `Connecting`, `Connected`, `Reconnecting`, and `Disconnected` UI.
- LiveKit performs WebRTC reconnection; the app keeps the same local conversation identifier and does not clear history.
- Optimistic text that fails to send is marked retryable instead of silently removed.
- Malformed status/control/approval packets are ignored safely and logged without payload contents.
- Hermes failures produce a concise visible failure state while retaining the conversation.
- A stopped or interrupted run closes its stream and cannot approve or continue a superseded destructive action.
- Worker shutdown denies all pending approvals and closes the persistent HTTP session as it does today.

## Test-Driven Implementation

Production behavior is implemented only after a corresponding test has been observed failing for the expected reason.

Worker unit tests cover:

- supported mention parsing and Hermes Main routing;
- unsupported mention behavior;
- control packet validation and exact participant binding;
- `/new` session rotation and chat-context reset;
- `/stop` cancellation;
- safe status projection from Hermes SSE events;
- telemetry timing without content; and
- existing approval enforcement regressions.

Android unit/UI tests cover:

- command classification and local execution intent;
- mention and slash autocomplete;
- optimistic message reconciliation;
- interim-to-final transcript replacement without duplication;
- unified voice/text ordering;
- persistence redaction and cap;
- conversation rotation;
- latency span calculation;
- destructive dialog labels and response mapping; and
- no text/voice approval bypass.

## Focused Verification

After implementation, run only relevant checks:

1. Worker unit tests and lint for changed modules.
2. Android unit tests, lint, and debug APK build.
3. Install with `adb install -r` to preserve app data.
4. Confirm auto-connected text UI with microphone off.
5. Send normal text and observe one progressively rendered Hermes reply.
6. Enable voice in the same room and confirm voice transcript joins the same timeline.
7. Send text while voice is enabled.
8. Verify `@coder` routes through Hermes Main and yields delegation status.
9. Verify `@computer-operator` performs one harmless action through Hermes Main.
10. Verify one non-media slash command plus immediate `/mute` and `/endcall` behavior.
11. Verify interruption after the voice tuning change.
12. Verify the destructive dialog still requires a physical button and deny a harmless no-op probe.
13. Re-run APK secret scanning and confirm Hermes remains loopback-only.
14. Report measured stage timings and the largest observed bottleneck without claiming zero latency.

## Non-Goals

- Replacing Hermes Main or OmniRoute.
- Deploying the worker to LiveKit Cloud.
- Exposing Hermes through a public tunnel, reverse proxy, or Android credential.
- Recording or uploading private audio/transcripts for telemetry.
- Adding `/approve` or accepting spoken/text affirmation as destructive authorization.
- Re-running the previously completed broad acceptance suite.
