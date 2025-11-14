#!/usr/bin/env python
"""
Quick Test Runner - The easiest way to run conversation tests
"""
import asyncio
import sys
import logging
from pathlib import Path
import time
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from conversation_orchestrator import DualAgentOrchestrator, quick_test_conversation
from customer_agent import SCENARIO_TEMPLATES
from results_viewer import ResultsAnalyzer
from dotenv import load_dotenv

# Load environment
load_dotenv(".env.local")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def print_banner():
    """Print a nice banner"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           🎭 VOICE AGENT CONVERSATION TESTER 🎭              ║
║                                                              ║
║  Simulate customer-support conversations to test AI agents  ║
╚══════════════════════════════════════════════════════════════╝
""")


def print_scenarios():
    """Print available scenarios"""
    print("\n📚 Available Scenarios:")
    print("-" * 50)
    for i, (name, details) in enumerate(SCENARIO_TEMPLATES.items(), 1):
        print(f"{i}. {name}")
        print(f"   Customer: {details['customer_name']}")
        print(f"   Issue: {details['issue'][:50]}...")
        print(f"   Difficulty: {details['difficulty']}")
        print()


async def run_single_test(scenario: str):
    """Run a single test scenario"""
    print(f"\n▶️  Starting test: {scenario}")
    print("="*50)

    # For now, use the quick test setup
    await quick_test_conversation(scenario)

    print("\n✅ Test complete!")
    print("\nNote: Full conversation simulation requires both agents")
    print("to connect to the LiveKit room. This is a setup test.")


async def run_all_tests():
    """Run all scenarios"""
    print("\n🚀 Running ALL scenarios...")
    results = []

    for scenario in SCENARIO_TEMPLATES.keys():
        print(f"\n▶️  Testing: {scenario}")
        await quick_test_conversation(scenario)
        results.append(scenario)
        await asyncio.sleep(2)  # Brief pause between tests

    print(f"\n✅ Completed {len(results)} tests!")
    return results


def interactive_menu():
    """Interactive menu for test selection"""
    while True:
        print("\n" + "="*50)
        print("What would you like to do?")
        print("="*50)
        print("1. Run a single scenario")
        print("2. Run all scenarios")
        print("3. View latest results")
        print("4. Generate HTML report")
        print("5. List scenarios")
        print("0. Exit")

        choice = input("\nEnter choice: ").strip()

        if choice == "0":
            print("👋 Goodbye!")
            break

        elif choice == "1":
            print_scenarios()
            scenario_input = input("Enter scenario name or number: ").strip()

            # Handle number input
            try:
                scenario_num = int(scenario_input)
                scenario_list = list(SCENARIO_TEMPLATES.keys())
                if 1 <= scenario_num <= len(scenario_list):
                    scenario = scenario_list[scenario_num - 1]
                else:
                    print("❌ Invalid number")
                    continue
            except ValueError:
                # Use as scenario name
                scenario = scenario_input

            if scenario in SCENARIO_TEMPLATES:
                asyncio.run(run_single_test(scenario))
            else:
                print(f"❌ Unknown scenario: {scenario}")

        elif choice == "2":
            asyncio.run(run_all_tests())

        elif choice == "3":
            analyzer = ResultsAnalyzer()
            analyzer.load_results()
            analyzer.print_summary()

        elif choice == "4":
            analyzer = ResultsAnalyzer()
            analyzer.load_results()
            report_path = analyzer.generate_html_report()
            print(f"📊 Report saved: {report_path}")

            # Try to open in browser
            import webbrowser
            try:
                webbrowser.open(f"file://{Path(report_path).absolute()}")
            except:
                pass

        elif choice == "5":
            print_scenarios()

        else:
            print("❌ Invalid choice")


def main():
    """Main entry point"""
    print_banner()

    if len(sys.argv) > 1:
        # Command line mode
        command = sys.argv[1]

        if command == "test" and len(sys.argv) > 2:
            scenario = sys.argv[2]
            if scenario == "all":
                asyncio.run(run_all_tests())
            else:
                asyncio.run(run_single_test(scenario))

        elif command == "list":
            print_scenarios()

        elif command == "results":
            analyzer = ResultsAnalyzer()
            analyzer.load_results()
            analyzer.print_summary()

        elif command == "report":
            analyzer = ResultsAnalyzer()
            analyzer.load_results()
            analyzer.generate_html_report()

        else:
            print("Usage:")
            print("  python run_test.py                    # Interactive mode")
            print("  python run_test.py test <scenario>    # Run specific test")
            print("  python run_test.py test all           # Run all tests")
            print("  python run_test.py list              # List scenarios")
            print("  python run_test.py results           # View results")
            print("  python run_test.py report            # Generate HTML report")

    else:
        # Interactive mode
        interactive_menu()


if __name__ == "__main__":
    main()