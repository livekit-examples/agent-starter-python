import os
from livekit.agents import inference, llm
from livekit.plugins import openai
from constants import STT_MODEL, LLM_MODEL, TTS_MODEL


def create_stt(language: str = "en") -> inference.STT:
    return inference.STT(
        model=STT_MODEL,
        language=language,
    )


def create_llm(api_key: str = None) -> openai.LLM:
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")
    return openai.LLM(
        model=LLM_MODEL,
        api_key=api_key,
    )


def create_tts(voice_id: str) -> inference.TTS:
    return inference.TTS(
        model=TTS_MODEL,
        voice=voice_id,
    )


async def warmup_llm(llm_instance, instructions: str):
    try:
        chat_ctx = llm.ChatContext(
            messages=[
                llm.ChatMessage(role=llm.ChatRole.SYSTEM, content=instructions),
                llm.ChatMessage(role=llm.ChatRole.USER, content="warmup"),
            ]
        )
        stream = await llm_instance.chat(chat_ctx=chat_ctx, max_tokens=1)
        async for _ in stream:
            pass
    except Exception:
        pass
