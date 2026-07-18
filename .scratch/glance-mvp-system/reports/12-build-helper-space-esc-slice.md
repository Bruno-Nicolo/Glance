# Helper Space Esc Slice

Date: 2026-07-18

## Implemented

- Swift Helper installs a global keyboard event tap for Space and Esc.
- Space tap posts one CoreGraphics left mouse down/up pair at the latest valid overlay cursor point.
- Space repeat events are ignored and reported as suppressed `helper.input` telemetry.
- Space clicks are suppressed while tracking input is disabled, Esc pause is active, no cursor point
  exists, or Accessibility permission is unavailable.
- Esc is hold-to-pause: first key down starts pause, repeat key downs are ignored, key up ends pause.
- Fast recovery pause freezes the overlay at the latest cursor point; privacy/low-power pause hides
  it. With no cursor point, both modes hide the overlay until a valid gaze sample arrives.
- Privacy/low-power Esc pause tells Core to release the camera provider and clear prior camera
  smoothing output.
- Helper reports `helper.input` and `helper.permission` messages over the authenticated `/events`
  WebSocket.
- Core now receives Helper-to-Core messages on `/events`, stores only latest privacy-preserving
  debug state, updates `tracking.state` during Esc hold, and broadcasts UI status changes.
- Helper refreshes Core settings through authenticated `GET /settings` so `input.space_click_enabled`
  and `tracking.pause_behavior` are respected at runtime.
- Helper retries Input Monitoring event-tap installation after denied permission so the user can
  grant permission and recover without restarting Helper.

## macOS Permissions

- Input Monitoring is required to create the global Space/Esc keyboard event tap.
- Accessibility is required to post the CoreGraphics left-click events.
- Missing Input Monitoring prevents global Space/Esc capture, but Helper keeps running and reports
  `helper.permission` with `permission: "input-monitoring"` and `state: "denied"`.
- Missing Accessibility suppresses Space click posting, but overlay rendering and Esc handling can
  continue. Helper reports `helper.permission` with `permission: "accessibility"` and
  `state: "denied"` plus a suppressed `helper.input` reason of `permission-denied`.

## Observable Status And Debug

- `/status.helper.input.latest_action` reports the latest helper action such as `space-click`,
  `pause-started`, or `pause-ended`.
- `/status.helper.input.latest_suppressed_reason` reports the latest suppression reason without
  storing raw key history.
- `/status.helper.input.paused` is true while Esc hold pause is active.
- `/status.helper.input.permissions.accessibility` and
  `/status.helper.input.permissions.input_monitoring` reflect latest Helper permission telemetry.
- `/status.tracking.state` becomes `paused` while Esc is held and restores the previous running or
  stopped state when Esc is released.
- Core sends `tracking.status` with `reason: "esc-held"` and overlay `frozen` or `hidden` according
  to `tracking.pause_behavior`.
- In `privacy-low-power`, `/status.camera` returns to stopped/inactive with no live metrics after
  Helper reports Esc pause.

## Verification

- `.venv/bin/python -m pytest core/tests/test_core_ui_api_contract.py -q`
- `swift build --package-path native/macos-helper`

The Core API tests require localhost socket binding and were run with elevated sandbox permission.
The Swift build requires SwiftPM cache writes outside the workspace and was also run with elevated
sandbox permission.

## Caveats

- Automated tests verify the Core contract-level Helper telemetry path and privacy/low-power camera
  release. Real Space/Esc capture and CoreGraphics click posting still require manual validation on
  a permissioned macOS session.
- MVP 1 is single-monitor. The click target uses the same display-logical top-left coordinates as
  the overlay cursor and does not add multi-display conversion logic.
- Settings refresh is periodic in Helper, so changes to Space click enabled or pause behavior are
  picked up shortly after Core persists them rather than through a dedicated settings push event.
- Helper does not request permission prompts itself; denied permissions are reported as recoverable
  status so the UI/manual validation path can guide the user.

## Left For MVP 2

- Space double tap.
- Space hold drag.
- Option scroll mode.
- Accessibility target snap, soft magnetism, and hysteresis.
- Input history persistence remains intentionally out of scope.
