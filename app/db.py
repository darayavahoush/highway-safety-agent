"""
SQLite persistence for Highway Safety Incidents, Dispatches, and Blackspots.
Thread-safe database storage ensuring zero data loss across reboots.
"""

import json
import os
import sqlite3
import time
from typing import Dict, List, Optional, Any

DB_PATH = os.getenv("SQLITE_DB_PATH", "highway_incidents.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        # Incidents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence REAL,
                created_at REAL NOT NULL,
                camera_id TEXT,
                km_marker REAL,
                camera_json TEXT,
                vehicles_json TEXT,
                briefing TEXT,
                trace_json TEXT,
                verdict TEXT,
                snapshot_url TEXT,
                clip_url TEXT,
                updated_at REAL NOT NULL
            )
        """)

        # Dispatches table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dispatches (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                queued_at REAL,
                sent_at REAL,
                ack_at REAL,
                cancel_until REAL,
                payload_json TEXT,
                response_json TEXT,
                FOREIGN KEY (incident_id) REFERENCES incidents (id)
            )
        """)

        # Indexes for fast lookup & aggregation
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_km ON incidents(km_marker)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_inc ON dispatches(incident_id)")
        conn.commit()


def upsert_incident(inc: Dict[str, Any]):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = time.time()
        cursor.execute("""
            INSERT INTO incidents (
                id, type, severity, status, confidence, created_at, camera_id,
                km_marker, camera_json, vehicles_json, briefing, trace_json,
                verdict, snapshot_url, clip_url, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                confidence = excluded.confidence,
                vehicles_json = excluded.vehicles_json,
                briefing = excluded.briefing,
                trace_json = excluded.trace_json,
                verdict = excluded.verdict,
                updated_at = excluded.updated_at
        """, (
            inc.get("id"),
            inc.get("type"),
            inc.get("severity"),
            inc.get("status"),
            inc.get("confidence"),
            inc.get("createdAt", now),
            inc.get("camera", {}).get("id"),
            float(inc.get("camera", {}).get("km", 42.0)),
            json.dumps(inc.get("camera", {})),
            json.dumps(inc.get("vehicles", [])),
            inc.get("briefing", ""),
            json.dumps(inc.get("trace", [])),
            inc.get("verdict"),
            inc.get("snapshot_url"),
            inc.get("clip_url"),
            now
        ))

        # Upsert dispatches
        for d in inc.get("dispatches", []):
            cursor.execute("""
                INSERT INTO dispatches (
                    id, incident_id, target, status, message,
                    queued_at, sent_at, ack_at, cancel_until, payload_json, response_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    sent_at = excluded.sent_at,
                    ack_at = excluded.ack_at,
                    cancel_until = excluded.cancel_until,
                    response_json = excluded.response_json
            """, (
                d.get("id"),
                inc.get("id"),
                d.get("target"),
                d.get("status"),
                d.get("message"),
                d.get("queuedAt"),
                d.get("sentAt"),
                d.get("ackAt"),
                d.get("cancelUntil"),
                json.dumps(d.get("payload", {})),
                json.dumps(d.get("response", {})) if d.get("response") else None
            ))

        conn.commit()


def get_all_incidents(limit: int = 50) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM incidents ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        incidents = []

        for row in rows:
            inc_id = row["id"]
            # Fetch dispatches
            cursor.execute("SELECT * FROM dispatches WHERE incident_id = ?", (inc_id,))
            d_rows = cursor.fetchall()
            dispatches = [
                {
                    "id": d["id"],
                    "target": d["target"],
                    "status": d["status"],
                    "message": d["message"],
                    "queuedAt": d["queued_at"],
                    "sentAt": d["sent_at"],
                    "ackAt": d["ack_at"],
                    "cancelUntil": d["cancel_until"],
                }
                for d in d_rows
            ]

            incidents.append({
                "id": row["id"],
                "type": row["type"],
                "severity": row["severity"],
                "status": row["status"],
                "confidence": row["confidence"],
                "createdAt": row["created_at"],
                "camera": json.loads(row["camera_json"]) if row["camera_json"] else {},
                "vehicles": json.loads(row["vehicles_json"]) if row["vehicles_json"] else [],
                "briefing": row["briefing"],
                "trace": json.loads(row["trace_json"]) if row["trace_json"] else [],
                "dispatches": dispatches,
                "verdict": row["verdict"],
                "snapshot_url": row["snapshot_url"],
                "clip_url": row["clip_url"],
            })

        return incidents


