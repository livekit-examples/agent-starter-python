# ElevenLabs Integration Guide for Indian Voice Agents

## Executive Summary

ElevenLabs provides superior voice synthesis with:
- **Voice Cloning**: Create custom Indian voices with 1-minute audio samples
- **Multilingual Support**: Hindi + 31 other languages with the same voice
- **Ultra-Low Latency**: ~75ms with Flash v2.5 model
- **Emotion Control**: Natural emotional expression through text cues
- **32 kHz High-Quality Audio**: Professional-grade output

## Why ElevenLabs for Acme's Indian Call Center

### Key Advantages
1. **Authentic Indian Accents**: Clone actual Indian support agents' voices
2. **Hindi-English Code-Mixing**: Seamless language switching in same voice
3. **Regional Accent Support**: Different Indian regional accents possible
4. **Real-Time Streaming**: Essential for live agent conversations
5. **SOC2/GDPR Compliant**: Enterprise-ready security

### Comparison with OpenAI TTS
| Feature | OpenAI TTS | ElevenLabs |
|---------|------------|------------|
| Indian Accents | Generic only | Custom cloneable |
| Hindi Support | Limited | Full support |
| Voice Cloning | No | Yes (1 min sample) |
| Latency | ~200ms | ~75ms |
| Emotion Control | Basic | Advanced |
| Price per 1M chars | $15 | $99 (Creator plan) |

## Implementation Plan

### Phase 1: Quick Demo (1-2 hours)
```python
# Install
pip install elevenlabs python-dotenv

# Basic implementation
from elevenlabs import ElevenLabs, save

client = ElevenLabs(api_key="YOUR_KEY")

# Use pre-made Indian voice from library
audio = client.text_to_speech.convert(
    text="Namaste, main Faizan bol raha hun Jodo se",
    voice_id="indian_voice_id",  # Use existing Indian voice
    model_id="eleven_multilingual_v2"
)

save(audio, "output.mp3")
```

### Phase 2: Custom Voice Cloning (4-6 hours)
1. **Record Sample Audio**
   - Get 1-3 minute clear recording of Indian support agent
   - Male voice saying: "Hello, this is Faizan from Jodo..."
   - Female customer voices with different personalities

2. **Clone Voices**
   ```python
   # Upload and clone
   voice = client.voices.clone(
       name="Faizan_Jodo_Support",
       files=["faizan_sample.mp3"],
       description="Male Indian support agent, professional"
   )
   ```

3. **Create Voice Library**
   - Support Agent: Male, professional Hindi-English
   - Angry Customer: Female, frustrated tone
   - Elderly Customer: Male, confused, heavy Hindi
   - Young Professional: Female, English-dominant

### Phase 3: Integration with Test Framework

```python
# src/elevenlabs_voices.py
from elevenlabs import ElevenLabs, VoiceSettings
import os

class IndianVoiceGenerator:
    def __init__(self):
        self.client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

        # Voice IDs for different personas
        self.voices = {
            "support_male": "cloned_faizan_id",
            "customer_angry": "cloned_angry_female_id",
            "customer_elderly": "cloned_elderly_male_id",
            "customer_professional": "cloned_professional_female_id"
        }

    async def generate_speech(self, text: str, persona: str, emotion: str = "neutral"):
        voice_id = self.voices.get(persona, self.voices["support_male"])

        # Adjust settings based on emotion
        settings = VoiceSettings(
            stability=0.7 if emotion == "angry" else 0.5,
            similarity_boost=0.8,
            style=0.5,  # Natural conversational style
            use_speaker_boost=True
        )

        audio = await self.client.text_to_speech.convert_async(
            text=text,
            voice_id=voice_id,
            model_id="eleven_turbo_v2_5",  # Fast for real-time
            voice_settings=settings,
            output_format="mp3_44100_128"
        )

        return audio
```

### Phase 4: Enhanced Conversation Simulator

```python
# Update conversation_simulator.py
async def _add_turn(self, speaker: str, text: str):
    """Add turn with ElevenLabs voices"""

    # Determine persona based on speaker and scenario
    if speaker == "support":
        persona = "support_male"
        emotion = "professional"
    else:
        # Map customer scenarios to voices
        if "angry" in self.scenario['name']:
            persona = "customer_angry"
            emotion = "frustrated"
        elif "elderly" in self.scenario['name']:
            persona = "customer_elderly"
            emotion = "confused"
        else:
            persona = "customer_professional"
            emotion = self.scenario.get('emotional_state', 'neutral')

    # Generate with ElevenLabs
    voice_gen = IndianVoiceGenerator()
    audio = await voice_gen.generate_speech(text, persona, emotion)

    # Save audio segment
    self.audio_segments.append({
        "speaker": speaker,
        "audio_data": audio,
        "text": text
    })
```

## Pricing Analysis for Acme

### Development Phase (Creator Plan - $99/month)
- 500,000 characters (~500 minutes)
- 10 custom voice clones
- Sufficient for testing and demos

### Production Estimates
- Average call: 5 minutes = 5,000 characters
- 1,000 test calls/month = 5M characters
- **Recommended: Pro Plan ($330/month)**
  - 2M characters included
  - Additional at $0.18 per 1,000 chars
  - Professional voice cloning

### ROI Justification
- Reduce human QA time by 80%
- Test 100x more scenarios
- Catch edge cases before production
- Improve agent prompt quality faster

## Quick Start Commands

```bash
# 1. Install dependencies
uv add elevenlabs

# 2. Set API key
export ELEVENLABS_API_KEY="your_key_here"

# 3. Test basic TTS
uv run python -c "
from elevenlabs import generate, save
audio = generate(text='Namaste, main aapki kya madad kar sakta hun?', voice='Adam')
save(audio, 'test_hindi.mp3')
print('Generated test_hindi.mp3')
"

# 4. Run enhanced simulator
uv run python src/conversation_simulator.py cooperative_parent
```

## Key Insights for Demo

1. **Latency Advantage**: Show side-by-side comparison of OpenAI (200ms) vs ElevenLabs (75ms)
2. **Voice Consistency**: Same cloned voice speaking both Hindi and English naturally
3. **Emotional Range**: Demonstrate same voice with different emotions (angry, confused, happy)
4. **Regional Accents**: Show Bengali vs Punjabi vs South Indian accent variations
5. **Cost Efficiency**: $99/month for unlimited testing vs hiring voice actors

## Next Steps

1. Get ElevenLabs API key (free tier available)
2. Record 1-minute sample of Indian support agent
3. Clone voice and test with Jodo scenarios
4. Demo live streaming for real-time conversations
5. Show LiveKit + ElevenLabs integration potential

## Technical Notes

- **Models**: Use `eleven_turbo_v2_5` for speed, `eleven_multilingual_v2` for quality
- **Streaming**: Essential for real-time - use `convert_as_stream()` method
- **Caching**: Cache generated audio for repeated phrases to reduce costs
- **Fallback**: Keep OpenAI TTS as backup if ElevenLabs API fails

This positions Acme's demo as cutting-edge with authentic Indian voices that no competitor can match with generic TTS.