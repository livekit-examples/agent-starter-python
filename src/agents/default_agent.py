from livekit.agents import Agent, ChatContext, ChatMessage
from constants import DEFAULT_INSTRUCTIONS
from utils import extract_recent_utterances


class DefaultAgent(Agent):
    def __init__(self, instructions: str = DEFAULT_INSTRUCTIONS) -> None:
        super().__init__(instructions=instructions)

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        print(f"[DefaultAgent] turn_ctx: {[m.role + ': ' + (m.text_content or '') for m in turn_ctx.items]}")
        recent_utterances = extract_recent_utterances(turn_ctx, count=4)
        current_utterance = new_message.text_content or ""
        print(f"[DefaultAgent] recent_utterances: {recent_utterances}")
        # TODO: use recent_utterances + current_utterance for context fetch


    async def _fetch_context(self, user_message: str) -> str | None:
        return None

