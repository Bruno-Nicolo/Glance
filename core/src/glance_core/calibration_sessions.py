from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from .calibration_contract import (
    CALIBRATION_CONTRACT_VERSION,
    CALIBRATION_FEATURE_NAMES,
    CALIBRATION_TARGETS_9_POINT,
    VALIDATION_MAX_ERROR_THRESHOLD_PX,
    VALIDATION_MEAN_ERROR_THRESHOLD_PX,
    CalibrationDisplay,
    CalibrationMode,
    CalibrationProfile,
    CorrectionNode,
    RegressionModel,
    ValidationMetrics,
)
from .helper_events import DisplayBounds, now_ms


class CalibrationSessionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CalibrationSessionStore:
    def __init__(self, profile_path: Path):
        self.profile_path = profile_path
        self.active: CalibrationSessionRecord | None = None
        self.pending_initial: CalibrationSessionRecord | None = None
        self.profile = load_calibration_profile(profile_path)

    @property
    def profile_id(self) -> str | None:
        return self.profile.profile_id if self.profile else None

    @property
    def state(self) -> str:
        if self.active is not None:
            return "in-progress"
        if self.profile is not None:
            return "valid"
        return "missing"

    def create(self, mode: CalibrationMode, display: CalibrationDisplay) -> "CalibrationSessionRecord":
        if self.active is not None and self.active.state in {"collecting", "processing"}:
            raise CalibrationSessionError("calibration_busy", "Another calibration session is active")
        if mode == "validation" and self.pending_initial is None:
            raise CalibrationSessionError("calibration_failed", "Validation requires a completed initial calibration")
        if mode == "drift-1-point" and self.profile is None:
            raise CalibrationSessionError("calibration_failed", "Drift correction requires a valid calibration profile")

        self.active = CalibrationSessionRecord(
            session_id=f"cal_{uuid4().hex[:12]}",
            mode=mode,
            display=display,
            targets=calibration_targets_for_mode(mode, display),
        )
        return self.active

    def add_samples(self, session_id: str, payload: Any) -> "CalibrationSessionRecord":
        session = self.require_active(session_id)
        validate_calibration_samples_payload(session, payload)
        target = session.targets[session.current_target_index]
        target.samples.extend(payload["samples"])
        session.sample_count += len(payload["samples"])
        session.current_target_index = min(session.current_target_index + 1, len(session.targets))
        return session

    def complete(self, session_id: str) -> tuple["CalibrationSessionRecord", CalibrationProfile | None, ValidationMetrics | None]:
        session = self.require_active(session_id)
        if session.current_target_index < len(session.targets) or session.sample_count < len(session.targets):
            raise CalibrationSessionError("calibration_failed", "Calibration needs samples for every target")

        session.state = "complete"
        if session.mode == "initial-9-point":
            self.pending_initial = session
            self.active = None
            return session, None, None

        if session.mode == "validation":
            if self.pending_initial is None:
                raise CalibrationSessionError("calibration_failed", "Validation requires a completed initial calibration")
            profile = fit_profile(self.pending_initial, validation_session=session)
            self.pending_initial = None
        else:
            if self.profile is None:
                raise CalibrationSessionError("calibration_failed", "Drift correction requires a valid calibration profile")
            profile = apply_drift_correction(self.profile, session)

        self.profile = profile
        save_calibration_profile(self.profile_path, profile)
        self.active = None
        return session, profile, profile.validation

    def cancel(self, session_id: str) -> "CalibrationSessionRecord":
        session = self.require_active(session_id)
        session.state = "cancelled"
        self.active = None
        return session

    def require_active(self, session_id: str) -> "CalibrationSessionRecord":
        if self.active is None or self.active.session_id != session_id:
            raise CalibrationSessionError("invalid_calibration_session", "Unknown calibration session")
        if self.active.state != "collecting":
            raise CalibrationSessionError("invalid_calibration_sample", "Calibration session is not collecting")
        return self.active


class CalibrationSessionRecord:
    def __init__(
        self,
        *,
        session_id: str,
        mode: CalibrationMode,
        display: CalibrationDisplay,
        targets: list["SessionTarget"],
    ):
        self.session_id = session_id
        self.mode = mode
        self.display = display
        self.targets = targets
        self.current_target_index = 0
        self.state = "collecting"
        self.sample_count = 0


