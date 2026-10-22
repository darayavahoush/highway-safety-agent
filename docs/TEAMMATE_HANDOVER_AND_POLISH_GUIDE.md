# Highway Safety & Accident Prevention Autonomous Agent
## Comprehensive Engineering Documentation & Teammate Handover Guide

> **Challenge**: Highway Road Accident Prevention Innovation Challenge (HRAP-2026)  
> **Stakeholders**: Government of Andhra Pradesh & Ratan Tata Innovation Hub (RTIH)  
> **Repository**: [github.com/darayavahoush/highway-safety-agent](https://github.com/darayavahoush/highway-safety-agent)  
> **License**: MIT  

---

## 1. Executive Summary & Core Mission

Every day, high-speed national highway corridors across Andhra Pradesh (specifically **NH-16 Chennai–Kolkata** and **NH-44 Rayalaseema**) witness severe accidents caused by unlit stalled freight vehicles, reckless feeder road intrusions, opposing flow (wrong-way driving), and heavy commercial tailgating.

Traditional highway monitoring relies on human CCTV operators watching dozens of screens, leading to an average detection-to-dispatch latency of **8 to 22 minutes**—far exceeding the **Golden Hour** window for polytrauma victims.

This autonomous agent was engineered to solve this crisis through an **Edge-First, Two-Tier Architecture**:
1. **Tier 0 Deterministic Safety Floor**: Pure Python/NumPy perception executing at **sub-3ms latency** on low-cost edge CPUs and Raspberry Pi single-board computers. **Zero cloud dependency, zero LLM calls in the perception loop**, and continuous 15–30+ FPS throughput.
2. **Tier 1 Cognitive Safety Agent**: High-level reasoning, 4-stage forensic audit traces (*Observed &rarr; Assessed &rarr; Decided &rarr; Actions*), automated stakeholder dispatch generation with a 15-second human-in-the-loop cancellation window, and on-demand cognitive debriefing powered by **Parallel AI Web Intelligence**.

---

## 2. Complete Architecture Blueprint

```
+---------------------------------------------------------------------------------------------------+
|                                      EDGE DEVICE / CLOUD SENTRY                                    |
|                                                                                                   |
|  +--------------------+      +--------------------+      +--------------------+                   |
|  | Video Ingestion /  | ---> | YOLOv8 ONNX        | ---> | ByteTrack + Kalman |                   |
|  | RTSP Stream        |      | (Quantized CPU)    |      | State Estimation   |                   |
|  +--------------------+      +--------------------+      +--------------------+                   |
|           |                                                        |                              |
|           v                                                        v                              |
|  +--------------------+      +--------------------+      +--------------------+                   |
|  | Camera Health      |      | 0.5s Sliding Speed |      | Pure NumPy Rules   |                   |
|  | Stability & Light  |      | Spike Gate (>200)  | ---> | (Sub-3ms Latency)  |                   |
|  +--------------------+      +--------------------+      +--------------------+                   |
|           |                                                        |                              |
|           v                                                        v [IncidentCandidate]          |
|  +--------------------+                                  +--------------------+                   |
|  | 10s Ring Buffer &  | <=============================== | Bounded Queue      |                   |
|  | Async JPEG/MP4     |        (Thread-safe)             | (asyncio.Queue)    |                   |
|  +--------------------+                                  +--------------------+                   |
+--------------------------------------------------------------------|------------------------------+
                                                                     v
+---------------------------------------------------------------------------------------------------+
|                                    COGNITIVE SAFETY AGENT LAYER                                   |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | SafetyPolicyEngine (Tier 0 Deterministic Triage)                                            |  |
|  |  - Situation Briefing & Threat Assessment                                                   |  |
|  |  - 4-Stage Audit Trace: Observed -> Assessed -> Decided -> Actions                          |  |
|  |  - Stakeholder Dispatch Generation (VMS Gantry, NHAI Patrol, 108 EMS, Owner Notice)          |  |
|  +---------------------------------------------------------------------------------------------+  |
|           |                                                        |                              |
|           v                                                        v                              |
|  +--------------------+                                  +--------------------+                   |
|  | SQLite Persistence |                                  | On-Demand AI       |                   |
|  | (incidents & crops)|                                  | Parallel Copilot   |                   |
|  +--------------------+                                  +--------------------+                   |
+--------------------------------------------------------------------|------------------------------+
                                                                     v
+---------------------------------------------------------------------------------------------------+
|                                  OPERATOR CONTROL ROOM (React 18 + Vite)                          |
|                                                                                                   |
|  [ Incident Queue ] <---> [ Live Stage (Camera, 3D Map, Lane, Twin) ] <---> [ Reasoning & Trace ]|
|  [ TopBar Diagnostics: Camera Health (Static vs Sway) & Photometrics ] <---> [ Operator Copilot ] |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. What Is Already Built & Fully Verified

Every module below is implemented, tested with 100% passing tests, and pushed to `main`:

### 3.1. Edge Perception & State Tracking
- **File**: [`app/tracker.py`](../app/tracker.py)
- **Features**: ByteTrack two-stage Hungarian association (high-confidence $\ge 0.35$, low-confidence $\ge 0.15$) combined with an 8-state Kalman Filter ($cx, cy, w, h, v_{cx}, v_{cy}, v_w, v_h$). Tracks maintain identity across occlusions and crossovers.
- **Kinematic Smoothing**: 0.5-second sliding window velocity smoothing with an instantaneous physical spike rejection gate ($> 200\text{ km/h}$) isolating tracking artifacts from entering the rules engine.

### 3.2. Deterministic Edge Rule Engine
- **File**: [`app/incident_rules.py`](../app/incident_rules.py)
- **Rules Evaluated**:
  1. **Stalled Vehicle**: P0 in active travel lanes; P2 monitoring on shoulder with zero dispatch. Congestion suppression suppresses alerts when surrounding lane median speed is $< 15\text{ km/h}$.
  2. **Wrong-Way Driving**: Direction-vector analysis requiring opposing dot-product ($< -0.707$, angle $> 135^\circ$) and sustained displacement ($\ge 5\text{ m}$).
  3. **Tailgating (TTC)**: Longitudinal headway Time-to-Collision ($< 1.2\text{ s}$) requiring active closing speed ($v_{\text{close}} > 0.5\text{ m/s}$) with 1.3× safety multiplier for mixed freight following two-wheelers/cars.
  4. **Feeder-Road Merge Intrusion (P1)**: Trajectory cross-boundary tracking detecting unmerged vehicles abruptly cutting from service margin (`lane_0_feeder`) into live high-speed lanes with lateral velocity $v_y \ge 8.0\text{ km/h}$.
  5. **Dusk/Night Stationary Protocol**: Elevates shoulder stops to P1 hazard between 18:00 and 06:00 or when camera health detects low-light conditions, dispatching NHAI patrol for scene illumination.

### 3.3. Camera Health & Photometric Environmental Telemetry
- **File**: [`app/camera_health.py`](../app/camera_health.py)
- **Features**:
  - **Mount Stability**: Sparse Lucas-Kanade optical flow on non-vehicle background keypoints. Classifies camera as `STATIC_LOCKED` ($< 1.8\text{ px}$ drift), `WIND_SWAY` ($1.8\text{--}5.0\text{ px}$), or `PANNING_OR_DRIFT` ($> 5.0\text{ px}$).
  - **Photometrics**: Mean grayscale luminance, RMS contrast, and dynamic range classifying conditions as `OPTIMAL_DAYLIGHT`, `LOW_LIGHT_DUSK`, `NIGHT_VISION`, `GLARE_OVEREXPOSURE`, or `LOW_CONTRAST_FOG`.
  - **REST & Telemetry**: Exposed via `GET /api/camera/health` and live WebSocket broadcast to the frontend.

### 3.4. Edge ANPR Engine with Multi-Frame Consensus
- **File**: [`app/anpr.py`](../app/anpr.py)
- **Features**: Morphological bumper localization (bottom 45%), Sobel rectangular aspect gating (2.0–5.5), Tesseract OCR with Indian HSRP normalization (`AP 16 TX 4921`), multi-frame temporal voting across track history, and hotlist matching.

### 3.5. On-Demand Parallel AI Intelligence & Copilot
- **Files**: [`agent/parallel_client.py`](../agent/parallel_client.py), [`frontend/src/components/OperatorCopilot.jsx`](../frontend/src/components/OperatorCopilot.jsx)
- **Strict Zero-Cost Policy**: Zero automated background LLM calls during perception. Invoked on-demand when operators click **"Explain with AI"** or interact with the floating Copilot drawer for bilingual Telugu/English alerts and MoRTH blackspot risk breakdowns.

### 3.6. 3D Digital Twin & Trauma Network Map
- **File**: [`frontend/src/components/CorridorMap3D.jsx`](../frontend/src/components/CorridorMap3D.jsx)
- **Features**: MapLibre GL 3D interactive terrain map with OSRM ambulance routing to designated Level-1 trauma centres (AIIMS Mangalagiri, GGH Guntur, GGH Vijayawada), pulsating incident beacons, and offline SVG fallback.

### 3.7. Informative About Documentation & Accessibility
- **File**: [`frontend/src/components/AboutModal.jsx`](../frontend/src/components/AboutModal.jsx)
- **Features**: Complete architectural, corridor, and challenge breakdown modal accessible via the TopBar button or keyboard shortcut `?` / `A`.

---

## 4. Verification Proofs (All Tests Green)

To run the verification suites:
```bash
# Synthetic Edge Tracker & Rules Suite (10 Scenarios)
python tests/test_tracker_and_rules.py

# Acceptance Benchmark & Replay Harness (4 Acceptance Criteria)
python tests/test_replay_harness.py

# Production Frontend Build
npm run build --prefix frontend
```

### Verified Test Summary:
| Test ID | Description | Result |
| :--- | :--- | :--- |
| **TEST 1** | Missing vehicle for 3 frames retains tracking ID | **PASS** |
| **TEST 2** | Two vehicles crossing paths preserve identities | **PASS** |
| **TEST 3** | ID switch speed spike ($> 200\text{ km/h}$) isolated from rules | **PASS** |
| **TEST 4** | Daytime shoulder stop is P2 with 0 dispatches | **PASS** |
| **TEST 5** | Heavy traffic congestion suppresses false stalled alerts | **PASS** |
| **TEST 6** | Dual-carriageway traffic honors own lane direction | **PASS** |
| **TEST 7** | Genuine wrong-way vehicle fires once under dedupe cooldown | **PASS** |
| **TEST 8** | Tailgating fires on close follower, not leader pulling away | **PASS** |
| **TEST 9** | Feeder road intrusion detected with P1 and VMS/Patrol dispatch | **PASS** |
| **TEST 10**| Night protocol elevates shoulder stop to P1 with active patrol | **PASS** |
| **BENCH** | Pure NumPy Rule Engine throughput ($> 500\text{ FPS}$, $< 2.1\text{ ms}$) | **PASS** |

---

## 5. Actionable Next Steps for Teammate

Here are 5 concrete work packages your teammate can pick up immediately to polish the project to perfection:

### Work Package 1: Configure Custom Video / RTSP Feeds
- **Goal**: Connect live CCTV feeds or test additional highway drone videos.
- **Steps**:
  1. Place test MP4 files in `demo_videos/`.
  2. Run the interactive calibration utility:
     ```bash
     python tools/calibrate_camera.py --video demo_videos/your_video.mp4
     ```
  3. Drag polygon points to align with highway lanes (feeder margin, fast lane, commercial lane, shoulder).
  4. Save the generated JSON to `config/camera_config.json`.

### Work Package 2: Set Parallel AI Key on Render Dashboard
- **Goal**: Ensure the deployed cloud instance can run on-demand Copilot queries and AI explanations.
- **Steps**:
  1. Open the [Render Dashboard](https://dashboard.render.com).
  2. Navigate to the `highway-safety-agent` service.
  3. Go to **Environment** &rarr; **Add Environment Variable**:
     - Key: `PARALLEL_API_KEY`
     - Value: `bhuFWb9Z_gKmuCnqguG1wEODVVc0SXBg73hT19QN`
  4. Click **Save Changes** (Render will automatically re-deploy).

### Work Package 3: Record a 2-Minute Demo Showcase Video
- **Goal**: Create an engaging pitch video / GIF for hackathon judges.
- **Suggested Script (120 seconds)**:
  - **0:00 – 0:25**: Show the live control room UI with high-speed drone footage, active vehicle bounding boxes, and Indian HSRP plate chips (`IND AP 16 TX 8120`).
  - **0:25 – 0:50**: Show an incident firing (e.g. stalled vehicle or wrong-way driver) & show the 4-stage reasoning trace (*Observed &rarr; Assessed &rarr; Decided &rarr; Actions*) with the 15-second dispatch countdown.
  - **0:50 – 1:15**: Switch to the **3D Corridor Map** (press `2`), show the pulsing incident beacon and OSRM route to **AIIMS Mangalagiri Level-1 Trauma Centre**.
  - **1:15 – 1:40**: Open the **Operator Copilot** (press `C`), click *"Draft bilingual Telugu alert"*, and demonstrate on-demand AI grounding.
  - **1:40 – 2:00**: Highlight sub-3ms edge latency metrics at the bottom and explain Raspberry Pi readiness.

### Work Package 4: Hardware Benchmark on Raspberry Pi 4 / 5
- **Goal**: Generate hardware validation numbers on real edge hardware.
- **Steps**:
  1. Follow [`docs/EDGE_DEPLOYMENT_RASPBERRY_PI.md`](EDGE_DEPLOYMENT_RASPBERRY_PI.md).
  2. Install systemd unit `tools/highway-safety.service`.
  3. Record average CPU temperature, RAM usage, and steady-state FPS.

### Work Package 5: Optional Telugu VMS Audio Announcements
- **Goal**: Enhance operator experience with bilingual audio alerts.
- **Steps**:
  - In `frontend/src/lib/format.js` or `IncidentDetail.jsx`, use the Web Speech API (`window.speechSynthesis`) to pronounce high-priority P0 warnings in Telugu and English when selected by the operator.

---

## 6. Simultaneous Keyboard Navigation Quick Reference

| Key | Action |
| :---: | :--- |
| <kbd>1</kbd> | Switch to Live Camera MJPEG View |
| <kbd>2</kbd> | Switch to 3D Corridor & Trauma Network Map |
| <kbd>3</kbd> | Switch to Top-Down Lane Telemetry Map |
| <kbd>4</kbd> | Switch to Three.js 3D Digital Twin |
| <kbd>C</kbd> | Toggle Floating AI Operator Copilot Drawer |
| <kbd>?</kbd> or <kbd>A</kbd> | Open Architecture & About System Modal |
| <kbd>Esc</kbd> | Close active modal or drawer |
