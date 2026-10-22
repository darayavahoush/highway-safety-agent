"""
Mocked Government & Emergency REST Endpoints.
Simulates real API gateways for:
1. Andhra Pradesh Highway Police Control Room (Dial 112 / Interceptor)
2. NHAI Highway Route Patrol & Crane / Towing Service (1033)
3. 108 Emergency Medical Services (Golden Hour Trauma Ambulance)
4. Highway Variable Message LED Signs (VMS Gantry)

All calls return realistic government API responses and are logged for auditability.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import time
import uuid
from typing import Dict, List, Optional, Any

router = APIRouter(prefix="/mock", tags=["Mock Stakeholder APIs"])

# Audit log in memory
DISPATCH_AUDIT_LOG: List[Dict[str, Any]] = []


class PoliceDispatchPayload(BaseModel):
    incident_id: str
    camera_id: str
    km_marker: str
    gps: Dict[str, float]
    violation_type: str
    involved_plates: List[str] = Field(default_factory=list)
    evidence_snapshot_url: Optional[str] = None
    priority: str = "P1"
    situation_briefing: str


class NHAIDispatchPayload(BaseModel):
    incident_id: str
    highway_name: str
    km_marker: str
    lane_id: str
    hazard_type: str
    target_vehicle_class: str
    requires_towing_crane: bool = True
    evidence_snapshot_url: Optional[str] = None
    briefing: str


class EMS108DispatchPayload(BaseModel):
    incident_id: str
    incident_type: str
    km_marker: str
    gps: Dict[str, float]
    estimated_vehicles_count: int
    trauma_risk_level: str  # HIGH, CRITICAL
    nearest_hospital: str
    golden_hour_target_minutes: int = 15
    briefing: str


class VMSDisplayPayload(BaseModel):
    gantry_id: str
    message_text: str
    duration_seconds: int = 120
    incident_id: str
    amber_flash: bool = True


@router.post("/police")
def mock_police_dispatch(payload: PoliceDispatchPayload):
    ticket_id = f"AP-POLICE-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "stakeholder": "POLICE_CONTROL_ROOM",
        "ticket_id": ticket_id,
        "incident_id": payload.incident_id,
        "timestamp": time.time(),
        "payload": payload.model_dump(),
        "status": "DISPATCHED_TO_INTERCEPTOR",
    }
    DISPATCH_AUDIT_LOG.append(record)
    return {
        "status": "SUCCESS",
        "ticket_id": ticket_id,
        "dispatched_unit": "Mangalagiri Highway Patrol Interceptor #4",
        "eta_minutes": 4.5,
        "message": f"Police alert registered for {payload.violation_type} at {payload.km_marker}.",
    }


@router.post("/nhai")
def mock_nhai_dispatch(payload: NHAIDispatchPayload):
    ticket_id = f"NHAI-PATROL-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "stakeholder": "HIGHWAY_PATROL_NHAI",
        "ticket_id": ticket_id,
        "incident_id": payload.incident_id,
        "timestamp": time.time(),
        "payload": payload.model_dump(),
        "status": "PATROL_AND_CRANE_DISPATCHED",
    }
    DISPATCH_AUDIT_LOG.append(record)
    return {
        "status": "SUCCESS",
        "ticket_id": ticket_id,
        "dispatched_crane": "Kaza Toll Plaza Heavy Recovery Crane #1",
        "route_patrol_vehicle": "NH-16 Route Marshal AP-07",
        "eta_minutes": 6.0,
        "message": f"NHAI route patrol mobilized to clear {payload.lane_id}.",
    }


@router.post("/ems_108")
def mock_ems_dispatch(payload: EMS108DispatchPayload):
    ticket_id = f"EMS108-AP-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "stakeholder": "EMERGENCY_AMBULANCE_108",
        "ticket_id": ticket_id,
        "incident_id": payload.incident_id,
        "timestamp": time.time(),
        "payload": payload.model_dump(),
        "status": "AMBULANCE_DISPATCHED",
    }
    DISPATCH_AUDIT_LOG.append(record)
    return {
        "status": "SUCCESS",
        "ticket_id": ticket_id,
        "ambulance_id": "AP-108-AMB-209",
        "destination_hospital": payload.nearest_hospital,
        "priority_corridor": "ACTIVE",
        "eta_minutes": 8.0,
        "message": f"108 Trauma Ambulance dispatched. Golden Hour protocol active.",
    }


@router.post("/vms_gantry")
def mock_vms_dispatch(payload: VMSDisplayPayload):
    ticket_id = f"VMS-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "stakeholder": "VARIABLE_MESSAGE_SIGN_VMS",
        "ticket_id": ticket_id,
        "incident_id": payload.incident_id,
        "timestamp": time.time(),
        "payload": payload.model_dump(),
        "status": "DISPLAY_ACTIVATED",
    }
    DISPATCH_AUDIT_LOG.append(record)
    return {
        "status": "SUCCESS",
        "ticket_id": ticket_id,
        "gantry_id": payload.gantry_id,
        "active_message": payload.message_text,
        "message": f"VMS Display on {payload.gantry_id} updated with warning: '{payload.message_text}'",
    }


@router.post("/owner_notice")
def mock_owner_notice_dispatch(payload: Dict[str, Any]):
    notice_id = f"AP-NOTICE-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "stakeholder": "VEHICLE_OWNER_NOTICE",
        "notice_id": notice_id,
        "incident_id": payload.get("incident_id"),
        "timestamp": time.time(),
        "payload": payload,
        "status": "NOTICE_SENT_TO_PARIVAHAN",
    }
    DISPATCH_AUDIT_LOG.append(record)
    return {
        "status": "SUCCESS",
        "notice_id": notice_id,
        "channel": "SMS_AND_M_PARIVAHAN",
        "message": f"Owner safety notice & advisory queued for {payload.get('plate', 'registered owner')}.",
    }


@router.get("/audit_log")
def get_dispatch_audit_log():
    return {"total_dispatches": len(DISPATCH_AUDIT_LOG), "dispatches": DISPATCH_AUDIT_LOG}
