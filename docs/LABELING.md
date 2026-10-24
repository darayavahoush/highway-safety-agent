# Labelling the drone clips

Source clips belong to the repository owner. The licence for derived labels is set by the owner and must be stated here before publishing: LICENCE: TBD.

## Detection labels (sparse frames)

tools/sample_frames.py writes labels/frames/<clip>_<frame>.jpg and labels/frames/manifest.csv.

Manifest columns:
- clip: clip file name without extension
- source_frame: 0-based frame index in the video
- mot_frame: 1-based index, for MOT tools
- timestamp_s: time in the clip
- image: JPEG file name
- scene: fill with day, night, rain, glare, dense or occluded; separate several with a semicolon

Box labels use COCO format, one file per split.

## Tracking labels (continuous segments)

Tracking metrics (IDF1, HOTA) need unbroken sequences, so label short continuous segments, for example three 10-second segments per clip, and record their start and end frames in labels/tracks/segments.csv. Track metrics are computed only on those segments and the report must say so.

Per clip, labels/tracks/<clip>.txt uses MOT Challenge format, one line per box:

frame,id,bb_left,bb_top,bb_width,bb_height,conf,class,visibility

- frame: mot_frame (1-based)
- id: stable for the same vehicle across the segment
- conf: 1 for ground truth
- class: 1 car, 2 motorcycle, 3 truck, 4 bus, 5 other (proposed: auto-rickshaw, tractor)
- visibility: 0.0 to 1.0, the fraction not occluded

Frames outside labelled segments are not scored.

## Verification

A second annotator checks a random 20 percent of tracks and records the result in labels/tracks/REVIEW.csv: reviewer, date, tracks checked, disagreements. If there is no second annotator, the benchmark report must say the labels are single-annotator and not independently verified.

## Not in git

labels/frames/ is gitignored because it is derived from video. Commit only tools, tests and docs.
