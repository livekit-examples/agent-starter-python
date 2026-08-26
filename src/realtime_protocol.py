"""Validated realtime contracts shared by the Hermes LiveKit worker."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

CONTROL_TOPIC = "hermes.control"
STATUS_TOPIC = "hermes.status"
PROTOCOL_VERSION = 1
SUPPORTED_COMMANDS = frozenset({"new", "stop", "status"})
SUPPORTED_MENTIONS = frozenset(
    {
        "main",
        "architect",
        "researcher",
        "coder",
        "browser",
        "computer-operator",
        "qa",
        "reviewer",
        "security",
        "ops",
    }
)

_MAX_PACKET_BYTES = 4096
_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_LEADING_MENTION = re.compile(r"^@([a-z][a-z0-9-]*)(?:\s+|$)", re.IGNORECASE)


@dataclass(frozen=True)
class ControlMessage:
    version: int
    op_id: str
    command: str
    conversation_id: str | None = None


@dataclass
class ConversationState:
    current: str

    def reset(self, value: str) -> bool:
        parsed = parse_conversation_id(value, "")
        if not parsed:
            return False
        self.current = parsed
        return True


@dataclass(frozen=True)
class MentionRoute:
    mention: str | None
    hermes_input: str
    status: str | None


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def parse_conversation_id(value: str | None, fallback: str) -> str:
    """Return a validated conversation identifier, then a validated fallback."""
    if _valid_identifier(value):
        return value
    if _valid_identifier(fallback):
        return fallback
    return ""


def parse_control_packet(data: bytes) -> ControlMessage | None:
    """Decode a bounded control packet, rejecting every non-whitelisted shape."""
    if not isinstance(data, bytes) or not data or len(data) > _MAX_PACKET_BYTES:
        return None

    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    allowed_fields = {"version", "op_id", "command", "conversation_id"}
    required_fields = {"version", "op_id", "command"}
    if set(payload) - allowed_fields or not required_fields.issubset(payload):
        return None

    version = payload["version"]
    op_id = payload["op_id"]
    command = payload["command"]
    conversation_id = payload.get("conversation_id")
    if type(version) is not int or version != PROTOCOL_VERSION:
        return None
    if not _valid_identifier(op_id):
        return None
    if not isinstance(command, str) or command not in SUPPORTED_COMMANDS:
        return None
    if conversation_id is not None and not _valid_identifier(conversation_id):
        return None

    return ControlMessage(version, op_id, command, conversation_id)


def route_mention(text: str) -> MentionRoute:
    """Turn a supported leading mention into a Hermes Main routing instruction."""
    match = _LEADING_MENTION.match(text)
    if match is None:
        return MentionRoute(None, text, None)

    mention = match.group(1).lower()
    if mention not in SUPPORTED_MENTIONS:
        return MentionRoute(None, text, None)

    request = text[match.end() :]
    if mention == "main":
        return MentionRoute(
            mention,
            request,
            "Hermes Main assigned",
        )

    if mention == "computer-operator":
        return MentionRoute(
            mention,
            (
                "The user addressed @computer-operator. Hermes Main remains the "
                "commander. Act as the Computer Operator within this foreground "
                "Hermes Main run. Do not call delegate_task because a background "
                "child's later approval cannot be delivered to the connected mobile. "
                "Use the existing computer-use tools and safety mechanisms directly; "
                "route every approval through this current run.\n\n"
                f"User request: {request}"
            ),
            "Computer Operator assigned",
        )

    display_name = mention.replace("-", " ").title()
    hermes_input = (
        f"The user addressed @{mention}. Hermes Main remains the commander. "
        f"Use the existing delegation and safety mechanisms to delegate this "
        f"request to the {display_name} specialist; do not bypass Hermes Main.\n\n"
        f"User request: {request}"
    )
    return MentionRoute(mention, hermes_input, f"{display_name} assigned")
