# Glance MVP 1 Wayfinder Map

Label: wayfinder:map

## Destination

Implement MVP 1 end-to-end as described in [ADR 0001: Glance MVP Architecture](../../docs/adr/0001-glance-mvp-architecture.md): a macOS-only gaze-to-overlay-cursor system with Python Core, Swift Helper, and Electron UI connected through authenticated local runtime discovery. MVP 1 validates calibrated gaze driving the overlay cursor, Space click, Esc pause, basic settings/status, calibration UI, and full shutdown.

## Notes

ADR 0001 is the fixed architectural source of truth. Do not re-decide the three-component architecture, runtime ownership, security model, lifecycle boundaries, MVP 1/MVP 2 split, single-monitor scope, or privacy defaults unless a ticket discovers a contradiction that must be escalated.

This map intentionally carries implementation through vertical-slice `task` and `prototype` tickets after the necessary decisions are clear. Prefer vertical slices over component silos:

1. Core sends synthetic screen-coordinate gaze events to Helper.
2. Helper renders and moves the overlay cursor from those events.
3. UI connects to Core, shows status, and drives lifecycle.
4. Calibration flow creates persisted calibration data for later mapping.
5. Real webcam/MediaPipe gaze replaces synthetic events.
6. Space click and Esc pause are completed in Helper.

## Decisions so far

- MVP 1 follows the vertical sequence and acceptance checkpoints resolved in [01-lock-mvp-1-slice-sequence.md](issues/01-lock-mvp-1-slice-sequence.md).
- Each implementation slice must pass its observable acceptance checkpoint before later slices begin; contract tickets are gates for the implementation tickets that depend on them.

## Not yet specified

- The exact UI shape for calibration and status/debug views may need a prototype after the API contracts are known.
- The precise MediaPipe/OpenCV model/framework choice and macOS packaging constraints need research before the real-camera slice.
- The calibration math details beyond the ADR pipeline may need sharper decisions once synthetic cursor movement and API contracts exist.
- The confidence thresholds, smoothing defaults, and pause recovery defaults may need tuning from a working real-camera slice.
- The MVP 1 test strategy across Python Core, Swift Helper, and Electron UI may need a separate plan after the first vertical slice proves the runtime contract.

## Out of scope

- MVP 2 features from ADR 0001: Accessibility target cache, soft magnetism, hysteresis, double click, drag, Option scroll mode, and LaunchAgent start at login.
- Multi-monitor support.
- Training a custom gaze model.
- Saving camera frames, videos, continuous gaze traces, Accessibility targets, or input history by default.
