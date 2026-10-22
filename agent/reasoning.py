"""
Cognitive Reasoning Engine & Deterministic Safety Floor (Tier 0).
Generates structured situation briefings, threat assessments, and policy-guarded actions.
Never blocks life-safety alerts on an LLM API call.
"""

from typing import Dict, List, Tuple
from app.incident_schema import (
    IncidentCandidate,
    IncidentSeverity,
    IncidentType,
    StakeholderDispatch,
    StakeholderType,
)
import time


class SafetyPolicyEngine:
    def __init__(self, mock_base_url: str = "http://127.0.0.1:8000/mock"):
        self.base_url = mock_base_url

    def reason_and_triage(self, candidate: IncidentCandidate) -> Tuple[str, List[str], List[StakeholderDispatch]]:
        """
        Tier 0: Deterministic Rule-Based Triage & Situation Synthesis.
        Returns:
            briefing: str
            reasoning_trace: List[str] [Observed, Assessed, Decided, Actions]
            dispatches: List[StakeholderDispatch]
        """
        primary_veh = candidate.involved_vehicles[0] if candidate.involved_vehicles else None
        p_class = primary_veh.label if primary_veh else "Vehicle"
        p_speed = primary_veh.speed_kmh if primary_veh else 0.0

        trace = []
        dispatches = []

        if candidate.incident_type == IncidentType.STALLED_VEHICLE:
            briefing = (
                f"ALERT: A {p_class} (Track #{candidate.primary_track_id}) is stationary in the "
                f"{candidate.lane_id or 'active lane'} at {candidate.km_marker}. "
                f"Severe hazard of high-speed rear-end collision."
            )
            trace = [
                f"OBSERVED: {p_class} #{candidate.primary_track_id} stationary (speed: {p_speed} km/h) in active roadway for > 3.0 seconds.",
                f"ASSESSED: High-severity static obstacle. Fast highway traffic cannot brake in time without advance warning.",
                f"DECIDED: Immediate VMS warning gantry activation (P0) + Mobilization of NHAI route patrol and towing crane.",
                f"ACTIONS: Dispatched VMS Display and NHAI Towing Unit.",
            ]
            # Action 1: VMS Sign Warning
            dispatches.append(
                StakeholderDispatch(
                    incident_id=candidate.incident_id,
                    stakeholder=StakeholderType.VARIABLE_MESSAGE_SIGN_VMS,
                    endpoint_url=f"{self.base_url}/vms_gantry",
                    priority="P0",
                    payload={
                        "gantry_id": "VMS-NH16-GANTRY-04",
                        "message_text": f"DANGER: STALLED {p_class.upper()} AT {candidate.km_marker} - SLOW DOWN",
                        "incident_id": candidate.incident_id,
                    },
                )
            )
            # Action 2: NHAI Route Patrol & Crane
            dispatches.append(
                StakeholderDispatch(
                    incident_id=candidate.incident_id,
                    stakeholder=StakeholderType.HIGHWAY_PATROL_NHAI,
                    endpoint_url=f"{self.base_url}/nhai",
                    priority="P0",
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

        elif candidate.incident_type == IncidentType.WRONG_WAY_DRIVER:
            briefing = (
                f"CRITICAL LIFE-SAFETY ALERT: {p_class} #{candidate.primary_track_id} detected driving "
                f"AGAINST TRAFFIC FLOW at {p_speed} km/h on {candidate.km_marker} ({candidate.lane_id})."
            )
            trace = [
                f"OBSERVED: {p_class} #{candidate.primary_track_id} moving opposite to traffic direction at {p_speed} km/h.",
                f"ASSESSED: Catastrophic head-on collision threat with approaching vehicles.",
                f"DECIDED: Trigger emergency police interception and broadcast dynamic wrong-way driver alert on upstream gantries.",
                f"ACTIONS: Mobilized Highway Police Interceptor + VMS Emergency Warning.",
            ]
            dispatches.append(
                StakeholderDispatch(
                    incident_id=candidate.incident_id,
                    stakeholder=StakeholderType.VARIABLE_MESSAGE_SIGN_VMS,
                    endpoint_url=f"{self.base_url}/vms_gantry",
                    priority="P0",
                    payload={
                        "gantry_id": "VMS-NH16-GANTRY-04",
                        "message_text": f"EMERGENCY: WRONG WAY DRIVER NEAR {candidate.km_marker} - PULL OVER",
                        "incident_id": candidate.incident_id,
                    },
                )
            )
            dispatches.append(
                StakeholderDispatch(
                    incident_id=candidate.incident_id,
                    stakeholder=StakeholderType.POLICE_CONTROL_ROOM,
                    endpoint_url=f"{self.base_url}/police",
                    priority="P0",
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

        elif candidate.incident_type == IncidentType.TAILGATING_COLLISION_RISK:
            sec_veh = candidate.involved_vehicles[1] if len(candidate.involved_vehicles) > 1 else None
            s_class = sec_veh.label if sec_veh else "Vehicle"
            briefing = (
                f"HIGH COLLISION PROBABILITY: {p_class} #{candidate.primary_track_id} aggressively tailgating "
                f"{s_class} #{candidate.secondary_track_id} at {candidate.km_marker} with sub-second reaction margin."
            )
            trace = [
                f"OBSERVED: Longitudinal closing trajectory between {p_class} #{candidate.primary_track_id} and {s_class} #{candidate.secondary_track_id}.",
                f"ASSESSED: Time-to-Collision (TTC) is critically low. Sudden braking will trigger multi-vehicle pileup.",
                f"DECIDED: Issue highway VMS safe headway advisory and log telemetry for corridor enforcement.",
                f"ACTIONS: Dispatched VMS Headway Caution.",
            ]
            dispatches.append(
                StakeholderDispatch(
                    incident_id=candidate.incident_id,
                    stakeholder=StakeholderType.VARIABLE_MESSAGE_SIGN_VMS,
                    endpoint_url=f"{self.base_url}/vms_gantry",
                    priority="P1",
                    payload={
                        "gantry_id": "VMS-NH16-GANTRY-04",
                        "message_text": "KEEP SAFE DISTANCE - DANGEROUS TAILGATING DETECTED AHEAD",
                        "incident_id": candidate.incident_id,
                    },
                )
            )

        else:
            briefing = f"Safety Alert: {candidate.rule_reason}"
            trace = [
                f"OBSERVED: Hazard trigger on {candidate.primary_track_id}.",
                f"ASSESSED: General roadway anomaly.",
                f"DECIDED: Log event and monitor.",
                f"ACTIONS: Event logged to incident repository.",
            ]

        return briefing, trace, dispatches
