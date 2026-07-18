# Real Camera Gaze Slice

Date: 2026-07-18

## Implemented

- Added `core/src/glance_core/camera_gaze.py` as the real-camera boundary.
- Uses lazy OpenCV and MediaPipe imports so Core still starts without optional vision dependencies.
- Uses OpenCV `VideoCapture` and MediaPipe Tasks `FaceLandmarker` in `LIVE_STREAM` mode.
- Extracts the MVP 1 feature contract from MediaPipe face/iris landmarks:
  `left_iris_x`, `left_iris_y`, `right_iris_x`, `right_iris_y`, `avg_iris_x`, `avg_iris_y`,
  `face_center_x`, `face_center_y`, `face_scale`, `head_yaw`, `head_pitch`, and `head_roll`.
- Extracts the MVP 1 quality contract:
  `eye_openness`, `landmark_stability`, `face_stability`, `left_right_divergence`, and
  `temporal_jitter`.
- Added camera sample metrics for captured frames, emitted samples, invalid samples, dropped frames,
  last sample time, last error, captured FPS, inference FPS, and emitted FPS.
- Wired Core's Helper WebSocket so `debug.synthetic_gaze_enabled: false` switches the stream to
  camera-derived samples while preserving the existing `gaze.sample` event shape.
- Maps camera samples through the existing calibration profile, correction grid, smoothing, and
  confidence threshold before sending them to Swift Helper.
- Reports camera startup failure as `camera_unavailable` in `/status.error` and sends a
  `tracking.status` event with `reason: "camera-unavailable"`.
- Exposes privacy-preserving aggregate camera counters through `/status.camera.metrics`.
- Does not persist frames, landmarks, feature batches, videos, or continuous gaze traces.

## Runtime Configuration

- Install vision dependencies with the `vision` extra from `core/pyproject.toml`.
- Provide the MediaPipe model through `GLANCE_FACE_LANDMARKER_MODEL_PATH`.
- If `GLANCE_FACE_LANDMARKER_MODEL_PATH` is not set, Core looks for:
  `~/Library/Application Support/Glance/models/face_landmarker.task`.
- Synthetic gaze remains the default debug setting for the existing demo path. Set
  `debug.synthetic_gaze_enabled` to `false` and start tracking to exercise the real-camera path.

## Measured Behavior

Automated verification measured the contract-level behavior with a fake camera provider:

- Core emits authenticated Helper WebSocket events at the existing target cadence.
- Camera samples are mapped through the persisted calibration profile.
- Emitted Helper events use `source: "camera"` and the existing `gaze.sample` contract.
- `/status.camera` changes to `{ "state": "running", "active": true }` after a camera sample is
  emitted.
- `/status.camera.metrics` reports captured frames, inference results, emitted samples,
  invalid samples, dropped frames, last sample time, last error, captured FPS, inference FPS, and
  emitted FPS.
- `/status.gaze` reports the latest privacy-preserving camera mapping debug payload.

No real webcam FPS number was recorded in this environment because the MediaPipe model asset,
camera permission prompt, and physical camera path were not available to the automated test run.
The implementation records runtime counters needed for a manual measurement pass once the model
asset is installed.

This means the code slice is implemented, but the MVP acceptance claim "real camera drives the
Swift overlay cursor at 30 FPS on target Macs" remains a required manual hardware validation item.

## Verification

- `.venv/bin/python -m unittest core.tests.test_camera_gaze`
- `.venv/bin/python -m unittest core.tests.test_core_ui_api_contract`
- `.venv/bin/python -m unittest discover core/tests`
- `npm --workspace @glance/ui run typecheck`
- `npm --workspace @glance/ui test`

The Core API tests require localhost socket binding. They were run with elevated sandbox permission
for that reason.

## Caveats

- The slice cannot prove camera permission ownership from the packaged Electron launch path. That
  remains a packaging validation item.
- Sustained real-device 30 FPS still needs to be measured on target Macs with the actual
  `face_landmarker.task` asset.
- The feature extraction formulas are deliberately conservative MVP estimates around MediaPipe
  face/iris landmarks. Confidence and smoothing defaults may need tuning after real calibration
  sessions.
- Calibration sample collection is still UI-driven through existing endpoints; this slice only
  replaces the runtime Helper stream after a profile exists.

## Follow-Up Decisions

- Decide where the pinned `face_landmarker.task` model asset should live in development,
  packaging, and update flows.
- Add a UI/debug surface for the camera metrics once real-device measurement starts.
- Run an end-to-end manual pass from Electron launch through camera permission, calibration,
  camera gaze streaming, and Helper overlay movement.
- Tune confidence thresholds and smoothing only from measured real-device behavior.
