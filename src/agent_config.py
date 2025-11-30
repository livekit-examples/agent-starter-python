"""Agent configuration API client for fetching dynamic agent instructions."""
import json
import logging
import httpx

logger = logging.getLogger("agent-config")

API_BASE_URL = "https://wi5fbjhqu5mrsj2sxun42dkpqq0lstgv.lambda-url.ap-south-1.on.aws"


async def fetch_agent_config(agent_id: str) -> dict | None:
    """
    Fetch agent configuration from the API.
    
    Args:
        agent_id: The agent ID to fetch configuration for
        
    Returns:
        Dictionary containing 'system_prompt' and 'voice_id', or None if fetch fails
    """
    if not agent_id:
        return None
    
    try:
        api_url = f"{API_BASE_URL}/?agent_id={agent_id}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, timeout=10.0)
            response.raise_for_status()
            result = response.json()
        
        # Handle the nested JSON structure (Lambda response with body field containing JSON string)
        # or direct JSON response
        if "body" in result and isinstance(result["body"], str):
            # Lambda response format: {"statusCode": 200, "body": "{\"system_prompt\":...}"}
            body_data = json.loads(result["body"])
        elif "statusCode" in result and "body" in result:
            # Handle case where body might be a dict already
            body_data = result["body"] if isinstance(result["body"], dict) else json.loads(result["body"])
        else:
            # Direct JSON response: {"system_prompt": "...", "agent_config": {...}}
            body_data = result
        
        # Extract system_prompt and voice_id
        config = {}
        
        if "system_prompt" in body_data:
            config["system_prompt"] = body_data["system_prompt"]
        
        if "agent_config" in body_data and isinstance(body_data["agent_config"], dict) and "voice_id" in body_data["agent_config"]:
            config["voice_id"] = body_data["agent_config"]["voice_id"]
        
        return config if config else None
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching configuration from API: {e.response.status_code} - {e.response.text}", exc_info=True)
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error fetching configuration from API: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching configuration from API: {e}", exc_info=True)
        return None

