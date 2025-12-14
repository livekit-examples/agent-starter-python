import json
import asyncio
import os
from textwrap import dedent
from typing import Dict, Any
from dotenv import load_dotenv

from agent_config import fetch_agent_config
from transcript_tracker import TranscriptTracker
from upload_transcript import upload_transcript
from upload_worker import UploadWorkerConfig
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
    inference,
    llm,
)
from livekit import rtc
from livekit.plugins import noise_cancellation, silero, openai
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")

# =============================================================================
# Default Instructions
# =============================================================================

DEFAULT_INSTRUCTIONS = dedent("""
    ### ROLE
    You are a potential customer interested in real estate. You are currently receiving a phone call from a sales agent at a Real Estate Brokerage.

    ### CONTEXT
    You recently visited the brokerage's website or social media page and filled out a "More Information" form regarding a property or general investment opportunities. Because of this, you are considered a "warm lead," but you are not yet sold on a specific deal.

    ### BEHAVIORAL GUIDELINES
    1.  **Voice & Tone:** Speak casually and naturally. Use conversational fillers occasionally (e.g., "um," "well," "let me think"). Do not sound like an AI assistant; sound like a human on the phone.
    2.  **Length:** Keep your responses relatively short (1-3 sentences). People rarely give long monologues on sales calls.
    3.  **Information release:** Do not volunteer all your information (budget, timeline, needs) immediately. Make the salesperson ask the right questions to uncover them.
    4.  **Skepticism:** Start the call slightly guarded or busy. You "showed interest," but you might have forgotten filling out the form, or you might be busy right now. Warm up only if the salesperson builds rapport.
    5.  **Objections:** Introduce realistic objections naturally. Examples:
        * "I'm just looking right now."
        * "I'm actually really busy, can you make this quick?"
        * "The prices seem really high in that area."

    ### RULES OF ENGAGEMENT
    * **You are the CUSTOMER, not the assistant.** Never offer to help the salesperson.
    * **Never break character.** Do not mention you are an AI or act like the sales person
    * **End of Call:** If the salesperson is rude or aggressive, say you have to go and "hang up" (stop responding or say [HANGS UP]). If they do a good job, agree to a next step (e.g., a site visit or Zoom meeting).

    ### CURRENT GOAL
    Your goal is to determine if this agent is trustworthy and if they actually have inventory that matches your specific needs (based on the Persona).

    ### START
    Await the opening line from the Salesperson.
""").strip()


class AgentServer:
    """Minimal AgentServer wrapper to support the decorator pattern"""

    def __init__(self):
        self._entrypoint = None
        self._prewarm = None
        self._agent_name = None

    def rtc_session(self, agent_name: str = None):
        def decorator(func):
            self._entrypoint = func
            self._agent_name = agent_name
            return func

        return decorator

    @property
    def setup_fnc(self):
        return self._prewarm

    @setup_fnc.setter
    def setup_fnc(self, func):
        self._prewarm = func

    def __call__(self):
        """Allow cli.run_app(server) to work by converting to WorkerOptions"""
        return WorkerOptions(
            entrypoint_fnc=self._entrypoint,
            prewarm_fnc=self._prewarm,
            agent_name=self._agent_name,
        )


class DefaultAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=DEFAULT_INSTRUCTIONS)


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm

# =============================================================================
# Event Handlers for Transcript Tracking
# =============================================================================


def normalize_transcript(transcript_data) -> str:
    """Convert transcript data to a clean string."""
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
    """
    Wire up LiveKit session events to the transcript tracker.

    This connects:
    - User state changes (speaking/listening) → tracker.start_user_speech / end_user_speech
    - User transcripts → tracker.add_user_transcript
    - Agent state changes → tracker.start_agent_speech / end_agent_speech
    - Agent transcripts → tracker.add_agent_transcript
    """

    # -------------------------------------------------------------------------
    # User Speech Events
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Agent Speech Events
    # -------------------------------------------------------------------------

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


async def warmup_llm(llm_instance, instructions: str):
    """Send a dummy request to the LLM to trigger cache warmup."""
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