class SessionTarget:
    def __init__(self, *, target_id: str, x_ratio: float, y_ratio: float, display: CalibrationDisplay):
        self.id = target_id
        self.x_ratio = x_ratio
        self.y_ratio = y_ratio
        self.x = display.x + (display.width * x_ratio)
        self.y = display.y + (display.height * y_ratio)
        self.display = display
        self.samples: list[dict[str, Any]] = []


def calibration_display_from_bounds(bounds: DisplayBounds) -> CalibrationDisplay:
    return CalibrationDisplay(
        id=bounds.id,
        x=bounds.x,
        y=bounds.y,
        width=bounds.width,
        height=bounds.height,
        scale=bounds.scale,
    )


def calibration_targets_for_mode(
    mode: CalibrationMode,
    display: CalibrationDisplay,
) -> list[SessionTarget]:
    targets = CALIBRATION_TARGETS_9_POINT
    if mode == "validation":
        targets = (
            CALIBRATION_TARGETS_9_POINT[1],
            CALIBRATION_TARGETS_9_POINT[3],
            CALIBRATION_TARGETS_9_POINT[0],
            CALIBRATION_TARGETS_9_POINT[6],
            CALIBRATION_TARGETS_9_POINT[8],
        )
    elif mode == "drift-1-point":
        targets = (CALIBRATION_TARGETS_9_POINT[0],)

    return [
        SessionTarget(
            target_id=target.id,
            x_ratio=target.x_ratio,
            y_ratio=target.y_ratio,
            display=display,
        )
        for target in targets
    ]


def calibration_session_response(session: CalibrationSessionRecord) -> dict[str, Any]:
    return {
        "contract_version": CALIBRATION_CONTRACT_VERSION,
        "session_id": session.session_id,
        "mode": session.mode,
        "state": session.state,
        "current_target_index": session.current_target_index,
        "targets": [target_to_response(target) for target in session.targets],
        "error": None,
    }


def target_to_response(target: SessionTarget) -> dict[str, Any]:
    return {
        "id": target.id,
        "x": target.x,
        "y": target.y,
        "display": {
            "id": target.display.id,
            "x": target.display.x,
            "y": target.display.y,
            "width": target.display.width,
            "height": target.display.height,
            "scale": target.display.scale,
            "coordinate_space": target.display.coordinate_space,
        },
    }


def validate_calibration_samples_payload(session: CalibrationSessionRecord, payload: Any) -> None:
    if not isinstance(payload, dict):
        raise CalibrationSessionError("invalid_calibration_sample", "Sample payload must be an object")
    expected_target = (
        session.targets[session.current_target_index]
        if session.current_target_index < len(session.targets)
        else None
    )
    if expected_target is None:
        raise CalibrationSessionError("invalid_calibration_sample", "All targets already have samples")
    if payload.get("target_id") != expected_target.id:
        raise CalibrationSessionError("invalid_calibration_sample", f"Expected samples for target {expected_target.id}")
    samples = payload.get("samples")
    if not isinstance(samples, list) or len(samples) == 0:
        raise CalibrationSessionError("invalid_calibration_sample", "Sample batch must not be empty")

    for sample in samples:
        validate_calibration_sample(sample)


def validate_calibration_sample(sample: Any) -> None:
    if not isinstance(sample, dict):
        raise CalibrationSessionError("invalid_calibration_sample", "Calibration sample must be an object")
    if {"frame", "frames", "video", "landmarks"}.intersection(sample.keys()):
        raise CalibrationSessionError("invalid_calibration_sample", "Calibration sample must not include raw camera data")
    if not is_finite_number(sample.get("sample_at_ms")):
        raise CalibrationSessionError("invalid_calibration_sample", "sample_at_ms must be finite")

    features = sample.get("features")
    quality = sample.get("quality")
    if not isinstance(features, dict) or not isinstance(quality, dict):
        raise CalibrationSessionError("invalid_calibration_sample", "Calibration sample requires features and quality")

    for name in CALIBRATION_FEATURE_NAMES:
        value = features.get(name)
        if not is_finite_number(value):
            raise CalibrationSessionError("invalid_calibration_sample", f"Feature {name} must be finite")
        if name not in {"head_yaw", "head_pitch", "head_roll"} and not 0 <= value <= 1:
            raise CalibrationSessionError("invalid_calibration_sample", f"Feature {name} must be between 0 and 1")

    for name in (
        "eye_openness",
        "landmark_stability",
        "face_stability",
        "left_right_divergence",
        "temporal_jitter",
    ):
        value = quality.get(name)
        if not is_finite_number(value) or not 0 <= value <= 1:
            raise CalibrationSessionError("invalid_calibration_sample", f"Quality {name} must be between 0 and 1")


