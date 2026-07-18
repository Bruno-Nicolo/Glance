# Core to UI API Contract

Status: MVP 1 contract version 1.

Python Core exposes an authenticated localhost FastAPI API. Electron reads `runtime/core.port`
and `runtime/core.token`, sends `Authorization: Bearer <token>` on every HTTP request and
WebSocket handshake, and remains outside the runtime-critical gaze path.

## HTTP

All responses use JSON. Recoverable client-facing failures use this envelope:

```json
{
  "error": {
    "code": "invalid_settings",
    "message": "Unknown settings field: tracking.unknown",
    "recoverable": true
  }
}
```

### `GET /health`

Returns Core liveness and the UI contract version.

```json
{ "status": "ok", "contract": "core-ui", "contract_version": 1 }
```

### `GET /status`

Returns UI dashboard state. `ui.runtime_critical` is always `false` in MVP 1.

```json
{
  "contract_version": 1,
  "core": { "state": "running", "pid": 1234 },
  "helper": { "state": "running" },
  "camera": { "state": "stopped", "active": false },
  "tracking": { "state": "stopped", "input_enabled": false },
  "gaze": {
    "contract_version": 1,
    "profile_id": null,
    "status": "uncalibrated",
    "confidence": 0.0,
    "sample_at_ms": null,
    "source": "synthetic",
    "correction": "idw-3x3",
    "smoothing_alpha": 0.5,
    "confidence_threshold": 0.6,
    "invalid_reason": "uncalibrated"
  },
  "calibration": { "state": "missing", "profile_id": null },
  "ui": { "runtime_critical": false },
  "error": null
}
```

Allowed states:

- `core.state`: `starting`, `running`, `shutting-down`, `error`
- `helper.state`: `not-started`, `running`, `exited`, `error`
- `camera.state`: `stopped`, `starting`, `running`, `error`
- `tracking.state`: `stopped`, `running`, `paused`, `error`
- `gaze.status`: `valid`, `low-confidence`, `face-lost`, `uncalibrated`, `paused`
- `gaze.source`: `synthetic`, `camera`
- `calibration.state`: `missing`, `in-progress`, `valid`, `error`

`gaze` is privacy-preserving debug/status telemetry for the mapper. It reports confidence,
sample time, source, correction mode, smoothing alpha, threshold, and invalid reason, but never
camera frames, raw landmarks, feature vectors, quality vectors, or gaze traces. See
[Gaze Mapping and Confidence Contract](gaze-mapping-and-confidence-contract.md).

### `GET /settings`

Returns Core-owned persisted settings from `config.json`.

```json
{
  "contract_version": 1,
  "tracking": {
    "pause_behavior": "fast-recovery",
    "confidence_threshold": 0.6,
    "smoothing": 0.5
  },
  "input": { "space_click_enabled": true },
  "debug": { "synthetic_gaze_enabled": true }
}
```

### `PUT /settings`

Accepts a partial section update with the same nested field names as `GET /settings`.
Unknown fields are rejected with `400 invalid_settings`. Core persists the merged settings
and returns the full settings object.

### `POST /controls/start`

Requests Core to start or resume tracking. Returns the same shape as `GET /status`.

### `POST /controls/stop`

Requests Core to stop tracking without shutting down Core or Helper. Returns the same shape
as `GET /status`.

### `POST /calibration/sessions`

Creates one calibration run. Core owns the session id, target order, and persisted result.

Request:

```json
{ "mode": "initial-9-point", "display_id": "main" }
```

`mode` is one of `initial-9-point`, `validation`, or `drift-1-point`.

Response:

```json
{
  "contract_version": 1,
  "session_id": "cal_01HX...",
  "mode": "initial-9-point",
  "state": "collecting",
  "current_target_index": 0,
  "targets": [
    {
      "id": "center",
      "x": 720,
      "y": 450,
      "display": {
        "id": "main",
        "x": 0,
        "y": 0,
        "width": 1440,
        "height": 900,
        "scale": 2,
        "coordinate_space": "display-logical-top-left"
      }
    }
  ],
  "error": null
}
```

Session states are `collecting`, `processing`, `complete`, `cancelled`, and `error`.
Coordinates use display-logical top-left space, matching Helper gaze events.

### `POST /calibration/sessions/{session_id}/samples`

Records one batch for a target. Payloads must not include raw camera frames.

Request:

```json
{
  "target_id": "center",
  "samples": [
    {
      "sample_at_ms": 1721300000000,
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
  ]
}
```

Response returns the session shape from `POST /calibration/sessions` with updated progress.
Invalid session id, target id, sample feature ranges, or cancelled/completed sessions return a
recoverable `400 invalid_calibration_sample` error.

Core stores submitted samples only in memory while the session is active. The persisted
`calibration.json` profile contains fitted model parameters, correction nodes, display metadata,
and validation metrics, never raw feature samples or image data. See
[Calibration Flow and Data Model](calibration-flow-and-data-model.md) for the exact MVP 1 flow,
profile schema, retry states, and privacy boundaries.

### `POST /calibration/sessions/{session_id}/complete`

Requests Core to fit or validate the calibration and persist `calibration.json` when successful.

Response:

```json
{
  "contract_version": 1,
  "session_id": "cal_01HX...",
  "state": "complete",
  "mode": "validation",
  "profile_id": "profile_01HX...",
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
  "status": { "...": "same shape as GET /status" },
  "error": null
}
```

For `mode: "initial-9-point"`, `validation` is `null` until a later validation session is
accepted. Insufficient samples or failed validation return `400 calibration_failed` with
`recoverable: true`.

### `DELETE /calibration/sessions/{session_id}`

Cancels an in-progress session and returns:

```json
{
  "contract_version": 1,
  "session_id": "cal_01HX...",
  "state": "cancelled",
  "status": { "...": "same shape as GET /status" },
  "error": null
}
```

### `POST /shutdown`

Requests full runtime shutdown: Python Core stops Swift Helper, terminates itself, and tells
Electron it should exit.

```json
{
  "status": "shutting-down",
  "scope": "full-runtime",
  "ui_should_exit": true
}
```

Closing Electron or pressing `Cmd+Q` is not a full runtime shutdown.

## WebSocket

### `GET /ui/events`

Electron opens `ws://127.0.0.1:{port}/ui/events` with the same bearer token. The stream is
non-critical status/debug UI telemetry. MVP 1 events:

```json
{ "type": "ui.ready", "contract_version": 1 }
```

```json
{
  "type": "status.changed",
  "contract_version": 1,
  "status": { "...": "same shape as GET /status" }
}
```

Calibration UI changes use:

```json
{
  "type": "calibration.changed",
  "contract_version": 1,
  "session_id": "cal_01HX...",
  "state": "collecting",
  "target_id": "center",
  "completed_targets": 0,
  "total_targets": 9,
  "error": null
}
```

Runtime gaze samples for Swift Helper remain on `/events` and are not routed through Electron.
