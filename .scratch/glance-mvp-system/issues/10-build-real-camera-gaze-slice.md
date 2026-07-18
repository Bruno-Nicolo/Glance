# Build Real Camera Gaze Slice

Status: implemented
Type: task
Blocked by: 07, 09

## Question

Can Python Core replace synthetic gaze with webcam/MediaPipe/OpenCV gaze estimation, apply calibration mapping, and drive the Swift overlay cursor at the target MVP 1 rate?

Implement the real-camera slice and record measured behavior, verification steps, performance caveats, and any follow-up decisions needed for confidence/smoothing tuning.

## Result

Implemented the real-camera runtime boundary and Core-to-Helper camera streaming path. Real-device
30 FPS and macOS camera-permission behavior still require the manual hardware validation pass
called out in the report.

See [10-build-real-camera-gaze-slice.md](../reports/10-build-real-camera-gaze-slice.md).
