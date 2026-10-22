"""
Queue boundary separating perception layer from cognitive agent.
Ensures zero-latency perception loop (edge tracker never blocks on agent).
Uses a bounded queue carrying compact IncidentCandidate packets.
"""

import asyncio
from typing import Optional
from app.incident_schema import IncidentCandidate


class IncidentEventQueue:
    def __init__(self, maxsize: int = 100):
        self._queue: asyncio.Queue[IncidentCandidate] = asyncio.Queue(maxsize=maxsize)
        self.dropped_events_count: int = 0

    def put_nowait(self, candidate: IncidentCandidate) -> bool:
        """
        Non-blocking put. If the queue is full, drops the oldest or logs drop,
        preventing edge perception thread from ever waiting.
        """
        try:
            self._queue.put_nowait(candidate)
            return True
        except asyncio.QueueFull:
            self.dropped_events_count += 1
            # Force pop oldest to make room for newest high-priority hazard
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(candidate)
                return True
            except Exception:
                return False

    async def get(self) -> IncidentCandidate:
        """Asynchronously waits for the next candidate to be consumed by the agent worker."""
        return await self._queue.get()

    def qsize(self) -> int:
        return self._queue.qsize()


# Global in-process queue instance
incident_queue = IncidentEventQueue(maxsize=100)
