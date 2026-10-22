# Frontend ↔ backend contract

The UI is driven by three event kinds on one WebSocket, plus four REST routes.
`src/api/normalize.js` is the only place that maps backend field names, so if your
schema differs, edit the aliases there and leave the components alone.

## WebSocket: `/ws/incidents` (override with VITE_WS_PATH)

Every message is JSON. Send the **full incident object** on every change (upsert), not diffs.

```json
{ "incident": { ...Incident } }
{ "metrics":  { "fps": 24.2, "ruleMs": 0.11, "cpuMsPerFrame": 34, "agentLatencyMs": 4300, "detectToDispatchS": 4.3 } }
{ "incidents": [ ...Incident ], "blackspots": [ { "km": 42, "count": 9 } ], "camera": { ...Camera } }
```

The last form is a snapshot. Send it once after connect, or serve it from `GET /api/incidents`.

## Incident

```json
{
  "id": "INC-20261022-0001",
  "type": "STALLED_VEHICLE | WRONG_WAY | TAILGATING | IMPACT",
  "severity": "P0 | P1 | P2",
  "status": "detected | analysing | dispatched | acknowledged | resolved | false_alarm",
  "confidence": 0.93,
  "createdAt": 1792650000000,
  "camera": { "id": "CAM-NH16-042", "highway": "NH-16", "km": 42.4, "lat": 16.5062, "lng": 80.648,
              "towards": "Visakhapatnam", "opposite": "Vijayawada" },
  "vehicles": [
    { "trackId": 45, "cls": "truck", "speedKmh": 0, "lane": "Fast lane", "laneIndex": 1,
      "x": 0.58, "dir": 1,
      "plate": { "text": "AP 07 AB 1234", "confidence": 0.92, "votes": 4, "frames": 5 } }
  ],
  "briefing": "Plain-language summary written by the agent.",
  "trace": [ { "stage": "observed | assessed | decided | actions", "text": "...", "at": 1792650000900 } ],
  "dispatches": [
    { "id": "INC-...-D1", "target": "VARIABLE_MESSAGE_SIGN_VMS | HIGHWAY_PATROL_NHAI | POLICE_CONTROL_ROOM | EMS_108_AMBULANCE | VEHICLE_OWNER_NOTICE",
      "status": "queued | sent | acknowledged | cancelled",
      "message": "Text sent to the stakeholder",
      "queuedAt": 0, "sentAt": 0, "ackAt": null, "cancelUntil": null }
  ],
  "verdict": null
}
```

Notes
- Times are epoch milliseconds (epoch seconds and ISO strings are also accepted).
- `plate` is `null` until ANPR has produced a result. The UI shows "Reading plate".
- `x` is the vehicle's position along the road as 0 to 1, `dir` is 1 for with-traffic and -1 for wrong-way. They only drive the lane view.
- `queued` dispatches carry `cancelUntil`. The UI shows a countdown and a Cancel button until then.
- `status: false_alarm` and `resolved` count as closed. Everything else is active.

## REST

| Route | Purpose |
|---|---|
| `GET /api/incidents` | Snapshot of recent incidents (today plus history), with `blackspots` and `camera` |
| `POST /api/incidents/{id}/dispatches/{dispatchId}/cancel` | Operator cancels a queued dispatch. The backend must then skip the mock POST. |
| `POST /api/incidents/{id}/feedback` body `{ "verdict": "confirmed" | "false_alarm" }` | Operator feedback, the feedback loop from the pipeline sketch. Persist it. |
| `GET /evidence/snapshots/{id}.jpg`, `GET /evidence/clips/{id}.mp4` | Evidence files |

Video: the Camera tab shows an `<img>` pointing at VITE_VIDEO_PATH (default `/video_feed`), so it expects MJPEG.
