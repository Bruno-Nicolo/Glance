# Build Synthetic Gaze Overlay Slice

Status: resolved
Type: prototype
Blocked by: 02

## Question

Can the first vertical slice prove the runtime path by moving the Swift overlay cursor from synthetic screen-coordinate gaze events emitted by Python Core?

Build the cheapest concrete slice that validates authenticated WebSocket delivery, event decoding, overlay movement, lifecycle behavior, and a visible cursor on macOS. Record the implementation facts and any contract changes needed before real gaze work begins.

## Implementation Facts

- Python Core now streams `core.ready`, `tracking.status`, and synthetic `gaze.sample` events on the authenticated `/events` WebSocket.
- Synthetic samples use the existing version 1 Core-to-Helper contract, `source: "synthetic"`, `status: "valid"`, `confidence: 1.0`, and a looping path at the target 30 FPS.
- The synthetic display defaults to `main`, origin `0,0`, size `1440x900`, scale `2`, and can be overridden with `GLANCE_SYNTHETIC_DISPLAY_*` environment variables for local display matching.
- Swift Helper now applies decoded valid fresh `gaze.sample` events to the overlay cursor on the main AppKit thread.
- Helper ignores stale samples, invalid samples, hidden/frozen overlay states, and non-moving gaze statuses before updating the cursor.
- Helper applies `tracking.status` overlay visibility, with `hidden` hiding the view and `frozen` retaining the current cursor position.

## Contract Notes

- No version 1 schema changes were required for this slice.
- The first real-gaze slice should replace only the Core sample producer; the Helper can continue consuming the same `gaze.sample` event shape.
- Native display discovery is still future work. Until then, synthetic display bounds are configurable environment data owned by the local slice.

## Validation

- `PYTHONPATH=core/src python3 -m unittest discover core/tests` passed.
- `swift build --package-path native/macos-helper` passed.
- A localhost smoke test using the repo `.venv` verified that invalid WebSocket auth is rejected and valid auth receives ordered `core.ready`, `tracking.status`, and moving `gaze.sample` events.
- The Swift Helper overlay path was compile-verified. A live visual macOS run was not automated in this slice; the runnable path is `npm run dev:core` or `PYTHONPATH=core/src python3 -m glance_core` with the Helper launched by Core.
