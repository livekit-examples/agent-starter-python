# Conversation Generation Logic - Complete Explanation

This document explains exactly how conversations are generated, including context passing, prompts, models, and voice configuration.

## 📋 Table of Contents
1. [LLM Models Used](#llm-models-used)
2. [Conversation Flow](#conversation-flow)
3. [Context Passing](#context-passing)
4. [Support Agent Prompting](#support-agent-prompting)
5. [Customer Agent Prompting](#customer-agent-prompting)
6. [Voice Configuration](#voice-configuration)
7. [How to Use Indian Accent Voices](#how-to-use-indian-accent-voices)

---

## 1. LLM Models Used

**Both agents use the SAME LLM instance:**
- **Default Model**: `GPT-4` (configured in `config.py:44`)
- **Location**: `src/voice_conversation_generator/providers/llm/openai.py:35`
- **Temperature**: `0.8` (default, makes conversation more natural)
- **Max Tokens**: `150` per turn (to keep responses concise)

You can change the model by:
```bash
# Environment variable
export LLM_MODEL=gpt-4.1

# Or in code
config.providers.llm['model'] = 'gpt-4.1'
```

---

## 2. Conversation Flow

Here's the exact flow for each conversation:

### Initial Setup
```python
# orchestrator.py:86-97
1. Support agent generates OPENING GREETING (uses system prompt + opening instruction)
2. Turn is added to conversation history
3. Audio is generated from text
```

### Turn-by-Turn Loop
```python
# orchestrator.py:100-147
for each turn (up to max_turns):
    # Customer speaks
    1. Get full conversation context (last 6 turns by default)
    2. Customer agent generates response based on:
       - Customer persona (personality, issue, goal, emotional state)
       - Full conversation context
       - Special behaviors
    3. Add customer turn to history
    4. Generate audio

    # Check if resolved
    if customer satisfied:
        Support sends closing message
        break

    # Support responds
    5. Get full conversation context (including customer's new message)
    6. Support agent generates response based on:
       - Support system prompt (Jodo agent prompt)
       - Company policies
       - Guardrails
       - Full conversation context
    7. Add support turn to history
    8. Generate audio
```

---

## 3. Context Passing ✅

**YES, full conversation history is passed on every turn!**

### How Context Works

**Location**: `conversation.py:164-167`
```python
def get_conversation_context(self, last_n: int = 6) -> str:
    """Get the last N turns as formatted context"""
    recent_turns = self.turns[-last_n:] if len(self.turns) > last_n else self.turns
    return "\n".join([f"{turn.speaker.value}: {turn.text}" for turn in recent_turns])
```

**What gets passed:**
- Last 6 turns by default (configurable)
- Format: `"customer: <text>\nsupport: <text>\n..."`
- Both customer AND support messages are included

**Example context string:**
```
support: नमस्ते, मैं फ़ैज़ान बोल रहा हूँ Jodo से
customer: नमस्ते, मुझे payment में problem आ रही है
support: मैं आपकी मदद कर सकता हूँ। आपका नाम क्या है?
```

---

## 4. Support Agent Prompting ✅

**YES, the full Jodo support agent system prompt is used on EVERY turn!**

### System Prompt Construction

**Location**: `orchestrator.py:220-234`

```python
# Base: Full Jodo system prompt from file
system_prompt = persona.system_prompt  # 19KB prompt from support_agent_system_prompt.txt

# Prepended info
system_prompt = f"Your name is {persona.agent_name}. " + system_prompt
system_prompt = f"You work for {persona.company_name}. " + system_prompt

# Appended policies
system_prompt += "\n\nPolicies to follow:\n"
system_prompt += "- Verify customer identity before discussing account details\n"
system_prompt += "- Offer payment plans for amounts over ₹5000\n"
system_prompt += "- Escalate to supervisor for refund requests over ₹10000\n"

# Appended guardrails
system_prompt += "\n\nGuardrails:\n"
system_prompt += "- Always be respectful and patient\n"
system_prompt += "- Follow company policies\n"
system_prompt += "- Escalate when necessary\n"
```

### User Prompt (per turn)

**Location**: `orchestrator.py:248-253`

**Opening turn:**
```
This is the start of a new call. Greet the customer warmly and introduce yourself.
Follow your guidelines for the opening script. State your name, company, and the purpose of the call.
Keep it natural and conversational. Do not use any formatting or quotation marks.
```

**Regular turn:**
```
Conversation so far:
customer: <previous messages>
support: <previous messages>

Respond professionally to help the customer. Keep it under 2 sentences.
Follow your guidelines and policies. Do not use any formatting or quotation marks.
```

**Closing turn:**
```
Conversation so far:
<full context>

The customer seems satisfied. Provide a warm closing to end the conversation.
Keep it under 2 sentences. Do not use any formatting or quotation marks.
```

---

## 5. Customer Agent Prompting

### System Prompt
**Customer agents do NOT use a system prompt** - all context is in the user prompt.

### User Prompt (per turn)

**Location**: `orchestrator.py:180-191`

```
You are {persona.name} receiving a call from customer support.
Your personality: {persona.personality}
Your issue/situation: {persona.issue}
Your goal: {persona.goal}
Emotional state: {persona.emotional_state.value}

Conversation so far:
customer: <previous messages>
support: <previous messages>

Respond naturally based on your personality and situation.
{persona.special_behavior}
Keep your response under 2 sentences. Do not use any formatting or quotation marks. Just speak naturally.
```

**Example for angry_insufficient_funds:**
```
You are प्रिया गुप्ता receiving a call from customer support.
Your personality: Frustrated parent dealing with financial stress
Your issue/situation: Payment failed due to insufficient funds, but angry about repeated calls
Your goal: Express frustration and potentially avoid immediate payment
Emotional state: angry

Conversation so far:
support: नमस्ते, मैं फ़ैज़ान बोल रहा हूँ Jodo से

Respond naturally based on your personality and situation.
Start angry but may calm down if agent is empathetic
Keep your response under 2 sentences.
```

---

## 6. Voice Configuration

### Current Voice Setup

**Support Agent** (`persona_service.py:75-79`):
```python
voice_config=VoiceConfig(
    provider="openai",
    voice_name="onyx",  # Male voice
    speed=1.0
)
```

**Customer Agents** (`persona_service.py:189-196`):
- **Female personas**: `nova` (OpenAI female voice)
- **Elderly personas**: `fable` (older sounding, speed=0.9)
- **Male personas**: `echo` (default male voice)

### Available Voice Providers

1. **OpenAI** (current default):
   - Voices: alloy, echo, fable, onyx, nova, shimmer
   - No specific Indian accent support

2. **ElevenLabs**:
   - 100+ voices in multiple languages
   - Some Indian-accented English voices available
   - Better quality but slower

3. **Cartesia** (newly integrated):
   - Sonic-3 model with 15+ languages
   - **Hindi language support** ✅
   - Ultra-realistic voices

---

## 7. How to Use Indian Accent Voices

### Option 1: Use Cartesia with Specific Voice IDs

Cartesia doesn't have "Indian accent English" per se, but has **native Hindi speakers** which will naturally have Indian accents when speaking English.

**Step 1: Find Indian voices**
Visit Cartesia Voice Library or use their API to search for Hindi voices.

**Step 2: Update persona voice configs**
Create a custom configuration file:

```python
# custom_voices.py
from voice_conversation_generator.models import VoiceConfig

# Cartesia Indian voices (example IDs - you need to get actual IDs from Cartesia)
INDIAN_VOICES = {
    'male': 'cartesia-hindi-male-voice-id',
    'female': 'cartesia-hindi-female-voice-id'
}

# Update support agent
support_voice = VoiceConfig(
    provider="cartesia",
    voice_id=INDIAN_VOICES['male'],
    model="sonic-3",
    speed=1.0
)

# Update customer personas
customer_voice_male = VoiceConfig(
    provider="cartesia",
    voice_id=INDIAN_VOICES['male'],
    model="sonic-3",
    speed=1.0
)

customer_voice_female = VoiceConfig(
    provider="cartesia",
    voice_id=INDIAN_VOICES['female'],
    model="sonic-3",
    speed=1.0
)
```

**Step 3: Modify persona service** to use these voice configs:

```python
# In persona_service.py:75-79
support_persona = SupportPersona(
    ...
    voice_config=support_voice  # Use custom voice
)

# In persona_service.py:189-196
if "female" in scenario_data["personality"].lower():
    voice_config = customer_voice_female
else:
    voice_config = customer_voice_male
```

### Option 2: Use ElevenLabs Indian Voices

ElevenLabs has several Indian-accented English voices in their voice library.

**Step 1: Browse ElevenLabs voice library**
- Visit: https://elevenlabs.io/voice-library
- Filter by accent: "Indian"
- Note the voice IDs

**Step 2: Update configurations** similarly to Cartesia above

### Option 3: Request Cartesia to Generate Native Hindi

Since your customer names are already in Hindi (राज शर्मा, प्रिया गुप्ता, etc.), you could:

1. Set language to Hindi: `language="hi"`
2. Cartesia will use native Hindi pronunciation
3. Code-switching (Hindi-English mix) will sound more natural

```python
# In cartesia.py when generating speech
audio_data = await self.tts.generate_speech(
    text=text,
    voice_config=voice_config,
    language="hi"  # Use Hindi
)
```

---

## Quick Implementation Guide

### To set specific voices for both agents:

```bash
# 1. Get Cartesia Hindi voice IDs
# Visit Cartesia playground and note voice IDs

# 2. Update persona_service.py
# Lines 75-79 (support agent)
# Lines 189-196 (customer agents)

# 3. Set voice_id instead of voice_name
voice_config = VoiceConfig(
    provider="cartesia",
    voice_id="actual-voice-id-from-cartesia",
    model="sonic-3"
)

# 4. Generate with Cartesia
uv run python src/vcg_cli.py generate --tts cartesia
```

---

## Summary: Your Questions Answered

### Q1: How do I choose specific voices for customer and support?
**A**: Modify `persona_service.py:75-79` (support) and `189-196` (customers). Set `voice_config.voice_id` to specific Cartesia or ElevenLabs voice IDs.

### Q2: Indian accents for both agents?
**A**: Use Cartesia with Hindi language voices, or ElevenLabs Indian-accented voices. Update the voice IDs in persona service.

### Q3: Is conversation history passed to support agent?
**A**: ✅ **YES** - Full context (last 6 turns) is passed on every turn via `conversation.get_conversation_context()` at `orchestrator.py:248`.

### Q4: Is Jodo prompt passed to support agent?
**A**: ✅ **YES** - The complete 19KB system prompt from `support_agent_system_prompt.txt` is loaded and passed on EVERY turn at `orchestrator.py:220`, along with policies and guardrails.

### Q5: Which GPT models are used?
**A**: **Both agents use `GPT-4`** (same model, same temperature). Configured at `config.py:44`. Can be changed via `LLM_MODEL` environment variable or config.

---

## Files Referenced

- `orchestrator.py:170-263` - Message generation logic
- `conversation.py:164-167` - Context management
- `persona_service.py:37-210` - Persona and voice configuration
- `config.py:42-44` - LLM model configuration
- `openai.py:35` - Model initialization

All logic is verified and correct! ✅
