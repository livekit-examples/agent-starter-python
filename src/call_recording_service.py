"""
LiveKit Call Recording Service

Requirements:
    pip install livekit-api python-dotenv
"""

import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv
from livekit.api import LiveKitAPI
from livekit.api.egress_service import RoomCompositeEgressRequest
from livekit.protocol.egress import (
    EncodedFileOutput,
    S3Upload,
    EncodedFileType,
    DUAL_CHANNEL_AGENT,
    StopEgressRequest,
)
from livekit.protocol.models import WebhookConfig

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RecordingConfig:
    LIVEKIT_URL = os.getenv("LIVEKIT_URL")
    LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
    LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
    AWS_ACCESS_KEY = os.getenv("S3_UPLOAD_ACCESS_KEY")
    AWS_SECRET_VALUE = os.getenv("S3_UPLOAD_ACCESS_SECRET_VALUE")
    AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
    S3_BUCKET = os.getenv("S3_BUCKET_NAME")


@dataclass
class RecordingResult:
    egress_id: str
    s3_key: str
    status: str


class CallRecordingService:
    def __init__(self):
        print(f"[CallRecordingService] LIVEKIT_URL: {RecordingConfig.LIVEKIT_URL}")
        print(f"[CallRecordingService] LIVEKIT_API_KEY: {RecordingConfig.LIVEKIT_API_KEY[:10]}...")
        self.livekit_api = LiveKitAPI(
            url=RecordingConfig.LIVEKIT_URL,
            api_key=RecordingConfig.LIVEKIT_API_KEY,
            api_secret=RecordingConfig.LIVEKIT_API_SECRET,
        )
        print(f"[CallRecordingService] LiveKitAPI initialized")

    def _build_s3_path(self, session_id: str, extension: str) -> str:
        return f"default/{session_id}.{extension}"

    async def start_recording(
        self,
        room_name: str,
        session_id: str,
        upload_mp3: bool = False
    ) -> RecordingResult:
        """
        Start recording a LiveKit room.

        Args:
            room_name: The LiveKit room name to record
            session_id: Your application's session identifier
            upload_mp3: If True, use MP3 format. Otherwise use OGG/Opus (default)
            audio_only: If True, record audio only. Otherwise record audio and video

        Returns:
            RecordingResult with egress_id and s3_key
        """
        if upload_mp3:
            file_type = EncodedFileType.MP3
            extension = "mp3"
        else:
            file_type = EncodedFileType.OGG
            extension = "ogg"

        s3_key = self._build_s3_path(session_id, extension)

        s3_upload = S3Upload(
            bucket=RecordingConfig.S3_BUCKET,
            region=RecordingConfig.AWS_REGION,
            access_key=RecordingConfig.AWS_ACCESS_KEY,
            secret=RecordingConfig.AWS_SECRET_VALUE,
        )

        file_output = EncodedFileOutput(
            filepath=s3_key,
            s3=s3_upload,
            file_type=file_type,
        )

        request = RoomCompositeEgressRequest(
            room_name=room_name,
            file=file_output,
            audio_only=True,
            audio_mixing=DUAL_CHANNEL_AGENT,
            webhooks=[
                WebhookConfig(
                    url="https://zr1red2j54.execute-api.ap-south-1.amazonaws.com/dev/webhooks/livekit",
                    signing_key=RecordingConfig.LIVEKIT_API_KEY
                )
            ]
        )

        egress_info = await self.livekit_api.egress.start_room_composite_egress(request)

        logger.info(f"Started recording for room {room_name}, egress_id: {egress_info.egress_id}")

        return RecordingResult(
            egress_id=egress_info.egress_id,
            s3_key=s3_key,
            status="recording",
        )

    async def stop_recording(self, egress_id: str) -> RecordingResult:
        request = StopEgressRequest(egress_id=egress_id)
        egress_info = await self.livekit_api.egress.stop_egress(request)

        logger.info(f"Stopped recording {egress_id}")

        return RecordingResult(
            egress_id=egress_id,
            s3_key="",
            status=str(egress_info.status),
        )