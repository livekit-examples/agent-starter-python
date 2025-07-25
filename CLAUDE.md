# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with LiveKit Agent projects in Python.

## Project Overview

This covers multimodal AI agent development with LiveKit Agents, a realtime framework for production-grade voice, text, and vision AI agents. While this guide focuses on Python development, LiveKit also supports Node.js (beta). The concepts and patterns described here apply to building, extending, and improving LiveKit-based conversational AI agents across multiple platforms and use cases.

## Development Commands

### Environment Setup
- `uv sync` - Install dependencies to virtual environment
- `uv sync --dev` - Install dependencies including dev tools (pytest, ruff)
- Copy `.env.example` to `.env` and configure API keys
- `lk app env -w .env` - Auto-load LiveKit environment using CLI

### Running Agents
- `uv run python <agent_file> download-files` - Download required models (Silero VAD, LiveKit turn detector) before first run
- `uv run python <agent_file> console` - Run agent in terminal for direct interaction
- `uv run python <agent_file> dev` - Run agent for frontend/telephony integration
- `uv run python <agent_file> start` - Production mode

### Code Quality
- `uv run ruff check .` - Run linter
- `uv run ruff format .` - Format code
- `uv run ruff check --output-format=github .` - Lint with GitHub Actions format
- `uv run ruff format --check --diff .` - Check formatting without applying changes

### Testing
- `uv run pytest` - Run full test suite including evaluations
- `uv run pytest <test_file>::<test_function>` - Run specific test

## Architecture Concepts

### Core Components
- **Agent Implementation** - Main agent class inheriting from `Agent` base class
- **Agent Instructions** - System prompts and behavior definitions for the conversational AI
- **Function Tools** - Methods decorated with `@function_tool` that extend agent capabilities
- **Entrypoint Function** - Sets up the voice AI pipeline with STT/LLM/TTS components

### Multimodal AI Pipeline Architecture
LiveKit agents use a modular pipeline approach with swappable components:
- **STT (Speech-to-Text)**: Converts audio input to text transcripts
- **LLM (Large Language Model)**: Processes conversations, text, and vision inputs to generate responses
- **TTS (Text-to-Speech)**: Converts text responses back to synthesized speech
- **Vision Processing**: Handles image and video understanding for multimodal interactions
- **Turn Detection**: Determines when users finish speaking for natural conversation flow
- **VAD (Voice Activity Detection)**: Detects when users are speaking vs silent
- **Background Audio Handling**: Manages background audio and interruption scenarios
- **Interrupt Management**: Handles conversation interruptions and context switching
- **Noise Cancellation**: Optional audio enhancement (LiveKit Cloud BVC or self-hosted alternatives)
- **Real-time Audio/Video Processing**: Low-latency multimedia stream handling

### Testing Framework Concepts
LiveKit Agents provide evaluation-based testing:
- **AgentSession**: Test harness that simulates real conversations with LLM interactions
- **LLM-based Evaluation**: `.judge()` method evaluates agent responses against intent descriptions
- **Mock Tools**: Enable testing of error conditions and external integrations
- **End-to-End Testing**: Full conversation flow validation with real AI providers

### Configuration Patterns
- **Environment Variables**: Store API keys and configuration separately from code
- **Provider Abstraction**: Swap AI providers without changing core agent logic
- **Modular Setup**: Configure pipeline components independently in entrypoint functions

### Function Tools Pattern
Functions decorated with `@function_tool` extend agent capabilities:
- **Async Methods**: All tools are async methods on the Agent class
- **Structured Documentation**: Docstrings provide tool descriptions and argument specifications for LLM understanding
- **External Integration**: Connect agents to APIs, databases, computations, and other services
- **Natural Language Interface**: LLM decides when and how to use tools based on conversation context

### Metrics and Observability
- **Automatic Metrics Collection**: Built-in tracking of STT/LLM/TTS performance and usage
- **Event-Driven Logging**: `MetricsCollectedEvent` handlers for custom analytics
- **Usage Summaries**: Session-level statistics and resource consumption tracking
- **Contextual Logging**: Room and session context automatically included in log entries

