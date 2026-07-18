# Define Gaze Mapping and Confidence Contract

Status: closed
Type: grilling
Blocked by: 06, 08

## Question

What concrete mapping, smoothing, and confidence contract should Python Core expose for MVP 1 after MediaPipe/OpenCV samples are available?

ADR 0001 defines the intended feature pipeline. Resolve the minimal regression/correction implementation, confidence fields, smoothing defaults, invalid-sample behavior, and debug/status outputs needed for a usable single-monitor MVP.

## Resolution

Defined in [Gaze Mapping and Confidence Contract](../../../docs/gaze-mapping-and-confidence-contract.md)
and mirrored by `core/src/glance_core/gaze_mapping_contract.py`.