def fit_profile(
    initial_session: CalibrationSessionRecord,
    *,
    validation_session: CalibrationSessionRecord,
) -> CalibrationProfile:
    regression = fit_regression(initial_session)
    correction_grid = [
        correction_node_for_target(target, regression)
        for target in initial_session.targets
    ]
    validation = validate_profile(regression, correction_grid, validation_session)
    if not validation.accepted:
        raise CalibrationSessionError("calibration_failed", "Validation error exceeded MVP thresholds")

    created_at = now_ms()
    return CalibrationProfile(
        profile_id=f"profile_{uuid4().hex[:12]}",
        created_at_ms=created_at,
        updated_at_ms=created_at,
        display=initial_session.display,
        feature_names=CALIBRATION_FEATURE_NAMES,
        regression=regression,
        correction_grid=correction_grid,
        validation=validation,
        drift_corrections=0,
    )


def fit_regression(session: CalibrationSessionRecord) -> RegressionModel:
    rows: list[list[float]] = []
    x_values: list[float] = []
    y_values: list[float] = []
    for target in session.targets:
        for sample in target.samples:
            rows.append(feature_row(sample))
            x_values.append(target.x)
            y_values.append(target.y)

    if len(rows) < len(session.targets):
        raise CalibrationSessionError("calibration_failed", "Insufficient calibration samples")

    x_coefficients, x_intercept = solve_ridge(rows, x_values, alpha=1.0)
    y_coefficients, y_intercept = solve_ridge(rows, y_values, alpha=1.0)
    return RegressionModel(
        x_coefficients=x_coefficients,
        y_coefficients=y_coefficients,
        x_intercept=x_intercept,
        y_intercept=y_intercept,
    )


def solve_ridge(rows: list[list[float]], values: list[float], alpha: float) -> tuple[list[float], float]:
    width = len(CALIBRATION_FEATURE_NAMES) + 1
    matrix = [[0.0 for _ in range(width)] for _ in range(width)]
    vector = [0.0 for _ in range(width)]

    for row, value in zip(rows, values, strict=True):
        design = [*row, 1.0]
        for i, left in enumerate(design):
            vector[i] += left * value
            for j, right in enumerate(design):
                matrix[i][j] += left * right

    for index in range(width - 1):
        matrix[index][index] += alpha

    solved = solve_linear_system(matrix, vector)
    return solved[:-1], solved[-1]


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for pivot_index in range(size):
        best_row = max(range(pivot_index, size), key=lambda row: abs(augmented[row][pivot_index]))
        if abs(augmented[best_row][pivot_index]) < 1e-9:
            raise CalibrationSessionError("calibration_failed", "Model fitting failed")
        augmented[pivot_index], augmented[best_row] = augmented[best_row], augmented[pivot_index]
        pivot = augmented[pivot_index][pivot_index]
        augmented[pivot_index] = [value / pivot for value in augmented[pivot_index]]
        for row_index in range(size):
            if row_index == pivot_index:
                continue
            factor = augmented[row_index][pivot_index]
            augmented[row_index] = [
                value - factor * augmented[pivot_index][column_index]
                for column_index, value in enumerate(augmented[row_index])
            ]
    return [row[-1] for row in augmented]


