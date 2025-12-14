"""
Async upload worker for processing queued items.

This module provides a reusable worker pattern that can be used
for uploading transcripts or any other async processing task.
"""
import asyncio
from typing import Callable, Any, Optional, Protocol, Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class Uploadable(Protocol):
    """Protocol for items that can be uploaded."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert item to dictionary for upload."""
        ...


@dataclass
class UploadWorkerConfig:
    """Configuration for the upload worker."""
    max_queue_size: int = 100
    shutdown_timeout: float = 30.0
    poll_interval: float = 1.0  # How often to check for shutdown when idle


class UploadWorker:
    """
    Async worker that processes items from a queue and uploads them.

    Features:
    - Single worker with controlled concurrency
    - Backpressure via bounded queue
    - Graceful shutdown with configurable timeout
    - Supports both sync and async upload callbacks

    Usage:
        async def my_upload_fn(data: dict):
            await http_client.post("/upload", json=data)

        worker = UploadWorker(upload_callback=my_upload_fn)
        await worker.start()

        await worker.enqueue(my_item)

        await worker.stop()
    """

    def __init__(
        self,
        upload_callback: Callable[[Dict[str, Any]], Any],
        config: Optional[UploadWorkerConfig] = None,
        on_success: Optional[Callable[[Uploadable], None]] = None,
        on_failure: Optional[Callable[[Uploadable, Exception], None]] = None,
    ):
        """
        Initialize the upload worker.

        Args:
            upload_callback: Function to call for each upload. Can be sync or async.
                           Receives the dict from item.to_dict().
            config: Worker configuration. Uses defaults if not provided.
            on_success: Optional callback when upload succeeds.
            on_failure: Optional callback when upload fails.
        """
        self.upload_callback = upload_callback
        self.config = config or UploadWorkerConfig()
        self.on_success = on_success
        self.on_failure = on_failure

        # Queue for items pending upload
        self._queue: asyncio.Queue[Uploadable] = asyncio.Queue(
            maxsize=self.config.max_queue_size
        )

        # Worker state
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Check if worker is currently running."""
        return self._is_running

    @property
    def pending_count(self) -> int:
        """Number of items waiting in queue."""
        return self._queue.qsize()

    @property
    def is_idle(self) -> bool:
        """Check if worker has no pending items."""
        return self._queue.empty()

    async def start(self):
        """Start the upload worker."""
        if self._is_running:
            logger.warning("UploadWorker already running")
            return

        self._shutdown_event.clear()
        self._is_running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("UploadWorker started")

    async def stop(self):
        """
        Gracefully stop the worker.

        Waits for pending uploads to complete (up to shutdown_timeout).
        """
        if not self._is_running:
            logger.warning("UploadWorker not running")
            return

        logger.info("Stopping UploadWorker...")
        self._shutdown_event.set()

        # Wait for queue to drain
        if not self._queue.empty():
            pending = self._queue.qsize()
            logger.info(f"Waiting for {pending} pending uploads to complete...")
            try:
                await asyncio.wait_for(
                    self._queue.join(),
                    timeout=self.config.shutdown_timeout
                )
                logger.info("All pending uploads completed")
            except asyncio.TimeoutError:
                logger.warning(
                    f"Shutdown timeout ({self.config.shutdown_timeout}s) reached. "
                    f"{self._queue.qsize()} uploads may be lost."
                )

        # Cancel worker task
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        self._is_running = False
        logger.info("UploadWorker stopped")

    async def enqueue(self, item: Uploadable):
        """
        Add an item to the upload queue.

        Args:
            item: Item to upload. Must implement to_dict() method.

        Raises:
            RuntimeError: If worker is not running.

        Note:
            This will block if queue is full (backpressure).
        """
        if not self._is_running:
            raise RuntimeError("Cannot enqueue: UploadWorker is not running")

        await self._queue.put(item)
        logger.debug(f"Enqueued item. Queue size: {self._queue.qsize()}")

    def enqueue_nowait(self, item: Uploadable) -> bool:
        """
        Add an item to the queue without waiting.

        Args:
            item: Item to upload.

        Returns:
            True if enqueued successfully, False if queue is full.

        Raises:
            RuntimeError: If worker is not running.
        """
        if not self._is_running:
            raise RuntimeError("Cannot enqueue: UploadWorker is not running")

        try:
            self._queue.put_nowait(item)
            logger.debug(f"Enqueued item. Queue size: {self._queue.qsize()}")
            return True
        except asyncio.QueueFull:
            logger.warning("Upload queue is full. Item dropped.")
            return False

    async def _worker_loop(self):
        """Main worker loop that processes the queue."""
        logger.debug("Worker loop started")

        while not self._shutdown_event.is_set():
            try:
                # Wait for item with timeout to allow shutdown checks
                try:
                    item = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=self.config.poll_interval
                    )
                except asyncio.TimeoutError:
                    # No item available, loop back to check shutdown
                    continue

                # Process the item
                await self._process_item(item)

            except asyncio.CancelledError:
                logger.debug("Worker loop cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {e}", exc_info=True)

        logger.debug("Worker loop ended")

    async def _process_item(self, item: Uploadable):
        """Process a single item from the queue."""
        try:
            item_dict = item.to_dict()
            await self._do_upload(item_dict)

            logger.debug(f"Upload successful for item")

            if self.on_success:
                try:
                    self.on_success(item)
                except Exception as e:
                    logger.error(f"on_success callback error: {e}")

        except Exception as e:
            logger.error(f"Upload failed: {e}")

            if self.on_failure:
                try:
                    self.on_failure(item, e)
                except Exception as callback_error:
                    logger.error(f"on_failure callback error: {callback_error}")
        finally:
            self._queue.task_done()

    async def _do_upload(self, data: Dict[str, Any]):
        """Execute the upload callback (handles both sync and async)."""
        result = self.upload_callback(data)
        if asyncio.iscoroutine(result):
            await result

    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        return {
            "is_running": self._is_running,
            "pending_count": self._queue.qsize(),
            "max_queue_size": self.config.max_queue_size,
            "is_idle": self._queue.empty(),
        }

