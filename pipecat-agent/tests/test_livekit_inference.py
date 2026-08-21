"""Tests for the LiveKit Inference STT and TTS services.

These drive the services through a real Pipecat pipeline against a scripted
fake LiveKit Inference server, so they cover the wire protocol (what gets sent) and the frame
behavior (what the pipeline sees) without touching the network.
"""

import itertools
import time

import jwt
import pytest
from conftest import FakeInferenceWebsocket, attach_fake_inference
from pipecat.frames.frames import (
    ErrorFrame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.worker import PipelineParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.tests.utils import SleepFrame, run_test

import livekit_inference
from livekit_inference import (
    DEFAULT_HTTP_URL,
    DEFAULT_WS_URL,
    LLM_TOKEN_REFRESH_MARGIN_S,
    LiveKitInferenceLLMService,
    LiveKitInferenceSTTService,
    LiveKitInferenceTTSService,
    _dial_with_429_retry,
    create_inference_token,
    inference_url,
)

SECRET = "test-secret-not-a-real-one"
AUDIO = b"\x00\x01" * 160


def _tts(**kwargs) -> LiveKitInferenceTTSService:
    """Build the TTS service for a transport-less test pipeline.

    ``pause_frame_processing`` is on in production, where the transport output
    confirms playback with a BotStartedSpeakingFrame. There is no output
    transport here, so leaving it on just means every TTS test waits out the
    3-second pause watchdog.
    """
    kwargs.setdefault("pause_frame_processing", False)
    return LiveKitInferenceTTSService(**kwargs)


def _llm_says(text: str, settle: float = 0.3):
    """The frame sequence a TTS service sees for one LLM response."""
    return [
        LLMFullResponseStartFrame(),
        TextFrame(text),
        LLMFullResponseEndFrame(),
        SleepFrame(settle),
    ]


def frames_of(frames, frame_type):
    """Every frame of the given type in a captured sequence."""
    return [f for f in frames if isinstance(f, frame_type)]


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


def test_token_carries_the_inference_perform_grant():
    """A token without inference.perform=true is rejected by LiveKit Inference with 401."""
    claims = jwt.decode(create_inference_token(), SECRET, algorithms=["HS256"])

    assert claims["iss"] == "APItestkey"
    assert claims["inference"] == {"perform": True}


def test_token_honors_explicit_credentials():
    """Credentials passed in win over the environment."""
    token = create_inference_token("APIother", "another-secret")

    claims = jwt.decode(token, "another-secret", algorithms=["HS256"])
    assert claims["iss"] == "APIother"


def test_inference_url_defaults_to_global_and_pins_to_a_region():
    assert inference_url() == DEFAULT_WS_URL
    assert inference_url("uswest2").startswith("wss://uswest2.agent-gateway")


# --------------------------------------------------------------------------- #
# Dialing
# --------------------------------------------------------------------------- #


class _HandshakeError(Exception):
    def __init__(self, status_code):
        super().__init__(f"handshake failed: {status_code}")
        self.status_code = status_code


async def test_dial_retries_a_429_then_succeeds():
    """A 429 handshake is concurrency pressure, so the dial is retried."""
    attempts = []

    async def connect(uri, **kwargs):
        attempts.append(uri)
        if len(attempts) < 3:
            raise _HandshakeError(429)
        return "connected"

    # Patch out the backoff sleeps so the test doesn't actually wait 3 seconds.
    import livekit_inference

    livekit_inference._DIAL_BACKOFF_S = (0, 0, 0)

    result = await _dial_with_429_retry(connect, "wss://inference.test/v1/stt", "token")

    assert result == "connected"
    assert len(attempts) == 3


async def test_dial_fails_fast_on_401():
    """A bad or grantless token is deterministic; retrying would only waste time."""
    attempts = []

    async def connect(uri, **kwargs):
        attempts.append(uri)
        raise _HandshakeError(401)

    with pytest.raises(_HandshakeError):
        await _dial_with_429_retry(connect, "wss://inference.test/v1/stt", "token")

    assert len(attempts) == 1


async def test_dial_sends_the_token_as_a_bearer_header():
    captured = {}

    async def connect(uri, **kwargs):
        captured.update(kwargs)
        return "connected"

    await _dial_with_429_retry(connect, "wss://inference.test/v1/stt", "a-token")

    assert captured["additional_headers"]["Authorization"] == "Bearer a-token"


# --------------------------------------------------------------------------- #
# STT
# --------------------------------------------------------------------------- #


async def test_stt_nests_its_settings_in_session_create():
    """STT nests settings; TTS does not. Getting this backwards breaks the session."""
    stt = LiveKitInferenceSTTService(
        model="assemblyai/universal-3-5-pro", language="en"
    )
    sockets = attach_fake_inference(stt)

    await run_test(stt, frames_to_send=[], expected_down_frames=None)

    (create,) = sockets[0].sent_of_type("session.create")
    assert create["model"] == "assemblyai/universal-3-5-pro"
    assert create["settings"] == {
        "sample_rate": 16000,
        "encoding": "pcm_s16le",
        "language": "en",
    }
    assert sockets[0].uri.endswith("/stt")


async def test_stt_omits_language_when_unset():
    """Omitting the language lets the provider decide."""
    stt = LiveKitInferenceSTTService()
    sockets = attach_fake_inference(stt)

    await run_test(stt, frames_to_send=[])

    (create,) = sockets[0].sent_of_type("session.create")
    assert "language" not in create["settings"]


async def test_stt_sends_base64_audio_and_emits_a_final_transcript():
    def script(message):
        if message["type"] == "input_audio":
            return [
                {
                    "type": "final_transcript",
                    "transcript": "hello there",
                    "language": "en",
                }
            ]
        return []

    stt = LiveKitInferenceSTTService(language="en")
    sockets = attach_fake_inference(stt, script=script)

    down, _ = await run_test(
        stt,
        frames_to_send=[
            InputAudioRawFrame(audio=AUDIO, sample_rate=16000, num_channels=1),
            SleepFrame(0.2),
        ],
    )

    (audio_msg,) = sockets[0].sent_of_type("input_audio")
    import base64

    assert base64.b64decode(audio_msg["audio"]) == AUDIO

    (transcription,) = frames_of(down, TranscriptionFrame)
    assert transcription.text == "hello there"
    assert transcription.language is not None


async def test_stt_emits_interim_transcripts_separately():
    def script(message):
        if message["type"] == "input_audio":
            return [{"type": "interim_transcript", "transcript": "hel"}]
        return []

    stt = LiveKitInferenceSTTService()
    attach_fake_inference(stt, script=script)

    down, _ = await run_test(
        stt,
        frames_to_send=[
            InputAudioRawFrame(audio=AUDIO, sample_rate=16000, num_channels=1),
            SleepFrame(0.2),
        ],
    )

    assert len(frames_of(down, InterimTranscriptionFrame)) == 1
    assert frames_of(down, TranscriptionFrame) == []


async def test_stt_ignores_empty_transcripts():
    """Providers emit empty interims during silence; they aren't turns."""

    def script(message):
        if message["type"] == "input_audio":
            return [{"type": "interim_transcript", "transcript": ""}]
        return []

    stt = LiveKitInferenceSTTService()
    attach_fake_inference(stt, script=script)

    down, _ = await run_test(
        stt,
        frames_to_send=[
            InputAudioRawFrame(audio=AUDIO, sample_rate=16000, num_channels=1),
            SleepFrame(0.2),
        ],
    )

    assert frames_of(down, InterimTranscriptionFrame) == []


async def test_stt_ignores_unknown_message_types():
    """Provider-conditional events ship without a version bump."""

    def script(message):
        if message["type"] == "input_audio":
            return [
                {"type": "start_of_speech"},
                {"type": "preflight_transcript", "transcript": "ignored"},
                {"type": "session.finalized"},
                {"type": "something.invented.tomorrow"},
                {"type": "final_transcript", "transcript": "real"},
            ]
        return []

    stt = LiveKitInferenceSTTService()
    attach_fake_inference(stt, script=script)

    down, _ = await run_test(
        stt,
        frames_to_send=[
            InputAudioRawFrame(audio=AUDIO, sample_rate=16000, num_channels=1),
            SleepFrame(0.2),
        ],
    )

    (transcription,) = frames_of(down, TranscriptionFrame)
    assert transcription.text == "real"


async def test_stt_finalizes_when_the_user_stops_speaking():
    """session.finalize asks LiveKit Inference to flush pending finals at end of turn."""
    stt = LiveKitInferenceSTTService()
    sockets = attach_fake_inference(stt)

    await run_test(stt, frames_to_send=[VADUserStoppedSpeakingFrame(), SleepFrame(0.1)])

    assert len(sockets[0].sent_of_type("session.finalize")) == 1


async def test_stt_surfaces_livekit_inference_errors():
    """STT errors carry an integer code and text under `message`."""

    def script(message):
        if message["type"] == "input_audio":
            return [{"type": "error", "code": 1011, "message": "provider exploded"}]
        return []

    stt = LiveKitInferenceSTTService()
    attach_fake_inference(stt, script=script)

    down, up = await run_test(
        stt,
        frames_to_send=[
            InputAudioRawFrame(audio=AUDIO, sample_rate=16000, num_channels=1),
            SleepFrame(0.2),
        ],
    )

    errors = frames_of(down, ErrorFrame) + frames_of(up, ErrorFrame)
    assert any("1011" in e.error and "provider exploded" in e.error for e in errors)


async def test_stt_closes_the_session_gracefully():
    """session.close gives the provider a chance to return trailing finals."""
    stt = LiveKitInferenceSTTService()
    sockets = attach_fake_inference(stt)

    await run_test(stt, frames_to_send=[])

    assert sockets[0].sent_of_type("session.close")
    assert sockets[0].close_calls >= 1


def test_stt_rejects_a_sample_rate_livekit_inference_rejects():
    """Declaring a rate outside 8000-32000 would be silently mistranscribed."""
    with pytest.raises(ValueError, match="outside the range"):
        LiveKitInferenceSTTService(sample_rate=48000)


async def test_stt_does_not_connect_when_session_create_is_rejected():
    """Audio is gated on session.created, which confirms the provider is up."""
    stt = LiveKitInferenceSTTService()
    sockets = attach_fake_inference(
        stt, ack={"type": "error", "code": 401, "message": "no inference grant"}
    )

    down, up = await run_test(
        stt,
        frames_to_send=[
            InputAudioRawFrame(audio=AUDIO, sample_rate=16000, num_channels=1),
            SleepFrame(0.1),
        ],
    )

    # No audio may be sent on a session LiveKit Inference never created.
    assert sockets[0].sent_of_type("input_audio") == []
    errors = frames_of(down, ErrorFrame) + frames_of(up, ErrorFrame)
    assert any("session.create failed" in e.error for e in errors)


async def test_stt_keepalive_wraps_silence_in_the_json_envelope():
    """Raw PCM on this protocol would be a protocol violation, not a keepalive."""
    stt = LiveKitInferenceSTTService()
    sockets = attach_fake_inference(stt)

    await run_test(stt, frames_to_send=[])
    # The socket is closed by now; call the hook directly on a fresh one.
    stt._websocket = FakeInferenceWebsocket()

    await stt._send_keepalive(b"\x00" * 320)

    (message,) = stt._websocket.sent_of_type("input_audio")
    assert "audio" in message
    assert sockets  # the session really was established first


# --------------------------------------------------------------------------- #
# TTS
# --------------------------------------------------------------------------- #


def _tts_script(message):
    """Answer a flush with one audio chunk and the turn terminator."""
    if message["type"] == "session.flush":
        return [
            {"type": "output_audio", "audio": "AAAA"},
            {"type": "done"},
        ]
    return []


async def test_tts_session_create_is_flat():
    """TTS puts sample_rate/encoding/voice at the top level, unlike STT."""
    tts = _tts(model="fishaudio/s2.1-pro", voice="a-voice-id")
    sockets = attach_fake_inference(tts, script=_tts_script)

    await run_test(tts, frames_to_send=[])

    (create,) = sockets[0].sent_of_type("session.create")
    assert "settings" not in create
    assert create["model"] == "fishaudio/s2.1-pro"
    assert create["voice"] == "a-voice-id"
    assert create["sample_rate"] == 24000
    assert create["encoding"] == "pcm_s16le"
    assert sockets[0].uri.endswith("/tts")


async def test_tts_synthesizes_text_and_ends_the_turn_on_done():
    tts = _tts()
    sockets = attach_fake_inference(tts, script=_tts_script)

    down, _ = await run_test(tts, frames_to_send=_llm_says("Hello there."))

    (transcript,) = sockets[0].sent_of_type("input_transcript")
    assert transcript["transcript"].strip() == "Hello there."
    # Exactly one flush: a second would be answered with a second `done`, which
    # would close the audio context while audio was still arriving.
    assert len(sockets[0].sent_of_type("session.flush")) == 1

    assert frames_of(down, TTSStartedFrame)
    assert frames_of(down, TTSAudioRawFrame)
    assert frames_of(down, TTSStoppedFrame)


async def test_tts_flushes_once_per_turn_not_once_per_sentence():
    """A flush terminates the whole turn.

    LiveKit Inference answers one flush with one ``done``, and synthesis starts
    as text arrives rather than at the flush. Flushing per sentence therefore
    ends the turn on the first sentence and drops the rest of the response.
    """
    tts = _tts()
    sockets = attach_fake_inference(tts, script=_tts_script)

    down, _ = await run_test(
        tts,
        frames_to_send=[
            LLMFullResponseStartFrame(),
            TextFrame("First sentence. "),
            TextFrame("Second sentence. "),
            TextFrame("Third sentence. "),
            LLMFullResponseEndFrame(),
            SleepFrame(0.4),
        ],
    )

    types = [m["type"] for m in sockets[0].sent]
    assert types.count("input_transcript") == 3
    assert types.count("session.flush") == 1

    # The flush has to come after the last chunk, or it ends the turn early.
    last_chunk = max(i for i, t in enumerate(types) if t == "input_transcript")
    assert types.index("session.flush") > last_chunk

    assert frames_of(down, TTSAudioRawFrame)
    assert len(frames_of(down, TTSStoppedFrame)) == 1


async def test_tts_separates_chunks_with_a_trailing_space():
    """Chunks land verbatim in the provider buffer, so "Hello"+"world" would run together."""
    tts = _tts()
    sockets = attach_fake_inference(tts, script=_tts_script)

    await run_test(tts, frames_to_send=_llm_says("Hello there."))

    (transcript,) = sockets[0].sent_of_type("input_transcript")
    assert transcript["transcript"].endswith(" ")


async def test_tts_sends_the_generation_config_with_each_turn():
    tts = _tts(model="fishaudio/s2.1-pro", voice="a-voice-id", language="en")
    sockets = attach_fake_inference(tts, script=_tts_script)

    await run_test(tts, frames_to_send=_llm_says("Hello there."))

    (transcript,) = sockets[0].sent_of_type("input_transcript")
    assert transcript["generation_config"] == {
        "model": "fishaudio/s2.1-pro",
        "voice": "a-voice-id",
        "language": "en",
    }


async def test_tts_reports_a_non_retryable_error_and_closes_the_turn():
    """A refused turn must not leave the pipeline waiting for audio that never comes."""

    def script(message):
        if message["type"] == "session.flush":
            return [
                {
                    "type": "error",
                    "code": "invalid_voice",
                    "data": "unknown voice id",
                    "retryable": False,
                }
            ]
        return []

    tts = _tts()
    attach_fake_inference(tts, script=script)

    down, up = await run_test(tts, frames_to_send=_llm_says("Hello there."))

    errors = frames_of(down, ErrorFrame) + frames_of(up, ErrorFrame)
    assert any(
        "invalid_voice" in e.error and "unknown voice id" in e.error for e in errors
    )
    assert frames_of(down, TTSStoppedFrame)


def test_tts_rejects_a_sample_rate_livekit_inference_rejects():
    with pytest.raises(ValueError, match="not one of the rates"):
        LiveKitInferenceTTSService(sample_rate=12345)


async def test_tts_refuses_to_open_a_session_at_a_rejected_transport_rate():
    """The rate can also arrive from the transport, after __init__ has run."""
    tts = _tts()
    sockets = attach_fake_inference(tts, script=_tts_script)

    down, up = await run_test(
        tts,
        frames_to_send=[],
        pipeline_params=PipelineParams(audio_out_sample_rate=12345),
    )

    assert sockets == []
    errors = frames_of(down, ErrorFrame) + frames_of(up, ErrorFrame)
    assert any("not one of the rates" in e.error for e in errors)


async def test_tts_closes_the_session_on_shutdown():
    tts = _tts()
    sockets = attach_fake_inference(tts, script=_tts_script)

    await run_test(tts, frames_to_send=[])

    assert sockets[0].sent_of_type("session.close")
    assert sockets[0].close_calls >= 1


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #


def test_llm_talks_to_livekit_inference_with_an_inference_token():
    llm = LiveKitInferenceLLMService(model="google/gemma-4-31b-it")

    assert llm._settings.model == "google/gemma-4-31b-it"
    assert str(llm._client.base_url).startswith(DEFAULT_HTTP_URL)

    claims = jwt.decode(llm._client.api_key, SECRET, algorithms=["HS256"])
    assert claims["inference"] == {"perform": True}


def test_llm_ignores_a_provider_api_key_in_the_environment(monkeypatch):
    """The OpenAI SDK falls back to OPENAI_API_KEY, which would silently bill OpenAI."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-a-real-looking-openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    llm = LiveKitInferenceLLMService()

    assert llm._client.api_key != "sk-a-real-looking-openai-key"
    assert "openai.com" not in str(llm._client.base_url)


def test_llm_keeps_a_token_that_is_still_fresh(monkeypatch):
    llm = LiveKitInferenceLLMService(token_ttl_seconds=3600)
    original = llm._client.api_key
    monkeypatch.setattr(
        livekit_inference,
        "create_inference_token",
        lambda *a, **k: "should-not-be-used",
    )

    llm._refresh_token_if_stale()

    assert llm._client.api_key == original


def test_llm_remints_the_token_before_it_expires(monkeypatch):
    """The token rides on every request, so an expiring one would 401 mid-session."""
    llm = LiveKitInferenceLLMService(token_ttl_seconds=3600)
    counter = itertools.count(1)
    monkeypatch.setattr(
        livekit_inference,
        "create_inference_token",
        lambda *a, **k: f"reminted-{next(counter)}",
    )

    # Wind the clock to just inside the refresh margin.
    llm._token_expires_at = time.monotonic() + LLM_TOKEN_REFRESH_MARGIN_S - 1
    llm._refresh_token_if_stale()

    assert llm._client.api_key == "reminted-1"
    assert llm._token_expires_at > time.monotonic() + LLM_TOKEN_REFRESH_MARGIN_S


async def test_llm_checks_the_token_before_every_completion(monkeypatch):
    llm = LiveKitInferenceLLMService()
    checked = []
    monkeypatch.setattr(llm, "_refresh_token_if_stale", lambda: checked.append(True))

    async def fake_super(self, context):
        return "stream"

    monkeypatch.setattr(OpenAILLMService, "get_chat_completions", fake_super)

    result = await llm.get_chat_completions(context=None)

    assert result == "stream"
    assert checked == [True]