def validate_profile(
    regression: RegressionModel,
    correction_grid: list[CorrectionNode],
    validation_session: CalibrationSessionRecord,
) -> ValidationMetrics:
    errors = [
        distance(predict_with_correction(regression, correction_grid, sample, target), (target.x, target.y))
        for target in validation_session.targets
        for sample in target.samples
    ]
    if not errors:
        raise CalibrationSessionError("calibration_failed", "Validation needs samples")

    sorted_errors = sorted(errors)
    midpoint = len(sorted_errors) // 2
    median = (
        sorted_errors[midpoint]
        if len(sorted_errors) % 2
        else (sorted_errors[midpoint - 1] + sorted_errors[midpoint]) / 2
    )
    mean = sum(errors) / len(errors)
    max_error = max(errors)
    return ValidationMetrics(
        mode="validation-5-point",
        mean_error_px=mean,
        median_error_px=median,
        max_error_px=max_error,
        accepted=mean <= VALIDATION_MEAN_ERROR_THRESHOLD_PX and max_error <= VALIDATION_MAX_ERROR_THRESHOLD_PX,
        mean_error_threshold_px=VALIDATION_MEAN_ERROR_THRESHOLD_PX,
        max_error_threshold_px=VALIDATION_MAX_ERROR_THRESHOLD_PX,
        sample_count=len(errors),
    )


def correction_node_for_target(target: SessionTarget, regression: RegressionModel) -> CorrectionNode:
    predictions = [predict(regression, sample) for sample in target.samples]
    if not predictions:
        dx = 0.0
        dy = 0.0
    else:
        dx = sum(target.x - prediction[0] for prediction in predictions) / len(predictions)
        dy = sum(target.y - prediction[1] for prediction in predictions) / len(predictions)
    return CorrectionNode(target_id=target.id, x_ratio=target.x_ratio, y_ratio=target.y_ratio, dx=dx, dy=dy)


def apply_drift_correction(
    profile: CalibrationProfile,
    session: CalibrationSessionRecord,
) -> CalibrationProfile:
    target = session.targets[0]
    errors = [
        (target.x - predict(profile.regression, sample)[0], target.y - predict(profile.regression, sample)[1])
        for sample in target.samples
    ]
    if not errors:
        raise CalibrationSessionError("calibration_failed", "Drift correction needs samples")

    dx = sum(error[0] for error in errors) / len(errors)
    dy = sum(error[1] for error in errors) / len(errors)
    if math.hypot(dx, dy) > 220:
        raise CalibrationSessionError("calibration_failed", "Drift correction error is implausible")

    return replace(
        profile,
        updated_at_ms=now_ms(),
        correction_grid=[
            replace(node, dx=node.dx + dx, dy=node.dy + dy)
            for node in profile.correction_grid
        ],
        drift_corrections=profile.drift_corrections + 1,
    )


def predict(regression: RegressionModel, sample: dict[str, Any]) -> tuple[float, float]:
    row = feature_row(sample)
    x = sum(coefficient * value for coefficient, value in zip(regression.x_coefficients, row, strict=True))
    y = sum(coefficient * value for coefficient, value in zip(regression.y_coefficients, row, strict=True))
    return x + regression.x_intercept, y + regression.y_intercept


def predict_with_correction(
    regression: RegressionModel,
    correction_grid: list[CorrectionNode],
    sample: dict[str, Any],
    target: SessionTarget,
) -> tuple[float, float]:
    x, y = predict(regression, sample)
    node = min(
        correction_grid,
        key=lambda item: math.hypot(item.x_ratio - target.x_ratio, item.y_ratio - target.y_ratio),
    )
    return x + node.dx, y + node.dy


def feature_row(sample: dict[str, Any]) -> list[float]:
    return [float(sample["features"][name]) for name in CALIBRATION_FEATURE_NAMES]


def distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def is_finite_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def load_calibration_profile(path: Path) -> CalibrationProfile | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("profile_id"), str):
        return None

    return CalibrationProfile(
        profile_id=payload["profile_id"],
        created_at_ms=payload["created_at_ms"],
        updated_at_ms=payload["updated_at_ms"],
        display=CalibrationDisplay(**payload["display"]),
        feature_names=tuple(payload["feature_names"]),
        regression=RegressionModel(**payload["regression"]),
        correction_grid=[CorrectionNode(**node) for node in payload["correction_grid"]],
        validation=ValidationMetrics(**payload["validation"]),
        drift_corrections=payload.get("drift_corrections", 0),
    )


def save_calibration_profile(path: Path, profile: CalibrationProfile) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(profile.to_json_dict(), file, indent=2, sort_keys=True)
        file.write("\n")
