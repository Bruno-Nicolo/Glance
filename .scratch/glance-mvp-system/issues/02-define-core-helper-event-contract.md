# Define Core to Helper Event Contract

Status: resolved
Type: grilling
Blocked by: 01

## Question

What is the MVP 1 WebSocket event contract from Python Core to Swift Helper?

ADR 0001 already decides that Python Core owns gaze estimation and Swift Helper owns overlay/input. Resolve the concrete event names, payload fields, coordinate space, timing expectations, confidence/status semantics, and compatibility expectations needed for synthetic gaze first and real gaze later.

## Decision

Python Core exposes one authenticated local WebSocket stream for Swift Helper at:

```text
GET ws://127.0.0.1:<core.port>/events
Authorization: Bearer <core.token>
```

The Helper receives Core-to-Helper events only. Helper-to-Core notifications, including Space/Esc status reporting, will be defined in ticket 11. The first synthetic slice may stream only `core.ready` and `gaze.sample`; real gaze work later must preserve the same event shape.

All Core-to-Helper events use a shared envelope:

```json
{
  "type": "gaze.sample",
  "version": 1,
  "sent_at_ms": 1760000000033,
  "sequence": 42
}
```

Envelope fields:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `type` | string | yes | Event name. MVP 1 event names are `core.ready`, `gaze.sample`, and `tracking.status`. |
| `version` | integer | yes | Contract version. MVP 1 starts at `1`. |
| `sent_at_ms` | integer | yes | Core wall-clock Unix epoch time in milliseconds when the event was sent. |
| `sequence` | integer | yes | Monotonic per-WebSocket sequence number starting at `0` for `core.ready`. Gaps are allowed; order is authoritative. |

### `core.ready`

Sent once immediately after WebSocket authentication succeeds and the socket is accepted.

```json
{
  "type": "core.ready",
  "version": 1,
  "sent_at_ms": 1760000000000,
  "sequence": 0,
  "min_version": 1,
  "target_fps": 30,
  "stale_sample_ms": 150
}
```

Fields:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `min_version` | integer | yes | Oldest event version Core expects Helper to understand for this connection. |
| `target_fps` | integer | yes | Intended gaze stream cadence. MVP 1 target is 30 FPS. |
| `stale_sample_ms` | integer | yes | Helper should ignore movement samples older than this age when received. MVP 1 uses 150 ms. |

### `gaze.sample`

Sent whenever Core has a synthetic or camera-derived gaze position for the Helper overlay.

```json
{
  "type": "gaze.sample",
  "version": 1,
  "sent_at_ms": 1760000000033,
  "sequence": 1,
  "sample_at_ms": 1760000000029,
  "x": 512.5,
  "y": 384.25,
  "display": {
    "id": "main",
    "x": 0,
    "y": 0,
    "width": 1440,
    "height": 900,
    "scale": 2,
    "coordinate_space": "display-logical-top-left"
  },
  "confidence": 0.92,
  "status": "valid",
  "source": "synthetic"
}
```

Fields:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `sample_at_ms` | integer | yes | Unix epoch milliseconds when the source sample was captured or generated. |
| `x` | number | yes | Horizontal gaze coordinate in display logical points. |
| `y` | number | yes | Vertical gaze coordinate in display logical points. |
| `display` | object | yes | Single active display bounds for interpreting `x` and `y`. MVP 1 sends only the active/main display. |
| `display.id` | string | yes | Stable-enough per-session display identifier. Use `main` until native display IDs are introduced. |
| `display.x` / `display.y` | number | yes | Display origin in the same coordinate space. MVP 1 single-monitor values are normally `0`, `0`. |
| `display.width` / `display.height` | number | yes | Display size in logical points. |
| `display.scale` | number | yes | Backing scale factor, for example `2` on Retina displays. |
| `display.coordinate_space` | string | yes | Always `display-logical-top-left`: origin is the active display's top-left corner, `x` increases right, `y` increases down. |
| `confidence` | number | yes | Normalized confidence from `0.0` to `1.0`; synthetic samples should send `1.0` unless deliberately testing degraded states. |
| `status` | string | yes | One of `valid`, `low-confidence`, `face-lost`, `uncalibrated`, or `paused`. |
| `source` | string | yes | `synthetic` or `camera`. Synthetic and real gaze must share the same coordinate and confidence semantics. |

Helper movement behavior:

- `status: "valid"` moves the overlay to `x`,`y`.
- `status: "low-confidence"` may move the overlay but should visually/debug-mark degraded confidence once that UI exists.
- `status: "face-lost"`, `"uncalibrated"`, or `"paused"` must not move the overlay to `x`,`y`; Helper should retain or hide/freeze according to the latest `tracking.status`.
- Samples received more than `stale_sample_ms` after `sample_at_ms` should be dropped.
- If samples arrive faster than Helper can draw, latest sample wins.

### `tracking.status`

Sent when Core needs Helper to update overlay/tracking state independently of a gaze coordinate.

```json
{
  "type": "tracking.status",
  "version": 1,
  "sent_at_ms": 1760000000500,
  "sequence": 20,
  "tracking": "paused",
  "overlay": "frozen",
  "reason": "esc-held"
}
```

Fields:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `tracking` | string | yes | `running`, `paused`, or `stopped`. |
| `overlay` | string | yes | `visible`, `hidden`, or `frozen`. |
| `reason` | string or null | yes | Short machine-readable reason such as `startup`, `shutdown`, `esc-held`, `camera-lost`, or `permission-denied`. |

## Timing Expectations

Core targets 30 FPS for `gaze.sample`, roughly one event every 33 ms. MVP 1 does not require exact frame pacing; the Helper should treat the stream as best effort and render the newest valid non-stale sample available on the AppKit run loop.

Core may send lower-rate samples during startup, calibration, pause, or camera loss. Helper must not synthesize clicks or movement from missing samples.

## Invalid Event Behavior

- Missing or invalid Authorization closes the WebSocket with policy violation semantics.
- Malformed JSON is ignored by Helper and logged locally.
- Unknown `type` values are ignored by Helper and logged locally.
- Unsupported `version` values are ignored by Helper and logged locally for MVP 1. If a future breaking version is required, Core should expose a newer endpoint or close with a clear protocol error after `core.ready`.
- Invalid `gaze.sample` values are ignored: non-finite coordinates, coordinates outside `display` bounds by more than one display width/height, confidence outside `0.0...1.0`, unknown `status`, or unknown `source`.

## Compatibility Rules

Version `1` is additive-compatible: Core may add optional fields to existing events, and Helper must ignore fields it does not understand. Core must not remove required fields, change coordinate space, change event names, or change status/source values inside version `1`.

Synthetic gaze and real camera gaze are intentionally the same `gaze.sample` event. Later mapping/calibration work may improve how Core produces `x`, `y`, `confidence`, and `status`, but it must not require a Helper contract change for MVP 1.

## Implementation Notes

- Python Core defines the MVP 1 constants and payload dataclasses in `core/src/glance_core/helper_events.py`.
- The existing Core WebSocket handshake now emits the versioned `core.ready` payload.
- Swift Helper has matching `Decodable` envelope/event structs and validates the envelope before later slices attach overlay movement behavior.
