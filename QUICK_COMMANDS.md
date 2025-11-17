# Quick Command Reference

## Generate Conversations

### Basic
```bash
# Default (OpenAI TTS, cooperative customer, 10 turns)
uv run python src/vcg_cli.py generate

# With OpenAI TTS
uv run python src/vcg_cli.py generate --tts openai

# With ElevenLabs TTS
uv run python src/vcg_cli.py generate --tts elevenlabs

# With Cartesia TTS (best for Indian voices)
uv run python src/vcg_cli.py generate --tts cartesia
```

### Customer Personas
```bash
# Cooperative parent
uv run python src/vcg_cli.py generate --customer cooperative_parent

# Angry about insufficient funds
uv run python src/vcg_cli.py generate --customer angry_insufficient_funds

# Confused elderly Hindi speaker
uv run python src/vcg_cli.py generate --customer confused_elderly_hindi

# Financial hardship
uv run python src/vcg_cli.py generate --customer financial_hardship

# Call back later (busy)
uv run python src/vcg_cli.py generate --customer call_back_later

# Wrong person (wife answers)
uv run python src/vcg_cli.py generate --customer wrong_person_family

# Payment confusion (claims already paid)
uv run python src/vcg_cli.py generate --customer already_paid_confusion

# Wants to cancel
uv run python src/vcg_cli.py generate --customer payment_cancellation_attempt
```

### Combined Options
```bash
# Angry customer, Cartesia TTS, 6 turns
uv run python src/vcg_cli.py generate \
  --customer angry_insufficient_funds \
  --tts cartesia \
  --max-turns 6

# Elderly confused, ElevenLabs, 8 turns
uv run python src/vcg_cli.py generate \
  --customer confused_elderly_hindi \
  --tts elevenlabs \
  --max-turns 8

# Financial hardship, OpenAI, don't save
uv run python src/vcg_cli.py generate \
  --customer financial_hardship \
  --tts openai \
  --no-save
```

## View Data

```bash
# List all customer personas
uv run python src/vcg_cli.py list-personas --type customer

# List support personas
uv run python src/vcg_cli.py list-personas --type support

# Show current configuration
uv run python src/vcg_cli.py show-config

# List generated conversations
uv run python src/vcg_cli.py list-conversations
```

## Environment Variables

```bash
# Set API keys
export OPENAI_API_KEY=sk-...
export ELEVENLABS_API_KEY=...
export CARTESIA_API_KEY=...

# Change LLM model
export LLM_MODEL=gpt-4.1

# Change default TTS provider
export TTS_PROVIDER=cartesia
```

## Best for Indian Voices

```bash
# Use Cartesia (supports Hindi natively)
uv run python src/vcg_cli.py generate \
  --customer angry_insufficient_funds \
  --tts cartesia \
  --max-turns 5
```
