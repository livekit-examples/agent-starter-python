#!/usr/bin/env python
"""
Voice Conversation Generator CLI - Clean modular interface
"""
import asyncio
import sys
from pathlib import Path
import click

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from voice_conversation_generator.config.config import Config, get_config
from voice_conversation_generator.services import (
    ConversationOrchestrator,
    PersonaService,
    ProviderFactory
)
from voice_conversation_generator.models import ConversationConfig


@click.group()
@click.pass_context
def cli(ctx):
    """Voice Conversation Generator - Generate synthetic customer support conversations"""
    # Load configuration
    ctx.ensure_object(dict)
    ctx.obj['config'] = Config.load()


@cli.command()
@click.option('--customer', '-c', default='cooperative_parent', help='Customer persona ID')
@click.option('--support', '-s', default='default', help='Support persona ID')
@click.option('--max-turns', '-t', default=10, help='Maximum conversation turns')
@click.option('--tts', type=click.Choice(['openai', 'elevenlabs', 'cartesia', 'auto']), default='auto', help='TTS provider')
@click.option('--save/--no-save', default=True, help='Save conversation to storage')
@click.pass_context
def generate(ctx, customer: str, support: str, max_turns: int, tts: str, save: bool):
    """Generate a synthetic conversation"""

    config = ctx.obj['config']

    # Override TTS provider if specified
    if tts != 'auto':
        config.providers.tts['type'] = tts

    # Run async function
    asyncio.run(_generate_conversation(config, customer, support, max_turns, save))


async def _generate_conversation(
    config: Config,
    customer_id: str,
    support_id: str,
    max_turns: int,
    save: bool
):
    """Async function to generate conversation"""

    print("\n🚀 Voice Conversation Generator")
    print("=" * 50)

    # Initialize services
    print("📦 Loading services...")
    tts_provider = config.providers.tts.get('type', 'openai')
    persona_service = PersonaService(tts_provider=tts_provider)
    persona_service.load_default_personas()

    # Get personas
    customer_persona = persona_service.get_customer_persona(customer_id)
    if not customer_persona:
        print(f"❌ Customer persona '{customer_id}' not found")
        print(f"Available personas: {', '.join(persona_service.customer_personas.keys())}")
        return

    support_persona = persona_service.get_support_persona(support_id)
    if not support_persona:
        print(f"❌ Support persona '{support_id}' not found")
        return

    print(f"✅ Loaded customer: {customer_persona.name} ({customer_persona.emotional_state.value})")
    print(f"✅ Loaded support: {support_persona.agent_name} from {support_persona.company_name}")

    # Create providers
    print("\n🔧 Initializing providers...")
    providers = ProviderFactory.create_all_providers(config)
    print(f"  LLM: {providers['llm'].get_model_name()}")
    print(f"  TTS: {providers['tts'].get_provider_name()}")
    print(f"  Storage: {providers['storage'].get_storage_type()}")

    # Create orchestrator
    orchestrator = ConversationOrchestrator(
        llm_provider=providers['llm'],
        tts_provider=providers['tts'],
        storage_gateway=providers['storage']
    )

    # Configure conversation
    conv_config = ConversationConfig(
        max_turns=max_turns,
        llm_provider=config.providers.llm['type'],
        llm_model=config.providers.llm.get('model', 'gpt-4'),
        tts_provider=config.providers.tts['type']
    )

    # Generate conversation
    print("\n🎭 Generating conversation...")
    conversation, metrics = await orchestrator.generate_conversation(
        customer_persona=customer_persona,
        support_persona=support_persona,
        config=conv_config
    )

    # Save if requested
    if save:
        print("\n💾 Saving conversation...")
        paths = await orchestrator.save_conversation(conversation, metrics)
        print(f"✅ Saved successfully!")

    # Print metrics summary
    print("\n📊 Metrics Summary:")
    print(metrics.generate_summary())


@cli.command()
@click.option('--type', '-t', type=click.Choice(['customer', 'support', 'all']), default='all', help='Persona type to list')
@click.pass_context
def list_personas(ctx, type: str):
    """List available personas"""

    # Initialize persona service
    persona_service = PersonaService()
    persona_service.load_default_personas()

    if type in ['customer', 'all']:
        print("\n👥 Customer Personas:")
        print("=" * 50)
        for persona in persona_service.list_customer_personas():
            print(f"\n📌 {persona.id}")
            print(f"  Name: {persona.name}")
            print(f"  Personality: {persona.personality}")
            print(f"  Emotional State: {persona.emotional_state.value}")
            print(f"  Issue: {persona.issue[:50]}...")

    if type in ['support', 'all']:
        print("\n🎧 Support Personas:")
        print("=" * 50)
        for persona in persona_service.list_support_personas():
            print(f"\n📌 {persona.id}")
            print(f"  Name: {persona.agent_name}")
            print(f"  Company: {persona.company_name}")
            print(f"  Personality: {persona.personality}")


@cli.command()
@click.option('--limit', '-l', default=10, help='Number of conversations to list')
@click.pass_context
def list_conversations(ctx, limit: int):
    """List recent conversations"""

    config = ctx.obj['config']

    # Run async function
    asyncio.run(_list_conversations(config, limit))


async def _list_conversations(config: Config, limit: int):
    """Async function to list conversations"""

    # Create storage gateway
    storage = ProviderFactory.create_storage_gateway(config)

    # List conversations
    conversations = await storage.list_conversations(limit=limit)

    if not conversations:
        print("No conversations found")
        return

    print(f"\n📚 Recent Conversations (showing {len(conversations)} of {limit} max):")
    print("=" * 60)

    for conv in conversations:
        print(f"\n🗂️  {conv.get('scenario_name', 'Unknown')}")
        print(f"   ID: {conv.get('id', 'N/A')}")
        print(f"   Created: {conv.get('created_at', 'Unknown')}")
        print(f"   Turns: {conv.get('total_turns', 0)}")
        print(f"   Transcript: {conv.get('transcript_path', 'N/A')}")

        if 'metrics_summary' in conv:
            metrics = conv['metrics_summary']
            if metrics.get('total_duration_seconds'):
                print(f"   Duration: {metrics['total_duration_seconds']:.1f}s")
            if metrics.get('average_latency_ms'):
                print(f"   Avg Latency: {metrics['average_latency_ms']:.1f}ms")


@cli.command()
@click.pass_context
def show_config(ctx):
    """Show current configuration"""

    config = ctx.obj['config']

    print("\n⚙️  Current Configuration:")
    print("=" * 50)
    print(f"\n📱 Application:")
    print(f"  Environment: {config.app.environment}")
    print(f"  Debug: {config.app.debug}")

    print(f"\n💾 Storage:")
    print(f"  Type: {config.storage.type}")
    if config.storage.type == 'local':
        print(f"  Path: {config.storage.local['base_path']}")

    print(f"\n🤖 Providers:")
    print(f"  LLM: {config.providers.llm['type']} ({config.providers.llm.get('model', 'default')})")
    print(f"  TTS: {config.providers.tts['type']}")

    print(f"\n🔌 Integrations:")
    print(f"  Database: {'Enabled' if config.database.enabled else 'Disabled'}")
    print(f"  LiveKit: {'Enabled' if config.livekit.enabled else 'Disabled'}")


if __name__ == '__main__':
    cli()