## Key Development Patterns

### Agent Customization Approach
To modify agent behavior:
1. **Update Instructions**: Modify system prompts and behavioral guidelines
2. **Add Function Tools**: Implement `@function_tool` methods for custom capabilities  
3. **Swap AI Providers**: Configure different STT/LLM/TTS providers in session setup
4. **Configure Pipeline**: Adjust turn detection, VAD, and audio processing settings

### Testing Strategy
1. **Unit Testing**: Test individual agent functions and tool behavior
2. **LLM Evaluation**: Use `.judge()` evaluations for response quality assessment
3. **Mock External Dependencies**: Test error conditions with `mock_tools()`
4. **Conversation Testing**: Validate full dialogue flows and user experience

### Deployment Considerations
- **Production Readiness**: Container support with Dockerfile patterns
- **Dependency Management**: Use `uv` for reproducible Python environments
- **CI/CD Integration**: Automated linting, formatting, and testing workflows
- **Environment Configuration**: Secure API key management and environment-specific settings

## LiveKit Documentation & Examples

The LiveKit documentation is comprehensive and provides detailed guidance for all aspects of agent development. **All documentation URLs support `.md` suffix for markdown format** and the docs follow the **llms.txt standard** for AI-friendly consumption.

**Core Documentation**: https://docs.livekit.io/agents/
- **Quick Start**: https://docs.livekit.io/agents/start/voice-ai/
- **Building Agents**: https://docs.livekit.io/agents/build/
- **Integrations**: https://docs.livekit.io/agents/integrations/
- **Operations & Deployment**: https://docs.livekit.io/agents/ops/

**Practical Examples Repository**: https://github.com/livekit-examples/python-agents-examples
- Contains dozens of real-world agent implementations
- Advanced patterns and use cases beyond starter templates
- Integration examples with various AI providers and tools
- Production-ready code samples

## AI Provider Integration Patterns

