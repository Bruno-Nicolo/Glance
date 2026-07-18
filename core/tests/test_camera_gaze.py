from __future__ import annotations

import unittest
from types import SimpleNamespace

from glance_core.calibration_contract import (
    CALIBRATION_FEATURE_NAMES,
    CalibrationDisplay,
    CalibrationProfile,
    RegressionModel,
    ValidationMetrics,
)
from glance_core.camera_gaze import (
    CameraGazeMetrics,
    extract_raw_gaze_sample,
    gaze_sample_event_from_mapping,
)
from glance_core.gaze_mapping_contract import RawGazeSample, map_gaze_sample
from glance_core.helper_events import DisplayBounds


class CameraGazeTests(unittest.TestCase):
    def test_extracts_normalized_feature_and_quality_contract_from_face_landmarks(self) -> None:
        previous = self.landmark_result(
            left_iris=(0.44, 0.50),
            right_iris=(0.56, 0.50),
            face_center=(0.50, 0.50),
        )
        current = self.landmark_result(
            left_iris=(0.45, 0.52),
            right_iris=(0.57, 0.52),
            face_center=(0.51, 0.50),
        )

        sample = extract_raw_gaze_sample(
            current,
            sample_at_ms=1721300000000,
            previous_landmarks=previous.face_landmarks[0],
        )

        self.assertTrue(sample.face_detected)
        self.assertIsNotNone(sample.features)
        self.assertIsNotNone(sample.quality)
        assert sample.features is not None
        assert sample.quality is not None
        self.assertEqual(set(sample.features), set(CALIBRATION_FEATURE_NAMES))
        self.assertAlmostEqual(sample.features["left_iris_x"], 0.5)
        self.assertAlmostEqual(sample.features["right_iris_x"], 0.5)
        self.assertAlmostEqual(sample.features["avg_iris_x"], 0.5)
        self.assertAlmostEqual(sample.features["face_center_x"], 0.51)
        self.assertGreater(sample.features["face_scale"], 0)
        self.assertGreaterEqual(sample.quality["eye_openness"], 0)
        self.assertLessEqual(sample.quality["temporal_jitter"], 1)

    def test_extracts_face_lost_when_mediapipe_has_no_face_landmarks(self) -> None:
        sample = extract_raw_gaze_sample(
            SimpleNamespace(face_landmarks=[]),
            sample_at_ms=1721300000000,
        )

        self.assertEqual(
            sample,
            RawGazeSample(
                sample_at_ms=1721300000000,
                features=None,
                quality=None,
                face_detected=False,
            ),
        )

    def test_camera_mapping_result_converts_to_helper_gaze_event(self) -> None:
        profile = self.profile()
        result = map_gaze_sample(
            RawGazeSample(
                sample_at_ms=1721300000000,
                features={name: 0.5 for name in CALIBRATION_FEATURE_NAMES},
                quality={
                    "eye_openness": 0.9,
                    "landmark_stability": 0.91,
                    "face_stability": 0.92,
                    "left_right_divergence": 0.03,
                    "temporal_jitter": 0.04,
                },
            ),
            profile=profile,
            previous_output=None,
        )

        event = gaze_sample_event_from_mapping(
            result,
            display=DisplayBounds(id="main", x=0, y=0, width=1440, height=900, scale=2),
            sent_at_ms=1721300000033,
            sequence=7,
        ).to_json_dict()

        self.assertEqual(event["type"], "gaze.sample")
        self.assertEqual(event["source"], "camera")
        self.assertEqual(event["status"], "valid")
        self.assertEqual(event["sample_at_ms"], 1721300000000)
        self.assertEqual(event["sequence"], 7)
        self.assertEqual(event["x"], 720)
        self.assertEqual(event["y"], 450)

    def test_metrics_report_measured_fps_and_invalid_counts(self) -> None:
        metrics = CameraGazeMetrics(started_at_ms=1000)
        metrics.record_frame_submitted()
        metrics.record_frame_submitted()
        metrics.record_inference_result(sample_at_ms=2000, valid=True)
        metrics.record_inference_result(sample_at_ms=3000, valid=False)
        metrics.record_sample_emitted()
        metrics.record_sample_emitted()
        metrics.record_frame_dropped()

        payload = metrics.to_json_dict(now_ms=5000)

        self.assertEqual(payload["captured_frames"], 2)
        self.assertEqual(payload["inference_results"], 2)
        self.assertEqual(payload["emitted_samples"], 2)
        self.assertEqual(payload["invalid_samples"], 1)
        self.assertEqual(payload["dropped_frames"], 1)
        self.assertEqual(payload["last_sample_at_ms"], 3000)
        self.assertEqual(payload["captured_fps"], 0.5)
        self.assertEqual(payload["inference_fps"], 0.5)
        self.assertEqual(payload["emitted_fps"], 0.5)

    def profile(self) -> CalibrationProfile:
        x_coefficients = [0.0] * len(CALIBRATION_FEATURE_NAMES)
        y_coefficients = [0.0] * len(CALIBRATION_FEATURE_NAMES)
        x_coefficients[CALIBRATION_FEATURE_NAMES.index("avg_iris_x")] = 1440
        y_coefficients[CALIBRATION_FEATURE_NAMES.index("avg_iris_y")] = 900
        return CalibrationProfile(
            profile_id="profile_test",
            created_at_ms=1721300000000,
            updated_at_ms=1721300000000,
            display=CalibrationDisplay(id="main", width=1440, height=900, scale=2),
            feature_names=CALIBRATION_FEATURE_NAMES,
            regression=RegressionModel(
                x_coefficients=x_coefficients,
                y_coefficients=y_coefficients,
                x_intercept=0,
                y_intercept=0,
            ),
            correction_grid=[],
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

    def landmark_result(
        self,
        *,
        left_iris: tuple[float, float],
        right_iris: tuple[float, float],
        face_center: tuple[float, float],
    ) -> SimpleNamespace:
        landmarks = [SimpleNamespace(x=face_center[0], y=face_center[1], z=0.0) for _ in range(478)]
        for index, point in {
            33: (0.40, 0.50),
            133: (0.50, 0.50),
            159: (0.45, 0.47),
            145: (0.45, 0.57),
            362: (0.52, 0.50),
            263: (0.62, 0.50),
            386: (0.57, 0.47),
            374: (0.57, 0.57),
        }.items():
            landmarks[index] = SimpleNamespace(x=point[0], y=point[1], z=0.0)
        for index in range(468, 473):
            landmarks[index] = SimpleNamespace(x=left_iris[0], y=left_iris[1], z=0.0)
        for index in range(473, 478):
            landmarks[index] = SimpleNamespace(x=right_iris[0], y=right_iris[1], z=0.0)
        landmarks[10] = SimpleNamespace(x=face_center[0], y=face_center[1] - 0.25, z=0.0)
        landmarks[152] = SimpleNamespace(x=face_center[0], y=face_center[1] + 0.25, z=0.0)
        landmarks[234] = SimpleNamespace(x=face_center[0] - 0.25, y=face_center[1], z=0.0)
        landmarks[454] = SimpleNamespace(x=face_center[0] + 0.25, y=face_center[1], z=0.0)
        return SimpleNamespace(face_landmarks=[landmarks], facial_transformation_matrixes=[])


if __name__ == "__main__":
    unittest.main()
