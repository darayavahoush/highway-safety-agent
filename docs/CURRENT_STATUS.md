# Current status: what is real, what is simulated

Written so an evaluator can tell, without reading the code, what this project does today.
It is a working prototype. It is not a certified or deployed emergency system.

## What works today
- Control-room interface: incident queue, incident detail with briefing and reasoning, dispatch history, activity log, system status, keyboard and screen-reader support.
- Demo mode (default): a built-in simulator produces incidents, dispatches and camera health so the whole workflow can be shown with no backend.
- Live mode (`VITE_DATA_MODE=live`): the FastAPI backend runs detection and tracking on video, applies the incident rules, stores incidents and dispatches in SQLite, and streams updates over WebSocket.
- Honest states: the interface shows connecting, offline and stale-data states, never shows "All clear" when it cannot know, and never shows a failed or unconfirmed dispatch as sent, acknowledged or cancelled.

## What is simulated
- **Dispatch is mocked.** The police, patrol/crane, 108 ambulance and variable-message-sign endpoints live in `app/mock_dispatch.py`. They return realistic responses but do not contact any real service. "Sent" in this prototype means "sent to the mock".
- **Demo-mode incidents and metrics are generated**, not detected from a camera.
- The mock dispatch audit log is in memory and is lost on restart.

## What is not built yet
- Operator login, roles and permissions. The API has no authentication and allows any origin (CORS `*`).
- A tamper-proof audit trail of operator actions.
- Integration with real dispatch systems, with acknowledgement timers, escalation and retry.
- Measured detection accuracy (precision, recall, false alarms per camera-hour) on representative Andhra Pradesh footage. Rules and thresholds have not been calibrated for deployment.
- A security review, a data-retention policy, and a privacy assessment (for example DPDP Act) for plates and video.

## Before any real pilot
Run in shadow mode on an authorised camera feed, with operator approval required before any live dispatch, and acceptance criteria agreed with the responsible department.
