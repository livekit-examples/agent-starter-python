"""
Test Runner - Orchestrates conversations between customer and support agents
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import uuid

from livekit import api, rtc
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.agents.voice import MetricsCollectedEvent
from livekit.plugins import silero, noise_cancellation
from dotenv import load_dotenv
import os

from customer_agent import create_customer_agent, SCENARIO_TEMPLATES
from support_agent import create_support_agent
from metrics_collector import ConversationAnalyzer

load_dotenv(".env.local")
logger = logging.getLogger("test_runner")


class ConversationTest:
    """Manages a single test conversation between customer and support agents"""

    def __init__(self, test_id: str, scenario_name: str,
                 support_prompt: Optional[str] = None):
        self.test_id = test_id
        self.scenario_name = scenario_name
        self.scenario = SCENARIO_TEMPLATES.get(scenario_name, SCENARIO_TEMPLATES["friendly_billing"])
        self.support_prompt = support_prompt
        self.room_name = f"test-{test_id}"
        self.start_time = None
        self.end_time = None
        self.analyzer = None
        self.results = {
            "test_id": test_id,
            "scenario": scenario_name,
            "status": "pending",
            "transcript": [],
            "metrics": {},
            "errors": []
        }

    async def run(self, timeout: int = 180) -> Dict[str, Any]:
        """Run the test conversation"""
        logger.info(f"Starting test {self.test_id} with scenario: {self.scenario_name}")
        self.start_time = time.time()

        try:
            # Create room for the test
            room = await self._create_room()

            # Start both agents in parallel
            customer_task = asyncio.create_task(self._run_customer_agent())
            support_task = asyncio.create_task(self._run_support_agent())

            # Wait for conversation with timeout
            await asyncio.wait_for(
                asyncio.gather(customer_task, support_task),
                timeout=timeout
            )

            self.results["status"] = "completed"

        except asyncio.TimeoutError:
            logger.warning(f"Test {self.test_id} timed out after {timeout} seconds")
            self.results["status"] = "timeout"
        except Exception as e:
            logger.error(f"Test {self.test_id} failed: {e}")
            self.results["status"] = "failed"
            self.results["errors"].append(str(e))
        finally:
            self.end_time = time.time()
            self.results["duration"] = self.end_time - self.start_time
            await self._cleanup()

        return self.results

    async def _create_room(self) -> rtc.Room:
        """Create a LiveKit room for the test"""
        livekit_api = api.LiveKitAPI()

        # Create room with metadata about the test
        room_metadata = json.dumps({
            "test_id": self.test_id,
            "scenario": self.scenario_name,
            "type": "agent_test"
        })

        await livekit_api.room.create_room(
            api.CreateRoomRequest(
                name=self.room_name,
                metadata=room_metadata,
                empty_timeout=60,  # Auto-delete after 1 minute of being empty
                max_participants=4  # Customer, Support, and potential observers
            )
        )

        logger.info(f"Created room: {self.room_name}")
        return self.room_name

    async def _run_customer_agent(self):
        """Run the customer agent in the test room"""
        # This would normally connect to the room and start the customer agent
        # For now, we'll simulate this
        logger.info(f"Customer agent starting in room {self.room_name}")

        # Create a worker context that will run the customer agent
        customer_agent = create_customer_agent(self.scenario_name)

        # The actual implementation would join the room here
        await asyncio.sleep(60)  # Simulate conversation time

    async def _run_support_agent(self):
        """Run the support agent in the test room"""
        logger.info(f"Support agent starting in room {self.room_name}")

        # Create support agent with custom prompt if provided
        support_agent = create_support_agent(prompt_file=self.support_prompt)

        # The actual implementation would join the room here
        await asyncio.sleep(60)  # Simulate conversation time

    async def _cleanup(self):
        """Clean up resources after test"""
        try:
            livekit_api = api.LiveKitAPI()
            await livekit_api.room.delete_room(api.DeleteRoomRequest(room=self.room_name))
            logger.info(f"Cleaned up room: {self.room_name}")
        except Exception as e:
            logger.error(f"Failed to cleanup room {self.room_name}: {e}")


class TestBatch:
    """Manages a batch of test conversations"""

    def __init__(self, batch_id: Optional[str] = None):
        self.batch_id = batch_id or str(uuid.uuid4())[:8]
        self.tests: List[ConversationTest] = []
        self.results_dir = Path(f"results/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.batch_id}")
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def add_test(self, scenario_name: str, support_prompt: Optional[str] = None) -> ConversationTest:
        """Add a test to the batch"""
        test_id = f"{self.batch_id}-{len(self.tests):03d}"
        test = ConversationTest(test_id, scenario_name, support_prompt)
        self.tests.append(test)
        return test

    async def run(self, parallel: int = 3) -> Dict[str, Any]:
        """Run all tests in the batch with controlled parallelism"""
        logger.info(f"Starting batch {self.batch_id} with {len(self.tests)} tests")
        start_time = time.time()

        results = {
            "batch_id": self.batch_id,
            "total_tests": len(self.tests),
            "completed": 0,
            "failed": 0,
            "timeout": 0,
            "tests": []
        }

        # Run tests in chunks to control parallelism
        for i in range(0, len(self.tests), parallel):
            chunk = self.tests[i:i+parallel]
            chunk_tasks = [test.run() for test in chunk]
            chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)

            for test_result in chunk_results:
                if isinstance(test_result, Exception):
                    logger.error(f"Test failed with exception: {test_result}")
                    results["failed"] += 1
                else:
                    results["tests"].append(test_result)
                    if test_result["status"] == "completed":
                        results["completed"] += 1
                    elif test_result["status"] == "timeout":
                        results["timeout"] += 1
                    else:
                        results["failed"] += 1

                    # Save individual test result
                    self._save_test_result(test_result)

        # Save batch summary
        results["duration"] = time.time() - start_time
        results["success_rate"] = results["completed"] / results["total_tests"] if results["total_tests"] > 0 else 0

        self._save_batch_summary(results)
        logger.info(f"Batch {self.batch_id} completed: {results['completed']}/{results['total_tests']} successful")

        return results

    def _save_test_result(self, result: Dict[str, Any]):
        """Save individual test result to file"""
        test_file = self.results_dir / f"test_{result['test_id']}.json"
        with open(test_file, 'w') as f:
            json.dump(result, f, indent=2)

    def _save_batch_summary(self, summary: Dict[str, Any]):
        """Save batch summary to file"""
        summary_file = self.results_dir / "batch_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Results saved to {self.results_dir}")


async def run_quick_test():
    """Run a quick test with one scenario"""
    batch = TestBatch("quick")
    batch.add_test("angry_refund")
    results = await batch.run(parallel=1)
    print(f"\nQuick test results: {results['completed']}/{results['total_tests']} successful")
    return results


async def run_comprehensive_test(support_prompt: Optional[str] = None):
    """Run comprehensive tests with all scenarios"""
    batch = TestBatch("comprehensive")

    # Add all scenario types
    for scenario_name in SCENARIO_TEMPLATES.keys():
        batch.add_test(scenario_name, support_prompt)

    # Run with higher parallelism
    results = await batch.run(parallel=5)

    print(f"\n{'='*50}")
    print(f"COMPREHENSIVE TEST RESULTS")
    print(f"{'='*50}")
    print(f"Total Tests: {results['total_tests']}")
    print(f"Completed: {results['completed']}")
    print(f"Failed: {results['failed']}")
    print(f"Timeout: {results['timeout']}")
    print(f"Success Rate: {results['success_rate']*100:.1f}%")
    print(f"Duration: {results['duration']:.1f} seconds")
    print(f"Results saved to: {batch.results_dir}")

    return results


# CLI for running tests
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run agent conversation tests")
    parser.add_argument("--mode", choices=["quick", "comprehensive", "single"],
                       default="quick", help="Test mode to run")
    parser.add_argument("--scenario", default="angry_refund",
                       help="Scenario to use for single test")
    parser.add_argument("--prompt", help="Path to custom support agent prompt file")
    parser.add_argument("--parallel", type=int, default=3,
                       help="Number of parallel tests to run")

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run the appropriate test
    if args.mode == "quick":
        asyncio.run(run_quick_test())
    elif args.mode == "comprehensive":
        asyncio.run(run_comprehensive_test(args.prompt))
    else:  # single
        batch = TestBatch("single")
        batch.add_test(args.scenario, args.prompt)
        asyncio.run(batch.run(parallel=1))