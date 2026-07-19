# Glance

Glance is an experimental macOS gaze-to-cursor system. It uses the built-in webcam to estimate gaze,
maps calibrated gaze samples into screen coordinates, and drives a native overlay cursor with a
small keyboard input scheme.

## Codebase Structure

```text
apps/ui/                  Electron Forge + React UI
  src/main/               Electron main process and Core lifecycle/discovery
  src/preload/            Safe renderer bridge
  src/renderer/           React UI
  src/shared/             Shared TypeScript contracts and calibration helpers

core/                     Python Core package
  src/glance_core/        FastAPI server, runtime security, calibration, gaze mapping, camera path
  tests/                  Python contract and runtime-boundary tests

native/macos-helper/      Swift Package for the native macOS Helper
  Sources/GlanceHelper/   AppKit overlay, WebSocket client, Space click, Esc pause

docs/                     ADRs, API contracts, behavior contracts, acceptance plan
.scratch/glance-mvp-system/
                           Planning tickets and implementation reports
```

Runtime and persisted app data live under:

```text
~/Library/Application Support/Glance/
  config.json
  calibration.json
  logs/
  runtime/
    core.pid
    core.lock
    core.port
    core.token
```

The runtime directory is private (`0700`), and Core requires `Authorization: Bearer <token>` for
HTTP and WebSocket clients.

## Prerequisites

- macOS with Xcode command line tools or Xcode installed.
- Node.js and npm.
- Python 3.11 or newer.
- SwiftPM, available through the Xcode toolchain.
- For real camera gaze: OpenCV, MediaPipe, NumPy, scikit-learn, and a local MediaPipe Face
  Landmarker model.

## Setup

Install JavaScript dependencies:

```bash
npm install
```

Create and install the Python Core environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e core
```

Install optional vision dependencies when exercising the real webcam path:

```bash
.venv/bin/python -m pip install -e 'core[vision]'
```

Place the Face Landmarker model at the default path:

```text
~/Library/Application Support/Glance/models/face_landmarker.task
```

or point Core at it explicitly:

```bash
export GLANCE_FACE_LANDMARKER_MODEL_PATH=/absolute/path/to/face_landmarker.task
```

## Running

Start the Electron UI:

```bash
npm run dev:ui
```

The UI discovers an existing Core through `runtime/core.port` and `runtime/core.token`; if no
healthy Core is running, it starts one. Core then launches the Swift Helper.

For component-level development, run the processes directly:

```bash
npm run dev:core
npm run dev:helper
```

Useful environment variables:

- `GLANCE_CORE_PORT`: force Core to bind a specific localhost port.
- `GLANCE_DISABLE_HELPER=1`: run Core without launching the Swift Helper.
- `GLANCE_HELPER_COMMAND`: override the Helper command Core launches.
- `GLANCE_FACE_LANDMARKER_MODEL_PATH`: set the real-camera MediaPipe model path.

By default, Glance uses real camera tracking. Synthetic gaze remains available as an optional
debugging mode through the UI settings or Core settings API by setting
`debug.synthetic_gaze_enabled` to `true`.

## Testing

Run the Core test suite:

```bash
.venv/bin/python -m unittest discover core/tests
```

Run UI typechecking and tests:

```bash
npm --workspace @glance/ui run typecheck
npm --workspace @glance/ui test
```

Build the Swift Helper:

```bash
swift build --package-path native/macos-helper
```

The Core API tests bind localhost sockets. The Swift build writes normal SwiftPM/clang cache files.
In a restricted sandbox, those commands may need permission to access those resources.