@server.rtc_session(agent_name="default")
async def entrypoint(ctx: JobContext):
    """Agent entrypoint with transcript tracking."""
    tracker = None
    disconnect_event = asyncio.Event()

    try:
        # Parse job metadata
        agent_id = None
        call_id = None
        job_metadata = None

        if hasattr(ctx, "job") and ctx.job and hasattr(ctx.job, "metadata"):
            job_metadata = ctx.job.metadata
            print(f"[AGENT] Raw metadata: {job_metadata}")

        if job_metadata:
            try:
                job_data = (
                    json.loads(job_metadata)
                    if isinstance(job_metadata, str)
                    else job_metadata
                )
                # Extract agentId (support multiple formats)
                agent_id = (
                    job_data.get("agent_id")
                    or job_data.get("agentId")
                    or job_data.get("uuid")
                    or job_data.get("id")
                )
                # Extract callId (support multiple formats)
                call_id = (
                    job_data.get("call_id")
                    or job_data.get("callId")
                )
                # Fallback: if metadata is just a string and not JSON, use it as agent_id
                if not agent_id:
                    agent_id = (
                        job_metadata
                        if isinstance(job_metadata, str)
                        else str(job_metadata)
                    )
            except Exception:
                # If JSON parsing fails, treat metadata as plain string (backward compatibility)
                agent_id = (
                    job_metadata if isinstance(job_metadata, str) else str(job_metadata)
                )

        # Log parsed metadata
        print(f"[AGENT] Agent ID: {agent_id}")
        print(f"[AGENT] Call ID: {call_id if call_id else 'None'}")

        # Fetch agent configuration
        config = None
        if agent_id:
            try:
                config = await fetch_agent_config(agent_id)
            except Exception as e:
                print(f"[AGENT] Error fetching config: {e}")

        # Extract config values
        system_prompt = config.get("system_prompt") if config else None
        agent_instructions = system_prompt if system_prompt else DEFAULT_INSTRUCTIONS

        # Voice configuration - use a known working Cartesia voice as default
        # Cartesia voice IDs for sonic-3 model
        DEFAULT_CARTESIA_VOICE = "c961b81c-a935-4c17-bfb3-ba2239de8c2f"  # "Kyle" voice (American English)

        voice_id = None
        if config:
            voice_id = config.get("voice_id")

        # Validate voice_id - must be non-empty string
        if not voice_id or not isinstance(voice_id, str) or len(voice_id.strip()) == 0:
            voice_id = DEFAULT_CARTESIA_VOICE
            print(f"[AGENT] Using default Cartesia voice: {voice_id}")
        else:
            print(f"[AGENT] Using configured voice: {voice_id}")

        # Initialize transcript tracker
        room_id = ctx.room.name if ctx.room else None

        worker_config = UploadWorkerConfig(
            max_queue_size=100,
            shutdown_timeout=30.0,
            poll_interval=1.0,
        )

        tracker = TranscriptTracker(
            upload_callback=upload_transcript,
            transcript_timeout=5.0,
            worker_config=worker_config,
            room_id=room_id,
            agent_id=agent_id,
        )

        await tracker.start()

        # Create agent and session
        dynamic_agent = Agent(instructions=agent_instructions)
        openai_key = os.getenv("OPENAI_API_KEY")

        stt_instance = inference.STT(
            model="assemblyai/universal-streaming",
            language="en",
        )

        llm_instance = openai.LLM(
            model="gpt-4o-mini",
            api_key=openai_key,
        )

        tts_instance = inference.TTS(
            model="cartesia/sonic-3",
            voice="c961b81c-a935-4c17-bfb3-ba2239de8c2f",
        )

        session = AgentSession(
            stt=stt_instance,
            llm=llm_instance,
            tts=tts_instance,
            turn_detection=MultilingualModel(),
            vad=ctx.proc.userdata["vad"],
        )

        # Setup event handlers
        setup_transcript_tracking(session, tracker)

        @ctx.room.on("disconnected")
        def on_room_disconnected():
            disconnect_event.set()

        @ctx.room.on("participant_disconnected")
        def on_participant_disconnected(participant: rtc.RemoteParticipant):
            disconnect_event.set()

        @session.on("close")
        def on_session_close():
            disconnect_event.set()

        # Start session
        warmup_task = asyncio.create_task(warmup_llm(session.llm, agent_instructions))

        await session.start(
            agent=dynamic_agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        )

        await ctx.connect()

        # After connection, try to get room metadata (contains both agentId and callId)
        if ctx.room:
            try:
                room_metadata = None
                if hasattr(ctx.room, "metadata"):
                    room_metadata = ctx.room.metadata
                    print(f"[AGENT] Room metadata: {room_metadata}")
                
                if room_metadata:
                    try:
                        room_data = (
                            json.loads(room_metadata)
                            if isinstance(room_metadata, str)
                            else room_metadata
                        )
                        # Extract agentId from room metadata (prefer room metadata over job metadata)
                        room_agent_id = (
                            room_data.get("agent_id")
                            or room_data.get("agentId")
                            or room_data.get("uuid")
                            or room_data.get("id")
                        )
                        # Extract callId from room metadata
                        room_call_id = (
                            room_data.get("call_id")
                            or room_data.get("callId")
                        )
                        
                        # Update values if found in room metadata
                        if room_agent_id:
                            agent_id = room_agent_id
                        if room_call_id:
                            call_id = room_call_id
                            
                        print(f"[AGENT] Updated from room metadata - Agent ID: {agent_id}, Call ID: {call_id if call_id else 'None'}")
                    except Exception as e:
                        print(f"[AGENT] Error parsing room metadata: {e}")
                else:
                    print(f"[AGENT] Room metadata not available (hasattr check: {hasattr(ctx.room, 'metadata')})")
            except Exception as e:
                print(f"[AGENT] Error accessing room metadata: {e}")

        try:
            await warmup_task
        except Exception:
            pass

        try:
            await ctx.room.local_participant.publish_data(
                payload=json.dumps({"type": "agent_ready"}),
                topic="agent_status",
                reliable=True,
            )
        except Exception:
            pass

        # Wait for disconnect
        await disconnect_event.wait()

    except Exception as e:
        print(f"[AGENT] FATAL ERROR: {e}")
        import traceback

        traceback.print_exc()
        raise

    finally:
        if tracker:
            try:
                await tracker.stop()
            except Exception:
                pass


if __name__ == "__main__":
    cli.run_app(server())
