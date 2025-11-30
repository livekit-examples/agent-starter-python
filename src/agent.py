import json
import asyncio
from textwrap import dedent
from dotenv import load_dotenv

from agent_config import fetch_agent_config
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
    inference,
    utils,
    llm,
)
from livekit import rtc
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")


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
        super().__init__(
            instructions=dedent("""
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
                
                Persona Summary:
                This persona is driven by data, logic, and a deep-seated fear of overpaying. He is under high stress due to a new baby on the way and the need to sell his current condo. He will be skeptical, ask for proof, and will not be swayed by emotional language.
                Life_Stage : "Move-Up_Family"
                Relationship_Status : "Married/Partnered (He is leading the search; his wife, Sarah, trusts his financial judgment but wants a nice home)"
                Family_Unit : "Family (Young Kids) (One 4-year-old, and one baby on the way)"
                Occupation_Profile : "Salaried/Stable (e.g., Senior Accountant)"
                Physical_Needs : "Dedicated_WFH_Office (He works from home 2 days/week)"
                Disease_Profile : "None"
                Family_History : "Middle-Class/Frugal (Grew up in a family that watched every penny)"
                Transaction_Type : "Selling_and_Buying (High Stress)"
                Urgency_Timeline : "High/Urgent (The baby is due in 5 months; he wants to be "settled")"
                Trigger_Event : "Life_Change (New baby on the way, his 2-bedroom condo is now impossible)"
                Market_Knowledge : "Some (Zillow Expert) (He has been tracking his condo's "Zestimate" and suburban comps for a year)"
                Local_Knowledge : "Local_Resident (He lives in the city but is moving to the suburbs)"
                Budget_Flexibility : "Strict/Maxed-Out (His budget is entirely dependent on a top-dollar sale of his condo)"
                Financial_Attitude : "Data-Driven/ROI-Focused"
                Source_of_Funds : "Sale_of_Current_Home (A major contingency and source of stress)"
                Price_Point_Sensitivity : "High (He will fight over $1,000)"
                Primary_Driver : "Logic_ROI ("Show me the comps. Is it a good investment?")"
                Core_Fear : "Overpaying ("I will not be the chump who buys at the top of the market.")"
                Decision_Style : "Deliberate/Slow (He needs a spreadsheet for everything)"
                Optimism_Level : "Cautious/Pragmatic (Leaning towards pessimistic about the market)"
                Risk_Tolerance : "Risk-Averse (He wants a "turnkey" home. No renovations. No surprises.)"
                Past_Experience_Sentiment : "Positive (His condo purchase was smooth, but it was 7 years ago in a very different market)"
                Aesthetic_Preference : "Turnkey_Only (He sees renovations as risk and unknown costs)"
                Communication_Style : "Analytical/Conscientious (Reserved, skeptical, asks "why" 10x, can seem a bit cold)"
                Preferred_Channel : "Email_Only ("I want a paper trail. Don't just text me.")"
                Agent_Trust_Level : "Medium (He's willing to be led, but he will verify everything you say)"
                Objection_Handling_Style : "Questioning/Probing ("Can you send me the data on that?" "How did you get that number?")"
                Technology_Adoption : "Digital_Comfortable (He is fine with digital tools but will read every line of a Docusign)"
                
                
            """).strip(),
        )


server = AgentServer()

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

async def warmup_llm(llm_instance, instructions: str):
    """
    Send a dummy request to the LLM to trigger cache warmup using the LiveKit pipeline.
    """
    print("[WARMUP] Sending warmup request...")
    try:
        chat_ctx = llm.ChatContext(
            messages=[
                llm.ChatMessage(role=llm.ChatRole.SYSTEM, content=instructions),
                llm.ChatMessage(role=llm.ChatRole.USER, content="ignore this message, just warming up"),
            ]
        )
        
        stream = await llm_instance.chat(chat_ctx=chat_ctx, max_tokens=1)
        async for _ in stream:
            pass
            
        print("[WARMUP] Completed")
    except Exception as e:
        print(f"[WARMUP] Failed: {e}")

@server.rtc_session(agent_name="default")
async def entrypoint(ctx: JobContext):
    # Get agent_id from job metadata (from RoomAgentDispatch)
    agent_id = None
    if hasattr(ctx, 'job') and ctx.job and hasattr(ctx.job, 'metadata'):
        job_metadata = ctx.job.metadata
        print(f"[AGENT] Room metadata: {job_metadata}")
        
        # Extract agent_id from job metadata
        if job_metadata:
            try:
                if isinstance(job_metadata, str):
                    job_data = json.loads(job_metadata)
                else:
                    job_data = job_metadata
                # Try common field names for agent_id
                agent_id = job_data.get("agent_id") or job_data.get("agentId") or job_data.get("uuid") or job_data.get("id")
                # If not found in JSON, use the metadata string directly
                if not agent_id:
                    agent_id = job_metadata if isinstance(job_metadata, str) else str(job_metadata)
            except Exception:
                # If parsing fails, use metadata directly as agent_id
                agent_id = job_metadata if isinstance(job_metadata, str) else str(job_metadata)
    
    # Fetch agent configuration from API
    config = await fetch_agent_config(agent_id) if agent_id else None
    
    # Extract system_prompt and voice_id from config, or use defaults
    system_prompt = config.get("system_prompt") if config else None
    voice_id = config.get("voice_id", "c961b81c-a935-4c17-bfb3-ba2239de8c2f") if config else "c961b81c-a935-4c17-bfb3-ba2239de8c2f"
    
    # Log voice_id
    print(f"[AGENT] Voice ID: {voice_id}")
    
    # Log the actual instructions being provided to the model
    if system_prompt:
        agent_instructions = system_prompt
    else:
        # Fallback to default instructions
        agent_instructions = dedent("""
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
    
    print(f"[AGENT] Instructions being provided to the model:")
    print(f"[AGENT] {'=' * 80}")
    print(agent_instructions)
    print(f"[AGENT] {'=' * 80}")
    
    # Create agent with dynamic instructions
    dynamic_agent = Agent(instructions=agent_instructions)
    
    session = AgentSession(
        stt=inference.STT(model="assemblyai/universal-streaming", language="en"),
        llm=inference.LLM(model="openai/gpt-4.1-mini"),
        tts=inference.TTS(
            model="cartesia/sonic-3",
            voice=voice_id,
            extra_kwargs={"speed": 1.15},
        ),
        turn_detection=MultilingualModel(),  # type: ignore
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    # Determine noise cancellation based on participant type
    # For telephony applications, use BVCTelephony for best results
    noise_cancellation_option = noise_cancellation.BVC()
    
    # Start warmup in background
    warmup_task = asyncio.create_task(warmup_llm(session.llm, agent_instructions))

    await session.start(
        agent=dynamic_agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation_option,
        ),
    )
    
    await ctx.connect()

    # Wait for warmup to complete
    await warmup_task

    # Notify client that agent is ready
    print("[AGENT] Sending agent_ready event")
    await ctx.room.local_participant.publish_data(
        payload=json.dumps({"type": "agent_ready"}),
        topic="agent_status",
        reliable=True,
    )


if __name__ == "__main__":
    cli.run_app(server())
