# Helper Input Behavior Contract

Status: MVP 1 contract version 1.

This contract resolves Swift Helper behavior for Space click and Esc pause. It extends
[ADR 0001](adr/0001-glance-mvp-architecture.md) and the Core-to-Helper stream in
[Core to Helper Event Contract](../.scratch/glance-mvp-system/issues/02-define-core-helper-event-contract.md).

## Scope

MVP 1 supports:

- Space tap as one left click at the current overlay cursor.
- Esc hold as temporary tracking pause.
- Permission/status reporting from Helper to Core.

MVP 1 intentionally does not implement Space double tap, Space hold drag, Option scroll mode,
Accessibility target snap, or input history persistence.

## Space Click

Swift Helper owns the global Space key handling and the CoreGraphics click event.

Key semantics:

- Space `keyDown` starts a click candidate when tracking input is enabled and Esc pause is not active.
- Repeated Space `keyDown` events while the key is already down are ignored.
- Space `keyUp` completes the candidate only if input is still enabled, Esc pause is still inactive,
  Helper has a cursor point, and click-posting permission is still available.
- If Space is released after any click precondition becomes false, the candidate is cancelled and no
  click is posted.
- If Space is pressed while input is disabled, paused, missing a cursor point, or missing permission,
  no click is posted and Helper may report a suppressed `helper.input` event.

Click target:

- The click target is the latest Helper overlay cursor position at Space `keyUp`.
- Coordinates use `display-logical-top-left`, the same display space as `gaze.sample`.
- Helper converts the logical top-left cursor point to the native CoreGraphics coordinate required
  for event posting at the AppKit/CoreGraphics boundary.
- The CoreGraphics event sequence is left mouse down followed by left mouse up at the same point.
- The click uses the frozen cursor position if Esc is not active and the overlay is frozen for any
  non-pause reason. It never clicks while Esc pause is active.

The existing `input.space_click_enabled` setting gates only Space click behavior. Disabling it does
not disable Esc pause.

## Esc Pause

Esc is hold-to-pause, not toggle-to-pause.

Key semantics:

- Esc `keyDown` enters pause on the first non-repeat key down.
- Repeated Esc `keyDown` events while Esc is held are ignored.
- Esc `keyUp` exits pause.
- While paused, Helper suppresses Space click candidates and does not post mouse input.

Visual behavior:

- For `tracking.pause_behavior: "fast-recovery"`, Helper freezes the overlay at the last valid cursor
  position while Esc is held.
- For `tracking.pause_behavior: "privacy-low-power"`, Helper hides the overlay while Esc is held.
- If there is no previous cursor position, both pause modes keep the overlay hidden until tracking
  resumes with a valid cursor.

Core behavior:

- Helper notifies Core when Esc pause starts and ends.
- Core sets `tracking.state` to `paused` while Esc is held and restores the previous start/stop state
  after Esc is released.
- In fast recovery, Core keeps camera/tracking resources warm and sends `tracking.status` with
  `overlay: "frozen"` and `reason: "esc-held"`.
- In privacy/low power, Core stops or suspends camera/tracking work and sends `tracking.status` with
  `overlay: "hidden"` and `reason: "esc-held"`.

## Helper-to-Core Messages

Helper sends input and permission messages on the authenticated `/events` WebSocket. Core-to-Helper
and Helper-to-Core messages share the same envelope fields: `type`, `version`, `sent_at_ms`, and
`sequence`.

### `helper.input`

```json
{
  "type": "helper.input",
  "version": 1,
  "sent_at_ms": 1760000000600,
  "sequence": 21,
  "action": "space-click",
  "cursor": {
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
    }
  },
  "suppressed_reason": null
}
```

`action` is one of `space-down`, `space-up`, `space-click`, `esc-down`, `esc-up`,
`pause-started`, or `pause-ended`. Key transition actions are ephemeral status/debug telemetry only;
Core/UI must not persist them as raw key history.

`cursor` is included for `space-click` when a click is posted. It is `null` when no cursor point is
available or when an action is suppressed.

`suppressed_reason` is `null` for completed actions. Suppressed actions use one of `disabled`,
`paused`, `permission-denied`, `repeat`, or `no-cursor`.

Core and UI may use this event for current debug/status state. They must not persist an input
history by default.

### `helper.permission`

```json
{
  "type": "helper.permission",
  "version": 1,
  "sent_at_ms": 1760000000610,
  "sequence": 22,
  "permission": "accessibility",
  "state": "denied",
  "required_for": ["space-click"],
  "recoverable": true
}
```

`permission` is `accessibility` or `input-monitoring`.

`state` is `granted`, `denied`, or `unknown`.

`required_for` entries are `space-click` or `esc-pause`.

Permission behavior:

- Missing Accessibility permission disables CoreGraphics click posting but does not prevent overlay
  rendering.
- Missing Input Monitoring permission disables global Space/Esc capture.
- Permission failures are recoverable. Core surfaces them through status/debug UI as Helper errors,
  and Helper keeps running so the user can grant permissions and retry.
- Helper should report permission state at startup and whenever it detects a permission-dependent
  action cannot run.

## Privacy

Helper input reporting is privacy-preserving debug telemetry. Core/UI may expose the latest Helper
input state, latest suppressed reason, current pause state, and current permission state. Core/UI
must not save raw key events, continuous input history, or click history by default.
