# ADR 0001: Glance MVP Architecture

## Status

Accepted for MVP planning.

## Context

Glance is a macOS-only eye-tracking interaction system that uses the built-in webcam. The user wants a UX similar to a mouse or iPad pointer: gaze moves a custom cursor, nearby interactive targets can eventually attract the cursor, and a small set of keyboard inputs confirms actions.

The system must avoid putting Electron in the runtime-critical path. The UI should be optional and closable while the core process continues to run.

## Decisions

Glance will use three separate components:

```text
Electron + React UI
  - settings
  - calibration UI
  - status/debug dashboard
  - start/stop/quit controls
  - not in critical runtime path

Python Core
  - central orchestrator
  - FastAPI + Uvicorn HTTP/WebSocket API
  - webcam and MediaPipe/OpenCV
  - gaze estimation
  - calibration/mapping/smoothing/confidence
  - settings and calibration persistence
  - launches Swift Helper

Swift macOS Helper
  - AppKit run loop
  - custom overlay cursor
  - CoreGraphics mouse/click/drag/scroll/input events
  - global key handling
  - macOS permission checks
  - Accessibility cache and snap/magnetism in a later milestone
```

Python Core is the orchestrator. Electron and Swift Helper connect to it.

## Runtime Security And Discovery

Runtime files live under:

```text
~/Library/Application Support/Glance/runtime/
  core.pid
  core.lock
  core.port
  core.token
```

The runtime directory should use `0700`; the token file should use `0600`.

The core uses a dynamic local port and requires `Authorization: Bearer <token>` for HTTP and WebSocket requests.

Electron startup flow:

```text
1. Read core.port and core.token if present.
2. Try GET /health with Authorization.
3. If healthy, connect to existing core.
4. If not healthy, inspect/clean stale lock/PID if needed.
5. Start Python Core.
6. Wait for /health.
7. Open WebSocket.
```

Swift Helper is launched by Python Core and receives connection details through controlled process startup data, initially environment variables.

## Lifecycle

Manual launch:

```text
Electron starts
-> Electron starts Python Core if not already running
-> Python Core starts Swift Helper
```

Start at login:

```text
LaunchAgent starts Python Core
-> Python Core starts Swift Helper
-> Electron UI remains closed
```

`Cmd+Q` in Electron closes only the UI. Python Core and Swift Helper continue to run. The UI must expose a separate `Quit Glance` action that requests full shutdown through Python Core.

## Input Scheme

Target input model:

```text
Space
  tap = left click
  double tap = double click
  hold = drag

Option
  hold = scroll mode
  anchor = overlay cursor position when Option is pressed
  gaze above/below anchor = vertical scroll
  gaze left/right anchor = horizontal scroll
  dominant axis wins
  distance from anchor = scroll speed
  release = stop scroll

Esc
  hold = pause tracking
```

Drag includes a short stabilization phase before `mouse down`.

Pause behavior is configurable:

```text
Fast recovery
  - hide/freeze overlay
  - disable input
  - keep camera/tracking warm

Privacy / low power
  - hide overlay
  - disable input
  - stop camera/tracking
  - slower resume
```

## Gaze Estimation

Use MediaPipe/OpenCV with a ready-made model/framework. Do not train a custom model for the MVP.

MVP supports one monitor only.

Calibration:

```text
initial calibration: 9 points
validation: 3-5 random targets
drift correction: quick 1-point recalibration
```

Mapping pipeline:

```text
MediaPipe landmarks
-> feature extraction
-> regularized regression feature -> screen coordinate
-> local grid correction/interpolation from 3x3 calibration grid
-> smoothing
-> confidence
-> output x/y
```

Regression features:

- left iris relative x/y
- right iris relative x/y
- average iris relative x/y
- face center x/y
- face scale
- head yaw
- head pitch
- head roll

Confidence features:

- eye openness
- landmark stability
- face detection stability
- divergence between left/right eye estimates
- temporal jitter

## Privacy

Glance is local-first. By default it saves only:

- `config.json`
- `calibration.json`
- minimal technical logs

It must not save by default:

- camera frames
- videos
- continuous gaze traces
- observed Accessibility targets
- input history

## Persistence

Python Core owns persistence under:

```text
~/Library/Application Support/Glance/
  config.json
  calibration.json
  logs/
  runtime/
```

Electron reads and writes settings only through the Python Core API.

## MVP 1 Scope

MVP 1 validates gaze-to-overlay-cursor without Accessibility snap.

```text
Python Core
  - FastAPI + WebSocket authenticated with token
  - health/status/settings JSON
  - webcam + MediaPipe
  - 9-point calibration
  - regularized regression + correction grid
  - gaze events at target 30 FPS

Swift Helper
  - authenticated WebSocket connection
  - custom overlay cursor
  - real click via Space
  - pause via Esc
  - no AX snap yet

Electron UI
  - start/connect to Core
  - status screen
  - 9-point calibration UI
  - basic settings
  - Quit Glance action
```

## MVP 2 Scope

```text
- Accessibility target cache
- soft magnetism + hysteresis
- double click
- drag
- Option scroll mode
- LaunchAgent start at login
```

## Future Smart Cursor Direction

Snap/magnetism will live in Swift Helper because it owns AX target data and overlay rendering. The intended approach is soft magnetism plus hysteresis using a conservative Accessibility target whitelist.

Initial target roles:

```text
AXButton
AXCheckBox
AXRadioButton
AXPopUpButton
AXMenuItem
AXTextField
AXTextArea
AXLink
AXTab
AXSlider
AXIncrementor
AXDecrementor
```

Click strategy starts with real mouse events only. `AXPress` is a possible future enhancement, not part of MVP 1.
