"""
Asynchronous Cognitive Safety Agent Worker.
Handles event triage, 15-second cancel window, mock dispatch execution,
SQLite persistence, and real-time WebSocket event broadcasting.
"""

import asyncio
import json
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Callable, Any

from app.incident_schema import (
    IncidentCandidate,
    IncidentEvent,
    IncidentStatus,
    StakeholderDispatch,
)
from app.queue_boundary import incident_queue
from app import db
from agent.reasoning import SafetyPolicyEngine


class SafetyAgentWorker:
    def __init__(self, mock_base_url: str = "http://127.0.0.1:8000/mock"):
        self.policy_engine = SafetyPolicyEngine(mock_base_url=mock_base_url)
        self.is_running: bool = False
        # Broadcast callback set by main.py
        self.broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        # Track cancelled dispatches: (incident_id, dispatch_id)
        self.cancelled_dispatches: set = set()

    async def broadcast(self, payload: Dict[str, Any]):
        """Broadcasts event payload to all connected WebSocket clients."""
        if self.broadcast_callback:
            try:
                res = self.broadcast_callback(payload)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"[AgentWorker] Broadcast error: {e}")

    async def run(self):
        """Main event loop for the cognitive agent."""
        self.is_running = True
        print("[AgentWorker] Cognitive Safety Agent loop active.")
        while self.is_running:
            candidate = await incident_queue.get()
            try:
                await self.process_candidate(candidate)
            except Exception as e:
                print(f"[AgentWorker] Error processing candidate {candidate.incident_id}: {e}")

    async def process_candidate(self, candidate: IncidentCandidate) -> IncidentEvent:
        """Processes candidate through reasoning, dispatch, persistence, and broadcasting."""
        now_ms = time.time() * 1000

        # Build initial IncidentEvent
        event = IncidentEvent(
            id=candidate.incident_id,
            type=candidate.incident_type,
            severity=candidate.severity,
            status=IncidentStatus.ANALYSING,
            confidence=candidate.rule_score,
            createdAt=candidate.timestamp or now_ms,
            camera={
                "id": candidate.camera_id,
                "highway": "NH-16",
                "km": float(candidate.km_marker.replace("KM", "").strip() or 42.4),
                "lat": candidate.gps.get("lat", 16.5412),
                "lng": candidate.gps.get("lng", 80.6421),
                "towards": "Visakhapatnam",
                "opposite": "Vijayawada",
            },
            vehicles=candidate.involved_vehicles,
            snapshot_url=candidate.evidence_snapshot_path,
            clip_url=candidate.evidence_clip_path,
        )

        # Broadcast initial "analysing" status
        await self.broadcast({"incident": event.to_contract_dict()})
        db.upsert_incident(event.to_contract_dict())

        # Perform reasoning
        t_reason_start = time.time()
        briefing, trace, dispatches = self.policy_engine.reason_and_triage(candidate)
        t_reason_end = time.time()
        event.briefing = briefing
        event.trace = trace
        event.dispatches = dispatches
        if dispatches:
            event.status = IncidentStatus.DISPATCHED
        elif candidate.severity in ["P2", IncidentSeverity.P2]:
            event.status = IncidentStatus.MONITORING
        else:
            event.status = IncidentStatus.DETECTED

        # Record agent dispatch latency metrics
        agent_latency_ms = round((t_reason_end - t_reason_start) * 1000.0, 1)
        detect_to_dispatch_s = round((t_reason_end * 1000.0 - (candidate.timestamp or now_ms)) / 1000.0, 2)
        try:
            from app.system_status import system_status_reporter
            system_status_reporter.record_agent_dispatch_latency(
                agent_latency_ms=agent_latency_ms,
                detect_to_dispatch_s=max(0.1, detect_to_dispatch_s),
            )
        except Exception:
            pass

        # Execute immediate dispatches (VMS, NHAI)
        for d in event.dispatches:
            if d.status == "sent":
                self._execute_dispatch(d)

        # Persist and broadcast dispatched state
        contract_dict = event.to_contract_dict()
        db.upsert_incident(contract_dict)
        await self.broadcast({"incident": contract_dict})

        # Launch background tasks for queued dispatches (15s cancel window)
        for d in event.dispatches:
            if d.status == "queued":
                asyncio.create_task(self._handle_queued_dispatch(event.id, d))

        return event

    async def _enrich_with_parallel_ai(self, event: IncidentEvent):
        """Asynchronously grounds incident with live road/corridor intelligence via Parallel AI."""
        try:
            from agent.parallel_client import parallel_client
            loop = asyncio.get_event_loop()
            intel = await loop.run_in_executor(
                None,
                parallel_client.get_corridor_intel,
                "NH-16 Amaravati Corridor",
                f"KM {event.camera.get('km', 42.4)}",
                str(event.type),
            )
            if intel:
                now_ms = time.time() * 1000
                from app.incident_schema import TraceStep
                step = TraceStep(stage="context", text=intel, at=now_ms)
                event.trace.append(step)
                contract_dict = event.to_contract_dict()
                db.upsert_incident(contract_dict)
                await self.broadcast({"incident": contract_dict})
        except Exception as e:
            print(f"[AgentWorker] Parallel AI enrichment notice: {e}")

    async def _handle_queued_dispatch(self, incident_id: str, dispatch: StakeholderDispatch):
        """Waits 15 seconds for operator cancellation before sending to mock endpoint."""
        wait_seconds = 15.0
        print(f"[AgentWorker] Dispatch {dispatch.id} to {dispatch.target} queued with 15s cancel window.")
        await asyncio.sleep(wait_seconds)

        # Check if cancelled by operator
        if (incident_id, dispatch.id) in self.cancelled_dispatches:
            print(f"[AgentWorker] Dispatch {dispatch.id} was CANCELLED by operator. Skipping mock POST.")
            return

        # Not cancelled: execute dispatch
        now_ms = time.time() * 1000
        dispatch.status = "sent"
        dispatch.sentAt = now_ms
        self._execute_dispatch(dispatch)
        print(f"[AgentWorker] Dispatch {dispatch.id} to {dispatch.target} SENT to mock endpoint (Status: {dispatch.status}).")

        # Update DB and broadcast
        incidents = db.get_all_incidents()
        for inc in incidents:
            if inc["id"] == incident_id:
                for d in inc.get("dispatches", []):
                    if d["id"] == dispatch.id:
                        d["status"] = dispatch.status
                        d["sentAt"] = dispatch.sentAt
                        d["ackAt"] = dispatch.ackAt
                db.upsert_incident(inc)
                await self.broadcast({"incident": inc})
                break

    def cancel_dispatch(self, incident_id: str, dispatch_id: str) -> bool:
        """Operator cancellation within the 15s window."""
        self.cancelled_dispatches.add((incident_id, dispatch_id))
        ok = db.cancel_dispatch(incident_id, dispatch_id)
        print(f"[AgentWorker] Operator cancelled dispatch {dispatch_id} for {incident_id}. (Success={ok})")
        return ok

    def _execute_dispatch(self, dispatch: StakeholderDispatch):
        """Executes dispatch via mock dispatch handlers and simulates realistic acknowledgement."""
        try:
            target_val = dispatch.target.value if hasattr(dispatch.target, "value") else str(dispatch.target)
            now_ms = time.time() * 1000
            
            if "VMS" in target_val:
                from app.mock_dispatch import VMSDisplayPayload, mock_vms_dispatch
                res = mock_vms_dispatch(VMSDisplayPayload(**dispatch.payload))
            elif "NHAI" in target_val:
                from app.mock_dispatch import NHAIDispatchPayload, mock_nhai_dispatch
                res = mock_nhai_dispatch(NHAIDispatchPayload(**dispatch.payload))
            elif "POLICE" in target_val:
                from app.mock_dispatch import PoliceDispatchPayload, mock_police_dispatch
                res = mock_police_dispatch(PoliceDispatchPayload(**dispatch.payload))
            elif "EMS" in target_val or "AMBULANCE" in target_val:
                from app.mock_dispatch import EMS108DispatchPayload, mock_ems_dispatch
                res = mock_ems_dispatch(EMS108DispatchPayload(**dispatch.payload))
            elif "OWNER" in target_val or "NOTICE" in target_val:
                from app.mock_dispatch import mock_owner_notice_dispatch
                res = mock_owner_notice_dispatch(dispatch.payload)
            else:
                res = {"status": "SUCCESS", "message": "Dispatched to stakeholder"}

            dispatch.response_code = 200
            dispatch.response_body = json.dumps(res)
            dispatch.ackAt = now_ms + 1200
            dispatch.status = "acknowledged"
        except Exception as e:
            dispatch.response_code = 500
            dispatch.response_body = str(e)
            dispatch.status = "failed"


# Global worker instance
agent_worker = SafetyAgentWorker()
