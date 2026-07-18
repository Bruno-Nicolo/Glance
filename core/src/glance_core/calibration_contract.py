from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

CALIBRATION_CONTRACT_VERSION = 1
VALIDATION_MEAN_ERROR_THRESHOLD_PX = 90
VALIDATION_MAX_ERROR_THRESHOLD_PX = 160
DRIFT_CORRECTION_PLAUSIBILITY_CEILING_PX = 220

CalibrationMode = Literal["initial-9-point", "validation", "drift-1-point"]
ValidationMode = Literal["validation-3-point", "validation-5-point", "drift-check-1-point"]
CoordinateSpace = Literal["display-logical-top-left"]

CALIBRATION_FEATURE_NAMES = (
    "left_iris_x",
    "left_iris_y",
    "right_iris_x",
    "right_iris_y",
    "avg_iris_x",
    "avg_iris_y",
    "face_center_x",
    "face_center_y",
    "face_scale",
    "head_yaw",
    "head_pitch",
    "head_roll",
)


@dataclass(frozen=True, kw_only=True)
class CalibrationTarget:
    id: str
    x_ratio: float
    y_ratio: float


CALIBRATION_TARGETS_9_POINT = (
    CalibrationTarget(id="center", x_ratio=0.5, y_ratio=0.5),
    CalibrationTarget(id="top-left", x_ratio=0.1, y_ratio=0.1),
    CalibrationTarget(id="top-center", x_ratio=0.5, y_ratio=0.1),
    CalibrationTarget(id="top-right", x_ratio=0.9, y_ratio=0.1),
    CalibrationTarget(id="middle-left", x_ratio=0.1, y_ratio=0.5),
    CalibrationTarget(id="middle-right", x_ratio=0.9, y_ratio=0.5),
    CalibrationTarget(id="bottom-left", x_ratio=0.1, y_ratio=0.9),
    CalibrationTarget(id="bottom-center", x_ratio=0.5, y_ratio=0.9),
    CalibrationTarget(id="bottom-right", x_ratio=0.9, y_ratio=0.9),
)


@dataclass(frozen=True, kw_only=True)
class CalibrationDisplay:
    id: str
    width: float
    height: float
    scale: float
    x: float = 0
    y: float = 0
    coordinate_space: CoordinateSpace = "display-logical-top-left"


@dataclass(frozen=True, kw_only=True)
class RegressionModel:
    x_coefficients: list[float]
    y_coefficients: list[float]
    x_intercept: float
    y_intercept: float
    regularization: Literal["ridge"] = "ridge"
    regularization_alpha: float = 1.0

    def __post_init__(self) -> None:
        expected_count = len(CALIBRATION_FEATURE_NAMES)
        if len(self.x_coefficients) != expected_count:
            raise ValueError(f"x_coefficients length must be {expected_count}")
        if len(self.y_coefficients) != expected_count:
            raise ValueError(f"y_coefficients length must be {expected_count}")


@dataclass(frozen=True, kw_only=True)
class CorrectionNode:
    target_id: str
    x_ratio: float
    y_ratio: float
    dx: float
    dy: float


@dataclass(frozen=True, kw_only=True)
class ValidationMetrics:
    mode: ValidationMode
    mean_error_px: float
    median_error_px: float
    max_error_px: float
    accepted: bool
    mean_error_threshold_px: float
    max_error_threshold_px: float
    sample_count: int

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class CalibrationProfile:
    profile_id: str
    created_at_ms: int
    updated_at_ms: int
    display: CalibrationDisplay
    feature_names: tuple[str, ...]
    regression: RegressionModel
    correction_grid: list[CorrectionNode]
    validation: ValidationMetrics
    drift_corrections: int = 0
    contract_version: int = CALIBRATION_CONTRACT_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["feature_names"] = list(self.feature_names)
        return payload
