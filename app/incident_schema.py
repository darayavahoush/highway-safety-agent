"""
Incident schemas and contracts for the Highway Safety Autonomous Agent.
Strict Pydantic models matching the Frontend-Backend Contract (src/api/CONTRACT.md).
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import time
import uuid


class IncidentType(str, Enum):
    STALLED_VEHICLE = "STALLED_VEHICLE"
    TAILGATING = "TAILGATING"
    WRONG_WAY = "WRONG_WAY"
    IMPACT = "IMPACT"
    FEEDER_INTRUSION = "FEEDER_INTRUSION"
    # Aliases
    TAILGATING_COLLISION_RISK = "TAILGATING"
    WRONG_WAY_DRIVER = "WRONG_WAY"
    SUDDEN_BRAKING = "IMPACT"
    FEEDER_ROAD_INTRUSION = "FEEDER_INTRUSION"


class IncidentSeverity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    # Legacy aliases
    CRITICAL = "P0"
    HIGH = "P1"
    MEDIUM = "P2"
    LOW = "P2"


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    ANALYSING = "analysing"
    DISPATCHED = "dispatched"
    MONITORING = "monitoring"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    FALSE_ALARM = "false_alarm"
    # Legacy aliases
    AGENT_ANALYZING = "analysing"
    CANCELLED = "resolved"


class StakeholderType(str, Enum):
    VARIABLE_MESSAGE_SIGN_VMS = "VARIABLE_MESSAGE_SIGN_VMS"
    HIGHWAY_PATROL_NHAI = "HIGHWAY_PATROL_NHAI"
    POLICE_CONTROL_ROOM = "POLICE_CONTROL_ROOM"
    EMS_108_AMBULANCE = "EMS_108_AMBULANCE"
    VEHICLE_OWNER_NOTICE = "VEHICLE_OWNER_NOTICE"
    # Legacy alias
    EMERGENCY_AMBULANCE_108 = "EMS_108_AMBULANCE"


class TraceStep(BaseModel):
    stage: str  # "observed", "assessed", "decided", "actions"
    text: str
    at: float = Field(default_factory=lambda: time.time() * 1000)


class VehicleTelemetry(BaseModel):
    trackId: int = Field(default=1)
    cls: str = Field(default="car")  # car, truck, van, bus, motorbike
    speedKmh: float = Field(default=0.0)
    lane: Optional[str] = None
    laneIndex: int = 1
    x: float = 0.5  # 0 to 1 position along road
    dir: int = 1  # 1 with traffic, -1 wrong way
    plate: Optional[Dict[str, Any]] = None  # null until ANPR exists!
    
    # Internal fields for 3D/bounding boxes
    box: List[float] = Field(default_factory=list)
    ground_pos: Optional[List[float]] = None

    # Backward compatibility properties
    @property
    def track_id(self) -> int:
        return self.trackId

    @property
    def label(self) -> str:
        return self.cls.capitalize()

    @property
    def speed_kmh(self) -> float:
        return self.speedKmh


class StakeholderDispatch(BaseModel):
    id: str = Field(default_factory=lambda: f"DSP-{uuid.uuid4().hex[:6].upper()}")
    target: StakeholderType
    status: str = "sent"  # "queued", "sent", "acknowledged", "cancelled"
    message: str = ""
    queuedAt: Optional[float] = None  # ms
    sentAt: Optional[float] = None    # ms
    ackAt: Optional[float] = None     # ms
    cancelUntil: Optional[float] = None  # ms
    
    # Internal execution details
    endpoint_url: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_code: Optional[int] = None
    response_body: Optional[str] = None

    # Backward compatibility properties
    @property
    def dispatch_id(self) -> str:
        return self.id

    @property
    def stakeholder(self) -> StakeholderType:
        return self.target


class IncidentCandidate(BaseModel):
    """
    Compact event emitted by the edge trigger engine into the bounded queue.
    """
    incident_id: str = Field(default_factory=lambda: f"INC-{int(time.time()*1000)%1000000:06d}")
    incident_type: IncidentType
    severity: IncidentSeverity
    camera_id: str
    km_marker: str
    gps: Dict[str, float] = Field(default_factory=lambda: {"lat": 16.5412, "lng": 80.6421})
    timestamp: float = Field(default_factory=lambda: time.time() * 1000)
    
    primary_track_id: int
    secondary_track_id: Optional[int] = None
    lane_id: Optional[str] = None
    
    rule_score: float = 1.0
    rule_reason: str
    
    involved_vehicles: List[VehicleTelemetry] = Field(default_factory=list)
    evidence_snapshot_path: Optional[str] = None
    evidence_clip_path: Optional[str] = None
    evidence_details: Dict[str, Any] = Field(default_factory=dict)


class IncidentEvent(BaseModel):
    """
    Full incident record stored in SQLite and broadcast to the frontend.
    Matches src/api/CONTRACT.md exactly.
    """
    id: str
    type: IncidentType
    severity: IncidentSeverity = IncidentSeverity.P1
    status: IncidentStatus = IncidentStatus.DETECTED
    confidence: float = 0.92
    createdAt: float = Field(default_factory=lambda: time.time() * 1000)
    
    camera: Dict[str, Any] = Field(default_factory=dict)
    vehicles: List[VehicleTelemetry] = Field(default_factory=list)
    briefing: str = ""
    trace: List[TraceStep] = Field(default_factory=list)
    dispatches: List[StakeholderDispatch] = Field(default_factory=list)
    verdict: Optional[str] = None  # None, "confirmed", "false_alarm"
    
    # Evidence URLs
    snapshot_url: Optional[str] = None
    clip_url: Optional[str] = None

    # Backward compatibility properties
    @property
    def incident_id(self) -> str:
        return self.id

    @property
    def incident_type(self) -> IncidentType:
        return self.type

    @property
    def agent_briefing(self) -> str:
        return self.briefing

    @property
    def reasoning_trace(self) -> List[str]:
        return [f"{s.stage.upper()}: {s.text}" for s in self.trace]

    @property
    def primary_track_id(self) -> int:
        return self.vehicles[0].trackId if self.vehicles else 1

    @property
    def secondary_track_id(self) -> Optional[int]:
        return self.vehicles[1].trackId if len(self.vehicles) > 1 else None

    @property
    def lane_id(self) -> Optional[str]:
        return self.vehicles[0].lane if self.vehicles else None

    @property
    def camera_id(self) -> str:
        return self.camera.get("id", "CAM-01")

    @property
    def km_marker(self) -> str:
        return str(self.camera.get("km", "42.4"))

    @property
    def gps(self) -> Dict[str, float]:
        return {"lat": self.camera.get("lat", 16.5412), "lng": self.camera.get("lng", 80.6421)}

    def to_contract_dict(self) -> Dict[str, Any]:
        """Returns JSON shape strictly matching CONTRACT.md."""
        return {
            "id": self.id,
            "type": self.type.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "confidence": round(self.confidence, 2),
            "createdAt": int(self.createdAt),
            "camera": self.camera,
            "vehicles": [
                {
                    "trackId": v.trackId,
                    "cls": v.cls,
                    "speedKmh": round(v.speedKmh, 1),
                    "lane": v.lane or "Lane 1",
                    "laneIndex": v.laneIndex,
                    "x": round(v.x, 2),
                    "dir": v.dir,
                    "plate": v.plate,  # null until ANPR
                }
                for v in self.vehicles
            ],
            "briefing": self.briefing,
            "trace": [
                {
                    "stage": s.stage,
                    "text": s.text,
                    "at": int(s.at),
                }
                for s in self.trace
            ],
            "dispatches": [
                {
                    "id": d.id,
                    "target": d.target.value,
                    "status": d.status,
                    "message": d.message,
                    "queuedAt": int(d.queuedAt) if d.queuedAt else None,
                    "sentAt": int(d.sentAt) if d.sentAt else None,
                    "ackAt": int(d.ackAt) if d.ackAt else None,
                    "cancelUntil": int(d.cancelUntil) if d.cancelUntil else None,
                }
                for d in self.dispatches
            ],
            "verdict": self.verdict,
            "snapshot_url": self.snapshot_url,
            "clip_url": self.clip_url,
        }
