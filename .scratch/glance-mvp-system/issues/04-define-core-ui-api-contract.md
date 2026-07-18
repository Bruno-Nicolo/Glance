# Define Core to UI API Contract

Status: complete
Type: grilling
Blocked by: 01

## Question

What is the MVP 1 HTTP/WebSocket API contract between Electron UI and Python Core?

ADR 0001 already assigns settings, calibration UI, status/debug dashboard, start/stop/quit controls, and non-critical runtime status to Electron. Resolve the concrete endpoints/events, settings shape, status shape, error states, and shutdown semantics the UI needs without putting Electron in the runtime-critical path.

## Resolution

Core/UI contract version 1 is defined in [docs/core-ui-api-contract.md](../../../docs/core-ui-api-contract.md).

Executable coverage lives in `core/tests/test_core_ui_api_contract.py` and verifies:

- authenticated `/health`, `/status`, `/settings`, `/controls/start`, `/controls/stop`, and `/shutdown`
- Core-owned settings persistence
- structured recoverable errors
- explicit full-runtime shutdown response semantics
- `/ui/events` ready/status WebSocket handshake

Electron now connects to `/ui/events`; Swift Helper gaze events remain on `/events`.
