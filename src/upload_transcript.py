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
        print(f"Session ID: {data.get('session_id', 'N/A')}")
        print(f"Type: {data.get('type', 'N/A')}")
        print(f"Room ID: {data.get('room_id', 'N/A')}")
        print(f"Agent ID: {data.get('agent_id', 'N/A')}")
        print(f"Duration: {data.get('duration', 'N/A')} seconds")
        print(f"\nTranscript:")
        print("-" * 80)
        print(data.get("transcript", "(No transcript)"))
        print("-" * 80)
        print(f"\nJSON: {json.dumps(data, indent=2, ensure_ascii=False)}")
        print("=" * 80 + "\n")
        return

    api_url = os.getenv("TRANSCRIPT_API_URL", "https://api.example.com/transcripts")
    api_key = os.getenv("TRANSCRIPT_API_KEY", "")

    async with aiohttp.ClientSession() as session:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with session.post(api_url, json=data, headers=headers) as response:
            if response.status >= 400:
                text = await response.text()
                raise Exception(f"Upload failed: {response.status} - {text}")
            print(
                f"[TRANSCRIPT] Uploaded: {data.get('session_id')} ({data.get('type')})"
            )

