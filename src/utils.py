from livekit.agents import ChatContext


def extract_recent_utterances(
        turn_ctx: ChatContext, count: int = 4
) -> list[str]:
    messages = [
        m.text_content
        for m in turn_ctx.items
        if m.text_content and m.role in ("user", "assistant")
    ]
    return messages[-(count + 1): -1] if len(messages) > 1 else []