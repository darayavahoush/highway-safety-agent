# Branch integration and baseline (Stage 0, partial)

Integration branch: `integrate/all-branches`, created from `main` at `c82a2c3`-descendant `43fdbd4`.

## Branch status before merging

| Branch | Status vs `main` | Action |
|---|---|---|
| `main` | Base | — |
| `fix/render-deployment` | Fully contained in `main` (0 unique commits) | None needed |
| `improvements/control-room-accessibility` | Fully contained in `main` (0 unique commits) | None needed |
| `fix/render-docker-deployment` | 3 unique commits (Docker config, optional Parallel key, OCR verification) | Merged; see below |

## Merge decisions

- `Dockerfile`: branch removes a leading UTF-8 byte-order mark before `FROM`. Kept (fixes a potential Docker parse issue).
- `render.yaml`: branch conflicts with `main`. The branch points `VIDEO_SOURCE` at `/tmp/highway-demo-video-missing.mp4` and removes the `PARALLEL_API_KEY` entry. `main` has `VIDEO_SOURCE: demo_videos/drone/DJI_0011.MP4` and `PARALLEL_API_KEY` (`sync: false`). `main`'s version was kept as the newer configuration. **This is a judgement call; confirm which `VIDEO_SOURCE` you want deployed.**

## Verification (measured on this branch)

- Backend: `python -m pytest tests -q` → 25 passed.
- Frontend: `npm test` → 79 passed (10 files).
- Frontend: `npm run build` → succeeded.

## Not yet measured (spec Stage 0 items still open)

- Detector/tracker benchmarks: NOT RUN (no labelled evaluation dataset selected yet).
- Edge (Jetson) latency: NOT RUN (no hardware available in this environment).
- Safety-regression failure injection (spec constraint 7): NOT RUN.
- Full API contract diff and SSE/WebSocket audit: NOT RUN.

## Evaluation dataset

Clip catalogue in `app/main.py` references HuggingFace `anabaena/drone-vehicle-clips`. The `demo_videos/` directory is not in the repository, so none of the listed clips is available in a clean checkout.
