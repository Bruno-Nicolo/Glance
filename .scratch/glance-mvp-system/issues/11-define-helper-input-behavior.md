# Define Helper Input Behavior

Status: resolved
Type: grilling
Blocked by: 02

## Question

What exact MVP 1 behavior should Swift Helper implement for Space click and Esc pause?

ADR 0001 assigns global key handling and CoreGraphics input events to Swift Helper. Resolve key down/up semantics, click target position, pause visual behavior, whether pause notifies Core, permission failure behavior, and what debug/status information Core/UI should see.

## Decision

The MVP 1 behavior is defined in
[Helper Input Behavior Contract](../../../docs/helper-input-behavior-contract.md).

Space is a tap-only MVP 1 click:

- Space `keyDown` starts a click candidate when tracking input is enabled and Esc pause is inactive.
- Repeated Space `keyDown` events are ignored.
- Space `keyUp` posts exactly one CoreGraphics left mouse down/up pair at the current overlay cursor
  only if input, pause, cursor, and permission preconditions still hold.
- Disabled input, active pause, missing cursor, repeated key events, or missing permissions suppress the click.

Esc is hold-to-pause:

- First Esc `keyDown` enters pause.
- Repeated Esc `keyDown` events are ignored.
- Esc `keyUp` exits pause.
- Space clicks are suppressed while paused.

Pause visual behavior follows `tracking.pause_behavior`:

- `fast-recovery` freezes the overlay at the last valid cursor and keeps tracking resources warm.
- `privacy-low-power` hides the overlay and allows Core to stop or suspend camera/tracking work.
- With no previous cursor point, both modes keep the overlay hidden until a valid cursor exists.

Helper notifies Core over the authenticated `/events` WebSocket:

- `helper.input` reports current input actions, completed Space clicks, pause start/end, and suppressed reasons.
- `helper.permission` reports Accessibility/Input Monitoring state and recoverable failures.

Core/UI may surface the latest Helper input state, pause state, suppressed reason, and permission
state for status/debug. They must not persist raw key events, click history, continuous input
history, camera frames, or gaze traces by default.

MVP 2 keeps Space double tap, Space hold drag, Option scroll mode, and Accessibility snap out of
this behavior.
