"""
Incident schemas and contracts for the Highway Safety Autonomous Agent.
Strict Pydantic models ensuring a microservice-ready contract between:
1. Fast Edge Perception Engine
2. Cognitive Safety Agent Worker
3. External Stakeholder Dispatches (Police, NHAI, 108 EMS, VMS)
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import time
import uuid


class IncidentType(str, Enum):
    STALLED_VEHICLE = "STALLED_VEHICLE"
    TAILGATING_COLLISION_RISK = "TAILGATING_COLLISION_RISK"
    WRONG_WAY_DRIVER = "WRONG_WAY_DRIVER"
    SUDDEN_BRAKING = "SUDDEN_BRAKING"
    HIGHWAY_OBSTACLE = "HIGHWAY_OBSTACLE"


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    AGENT_ANALYZING = "AGENT_ANALYZING"
    DISPATCHED = "DISPATCHED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


class StakeholderType(str, Enum):
    HIGHWAY_PATROL_NHAI = "HIGHWAY_PATROL_NHAI"
    POLICE_CONTROL_ROOM = "POLICE_CONTROL_ROOM"
    EMERGENCY_AMBULANCE_108 = "EMERGENCY_AMBULANCE_108"
    VARIABLE_MESSAGE_SIGN_VMS = "VARIABLE_MESSAGE_SIGN_VMS"


class VehicleTelemetry(BaseModel):
    track_id: int
    label: str
    speed_kmh: float = 0.0
    box: List[float] = Field(default_factory=list)  # [x, y, w, h]
    dimensions_3d: Optional[Dict[str, float]] = None  # length_m, width_m, height_m
    ground_pos: Optional[List[float]] = None  # [x, y] in road coordinates
    license_plate: Optional[str] = None
    plate_confidence: Optional[float] = None
    crop_path: Optional[str] = None


class IncidentCandidate(BaseModel):
    """
    Compact event emitted by the edge trigger engine into the bounded queue.
    Carries telemetry and crop references, NEVER raw video frames.
    """
    incident_id: str = Field(default_factory=lambda: f"INC-{int(time.time()*1000)%1000000:06d}")
    incident_type: IncidentType
    severity: IncidentSeverity
    camera_id: str
    km_marker: str
    gps: Dict[str, float] = Field(default_factory=lambda: {"lat": 16.5412, "lng": 80.6421})
    timestamp: float = Field(default_factory=time.time)
    
    primary_track_id: int
    secondary_track_id: Optional[int] = None
    lane_id: Optional[str] = None
    
    rule_score: float = 1.0
    rule_reason: str
    
    involved_vehicles: List[VehicleTelemetry] = Field(default_factory=list)
    evidence_snapshot_path: Optional[str] = None
    evidence_clip_path: Optional[str] = None


class StakeholderDispatch(BaseModel):
    dispatch_id: str = Field(default_factory=lambda: f"DSP-{uuid.uuid4().hex[:8].upper()}")
    incident_id: str
    stakeholder: StakeholderType
    endpoint_url: str
    priority: str = "P1"  # P0, P1, P2
    payload: Dict[str, Any] = Field(default_factory=dict)
    dispatched_at: float = Field(default_factory=time.time)
    status: str = "SENT"  # SENT, ACKNOWLEDGED, FAILED
    response_code: Optional[int] = None
    response_body: Optional[str] = None


class IncidentEvent(BaseModel):
    """
    Full incident record stored in memory/DB and published to the Control Room UI.
    """
    incident_id: str
    incident_type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.DETECTED
    
    camera_id: str
    highway: str = "NH-16"
    km_marker: str
    gps: Dict[str, float]
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    
    primary_track_id: int
    secondary_track_id: Optional[int] = None
    lane_id: Optional[str] = None
    
    involved_vehicles: List[VehicleTelemetry] = Field(default_factory=list)
    
    # Agent Reasoning & Situation Briefing
    agent_briefing: Optional[str] = None
    reasoning_trace: List[str] = Field(default_factory=list)  # [Observed, Assessed, Decided, Actions]
    
    # Evidence assets
    snapshot_url: Optional[str] = None
    clip_url: Optional[str] = None
    
    # Stakeholder actions taken
    dispatches: List[StakeholderDispatch] = Field(default_factory=list)
