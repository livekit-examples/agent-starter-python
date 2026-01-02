from livekit.agents import AgentSession
from transcript_tracker import TranscriptTracker


def normalize_transcript(transcript_data) -> str:
    if transcript_data is None:
        return ""

    if isinstance(transcript_data, str):
        return transcript_data.strip()

    if isinstance(transcript_data, (list, tuple)):
        parts = []
        for item in transcript_data:
            if item:
                if isinstance(item, str):
                    parts.append(item.strip())
                elif hasattr(item, "text"):
                    parts.append(str(item.text).strip())
                else:
                    parts.append(str(item).strip())
        return " ".join(parts)

    if hasattr(transcript_data, "text"):
        return str(transcript_data.text).strip()

    return str(transcript_data).strip()


def setup_transcript_tracking(
    session: AgentSession,
    tracker: TranscriptTracker,
) -> None:
    @session.on("user_state_changed")
    def on_user_state_changed(event):
        if isinstance(event, dict):
            new_state = event.get("new_state")
            old_state = event.get("old_state")
        else:
            new_state = getattr(event, "new_state", None)
            old_state = getattr(event, "old_state", None)

        if new_state == "speaking":
            tracker.start_user_speech()
        elif new_state == "listening" and old_state == "speaking":
            tracker.end_user_speech()

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event):
        if isinstance(event, dict):
            is_final = event.get("is_final", True)
            transcript = event.get("transcript") or event.get("text")
        else:
            is_final = getattr(event, "is_final", True)
            transcript = getattr(event, "transcript", None) or getattr(
                event, "text", None
            )

        if is_final and transcript:
            transcript_text = normalize_transcript(transcript)
            if transcript_text:
                tracker.add_user_transcript(transcript_text)

    @session.on("agent_state_changed")
    def on_agent_state_changed(event):
        if isinstance(event, dict):
            new_state = event.get("new_state")
            old_state = event.get("old_state")
        else:
            new_state = getattr(event, "new_state", None)
            old_state = getattr(event, "old_state", None)

        if new_state == "speaking":
            tracker.start_agent_speech()
        elif new_state == "listening" and old_state == "speaking":
            tracker.end_agent_speech()

    @session.on("conversation_item_added")
    def on_conversation_item_added(event):
        try:
            if isinstance(event, dict):
                item = event.get("item")
            else:
                item = getattr(event, "item", None)

            if not item:
                return

            if isinstance(item, dict):
                role = item.get("role", "")
            else:
                role = getattr(item, "role", "")

            role_str = str(role).lower() if role else ""

            if "assistant" in role_str:
                if isinstance(item, dict):
                    content = (
                        item.get("content") or item.get("text") or item.get("message")
                    )
                else:
                    content = (
                        getattr(item, "content", None)
                        or getattr(item, "text", None)
                        or getattr(item, "message", None)
                    )

                if content:
                    transcript_text = normalize_transcript(content)
                    if transcript_text:
                        tracker.add_agent_transcript(transcript_text)
        except Exception as e:
            print(f"[TRANSCRIPT ERROR] conversation_item_added: {e}")
