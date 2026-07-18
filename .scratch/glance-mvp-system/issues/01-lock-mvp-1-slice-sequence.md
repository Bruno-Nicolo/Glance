# Lock MVP 1 Vertical Slice Sequence

Status: resolved
Type: grilling
Blocked by:

## Question

Given ADR 0001 is fixed, what exact vertical-slice sequence should drive implementation of MVP 1, and what acceptance checkpoint proves each slice is complete before moving to the next?

Resolve this as an ordered route, not as component-by-component implementation. The answer should say which slice comes first, what observable behavior it proves, and which later tickets it unblocks.

## Decision

MVP 1 implementation should proceed as a vertical runtime route, proving one observable behavior at a time. The route includes contract/research gates only where they unblock the next vertical slice; those gates are not implementation slices by themselves.

The implementation slices are:

1. Synthetic gaze moves the Helper overlay cursor.
2. UI discovers/starts Core, shows status, and drives lifecycle/shutdown.
3. UI drives calibration against Core and persists calibration data using synthetic/manual samples.
4. Real webcam gaze replaces synthetic samples and drives the calibrated overlay cursor.
5. Helper performs Space click and Esc pause against the calibrated cursor.
6. Final MVP 1 acceptance verifies the whole system end to end.

The full route through existing tickets is:

1. Define the Core to Helper event contract.
2. Build synthetic Core to Helper gaze and overlay movement.
3. Define the Core to UI API contract.
4. Build UI discovery, status, lifecycle, and full shutdown.
5. Define calibration flow and persisted data.
6. Build synthetic/manual calibration through UI and Core.
7. Research the real gaze framework and macOS packaging constraints.
8. Define mapping, smoothing, confidence, and invalid-sample behavior.
9. Build real webcam gaze through calibration mapping to the overlay.
10. Define Helper Space click and Esc pause behavior.
11. Build Helper Space click and Esc pause against calibrated cursor output.
12. Finalize the MVP 1 acceptance checklist and test plan.

This sequence keeps the first runnable slice focused on the runtime-critical path: Python Core emits authenticated gaze events, Swift Helper consumes them, and the overlay visibly moves. Electron is added after that runtime path is proven, calibration is added after both Core/Helper and Core/UI contracts exist, and real camera work waits until the calibration and gaze framework decisions are resolved.

## Acceptance Checkpoints

| Step | Kind  | Ticket | Acceptance checkpoint                                                                                                                                                                                                                                                                                             | Unblocks         |
| ---- | ----- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| 1    | Gate  | 02     | The Core-to-Helper WebSocket event contract specifies auth, event names, schema versioning, screen-coordinate payloads, timestamps, confidence/status semantics, timing expectations, invalid-event behavior, and compatibility rules for both synthetic and real gaze events.                                    | 03, 06, 11       |
| 2    | Slice | 03     | Running the cheapest local slice starts Core and Helper, authenticates the Helper WebSocket, streams synthetic screen-coordinate gaze events, decodes them in Helper, and visibly moves the overlay cursor on the single active macOS display. The slice records lifecycle behavior and any contract corrections. | 06, 11           |
| 3    | Gate  | 04     | The Core-to-UI API contract specifies runtime discovery, `/health`, status, settings, calibration endpoints/events, error states, WebSocket auth, and full-shutdown semantics without making Electron part of the cursor runtime path.                                                                            | 05, 06           |
| 4    | Slice | 05     | Electron can discover or start Python Core, display live MVP 1 status, survive UI close while Core and Helper continue, and request full shutdown through Core. Runtime files use the ADR paths and security permissions.                                                                                         | 06, 13           |
| 5    | Gate  | 06     | The calibration flow defines the 9-point initial run, 3-5 point validation, quick 1-point drift correction, persisted `calibration.json` shape, Core API sequence, retry/failure states, and explicit privacy exclusions.                                                                                         | 07, 09           |
| 6    | Slice | 07     | The UI can drive a full calibration session against Core using synthetic or manually supplied samples, Core persists valid calibration data, validation results are visible, and no camera frames/videos/gaze traces/input history are saved by default.                                                          | 10               |
| 7    | Gate  | 08     | The real gaze research records the chosen ready-made MediaPipe/OpenCV approach, install/runtime constraints, camera permission implications, expected 30 FPS viability, packaging risks, and fallback plan.                                                                                                       | 09               |
| 8    | Gate  | 09     | The mapping contract specifies the minimal regression/correction implementation, smoothing defaults, confidence fields, invalid-sample behavior, debug/status outputs, and how calibrated screen coordinates feed the existing Helper gaze event contract.                                                        | 10               |
| 9    | Slice | 10     | Python Core can replace synthetic gaze with webcam/MediaPipe/OpenCV samples, apply persisted calibration mapping, emit authenticated gaze events at the target rate, and move the Swift overlay cursor with measured behavior and recorded caveats.                                                               | 12, 13           |
| 10   | Gate  | 11     | The Helper input contract specifies Space key down/up click semantics, click position, Esc pause semantics, overlay visibility while paused, Core notification/status behavior, permission failure behavior, and debug fields.                                                                                    | 12               |
| 11   | Slice | 12     | Swift Helper performs a real left click via Space at the current calibrated overlay cursor position and pauses/resumes tracking via Esc while respecting lifecycle and macOS permission constraints. MVP 2-only inputs remain explicitly out of scope.                                                            | 13               |
| 12   | Slice | 13     | The final checklist verifies Python Core, Swift Helper, Electron UI, persistence, privacy defaults, runtime security, lifecycle, calibration, real gaze cursor movement, Space click, and Esc pause end to end, with remaining gaps labeled outside MVP 1.                                                        | MVP 1 completion |

## Guardrails

- Do not start by building all Core, Helper, or UI infrastructure in isolation; each implementation ticket must prove a user-observable vertical behavior.
- Do not connect real webcam gaze before synthetic cursor movement, UI lifecycle, and calibration persistence have working acceptance evidence.
- Do not implement MVP 2 input behavior while completing MVP 1 Space and Esc; double click, drag, Option scroll mode, Accessibility snap, and LaunchAgent start at login remain out of scope.
- Treat each `grilling` ticket as a contract gate. The next implementation ticket should not begin until its blocking contract ticket has a resolved answer.
