# Autonomous Highway Safety & Incident Command System Architecture

## 1. Executive Summary & Design Principles

The Autonomous Highway Safety Agent is an edge-first incident detection, cognitive triage, and emergency dispatch mobilization system designed for high-speed highway corridors (such as NH-16). 

### Core Design Constraints:
1. **The Edge Tracker Never Waits on the Agent**: Real-time detection and tracking run in an isolated in-process loop at 15–30+ FPS on CPU hardware.
2. **The Agent Never Touches Raw Video**: Video frames stay on the edge device in a 10-second circular buffer. The handoff to the agent is an event packet (telemetry window, track IDs, crop references, and camera metadata).
3. **Deterministic Safety Floor (Tier 0)**: High-risk incidents (wrong-way traffic, stalled vehicles in fast lanes, high-speed tailgating) trigger deterministic policy actions within milliseconds without waiting for cloud LLM roundtrips.
4. **Human-in-the-Loop Operator Guardrails**: Dispatches are held in a 15-second countdown queue, allowing traffic management center (TMC) operators to override or cancel false alarms before notification dispatch.

---

## 2. System Architecture & Component Topology

```
+-----------------------------------------------------------------------------------------+
|                                    EDGE DEVICE (CPU / SBC)                              |
|                                                                                         |
|  +-----------------------+     +-----------------------+     +-----------------------+  |
|  | Video Ingestion /     | --> | YOLOv8 ONNX Detector  | --> | ByteTrack + Kalman    |  |
|  | RTSP Stream           |     | (CPU quantized)       |     | State Estimation      |  |
|  +-----------------------+     +-----------------------+     +-----------------------+  |
|              |                                                           |              |
|              v                                                           v              |
|  +-----------------------+                                   +-----------------------+  |
|  | Circular Ring Buffer  |                                   | Edge Trigger Engine   |  |
|  | (10s in-memory deque) |                                   | (Pure Python / NumPy) |  |
|  +-----------------------+                                   +-----------------------+  |
|              |                                                           |              |
|              | Decoupled ThreadPool                                      | Candidate    |
|              v                                                           v Event        |
|  +-----------------------+                                   +-----------------------+  |
|  | Evidence Persistence  |                                   | Bounded Event Queue   |  |
|  | (MP4 Clip + JPEGs)    |                                   | (asyncio / mp.Queue)  |  |
|  +-----------------------+                                   +-----------------------+  |
+--------------------------------------------------------------------------|--------------+
                                                                           |
                                                                           v
+-----------------------------------------------------------------------------------------+
|                                  COGNITIVE SAFETY AGENT                                 |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | SafetyPolicyEngine (Tier 0 Deterministic Floor)                                    |  |
|  |  * Situation Briefing Synthesis                                                   |  |
|  |  * 4-Stage Reasoning Trace: Observed -> Assessed -> Decided -> Actions           |  |
|  |  * Stakeholder Dispatch Matrix (VMS Gantry, NHAI Patrol Crane, 108 EMS Ambulance) |  |
|  +-----------------------------------------------------------------------------------+  |
|                                          |                                              |
|                                          v                                              |
|  +-----------------------------------------------------------------------------------+  |
|  | SQLite Persistent Storage (highway_incidents.db)                                  |  |
|  |  * Incident Records, Dispatches, Operator Feedback, Audit Log                     |  |
|  +-----------------------------------------------------------------------------------+  |
+--------------------------------------------------------------------------|--------------+
                                                                           |
                                              WebSocket & REST SSE Stream  v
+-----------------------------------------------------------------------------------------+
|                              OPERATOR CONTROL ROOM (React + Vite)                       |
|                                                                                         |
|  [ Incident Queue ] <--------> [ Top-Down Lane Map ] <--------> [ Live Briefing & Trace]|
|  (Severity P0/P1/P2)           (Telemetry Projection)           (15s Cancel Countdown)  |
+-----------------------------------------------------------------------------------------+
```

---

## 3. Perception & Tracking Pipeline

### 3.1 Object Detection
- **Model**: YOLOv8n ONNX runtime with CPU-optimized execution provider.
- **Input Scaling**: Dynamically scaled to process width (default 640px) while maintaining aspect ratio.
- **Classes Filtered**: Vehicles only (`Car`, `Truck`, `Bus`, `Van`, `Motorbike`).

