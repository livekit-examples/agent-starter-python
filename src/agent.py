import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from agent_config import fetch_agent_config
from transcript_tracker import TranscriptTracker
from upload_transcript import upload_transcript
from upload_worker import UploadWorkerConfig
from constants import DEFAULT_CARTESIA_VOICE, DEFAULT_INSTRUCTIONS
from metadata import parse_metadata
from services import create_stt, create_llm, create_tts, warmup_llm
from transcript_handlers import setup_transcript_tracking
from server import AgentServer, prewarm
from agents import DefaultAgent
from livekit.agents import (
    AgentSession,
    JobContext,
    RoomInputOptions,
    cli,
)
from livekit import rtc
from livekit.plugins import noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")


server = AgentServer()
server.setup_fnc = prewarm


@server.rtc_session(agent_name="default")
async def entrypoint(ctx: JobContext):
    tracker = None
    disconnect_event = asyncio.Event()

    try:
        job_meta = parse_metadata(ctx.job.metadata if hasattr(ctx, "job") and ctx.job and hasattr(ctx.job, "metadata") else None)
        print(f"[AGENT] Job metadata - Agent ID: {job_meta['agent_id']}, Call ID: {job_meta['call_id']}")

        config = None
        if job_meta["agent_id"]:
            try:
                config = await fetch_agent_config(job_meta["agent_id"])
            except Exception as e:
                print(f"[AGENT] Error fetching config: {e}")

        system_prompt = config.get("system_prompt") if config else None
        agent_instructions = system_prompt if system_prompt else DEFAULT_INSTRUCTIONS

        voice_id = config.get("voice_id") if config else None
        if not voice_id or not isinstance(voice_id, str) or len(voice_id.strip()) == 0:
            voice_id = DEFAULT_CARTESIA_VOICE
            print(f"[AGENT] Using default Cartesia voice: {voice_id}")
        else:
            print(f"[AGENT] Using configured voice: {voice_id}")

        dynamic_agent = DefaultAgent(instructions=agent_instructions)
        
        stt_instance = create_stt()
        llm_instance = create_llm()
        tts_instance = create_tts(voice_id)

        session = AgentSession(
            stt=stt_instance,
            llm=llm_instance,
            tts=tts_instance,
            turn_detection=MultilingualModel(),
            vad=ctx.proc.userdata["vad"],
        )

        @ctx.room.on("disconnected")
        def on_room_disconnected():
            disconnect_event.set()

        @ctx.room.on("participant_disconnected")
        def on_participant_disconnected(participant: rtc.RemoteParticipant):
            disconnect_event.set()

        @session.on("close")
        def on_session_close():
            disconnect_event.set()

        warmup_task = asyncio.create_task(warmup_llm(session.llm, agent_instructions))

        await session.start(
            agent=dynamic_agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        )

        await ctx.connect()

        call_start_time = datetime.utcnow()

        room_meta = parse_metadata(ctx.room.metadata if ctx.room and hasattr(ctx.room, "metadata") else None)
        print(f"[AGENT] Room metadata - Agent ID: {room_meta['agent_id']}, Call ID: {room_meta['call_id']}")

        agent_id = room_meta["agent_id"] or job_meta["agent_id"]
        call_id = room_meta["call_id"] or job_meta["call_id"]

        if not call_id:
            raise ValueError("call_id is required but could not be determined from metadata")

        worker_config = UploadWorkerConfig(
            max_queue_size=100,
            shutdown_timeout=30.0,
            poll_interval=1.0,
        )

        tracker = TranscriptTracker(
            upload_callback=upload_transcript,
            call_id=call_id,
            call_start_time=call_start_time,
            transcript_timeout=5.0,
            worker_config=worker_config,
            room_id=ctx.room.name if ctx.room else None,
            agent_id=agent_id,
        )

        await tracker.start()
        setup_transcript_tracking(session, tracker)

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
