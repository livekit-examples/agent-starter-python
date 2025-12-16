import json
import os
from datetime import datetime
from typing import Dict, Any

import aiohttp


async def upload_transcript(data: Dict[str, Any]) -> None:
    """
    Upload transcript data to your backend server.

    Set TRANSCRIPT_LOG_ONLY=true to log to console instead of uploading.
    This is useful for testing without an API endpoint.
    """
    # Check if we should only log (no actual upload)
    log_only = os.getenv("TRANSCRIPT_LOG_ONLY", "false").lower() == "true"

    if log_only:
        print("\n" + "=" * 80)
        print(f"[TRANSCRIPT] 📝 Transcript Data (Console Log Mode)")
        print("=" * 80)
        print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
        print(f"Call ID: {data.get('call_id', 'N/A')}")
        print(f"Speaker: {data.get('speaker', 'N/A')}")
        print(f"Start Time: {data.get('start_time', 'N/A')}")
        print(f"End Time: {data.get('end_time', 'N/A')}")
        print(f"Duration: {data.get('duration', 'N/A')} seconds")
        print(f"\nTranscript:")
        print("-" * 80)
        print(data.get("transcript", "(No transcript)"))
        print("-" * 80)
        print(f"\nJSON: {json.dumps(data, indent=2, ensure_ascii=False)}")
        print("=" * 80 + "\n")
        return

    # Extract call_id from data (required for URL construction)
    call_id = data.get("call_id")
    if not call_id:
        raise ValueError("call_id is required in transcript data")

    # Get base URL and construct full endpoint URL
    api_base_url = os.getenv(
        "TRANSCRIPT_API_URL",
        "https://zr1red2j54.execute-api.ap-south-1.amazonaws.com/dev"
    )
    api_url = f"{api_base_url}/calls/{call_id}/utterance"

    async with aiohttp.ClientSession() as session:
        headers = {"Content-Type": "application/json"}

        async with session.post(api_url, json=data, headers=headers) as response:
            if response.status >= 400:
                text = await response.text()
                raise Exception(f"Upload failed: {response.status} - {text}")
            print(
                f"[TRANSCRIPT] Uploaded: {data.get('call_id')} ({data.get('speaker')})"
            )

