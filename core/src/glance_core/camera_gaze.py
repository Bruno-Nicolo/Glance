from __future__ import annotations

import math
import queue
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gaze_mapping_contract import GazeMappingResult, RawGazeSample
from .helper_events import DisplayBounds, GazeSampleEvent, now_ms

LEFT_EYE_INDICES = (33, 133, 159, 145)
RIGHT_EYE_INDICES = (362, 263, 386, 374)
LEFT_IRIS_INDICES = tuple(range(468, 473))
RIGHT_IRIS_INDICES = tuple(range(473, 478))
FACE_BOUNDS_INDICES = (10, 152, 234, 454)


class CameraGazeError(RuntimeError):
    pass


@dataclass
class CameraGazeMetrics:
    started_at_ms: int
    captured_frames: int = 0
    inference_results: int = 0
    emitted_samples: int = 0
    invalid_samples: int = 0
    dropped_frames: int = 0
    last_sample_at_ms: int | None = None
    last_error: str | None = None

    def record_frame_submitted(self) -> None:
        self.captured_frames += 1

    def record_inference_result(self, *, sample_at_ms: int, valid: bool) -> None:
        self.inference_results += 1
        if not valid:
            self.invalid_samples += 1
        self.last_sample_at_ms = sample_at_ms

    def record_sample_emitted(self) -> None:
        self.emitted_samples += 1

    def record_frame_dropped(self) -> None:
        self.dropped_frames += 1

    def record_error(self, message: str) -> None:
        self.last_error = message

    def to_json_dict(self, *, now_ms: int) -> dict[str, object]:
        elapsed_seconds = max((now_ms - self.started_at_ms) / 1000, 0.001)
        return {
            "captured_frames": self.captured_frames,
            "inference_results": self.inference_results,
            "emitted_samples": self.emitted_samples,
            "invalid_samples": self.invalid_samples,
            "dropped_frames": self.dropped_frames,
            "last_sample_at_ms": self.last_sample_at_ms,
            "last_error": self.last_error,
            "captured_fps": round(self.captured_frames / elapsed_seconds, 2),
            "inference_fps": round(self.inference_results / elapsed_seconds, 2),
            "emitted_fps": round(self.emitted_samples / elapsed_seconds, 2),
        }


class MediaPipeOpenCVCamera:
    def __init__(
        self,
        *,
        model_asset_path: Path,
        camera_index: int = 0,
        frame_width: int = 640,
        frame_height: int = 480,
    ):
        self.model_asset_path = model_asset_path
        self.camera_index = camera_index
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.metrics = CameraGazeMetrics(started_at_ms=now_ms())
        self._cv2: Any | None = None
        self._mp: Any | None = None
        self._capture: Any | None = None
        self._landmarker: Any | None = None
        self._results: queue.Queue[RawGazeSample] = queue.Queue(maxsize=1)
        self._previous_landmarks: list[Any] | None = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        if not self.model_asset_path.exists():
            raise CameraGazeError(f"Missing MediaPipe Face Landmarker model: {self.model_asset_path}")

        try:
            import cv2  # type: ignore[import-not-found]
            import mediapipe as mp  # type: ignore[import-not-found]
        except ImportError as error:
            raise CameraGazeError("Install glance-core[vision] to enable camera gaze") from error

        self._cv2 = cv2
        self._mp = mp
        self._capture = cv2.VideoCapture(self.camera_index)
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        if not self._capture.isOpened():
            raise CameraGazeError("Camera is unavailable or permission was denied")

        vision = mp.tasks.vision
        options = vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_asset_path)),
            running_mode=vision.RunningMode.LIVE_STREAM,
            num_faces=1,
            output_facial_transformation_matrixes=True,
            result_callback=self._handle_result,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._started = True

    def sample(self) -> RawGazeSample | None:
        self.start()
        assert self._cv2 is not None
        assert self._mp is not None
        assert self._capture is not None
        assert self._landmarker is not None

        sample_at_ms = now_ms()
        ok, frame = self._capture.read()
        if not ok:
            self.metrics.record_error("Camera frame read failed")
            return RawGazeSample(
                sample_at_ms=sample_at_ms,
                features=None,
                quality=None,
                face_detected=False,
            )

        rgb_frame = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb_frame)
        self._landmarker.detect_async(image, sample_at_ms)
        self.metrics.record_frame_submitted()
        return self._latest_result()

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._started = False

    def _handle_result(self, result: Any, _output_image: Any, timestamp_ms: int) -> None:
        sample = extract_raw_gaze_sample(
            result,
            sample_at_ms=timestamp_ms,
            previous_landmarks=self._previous_landmarks,
        )
        if sample.face_detected and result.face_landmarks:
            self._previous_landmarks = list(result.face_landmarks[0])
        self.metrics.record_inference_result(
            sample_at_ms=sample.sample_at_ms,
            valid=sample.face_detected,
        )
        if self._results.full():
            self._results.get_nowait()
            self.metrics.record_frame_dropped()
        self._results.put_nowait(sample)

    def _latest_result(self) -> RawGazeSample | None:
        latest: RawGazeSample | None = None
        while True:
            try:
                latest = self._results.get_nowait()
            except queue.Empty:
                return latest


