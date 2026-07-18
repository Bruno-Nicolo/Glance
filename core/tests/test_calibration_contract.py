from __future__ import annotations

import unittest

from glance_core.calibration_contract import (
    CALIBRATION_CONTRACT_VERSION,
    CALIBRATION_FEATURE_NAMES,
    DRIFT_CORRECTION_PLAUSIBILITY_CEILING_PX,
    VALIDATION_MAX_ERROR_THRESHOLD_PX,
    VALIDATION_MEAN_ERROR_THRESHOLD_PX,
    CALIBRATION_TARGETS_9_POINT,
    CalibrationDisplay,
    CalibrationProfile,
    CorrectionNode,
    RegressionModel,
    ValidationMetrics,
)


class CalibrationContractTests(unittest.TestCase):
    def test_validation_and_drift_thresholds_are_named_contract_values(self) -> None:
        self.assertEqual(VALIDATION_MEAN_ERROR_THRESHOLD_PX, 90)
        self.assertEqual(VALIDATION_MAX_ERROR_THRESHOLD_PX, 160)
        self.assertEqual(DRIFT_CORRECTION_PLAUSIBILITY_CEILING_PX, 220)

    def test_initial_calibration_uses_fixed_nine_point_order(self) -> None:
        self.assertEqual(
            [target.id for target in CALIBRATION_TARGETS_9_POINT],
            [
                "center",
                "top-left",
                "top-center",
                "top-right",
                "middle-left",
                "middle-right",
                "bottom-left",
                "bottom-center",
                "bottom-right",
            ],
        )
        self.assertEqual(CALIBRATION_TARGETS_9_POINT[0].x_ratio, 0.5)
        self.assertEqual(CALIBRATION_TARGETS_9_POINT[0].y_ratio, 0.5)
        self.assertEqual(CALIBRATION_TARGETS_9_POINT[-1].x_ratio, 0.9)
        self.assertEqual(CALIBRATION_TARGETS_9_POINT[-1].y_ratio, 0.9)

    def test_persisted_profile_contains_model_metrics_and_no_raw_samples(self) -> None:
        profile = CalibrationProfile(
            profile_id="profile_01HX",
            created_at_ms=1721300000000,
            updated_at_ms=1721300005000,
            display=CalibrationDisplay(
                id="main",
                width=1440,
                height=900,
                scale=2,
            ),
            feature_names=CALIBRATION_FEATURE_NAMES,
            regression=RegressionModel(
                x_coefficients=[0.1] * len(CALIBRATION_FEATURE_NAMES),
                y_coefficients=[0.2] * len(CALIBRATION_FEATURE_NAMES),
                x_intercept=12.5,
                y_intercept=24.5,
                regularization="ridge",
                regularization_alpha=1.0,
            ),
            correction_grid=[
                CorrectionNode(target_id="center", x_ratio=0.5, y_ratio=0.5, dx=1.25, dy=-2.5)
            ],
            validation=ValidationMetrics(
                mode="validation-5-point",
                mean_error_px=42.5,
                median_error_px=38.25,
                max_error_px=91.2,
                accepted=True,
                mean_error_threshold_px=90,
                max_error_threshold_px=160,
                sample_count=240,
            ),
            drift_corrections=1,
        )

        payload = profile.to_json_dict()

        self.assertEqual(payload["contract_version"], CALIBRATION_CONTRACT_VERSION)
        self.assertEqual(payload["profile_id"], "profile_01HX")
        self.assertEqual(payload["display"]["coordinate_space"], "display-logical-top-left")
        self.assertEqual(payload["feature_names"], list(CALIBRATION_FEATURE_NAMES))
        self.assertEqual(payload["regression"]["regularization"], "ridge")
        self.assertEqual(payload["validation"]["accepted"], True)
        self.assertEqual(payload["drift_corrections"], 1)
        self.assert_no_private_payload_keys(payload)

    def test_regression_coefficients_must_match_feature_vector_length(self) -> None:
        with self.assertRaisesRegex(ValueError, "x_coefficients length"):
            RegressionModel(
                x_coefficients=[0.1],
                y_coefficients=[0.2] * len(CALIBRATION_FEATURE_NAMES),
                x_intercept=12.5,
                y_intercept=24.5,
            )

    def assert_no_private_payload_keys(self, payload: object) -> None:
        private_keys = {"samples", "frames", "frame", "video", "landmarks", "gaze_trace"}

        if isinstance(payload, dict):
            self.assertTrue(private_keys.isdisjoint(payload.keys()))
            for value in payload.values():
                self.assert_no_private_payload_keys(value)
        elif isinstance(payload, list):
            for value in payload:
                self.assert_no_private_payload_keys(value)


if __name__ == "__main__":
    unittest.main()
