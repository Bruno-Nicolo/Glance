from __future__ import annotations

import unittest

from glance_core.calibration_contract import (
    CALIBRATION_FEATURE_NAMES,
    CalibrationDisplay,
    CalibrationProfile,
    CorrectionNode,
    RegressionModel,
    ValidationMetrics,
)
from glance_core.gaze_mapping_contract import (
    CONFIDENCE_QUALITY_FIELD_NAMES,
    GAZE_MAPPING_CONTRACT_VERSION,
    GAZE_MAPPING_INVALID_SAMPLE_STATUSES,
    GAZE_MAPPING_LOW_CONFIDENCE_THRESHOLD,
    GAZE_MAPPING_SMOOTHING_ALPHA,
    GazeMappingDebug,
    RawGazeSample,
    map_gaze_sample,
)


class GazeMappingContractTests(unittest.TestCase):
    def test_contract_names_mapping_confidence_and_invalid_sample_defaults(self) -> None:
        self.assertEqual(GAZE_MAPPING_CONTRACT_VERSION, 1)
        self.assertEqual(GAZE_MAPPING_SMOOTHING_ALPHA, 0.5)
        self.assertEqual(GAZE_MAPPING_LOW_CONFIDENCE_THRESHOLD, 0.6)
        self.assertEqual(
            CONFIDENCE_QUALITY_FIELD_NAMES,
            (
                "eye_openness",
                "landmark_stability",
                "face_stability",
                "left_right_divergence",
                "temporal_jitter",
            ),
        )
        self.assertEqual(
            GAZE_MAPPING_INVALID_SAMPLE_STATUSES,
            ("face-lost", "uncalibrated", "paused"),
        )

    def test_mapping_uses_regression_then_interpolated_grid_correction_then_smoothing(self) -> None:
        profile = self.profile(
            correction_grid=[
                CorrectionNode(target_id="top-left", x_ratio=0.1, y_ratio=0.1, dx=10, dy=0),
                CorrectionNode(target_id="top-right", x_ratio=0.9, y_ratio=0.1, dx=30, dy=0),
                CorrectionNode(target_id="bottom-left", x_ratio=0.1, y_ratio=0.9, dx=50, dy=0),
                CorrectionNode(target_id="bottom-right", x_ratio=0.9, y_ratio=0.9, dx=70, dy=0),
            ],
        )

        result = map_gaze_sample(
            RawGazeSample(
                sample_at_ms=1721300000000,
                features=self.features(avg_iris_x=0.5, avg_iris_y=0.5),
                quality=self.quality(),
            ),
            profile=profile,
            previous_output=(300, 100),
            smoothing_alpha=0.5,
            confidence_threshold=0.6,
        )

        self.assertEqual(result.status, "valid")
        self.assertEqual(result.source, "camera")
        self.assertEqual(result.profile_id, "profile_test")
        self.assertEqual(result.raw_x, 500)
        self.assertEqual(result.raw_y, 250)
        self.assertEqual(result.corrected_x, 540)
        self.assertEqual(result.corrected_y, 250)
        self.assertEqual(result.x, 420)
        self.assertEqual(result.y, 175)
        self.assertEqual(result.confidence, 0.95)

    def test_low_confidence_sample_keeps_coordinates_but_marks_status(self) -> None:
        result = map_gaze_sample(
            RawGazeSample(
                sample_at_ms=1721300000000,
                features=self.features(avg_iris_x=0.5, avg_iris_y=0.5),
                quality=self.quality(eye_openness=0.4),
            ),
            profile=self.profile(),
            previous_output=None,
            confidence_threshold=0.6,
        )

        self.assertEqual(result.status, "low-confidence")
        self.assertEqual(result.confidence, 0.4)
        self.assertEqual(result.x, 500)
        self.assertEqual(result.y, 250)

    def test_mapping_uses_persisted_profile_feature_order(self) -> None:
        feature_names = tuple(reversed(CALIBRATION_FEATURE_NAMES))
        x_coefficients = [0.0] * len(feature_names)
        x_coefficients[feature_names.index("avg_iris_x")] = 1000
        y_coefficients = [0.0] * len(feature_names)
        y_coefficients[feature_names.index("avg_iris_y")] = 500

        profile = self.profile(
            feature_names=feature_names,
            x_coefficients=x_coefficients,
            y_coefficients=y_coefficients,
        )

        result = map_gaze_sample(
            RawGazeSample(
                sample_at_ms=1721300000000,
                features=self.features(avg_iris_x=0.25, avg_iris_y=0.75),
                quality=self.quality(),
            ),
            profile=profile,
            previous_output=None,
        )

        self.assertEqual(result.x, 250)
        self.assertEqual(result.y, 375)

    def test_invalid_sample_freezes_previous_position_and_reports_reason(self) -> None:
        result = map_gaze_sample(
            RawGazeSample(
                sample_at_ms=1721300000000,
                features=None,
                quality=None,
                face_detected=False,
            ),
            profile=self.profile(),
            previous_output=(321, 654),
        )

        self.assertEqual(result.status, "face-lost")
        self.assertEqual(result.confidence, 0)
        self.assertEqual(result.x, 321)
        self.assertEqual(result.y, 654)
        self.assertIsNone(result.raw_x)
        self.assertIsNone(result.corrected_x)

    def test_mapping_debug_status_payload_is_privacy_preserving(self) -> None:
        payload = GazeMappingDebug(
            profile_id="profile_test",
            status="low-confidence",
            confidence=0.42,
            sample_at_ms=1721300000000,
            correction="idw-3x3",
            smoothing_alpha=0.5,
            confidence_threshold=0.6,
            invalid_reason=None,
        ).to_json_dict()

        self.assertEqual(
            payload,
            {
                "contract_version": 1,
                "profile_id": "profile_test",
                "status": "low-confidence",
                "confidence": 0.42,
                "sample_at_ms": 1721300000000,
                "source": "camera",
                "correction": "idw-3x3",
                "smoothing_alpha": 0.5,
                "confidence_threshold": 0.6,
                "invalid_reason": None,
            },
        )
        self.assertNotIn("features", payload)
        self.assertNotIn("quality", payload)

    def profile(
        self,
        *,
        correction_grid: list[CorrectionNode] | None = None,
        feature_names: tuple[str, ...] = CALIBRATION_FEATURE_NAMES,
        x_coefficients: list[float] | None = None,
        y_coefficients: list[float] | None = None,
    ) -> CalibrationProfile:
        if x_coefficients is None:
            x_coefficients = [0.0] * len(feature_names)
            x_coefficients[feature_names.index("avg_iris_x")] = 1000
        if y_coefficients is None:
            y_coefficients = [0.0] * len(feature_names)
            y_coefficients[feature_names.index("avg_iris_y")] = 500
        return CalibrationProfile(
            profile_id="profile_test",
            created_at_ms=1721300000000,
            updated_at_ms=1721300000000,
            display=CalibrationDisplay(id="main", width=1000, height=500, scale=2),
            feature_names=feature_names,
            regression=RegressionModel(
                x_coefficients=x_coefficients,
                y_coefficients=y_coefficients,
                x_intercept=0,
                y_intercept=0,
            ),
            correction_grid=correction_grid or [],
            validation=ValidationMetrics(
                mode="validation-5-point",
                mean_error_px=10,
                median_error_px=9,
                max_error_px=20,
                accepted=True,
                mean_error_threshold_px=90,
                max_error_threshold_px=160,
                sample_count=50,
            ),
        )

    def features(self, *, avg_iris_x: float, avg_iris_y: float) -> dict[str, float]:
        return {
            name: (
                avg_iris_x
                if name == "avg_iris_x"
                else avg_iris_y
                if name == "avg_iris_y"
                else 0.5
            )
            for name in CALIBRATION_FEATURE_NAMES
        }

    def quality(self, *, eye_openness: float = 0.95) -> dict[str, float]:
        return {
            "eye_openness": eye_openness,
            "landmark_stability": 0.96,
            "face_stability": 0.97,
            "left_right_divergence": 0.04,
            "temporal_jitter": 0.03,
        }


if __name__ == "__main__":
    unittest.main()
