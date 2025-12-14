"""
Event-driven transcript tracking system for LiveKit Agents.

This version uses asyncio primitives for true event-based processing
instead of polling and sleep-based waiting.
"""
import asyncio
import uuid
import time
from datetime import datetime
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum, auto
import logging

from upload_worker import UploadWorker, UploadWorkerConfig

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """State machine for transcript sessions."""
    SPEAKING = auto()      # Speech in progress
    WAITING_TRANSCRIPT = auto()  # Speech ended, waiting for transcript
    COMPLETE = auto()      # Ready for upload
    UPLOADED = auto()      # Successfully uploaded


@dataclass
class TranscriptSession:
    """Represents a single speech session with event-driven completion tracking."""

    session_id: str
    role: str  # "user" or "agent"
    start_time: float
    start_time_iso: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    end_time: Optional[float] = None
    end_time_iso: Optional[str] = None
    transcript: Optional[str] = None
    state: SessionState = SessionState.SPEAKING
    room_id: Optional[str] = None
    agent_id: Optional[str] = None

    # Event that fires when session becomes complete
    _completion_event: asyncio.Event = field(default_factory=asyncio.Event)

    def end_speech(self):
        """Mark speech as ended and transition state."""
        self.end_time = time.time()
        self.end_time_iso = datetime.utcnow().isoformat()

        if self.transcript is not None:
            self._mark_complete()
        else:
            self.state = SessionState.WAITING_TRANSCRIPT

    def set_transcript(self, transcript: str):
        """Set transcript and potentially mark complete."""
        self.transcript = transcript

        if self.state == SessionState.WAITING_TRANSCRIPT:
            self._mark_complete()

    def _mark_complete(self):
        """Mark session as complete and signal waiting tasks."""
        self.state = SessionState.COMPLETE
        self._completion_event.set()

    def is_complete(self) -> bool:
        return self.state == SessionState.COMPLETE

    async def wait_for_completion(self, timeout: float) -> bool:
        """
        Wait for session to become complete.

        Returns:
            True if completed, False if timed out
        """
        if self.is_complete():
            return True

        try:
            await asyncio.wait_for(self._completion_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    @property
    def duration(self) -> Optional[float]:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "type": self.role,
            "transcript": self.transcript or "",
            "start_time": self.start_time_iso,
            "end_time": self.end_time_iso or self.start_time_iso,
            "duration": self.duration,
            "has_transcript": self.transcript is not None,
            "room_id": self.room_id,
            "agent_id": self.agent_id,
        }