### LLM Provider Abstraction ([docs](https://docs.livekit.io/agents/integrations/llm/))
All LLM providers follow consistent interfaces for easy swapping:
- **OpenAI**: `openai.LLM(model="gpt-4o-mini")` ([docs](https://docs.livekit.io/agents/integrations/llm/openai/))
- **Anthropic**: `anthropic.LLM(model="claude-3-haiku")` ([docs](https://docs.livekit.io/agents/integrations/llm/anthropic/))
- **Google Gemini**: `google.LLM(model="gemini-1.5-flash")` ([docs](https://docs.livekit.io/agents/integrations/llm/google/))
- **Azure OpenAI**: `azure_openai.LLM(model="gpt-4o")` ([docs](https://docs.livekit.io/agents/integrations/llm/azure-openai/))
- **Groq**: `groq.LLM()` ([docs](https://docs.livekit.io/agents/integrations/llm/groq/))
- **Fireworks**: `fireworks.LLM()` ([docs](https://docs.livekit.io/agents/integrations/llm/fireworks/))
- **DeepSeek**: `deepseek.LLM()` ([docs](https://docs.livekit.io/agents/integrations/llm/deepseek/))
- **Cerebras**: `cerebras.LLM()` ([docs](https://docs.livekit.io/agents/integrations/llm/cerebras/))
- **Amazon Bedrock**: `bedrock.LLM()` ([docs](https://docs.livekit.io/agents/integrations/llm/bedrock/))
- **And others**: Additional providers regularly added

### STT Provider Options ([docs](https://docs.livekit.io/agents/integrations/stt/))
All support low-latency multilingual transcription:
- **Deepgram**: `deepgram.STT(model="nova-3", language="multi")` ([docs](https://docs.livekit.io/agents/integrations/stt/deepgram/))
- **AssemblyAI**: `assemblyai.STT()` ([docs](https://docs.livekit.io/agents/integrations/stt/assemblyai/))
- **Azure AI Speech**: `azure_ai_speech.STT()` ([docs](https://docs.livekit.io/agents/integrations/stt/azure-ai-speech/))
- **Google Cloud**: `google.STT()` ([docs](https://docs.livekit.io/agents/integrations/stt/google/))
- **OpenAI**: `openai.STT()` ([docs](https://docs.livekit.io/agents/integrations/stt/openai/))

### TTS Provider Selection ([docs](https://docs.livekit.io/agents/integrations/tts/))
High-quality, low-latency voice synthesis options:
- **Cartesia**: `cartesia.TTS(model="sonic-english")` ([docs](https://docs.livekit.io/agents/integrations/tts/cartesia/))
- **ElevenLabs**: `elevenlabs.TTS()` ([docs](https://docs.livekit.io/agents/integrations/tts/elevenlabs/))
- **Azure AI Speech**: `azure_ai_speech.TTS()` ([docs](https://docs.livekit.io/agents/integrations/tts/azure-ai-speech/))
- **Amazon Polly**: `polly.TTS()` ([docs](https://docs.livekit.io/agents/integrations/tts/polly/))
- **Google Cloud**: `google.TTS()` ([docs](https://docs.livekit.io/agents/integrations/tts/google/))

## Alternative Pipeline Architectures

### OpenAI Realtime API Integration ([docs](https://docs.livekit.io/agents/integrations/realtime/openai))
Replace entire STT-LLM-TTS pipeline with single provider:
```python
session = AgentSession(
    llm=openai.realtime.RealtimeModel(
        model="gpt-4o-realtime-preview",
        voice="alloy",
        temperature=0.8,
    )
)
```
- **Built-in VAD**: Server or semantic turn detection modes
- **Lower Latency**: Single-provider processing reduces round-trip time
- **Unified Processing**: Supports both audio and text processing in one model

### Advanced Turn Detection ([docs](https://docs.livekit.io/agents/build/turns/turn-detector/))
**LiveKit Turn Detector Models**:
- **English Model**: `EnglishModel()` (66MB, ~15-45ms per turn)
- **Multilingual Model**: `MultilingualModel()` (281MB, ~50-160ms, 14 languages)
- **Enhanced Context**: Adds conversational understanding to VAD for better end-of-turn detection

## Function Tools and Capability Extension

### Tool Implementation Patterns
Functions decorated with `@function_tool` become available to the LLM:
```python
@function_tool
async def external_integration(self, context: RunContext, parameter: str):
    """Description of what this tool does for the LLM.
    
    Args:
        parameter: Clear description for LLM understanding
    """
    # Implementation logic (APIs, databases, computations, etc.)
    return "structured result or simple string"
```

### Best Practices for Tool Development
- **Async Implementation**: All tools should be async methods
- **Clear Documentation**: Docstrings guide LLM understanding and usage
- **Error Handling**: Graceful failure with informative error messages
- **Simple Returns**: Return strings or simple structured data
- **External Integration**: Connect to APIs, databases, or other services
- **Contextual Logging**: Use `logger.info()` for debugging and monitoring

## Testing and Evaluation Strategies ([docs](https://docs.livekit.io/agents/build/testing/))

### LLM-Based Test Evaluation
Use LiveKit's evaluation framework for intelligent testing:
```python
@pytest.mark.asyncio
async def test_agent_capability():
    async with AgentSession(llm=openai.LLM()) as session:
        await session.start(YourAgent())
        result = await session.run(user_input="Test query")
        
        await result.expect.next_event().is_message(role="assistant").judge(
            llm, intent="Description of expected behavior"
        )
```

### Mock Tool Testing Patterns
Test error conditions and edge cases:
```python
with mock_tools(YourAgent, {"tool_name": lambda: "mocked_response"}):
    result = await session.run(user_input="test input")
```

### Comprehensive Test Categories
- **Core Functionality**: Primary agent capabilities work correctly
- **Tool Integration**: Function calls with proper arguments and responses
- **Error Scenarios**: Graceful handling of failures and edge cases
- **Information Accuracy**: Factual grounding and admission of limitations
- **Safety & Ethics**: Appropriate refusal of inappropriate requests

## Metrics and Performance Monitoring ([docs](https://docs.livekit.io/agents/build/metrics/))

### Automatic Metrics Collection
Built-in tracking includes:
- **STT Performance**: Audio duration, transcript timing, streaming efficiency
- **LLM Metrics**: Response time, token usage, time-to-first-token (TTFT)
- **TTS Efficiency**: Audio generation time, character processing, output duration

### Custom Metrics Implementation
```python
@session.on("metrics_collected")
def handle_metrics(ev: MetricsCollectedEvent):
    # Process built-in metrics
    metrics.log_metrics(ev.metrics)
    # Add custom analytics
    custom_tracker.record(ev.metrics)
```

### Usage Analytics Patterns
```python
usage_collector = metrics.UsageCollector()
# Collect metrics throughout session lifecycle
final_summary = usage_collector.get_summary()  # Session statistics
```

## Frontend Integration Strategies ([docs](https://docs.livekit.io/agents/start/frontend/))

### Ready-to-Use Starter Templates
Complete application templates with full source code:
- **Web Applications**: React/Next.js implementations
- **Mobile Apps**: iOS/Swift, Android/Kotlin, Flutter, React Native
- **Embedded Solutions**: Web widget and iframe integrations

### Custom Frontend Development Patterns
- **LiveKit SDK Integration**: Use platform-specific SDKs for real-time connectivity
- **Audio/Video Streaming**: Subscribe to agent tracks and transcription streams
- **WebRTC Implementation**: Handle real-time communication protocols with NAT traversal
- **Enhanced UX Features**: 
  - Audio visualizers and waveform displays
  - Virtual avatars and character animations
  - Custom UI controls and interaction patterns
  - Real-time transcription overlays
  - Visual feedback for agent processing states
  - Interactive chat interfaces alongside voice
- **Cross-Platform Support**: Consistent experience across web, mobile, and desktop

## Workflow Modeling and Advanced Features

### Workflow Modeling ([docs](https://docs.livekit.io/agents/build/workflows/))
LiveKit supports sophisticated workflow modeling for complex agent behaviors:
- **State Management**: Define agent states and transitions
- **Conditional Logic**: Implement branching conversation flows
- **Context Preservation**: Maintain conversation context across workflow steps
- **Error Recovery**: Handle failures and provide graceful fallbacks
- **Multi-Step Processes**: Guide users through complex tasks

### Background Processing Capabilities
- **Background Audio Handling**: Process audio while maintaining conversation flow
- **Parallel Task Execution**: Handle multiple operations simultaneously
- **Context Switching**: Seamlessly transition between different conversation topics
- **Asynchronous Operations**: Non-blocking external API calls and computations

## Advanced Integration Capabilities

### Telephony Integration ([docs](https://docs.livekit.io/agents/start/telephony/))
Add voice calling capabilities with SIP integration:
- **Inbound/Outbound Calling**: Handle phone-based interactions
- **SIP Protocol Support**: Industry-standard telephony integration
- **Call Management**: Handle call routing, transfers, and conferencing
- **Phone Number Provisioning**: Manage virtual phone numbers for agents

### Production Deployment ([docs](https://docs.livekit.io/agents/ops/deployment/))
- **LiveKit Cloud**: Managed hosting with enterprise features
- **Self-Hosting**: Container-based deployment with provided Docker configurations
- **Kubernetes Support**: Production-grade orchestration and scaling
- **Scaling Strategies**: Handle multiple concurrent sessions and load balancing
- **Security Configuration**: API key management and access control
- **High Availability**: Multi-region deployment and failover capabilities

### Environment Configuration Standards
Required environment variables for different provider integrations:
- **Core LiveKit**: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- **AI Providers**: Provider-specific API keys (e.g., `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`)
- **Configuration Management**: Use `.env` files and secure secret management