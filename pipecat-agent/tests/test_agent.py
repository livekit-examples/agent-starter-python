"""Tests that the Pipecat agent stays equivalent to the LiveKit starter.

The point of this port is parity, so these assert the pipeline shape and pin the
prompt and model choices to ``src/agent.py``. If someone changes the starter,
these fail and say what drifted.
"""

import re
import textwrap
from pathlib import Path

import jwt
import pytest
from pipecat.pipeline.pipeline import PipelineSink, PipelineSource
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregator,
    LLMUserAggregator,
)
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport

import agent
from livekit_inference import (
    STT_SAMPLE_RATE_RANGE,
    TTS_VALID_SAMPLE_RATES,
    LiveKitInferenceLLMService,
    LiveKitInferenceSTTService,
    LiveKitInferenceTTSService,
)

STARTER_AGENT = Path(__file__).parent.parent.parent / "src" / "agent.py"

# Matches the credentials the autouse fixture in conftest.py installs.
SECRET = "test-secret-not-a-real-one"


def stages(pipeline):
    """The pipeline's own processors, without the source/sink Pipeline wraps them in."""
    return [
        p
        for p in pipeline.processors
        if not isinstance(p, (PipelineSource, PipelineSink))
    ]


def stage_of(pipeline, stage_type):
    """The single stage of the given type."""
    (found,) = [p for p in stages(pipeline) if isinstance(p, stage_type)]
    return found


@pytest.fixture
def transport():
    """A LiveKit transport that is constructed but never connected."""
    return LiveKitTransport(
        url="ws://localhost:7880",
        token="not-a-real-token",
        room_name="test-room",
        params=LiveKitParams(audio_in_enabled=True, audio_out_enabled=True),
    )


@pytest.fixture
def starter_source():
    """The LiveKit starter agent's source, or a skip if it isn't there."""
    if not STARTER_AGENT.exists():
        pytest.skip(f"LiveKit starter agent not found at {STARTER_AGENT}")
    return STARTER_AGENT.read_text()


def test_pipeline_runs_stt_llm_tts_in_order(transport):
    pipeline, _ = agent.build_pipeline(transport)

    expected = [
        BaseInputTransport,
        LiveKitInferenceSTTService,
        LLMUserAggregator,
        LiveKitInferenceLLMService,
        LiveKitInferenceTTSService,
        BaseOutputTransport,
        LLMAssistantAggregator,
    ]
    actual = stages(pipeline)

    assert len(actual) == len(expected), [type(p).__name__ for p in actual]
    for stage, stage_type in zip(actual, expected, strict=True):
        assert isinstance(stage, stage_type), (
            f"expected {stage_type.__name__}, got {type(stage).__name__}"
        )


def test_system_prompt_seeds_the_context(transport):
    _, context = agent.build_pipeline(transport)

    (message,) = context.get_messages()
    assert message["role"] == "system"
    assert message["content"] == agent.INSTRUCTIONS


def test_models_match_the_livekit_starter(transport, starter_source):
    """The whole point of the port is that it runs the same models."""
    pipeline, _ = agent.build_pipeline(transport)
    stt = stage_of(pipeline, LiveKitInferenceSTTService)
    tts = stage_of(pipeline, LiveKitInferenceTTSService)
    llm = stage_of(pipeline, LiveKitInferenceLLMService)

    (starter_llm,) = re.findall(r'inference\.LLM\(model="([^"]+)"', starter_source)
    (starter_stt,) = re.findall(r'inference\.STT\(\s*model="([^"]+)"', starter_source)
    (starter_tts, starter_voice) = re.findall(
        r'inference\.TTS\(\s*model="([^"]+)",\s*voice="([^"]+)"', starter_source
    )[0]

    assert llm._settings.model == starter_llm
    assert stt._settings.model == starter_stt
    assert tts._settings.model == starter_tts
    assert tts._settings.voice == starter_voice


def test_stt_language_matches_the_livekit_starter(transport, starter_source):
    pipeline, _ = agent.build_pipeline(transport)
    stt = stage_of(pipeline, LiveKitInferenceSTTService)

    (starter_language,) = re.findall(
        r'inference\.STT\([^)]*language="([^"]+)"', starter_source
    )

    assert stt._settings.language == starter_language


def test_instructions_match_the_livekit_starter(starter_source):
    """A drifted prompt is the least visible way for the two agents to diverge."""
    match = re.search(
        r'instructions=textwrap\.dedent\(\s*"""\\\n(.*?)"""', starter_source, re.DOTALL
    )
    assert match, "could not locate the instructions block in the starter agent"

    starter_instructions = textwrap.dedent(match.group(1))

    assert starter_instructions.strip() == agent.INSTRUCTIONS.strip()


def test_sample_rates_are_ones_livekit_inference_accepts():
    low, high = STT_SAMPLE_RATE_RANGE
    assert low <= agent.AUDIO_IN_SAMPLE_RATE <= high
    assert agent.AUDIO_OUT_SAMPLE_RATE in TTS_VALID_SAMPLE_RATES


def test_agent_joins_the_room_as_an_agent_participant():
    """Frontends find the agent by participant kind, which LiveKit takes from this claim.

    The `agent` video grant alone leaves the participant kind as STANDARD, which
    is what Pipecat's own runner produces.
    """
    claims = jwt.decode(
        agent.agent_room_token("some-room"), SECRET, algorithms=["HS256"]
    )

    assert claims["kind"] == "agent"
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["room"] == "some-room"
    assert claims["video"]["agent"] is True
