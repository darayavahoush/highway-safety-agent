# Highway Safety Agent: control room frontend

React + Vite. No UI framework. Plain CSS with design tokens at the top of `src/styles.css`.

## Run

```bash
npm install
cp .env.example .env     # VITE_DATA_MODE=demo works with no backend
npm run dev              # http://localhost:5173
```

Demo mode runs a built-in simulator that raises a stalled truck, tailgating, a crash and a wrong-way
car in turn, with the agent's reasoning, plates, dispatches, the operator cancel window and acknowledgements.

Set `VITE_DATA_MODE=live` to use the FastAPI backend. Read `src/api/CONTRACT.md` first.

## Layout

| Area | File |
|---|---|
| Incident queue (left) | `components/IncidentQueue.jsx` |
| Lane view, camera, digital twin tabs (centre) | `components/LiveStage.jsx`, `LaneMap.jsx` |
| Dispatch activity (centre, below) | `components/ActivityLog.jsx` |
| Briefing, plates, reasoning, dispatches, feedback (right) | `components/IncidentDetail.jsx` and children |
| Metrics and blackspot strip (footer) | `components/StatsStrip.jsx` |
| Data source switch | `api/client.js` (live) and `api/simulator.js` (demo) |

## Wiring the existing Three.js twin

Serve the twin page from the backend or its own dev server and set `VITE_TWIN_URL`. It loads in the Digital twin tab.
