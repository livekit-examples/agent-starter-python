"""Pipecat services for LiveKit Inference: speech-to-text, LLM, and text-to-speech.

LiveKit Inference serves the best voice AI models through one API as part of LiveKit Cloud.

- Overview:   https://livekit.com/products/inference
- Pricing:    https://livekit.com/pricing/inference
- Models:     https://docs.livekit.io/agents/models/

Install::

    pip install "pipecat-ai[openai,silero]" livekit-api websockets

Set your LiveKit Cloud project keys, and the services pick them up from the
environment (``livekit-api`` is used only to sign LiveKit Inference tokens):

    LIVEKIT_API_KEY / LIVEKIT_API_SECRET

Then wire them into a Pipecat pipeline. These services are transport-agnostic,
so bring whichever transport carries your audio.

    stt = LiveKitInferenceSTTService(
        model="assemblyai/universal-3-5-pro", language="en"
    )

    llm = LiveKitInferenceLLMService(model="google/gemma-4-31b-it")

    tts = LiveKitInferenceTTSService(
        model="fishaudio/s2.1-pro",
        voice="fa4c9eb3dccc4806b382b40d61c6b10a",
    )
"""

import asyncio
import base64
import contextlib
import datetime
import json
import os
import time
from collections.abc import AsyncGenerator

from livekit import api as lk_api
from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.settings import STTSettings, TTSSettings
from pipecat.services.stt_service import WebsocketSTTService
from pipecat.services.tts_service import InterruptibleTTSService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601

DEFAULT_WS_URL = "wss://agent-gateway.livekit.cloud/v1"
DEFAULT_HTTP_URL = "https://agent-gateway.livekit.cloud/v1"

_DIAL_BACKOFF_S = (1, 2, 4)
STT_SAMPLE_RATE_RANGE = (8000, 32000)
LLM_TOKEN_TTL_S = 3600.0
LLM_TOKEN_REFRESH_MARGIN_S = 300.0
TTS_VALID_SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)


def _check_stt_sample_rate(sample_rate: int) -> None:
    """Raise if LiveKit Inference would reject this STT input rate."""
    low, high = STT_SAMPLE_RATE_RANGE
    if not low <= sample_rate <= high:
        raise ValueError(
            f"sample rate {sample_rate} is outside the range LiveKit Inference accepts "
            f"({low}-{high}). Set the transport's audio_in_sample_rate (or this "
            f"service's sample_rate) accordingly."
        )


def _check_tts_sample_rate(sample_rate: int) -> None:
    """Raise if LiveKit Inference would reject this TTS output rate."""
    if sample_rate not in TTS_VALID_SAMPLE_RATES:
        raise ValueError(
            f"sample rate {sample_rate} is not one of the rates LiveKit Inference accepts "
            f"{TTS_VALID_SAMPLE_RATES}. Set the transport's audio_out_sample_rate "
            f"(or this service's sample_rate) accordingly."
        )


def inference_url(region: str | None = None) -> str:
    """Global LiveKit Inference URL by default; region-pinned for a specific cluster."""
    if region:
        return f"wss://{region}.agent-gateway.production.livekit.cloud/v1"
    return DEFAULT_WS_URL


def create_inference_token(
    api_key: str | None = None,
    api_secret: str | None = None,
    ttl_seconds: float = 600,
) -> str:
    """Mint a LiveKit Inference JWT from a LiveKit Cloud API key/secret.

    Args:
        api_key: LiveKit API key. Defaults to ``LIVEKIT_API_KEY``.
        api_secret: LiveKit API secret. Defaults to ``LIVEKIT_API_SECRET``.
        ttl_seconds: Token lifetime.
    """
    return (
        lk_api.AccessToken(
            api_key or os.environ["LIVEKIT_API_KEY"],
            api_secret or os.environ["LIVEKIT_API_SECRET"],
        )
        .with_identity("pipecat-inference")
        .with_inference_grants(lk_api.access_token.InferenceGrants(perform=True))
        .with_ttl(datetime.timedelta(seconds=ttl_seconds))
        .to_jwt()
    )


