# Finalize MVP 1 Acceptance and Test Plan

Status: resolved
Type: grilling
Blocked by: 05, 10, 12

## Question

What final acceptance checklist and automated/manual test plan proves MVP 1 is implemented end-to-end according to ADR 0001?

Resolve the verification matrix across Python Core, Swift Helper, Electron UI, persistence, privacy defaults, runtime security, lifecycle, calibration, cursor movement, Space click, and Esc pause. The answer should identify any remaining gaps that are explicitly out of MVP 1.

## Result

The final MVP 1 acceptance checklist and automated/manual test plan is defined in
[MVP 1 Acceptance and Test Plan](../../../docs/mvp-1-acceptance-and-test-plan.md).

MVP 1 acceptance requires both the repo automated gate and a manual macOS hardware pass because
real webcam FPS, macOS camera/Input Monitoring/Accessibility permission behavior, visible cursor
movement, Space click posting, and Esc pause are not fully provable in headless automation.

The plan also records the remaining non-blocking exclusions from ADR 0001: Accessibility target
cache, soft magnetism/hysteresis/snap, Space double tap, Space hold drag, Option scroll mode,
multi-monitor support, LaunchAgent start at login, custom model training, user-facing capture/export
features for privacy-sensitive artifacts, and packaged model distribution beyond the documented
manual-pass model path. The default prohibition on saving camera frames, videos, continuous gaze
traces, observed Accessibility targets, input history, and click history remains an MVP 1 acceptance
requirement.
