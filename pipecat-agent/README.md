# Pipecat port of the LiveKit agent starter

A [Pipecat](https://github.com/pipecat-ai/pipecat) agent that runs the same voice
pipeline as [`src/agent.py`](../src/agent.py), using **LiveKit transport** for media
and [**LiveKit Inference**](https://livekit.com/products/inference) for STT, LLM,
and TTS ([pricing](https://livekit.com/pricing/inference)). The only credentials it
needs are your LiveKit Cloud API keys — no per-provider API keys.

```
pipecat-agent/
├── livekit_inference.py   # Pipecat services for LiveKit Inference (STT, LLM, TTS)
├── agent.py               # the agent: same models and prompt as src/agent.py
└── tests/                 # protocol tests + parity tests against src/agent.py
```

This is a self-contained uv project with its own lockfile, so Pipecat's
dependencies stay out of the starter's own environment.

## Setup

Dependencies:

```bash
cd pipecat-agent && uv sync
```

Credentials are read from the starter's `.env.local` at the repo root (a
`.env.local` in this directory wins if you'd rather keep them separate):

```
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
```

## Run the agent

```bash
uv run agent.py --room my-room
```

The room name can also come from `LIVEKIT_ROOM_NAME`. On startup the runner logs a
participant token for that room — paste it into any
[LiveKit frontend](https://docs.livekit.io/frontends/) to talk to the agent. Note
that the frontend has to join *that* room: there's no agent dispatch here, so a
frontend that generates its own random room name needs to be pinned to this one.

Like `src/agent.py`, the agent waits for the user to speak first. `agent.py` has a
commented block that makes it introduce itself instead.

## Tests

```bash
uv run pytest
```

The suite is offline: it drives both services through a real Pipecat pipeline
against a scripted fake LiveKit Inference server, covering the wire protocol (STT's nested
`settings` vs TTS's flat `session.create`, base64 audio framing, `session.finalize`,
one flush per turn, the two different error shapes) and the frames the pipeline
sees. `tests/test_agent.py` pins the prompt, models, and voice to `src/agent.py`,
so if the starter changes, these fail and name what drifted.

Run the starter's own tests from the repo root, not here — the root `pytest` config
only collects `tests/`.

## How this maps to the LiveKit starter

Same models, same prompt (asserted by a test):

| | `src/agent.py` | This port |
|---|---|---|
| LLM | `inference.LLM("google/gemma-4-31b-it")` | `LiveKitInferenceLLMService` |
| STT | `inference.STT("assemblyai/universal-3-5-pro", language="en")` | `LiveKitInferenceSTTService` |
| TTS | `inference.TTS("fishaudio/s2.1-pro", voice=…)` | `LiveKitInferenceTTSService` |
| Turn detection | `inference.TurnDetector()` | `LocalSmartTurnAnalyzerV3` — also semantic + acoustic, but a different model, running locally rather than as a hosted LiveKit model |
| VAD | supplied automatically by `AgentSession` | `SileroVADAnalyzer`, passed explicitly |

### What doesn't carry over

These are LiveKit Agents features with no Pipecat equivalent, so the port simply
doesn't have them:

- **`preemptive_generation`** — the starter lets the LLM start generating before
  the user's turn is confirmed complete.
- **`interruption={"mode": "adaptive"}`** — the starter's turn detector tells a
  real interruption from a backchannel ("mhm", "right") and keeps talking through
  the latter. Here any detected turn interrupts.
- **`expressive=True`** — injects the TTS provider's markup guide into the LLM
  prompt so the model emits inline delivery tags. Nothing here does that, so
  Fish Audio's markup support goes unused.
- **ai-coustics noise cancellation** — the starter gets
  `ai_coustics.audio_enhancement(...)` through LiveKit Cloud. Pipecat has an
  `AICFilter`, but it needs your own ai-coustics license key; the LiveKit-provided
  enhancement isn't reachable from outside LiveKit Agents.
- **Agent dispatch** — the starter registers with `AgentServer` and is dispatched
  into rooms by LiveKit Cloud. This joins one room you name and runs until the
  participant leaves; there's no worker registration or job queue. It does still
  join *as an agent* (see below), so frontends recognize it once it's in the room.
- **LiveKit Cloud session insights** — Pipecat metrics are enabled
  (`enable_metrics`, `enable_usage_metrics`) but they land in local logs, not in
  [Agent Observability](https://docs.livekit.io/deploy/observability/).

## Notes on the services

All three services live in `livekit_inference.py` and follow Pipecat's own
service conventions, so reconnection, interruption handling, and metrics come
from the base classes:

| Service | Extends | Endpoint |
|---|---|---|
| `LiveKitInferenceSTTService` | `WebsocketSTTService` | `GET /v1/stt` |
| `LiveKitInferenceTTSService` | `InterruptibleTTSService` | `GET /v1/tts` |
| `LiveKitInferenceLLMService` | `OpenAILLMService` | `POST /v1/chat/completions` |

`LiveKitInferenceLLMService` subclasses Pipecat's OpenAI service because the
LiveKit Inference completions endpoint is OpenAI-compatible — it swaps in the
LiveKit Inference base URL and auth, and nothing else. Worth knowing: the model
id echoed back can differ in namespace and casing from the one you request
(`google/gemma-4-31b-it` has come back as both `livekit/gemma-4-31b-it` and
`google/gemma-4-31B-it`), so don't string-match on it. It also never falls back to a provider key: if
`OPENAI_API_KEY` is set in your environment (the OpenAI SDK reads it by default),
it is ignored, and a test pins that.

- **Auth.** A JWT signed with your API secret, carrying `inference.perform=true`.
  Auth happens at the websocket handshake, so the STT and TTS services mint a
  fresh short-lived token on every connect. A handshake `429` is retried with
  backoff; `401`/`403` fail immediately.
- **LLM token lifetime.** The LLM sends its token on every HTTP request rather
  than at a handshake, so `LiveKitInferenceLLMService` remints it 5 minutes
  before expiry (signing is local and cheap). Session length is not bounded by
  the token's TTL.
- **Sample rates.** LiveKit Inference accepts 8000–32000 Hz for STT input and a fixed
  set of rates for TTS output. Both services follow the transport's rates
  (16 kHz in, 24 kHz out here) and reject a rate LiveKit Inference would refuse, rather
  than declaring one rate and sending another.
- **Participant kind.** The agent joins with `kind == AGENT`, which is how
  frontends pick it out of the room (it's what the LiveKit React SDK's
  `useVoiceAssistant` looks for). LiveKit takes this from the token's `kind`
  claim; Pipecat's runner sets the `agent` video grant but not that claim, which
  only gets you a STANDARD participant, so `agent.py` mints its own room token
  the way `livekit-agents` does.
- **`ttfs_p99_latency not set` on startup.** Pipecat uses this to size how long it
  waits for transcripts, and falls back to 1.0s. It's left unset rather than
  guessing a number; pass it to `LiveKitInferenceSTTService` if
  you've measured your own.
