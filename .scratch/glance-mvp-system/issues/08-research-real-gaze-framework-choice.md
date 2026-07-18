# Research Real Gaze Framework Choice

Status: implemented
Type: research
Blocked by: 01

## Question

Which ready-made MediaPipe/OpenCV-based gaze estimation approach should MVP 1 use on macOS, and what packaging/runtime constraints matter for this repo?

ADR 0001 rules out training a custom model and requires a ready-made model/framework. Resolve the candidate library/framework choice, install/runtime constraints, camera permission implications, expected performance at target 30 FPS, and any risks that affect the real-camera implementation slice.

## Result

Use MediaPipe Tasks `FaceLandmarker` in Python `LIVE_STREAM` mode with OpenCV `VideoCapture` as the
macOS webcam source. Glance should derive the existing calibration feature contract from MediaPipe
landmarks and keep screen-coordinate gaze mapping in Core's calibrated regression/correction pipeline.

See [08-research-real-gaze-framework-choice.md](../reports/08-research-real-gaze-framework-choice.md).
