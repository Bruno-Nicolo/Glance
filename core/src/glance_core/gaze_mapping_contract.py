from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .calibration_contract import CALIBRATION_FEATURE_NAMES, CalibrationProfile, CorrectionNode

GAZE_MAPPING_CONTRACT_VERSION = 1
GAZE_MAPPING_SMOOTHING_ALPHA = 0.5
GAZE_MAPPING_LOW_CONFIDENCE_THRESHOLD = 0.6
GAZE_MAPPING_CORRECTION_MODE = "idw-3x3"
GAZE_MAPPING_INVALID_SAMPLE_STATUSES = ("face-lost", "uncalibrated", "paused")

CONFIDENCE_QUALITY_FIELD_NAMES = (
    "eye_openness",
    "landmark_stability",
    "face_stability",
    "left_right_divergence",
    "temporal_jitter",
)

GazeMappingStatus = Literal[
    "valid",
    "low-confidence",
    "face-lost",
    "uncalibrated",
    "paused",
]
GazeSource = Literal["synthetic", "camera"]
GazeInvalidReason = Literal[
    "face-lost",
    "uncalibrated",
    "paused",
    "synthetic-disabled",
    "tracking-stopped",
]


@dataclass(frozen=True, kw_only=True)
class RawGazeSample:
    sample_at_ms: int
    features: dict[str, float] | None
    quality: dict[str, float] | None
    face_detected: bool = True
    paused: bool = False


@dataclass(frozen=True, kw_only=True)
class GazeMappingResult:
    sample_at_ms: int
    x: float
    y: float
    confidence: float
    status: GazeMappingStatus
    source: GazeSource
    profile_id: str | None
    raw_x: float | None
    raw_y: float | None
    corrected_x: float | None
    corrected_y: float | None
    smoothing_alpha: float
    confidence_threshold: float
    correction: str
    invalid_reason: GazeInvalidReason | None = None

    def debug(self) -> "GazeMappingDebug":
        return GazeMappingDebug(
            profile_id=self.profile_id,
            status=self.status,
            confidence=self.confidence,
            sample_at_ms=self.sample_at_ms,
            source=self.source,
            correction=self.correction,
            smoothing_alpha=self.smoothing_alpha,
            confidence_threshold=self.confidence_threshold,
            invalid_reason=self.invalid_reason,
        )


@dataclass(frozen=True, kw_only=True)
class GazeMappingDebug:
    profile_id: str | None
    status: GazeMappingStatus
    confidence: float | None
    sample_at_ms: int | None
    correction: str = GAZE_MAPPING_CORRECTION_MODE
    smoothing_alpha: float = GAZE_MAPPING_SMOOTHING_ALPHA
    confidence_threshold: float = GAZE_MAPPING_LOW_CONFIDENCE_THRESHOLD
    invalid_reason: GazeInvalidReason | None = None
    source: GazeSource = "camera"
    contract_version: int = GAZE_MAPPING_CONTRACT_VERSION

    def to_json_dict(self) -> dict[str, object]:
        return asdict(self)


def map_gaze_sample(
    sample: RawGazeSample,
    *,
    profile: CalibrationProfile | None,
    previous_output: tuple[float, float] | None,
    smoothing_alpha: float = GAZE_MAPPING_SMOOTHING_ALPHA,
    confidence_threshold: float = GAZE_MAPPING_LOW_CONFIDENCE_THRESHOLD,
) -> GazeMappingResult:
    if sample.paused:
        return invalid_result(
            sample,
            status="paused",
            previous_output=previous_output,
            profile_id=profile.profile_id if profile else None,
            smoothing_alpha=smoothing_alpha,
            confidence_threshold=confidence_threshold,
        )
    if profile is None:
        return invalid_result(
            sample,
            status="uncalibrated",
            previous_output=previous_output,
            profile_id=None,
            smoothing_alpha=smoothing_alpha,
            confidence_threshold=confidence_threshold,
        )
    if not sample.face_detected or sample.features is None or sample.quality is None:
        return invalid_result(
            sample,
            status="face-lost",
            previous_output=previous_output,
            profile_id=profile.profile_id,
            smoothing_alpha=smoothing_alpha,
            confidence_threshold=confidence_threshold,
        )

    raw_x, raw_y = predict(profile, sample.features)
    corrected_x, corrected_y = apply_interpolated_correction(profile, raw_x, raw_y)
    x, y = smooth(
        previous_output=previous_output,
        corrected=(corrected_x, corrected_y),
        alpha=smoothing_alpha,
    )
    confidence = confidence_from_quality(sample.quality)
    status: GazeMappingStatus = "valid" if confidence >= confidence_threshold else "low-confidence"

    return GazeMappingResult(
        sample_at_ms=sample.sample_at_ms,
        x=x,
        y=y,
        confidence=confidence,
        status=status,
        source="camera",
        profile_id=profile.profile_id,
        raw_x=raw_x,
        raw_y=raw_y,
        corrected_x=corrected_x,
        corrected_y=corrected_y,
        smoothing_alpha=smoothing_alpha,
        confidence_threshold=confidence_threshold,
        correction=GAZE_MAPPING_CORRECTION_MODE,
    )