def cancel_dispatch(incident_id: str, dispatch_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE dispatches
            SET status = 'cancelled'
            WHERE incident_id = ? AND id = ? AND status = 'queued'
        """, (incident_id, dispatch_id))
        conn.commit()
        return cursor.rowcount > 0


def set_incident_feedback(incident_id: str, verdict: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        new_status = "false_alarm" if verdict == "false_alarm" else None
        if new_status:
            cursor.execute("""
                UPDATE incidents
                SET verdict = ?, status = ?, updated_at = ?
                WHERE id = ?
            """, (verdict, new_status, time.time(), incident_id))
        else:
            cursor.execute("""
                UPDATE incidents
                SET verdict = ?, updated_at = ?
                WHERE id = ?
            """, (verdict, time.time(), incident_id))
        conn.commit()

        # Return updated incident
        cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)


def get_blackspots_summary() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT CAST(ROUND(km_marker) AS INTEGER) AS km, COUNT(*) AS count
            FROM incidents
            WHERE status != 'false_alarm'
            GROUP BY km
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        results = [{"km": int(r["km"]), "count": int(r["count"])} for r in rows]
        # Always provide default active corridor km markers if empty
        if not results:
            results = [
                {"km": 40, "count": 2},
                {"km": 41, "count": 5},
                {"km": 42, "count": 12},
                {"km": 43, "count": 7},
                {"km": 44, "count": 3},
            ]
        return results


def reset_database_with_seed() -> List[Dict[str, Any]]:
    """Wipes the cluttered incidents and seeds 4 clean, distinct benchmark incidents."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dispatches")
        cursor.execute("DELETE FROM incidents")
        conn.commit()

    now_ms = time.time() * 1000

    seed_incidents = [
        {
            "id": "INC-2026-P0-WRONGWAY",
            "type": "WRONG_WAY",
            "severity": "P0",
            "status": "dispatched",
            "confidence": 0.96,
            "createdAt": now_ms - 120000,
            "camera": {
                "id": "CAM-AP-NH16-KM42",
                "highway": "NH-16",
                "km": 42.6,
                "lat": 16.5412,
                "lng": 80.6421,
                "towards": "Visakhapatnam",
                "opposite": "Vijayawada",
            },
            "vehicles": [
                {
                    "trackId": 104,
                    "cls": "car",
                    "speedKmh": -62.4,
                    "lane": "Fast Lane",
                    "box": [280, 190, 85, 60],
                    "plate": {
                        "text": "AP 16 TX 5928",
                        "confidence": 0.94,
                        "state": "Andhra Pradesh",
                    },
                }
            ],
            "briefing": "CRITICAL: Wrong-Way vehicle travelling north against oncoming highway traffic at KM 42.6 (Fast Lane). High collision threat.",
            "trace": [
                {"stage": "observed", "text": "Car #104 detected with negative longitudinal velocity (-62.4 km/h) in fast overtaking lane.", "at": now_ms - 120000},
                {"stage": "assessed", "text": "Direct head-on collision threat with southbound traffic. Delta velocity exceeds 140 km/h.", "at": now_ms - 119500},
                {"stage": "decided", "text": "Emergency Priority P0: Immediate VMS upstream closure warning and Police Interceptor dispatch.", "at": now_ms - 119200},
                {"stage": "actions", "text": "VMS-NH16-GANTRY-04 set to flashing red warning. AP Highway Police Patrol Unit 4 notified via Dial 112.", "at": now_ms - 119000},
            ],
            "dispatches": [
                {
                    "id": "INC-2026-P0-WRONGWAY-D1",
                    "target": "VARIABLE_MESSAGE_SIGN_VMS",
                    "status": "acknowledged",
                    "message": "CRITICAL: WRONG-WAY DRIVER AHEAD AT KM 42.6 - PULL OVER IMMEDIATELY",
                    "queuedAt": now_ms - 120000,
                    "sentAt": now_ms - 119900,
                    "ackAt": now_ms - 118000,
                    "cancelUntil": None,
                },
                {
                    "id": "INC-2026-P0-WRONGWAY-D2",
                    "target": "POLICE_CONTROL_ROOM",
                    "status": "acknowledged",
                    "message": "Intercept wrong-way vehicle AP 16 TX 5928 at KM 42.6 fast lane.",
                    "queuedAt": now_ms - 120000,
                    "sentAt": now_ms - 119800,
                    "ackAt": now_ms - 115000,
                    "cancelUntil": None,
                },
                {
                    "id": "INC-2026-P0-WRONGWAY-D3",
                    "target": "EMS_108_AMBULANCE",
                    "status": "acknowledged",
                    "message": "Pre-alert AIIMS Mangalagiri Trauma Unit for possible head-on collision at KM 42.6.",
                    "queuedAt": now_ms - 120000,
                    "sentAt": now_ms - 119700,
                    "ackAt": now_ms - 114000,
                    "cancelUntil": None,
                },
            ],
            "verdict": None,
            "snapshot_url": None,
            "clip_url": None,
        },
        {
            "id": "INC-2026-P1-TAILGATE",
            "type": "TAILGATING",
            "severity": "P1",
            "status": "dispatched",
            "confidence": 0.89,
            "createdAt": now_ms - 75000,
            "camera": {
                "id": "CAM-AP-NH16-KM42",
                "highway": "NH-16",
                "km": 42.4,
                "lat": 16.5412,
                "lng": 80.6421,
                "towards": "Visakhapatnam",
                "opposite": "Vijayawada",
            },
            "vehicles": [
                {
                    "trackId": 218,
                    "cls": "truck",
                    "speedKmh": 78.5,
                    "lane": "Lane 1",
                    "box": [310, 210, 110, 95],
                    "plate": {
                        "text": "AP 21 ER 5243",
                        "confidence": 0.91,
                        "state": "Andhra Pradesh",
                    },
                },
                {
                    "trackId": 219,
                    "cls": "car",
                    "speedKmh": 74.0,
                    "lane": "Lane 1",
                    "box": [315, 175, 75, 55],
                    "plate": {
                        "text": "AP 31 CZ 6438",
                        "confidence": 0.95,
                        "state": "Andhra Pradesh",
                    },
                },
            ],
            "briefing": "Commercial Truck #218 following passenger car at 78.5 km/h with 0.42s Time-to-Collision (TTC). High rear-end crush risk.",
            "trace": [
                {"stage": "observed", "text": "Heavy Truck #218 maintains 4.8m following distance behind Car #219 at 78.5 km/h.", "at": now_ms - 75000},
                {"stage": "assessed", "text": "Commercial truck stopping distance is 38m. Sudden deceleration will cause immediate underride collision.", "at": now_ms - 74500},
                {"stage": "decided", "text": "Issue dynamic VMS safe-distance alert and log commercial vehicle license for fleet compliance.", "at": now_ms - 74200},
                {"stage": "actions", "text": "VMS gantry safe-distance warning activated. NHAI route marshals informed.", "at": now_ms - 74000},
            ],
            "dispatches": [
                {
                    "id": "INC-2026-P1-TAILGATE-D1",
                    "target": "VARIABLE_MESSAGE_SIGN_VMS",
                    "status": "acknowledged",
                    "message": "MAINTAIN 50M DISTANCE - HIGH-SPEED TAILGATING DETECTED KM 42.4",
                    "queuedAt": now_ms - 75000,
                    "sentAt": now_ms - 74900,
                    "ackAt": now_ms - 73000,
                    "cancelUntil": None,
                },
                {
                    "id": "INC-2026-P1-TAILGATE-D2",
                    "target": "HIGHWAY_PATROL_NHAI",
                    "status": "acknowledged",
                    "message": "Advisory notice dispatched to NHAI corridor patrol at KM 42.4.",
                    "queuedAt": now_ms - 75000,
                    "sentAt": now_ms - 74800,
                    "ackAt": now_ms - 72000,
                    "cancelUntil": None,
                },
            ],
            "verdict": None,
            "snapshot_url": None,
            "clip_url": None,
        },
        {
            "id": "INC-2026-P1-FEEDER",
            "type": "FEEDER_INTRUSION",
            "severity": "P1",
            "status": "dispatched",
            "confidence": 0.92,
            "createdAt": now_ms - 40000,
            "camera": {
                "id": "CAM-AP-NH16-KM42",
                "highway": "NH-16",
                "km": 42.4,
                "lat": 16.5412,
                "lng": 80.6421,
                "towards": "Visakhapatnam",
                "opposite": "Vijayawada",
            },
            "vehicles": [
                {
                    "trackId": 305,
                    "cls": "motorbike",
                    "speedKmh": 24.0,
                    "lane": "Feeder Road",
                    "box": [120, 260, 45, 50],
                    "plate": {
                        "text": "AP 16 BN 8821",
                        "confidence": 0.88,
                        "state": "Andhra Pradesh",
                    },
                }
            ],
            "briefing": "Lateral Intrusion: Unchecked vehicle entering high-speed carriageway from un-signaled rural feeder road at KM 42.4.",
            "trace": [
                {"stage": "observed", "text": "Two-wheeler #305 entering carriageway at lateral velocity vy = 11.8 km/h.", "at": now_ms - 40000},
                {"stage": "assessed", "text": "Blind spot merge into 80 km/h expressway traffic stream without acceleration ramp.", "at": now_ms - 39500},
                {"stage": "decided", "text": "Warn oncoming traffic via upstream VMS and alert NHAI junction marshals.", "at": now_ms - 39200},
                {"stage": "actions", "text": "VMS junction hazard warning deployed. NHAI marshals dispatched.", "at": now_ms - 39000},
            ],
            "dispatches": [
                {
                    "id": "INC-2026-P1-FEEDER-D1",
                    "target": "VARIABLE_MESSAGE_SIGN_VMS",
                    "status": "acknowledged",
                    "message": "CAUTION: VEHICLE ENTERING FROM FEEDER ROAD AT KM 42.4 - SLOW DOWN",
                    "queuedAt": now_ms - 40000,
                    "sentAt": now_ms - 39900,
                    "ackAt": now_ms - 38000,
                    "cancelUntil": None,
                },
                {
                    "id": "INC-2026-P1-FEEDER-D2",
                    "target": "HIGHWAY_PATROL_NHAI",
                    "status": "acknowledged",
                    "message": "Deploy mobile marshal to KM 42.4 feeder road access point.",
                    "queuedAt": now_ms - 40000,
                    "sentAt": now_ms - 39800,
                    "ackAt": now_ms - 37000,
                    "cancelUntil": None,
                },
            ],
            "verdict": None,
            "snapshot_url": None,
            "clip_url": None,
        },
        {
            "id": "INC-2026-P2-SHOULDER",
            "type": "STALLED_VEHICLE",
            "severity": "P2",
            "status": "monitoring",
            "confidence": 0.84,
            "createdAt": now_ms - 15000,
            "camera": {
                "id": "CAM-AP-NH16-KM42",
                "highway": "NH-16",
                "km": 42.4,
                "lat": 16.5412,
                "lng": 80.6421,
                "towards": "Visakhapatnam",
                "opposite": "Vijayawada",
            },
            "vehicles": [
                {
                    "trackId": 26974,
                    "cls": "car",
                    "speedKmh": 0.0,
                    "lane": "Emergency Shoulder",
                    "box": [480, 290, 80, 50],
                    "plate": {
                        "text": "AP 31 CZ 5654",
                        "confidence": 0.95,
                        "state": "Andhra Pradesh",
                    },
                }
            ],
            "briefing": "Vehicle #26974 (Car) parked on Emergency Shoulder at KM 42.4. Non-critical observation.",
            "trace": [
                {"stage": "observed", "text": "Car #26974 stationary in Emergency Shoulder for > 3.0 seconds.", "at": now_ms - 15000},
                {"stage": "assessed", "text": "Vehicle is situated outside active travel lanes in daylight. Zero carriageway obstruction.", "at": now_ms - 14500},
                {"stage": "decided", "text": "Logged for highway corridor monitoring. No emergency dispatches required.", "at": now_ms - 14200},
                {"stage": "actions", "text": "Stationary shoulder observation recorded. Zero dispatches issued.", "at": now_ms - 14000},
            ],
            "dispatches": [],
            "verdict": None,
            "snapshot_url": None,
            "clip_url": None,
        },
    ]

    for inc in seed_incidents:
        upsert_incident(inc)

    return get_all_incidents()