def _normalize_language(language: str | Language | None) -> str | None:
    """Render a language as the wire string LiveKit Inference expects."""
    if language is None:
        return None
    return language.value if isinstance(language, Language) else language


async def _dial_with_429_retry(websocket_connect, url: str, token: str):
    """Dial LiveKit Inference, retrying only a handshake 429 (concurrency pressure)."""
    headers = {"Authorization": f"Bearer {token}"}
    last_exc: Exception | None = None
    for delay in (*_DIAL_BACKOFF_S, None):
        try:
            return await websocket_connect(url, additional_headers=headers)
        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(
                getattr(e, "response", None), "status_code", None
            )
            if status == 429 and delay is not None:
                logger.warning(
                    f"LiveKit Inference dial 429, retrying in {delay}s ({url})"
                )
                last_exc = e
                await asyncio.sleep(delay)
                continue
            raise
    raise last_exc  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# STT
# --------------------------------------------------------------------------- #


class LiveKitInferenceSTTService(WebsocketSTTService):
    """Streaming speech-to-text via LiveKit Inference (``GET /v1/stt``).

    Emits an ``InterimTranscriptionFrame`` per partial result and a
    ``TranscriptionFrame`` per final one. Interim results supersede each other
    rather than accumulating.

    The sample rate follows the transport's ``audio_in_sample_rate`` unless
    ``sample_rate`` is passed explicitly, so the rate declared always matches the
    bytes on the wire.
    """

    def __init__(
        self,
        *,
        model: str = "assemblyai/universal-3-5-pro",
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        region: str | None = None,
        language: str | Language | None = None,
        extra: dict | None = None,
        sample_rate: int | None = None,
        **kwargs,
    ):
        """Initialize the LiveKit Inference STT service.

        Args:
            model: LiveKit Inference model id, e.g. ``"assemblyai/universal-3-5-pro"``.
            api_key: LiveKit API key. Defaults to ``LIVEKIT_API_KEY``.
            api_secret: LiveKit API secret. Defaults to ``LIVEKIT_API_SECRET``.
            base_url: Override the LiveKit Inference base URL (wss://.../v1).
            region: Pin to a specific region instead of the global URL.
            language: Recognition language. Omitted means the provider decides.
            extra: Provider-specific passthrough options.
            sample_rate: Input rate to declare to LiveKit Inference. Defaults to
                following the transport's ``audio_in_sample_rate``.
            **kwargs: Passed to ``WebsocketSTTService``.

        Raises:
            ValueError: If ``sample_rate`` is outside the range LiveKit Inference accepts.
        """
        if sample_rate is not None:
            _check_stt_sample_rate(sample_rate)

        settings = STTSettings(model=model, language=_normalize_language(language))
        settings.extra = extra or {}

        kwargs.setdefault("keepalive_timeout", 120)
        kwargs.setdefault("keepalive_interval", 30)
        super().__init__(settings=settings, sample_rate=sample_rate, **kwargs)

        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = (base_url or inference_url(region)).rstrip("/")
        self._receive_task = None
        self._session_ready = asyncio.Event()

    def can_generate_metrics(self) -> bool:
        """Whether this service reports metrics."""
        return True

    async def start(self, frame: StartFrame):
        """Resolve the sample rate and open the session."""
        await super().start(frame)

        try:
            _check_stt_sample_rate(self.sample_rate)
        except ValueError as e:
            # Exceptions raised handling a StartFrame are only logged, so report
            # this rather than opening a session that could only mistranscribe.
            await self.push_error(error_msg=f"{self}: {e}", exception=e)
            return

        await self._connect()

    # WebsocketSTTService.stop/cancel/cleanup already disconnect for us.

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Flush pending transcripts when the user stops speaking."""
        await super().process_frame(frame, direction)

        if (
            isinstance(frame, VADUserStoppedSpeakingFrame)
            and self._session_ready.is_set()
        ):
            # Fire-and-forget: the ack is provider-mediated and not guaranteed.
            await self._send_json({"type": "session.finalize"})

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        """Stream 16-bit mono PCM; transcripts arrive on the receive loop."""
        if not self._session_ready.is_set():
            await self._connect()

        if not self._session_ready.is_set():
            logger.warning(
                f"{self}: session unavailable after reconnect, dropping audio"
            )
            yield None
            return

        await self._send_json(
            {"type": "input_audio", "audio": base64.b64encode(audio).decode("utf-8")}
        )
        yield None

    async def _update_settings(self, delta: STTSettings) -> dict:
        """Apply a delta, reconnecting since model and language are fixed per session."""
        changed = await super()._update_settings(delta)
        if changed:
            await self._request_reconnect()
        return changed

    async def _send_keepalive(self, silence: bytes):
        """Send silence in LiveKit Inference's JSON envelope to hold the session open."""
        await self._send_json(
            {"type": "input_audio", "audio": base64.b64encode(silence).decode("utf-8")}
        )
        self._record_stt_audio_usage(silence)

    async def _send_json(self, message: dict):
        """Send one JSON frame, tolerating a socket that died between turns."""
        ws = self._websocket
        if ws is None:
            return
        try:
            await ws.send(json.dumps(message))
        except Exception as e:
            logger.warning(f"{self}: send failed: {e}")

    async def _connect(self):
        await super()._connect()

        await self._connect_websocket()

        if self._websocket and not self._receive_task:
            self._receive_task = self.create_task(
                self._receive_task_handler(self._report_error)
            )

    async def _disconnect(self):
        await super()._disconnect()

        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None

        await self._disconnect_websocket()

    async def _connect_websocket(self):
        try:
            if self._websocket and self._session_ready.is_set():
                return

            logger.debug(
                f"Connecting to LiveKit Inference STT ({self._settings.model})"
            )
            ws = await _dial_with_429_retry(
                self._websocket_connect,
                f"{self._base_url}/stt",
                create_inference_token(self._api_key, self._api_secret),
            )

            settings: dict = {
                "sample_rate": self.sample_rate,
                "encoding": "pcm_s16le",
            }
            if self._settings.language:
                settings["language"] = self._settings.language
            if self._settings.extra:
                settings["extra"] = self._settings.extra
            await ws.send(
                json.dumps(
                    {
                        "type": "session.create",
                        "model": self._settings.model,
                        "settings": settings,
                    }
                )
            )

            # session.created confirms the provider connected, not just that our
            # JSON parsed, so audio is gated on it.
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if ack.get("type") != "session.created":
                await ws.close()
                raise RuntimeError(
                    f"session.create failed: {ack.get('code')}: {ack.get('message')}"
                )

            self._websocket = ws
            self._session_ready.set()
            await self._call_event_handler("on_connected")
        except Exception as e:
            self._websocket = None
            self._session_ready.clear()
            await self.push_error(
                error_msg=f"Unable to connect to LiveKit Inference STT: {e}",
                exception=e,
            )
            await self._call_event_handler("on_connection_error", f"{e}")

    async def _disconnect_websocket(self):
        ws = self._websocket
        try:
            if ws:
                logger.debug("Disconnecting from LiveKit Inference STT")
                await self._send_json({"type": "session.close"})
                await ws.close()
        except Exception as e:
            await self.push_error(
                error_msg=f"Error closing websocket: {e}", exception=e
            )
        finally:
            # Only clear if a concurrent _connect hasn't already replaced it.
            if self._websocket is ws:
                self._websocket = None
            self._session_ready.clear()
            await self._call_event_handler("on_disconnected")

    def _get_websocket(self):
        if self._websocket:
            return self._websocket
        raise Exception("Websocket not connected")

    async def _receive_messages(self):
        async for message in self._get_websocket():
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning(f"{self}: received non-JSON message: {message}")
                continue

            mtype = data.get("type")
            if mtype in ("interim_transcript", "final_transcript"):
                await self._handle_transcript(mtype, data)
            elif mtype == "error":
                await self.push_error(
                    error_msg=f"LiveKit Inference STT error "
                    f"{data.get('code')}: {data.get('message')}"
                )
            # Anything else is ignored: provider-conditional events ship freely.

    async def _handle_transcript(self, mtype: str, data: dict):
        text = data.get("transcript", "")
        if not text:
            # Providers emit empty interims during silence.
            return

        language = None
        if data.get("language"):
            # A language Pipecat has no enum for still has a good transcript.
            with contextlib.suppress(ValueError):
                language = Language(data["language"])

        if mtype == "final_transcript":
            await self.push_frame(
                TranscriptionFrame(
                    text, self._user_id, time_now_iso8601(), language, result=data
                )
            )
        else:
            await self.push_frame(
                InterimTranscriptionFrame(
                    text, self._user_id, time_now_iso8601(), language, result=data
                )
            )


