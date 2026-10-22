"""
Asynchronous Cognitive Safety Agent Worker.
Consumes incident candidates from the bounded queue, runs cognitive/deterministic triage,
dispatches to government stakeholder endpoints, and records audit trails.
"""

import asyncio
import json
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional

from app.incident_schema import (
    IncidentCandidate,
    IncidentEvent,
    IncidentStatus,
    StakeholderDispatch,
)
from app.queue_boundary import incident_queue
from agent.reasoning import SafetyPolicyEngine


class SafetyAgentWorker:
    def __init__(self, mock_base_url: str = "http://127.0.0.1:8000/mock"):
        self.policy_engine = SafetyPolicyEngine(mock_base_url=mock_base_url)
        self.incidents_store: Dict[str, IncidentEvent] = {}
        self.is_running: bool = False

    async def run(self):
        """Main event loop for the cognitive agent."""
        self.is_running = True
        while self.is_running:
            candidate = await incident_queue.get()
            try:
                await self.process_candidate(candidate)
            except Exception as e:
                print(f"[AgentWorker] Error processing incident {candidate.incident_id}: {e}")

    async def process_candidate(self, candidate: IncidentCandidate) -> IncidentEvent:
        """Processes a candidate through reasoning, dispatch, and storage."""
        briefing, trace, dispatches = self.policy_engine.reason_and_triage(candidate)

        # Dispatch to mock endpoints asynchronously
        for d in dispatches:
            self._execute_dispatch(d)

        # Build full IncidentEvent record
        event = IncidentEvent(
            incident_id=candidate.incident_id,
            incident_type=candidate.incident_type,
            severity=candidate.severity,
            status=IncidentStatus.DISPATCHED,
            camera_id=candidate.camera_id,
            km_marker=candidate.km_marker,
            gps=candidate.gps,
            primary_track_id=candidate.primary_track_id,
            secondary_track_id=candidate.secondary_track_id,
            lane_id=candidate.lane_id,
            involved_vehicles=candidate.involved_vehicles,
            agent_briefing=briefing,
            reasoning_trace=trace,
            snapshot_url=candidate.evidence_snapshot_path,
            clip_url=candidate.evidence_clip_path,
            dispatches=dispatches,
        )

        self.incidents_store[candidate.incident_id] = event
        return event

    def _execute_dispatch(self, dispatch: StakeholderDispatch):
        """Sends HTTP POST to the stakeholder endpoint."""
        try:
            req_data = json.dumps(dispatch.payload).encode("utf-8")
            req = urllib.request.Request(
                dispatch.endpoint_url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                dispatch.response_code = resp.status
                dispatch.response_body = resp.read().decode("utf-8")
                dispatch.status = "ACKNOWLEDGED"
        except urllib.error.HTTPError as e:
            dispatch.response_code = e.code
            dispatch.response_body = e.read().decode("utf-8")
            dispatch.status = "FAILED"
        except Exception as e:
            dispatch.response_code = 500
            dispatch.response_body = str(e)
            dispatch.status = "FAILED"

    def get_all_incidents(self) -> List[IncidentEvent]:
        return list(self.incidents_store.values())


# Global worker instance
agent_worker = SafetyAgentWorker()
