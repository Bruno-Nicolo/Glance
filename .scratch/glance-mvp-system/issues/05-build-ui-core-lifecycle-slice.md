# Build UI Core Lifecycle Slice

Status: complete
Type: task
Blocked by: 04

## Question

Can Electron reliably discover or start Python Core, display MVP 1 status, and request full shutdown while Core and Helper keep running when the UI closes?

Complete the UI/Core lifecycle slice according to ADR 0001 and the resolved API contract. Record what was implemented, how it was verified, and any remaining lifecycle gaps before calibration work starts.

## Resolution

Implemented the UI/Core lifecycle slice through Electron's main/preload/renderer boundary:

- Electron discovers Core from `~/Library/Application Support/Glance/runtime/core.port` and `core.token`, authenticates `/health`, and connects to an existing healthy Core.
- If discovery files point to an unhealthy Core, Electron removes stale `core.pid`, `core.lock`, and `core.port`, starts Python Core with `PYTHONPATH=core/src`, waits for authenticated `/health`, and opens `/ui/events`.
- The renderer displays MVP 1 Core, Helper, Camera, Tracking, Input, Calibration, and Core/UI contract status, plus start/stop/settings controls.
- `Cmd+Q`/window close on macOS keeps Core and Helper alive; the explicit `Quit Glance` action calls `POST /shutdown` and then exits the UI.
- Electron Forge packaging now recognizes Electron as a build-time dependency.

Verification:

- `npm --workspace @glance/ui run test`
- `npm --workspace @glance/ui run typecheck`
- `PYTHONPATH=core/src .venv/bin/python -m unittest discover core/tests`
- `npm --workspace @glance/ui run package`

Remaining lifecycle gaps before calibration:

- Runtime ownership is still dev-mode oriented; packaged Python Core discovery/startup will need a production bundle path.
- Core writes runtime files and launches Helper, but `core.lock` is not yet used as an actual interprocess lock.
- `/ui/events` is opened by Electron main, but renderer updates are still refresh/request driven rather than pushed from the WebSocket stream.
