"""
Conversation Orchestrator - Makes two agents talk to each other in a LiveKit room
This is the KEY component that connects everything!
"""
import asyncio
import logging
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli, MetricsCollectedEvent
from livekit import api
from livekit.plugins import silero, noise_cancellation
from dotenv import load_dotenv
import os

from customer_agent import create_customer_agent
from support_agent import create_support_agent
from metrics_collector import ConversationAnalyzer, LiveKitMetricsAdapter

load_dotenv(".env.local")
logger = logging.getLogger("orchestrator")


class DualAgentOrchestrator:
    """Runs both customer and support agents in the same room"""

    def __init__(self, scenario_name: str, support_prompt: Optional[str] = None):
        self.scenario_name = scenario_name
        self.support_prompt = support_prompt
        self.analyzer = ConversationAnalyzer()
        self.adapter = LiveKitMetricsAdapter(self.analyzer)
        self.test_id = f"{scenario_name}_{int(time.time())}"
        self.customer_session = None
        self.support_session = None

    async def run_conversation(self, ctx: JobContext, max_duration: int = 120):
        """Run both agents in the same room"""
        logger.info(f"Starting conversation test: {self.test_id}")

        # Determine which agent we are based on participant identity
        participant_identity = ctx.participant_identity if hasattr(ctx, 'participant_identity') else None

        if participant_identity == "customer":
            await self.run_customer(ctx)
        elif participant_identity == "support":
            await self.run_support(ctx)
        else:
            # If no specific identity, run both (for local testing)
            await self.run_both_agents(ctx, max_duration)

    async def run_customer(self, ctx: JobContext):
        """Run the customer agent"""
        logger.info(f"Starting CUSTOMER agent for scenario: {self.scenario_name}")

        customer = create_customer_agent(self.scenario_name)

        self.customer_session = AgentSession(
            stt="deepgram",
            llm="openai/gpt-4o-mini",
            tts="cartesia/sonic-3:cardinal",  # More assertive voice for customer
            vad=silero.VAD.load(),
        )

        # Set up metrics collection
        self._setup_customer_metrics()

        await self.customer_session.start(
            room=ctx.room,
            agent=customer,
            room_input_options={
                "noise_cancellation": noise_cancellation.BVC()
            }
        )

        # Wait a moment for support to join, then start talking
        await asyncio.sleep(2)

        # Customer initiates the conversation
        await self.customer_session.generate_reply(
            instructions="Start the conversation by explaining your issue clearly and directly"
        )

        # Keep the session alive
        await asyncio.sleep(120)

    async def run_support(self, ctx: JobContext):
        """Run the support agent"""
        logger.info(f"Starting SUPPORT agent")

        support = create_support_agent(self.support_prompt)

        self.support_session = AgentSession(
            stt="deepgram",
            llm="openai/gpt-4o-mini",
            tts="cartesia/sonic-3:asheville",  # Professional voice for support
            vad=silero.VAD.load(),
        )

        # Set up metrics collection
        self._setup_support_metrics()

        await self.support_session.start(
            room=ctx.room,
            agent=support,
            room_input_options={
                "noise_cancellation": noise_cancellation.BVC()
            }
        )

        # Support waits for customer to speak first
        logger.info("Support agent ready and listening...")

        # Keep the session alive
        await asyncio.sleep(120)

    async def run_both_agents(self, ctx: JobContext, max_duration: int):
        """Run both agents in parallel (for local testing)"""
        logger.info("Running BOTH agents in the same process")

        # Create tasks for both agents
        customer_task = asyncio.create_task(self.run_customer(ctx))
        support_task = asyncio.create_task(self.run_support(ctx))

        # Run with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(customer_task, support_task),
                timeout=max_duration
            )
        except asyncio.TimeoutError:
            logger.info(f"Conversation ended after {max_duration} seconds")

        # Save results
        self.save_results()

    def _setup_customer_metrics(self):
        """Set up metrics collection for customer session"""
        if not self.customer_session:
            return

        @self.customer_session.on("metrics_collected")
        def on_customer_metrics(event: MetricsCollectedEvent):
            logger.debug(f"Customer metrics: {event.metrics}")
            # Process metrics through adapter
            self.adapter.on_metrics_collected(event)

        @self.customer_session.on("user_speech_committed")
        def on_customer_spoke(event):
            logger.info(f"CUSTOMER said: {event.text[:50]}...")
            self.adapter.on_user_speech_ended(event)

    def _setup_support_metrics(self):
        """Set up metrics collection for support session"""
        if not self.support_session:
            return

        @self.support_session.on("metrics_collected")
        def on_support_metrics(event: MetricsCollectedEvent):
            logger.debug(f"Support metrics: {event.metrics}")
            # Process metrics through adapter
            self.adapter.on_metrics_collected(event)

        @self.support_session.on("agent_speech_started")
        def on_support_started(event):
            self.adapter.on_agent_speech_started(event)

        @self.support_session.on("agent_speech_committed")
        def on_support_spoke(event):
            logger.info(f"SUPPORT said: {event.text[:50]}...")
            self.adapter.on_agent_speech_ended(event)

    def save_results(self):
        """Save conversation results to file"""
        results_dir = Path(f"results/{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        results_dir.mkdir(parents=True, exist_ok=True)

        # Get metrics summary
        summary = self.analyzer.get_summary()
        summary["test_id"] = self.test_id
        summary["scenario"] = self.scenario_name

        # Save to file
        results_file = results_dir / f"{self.test_id}.json"
        with open(results_file, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Results saved to {results_file}")
        print(f"\n{'='*50}")
        print(f"Conversation Summary:")
        print(f"  Scenario: {self.scenario_name}")
        print(f"  Duration: {summary['duration']:.1f}s")
        print(f"  Turns: {summary['turns']}")
        print(f"  Interruptions: {summary['quality_metrics']['interruptions']['count']}")
        print(f"  Results: {results_file}")
        print(f"{'='*50}\n")


# Entrypoint for running via LiveKit CLI
async def entrypoint(ctx: JobContext):
    """Main entrypoint for the worker"""

    # Get configuration from room metadata
    room_metadata = {}
    if ctx.room.metadata:
        try:
            room_metadata = json.loads(ctx.room.metadata)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse room metadata: {ctx.room.metadata}")

    scenario = room_metadata.get("scenario", "friendly_billing")
    support_prompt = room_metadata.get("support_prompt")

    # Create and run orchestrator
    orchestrator = DualAgentOrchestrator(scenario, support_prompt)
    await orchestrator.run_conversation(ctx)


# Quick test runner
async def quick_test_conversation(scenario: str = "angry_refund"):
    """Quick way to test a conversation locally"""
    print(f"\n{'='*50}")
    print(f"Starting Quick Test: {scenario}")
    print(f"{'='*50}\n")

    # Create API client
    livekit_api = api.LiveKitAPI()

    # Create a test room
    room_name = f"test_{scenario}_{int(time.time())}"
    room_metadata = json.dumps({
        "scenario": scenario,
        "type": "test"
    })

    try:
        # Create room
        await livekit_api.room.create_room(
            api.CreateRoomRequest(
                name=room_name,
                metadata=room_metadata,
                empty_timeout=30
            )
        )
        logger.info(f"Created room: {room_name}")

        # Generate tokens for both agents
        from livekit import api as lk_api

        customer_token = lk_api.AccessToken(
            os.getenv("LIVEKIT_API_KEY"),
            os.getenv("LIVEKIT_API_SECRET")
        ).with_identity("customer").with_name("Customer").with_grants(
            lk_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True
            )
        ).to_jwt()

        support_token = lk_api.AccessToken(
            os.getenv("LIVEKIT_API_KEY"),
            os.getenv("LIVEKIT_API_SECRET")
        ).with_identity("support").with_name("Support Agent").with_grants(
            lk_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True
            )
        ).to_jwt()

        print(f"Room created: {room_name}")
        print(f"Customer token: {customer_token[:20]}...")
        print(f"Support token: {support_token[:20]}...")

        # In a real implementation, both agents would connect to this room
        # For now, we'll simulate the conversation
        print("\nSimulating conversation...")
        await asyncio.sleep(5)

        print("\n✅ Test setup complete!")
        print(f"Room: {room_name}")
        print("Both agents would connect and start talking here")

    finally:
        # Cleanup
        try:
            await livekit_api.room.delete_room(api.DeleteRoomRequest(room=room_name))
            logger.info(f"Deleted room: {room_name}")
        except:
            pass


if __name__ == "__main__":
    import sys

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        # Run as a worker
        cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
    else:
        # Run quick test
        scenario = sys.argv[1] if len(sys.argv) > 1 else "angry_refund"
        asyncio.run(quick_test_conversation(scenario))