# Prompt to paste into Antigravity

Paste everything below the line.

---

You are working in my repo `~/Downloads/highway-safety-agent` (FastAPI backend in `app/` and `agent/`, config in `config/`, tests in `tests/`). Phase 1 is done and its replay test passes. Do not start Phase 2 (ANPR) in this task.

I have a finished React frontend for the control room. It is in the folder `highway-control-room` that I am adding to this repo as `frontend/`. Treat its UI as final: do not restyle it, rename components, change `src/styles.css` tokens, or add UI libraries. Your job is to run it, then connect it to the real backend.

## Step 1: Run the frontend in demo mode
1. Copy the `highway-control-room` folder to `frontend/` in the repo root. Add `frontend/node_modules` and `frontend/dist` to `.gitignore`.
2. In `frontend/`: `npm install`, `cp .env.example .env`, `npm run build`, then `npm run dev`.
3. Confirm it builds with no errors and that demo mode shows incidents appearing. Report anything that fails.

## Step 2: Read the contract, then read the backend
1. Read `frontend/src/api/CONTRACT.md` completely. It defines the WebSocket events, the Incident shape and four REST routes the UI needs.
2. Read `app/main.py`, `app/incident_schema.py`, `app/queue_boundary.py`, `app/mock_dispatch.py`, `agent/reasoning.py`, `agent/worker.py`.
3. Before writing code, give me a short table: each field in the contract, where it comes from in the backend today, and what is missing. Wait for nothing; continue after posting it.

## Step 3: Backend changes (backend only)
Implement what is missing so the contract holds:
1. **Incident store.** Persist incidents, trace steps, dispatches and verdicts in the existing SQLite database (new tables or columns, with a migration that does not drop data).
2. **WebSocket `/ws/incidents`.** Broadcast the full Incident object (`{ "incident": {...} }`) every time the agent worker changes it: when created, after each reasoning step (observed, assessed, decided, actions), when dispatches are created, and when a dispatch changes status. Also broadcast `{ "metrics": {...} }` about every 1.5 s using real numbers (tracker FPS, rule-engine ms per frame, agent latency, median detection-to-first-dispatch).
3. **`GET /api/incidents`.** Return `{ incidents, blackspots, camera }`. Build `blackspots` from stored incident history grouped by whole km marker. Build `camera` from `config/camera_config.json`.
4. **Cancel window.** Dispatches to `EMS_108_AMBULANCE`, `POLICE_CONTROL_ROOM` and `VEHICLE_OWNER_NOTICE` start as `queued` with `cancelUntil = now + 15 s`. VMS and `HIGHWAY_PATROL_NHAI` send immediately. Implement `POST /api/incidents/{id}/dispatches/{dispatchId}/cancel` so a cancelled dispatch never calls its mock endpoint. After the window, send it and set `sentAt`.
5. **Acknowledgements.** The mock endpoints should return an acknowledgement after a short random delay so `ackAt` and `acknowledged` get filled in.
6. **Feedback.** `POST /api/incidents/{id}/feedback` with `{ "verdict": "confirmed" | "false_alarm" }`. Store it and set `status: false_alarm` when applicable.
7. **Owner notice.** Add `POST /mock/owner_notice` and the `VEHICLE_OWNER_NOTICE` dispatch target (used for tailgating and speeding evidence).
8. **Static and video.** Serve `evidence/` at `/evidence`. Make sure the existing MJPEG stream is available at `/video_feed` (or tell me its real path and I will set `VITE_VIDEO_PATH`).
9. **CORS** for `http://localhost:5173`.
10. `plate` must be `null` in the payload until ANPR exists. Do not invent plates.

If a field name in the backend differs from the contract, prefer editing `frontend/src/api/normalize.js` over renaming backend fields. That is the only frontend file you may edit.

## Step 4: Verify end to end
1. Start the backend, then the frontend with `VITE_DATA_MODE=live`.
2. Run the replay harness so a stalled vehicle, wrong-way driver and tailgating incident fire.
3. Check in the browser: the incident appears live, reasoning steps arrive in order, dispatches show up with the right timers, Cancel on a queued dispatch prevents the mock call (show me the log line), Confirm and False alarm persist after a page reload.
4. Run `tests/test_replay_harness.py` and `npm run build`. Both must still pass.

## Report back
List every file you changed, anything in the contract you could not satisfy and why, and the exact commands to start backend and frontend. Do not claim something works unless you ran it.