def invalid_result(
    sample: RawGazeSample,
    *,
    status: Literal["face-lost", "uncalibrated", "paused"],
    previous_output: tuple[float, float] | None,
    profile_id: str | None,
    smoothing_alpha: float,
    confidence_threshold: float,
) -> GazeMappingResult:
    x, y = previous_output or (0.0, 0.0)
    return GazeMappingResult(
        sample_at_ms=sample.sample_at_ms,
        x=x,
        y=y,
        confidence=0.0,
        status=status,
        source="camera",
        profile_id=profile_id,
        raw_x=None,
        raw_y=None,
        corrected_x=None,
        corrected_y=None,
        smoothing_alpha=smoothing_alpha,
        confidence_threshold=confidence_threshold,
        correction=GAZE_MAPPING_CORRECTION_MODE,
        invalid_reason=status,
    )


def predict(profile: CalibrationProfile, features: dict[str, float]) -> tuple[float, float]:
    row = [features[name] for name in profile.feature_names]
    x = sum(
        coefficient * value
        for coefficient, value in zip(profile.regression.x_coefficients, row, strict=True)
    )
    y = sum(
        coefficient * value
        for coefficient, value in zip(profile.regression.y_coefficients, row, strict=True)
    )
    return x + profile.regression.x_intercept, y + profile.regression.y_intercept


def apply_interpolated_correction(
    profile: CalibrationProfile,
    raw_x: float,
    raw_y: float,
) -> tuple[float, float]:
    if not profile.correction_grid:
        return raw_x, raw_y

    x_ratio = (raw_x - profile.display.x) / profile.display.width
    y_ratio = (raw_y - profile.display.y) / profile.display.height
    dx, dy = interpolated_delta(profile.correction_grid, x_ratio, y_ratio)
    return raw_x + dx, raw_y + dy


def interpolated_delta(
    correction_grid: list[CorrectionNode],
    x_ratio: float,
    y_ratio: float,
) -> tuple[float, float]:
    weighted_dx = 0.0
    weighted_dy = 0.0
    total_weight = 0.0
    for node in correction_grid:
        distance_squared = ((node.x_ratio - x_ratio) ** 2) + ((node.y_ratio - y_ratio) ** 2)
        if distance_squared == 0:
            return node.dx, node.dy
        weight = 1 / distance_squared
        weighted_dx += node.dx * weight
        weighted_dy += node.dy * weight
        total_weight += weight

    return weighted_dx / total_weight, weighted_dy / total_weight


def smooth(
    *,
    previous_output: tuple[float, float] | None,
    corrected: tuple[float, float],
    alpha: float,
) -> tuple[float, float]:
    if previous_output is None:
        return corrected
    return (
        previous_output[0] + ((corrected[0] - previous_output[0]) * alpha),
        previous_output[1] + ((corrected[1] - previous_output[1]) * alpha),
    )


def confidence_from_quality(quality: dict[str, float]) -> float:
    openness = quality["eye_openness"]
    landmark_stability = quality["landmark_stability"]
    face_stability = quality["face_stability"]
    divergence_score = 1 - quality["left_right_divergence"]
    jitter_score = 1 - quality["temporal_jitter"]
    confidence = min(openness, landmark_stability, face_stability, divergence_score, jitter_score)
    return max(0.0, min(1.0, confidence))
