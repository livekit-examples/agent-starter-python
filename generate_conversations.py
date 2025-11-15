#!/usr/bin/env python
"""
Generate Multiple Synthetic Conversations with Audio
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.conversation_simulator import simulate_conversation, SCENARIOS


async def generate_all_conversations():
    """Generate conversations for all scenarios"""

    print("""
╔══════════════════════════════════════════════════════════════╗
║       🎭 SYNTHETIC CONVERSATION GENERATOR WITH AUDIO 🎭      ║
╚══════════════════════════════════════════════════════════════╝
    """)

    results = []

    for scenario_name in SCENARIOS.keys():
        print(f"\n{'='*60}")
        print(f"Generating: {scenario_name}")
        print('='*60)

        try:
            result = await simulate_conversation(scenario_name)
            results.append(result)
            await asyncio.sleep(2)  # Brief pause between generations
        except Exception as e:
            print(f"Error generating {scenario_name}: {e}")

    # Summary
    print(f"\n{'='*60}")
    print("📊 GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"✅ Generated {len(results)} conversations")
    print(f"📁 Files saved in: conversations/")
    print("\nYou now have:")
    print("  • Audio files (MP3) of each conversation")
    print("  • JSON transcripts with timestamps")
    print("  • Conversation metrics")

    # List all files
    conversations_dir = Path("conversations")
    if conversations_dir.exists():
        files = list(conversations_dir.glob("*.mp3"))
        print(f"\n🎵 Audio Files Generated ({len(files)}):")
        for f in files:
            print(f"  • {f.name}")

    return results


async def main():
    """Main entry point"""

    if len(sys.argv) > 1 and sys.argv[1] == "all":
        # Generate all scenarios
        await generate_all_conversations()
    elif len(sys.argv) > 1:
        # Generate specific scenario
        scenario = sys.argv[1]
        if scenario in SCENARIOS:
            await simulate_conversation(scenario)
        else:
            print(f"Unknown scenario: {scenario}")
            print(f"Available: {', '.join(SCENARIOS.keys())}")
    else:
        # Interactive mode
        print("""
🎭 CONVERSATION GENERATOR

Usage:
  python generate_conversations.py all              # Generate all scenarios
  python generate_conversations.py angry_refund     # Generate specific scenario

Available scenarios:
""")
        for name, details in SCENARIOS.items():
            print(f"  • {name}: {details['customer_name']} - {details['issue'][:50]}...")


if __name__ == "__main__":
    asyncio.run(main())