"""
Persona Service - Manages customer and support personas
"""
import json
from pathlib import Path
from typing import Dict, List, Optional
from ..models import (
    CustomerPersona,
    SupportPersona,
    PersonaType,
    EmotionalState,
    VoiceConfig
)
from .voice_catalog import get_voice_catalog


class PersonaService:
    """Service for managing personas"""

    def __init__(self, personas_dir: str = "personas", tts_provider: str = "openai"):
        """Initialize persona service

        Args:
            personas_dir: Directory containing persona definitions
            tts_provider: TTS provider to use for voice selection (default: 'openai')
        """
        self.personas_dir = Path(personas_dir)
        self.customer_personas: Dict[str, CustomerPersona] = {}
        self.support_personas: Dict[str, SupportPersona] = {}
        self.tts_provider = tts_provider
        self.voice_catalog = get_voice_catalog()

    def load_default_personas(self):
        """Load default personas from the existing scenarios"""
        # Default support persona (from the prompts directory)
        self._load_support_persona_from_file()

        # Default customer personas (from existing scenarios)
        self._load_default_customer_personas()

    def _load_support_persona_from_file(self):
        """Load support persona from prompt file"""
        # Try to load from multiple possible locations
        prompt_paths = [
            Path("prompts/support_agent_system_prompt.txt"),
            Path("src/prompts/support_agent_system_prompt.txt"),
            Path("../prompts/support_agent_system_prompt.txt")
        ]

        prompt_text = None
        for path in prompt_paths:
            if path.exists():
                prompt_text = path.read_text()
                break

        if not prompt_text:
            # Fallback default
            prompt_text = """You are a helpful customer support agent.
Be professional, empathetic, and solution-focused."""

        # Query voice catalog for support agent (Hinglish support for Indian context)
        support_voice = self.voice_catalog.get_voice(
            provider=self.tts_provider,
            languages=["hi", "en"],  # Hinglish support
            accent="india",
            gender="male",
            persona_type="support_agent"
        )

        # Create voice config from catalog
        voice_config = VoiceConfig(provider=self.tts_provider, speed=1.0)
        if support_voice:
            voice_config.voice_id = support_voice.voice_id
            voice_config.voice_name = support_voice.name

        # Create default support persona
        support_persona = SupportPersona(
            id="default_support",
            name="Standard Support Agent",
            agent_name="फ़ैज़ान",  # Faizan in Hindi
            company_name="Jodo",
            system_prompt=prompt_text,
            personality="Professional, empathetic, solution-focused",
            guardrails=[
                "Always be respectful and patient",
                "Follow company policies",
                "Escalate when necessary"
            ],
            policies=[
                "Verify customer identity before discussing account details",
                "Offer payment plans for amounts over ₹5000",
                "Escalate to supervisor for refund requests over ₹10000"
            ],
            voice_config=voice_config
        )

        self.support_personas["default"] = support_persona

    def _load_default_customer_personas(self):
        """Load default customer personas from existing scenarios"""

        # These are the Jodo payment collection scenarios
        scenarios = {
            "cooperative_parent": {
                "name": "Cooperative Parent",
                "customer_name": "राज शर्मा",  # Raj Sharma
                "personality": "Cooperative and understanding parent",
                "emotional_state": "neutral",
                "issue": "School fee payment failed due to technical error",
                "goal": "Understand the issue and make the payment",
                "special_behavior": "",
                "difficulty": "easy",
                "languages": ["hi", "en"]  # Hinglish speaker
            },
            "angry_insufficient_funds": {
                "name": "Angry Parent - Financial Stress",
                "customer_name": "प्रिया गुप्ता",  # Priya Gupta
                "personality": "Frustrated female parent dealing with financial stress",
                "emotional_state": "angry",
                "issue": "Payment failed due to insufficient funds, but angry about repeated calls",
                "goal": "Express frustration and potentially avoid immediate payment",
                "special_behavior": "Start angry but may calm down if agent is empathetic",
                "difficulty": "hard",
                "languages": ["hi", "en"]  # Hinglish speaker
            },
            "wrong_person_family": {
                "name": "Wrong Person - Wife Takes Message",
                "customer_name": "सुनीता वर्मा",  # Sunita Verma
                "personality": "Helpful spouse who answers husband's phone",
                "emotional_state": "neutral",
                "issue": "Answering call meant for husband about his child's school fees",
                "goal": "Take a message or provide husband's callback time",
                "special_behavior": "Clarify early that the account holder (husband) is not available",
                "difficulty": "medium"
            },
            "confused_elderly_hindi": {
                "name": "Confused Elderly - Hindi Speaker",
                "customer_name": "रामेश्वर सिंह",  # Rameshwar Singh
                "personality": "Elderly grandparent, primarily Hindi speaker, limited tech understanding",
                "emotional_state": "confused",
                "issue": "Doesn't understand online payments, usually son handles it",
                "goal": "Understand what's happening and get help from son",
                "special_behavior": "Mix Hindi and English. Ask agent to speak slowly. Mention 'मेरा बेटा' (my son) handles these things",
                "difficulty": "medium",
                "languages": ["hi", "en"]  # Hinglish speaker (primarily Hindi)
            },
            "financial_hardship": {
                "name": "Financial Hardship - Needs Help",
                "customer_name": "अमित पटेल",  # Amit Patel
                "personality": "Honest parent facing temporary financial crisis",
                "emotional_state": "anxious",
                "issue": "Lost job recently, can't pay full amount",
                "goal": "Request payment plan or extension",
                "special_behavior": "Be apologetic and explain situation genuinely",
                "difficulty": "medium"
            },
            "already_paid_confusion": {
                "name": "Payment Confusion - Claims Paid",
                "customer_name": "कविता मेहता",  # Kavita Mehta
                "personality": "Confident parent who believes payment was made",
                "emotional_state": "confused",
                "issue": "Claims payment was already made last week",
                "goal": "Prove payment was made or understand the confusion",
                "special_behavior": "Insist on checking transaction history, mention UPI reference number",
                "difficulty": "medium"
            },
            "payment_cancellation_attempt": {
                "name": "Wants to Cancel - Needs Convincing",
                "customer_name": "विकास चौधरी",  # Vikas Choudhary
                "personality": "Parent considering changing schools",
                "emotional_state": "frustrated",
                "issue": "Unhappy with school, wants to cancel admission",
                "goal": "Cancel payment and possibly admission",
                "special_behavior": "Mention dissatisfaction with school services",
                "difficulty": "hard"
            },
            "call_back_later": {
                "name": "Busy Professional - Call Later",
                "customer_name": "नेहा अग्रवाल",  # Neha Agarwal
                "personality": "Busy working professional",
                "emotional_state": "neutral",
                "issue": "In a meeting, can't talk now",
                "goal": "Schedule callback for later",
                "special_behavior": "Be brief, mention being in office/meeting",
                "difficulty": "easy"
            }
        }

        # Convert to CustomerPersona objects
        for scenario_id, scenario_data in scenarios.items():
            # Map emotional state string to enum
            emotional_state_map = {
                "neutral": EmotionalState.NEUTRAL,
                "angry": EmotionalState.ANGRY,
                "confused": EmotionalState.CONFUSED,
                "frustrated": EmotionalState.FRUSTRATED,
                "anxious": EmotionalState.ANXIOUS,
                "happy": EmotionalState.HAPPY
            }

            emotional_state = emotional_state_map.get(
                scenario_data["emotional_state"],
                EmotionalState.NEUTRAL
            )

            # Determine gender from personality
            personality_lower = scenario_data["personality"].lower()
            gender = "female" if ("female" in personality_lower or "wife" in personality_lower) else "male"

            # Get languages from scenario data (default to English)
            languages = scenario_data.get("languages", ["en"])

            # Determine accent/country (default to India for this project)
            accent = "india" if any(lang in ["hi", "hindi"] for lang in languages) else "us"

            # Query voice catalog for best matching voice
            voice_entry = self.voice_catalog.get_voice(
                provider=self.tts_provider,
                languages=languages,
                accent=accent,
                gender=gender,
                persona_type="customer"
            )

            # Create voice config from catalog entry
            voice_config = VoiceConfig(provider=self.tts_provider, speed=1.0)
            if voice_entry:
                voice_config.voice_id = voice_entry.voice_id
                voice_config.voice_name = voice_entry.name

            # Adjust speed for elderly personas
            if "elderly" in personality_lower:
                voice_config.speed = 0.9

            persona = CustomerPersona(
                id=scenario_id,
                name=scenario_data["customer_name"],
                personality=scenario_data["personality"],
                emotional_state=emotional_state,
                issue=scenario_data["issue"],
                goal=scenario_data["goal"],
                special_behavior=scenario_data.get("special_behavior", ""),
                difficulty=scenario_data.get("difficulty", "medium"),
                languages=languages,  # Include languages from scenario
                voice_config=voice_config
            )

            self.customer_personas[scenario_id] = persona

    def get_customer_persona(self, persona_id: str) -> Optional[CustomerPersona]:
        """Get a customer persona by ID

        Args:
            persona_id: ID of the persona

        Returns:
            CustomerPersona or None if not found
        """
        return self.customer_personas.get(persona_id)

    def get_support_persona(self, persona_id: str = "default") -> Optional[SupportPersona]:
        """Get a support persona by ID

        Args:
            persona_id: ID of the persona (default: "default")

        Returns:
            SupportPersona or None if not found
        """
        return self.support_personas.get(persona_id)

    def list_customer_personas(self) -> List[CustomerPersona]:
        """List all available customer personas

        Returns:
            List of customer personas
        """
        return list(self.customer_personas.values())

    def list_support_personas(self) -> List[SupportPersona]:
        """List all available support personas

        Returns:
            List of support personas
        """
        return list(self.support_personas.values())

    def add_customer_persona(self, persona: CustomerPersona):
        """Add a customer persona

        Args:
            persona: CustomerPersona to add
        """
        if not persona.id:
            # Generate ID from name
            persona.id = persona.name.lower().replace(" ", "_")
        self.customer_personas[persona.id] = persona

    def add_support_persona(self, persona: SupportPersona):
        """Add a support persona

        Args:
            persona: SupportPersona to add
        """
        if not persona.id:
            # Generate ID from name
            persona.id = persona.name.lower().replace(" ", "_")
        self.support_personas[persona.id] = persona

    def save_personas_to_file(self, filepath: str):
        """Save all personas to a JSON file

        Args:
            filepath: Path to save personas
        """
        data = {
            "customer_personas": {
                pid: p.to_dict() for pid, p in self.customer_personas.items()
            },
            "support_personas": {
                pid: p.to_dict() for pid, p in self.support_personas.items()
            }
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def load_personas_from_file(self, filepath: str):
        """Load personas from a JSON file

        Args:
            filepath: Path to load personas from
        """
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Load customer personas
        if "customer_personas" in data:
            for pid, pdata in data["customer_personas"].items():
                persona = CustomerPersona.from_dict(pdata)
                self.customer_personas[pid] = persona

        # Load support personas
        if "support_personas" in data:
            for pid, pdata in data["support_personas"].items():
                persona = SupportPersona.from_dict(pdata)
                self.support_personas[pid] = persona