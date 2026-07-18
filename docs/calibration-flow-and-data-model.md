# Calibration Flow and Data Model

Status: MVP 1 contract version 1.

ADR 0001 fixes the calibration scope: Python Core owns calibration, gaze mapping, validation,
and `calibration.json` persistence. Electron renders the guided UI and sends feature batches to
Core; it never owns the model or writes calibration files.

## Coordinate And Feature Contract

Calibration targets and fitted gaze coordinates use the same display space as Helper gaze events:
`display-logical-top-left`. The origin is the active display's top-left corner, `x` increases
right, and `y` increases down. MVP 1 calibrates only the main display.

Every camera-derived calibration sample contains normalized feature values plus quality values:

```json
{
  "features": {
    "left_iris_x": 0.42,
    "left_iris_y": 0.51,
    "right_iris_x": 0.44,
    "right_iris_y": 0.5,
    "avg_iris_x": 0.43,
    "avg_iris_y": 0.505,
    "face_center_x": 0.5,
    "face_center_y": 0.48,
    "face_scale": 0.37,
    "head_yaw": 0.02,
    "head_pitch": -0.01,
    "head_roll": 0.01
  },
  "quality": {
    "eye_openness": 0.92,
    "landmark_stability": 0.88,
    "face_stability": 0.9,
    "left_right_divergence": 0.04,
    "temporal_jitter": 0.03
  }
}
```

Feature and quality values must be finite numbers. Normalized position, scale, openness, stability,
divergence, and jitter values are constrained to `0.0...1.0`; head pose values are finite signed
numbers.

## Initial 9-Point Flow

The UI starts with `POST /calibration/sessions` and `mode: "initial-9-point"`. Core pauses normal
tracking input, creates a session, records the display bounds, and returns targets in this order:

```text
center
top-left
top-center
top-right
middle-left
middle-right
bottom-left
bottom-center
bottom-right
```

Targets use display ratios before conversion to logical display coordinates:

```text
0.5,0.5
0.1,0.1  0.5,0.1  0.9,0.1
0.1,0.5           0.9,0.5
0.1,0.9  0.5,0.9  0.9,0.9
```

For each target, the UI renders the target and posts a batch to
`POST /calibration/sessions/{session_id}/samples`. MVP 1 should collect about 700 ms of samples per
target and may discard the first 150 ms after target display to avoid transition movement. Core
returns updated session progress after each accepted batch.

When all targets are collected, the UI calls `POST /calibration/sessions/{session_id}/complete`.
Core fits a ridge regression from the feature vector to screen `x/y`, then derives a 3x3 local
correction grid from residuals at the nine calibration targets. A successful initial calibration is
persisted only after validation is accepted.

## Validation Flow

Validation uses the same session endpoint with `mode: "validation"`. Core chooses three to five
targets that are not in the same fixed order as the 9-point grid. The UI renders them exactly like
calibration targets and posts feature batches.

Core maps validation features through the current fitted model and correction grid, compares
predicted coordinates to the target coordinates, and returns:

```json
{
  "mode": "validation-5-point",
  "mean_error_px": 42.5,
  "median_error_px": 38.25,
  "max_error_px": 91.2,
  "accepted": true,
  "mean_error_threshold_px": 90,
  "max_error_threshold_px": 160,
  "sample_count": 240
}
```

MVP 1 accepts validation when mean error is at or below `90 px` and max error is at or below
`160 px`. These thresholds are product defaults, not user settings. Later real-camera work may tune
them only by updating this contract and tests.

## Quick Drift Correction

Drift correction uses `mode: "drift-1-point"` and one center target. It does not replace the
regression coefficients. Core computes the current center residual and applies it as an additive
offset across the correction grid, updates `updated_at_ms`, and keeps the existing validation
history plus a `drift_corrections` count.

If the one-point correction error is too large to be plausible, Core rejects it with
`400 calibration_failed` and leaves the previous profile unchanged. MVP 1 uses `220 px` as the
plausibility ceiling.

## Retry And Failure States

Session states are:

- `collecting`: the UI may submit samples for the current target.
- `processing`: Core is fitting or validating; sample submission is rejected.
- `complete`: Core finished and no more samples are accepted.
- `cancelled`: the UI or Core cancelled the session; no data is persisted.
- `error`: the session failed and can be retried with a new session.

Recoverable failures use the Core/UI error envelope:

- `invalid_calibration_session`: unknown session id or mode mismatch.
- `invalid_calibration_sample`: wrong target id, empty batch, non-finite values, out-of-range
  normalized values, or raw frame/video fields in the payload.
- `calibration_failed`: insufficient accepted samples, validation above threshold, implausible
  drift correction, or model fitting failure.
- `calibration_busy`: another calibration session is already collecting or processing.

On target-level sample failure, the UI should keep the same target visible and retry collection.
On `calibration_failed`, the UI should offer retrying validation or restarting the full 9-point
flow depending on Core's message. Cancelling a session discards all in-memory samples and restores
the previous calibration status.

## Persisted `calibration.json`

Python Core persists exactly one active calibration profile for MVP 1:

```json
{
  "contract_version": 1,
  "profile_id": "profile_01HX...",
  "created_at_ms": 1721300000000,
  "updated_at_ms": 1721300005000,
  "display": {
    "id": "main",
    "x": 0,
    "y": 0,
    "width": 1440,
    "height": 900,
    "scale": 2,
    "coordinate_space": "display-logical-top-left"
  },
  "feature_names": [
    "left_iris_x",
    "left_iris_y",
    "right_iris_x",
    "right_iris_y",
    "avg_iris_x",
    "avg_iris_y",
    "face_center_x",
    "face_center_y",
    "face_scale",
    "head_yaw",
    "head_pitch",
    "head_roll"
  ],
  "regression": {
    "regularization": "ridge",
    "regularization_alpha": 1.0,
    "x_coefficients": [0.0],
    "y_coefficients": [0.0],
    "x_intercept": 0.0,
    "y_intercept": 0.0
  },
  "correction_grid": [
    { "target_id": "center", "x_ratio": 0.5, "y_ratio": 0.5, "dx": 0.0, "dy": 0.0 }
  ],
  "validation": {
    "mode": "validation-5-point",
    "mean_error_px": 42.5,
    "median_error_px": 38.25,
    "max_error_px": 91.2,
    "accepted": true,
    "mean_error_threshold_px": 90,
    "max_error_threshold_px": 160,
    "sample_count": 240
  },
  "drift_corrections": 0
}
```

The executable mirror for this schema lives in `core/src/glance_core/calibration_contract.py`.

## Privacy Boundary

Core may keep calibration feature batches in memory only for the active session. By default it must
not persist:

- camera frames
- videos
- raw MediaPipe landmarks
- raw per-sample calibration feature batches
- validation gaze traces
- continuous gaze traces
- observed Accessibility targets
- input history

Minimal technical logs may include session ids, failure codes, aggregate sample counts, and
aggregate validation metrics. Logs must not include frame data or per-sample feature vectors by
default.
