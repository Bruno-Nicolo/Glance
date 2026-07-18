# Build Calibration UI Core Slice

Status: resolved
Type: prototype
Blocked by: 06

## Question

Can the UI drive a full MVP 1 calibration session against Python Core and produce persisted calibration data without using the real camera yet?

Build the calibration flow using synthetic or manually supplied samples first. Record whether the flow is usable, what files are written, and what must change before real MediaPipe samples are connected.

## Resolution

The Electron UI now drives Core calibration sessions with synthetic samples, completes initial
9-point calibration plus 5-point validation, persists `calibration.json`, and supports 1-point drift
correction against the existing profile.

Prototype findings are recorded in
[07-calibration-ui-core-slice.md](../reports/07-calibration-ui-core-slice.md).