# --------------------------------------------------------------------------- #
# TTS
# --------------------------------------------------------------------------- #


class LiveKitInferenceTTSService(InterruptibleTTSService):
    """Streaming TTS via LiveKit Inference (``GET /v1/tts``).

    One session serves every turn, reconnecting if it goes idle long enough to be
    reaped. There is no per-turn cancel message, so interruptions are handled by
    ``InterruptibleTTSService``, which drops and reopens the connection.
    """

    def __init__(
        self,
        *,
        model: str = "fishaudio/s2.1-pro",
        voice: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        region: str | None = None,
        language: str | Language | None = None,
        extra: dict | None = None,
        sample_rate: int | None = None,
        **kwargs,
    ):
        """Initialize the LiveKit Inference TTS service.

        Args:
            model: LiveKit Inference model id, e.g. ``"fishaudio/s2.1-pro"``.
            voice: Provider voice id.
            api_key: LiveKit API key. Defaults to ``LIVEKIT_API_KEY``.
            api_secret: LiveKit API secret. Defaults to ``LIVEKIT_API_SECRET``.
            base_url: Override the LiveKit Inference base URL (wss://.../v1).
            region: Pin to a specific region instead of the global URL.
            language: Synthesis language. Omitted means the provider decides.
            extra: Provider-specific passthrough options.
            sample_rate: Output rate to request from LiveKit Inference. Defaults to
                following the transport's ``audio_out_sample_rate``.
            **kwargs: Passed to ``InterruptibleTTSService``.

        Raises:
            ValueError: If ``sample_rate`` is not a rate LiveKit Inference accepts.
        """
        if sample_rate is not None:
            _check_tts_sample_rate(sample_rate)

        settings = TTSSettings(
            model=model, voice=voice, language=_normalize_language(language)
        )
        settings.extra = extra or {}

        # Chunks land verbatim in the provider's buffer, so without a separator
        # "Hello" + "world" would synthesize as "Helloworld".
        kwargs.setdefault("append_trailing_space", True)
        # Required: the base class opens the audio context that audio arriving on
        # the receive loop gets appended to. `done` closes it again.
        kwargs.setdefault("push_start_frame", True)
        kwargs.setdefault("pause_frame_processing", True)
        super().__init__(settings=settings, sample_rate=sample_rate, **kwargs)

        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = (base_url or inference_url(region)).rstrip("/")
        self._receive_task = None

    def can_generate_metrics(self) -> bool:
        """Whether this service reports metrics."""
        return True

    async def start(self, frame: StartFrame):
        """Resolve the sample rate and open the session."""
        await super().start(frame)

        try:
            _check_tts_sample_rate(self.sample_rate)
        except ValueError as e:
            # As in the STT service: a StartFrame exception would only be logged.
            await self.push_error(error_msg=f"{self}: {e}", exception=e)
            return

        await self._connect()

    async def stop(self, frame: EndFrame):
        """Close the session on a graceful end."""
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame):
        """Close the session immediately."""
        await super().cancel(frame)
        await self._disconnect()

    async def _connect(self):
        await super()._connect()

        await self._connect_websocket()

        if self._websocket and not self._receive_task:
            self._receive_task = self.create_task(
                self._receive_task_handler(self._report_error)
            )

    async def _disconnect(self):
        await super()._disconnect()

        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None

        await self._disconnect_websocket()

    async def _connect_websocket(self):
        try:
            if self._websocket:
                return

            logger.debug(
                f"Connecting to LiveKit Inference TTS ({self._settings.model})"
            )
            ws = await _dial_with_429_retry(
                self._websocket_connect,
                f"{self._base_url}/tts",
                create_inference_token(self._api_key, self._api_secret),
            )

            create: dict = {
                "type": "session.create",
                "model": self._settings.model,
                "sample_rate": self.sample_rate,
                "encoding": "pcm_s16le",
            }
            if self._settings.voice:
                create["voice"] = self._settings.voice
            if self._settings.language:
                create["language"] = self._settings.language
            if self._settings.extra:
                create["extra"] = self._settings.extra
            await ws.send(json.dumps(create))

            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if ack.get("type") != "session.created":
                await ws.close()
                raise RuntimeError(
                    f"session.create failed: {ack.get('code')}: {ack.get('data')}"
                )

            self._websocket = ws
            await self._call_event_handler("on_connected")
        except Exception as e:
            self._websocket = None
            await self.push_error(
                error_msg=f"Unable to connect to LiveKit Inference TTS: {e}",
                exception=e,
            )
            await self._call_event_handler("on_connection_error", f"{e}")

    async def _disconnect_websocket(self):
        ws = self._websocket
        try:
            await self.stop_all_metrics()
            if ws:
                logger.debug("Disconnecting from LiveKit Inference TTS")
                await ws.send(json.dumps({"type": "session.close"}))
                await ws.close()
        except Exception as e:
            logger.warning(f"{self}: error closing websocket: {e}")
        finally:
            if self._websocket is ws:
                self._websocket = None
            await self._call_event_handler("on_disconnected")

    def _get_websocket(self):
        if self._websocket:
            return self._websocket
        raise Exception("Websocket not connected")

    async def on_audio_context_interrupted(self, context_id: str):
        """Stop metrics when the audio context is interrupted."""
        await self.stop_all_metrics()
        await super().on_audio_context_interrupted(context_id)

    async def flush_audio(self, context_id: str | None = None):
        """End the turn's text, once the whole response has been sent.

        Synthesis starts as text arrives, so this is only the terminator: it is
        answered with the single ``done`` that closes this turn's audio context.
        Flushing per sentence instead would end the turn on the first sentence.

        Args:
            context_id: Unused; one session serves one turn at a time.
        """
        if not self._websocket:
            return
        await self._get_websocket().send(json.dumps({"type": "session.flush"}))

    async def run_tts(
        self, text: str, context_id: str
    ) -> AsyncGenerator[Frame | None, None]:
        """Synthesize one chunk of text; audio arrives on the receive loop."""
        try:
            # An idle session is reaped, so the socket may be dead between turns.
            if not self._websocket:
                await self._connect()
            if not self._websocket:
                yield ErrorFrame(
                    error=f"{self}: no connection to LiveKit Inference TTS"
                )
                yield TTSStoppedFrame(context_id=context_id)
                return

            generation_config: dict = {"model": self._settings.model}
            if self._settings.voice:
                generation_config["voice"] = self._settings.voice
            if self._settings.language:
                generation_config["language"] = self._settings.language

            packet: dict = {
                "type": "input_transcript",
                "transcript": text,
                "generation_config": generation_config,
            }
            if self._settings.extra:
                packet["extra"] = self._settings.extra

            try:
                # No flush here: a turn is N chunks terminated by one flush, from
                # flush_audio(). Synthesis begins on this send regardless.
                await self._get_websocket().send(json.dumps(packet))
                await self.start_tts_usage_metrics(text)
            except Exception as e:
                yield ErrorFrame(error=f"LiveKit Inference TTS send failed: {e}")
                yield TTSStoppedFrame(context_id=context_id)
                await self._disconnect()
                await self._connect()
                return

            yield None
        except Exception as e:
            yield ErrorFrame(error=f"LiveKit Inference TTS error: {e}")

    async def _receive_messages(self):
        async for message in self._get_websocket():
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning(f"{self}: received non-JSON message: {message}")
                continue

            mtype = data.get("type")
            # No context id is echoed back, so the base class's playback cursor
            # decides which turn this audio belongs to.
            context_id = self.get_active_audio_context_id()

            if mtype == "output_audio":
                if not context_id or not self.audio_context_available(context_id):
                    continue
                await self.stop_ttfb_metrics()
                await self.append_to_audio_context(
                    context_id,
                    TTSAudioRawFrame(
                        audio=base64.b64decode(data["audio"]),
                        sample_rate=self.sample_rate,
                        num_channels=1,
                        context_id=context_id,
                    ),
                )
            elif mtype == "done":
                await self.stop_ttfb_metrics()
                await self._close_context(context_id)
            elif mtype == "error":
                retryable = data.get("retryable")  # absent means unknown, not false
                await self.push_error(
                    error_msg=f"LiveKit Inference TTS error {data.get('code')}: "
                    f"{data.get('data')} (retryable={retryable})"
                )
                if retryable is False:
                    # The turn is refused but the session lives, so close this
                    # context rather than leave the pipeline awaiting audio.
                    await self.stop_all_metrics()
                    await self._close_context(context_id)
            # Anything else is ignored: provider-conditional events ship freely.

    async def _close_context(self, context_id: str | None):
        """End a turn's audio context, if it is still open."""
        if not context_id or not self.audio_context_available(context_id):
            return
        await self.append_to_audio_context(
            context_id, TTSStoppedFrame(context_id=context_id)
        )
        await self.remove_audio_context(context_id)


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #


