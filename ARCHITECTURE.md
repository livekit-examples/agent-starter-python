# Voice Conversation Generator - Architecture

Clean, modular architecture for generating synthetic customer support conversations.

## Core Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Interface                         │
│                    (vcg_cli.py)                         │
├─────────────────────────────────────────────────────────┤
│                 Core Services Layer                      │
├─────────────────────────────────────────────────────────┤
│  ConversationOrchestrator │ PersonaService │ Factory    │
├─────────────────────────────────────────────────────────┤
│                   Domain Models                          │
├─────────────────────────────────────────────────────────┤
│    Persona    │    Conversation    │    Metrics         │
├─────────────────────────────────────────────────────────┤
│              Provider Abstraction Layer                  │
├─────────────────────────────────────────────────────────┤
│  LLMProvider  │  TTSProvider  │  StorageGateway        │
├─────────────────────────────────────────────────────────┤
│              Provider Implementations                    │
├─────────────────────────────────────────────────────────┤
│ OpenAI │ ElevenLabs │ LocalStorage │ (Future: GCS, S3) │
└─────────────────────────────────────────────────────────┘
```

## Directory Structure

```
src/
├── vcg_cli.py                    # CLI entry point
└── voice_conversation_generator/
    ├── config/
    │   └── config.py             # Configuration management
    ├── models/
    │   ├── persona.py            # Persona models
    │   ├── conversation.py       # Conversation & Turn models
    │   └── metrics.py            # Metrics tracking
    ├── providers/
    │   ├── base.py              # Abstract base classes
    │   ├── llm/
    │   │   └── openai.py        # OpenAI LLM
    │   ├── tts/
    │   │   ├── openai.py        # OpenAI TTS
    │   │   └── elevenlabs.py   # ElevenLabs TTS
    │   └── storage/
    │       └── local.py         # Local file storage
    └── services/
        ├── orchestrator.py       # Conversation orchestration
        ├── persona_service.py    # Persona management
        └── provider_factory.py   # Provider creation
```

## Key Design Patterns

### 1. Provider Pattern
Abstract interfaces with swappable implementations:

```python
class TTSProvider(ABC):
    @abstractmethod
    async def generate_speech(text, voice_config) -> bytes:
        pass
```

### 2. Storage Gateway
Unified interface for file storage:

```python
class StorageGateway(ABC):
    @abstractmethod
    async def save_conversation(conversation, metrics) -> Dict:
        pass
```

### 3. Dependency Injection
Services receive dependencies through constructor:

```python
orchestrator = ConversationOrchestrator(
    llm_provider=llm,
    tts_provider=tts,
    storage_gateway=storage
)
```

## Data Flow

1. **CLI** receives user command
2. **PersonaService** loads customer/support personas
3. **ProviderFactory** creates providers from config
4. **ConversationOrchestrator** manages the flow:
   - Generates text via LLMProvider
   - Converts to speech via TTSProvider
   - Tracks metrics
5. **StorageGateway** saves all artifacts

## Configuration

Layered configuration with environment overrides:

```yaml
# config.yaml
providers:
  llm:
    type: "openai"
    model: "gpt-4"
  tts:
    type: "elevenlabs"
storage:
  type: "local"
  local:
    base_path: "data/conversations"
```

Environment variables override file config:
- `LLM_PROVIDER`, `LLM_MODEL`
- `TTS_PROVIDER`
- `STORAGE_TYPE`

## Extension Points

### Adding New Providers

1. Create provider class implementing abstract interface
2. Register in `ProviderFactory`
3. Update configuration

Example:
```python
# providers/llm/anthropic.py
class AnthropicLLMProvider(LLMProvider):
    async def generate_completion(...):
        # Implementation
```

### Database Integration

Future support for PostgreSQL:
- Persona storage and retrieval
- Conversation history
- Analytics queries

### Cloud Deployment

Ready for:
- **FastAPI**: REST endpoints
- **Docker**: Container deployment
- **Cloud Storage**: GCS/S3 support
- **LiveKit**: Real-time simulation

## Benefits

- **Modularity**: Single responsibility per component
- **Testability**: Easy mocking and isolation
- **Extensibility**: Add providers without core changes
- **Maintainability**: Clear separation of concerns
- **Scalability**: Cloud-ready architecture