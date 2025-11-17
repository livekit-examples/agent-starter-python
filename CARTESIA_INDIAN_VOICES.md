# Cartesia Indian Accent & Hindi/Hinglish Support

## ✅ Confirmed: Cartesia Supports Indian Accents

Based on Cartesia's official documentation and announcements (2024), here's what's available:

### 1. **Hindi Language Support**
- **Language Code**: `hi`
- **Use Case**: Pure Hindi text-to-speech
- **Natural Accent**: Hindi voices naturally have Indian accent when speaking mixed English-Hindi

### 2. **Hinglish Support** (NEW in 2024)
- **What is it**: Native support for mixed Hindi-English conversations
- **Features**:
  - Fluid transitions between English and Hindi
  - Softens English consonants where appropriate
  - Adds Hindi intonation naturally
  - Understands code-switching patterns
- **Deployment**: Special deployments in India for lowest latency (40ms time-to-first-audio)

### 3. **Available Indian Voices**
- **Conversational male voice** - Perfect for sales and customer support (Hinglish)
- **Warm feminine voice** - Smooth Indian accent for storytelling and dialogue
- Multiple Hindi voices available

---

## How to Use Indian Accents in Your Code

### Current Implementation (Already Supports It!)

Your Cartesia provider in `cartesia.py` already supports the `language` parameter:

```python
# Line 84-87 in cartesia.py
bytes_iter = self.client.tts.bytes(
    model_id=model,
    transcript=text,
    voice={"mode": "id", "id": voice_id},
    language=language,  # Already implemented! ✅
    output_format=self.output_format
)
```

### Method 1: Use Hindi Language Code (Recommended)

For Indian accent when speaking Hindi/English mix:

```python
# Update voice config in persona_service.py
voice_config = VoiceConfig(
    provider="cartesia",
    voice_id="hinglish-male-voice-id",  # Get from Cartesia dashboard
    model="sonic-3"
)

# When generating speech, pass language="hi"
audio_data = await self.tts.generate_speech(
    text=text,
    voice_config=voice_config,
    language="hi"  # Use Hindi - gives natural Indian accent
)
```

### Method 2: Use Hinglish-Specific Voices

Cartesia has specific voices designed for Hinglish that automatically handle mixed language:

```python
# These voices are specifically trained for Indian accent
HINGLISH_VOICES = {
    'male': 'hinglish-conversational-male-voice-id',
    'female': 'hinglish-warm-feminine-voice-id'
}

voice_config = VoiceConfig(
    provider="cartesia",
    voice_id=HINGLISH_VOICES['male'],
    model="sonic-3"
)
```

---

## Supported Languages

Cartesia Sonic supports **15 languages** including:
- English (en)
- Hindi (hi) ✅
- French (fr)
- German (de)
- Spanish (es)
- Portuguese (pt)
- Chinese (zh)
- Japanese (ja)
- Italian (it)
- Korean (ko)
- Dutch (nl)
- Polish (pl)
- Russian (ru)
- Swedish (sv)
- Turkish (tr)

---

## Implementation Steps for Your Project

### Step 1: Find Cartesia Voice IDs

Visit Cartesia's voice playground to browse and test Indian voices:
1. Go to: https://cartesia.ai/voices (or your Cartesia dashboard)
2. Filter for Hindi or Hinglish voices
3. Listen to samples
4. Note the voice IDs

### Step 2: Update Voice Configuration

Edit `src/voice_conversation_generator/services/persona_service.py`:

```python
# Around line 75-79 for support agent
support_persona = SupportPersona(
    ...
    voice_config=VoiceConfig(
        provider="cartesia",
        voice_id="your-hinglish-male-voice-id",  # From Cartesia
        model="sonic-3"
    )
)

# Around line 189-196 for customer agents
voice_config = VoiceConfig(
    provider="cartesia",
    voice_id="your-hinglish-female-voice-id",  # From Cartesia
    model="sonic-3"
)
```

### Step 3: (Optional) Modify Cartesia Provider

If you want to default to Hindi language, edit `cartesia.py:40`:

```python
# In __init__ method
self.default_language = config.get('language', 'hi')  # Change from 'en' to 'hi'
```

### Step 4: Generate Conversations

```bash
# Set API key
export CARTESIA_API_KEY=your_key

# Generate with Cartesia (will use Indian voices)
uv run python src/vcg_cli.py generate --tts cartesia --customer angry_insufficient_funds
```

---

## Why Cartesia is Best for Indian Accents

1. **Native Hinglish Support**: Specifically designed for Indian market
2. **Fluid Code-Switching**: Understands when to switch between Hindi and English
3. **Natural Intonation**: Proper Hindi intonation and English consonant softening
4. **Low Latency**: Deployments in India for 40ms time-to-first-audio
5. **Multiple Voices**: Various male/female voices with authentic Indian accents
6. **Recent Launch**: 2024 launch shows active development for Indian market

---

## Summary

**✅ YES - Cartesia fully supports Indian accents through:**
1. Hindi language code (`language="hi"`)
2. Dedicated Hinglish voices (specific voice IDs)
3. Natural code-switching between Hindi and English
4. Authentic Indian intonation and pronunciation

**Your current implementation already has the infrastructure:**
- Language parameter support in `cartesia.py:84-87`
- Voice configuration system in place
- Just need to set the right voice IDs from Cartesia

**Next Steps:**
1. Visit Cartesia dashboard and get Hindi/Hinglish voice IDs
2. Update voice configurations in `persona_service.py`
3. Test with: `uv run python src/vcg_cli.py generate --tts cartesia`

---

## Additional Resources

- Cartesia India Page: https://cartesia.ai/india
- Cartesia Hindi Voices: https://cartesia.ai/languages/hindi
- Python SDK Docs: https://docs.cartesia.ai/use-an-sdk/python
- Voice Playground: https://cartesia.ai/voices (check for latest voice IDs)
