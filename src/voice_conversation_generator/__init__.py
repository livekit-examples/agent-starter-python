"""
Voice Conversation Generator - Synthetic conversation generation system

A modular system for generating realistic customer support conversations
with AI-powered text generation and voice synthesis.
"""

__version__ = "1.0.0"

# Make key components available at package level
from .models import (
    Conversation,
    CustomerPersona,
    SupportPersona,
    ConversationMetrics,
    VoiceConfig
)

from .services import (
    ConversationOrchestrator,
    PersonaService,
    ProviderFactory
)

__all__ = [
    # Models
    "Conversation",
    "CustomerPersona",
    "SupportPersona",
    "ConversationMetrics",
    "VoiceConfig",

    # Services
    "ConversationOrchestrator",
    "PersonaService",
    "ProviderFactory",
]