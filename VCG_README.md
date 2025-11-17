# Voice Conversation Generator

A clean, modular system for generating synthetic customer support conversations with AI voices.

## Quick Start

```bash
# Setup
echo "OPENAI_API_KEY=your_key" > .env.local

# Generate a conversation
uv run python src/vcg_cli.py generate

# List personas
uv run python src/vcg_cli.py list-personas

# View saved conversations
uv run python src/vcg_cli.py list-conversations
```

## Features

✨ **Multiple Customer Personas** - 8 realistic scenarios from cooperative to angry customers
🎭 **Configurable Voices** - OpenAI and ElevenLabs TTS support
📊 **Performance Metrics** - Track latency, interruptions, resolution rates
💾 **Organized Storage** - Clean file structure for audio, transcripts, and metrics
🔌 **Extensible Design** - Easy to add new LLM/TTS providers

## Project Structure

```
src/
├── vcg_cli.py                    # CLI interface
└── voice_conversation_generator/ # Core module
    ├── models/                   # Domain objects
    ├── providers/                # LLM/TTS/Storage
    ├── services/                 # Business logic
    └── config/                   # Configuration
```

## Documentation

- [USAGE.md](USAGE.md) - Complete usage guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical architecture

## Key Files

- **vcg_cli.py** - Command-line interface
- **data/conversations/** - Generated conversations
- **.env.local** - API keys configuration