### 3.2 ByteTrack Two-Stage Association
Rather than a naive centroid distance tracker, the system implements a two-stage Hungarian association algorithm:
1. **High-Confidence Matching**: First associates high-confidence detections ($conf \ge 0.35$) with confirmed active tracks using Bounding Box Intersection-over-Union (IoU).
2. **Low-Confidence Recovery**: Matches remaining unmatched tracks against lower-confidence detections ($0.15 \le conf < 0.35$) to maintain identity continuity through occlusions, wiper blade crossings, or lighting flicker.
3. **Kalman State Estimation**: 8-dimensional state vector:
   $$x = [cx, cy, w, h, v_{cx}, v_{cy}, v_w, v_h]^T$$
   Smooths bounding box jitter and predicts positions across dropped frames.
4. **Track Confirmation & Retention**:
   - Gated confirmation: A track requires $N \ge 5$ consecutive detection hits before firing safety rules.
   - Time-based lost retention: Lost tracks persist for up to `max_lost_time_s = 1.0s` before deletion.

### 3.3 Motion & Speed Estimation
- **Velocity Estimation**: Computed via a 0.5-second sliding window over Kalman-smoothed ground coordinates.
- **Coordinate Conversion**: Pixel-to-meter homography mapping derived from lane markings and standard vehicle lengths.
- **Spike Isolation**: Instantaneous step velocities $> 200\text{ km/h}$ are flagged as tracking artifacts (ID switches/crossovers) and strictly blocked from reaching the incident rule engine.

---

## 4. Edge Trigger Rule Engine

The rule engine (`EdgeTriggerEngine`) evaluates verified track states with zero LLM in the critical path:

### 4.1 Stalled Vehicle in Travel Lane
- **Condition**: Vehicle in travel lane (`type: "travel"`) stationary for $\ge 3.0$ seconds with speed $\le 3.5\text{ km/h}$.
- **Congestion Gating**: If the median speed of other vehicles in the lane is $< 15\text{ km/h}$, the alert is suppressed as normal traffic queueing.
- **Shoulder Parking Isolation**: Stationary vehicles in the emergency shoulder (`type: "shoulder"`) are classified as non-critical **P2** observations with **0 dispatches**, preventing false alarms.

### 4.2 Wrong-Way Driver
- **Condition**: Track age $\ge 2.0$ seconds, net displacement along lane opposing traffic flow $\ge 5.0$ meters, heading angle $> 135^\circ$ to authorized lane vector, and speed $\ge 15\text{ km/h}$.
- **Multi-Lane Flow Vectors**: Supports bidirectional carriageways where lanes have distinct authorized directions.

### 4.3 Tailgating (Time-to-Collision)
- **Condition**: Follower and leader both confirmed in the same travel lane.
- **Closing Condition**: Requires headway $> 0$ and closing speed $> 0$ (follower faster than leader). If leader is pulling away, TTC calculation is suppressed.
- **TTC Formula**:
  $$\text{TTC} = \frac{\text{Headway (m)}}{\text{Closing Speed (m/s)}}$$
- **Threshold**: Critical alert at $\text{TTC} < 1.2\text{ s}$ sustained for $\ge 1.0\text{ s}$.

---

## 5. Cognitive Agent & Human-in-the-Loop Safety Floor

### 5.1 4-Stage Reasoning Trace
Every incident produces a structured audit trail:
1. **Observed**: Quantitative telemetry summary (speed, lane, track age, heading).
2. **Assessed**: Risk classification, collision probability, traffic disruption severity.
3. **Decided**: Immediate emergency response policy and required assets.
4. **Actions**: Targeted dispatches queued for stakeholder execution.

### 5.2 Dispatch Matrix
- **P0 Incidents (Stalled in Fast Lane / Wrong-Way)**:
  - Immediate Variable Message Sign (VMS) gantry warning activation.
  - NHAI Highway Route Patrol & towing crane mobilization.
  - 108 Emergency Medical Ambulance standby alert.
- **P1 Incidents (Tailgating Hazard)**:
  - VMS speed enforcement display warning.
- **P2 Incidents (Shoulder Stop)**:
  - Local logging, zero external dispatches.

### 5.3 15-Second Operator Cancellation Window
All outbound stakeholder dispatches enter a 15-second queued status (`queued`). Control room operators can click **Cancel Dispatch** or mark **False Alarm** to immediately abort outbound notifications before transmission.
