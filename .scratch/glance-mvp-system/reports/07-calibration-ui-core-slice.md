# Calibration UI Core Slice Report

Status: implemented

## Usability

The Electron UI can run a complete MVP 1 calibration prototype without the real camera:

- `Calibrate` starts an initial 9-point session, submits synthetic feature batches for every target,
  completes the initial fit, then runs a 5-point validation session.
- Core returns validation metrics and persists the accepted profile.
- The calibration panel shows current target position, target progress, profile id, and mean error.
- `Drift` is enabled only after Core reports a valid profile and applies a 1-point center drift
  correction to the existing profile.
- `Cancel` cancels the active Core session and restores status.

## Files Written

Python Core writes:

- `calibration.json` next to Core's `config.json` path.

For the default app runtime this is:

- `~/Library/Application Support/Glance/calibration.json`

In tests, the file is written beside the temporary `config.json`. The persisted profile contains
the fitted regression, correction grid, display metadata, validation metrics, and drift count. It
does not persist raw samples, camera frames, video, landmarks, or gaze traces.

## Before MediaPipe Samples

- Replace UI synthetic batches with real camera-derived `CalibrationSample` batches using the exact
  feature and quality field names from `docs/calibration-flow-and-data-model.md`.
- Keep target dwell timing around 700 ms and discard the first movement-settle window before sending
  real samples.
- Tune validation thresholds only if real-camera measurements show the MVP defaults are unusable,
  and update the contract/tests when doing so.
- Add target-level retry UX for low-quality or rejected batches once real quality failures are
  possible.
- Connect camera lifecycle/status to calibration so Core can report camera failures distinctly from
  calibration failures.
