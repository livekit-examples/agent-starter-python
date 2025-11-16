"""
Local Storage Provider Implementation
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from ...models import Conversation, ConversationMetrics
from ..base import StorageGateway


class LocalStorageProvider(StorageGateway):
    """Local file system storage provider"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize local storage provider

        Config should include:
        - base_path: Base directory for storage (default: 'data/conversations')
        - create_dirs: Whether to create directories if they don't exist (default: True)
        """
        super().__init__(config)

        # Set base path
        self.base_path = Path(config.get('base_path', 'data/conversations'))

        # Create directories if needed
        if config.get('create_dirs', True):
            self.base_path.mkdir(parents=True, exist_ok=True)
            (self.base_path / 'audio').mkdir(exist_ok=True)
            (self.base_path / 'transcripts').mkdir(exist_ok=True)
            (self.base_path / 'metrics').mkdir(exist_ok=True)

    def _generate_filename(self, prefix: str, extension: str) -> str:
        """Generate a unique filename with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{timestamp}_{prefix}.{extension}"

    async def save_audio(
        self,
        data: bytes,
        key: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save audio data to local file system

        Args:
            data: Audio data as bytes
            key: Filename or relative path
            metadata: Optional metadata (saved as .json sidecar)

        Returns:
            Path to the stored file
        """
        # Ensure key has .mp3 extension
        if not key.endswith('.mp3'):
            key = f"{key}.mp3"

        # Full path
        file_path = self.base_path / 'audio' / key

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write audio data
        file_path.write_bytes(data)

        # Save metadata if provided
        if metadata:
            metadata_path = file_path.with_suffix('.meta.json')
            metadata_path.write_text(json.dumps(metadata, indent=2))

        return str(file_path)

    async def save_transcript(
        self,
        data: Dict[str, Any],
        key: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save transcript data to local file system

        Args:
            data: Transcript data as dictionary
            key: Filename or relative path
            metadata: Optional metadata (merged with transcript)

        Returns:
            Path to the stored file
        """
        # Ensure key has .json extension
        if not key.endswith('.json'):
            key = f"{key}.json"

        # Full path
        file_path = self.base_path / 'transcripts' / key

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Merge metadata if provided
        if metadata:
            data['metadata'] = metadata

        # Write JSON data
        file_path.write_text(json.dumps(data, indent=2, default=str))

        return str(file_path)

    async def save_conversation(
        self,
        conversation: Conversation,
        metrics: ConversationMetrics,
        audio_data: Optional[bytes] = None
    ) -> Dict[str, str]:
        """Save a complete conversation with all artifacts

        Args:
            conversation: Conversation object
            metrics: Conversation metrics
            audio_data: Optional combined audio data

        Returns:
            Dictionary with paths to stored files
        """
        # Generate base filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{timestamp}_{conversation.scenario_name}"

        result = {}

        # Save transcript
        transcript_data = conversation.to_dict(include_turns=True)
        transcript_data['metrics'] = metrics.to_dict()
        transcript_key = f"{base_name}_transcript.json"
        result['transcript'] = await self.save_transcript(transcript_data, transcript_key)

        # Save metrics separately
        metrics_key = f"{base_name}_metrics.json"
        metrics_path = self.base_path / 'metrics' / metrics_key
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(metrics.to_dict(), indent=2, default=str))
        result['metrics'] = str(metrics_path)

        # Save audio if provided
        if audio_data:
            audio_key = f"{base_name}_conversation.mp3"
            result['audio'] = await self.save_audio(
                audio_data,
                audio_key,
                metadata={'conversation_id': conversation.id, 'scenario': conversation.scenario_name}
            )

        # Update conversation with storage paths
        conversation.transcript_url = result['transcript']
        if 'audio' in result:
            conversation.audio_url = result['audio']

        return result

    async def load_audio(self, key: str) -> bytes:
        """Load audio data from local file system

        Args:
            key: Path to the audio file

        Returns:
            Audio data as bytes
        """
        file_path = Path(key) if os.path.isabs(key) else self.base_path / 'audio' / key
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {key}")
        return file_path.read_bytes()

    async def load_transcript(self, key: str) -> Dict[str, Any]:
        """Load transcript data from local file system

        Args:
            key: Path to the transcript file

        Returns:
            Transcript data as dictionary
        """
        file_path = Path(key) if os.path.isabs(key) else self.base_path / 'transcripts' / key
        if not file_path.exists():
            raise FileNotFoundError(f"Transcript file not found: {key}")
        return json.loads(file_path.read_text())

    async def list_conversations(
        self,
        prefix: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List available conversations

        Args:
            prefix: Optional prefix to filter conversations
            limit: Maximum number of conversations to return

        Returns:
            List of conversation metadata
        """
        conversations = []
        transcript_dir = self.base_path / 'transcripts'

        if not transcript_dir.exists():
            return conversations

        # Get all transcript files
        pattern = f"*{prefix}*_transcript.json" if prefix else "*_transcript.json"
        transcript_files = sorted(transcript_dir.glob(pattern), reverse=True)[:limit]

        for transcript_file in transcript_files:
            try:
                # Load basic metadata without full transcript
                data = json.loads(transcript_file.read_text())

                # Extract key information
                conversation_info = {
                    'id': data.get('id'),
                    'scenario_name': data.get('scenario_name'),
                    'created_at': data.get('created_at'),
                    'total_turns': data.get('total_turns', len(data.get('turns', []))),
                    'transcript_path': str(transcript_file),
                    'audio_path': data.get('audio_url'),
                    'file_size_kb': transcript_file.stat().st_size // 1024
                }

                # Add metrics if available
                if 'metrics' in data:
                    conversation_info['metrics_summary'] = {
                        'total_duration_seconds': data['metrics'].get('total_duration_seconds'),
                        'average_latency_ms': data['metrics'].get('average_latency_ms'),
                        'resolution_achieved': data['metrics'].get('resolution_achieved')
                    }

                conversations.append(conversation_info)

            except (json.JSONDecodeError, KeyError):
                continue

        return conversations

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its artifacts

        Args:
            conversation_id: ID of the conversation to delete

        Returns:
            True if deletion was successful
        """
        deleted_any = False

        # Find and delete all files matching the conversation ID
        for subdir in ['audio', 'transcripts', 'metrics']:
            dir_path = self.base_path / subdir
            if dir_path.exists():
                for file_path in dir_path.glob(f"*{conversation_id}*"):
                    file_path.unlink()
                    deleted_any = True

        return deleted_any

    def get_storage_type(self) -> str:
        """Get the type of storage"""
        return "local"