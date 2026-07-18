# Define Calibration Flow and Data Model

Status: resolved
Type: grilling
Blocked by: 02, 04

## Question

What exact calibration flow, persisted data model, and Core API should MVP 1 use for 9-point calibration, 3-5 point validation, and quick 1-point drift correction?

ADR 0001 fixes the calibration scope and that Python Core owns persistence. Resolve the UI/Core interaction sequence, JSON schema, validation outputs, retry/failure states, and what data is explicitly not persisted for privacy.

## Resolution

MVP 1 calibration flow and persistence are defined in
[docs/calibration-flow-and-data-model.md](../../../docs/calibration-flow-and-data-model.md).

The Core/UI API contract now points calibration sample handling to that document and includes the
full ADR feature vector, including average iris features.

Executable coverage lives in `core/tests/test_calibration_contract.py` and verifies:

- the fixed 9-point target order and display ratios
- the persisted `calibration.json` profile schema
- JSON-native feature names
- explicit absence of raw samples, frames, or video fields from the persisted profile

Shared UI types for calibration session, sample, and completion payloads live in
`apps/ui/src/shared/core-contract.ts`.