class LiveKitInferenceLLMService(OpenAILLMService):
    """LLM via LiveKit Inference (``POST /v1/chat/completions``).

    The endpoint is OpenAI-compatible, so this rides on Pipecat's OpenAI service
    and replaces only the base URL and the auth. The token travels on every
    request rather than a handshake, so it is reminted before it expires.
    """

    def __init__(
        self,
        *,
        model: str = "google/gemma-4-31b-it",
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str = DEFAULT_HTTP_URL,
        token_ttl_seconds: float = LLM_TOKEN_TTL_S,
        **kwargs,
    ):
        """Initialize the LiveKit Inference LLM service.

        Args:
            model: LiveKit Inference model id, e.g. ``"google/gemma-4-31b-it"``.
            api_key: LiveKit API key. Defaults to ``LIVEKIT_API_KEY``.
            api_secret: LiveKit API secret. Defaults to ``LIVEKIT_API_SECRET``.
            base_url: LiveKit Inference HTTP base URL.
            token_ttl_seconds: Lifetime of each minted token. Not a cap on
                session length -- tokens are reminted before expiry.
            **kwargs: Passed to ``OpenAILLMService``.
        """
        self._lk_api_key = api_key
        self._lk_api_secret = api_secret
        self._token_ttl_seconds = token_ttl_seconds
        self._token_expires_at = 0.0

        super().__init__(
            settings=self.Settings(model=model),
            api_key=self._mint_token(),
            base_url=base_url,
            **kwargs,
        )

    def _mint_token(self) -> str:
        """Mint a token and record when it needs replacing."""
        token = create_inference_token(
            self._lk_api_key, self._lk_api_secret, ttl_seconds=self._token_ttl_seconds
        )
        self._token_expires_at = time.monotonic() + self._token_ttl_seconds
        return token

    def _refresh_token_if_stale(self) -> None:
        """Remint the token before it can expire mid-session."""
        if time.monotonic() < self._token_expires_at - LLM_TOKEN_REFRESH_MARGIN_S:
            return
        logger.debug(f"{self}: reminting LiveKit Inference token")
        self._client.api_key = self._mint_token()

    async def get_chat_completions(self, context):
        """Run a completion on a valid token."""
        self._refresh_token_if_stale()
        return await super().get_chat_completions(context)