def extract_raw_gaze_sample(
    result: Any,
    *,
    sample_at_ms: int,
    previous_landmarks: list[Any] | None = None,
) -> RawGazeSample:
    face_landmarks = getattr(result, "face_landmarks", None) or []
    if not face_landmarks:
        return RawGazeSample(
            sample_at_ms=sample_at_ms,
            features=None,
            quality=None,
            face_detected=False,
        )

    landmarks = face_landmarks[0]
    left_iris = centroid(landmarks, LEFT_IRIS_INDICES)
    right_iris = centroid(landmarks, RIGHT_IRIS_INDICES)
    left_eye = eye_relative_position(landmarks, LEFT_EYE_INDICES, left_iris)
    right_eye = eye_relative_position(landmarks, RIGHT_EYE_INDICES, right_iris)
    face_center_x, face_center_y, face_scale = face_geometry(landmarks)
    head_yaw, head_pitch, head_roll = head_pose(result)
    left_right_divergence = clamp01(distance(left_eye, right_eye))
    temporal_jitter = clamp01(iris_jitter(landmarks, previous_landmarks) * 20)
    landmark_stability = 1 - temporal_jitter
    face_stability = 1 - clamp01(face_motion(landmarks, previous_landmarks) * 20)

    return RawGazeSample(
        sample_at_ms=sample_at_ms,
        features={
            "left_iris_x": left_eye[0],
            "left_iris_y": left_eye[1],
            "right_iris_x": right_eye[0],
            "right_iris_y": right_eye[1],
            "avg_iris_x": (left_eye[0] + right_eye[0]) / 2,
            "avg_iris_y": (left_eye[1] + right_eye[1]) / 2,
            "face_center_x": face_center_x,
            "face_center_y": face_center_y,
            "face_scale": face_scale,
            "head_yaw": head_yaw,
            "head_pitch": head_pitch,
            "head_roll": head_roll,
        },
        quality={
            "eye_openness": eye_openness(landmarks),
            "landmark_stability": landmark_stability,
            "face_stability": face_stability,
            "left_right_divergence": left_right_divergence,
            "temporal_jitter": temporal_jitter,
        },
    )


def gaze_sample_event_from_mapping(
    result: GazeMappingResult,
    *,
    display: DisplayBounds,
    sent_at_ms: int,
    sequence: int,
) -> GazeSampleEvent:
    return GazeSampleEvent(
        sent_at_ms=sent_at_ms,
        sequence=sequence,
        sample_at_ms=result.sample_at_ms,
        x=result.x,
        y=result.y,
        display=display,
        confidence=result.confidence,
        status=result.status,
        source="camera",
    )


def centroid(landmarks: list[Any], indices: tuple[int, ...]) -> tuple[float, float]:
    return (
        sum(float(landmarks[index].x) for index in indices) / len(indices),
        sum(float(landmarks[index].y) for index in indices) / len(indices),
    )


def eye_relative_position(
    landmarks: list[Any],
    eye_indices: tuple[int, ...],
    iris_center: tuple[float, float],
) -> tuple[float, float]:
    xs = [float(landmarks[index].x) for index in eye_indices]
    ys = [float(landmarks[index].y) for index in eye_indices]
    width = max(max(xs) - min(xs), 1e-6)
    height = max(max(ys) - min(ys), 1e-6)
    return (
        clamp01((iris_center[0] - min(xs)) / width),
        clamp01((iris_center[1] - min(ys)) / height),
    )


def face_geometry(landmarks: list[Any]) -> tuple[float, float, float]:
    points = [landmarks[index] for index in FACE_BOUNDS_INDICES]
    xs = [float(point.x) for point in points]
    ys = [float(point.y) for point in points]
    return (
        clamp01(sum(xs) / len(xs)),
        clamp01(sum(ys) / len(ys)),
        clamp01(max(max(xs) - min(xs), max(ys) - min(ys))),
    )


def head_pose(result: Any) -> tuple[float, float, float]:
    matrices = getattr(result, "facial_transformation_matrixes", None) or []
    if not matrices:
        return 0.0, 0.0, 0.0
    matrix = matrices[0]
    yaw = float(matrix[0][2])
    pitch = -float(matrix[1][2])
    roll = math.atan2(float(matrix[1][0]), float(matrix[0][0]))
    return yaw, pitch, roll


def eye_openness(landmarks: list[Any]) -> float:
    left = openness_for_eye(landmarks, top=159, bottom=145, outer=33, inner=133)
    right = openness_for_eye(landmarks, top=386, bottom=374, outer=362, inner=263)
    return clamp01(((left + right) / 2) / 0.35)


def openness_for_eye(
    landmarks: list[Any],
    *,
    top: int,
    bottom: int,
    outer: int,
    inner: int,
) -> float:
    vertical = distance(point(landmarks[top]), point(landmarks[bottom]))
    horizontal = max(distance(point(landmarks[outer]), point(landmarks[inner])), 1e-6)
    return vertical / horizontal


def iris_jitter(landmarks: list[Any], previous_landmarks: list[Any] | None) -> float:
    if previous_landmarks is None:
        return 0.0
    current_left = centroid(landmarks, LEFT_IRIS_INDICES)
    current_right = centroid(landmarks, RIGHT_IRIS_INDICES)
    previous_left = centroid(previous_landmarks, LEFT_IRIS_INDICES)
    previous_right = centroid(previous_landmarks, RIGHT_IRIS_INDICES)
    return (distance(current_left, previous_left) + distance(current_right, previous_right)) / 2


def face_motion(landmarks: list[Any], previous_landmarks: list[Any] | None) -> float:
    if previous_landmarks is None:
        return 0.0
    current = face_geometry(landmarks)
    previous = face_geometry(previous_landmarks)
    return distance(current[:2], previous[:2]) + abs(current[2] - previous[2])


def point(landmark: Any) -> tuple[float, float]:
    return float(landmark.x), float(landmark.y)


def distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
