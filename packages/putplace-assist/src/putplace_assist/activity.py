"""Activity streaming for putplace-assist.

Provides SSE and WebSocket endpoints for real-time activity updates.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncIterator, Optional

from .database import db
from .models import ActivityEvent, EventType

logger = logging.getLogger(__name__)


class ActivityManager:
    """Manages activity event streaming to clients."""

    def __init__(self, poll_interval: float = 1.0):
        """Initialize activity manager.

        Args:
            poll_interval: Interval for polling new events in seconds
        """
        self.poll_interval = poll_interval
        self._subscribers: set[asyncio.Queue] = set()
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._last_event_id: int = 0

    async def start(self) -> None:
        """Start the activity polling task."""
        if self._running:
            return

        logger.info("Starting activity manager...")
        self._running = True

        # Get the last event ID
        events, _ = await db.get_activity(limit=1)
        if events:
            self._last_event_id = events[0].id

        # Start polling task
        self._poll_task = asyncio.create_task(self._poll_events())
        logger.info("Activity manager started")

    async def stop(self) -> None:
        """Stop the activity polling task."""
        if not self._running:
            return

        logger.info("Stopping activity manager...")
        self._running = False

        # Send shutdown event to all connected clients before closing
        if self._subscribers:
            from .models import ActivityEvent, EventType
            from datetime import datetime

            shutdown_event = ActivityEvent(
                event_type=EventType.ERROR,
                message="Server is shutting down",
                timestamp=datetime.utcnow(),
                details={"reason": "restart"}
            )

            # Notify all subscribers
            for queue in self._subscribers:
                try:
                    queue.put_nowait(shutdown_event)
                except asyncio.QueueFull:
                    pass  # Skip if queue is full

            # Give clients a moment to receive the shutdown event
            await asyncio.sleep(0.1)

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        # Clear subscribers
        self._subscribers.clear()
        logger.info("Activity manager stopped")

    async def _poll_events(self) -> None:
        """Poll for new events and broadcast to subscribers."""
        while self._running:
            try:
                # Get new events since last check
                events, _ = await db.get_activity(
                    limit=100,
                    since_id=self._last_event_id,
                )

                if events:
                    # Update last event ID (events are in DESC order)
                    self._last_event_id = max(e.id for e in events)

                    # Broadcast to subscribers (in chronological order)
                    for event in reversed(events):
                        await self._broadcast(event)

                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error polling events: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _broadcast(self, event: ActivityEvent) -> None:
        """Broadcast an event to all subscribers."""
        dead_subscribers = set()

        for queue in self._subscribers:
            try:
                await queue.put(event)
            except Exception:
                dead_subscribers.add(queue)

        # Remove dead subscribers
        self._subscribers -= dead_subscribers

    def subscribe(self) -> asyncio.Queue[ActivityEvent]:
        """Subscribe to activity events.

        Returns:
            Queue that will receive activity events
        """
        queue: asyncio.Queue[ActivityEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        logger.debug(f"New subscriber added, total: {len(self._subscribers)}")
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from activity events."""
        self._subscribers.discard(queue)
        logger.debug(f"Subscriber removed, total: {len(self._subscribers)}")

    @property
    def subscriber_count(self) -> int:
        """Get number of active subscribers."""
        return len(self._subscribers)

    async def emit(
        self,
        event_type: EventType,
        filepath: Optional[str] = None,
        path_id: Optional[int] = None,
        message: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> int:
        """Emit an activity event.

        This is the preferred method for components to log activity.
        It logs to the database and the event will be broadcast to subscribers.

        Args:
            event_type: Type of event
            filepath: Optional associated filepath
            path_id: Optional associated path ID
            message: Event message
            details: Optional additional details

        Returns:
            ID of the created event
        """
        return await db.log_activity(
            event_type=event_type,
            filepath=filepath,
            path_id=path_id,
            message=message,
            details=details,
        )


# Global activity manager
activity_manager = ActivityManager()


def event_to_sse(event: ActivityEvent) -> str:
    """Convert an ActivityEvent to SSE format.

    Args:
        event: The activity event

    Returns:
        SSE-formatted string
    """
    data = {
        "id": event.id,
        "event_type": event.event_type.value,
        "filepath": event.filepath,
        "path_id": event.path_id,
        "message": event.message,
        "details": event.details,
        "created_at": event.created_at.isoformat(),
    }

    return f"id: {event.id}\nevent: {event.event_type.value}\ndata: {json.dumps(data)}\n\n"


def event_to_json(event: ActivityEvent) -> dict:
    """Convert an ActivityEvent to JSON-serializable dict.

    Args:
        event: The activity event

    Returns:
        Dictionary representation
    """
    return {
        "id": event.id,
        "event_type": event.event_type.value,
        "filepath": event.filepath,
        "path_id": event.path_id,
        "message": event.message,
        "details": event.details,
        "created_at": event.created_at.isoformat(),
    }


async def stream_activity_sse(
    event_type: Optional[EventType] = None,
) -> AsyncIterator[str]:
    """Stream activity events as SSE.

    Args:
        event_type: Optional filter for specific event types

    Yields:
        SSE-formatted event strings
    """
    # Subscribe to events
    queue = activity_manager.subscribe()

    try:
        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'timestamp': datetime.utcnow().isoformat()})}\n\n"

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)

                # Filter by event type if specified
                if event_type and event.event_type != event_type:
                    continue

                yield event_to_sse(event)

            except asyncio.TimeoutError:
                # Send keepalive
                yield f": keepalive {datetime.utcnow().isoformat()}\n\n"
            except asyncio.CancelledError:
                break

    finally:
        activity_manager.unsubscribe(queue)


async def get_recent_activity(
    limit: int = 50,
    event_type: Optional[EventType] = None,
) -> list[dict]:
    """Get recent activity events.

    Args:
        limit: Maximum number of events to return
        event_type: Optional filter for specific event types

    Returns:
        List of event dictionaries
    """
    events, _ = await db.get_activity(limit=limit, event_type=event_type)
    return [event_to_json(event) for event in events]
