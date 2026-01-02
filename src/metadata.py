import json
from typing import Dict, Any, Optional, Union


def parse_metadata(raw: Optional[Union[str, Dict[str, Any]]]) -> Dict[str, Optional[str]]:
    if not raw:
        return {"agent_id": None, "call_id": None}
    
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return {
            "agent_id": (
                data.get("agent_id")
                or data.get("agentId")
                or data.get("uuid")
                or data.get("id")
            ),
            "call_id": (
                data.get("call_id")
                or data.get("callId")
            ),
        }
    except Exception:
        return {
            "agent_id": raw if isinstance(raw, str) else str(raw),
            "call_id": None
        }
