# Highway Safety & Accident Prevention Autonomous Agent (HRAP-2026)

Autonomous Edge Perception & Cognitive Safety Agent for Highway Accident Prevention.
Developed for the Highway Road Accident Prevention Innovation Challenge 2026.

## Running the Application

### Live Video Mode (Default)
Run the backend with a video stream or video file:
```bash
VIDEO_SOURCE="demo_videos/drone/DJI_0011.MP4" ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Simulation Mode (`ENABLE_SIMULATION=1`)
By default, synthetic simulation endpoints (`POST /api/simulate_incident/{incident_type}`) are disabled and return HTTP 403 Forbidden:
`"Simulation endpoints are disabled. Run with ENABLE_SIMULATION=1 for testing without a video feed."`

To enable simulation endpoints for testing without a live video feed:
```bash
ENABLE_SIMULATION=1 ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```
When enabled, you can trigger synthetic incidents:
- `POST /api/simulate_incident/stalled`
- `POST /api/simulate_incident/wrong_way`
- `POST /api/simulate_incident/tailgating`
