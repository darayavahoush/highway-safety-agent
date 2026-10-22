"""
Cognitive Reasoning Engine & Deterministic Safety Floor (Tier 0).
Generates structured situation briefings, threat assessments, and policy-guarded actions
strictly matching the frontend-backend contract.
"""

import time
from typing import Dict, List, Tuple
from app.incident_schema import (
    IncidentCandidate,
    IncidentSeverity,
    IncidentType,
    StakeholderDispatch,
    StakeholderType,
    TraceStep,
)


class SafetyPolicyEngine:
    def __init__(self, mock_base_url: str = "http://127.0.0.1:8000/mock"):
        self.base_url = mock_base_url

    def reason_and_triage(self, candidate: IncidentCandidate) -> Tuple[str, List[TraceStep], List[StakeholderDispatch]]:
        """
        Tier 0: Deterministic Rule-Based Triage & Situation Synthesis.
        Returns:
            briefing: str
            trace: List[TraceStep]
            dispatches: List[StakeholderDispatch]
        """
        now_ms = time.time() * 1000
        primary_veh = candidate.involved_vehicles[0] if candidate.involved_vehicles else None
        p_class = primary_veh.cls.capitalize() if primary_veh else "Vehicle"
        p_track = primary_veh.trackId if primary_veh else candidate.primary_track_id
        p_speed = round(primary_veh.speedKmh, 1) if primary_veh else 0.0

        trace: List[TraceStep] = []
        dispatches: List[StakeholderDispatch] = []

        if candidate.incident_type in [IncidentType.STALLED_VEHICLE, "STALLED_VEHICLE"]:
            is_shoulder = (candidate.severity in [IncidentSeverity.P2, "P2"]) or ("shoulder" in (candidate.lane_id or "").lower())
            lane_desc = candidate.lane_id or ("Emergency Shoulder" if is_shoulder else "active travel lane")

            if is_shoulder:
                briefing = (
                    f"Vehicle #{p_track} ({p_class}) parked on {lane_desc} "
                    f"at {candidate.km_marker}. Non-critical observation."
                )
                trace = [
                    TraceStep(
                        stage="observed",
                        text=f"{p_class} #{p_track} stationary in {lane_desc} for > 3.0s.",
                        at=now_ms - 800,
                    ),
                    TraceStep(
                        stage="assessed",
                        text=f"Vehicle is positioned on {lane_desc} outside active travel lanes. No immediate live-lane collision hazard.",
                        at=now_ms - 500,
                    ),
                    TraceStep(
                        stage="decided",
                        text="Logged for highway maintenance monitoring. No emergency dispatch required.",
                        at=now_ms - 200,
                    ),
                    TraceStep(
                        stage="actions",
                        text=f"Stationary observation on {lane_desc} recorded. Zero dispatches issued.",
                        at=now_ms,
                    ),
                ]
                dispatches = []
            else:
                briefing = (
                    f"Stationary {p_class} #{p_track} in {lane_desc} "
                    f"at {candidate.km_marker}. High probability of rear-end pileup."
                )
                trace = [
                    TraceStep(
                        stage="observed",
                        text=f"{p_class} #{p_track} has been stationary (0 km/h) in {lane_desc} for > 3.0s.",
                        at=now_ms - 800,
                    ),
                    TraceStep(
                        stage="assessed",
                        text=f"High-risk static obstacle in live lane ({lane_desc}). Approaching vehicles cannot brake within sight distance.",
                        at=now_ms - 500,
                    ),
                    TraceStep(
                        stage="decided",
                        text="Immediate VMS warning gantry activation (P0) + Mobilization of NHAI route patrol and towing crane.",
                        at=now_ms - 200,
                    ),
                    TraceStep(
                        stage="actions",
                        text="VMS gantry display updated. NHAI towing crane dispatched. 108 Emergency Ambulance pre-alerted.",
                        at=now_ms,
                    ),
                ]

                # 1. Immediate: VMS Gantry warning
                dispatches.append(
                    StakeholderDispatch(
                        id=f"{candidate.incident_id}-D1",
                        target=StakeholderType.VARIABLE_MESSAGE_SIGN_VMS,
                        status="sent",
                        sentAt=now_ms,
                        message=f"DANGER: STALLED {p_class.upper()} AT {candidate.km_marker} - SLOW DOWN",
                        endpoint_url=f"{self.base_url}/vms_gantry",
                        payload={
                            "gantry_id": "VMS-NH16-GANTRY-04",
                            "message_text": f"DANGER: STALLED {p_class.upper()} AT {candidate.km_marker} - SLOW DOWN",
                            "incident_id": candidate.incident_id,
                        },
                    )
                )

                # 2. Immediate: NHAI Route Patrol & Heavy Crane
                dispatches.append(
                    StakeholderDispatch(
                        id=f"{candidate.incident_id}-D2",
                        target=StakeholderType.HIGHWAY_PATROL_NHAI,
                        status="sent",
                        sentAt=now_ms,
                        message=f"Deploy route marshal and heavy recovery crane to {candidate.km_marker} for stalled {p_class}.",
                        endpoint_url=f"{self.base_url}/nhai",
                        payload={
                            "incident_id": candidate.incident_id,
                            "highway_name": "NH-16",
                            "km_marker": candidate.km_marker,
                            "lane_id": candidate.lane_id or "Fast Lane",
                            "hazard_type": "STALLED_VEHICLE_OBSTACLE",
                            "target_vehicle_class": p_class,
                            "requires_towing_crane": True,
                            "briefing": briefing,
                        },
                    )
                )

                # 3. Queued (15s cancel window): 108 Trauma Ambulance Pre-alert
                dispatches.append(
                    StakeholderDispatch(
                        id=f"{candidate.incident_id}-D3",
                        target=StakeholderType.EMS_108_AMBULANCE,
                        status="queued",
                        queuedAt=now_ms,
                        cancelUntil=now_ms + 15000,
                        message=f"Pre-alert 108 Trauma Ambulance for potential high-speed collision at {candidate.km_marker}.",
                        endpoint_url=f"{self.base_url}/ems_108",
                        payload={
                            "incident_id": candidate.incident_id,
                            "incident_type": "POTENTIAL_HIGH_SPEED_COLLISION",
                            "km_marker": candidate.km_marker,
                            "gps": candidate.gps,
                            "estimated_vehicles_count": len(candidate.involved_vehicles),
                            "trauma_risk_level": "CRITICAL",
                            "nearest_hospital": "AIIMS Mangalagiri Trauma Center",
                            "golden_hour_target_minutes": 15,
                            "briefing": briefing,
                        },
                    )
                )

        elif candidate.incident_type in [IncidentType.WRONG_WAY, "WRONG_WAY", "WRONG_WAY_DRIVER"]:
            briefing = (
                f"CRITICAL: {p_class} #{p_track} traveling in the wrong direction at {p_speed} km/h "
                f"near {candidate.km_marker}. Head-on collision imminent."
            )
            trace = [
                TraceStep(
                    stage="observed",
                    text=f"{p_class} #{p_track} observed moving against authorized flow at {p_speed} km/h.",
                    at=now_ms - 800,
                ),
                TraceStep(
                    stage="assessed",
                    text="Extreme catastrophic risk. Imminent risk of head-on collision with on-coming traffic.",
                    at=now_ms - 500,
                ),
                TraceStep(
                    stage="decided",
                    text="Immediate gantry alert broadcast + Mobilization of Highway Police Interceptor.",
                    at=now_ms - 200,
                ),
                TraceStep(
                    stage="actions",
                    text="VMS Gantries activated. Police Interceptor alerted with live coordinates.",
                    at=now_ms,
                ),
            ]

            # 1. Immediate: VMS Sign
            dispatches.append(
                StakeholderDispatch(
                    id=f"{candidate.incident_id}-D1",
                    target=StakeholderType.VARIABLE_MESSAGE_SIGN_VMS,
                    status="sent",
                    sentAt=now_ms,
                    message=f"EMERGENCY: WRONG-WAY DRIVER NEAR {candidate.km_marker} - STAY ALERT",
                    endpoint_url=f"{self.base_url}/vms_gantry",
                    payload={
                        "gantry_id": "VMS-NH16-GANTRY-04",
                        "message_text": f"EMERGENCY: WRONG-WAY DRIVER NEAR {candidate.km_marker} - STAY ALERT",
                        "incident_id": candidate.incident_id,
                    },
                )
            )

            # 2. Queued (15s cancel window): Police Control Room Dispatch
            dispatches.append(
                StakeholderDispatch(
                    id=f"{candidate.incident_id}-D2",
                    target=StakeholderType.POLICE_CONTROL_ROOM,
                    status="queued",
                    queuedAt=now_ms,
                    cancelUntil=now_ms + 15000,
                    message=f"Intercept wrong-way {p_class} traveling opposite traffic at {candidate.km_marker}.",
                    endpoint_url=f"{self.base_url}/police",
                    payload={
                        "incident_id": candidate.incident_id,
                        "camera_id": candidate.camera_id,
                        "km_marker": candidate.km_marker,
                        "gps": candidate.gps,
                        "violation_type": "WRONG_WAY_DRIVING",
                        "priority": "P0",
                        "situation_briefing": briefing,
                    },
                )
            )

        elif candidate.incident_type in [IncidentType.TAILGATING, "TAILGATING", "TAILGATING_COLLISION_RISK"]:
            sec_veh = candidate.involved_vehicles[1] if len(candidate.involved_vehicles) > 1 else None
            s_class = sec_veh.cls.capitalize() if sec_veh else "Vehicle"
            s_track = sec_veh.trackId if sec_veh else candidate.secondary_track_id
            briefing = (
                f"Aggressive tailgating: {p_class} #{p_track} following {s_class} #{s_track} "
                f"with sub-second reaction margin at {candidate.km_marker}."
            )
            trace = [
                TraceStep(
                    stage="observed",
                    text=f"{p_class} #{p_track} trailing {s_class} #{s_track} at critical Time-To-Collision headway.",
                    at=now_ms - 800,
                ),
                TraceStep(
                    stage="assessed",
                    text="Mixed traffic collision hazard. Any sudden braking will trigger catastrophic rear impact.",
                    at=now_ms - 500,
                ),
                TraceStep(
                    stage="decided",
                    text="Display safe following distance advisory on VMS and queue owner safety notice.",
                    at=now_ms - 200,
                ),
                TraceStep(
                    stage="actions",
                    text="VMS caution sent. Vehicle owner automated safety notice queued.",
                    at=now_ms,
                ),
            ]

            # 1. Immediate: VMS Caution
            dispatches.append(
                StakeholderDispatch(
                    id=f"{candidate.incident_id}-D1",
                    target=StakeholderType.VARIABLE_MESSAGE_SIGN_VMS,
                    status="sent",
                    sentAt=now_ms,
                    message="KEEP SAFE DISTANCE - DANGEROUS TAILGATING DETECTED AHEAD",
                    endpoint_url=f"{self.base_url}/vms_gantry",
                    payload={
                        "gantry_id": "VMS-NH16-GANTRY-04",
                        "message_text": "KEEP SAFE DISTANCE - DANGEROUS TAILGATING DETECTED AHEAD",
                        "incident_id": candidate.incident_id,
                    },
                )
            )

            # 2. Queued (15s cancel window): Owner Safety Notice (Track B)
            dispatches.append(
                StakeholderDispatch(
                    id=f"{candidate.incident_id}-D2",
                    target=StakeholderType.VEHICLE_OWNER_NOTICE,
                    status="queued",
                    queuedAt=now_ms,
                    cancelUntil=now_ms + 15000,
                    message=f"Send highway safety compliance advisory to registered owner of {p_class} #{p_track}.",
                    endpoint_url=f"{self.base_url}/owner_notice",
                    payload={
                        "incident_id": candidate.incident_id,
                        "plate": "PENDING_ANPR",
                        "vehicle_class": p_class,
                        "advisory_type": "DANGEROUS_TAILGATING_WARNING",
                        "km_marker": candidate.km_marker,
                    },
                )
            )

        else:
            briefing = f"Safety Alert: {candidate.rule_reason}"
            trace = [
                TraceStep(stage="observed", text=candidate.rule_reason, at=now_ms - 500),
                TraceStep(stage="assessed", text="General highway anomaly detected.", at=now_ms - 300),
                TraceStep(stage="decided", text="Log event and monitor corridor.", at=now_ms - 100),
                TraceStep(stage="actions", text="Event logged for blackspot analytics.", at=now_ms),
            ]

        return briefing, trace, dispatches
