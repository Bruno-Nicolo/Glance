# MVP 1 Acceptance and Test Plan

Status: MVP 1 acceptance gate.

This plan defines the evidence required to accept MVP 1 from
[ADR 0001: Glance MVP Architecture](adr/0001-glance-mvp-architecture.md). MVP 1 is accepted only
when the automated gates pass and the manual macOS hardware pass proves the runtime behavior on a
target Mac.

The verification details below also use the checked-in MVP 1 contracts for Core/UI, Core/Helper,
calibration, gaze mapping, and Helper input behavior. Those contracts refine ADR 0001 without
changing its architecture or MVP 1/MVP 2 boundary.

## Acceptance Checklist

| Area | Acceptance requirement | Verification |
| --- | --- | --- |
| Python Core runtime | Core starts as the orchestrator, exposes FastAPI HTTP/WebSocket endpoints, writes runtime files under `~/Library/Application Support/Glance/runtime/`, launches Swift Helper, and remains alive when Electron closes. | Automated Core/UI lifecycle tests plus manual launch/close pass. |
| Runtime security | `core.pid`, `core.lock`, `core.port`, and `core.token` are managed under the ADR runtime path; `core.port` and `core.token` are used for localhost discovery; HTTP and WebSocket calls without `Authorization: Bearer <token>` are rejected; runtime directory is `0700` and token file is `0600`. | Automated Core API/security tests plus manual permission check on runtime files. |
| Core-to-Helper stream | Core sends authenticated `/events` messages using the MVP 1 event contract: `core.ready`, `gaze.sample`, and `tracking.status`; valid gaze samples target 30 FPS and use `display-logical-top-left` coordinates. | Automated contract tests; manual synthetic and camera stream observation. |
| Swift Helper overlay | Helper connects to Core, renders a custom overlay cursor, moves it from newest valid non-stale gaze samples, freezes or hides on tracking status, and ignores invalid samples. | Swift build plus manual overlay movement pass. |
| Electron UI | UI discovers or starts Core, authenticates through runtime files, displays Core/Helper/Camera/Tracking/Input/Calibration status, exposes settings/start/stop controls, and calls Core for `Quit Glance`. | UI typecheck/tests plus manual Electron pass. |
| Lifecycle | Manual launch follows Electron -> Core -> Helper; closing Electron or pressing `Cmd+Q` closes only the UI; `Quit Glance` requests full runtime shutdown through `POST /shutdown` and stops Helper/Core. | Automated UI lifecycle tests plus manual process observation. |
| Settings persistence | Core owns `config.json`; Electron reads/writes settings only through the Core API; unknown settings are rejected; persisted settings affect synthetic/camera tracking, smoothing, confidence threshold, Space click, and pause behavior. | Automated Core API tests plus manual settings change pass. |
| Calibration | UI drives initial 9-point calibration, validation, cancellation, and 1-point drift correction through Core sessions; Core persists one accepted `calibration.json` profile containing model/correction/validation data. | Automated Core calibration tests and UI synthetic calibration pass; manual real-camera calibration pass. |
| Gaze mapping | Camera samples use the contracted feature and quality fields, map through persisted ridge regression, IDW 3x3 correction grid, smoothing, confidence classification, and emit Helper `gaze.sample` events. | Automated mapper/camera boundary tests plus manual camera stream pass. |
| Real camera | With the default `debug.synthetic_gaze_enabled: false`, installed vision dependencies, and the pinned Face Landmarker model, Core uses the built-in webcam through OpenCV/MediaPipe and records privacy-preserving camera metrics. | Automated fake-camera tests plus mandatory manual hardware pass. |
| Cursor movement | After accepted calibration, real camera gaze visibly drives the Helper overlay cursor on the main display at an observed rate near the 30 FPS target, with low-confidence or invalid samples not moving the cursor. | Mandatory manual hardware pass using `/status.camera.metrics` and visible overlay behavior. |
| Space click | Space tap posts one real left click at the latest overlay cursor point when tracking input is enabled, not paused, a cursor exists, and Accessibility permission is available; suppressed clicks are reported only as latest debug status. | Swift build and Core telemetry tests plus mandatory manual permissioned click pass. |
| Esc pause | Esc is hold-to-pause; repeat key-down is ignored; release resumes the previous tracking state; fast recovery hides or freezes the overlay while keeping tracking warm, and privacy/low-power hides the overlay and releases camera work. | Core telemetry tests plus mandatory manual permissioned pause pass. |
| Privacy defaults | Core persists only `config.json`, `calibration.json`, and minimal technical logs by default. It does not persist camera frames, videos, raw landmarks, raw calibration sample batches, continuous gaze traces, observed Accessibility targets, raw key events, input history, or click history. | Automated schema/status tests plus manual inspection of app support files and logs after an end-to-end pass. |
| Single-monitor scope | All accepted behavior is on the main display using `display-logical-top-left` coordinates. | Manual pass on a single-display configuration. |

## Automated Gate

Run these commands from the repo root before the manual pass:

