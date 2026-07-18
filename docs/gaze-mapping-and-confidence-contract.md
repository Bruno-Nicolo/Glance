# Gaze Mapping and Confidence Contract

Status: MVP 1 contract version 1.

ADR 0001 fixes Python Core as the owner of calibration, mapping, smoothing, confidence, and
Helper gaze samples. This contract defines the minimal MVP 1 runtime mapping behavior after a
calibration profile exists.

## Runtime Pipeline

Core maps each camera-derived sample in this order:

```text
normalized MediaPipe/OpenCV features
-> persisted ridge regression
-> inverse-distance weighted 3x3 correction grid
-> exponential smoothing
-> confidence classification
-> Helper gaze.sample event
```

Coordinates are `display-logical-top-left`, matching calibration targets and Helper events. MVP 1
uses the main display only.

## Mapping

The feature vector is the persisted `calibration.json.feature_names` order:

```text
left_iris_x
left_iris_y
right_iris_x
right_iris_y
avg_iris_x
avg_iris_y
face_center_x
face_center_y
face_scale
head_yaw
head_pitch
head_roll
```

Core computes raw `x/y` with the persisted ridge regression coefficients and intercepts. It then
converts the raw point to display ratios and applies an inverse-distance weighted correction from
the 3x3 residual grid. An exact correction-node hit uses that node's `dx/dy`; otherwise all
available nodes contribute by `1 / distance_squared`.

## Smoothing

MVP 1 uses exponential smoothing with default alpha `0.5`:

```text
output = previous_output + ((corrected_output - previous_output) * alpha)
```

If there is no previous valid output, Core emits the corrected point directly. The user-facing
`tracking.smoothing` setting is the alpha sent in debug/status output and used by the mapper.

## Confidence

The confidence inputs are:

```text
eye_openness
landmark_stability
face_stability
left_right_divergence
temporal_jitter
```

MVP 1 confidence is conservative:

```text
confidence = min(
  eye_openness,
  landmark_stability,
  face_stability,
  1 - left_right_divergence,
  1 - temporal_jitter
)
```

The default low-confidence threshold is `0.6`. Samples at or above the threshold are `valid`.
Samples below the threshold keep mapped coordinates but use status `low-confidence`.

## Invalid Samples

Invalid runtime samples do not move the overlay cursor. Core freezes the previous output coordinate
when one exists, sets confidence to `0.0`, and marks one of these statuses:

- `face-lost`
- `uncalibrated`
- `paused`

The Swift Helper contract accepts those statuses but ignores them for movement. If there is no
previous output, Core may emit `0,0`; Helper still ignores the sample because the status is invalid.
Status/debug `invalid_reason` is constrained to `face-lost`, `uncalibrated`, `paused`,
`synthetic-disabled`, or `tracking-stopped`.

## Status and Debug

`GET /status` includes a privacy-preserving `gaze` object:

```json
{
  "contract_version": 1,
  "profile_id": "profile_01HX...",
  "status": "valid",
  "confidence": 0.92,
  "sample_at_ms": 1721300000000,
  "source": "camera",
  "correction": "idw-3x3",
  "smoothing_alpha": 0.5,
  "confidence_threshold": 0.6,
  "invalid_reason": null
}
```

This object must not include camera frames, raw landmarks, feature vectors, quality vectors, or
continuous gaze traces.

The executable mirror for this contract lives in
`core/src/glance_core/gaze_mapping_contract.py`.
