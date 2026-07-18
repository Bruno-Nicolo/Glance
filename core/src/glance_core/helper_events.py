from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from math import cos, sin, tau
from typing import Any, Literal

HELPER_EVENT_VERSION = 1
HELPER_EVENT_MIN_VERSION = 1
HELPER_TARGET_FPS = 30
HELPER_FRAME_INTERVAL_MS = round(1000 / HELPER_TARGET_FPS)
HELPER_STALE_SAMPLE_MS = 150
SYNTHETIC_GAZE_LOOP_SECONDS = 4
SYNTHETIC_GAZE_HORIZONTAL_RADIUS_RATIO = 0.32
SYNTHETIC_GAZE_VERTICAL_RADIUS_RATIO = 0.28

CoordinateSpace = Literal["display-logical-top-left"]
GazeSource = Literal["synthetic", "camera"]
GazeStatus = Literal[
    "valid",
    "low-confidence",
    "face-lost",
    "uncalibrated",
    "paused",
]
TrackingState = Literal["running", "paused", "stopped"]
OverlayState = Literal["visible", "hidden", "frozen"]
HelperInputAction = Literal[
    "space-down",
    "space-up",
    "space-click",
    "esc-down",
    "esc-up",
    "pause-started",
    "pause-ended",
]
HelperInputSuppressedReason = Literal[
    "disabled",
    "paused",
    "permission-denied",
    "repeat",
    "no-cursor",
]
HelperPermissionName = Literal["accessibility", "input-monitoring"]
HelperPermissionState = Literal["granted", "denied", "unknown"]
HelperPermissionRequirement = Literal["space-click", "esc-pause"]


def now_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True, kw_only=True)
class DisplayBounds:
    id: str
    x: float
    y: float
    width: float
    height: float
    scale: float
    coordinate_space: CoordinateSpace = "display-logical-top-left"


@dataclass(frozen=True, kw_only=True)
class HelperEvent:
    type: str
    sent_at_ms: int
    sequence: int
    version: int = HELPER_EVENT_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class CoreReadyEvent(HelperEvent):
    type: Literal["core.ready"] = "core.ready"
    min_version: int = HELPER_EVENT_MIN_VERSION
    target_fps: int = HELPER_TARGET_FPS
    stale_sample_ms: int = HELPER_STALE_SAMPLE_MS


@dataclass(frozen=True, kw_only=True)
class GazeSampleEvent(HelperEvent):
    sample_at_ms: int
    x: float
    y: float
    display: DisplayBounds
    confidence: float
    status: GazeStatus = "valid"
    source: GazeSource = "synthetic"
    type: Literal["gaze.sample"] = "gaze.sample"


@dataclass(frozen=True, kw_only=True)
class TrackingStatusEvent(HelperEvent):
    tracking: TrackingState = "stopped"
    overlay: OverlayState = "hidden"
    reason: str | None = None
    type: Literal["tracking.status"] = "tracking.status"


@dataclass(frozen=True, kw_only=True)
class CursorPoint:
    x: float
    y: float
    display: DisplayBounds


@dataclass(frozen=True, kw_only=True)
class HelperInputEvent(HelperEvent):
    action: HelperInputAction
    cursor: CursorPoint | None = None
    suppressed_reason: HelperInputSuppressedReason | None = None
    type: Literal["helper.input"] = "helper.input"


@dataclass(frozen=True, kw_only=True)
class HelperPermissionEvent(HelperEvent):
    permission: HelperPermissionName
    state: HelperPermissionState
    required_for: list[HelperPermissionRequirement]
    recoverable: bool = True
    type: Literal["helper.permission"] = "helper.permission"


@dataclass(frozen=True)
class SyntheticGazePath:
    display: DisplayBounds
    frames_per_loop: int = HELPER_TARGET_FPS * SYNTHETIC_GAZE_LOOP_SECONDS

    def sample(self, *, sequence: int, sent_at_ms: int) -> GazeSampleEvent:
        progress = (sequence % self.frames_per_loop) / self.frames_per_loop
        center_x = self.display.x + (self.display.width / 2)
        center_y = self.display.y + (self.display.height / 2)
        radius_x = self.display.width * SYNTHETIC_GAZE_HORIZONTAL_RADIUS_RATIO
        radius_y = self.display.height * SYNTHETIC_GAZE_VERTICAL_RADIUS_RATIO

        return GazeSampleEvent(
            sent_at_ms=sent_at_ms,
            sequence=sequence,
            sample_at_ms=sent_at_ms,
            x=center_x + (cos(progress * tau) * radius_x),
            y=center_y + (sin(progress * tau) * radius_y),
            display=self.display,
            confidence=1.0,
            status="valid",
            source="synthetic",
        )