class TranscriptTracker:
    """
    Event-driven transcript tracker using asyncio primitives.

    Key features:
    - Uses asyncio.Event for completion signaling (no polling)
    - Delegates upload processing to separate UploadWorker
    - Proper cancellation and cleanup
    """

    def __init__(
        self,
        upload_callback: Callable[[Dict[str, Any]], Any],
        transcript_timeout: float = 5.0,
        worker_config: Optional[UploadWorkerConfig] = None,
        room_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        """
        Initialize the transcript tracker.

        Args:
            upload_callback: Function to call for uploads. Can be sync or async.
            transcript_timeout: Seconds to wait for transcript after speech ends.
            worker_config: Configuration for the upload worker.
            room_id: Optional room ID for tracking.
            agent_id: Optional agent ID for tracking.
        """
        self.transcript_timeout = transcript_timeout
        self.room_id = room_id
        self.agent_id = agent_id

        # Session storage
        self._sessions: Dict[str, TranscriptSession] = {}
        self._active_user_session: Optional[str] = None
        self._active_agent_session: Optional[str] = None

        # Upload worker (separate concern)
        self._upload_worker = UploadWorker(
            upload_callback=upload_callback,
            config=worker_config,
            on_success=self._on_upload_success,
            on_failure=self._on_upload_failure,
        )

        # Timeout tasks
        self._pending_timeout_tasks: Dict[str, asyncio.Task] = {}

    def _on_upload_success(self, session: TranscriptSession):
        """Callback when upload succeeds."""
        session.state = SessionState.UPLOADED
        self._sessions.pop(session.session_id, None)
        logger.info(f"Uploaded session: {session.session_id}")

    def _on_upload_failure(self, session: TranscriptSession, error: Exception):
        """Callback when upload fails."""
        self._sessions.pop(session.session_id, None)
        logger.error(f"Failed to upload session {session.session_id}: {error}")

    async def start(self):
        """Start the tracker and its upload worker."""
        await self._upload_worker.start()
        logger.info("TranscriptTracker started")

    async def stop(self):
        """Gracefully stop the tracker and flush pending uploads."""
        logger.info("Stopping TranscriptTracker...")

        # Cancel pending timeout tasks
        for task in self._pending_timeout_tasks.values():
            task.cancel()
        self._pending_timeout_tasks.clear()

        # Stop the upload worker (handles queue draining)
        await self._upload_worker.stop()

        logger.info("TranscriptTracker stopped")

    def _create_session(self, role: str) -> TranscriptSession:
        """Create a new session with unique ID."""
        session_id = f"{role}_{uuid.uuid4().hex[:8]}_{int(time.time() * 1000)}"
        session = TranscriptSession(
            session_id=session_id,
            role=role,
            start_time=time.time(),
            room_id=self.room_id,
            agent_id=self.agent_id,
        )
        self._sessions[session_id] = session
        return session

    def _schedule_timeout(self, session: TranscriptSession):
        """Schedule a timeout task for session completion."""
        async def timeout_handler():
            try:
                completed = await session.wait_for_completion(self.transcript_timeout)

                if not completed:
                    logger.warning(
                        f"Session {session.session_id} timed out waiting for transcript"
                    )
                    # Only upload if we have a transcript
                    if session.transcript:
                        session.state = SessionState.COMPLETE
                        await self._upload_worker.enqueue(session)
                    else:
                        # No transcript, skip upload and remove session
                        logger.info(
                            f"Skipping upload for session {session.session_id} - no transcript"
                        )
                        self._sessions.pop(session.session_id, None)
                        return
                else:
                    # Completed successfully, upload
                    await self._upload_worker.enqueue(session)

            except asyncio.CancelledError:
                pass
            finally:
                self._pending_timeout_tasks.pop(session.session_id, None)

        task = asyncio.create_task(timeout_handler())
        self._pending_timeout_tasks[session.session_id] = task

    # ==================== Public API ====================

    def start_user_speech(self) -> str:
        """Start tracking a new user speech session."""
        session = self._create_session("user")
        self._active_user_session = session.session_id
        logger.debug(f"Started user session: {session.session_id}")
        return session.session_id

    def end_user_speech(self) -> Optional[str]:
        """Mark user speech as ended."""
        if not self._active_user_session:
            logger.warning("end_user_speech called with no active session")
            return None

        session_id = self._active_user_session
        session = self._sessions.get(session_id)
        self._active_user_session = None

        if not session:
            logger.error(f"Session {session_id} not found")
            return None

        session.end_speech()

        # If already complete (transcript arrived first), queue immediately
        if session.is_complete():
            asyncio.create_task(self._upload_worker.enqueue(session))
        else:
            # Otherwise schedule timeout
            self._schedule_timeout(session)

        logger.debug(f"Ended user session: {session_id}")
        return session_id

    def add_user_transcript(self, transcript: str) -> Optional[str]:
        """Add transcript to user session."""
        session_id = self._active_user_session

        # Try to find a waiting session if no active one
        if not session_id:
            session_id = self._find_waiting_session("user")

        # Create new session if needed (late transcript)
        if not session_id:
            logger.warning("Creating session for late user transcript")
            session = self._create_session("user")
            session.set_transcript(transcript)
            session.end_speech()
            asyncio.create_task(self._upload_worker.enqueue(session))
            return session.session_id

        session = self._sessions.get(session_id)
        if session:
            session.set_transcript(transcript)

            # If session is now complete and was waiting, the Event will signal
            # the timeout handler to proceed with upload

        return session_id

    def start_agent_speech(self) -> str:
        """Start tracking a new agent speech session."""
        session = self._create_session("agent")
        self._active_agent_session = session.session_id
        logger.debug(f"Started agent session: {session.session_id}")
        return session.session_id

    def end_agent_speech(self) -> Optional[str]:
        """Mark agent speech as ended."""
        if not self._active_agent_session:
            logger.warning("end_agent_speech called with no active session")
            return None

        session_id = self._active_agent_session
        session = self._sessions.get(session_id)
        self._active_agent_session = None

        if not session:
            logger.error(f"Session {session_id} not found")
            return None

        session.end_speech()

        if session.is_complete():
            asyncio.create_task(self._upload_worker.enqueue(session))
        else:
            self._schedule_timeout(session)

        logger.debug(f"Ended agent session: {session_id}")
        return session_id

    def add_agent_transcript(self, transcript: str) -> Optional[str]:
        """Add transcript to agent session."""
        session_id = self._active_agent_session

        if not session_id:
            session_id = self._find_waiting_session("agent")

        if not session_id:
            logger.warning("Creating session for late agent transcript")
            session = self._create_session("agent")
            session.set_transcript(transcript)
            session.end_speech()
            asyncio.create_task(self._upload_worker.enqueue(session))
            return session.session_id

        session = self._sessions.get(session_id)
        if session:
            session.set_transcript(transcript)

        return session_id

    def _find_waiting_session(self, role: str) -> Optional[str]:
        """Find most recent session waiting for transcript."""
        for sid in sorted(self._sessions.keys(), reverse=True):
            session = self._sessions[sid]
            if (session.role == role and
                session.state == SessionState.WAITING_TRANSCRIPT):
                return sid
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get tracker statistics."""
        return {
            "total_sessions": len(self._sessions),
            "active_user_session": self._active_user_session,
            "active_agent_session": self._active_agent_session,
            "pending_timeouts": len(self._pending_timeout_tasks),
            "sessions_by_state": {
                state.name: sum(1 for s in self._sessions.values() if s.state == state)
                for state in SessionState
            },
            "upload_worker": self._upload_worker.get_stats(),
        }
