from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

HELPER_EVENT_VERSION = 1
HELPER_EVENT_MIN_VERSION = 1
HELPER_TARGET_FPS = 30
HELPER_FRAME_INTERVAL_MS = round(1000 / HELPER_TARGET_FPS)
HELPER_STALE_SAMPLE_MS = 150

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