```bash
.venv/bin/python -m unittest discover core/tests
npm --workspace @glance/ui run typecheck
npm --workspace @glance/ui test
swift build --package-path native/macos-helper
```

The Python API tests bind localhost sockets. The Swift build may write to SwiftPM caches outside the
repo. In restricted automation, run those commands with the required sandbox permissions rather than
weakening the tests.

The automated gate is complete when it verifies:

- Core/UI API authentication, settings validation, status shape, shutdown shape, and UI event auth.
- Core/Helper event payloads, versioning, display coordinates, synthetic path cadence, and invalid
  sample behavior.
- Calibration session state, target order, sample validation, profile persistence, validation
  thresholds, drift correction, and privacy boundaries.
- Gaze mapping, smoothing, confidence classification, invalid-sample freeze behavior, and status
  debug shape.
- Camera runtime boundary with a fake provider, including mapped camera `gaze.sample` events and
  aggregate camera metrics.
- Electron runtime discovery, stale marker cleanup, Core startup wait, macOS close behavior, and
  renderer/shared TypeScript contracts.
- Swift Helper compilation against the Core event and input behavior implementation.

## Manual Hardware Gate

Run this pass on a target macOS machine with the built-in webcam, the MediaPipe Face Landmarker
model installed at `~/Library/Application Support/Glance/models/face_landmarker.task` or supplied
through `GLANCE_FACE_LANDMARKER_MODEL_PATH`, and the needed macOS permissions available.

1. Start Electron and confirm it connects to an existing healthy Core or starts a new Core.
2. Confirm `~/Library/Application Support/Glance/runtime/` contains `core.pid`, `core.lock`,
   `core.port`, and `core.token`; verify directory/file permissions match the ADR security
   requirements.
3. Confirm the status screen reports `ui.runtime_critical: false` and shows Core, Helper, Camera,
   Tracking, Input, and Calibration state.
4. Close the Electron window or press `Cmd+Q`; confirm Core and Helper continue running.
5. Reopen Electron and confirm it reconnects to the existing Core through the runtime files.
6. Run the 9-point calibration and validation flow; confirm an accepted `calibration.json` profile
   is written and raw samples/images are not persisted.
7. Confirm synthetic gaze is disabled, start tracking, and grant camera permission if prompted.
8. Confirm `/status.camera.metrics` reports captured, inference, emitted, invalid, dropped, and FPS
   counters without exposing frames, landmarks, feature vectors, or gaze traces.
9. Look at several screen regions and confirm the overlay cursor follows calibrated gaze on the
   main display with no Accessibility snap.
10. Record captured, inference, and emitted FPS from `/status.camera.metrics`; acceptance requires
    observed emitted FPS within 10% of the 30 FPS target for a 60-second tracking run, with no
    sustained stale cursor behavior.
11. Press Space over a harmless clickable target and confirm exactly one left click is posted at the
    overlay cursor position.
12. Temporarily deny or remove Input Monitoring permission, then confirm global Space/Esc capture is
    disabled, Helper reports a recoverable `input-monitoring` permission state, and granting the
    permission allows the behavior to recover.
13. Temporarily deny or remove Accessibility permission, then confirm Space click is suppressed with
    recoverable permission status while overlay rendering can continue.
14. Disable Space click in settings and confirm Space no longer clicks while Esc pause remains
    available.
15. Hold Esc in fast recovery mode and confirm tracking pauses, input is suppressed, tracking stays
    warm, and the overlay either hides or freezes according to the Helper contract until Esc is
    released.
16. Switch to privacy/low-power pause, hold Esc, and confirm tracking pauses, input is suppressed,
    the overlay hides, and camera work stops or suspends until Esc is released.
17. Use `Quit Glance` from the UI and confirm Core stops Helper and exits, while a plain UI close
    did not perform full runtime shutdown.
18. Inspect `~/Library/Application Support/Glance/` after the pass and confirm only allowed
    persistence exists by default: `config.json`, `calibration.json`, `logs/`, and `runtime/`.

## Acceptance Decision

MVP 1 can be marked accepted when:

- Every automated gate command passes.
- Every manual hardware gate step passes on a target Mac.
- Any measured real-camera FPS, permission, or calibration failures are recorded with exact device,
  macOS version, model path, and status metrics.
- Any remaining issue is either fixed before acceptance or explicitly classified below as outside
  MVP 1.

## Explicitly Out Of MVP 1

These are not acceptance blockers for MVP 1:

- Accessibility target cache.
- Soft magnetism, hysteresis, and snap-to-target behavior.
- Space double tap.
- Space hold drag.
- Option scroll mode.
- Multi-monitor support.
- Start-at-login LaunchAgent behavior.
- Training a custom gaze model.
- User-facing capture/export features for camera frames, videos, continuous gaze traces, observed
  Accessibility targets, input history, or click history. The default prohibition on saving those
  artifacts remains an MVP 1 acceptance requirement.
- Packaged production installer/update flow for the Face Landmarker model, beyond documenting the
  required model path for the manual pass.
