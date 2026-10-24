# Current status: what is real, what is simulated

Written so an evaluator can tell, without reading the code, what this project does today.
It is a working prototype. It is not a certified or deployed emergency system.

## What works today
- Control-room interface: incident queue, incident detail with briefing and reasoning, dispatch history, activity log, system status, keyboard and screen-reader support.
- Demo mode (default): a built-in simulator produces incidents, dispatches and camera health so the whole workflow can be shown with no backend.
- Live mode (`VITE_DATA_MODE=live`): the FastAPI backend runs detection and tracking on video, applies the incident rules, stores incidents and dispatches in SQLite, and streams updates over WebSocket.
- Plate reading never invents a plate. If the text cannot be read, the system reports "NO READ" (confidence 0) and the UI shows "No plate read". Confidence is the OCR engine's own score scaled by how consistently the same text was read across frames.
- Stalled-vehicle alerts wait for a continuous stop (default 3 s), measured from the moment the vehicle stopped, not from when it was first tracked. Incident evidence records the real stopped time.
- Camera health starts as unknown. The backend reports how long ago the last video frame arrived, and the UI marks health as stale when frames stop, even if heartbeat messages keep coming.
- Honest states: the interface shows connecting, offline and stale-data states, never shows "All clear" when it cannot know, and never shows a failed or unconfirmed dispatch as sent, acknowledged or cancelled.

## What is simulated
- **Dispatch is mocked.** The police, patrol/crane, 108 ambulance and variable-message-sign endpoints live in `app/mock_dispatch.py`. They return realistic responses but do not contact any real service. "Sent" in this prototype means "sent to the mock".
- **Demo-mode incidents and metrics are generated**, not detected from a camera.
- The mock dispatch audit log is in memory and is lost on restart.
- **The plate hotlist is empty.** Demo entries load only when `ANPR_DEMO_HOTLIST=1` and are marked simulated. A real list can be supplied with `ANPR_HOTLIST_PATH`, and only an authorised, current list should ever be used.

## What is not built yet
- Calibrated speed and distance. Speed uses one fixed pixel-to-metre scale (`pixels_per_meter`), which is not valid across a perspective camera view. Speed, time-to-collision and wrong-way results are estimates, not measurements.
- Operator login, roles and permissions. The API has no authentication and allows any origin (CORS `*`).
- A tamper-proof audit trail of operator actions.
- Integration with real dispatch systems, with acknowledgement timers, escalation and retry.
- Measured detection accuracy (precision, recall, false alarms per camera-hour) on representative Andhra Pradesh footage. Rules and thresholds have not been calibrated for deployment.
- A security review, a data-retention policy, and a privacy assessment (for example DPDP Act) for plates and video.

## Before any real pilot
Run in shadow mode on an authorised camera feed, with operator approval required before any live dispatch, and acceptance criteria agreed with the responsible department.
