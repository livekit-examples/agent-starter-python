# 🎙️ Quick Start - Voice Conversations

## Generate Your First Conversation (30 seconds)

```bash
# Generate a voice conversation
uv run python src/conversation_simulator.py cooperative_parent
```

This creates:
- **Audio file**: `conversations/YYYYMMDD_HHMMSS_cooperative_parent_conversation.mp3`
- **Transcript**: `conversations/YYYYMMDD_HHMMSS_cooperative_parent_transcript.json`

## Available Scenarios

| Command | Description | Difficulty |
|---------|-------------|------------|
| `cooperative_parent` | Yash agrees to reschedule payment | Easy |
| `angry_insufficient_funds` | Frustrated parent with financial stress | Hard |
| `wrong_person_family` | Wife (Priya) takes message for husband | Medium |
| `confused_elderly_hindi` | Elderly Hindi-English speaker needs clarification | Medium |
| `financial_hardship` | Parent facing genuine financial crisis | Medium |
| `already_paid_confusion` | Claims payment was already made | Medium |
| `payment_cancellation_attempt` | Tries to cancel but gets convinced | Hard |
| `call_back_later` | Busy professional trying to postpone | Easy |

## Examples

```bash
# Angry customer
uv run python src/conversation_simulator.py angry_insufficient_funds

# Hindi-English conversation
uv run python src/conversation_simulator.py confused_elderly_hindi

# Wrong person answers phone
uv run python src/conversation_simulator.py wrong_person_family
```

## Voice Generation (Automatic)

The system automatically chooses the best available voice engine:

1. **ElevenLabs** (if API key exists in `.env.local`)
   - Better quality voices
   - 10,000 free credits = ~10 conversations

2. **OpenAI TTS** (automatic fallback)
   - Always works if OpenAI key is set
   - Generic but reliable voices

**Current behavior:**
- If ElevenLabs API key is set → tries ElevenLabs first
- If ElevenLabs fails → automatically falls back to OpenAI
- If no ElevenLabs key → uses OpenAI directly

## Force a Specific Engine (Optional)

```bash
# Force OpenAI TTS
uv run python src/conversation_simulator.py cooperative_parent --openai

# Force ElevenLabs (requires API key)
uv run python src/conversation_simulator.py cooperative_parent --elevenlabs
```

## Listen to Results

```bash
# Play latest audio (macOS)
open conversations/*.mp3

# List all generated conversations
ls -la conversations/*.mp3
```

## What Gets Generated

Each conversation includes:
- **Support Agent**: फ़ैज़ान (Faizan) from Jodo, male voice
- **Customer**: Various personas (Yash, Priya, etc.)
- **5-15 turns** of realistic dialogue
- **Proper protocol**: Agent greets first, follows Jodo guidelines
- **Hindi-English mixing**: In appropriate scenarios

## Cost

- **ElevenLabs**: Free tier gives 10 conversations
- **OpenAI TTS**: ~$0.015 per conversation

## Troubleshooting

If generation fails:
- Check `.env.local` has `OPENAI_API_KEY` set
- ElevenLabs is optional - system works without it
- Each conversation takes 10-30 seconds to generate

---

**Note**: This generates complete conversations as MP3 files for testing/demos. For real-time agent-to-agent calls via LiveKit, that would require a different setup with two separate agent processes.