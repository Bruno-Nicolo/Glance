from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

from .gaze_mapping_contract import GazeMappingDebug

CORE_UI_CONTRACT_VERSION = 1

PauseBehavior = Literal["fast-recovery", "privacy-low-power"]
CoreState = Literal["starting", "running", "shutting-down", "error"]
HelperState = Literal["not-started", "running", "exited", "error"]
CameraState = Literal["stopped", "starting", "running", "error"]
TrackingState = Literal["stopped", "running", "paused", "error"]
CalibrationState = Literal["missing", "in-progress", "valid", "error"]


@dataclass(frozen=True, kw_only=True)
class ContractError:
    code: str
    message: str
    recoverable: bool

    def to_response(self) -> dict[str, Any]:
        return {"error": asdict(self)}


@dataclass(frozen=True, kw_only=True)
class TrackingSettings:
    pause_behavior: PauseBehavior = "fast-recovery"
    confidence_threshold: float = 0.6
    smoothing: float = 0.5


@dataclass(frozen=True, kw_only=True)
class InputSettings:
    space_click_enabled: bool = True


@dataclass(frozen=True, kw_only=True)
class DebugSettings:
    synthetic_gaze_enabled: bool = True


@dataclass(frozen=True, kw_only=True)
class CoreUiSettings:
    contract_version: int = CORE_UI_CONTRACT_VERSION
    tracking: TrackingSettings = TrackingSettings()
    input: InputSettings = InputSettings()
    debug: DebugSettings = DebugSettings()

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class CoreUiStatus:
    helper_state: HelperState
    tracking_state: TrackingState
    input_enabled: bool
    gaze: GazeMappingDebug
    pid: int | None = None
    camera_state: CameraState = "stopped"
    camera_active: bool = False
    camera_metrics: dict[str, object] | None = None
    calibration_state: CalibrationState = "missing"
    calibration_profile_id: str | None = None
    error: ContractError | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CORE_UI_CONTRACT_VERSION,
            "core": {"state": "running", "pid": self.pid},
            "helper": {"state": self.helper_state},
            "camera": {
                "state": self.camera_state,
                "active": self.camera_active,
                "metrics": self.camera_metrics,
            },
            "tracking": {
                "state": self.tracking_state,
                "input_enabled": self.input_enabled,
            },
            "gaze": self.gaze.to_json_dict(),
            "calibration": {
                "state": self.calibration_state,
                "profile_id": self.calibration_profile_id,
            },
            "ui": {"runtime_critical": False},
            "error": asdict(self.error) if self.error else None,
        }


class SettingsValidationError(ValueError):
    pass


def load_settings(config_path: Path) -> CoreUiSettings:
    if not config_path.exists():
        return CoreUiSettings()

    with config_path.open("r", encoding="utf-8") as file:
        stored = json.load(file)

    return apply_settings_update(CoreUiSettings(), stored)


def save_settings(config_path: Path, settings: CoreUiSettings) -> None:
    config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as file:
        json.dump(settings.to_json_dict(), file, indent=2, sort_keys=True)
        file.write("\n")


def apply_settings_update(
    current: CoreUiSettings,
    update: dict[str, Any],
) -> CoreUiSettings:
    allowed_top_level = {"tracking", "input", "debug"}
    for key in update:
        if key not in allowed_top_level:
            raise SettingsValidationError(f"Unknown settings field: {key}")

    tracking = current.tracking
    if "tracking" in update:
        tracking_update = _object(update["tracking"], "tracking")
        tracking = _update_tracking_settings(tracking, tracking_update)

    input_settings = current.input
    if "input" in update:
        input_update = _object(update["input"], "input")
        input_settings = _update_input_settings(input_settings, input_update)

    debug = current.debug
    if "debug" in update:
        debug_update = _object(update["debug"], "debug")
        debug = _update_debug_settings(debug, debug_update)

    return replace(current, tracking=tracking, input=input_settings, debug=debug)


def _update_tracking_settings(
    current: TrackingSettings,
    update: dict[str, Any],
) -> TrackingSettings:
    allowed = {"pause_behavior", "confidence_threshold", "smoothing"}
    _reject_unknown("tracking", update, allowed)

    next_settings = current
    if "pause_behavior" in update:
        pause_behavior = update["pause_behavior"]
        if pause_behavior not in ("fast-recovery", "privacy-low-power"):
            raise SettingsValidationError("tracking.pause_behavior must be fast-recovery or privacy-low-power")
        next_settings = replace(next_settings, pause_behavior=pause_behavior)

    if "confidence_threshold" in update:
        next_settings = replace(
            next_settings,
            confidence_threshold=_bounded_float(
                update["confidence_threshold"],
                "tracking.confidence_threshold",
            ),
        )

    if "smoothing" in update:
        next_settings = replace(
            next_settings,
            smoothing=_bounded_float(update["smoothing"], "tracking.smoothing"),
        )

    return next_settings


def _update_input_settings(current: InputSettings, update: dict[str, Any]) -> InputSettings:
    allowed = {"space_click_enabled"}
    _reject_unknown("input", update, allowed)
    if "space_click_enabled" not in update:
        return current
    if not isinstance(update["space_click_enabled"], bool):
        raise SettingsValidationError("input.space_click_enabled must be a boolean")
    return replace(current, space_click_enabled=update["space_click_enabled"])


def _update_debug_settings(current: DebugSettings, update: dict[str, Any]) -> DebugSettings:
    allowed = {"synthetic_gaze_enabled"}
    _reject_unknown("debug", update, allowed)
    if "synthetic_gaze_enabled" not in update:
        return current
    if not isinstance(update["synthetic_gaze_enabled"], bool):
        raise SettingsValidationError("debug.synthetic_gaze_enabled must be a boolean")
    return replace(current, synthetic_gaze_enabled=update["synthetic_gaze_enabled"])


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SettingsValidationError(f"{path} must be an object")
    return value


def _reject_unknown(path: str, update: dict[str, Any], allowed: set[str]) -> None:
    for key in update:
        if key not in allowed:
            raise SettingsValidationError(f"Unknown settings field: {path}.{key}")


def _bounded_float(value: Any, path: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise SettingsValidationError(f"{path} must be a number")
    number = float(value)
    if number < 0 or number > 1:
        raise SettingsValidationError(f"{path} must be between 0 and 1")
    return number
