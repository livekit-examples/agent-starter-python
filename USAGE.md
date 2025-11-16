# Voice Conversation Generator - Quick Start Guide

Generate realistic customer support conversations with AI-powered voices.

## Setup

### 1. Install Dependencies
```bash
# If not already installed
pip install uv
uv sync
```

### 2. Configure API Keys
Create `.env.local` in project root:
```bash
OPENAI_API_KEY=your_openai_key
ELEVENLABS_API_KEY=your_elevenlabs_key  # Optional
```

## Basic Usage

### Generate a Conversation
```bash
# Simple generation with defaults
uv run python src/vcg_cli.py generate

# Specify customer persona and TTS provider
uv run python src/vcg_cli.py generate \
  --customer angry_insufficient_funds \
  --tts elevenlabs \
  --max-turns 6
```

### View Available Personas
```bash
uv run python src/vcg_cli.py list-personas
```

**Customer Personas:**
- `cooperative_parent` - Understanding parent, easy resolution
- `angry_insufficient_funds` - Frustrated about payment issues
- `confused_elderly_hindi` - Elderly, limited tech understanding
- `financial_hardship` - Needs payment plan
- `call_back_later` - Busy, needs callback

### List Generated Conversations
```bash
uv run python src/vcg_cli.py list-conversations
```

## File Storage

Generated conversations are saved in:
```
data/conversations/
├── audio/         # MP3 files
├── transcripts/   # JSON transcripts
└── metrics/       # Performance data
```

## Configuration Options

### TTS Providers
- `openai` - Fast, reliable (default)
- `elevenlabs` - More realistic voices

### Advanced Settings
Create `config.yaml` for custom settings:
```yaml
providers:
  llm:
    type: "openai"
    model: "gpt-4"
  tts:
    type: "openai"
    default_voice: "onyx"
```

## Programmatic Usage

```python
import asyncio
from voice_conversation_generator.config.config import Config
from voice_conversation_generator.services import (
    ProviderFactory,
    PersonaService,
    ConversationOrchestrator
)

async def main():
    # Load config and personas
    config = Config.load()
    persona_service = PersonaService()
    persona_service.load_default_personas()

    # Get personas
    customer = persona_service.get_customer_persona("cooperative_parent")
    support = persona_service.get_support_persona("default")

    # Create orchestrator
    providers = ProviderFactory.create_all_providers(config)
    orchestrator = ConversationOrchestrator(**providers)

    # Generate and save
    conversation, metrics = await orchestrator.generate_conversation(
        customer, support
    )
    await orchestrator.save_conversation(conversation, metrics)

asyncio.run(main())
```

## Extending the System

### Add Custom Persona
```python
from voice_conversation_generator.models import CustomerPersona, EmotionalState

persona = CustomerPersona(
    name="John Doe",
    personality="Technical professional",
    emotional_state=EmotionalState.NEUTRAL,
    issue="Service outage"
)
persona_service.add_customer_persona(persona)
```

## Architecture Overview

- **Models**: Domain objects (Persona, Conversation, Metrics)
- **Providers**: Pluggable LLM/TTS/Storage implementations
- **Services**: Business logic (Orchestrator, PersonaService)
- **Config**: YAML + environment variable configuration

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design.