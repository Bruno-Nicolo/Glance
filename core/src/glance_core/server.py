from __future__ import annotations

import asyncio
import os
import shlex
import signal
import socket
import subprocess
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import (
    BackgroundTasks,
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
import uvicorn

from .camera_gaze import (
    CameraGazeError,
    CameraGazeMetrics,
    MediaPipeOpenCVCamera,
    gaze_sample_event_from_mapping,
)
from .diagnostics import (
    DIAGNOSTIC_COMPONENTS,
    DIAGNOSTIC_SEVERITIES,
    DiagnosticLogStore,
)
from .helper_events import (
    HELPER_FRAME_INTERVAL_MS,
    CoreReadyEvent,
    DisplayBounds,
    SyntheticGazePath,
    TrackingStatusEvent,
    now_ms,
)
from .gaze_mapping_contract import GazeInvalidReason, GazeMappingDebug, RawGazeSample, map_gaze_sample
from .calibration_sessions import (
    CalibrationSessionError,
    CalibrationSessionRecord,
    CalibrationSessionStore,
    calibration_display_from_bounds,
    calibration_session_response,
)
from .paths import application_support_dir, runtime_dir
from .security import is_authorized, load_or_create_token
from .ui_contract import (
    CORE_UI_CONTRACT_VERSION,
    ContractError,
    CoreUiStatus,
    HelperInputDebug,
    SettingsValidationError,
    apply_settings_update,
    load_settings,
    save_settings,
)


@dataclass(frozen=True)
class RuntimeState:
    token: str
    port: int
    config_path: Path | None = None
    runtime_path: Path | None = None


class CameraSampleProvider(Protocol):
    metrics: CameraGazeMetrics

    def sample(self) -> RawGazeSample | None:
        pass

    def close(self) -> None:
        pass


class HelperProcess:
    def __init__(self, token: str, port: int, diagnostics: DiagnosticLogStore):
        self.token = token
        self.port = port
        self.diagnostics = diagnostics
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def status(self) -> str:
        if self.process is None:
            return "not-started"
        if self.process.poll() is None:
            return "running"
        return "exited"

    def start(self) -> None:
        if os.environ.get("GLANCE_DISABLE_HELPER") == "1":
            self.diagnostics.record("helper", "info", "Helper launch skipped by GLANCE_DISABLE_HELPER")
            return
        if self.process is not None and self.process.poll() is None:
            return

        repo_root = Path(__file__).resolve().parents[3]
        command = os.environ.get("GLANCE_HELPER_COMMAND")
        args = helper_command_args(repo_root, command)

        env = {
            **os.environ,
            "GLANCE_CORE_URL": f"http://127.0.0.1:{self.port}",
            "GLANCE_CORE_WS_URL": f"ws://127.0.0.1:{self.port}/events",
            "GLANCE_CORE_TOKEN": self.token,
        }

        try:
            self.process = subprocess.Popen(
                args,
                cwd=str(repo_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.diagnostics.record("helper", "info", "Helper process started")
            self._capture_stream("info", self.process.stdout)
            self._capture_stream("warning", self.process.stderr)
        except OSError:
            self.process = None
            self.diagnostics.record("helper", "error", "Helper process failed to start")

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            self.process = None
            return

        self.process.terminate()
        try:
            self.process.wait(timeout=2)
            self.diagnostics.record("helper", "info", "Helper process stopped")
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
            self.diagnostics.record("helper", "warning", "Helper process killed after shutdown timeout")
        finally:
            if self.process.stdout is not None:
                self.process.stdout.close()
            if self.process.stderr is not None:
                self.process.stderr.close()
            self.process = None

    def _capture_stream(self, severity: str, stream: object) -> None:
        if stream is None:
            return

        def read_lines() -> None:
            for line in stream:
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    self.diagnostics.record("helper", helper_output_severity(severity, text), text)

        threading.Thread(target=read_lines, daemon=True).start()


def create_app(
    state: RuntimeState,
    shutdown_callback: Callable[[], None] | None = None,
    camera_factory: Callable[[], CameraSampleProvider] | None = None,
) -> FastAPI:
    synthetic_gaze_path = SyntheticGazePath(display=synthetic_display_bounds())
    settings_path = state.config_path or (application_support_config_path())
    diagnostics = DiagnosticLogStore(settings_path.parent / "logs" / "glance-core.jsonl")
    helper = HelperProcess(token=state.token, port=state.port, diagnostics=diagnostics)
    calibration_store = CalibrationSessionStore(calibration_profile_path(settings_path))
    settings = load_settings(settings_path)
    tracking_state = "stopped"
    previous_tracking_state_before_pause = "stopped"
    camera_state = "stopped"
    camera_error: str | None = None
    camera_provider: CameraSampleProvider | None = None
    previous_camera_output: tuple[float, float] | None = None
    last_camera_gaze: GazeMappingDebug | None = None
    helper_input = HelperInputDebug()
    ui_event_clients: set[WebSocket] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = ensure_runtime_path(state.runtime_path) if state.runtime_path else runtime_dir()
        (runtime / "core.pid").write_text(str(os.getpid()), encoding="utf-8")
        (runtime / "core.port").write_text(str(state.port), encoding="utf-8")
        diagnostics.record("core", "info", "Core runtime started", {"port": state.port})
        helper.start()
        yield
        close_camera_provider(camera_provider)
        helper.stop()
        diagnostics.record("core", "info", "Core runtime stopped")

    app = FastAPI(title="Glance Core", version="0.1.0", lifespan=lifespan)

    def require_auth(authorization: str | None) -> None:
        if not is_authorized(authorization, state.token):
            raise HTTPException(
                status_code=401,
                detail=ContractError(
                    code="unauthorized",
                    message="Missing or invalid bearer token",
                    recoverable=True,
                ).to_response(),
            )

    def current_status() -> CoreUiStatus:
        synthetic_enabled = settings.debug.synthetic_gaze_enabled
        calibrated = calibration_store.profile_id is not None
        camera_active = not synthetic_enabled and tracking_state == "running" and camera_state == "running"
        if not synthetic_enabled and last_camera_gaze is not None and tracking_state == "running":
            gaze = last_camera_gaze
        else:
            gaze = status_gaze_debug(synthetic_enabled=synthetic_enabled, calibrated=calibrated)

        return CoreUiStatus(
            pid=os.getpid() if state.runtime_path is None else None,
            helper_state=helper.status,
            tracking_state=tracking_state,
            input_enabled=tracking_state == "running" and settings.input.space_click_enabled,
            gaze=gaze,
            helper_input=helper_input,
            camera_state=camera_state if not synthetic_enabled else "stopped",
            camera_active=camera_active,
            camera_metrics=(
                camera_provider.metrics.to_json_dict(now_ms=now_ms())
                if not synthetic_enabled and camera_provider is not None
                else None
            ),
            calibration_state=calibration_store.state,
            calibration_profile_id=calibration_store.profile_id,
            error=ContractError(
                code="camera_unavailable",
                message=camera_error,
                recoverable=True,
            )
            if camera_error
            else None,
        )

    def status_gaze_debug(*, synthetic_enabled: bool, calibrated: bool) -> GazeMappingDebug:
        gaze_running = tracking_state == "running" and synthetic_enabled and calibrated
        invalid_reason: GazeInvalidReason | None = None
        if not calibrated:
            invalid_reason = "uncalibrated"
        elif tracking_state != "running":
            invalid_reason = "paused" if tracking_state == "paused" else "tracking-stopped"
        elif not synthetic_enabled:
            invalid_reason = "synthetic-disabled"
        gaze_status = "valid" if gaze_running else "uncalibrated" if invalid_reason == "uncalibrated" else "paused"

        return GazeMappingDebug(
            profile_id=calibration_store.profile_id,
            status=gaze_status,
            confidence=1.0 if gaze_running else 0.0,
            sample_at_ms=now_ms() if gaze_running else None,
            source="synthetic" if synthetic_enabled else "camera",
            smoothing_alpha=settings.tracking.smoothing,
            confidence_threshold=settings.tracking.confidence_threshold,
            invalid_reason=invalid_reason,
        )

    def status_changed_event() -> dict[str, object]:
        return {
            "type": "status.changed",
            "contract_version": CORE_UI_CONTRACT_VERSION,
            "status": current_status().to_json_dict(),
        }

    def ensure_camera_sample_provider() -> CameraSampleProvider:
        nonlocal camera_provider, camera_state, camera_error
        if camera_provider is None:
            camera_provider = (
                camera_factory()
                if camera_factory is not None
                else MediaPipeOpenCVCamera(model_asset_path=camera_model_asset_path())
            )
        camera_state = "running"
        camera_error = None
        return camera_provider

    def camera_sample_to_calibration_sample(sample: RawGazeSample) -> dict[str, object] | None:
        if sample.features is None or sample.quality is None:
            return None
        return {
            "sample_at_ms": sample.sample_at_ms,
            "features": sample.features,
            "quality": sample.quality,
        }

    async def broadcast_status_changed() -> None:
        disconnected: list[WebSocket] = []
        for client in ui_event_clients:
            try:
                await client.send_json(status_changed_event())
            except RuntimeError:
                disconnected.append(client)
        for client in disconnected:
            ui_event_clients.discard(client)

    async def apply_helper_message(payload: dict[str, object]) -> TrackingStatusEvent | None:
        nonlocal camera_provider, camera_state, helper_input, previous_camera_output
        nonlocal tracking_state, previous_tracking_state_before_pause

        message_type = payload.get("type")
        if message_type == "helper.input":
            action = payload.get("action")
            suppressed_reason = payload.get("suppressed_reason")
            if action not in {
                "space-down",
                "space-up",
                "space-click",
                "esc-down",
                "esc-up",
                "pause-started",
                "pause-ended",
            }:
                diagnostics.record("helper", "warning", "Ignored helper input event with unknown action")
                return None
            if suppressed_reason not in {
                None,
                "disabled",
                "paused",
                "permission-denied",
                "repeat",
                "no-cursor",
            }:
                diagnostics.record("helper", "warning", "Ignored helper input event with unknown suppressed reason")
                return None

            paused = helper_input.paused
            response: TrackingStatusEvent | None = None
            if action == "pause-started":
                if tracking_state != "paused":
                    previous_tracking_state_before_pause = tracking_state
                tracking_state = "paused"
                paused = True
                if settings.tracking.pause_behavior == "privacy-low-power":
                    close_camera_provider(camera_provider)
                    camera_provider = None
                    camera_state = "stopped"
                    previous_camera_output = None
                response = TrackingStatusEvent(
                    sent_at_ms=now_ms(),
                    sequence=int(payload.get("sequence", 0)),
                    tracking="paused",
                    overlay="frozen" if settings.tracking.pause_behavior == "fast-recovery" else "hidden",
                    reason="esc-held",
                )
            elif action == "pause-ended":
                tracking_state = previous_tracking_state_before_pause
                paused = False
                response = TrackingStatusEvent(
                    sent_at_ms=now_ms(),
                    sequence=int(payload.get("sequence", 0)),
                    tracking=tracking_state,
                    overlay="visible" if tracking_state == "running" else "hidden",
                    reason="esc-released",
                )

            helper_input = HelperInputDebug(
                latest_action=action,
                latest_suppressed_reason=suppressed_reason,
                paused=paused,
                permissions=helper_input.permissions,
            )
            await broadcast_status_changed()
            diagnostics.record("tracking", "info", f"Helper input updated tracking state to {tracking_state}")
            return response

        if message_type == "helper.permission":
            permission = payload.get("permission")
            state_value = payload.get("state")
            if permission not in {"accessibility", "input-monitoring"}:
                diagnostics.record("helper", "warning", "Ignored helper permission event with unknown permission")
                return None
            if state_value not in {"granted", "denied", "unknown"}:
                diagnostics.record("helper", "warning", "Ignored helper permission event with unknown state")
                return None

            permissions = {**helper_input.permissions, str(permission).replace("-", "_"): state_value}
            helper_input = HelperInputDebug(
                latest_action=helper_input.latest_action,
                latest_suppressed_reason=helper_input.latest_suppressed_reason,
                paused=helper_input.paused,
                permissions=permissions,
            )
            await broadcast_status_changed()
            diagnostics.record("helper", "info", f"Helper permission {permission} is {state_value}")
            return None

        return None

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exception: HTTPException):
        if isinstance(exception.detail, dict) and "error" in exception.detail:
            return JSONResponse(status_code=exception.status_code, content=exception.detail)
        return JSONResponse(
            status_code=exception.status_code,
            content=ContractError(
                code="http_error",
                message=str(exception.detail),
                recoverable=exception.status_code < 500,
            ).to_response(),
        )

    @app.get("/health")
    async def health(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return {
            "status": "ok",
            "contract": "core-ui",
            "contract_version": CORE_UI_CONTRACT_VERSION,
        }

    @app.get("/status")
    async def status(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return current_status().to_json_dict()

    @app.get("/settings")
    async def get_settings(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return settings.to_json_dict()

    @app.put("/settings")
    async def put_settings(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        nonlocal settings
        require_auth(authorization)
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise SettingsValidationError("Settings update must be an object")
            settings = apply_settings_update(settings, payload)
            save_settings(settings_path, settings)
            diagnostics.record("core", "info", "Settings updated")
        except SettingsValidationError as error:
            diagnostics.record("core", "warning", "Rejected invalid settings update", {"error": str(error)})
            return JSONResponse(
                status_code=400,
                content=ContractError(
                    code="invalid_settings",
                    message=str(error),
                    recoverable=True,
                ).to_response(),
            )
        await broadcast_status_changed()
        return settings.to_json_dict()

    @app.post("/controls/start")
    async def start_tracking(authorization: str | None = Header(default=None)):
        nonlocal tracking_state
        require_auth(authorization)
        tracking_state = "running"
        diagnostics.record("tracking", "info", "Tracking started")
        await broadcast_status_changed()
        return current_status().to_json_dict()

    @app.post("/controls/stop")
    async def stop_tracking(authorization: str | None = Header(default=None)):
        nonlocal tracking_state
        require_auth(authorization)
        tracking_state = "stopped"
        diagnostics.record("tracking", "info", "Tracking stopped")
        await broadcast_status_changed()
        return current_status().to_json_dict()

    @app.post("/calibration/sessions")
    async def create_calibration_session(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        nonlocal tracking_state
        require_auth(authorization)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise_calibration_error("invalid_calibration_session", "Calibration request must be an object")

        mode = payload.get("mode")
        if mode not in ("initial-9-point", "validation", "drift-1-point") or payload.get("display_id") != "main":
            raise_calibration_error(
                "invalid_calibration_session",
                "Calibration session requires a supported mode and display_id main",
            )

        display = calibration_display_from_bounds(synthetic_display_bounds())
        try:
            session = calibration_store.create(mode=mode, display=display)
        except CalibrationSessionError as error:
            diagnostics.record("calibration", "warning", "Calibration session rejected", {"error": str(error)})
            raise_calibration_error(error.code, str(error))
        tracking_state = "paused"
        diagnostics.record("calibration", "info", f"Calibration session started: {mode}")
        await broadcast_status_changed()
        return calibration_session_response(session)

    @app.post("/calibration/sessions/{session_id}/samples")
    async def add_calibration_samples(
        session_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        payload = await request.json()
        try:
            session = calibration_store.add_samples(session_id, payload)
        except CalibrationSessionError as error:
            diagnostics.record("calibration", "warning", "Calibration samples rejected", {"error": str(error)})
            raise_calibration_error(error.code, str(error))

        diagnostics.record("calibration", "info", "Calibration samples accepted")
        await broadcast_calibration_changed(session)
        return calibration_session_response(session)

    @app.post("/calibration/sessions/{session_id}/capture")
    async def capture_calibration_samples(
        session_id: str,
        authorization: str | None = Header(default=None),
    ):
        nonlocal camera_state, camera_error
        require_auth(authorization)
        session = calibration_store.require_active(session_id)
        if session.current_target_index >= len(session.targets):
            raise_calibration_error("invalid_calibration_sample", "All targets already have samples")

        samples: list[dict[str, object]] = []
        try:
            provider = ensure_camera_sample_provider()
            for _index in range(15):
                sample = await asyncio.to_thread(provider.sample)
                calibration_sample = (
                    camera_sample_to_calibration_sample(sample)
                    if sample is not None
                    else None
                )
                if calibration_sample is not None:
                    samples.append(calibration_sample)
                await asyncio.sleep(0.05)
        except CameraGazeError as error:
            camera_state = "error"
            camera_error = str(error)
            diagnostics.record("camera", "error", "Camera calibration capture failed", {"error": str(error)})
            await broadcast_status_changed()
            raise HTTPException(
                status_code=400,
                detail=ContractError(
                    code="camera_unavailable",
                    message=str(error),
                    recoverable=True,
                ).to_response(),
            )

        if not samples:
            diagnostics.record("camera", "warning", "Camera calibration capture produced no samples")
            raise_calibration_error("calibration_failed", "Unable to collect camera calibration samples")

        target = session.targets[session.current_target_index]
        try:
            session = calibration_store.add_samples(
                session_id,
                {"target_id": target.id, "samples": samples},
            )
        except CalibrationSessionError as error:
            diagnostics.record("calibration", "warning", "Captured calibration samples rejected", {"error": str(error)})
            raise_calibration_error(error.code, str(error))

        diagnostics.record("camera", "info", "Camera calibration samples captured", {"sample_count": len(samples)})
        await broadcast_calibration_changed(session)
        await broadcast_status_changed()
        return calibration_session_response(session)

    @app.post("/calibration/sessions/{session_id}/complete")
    async def complete_calibration_session(
        session_id: str,
        authorization: str | None = Header(default=None),
    ):
        nonlocal tracking_state
        require_auth(authorization)
        try:
            session, profile, validation = calibration_store.complete(session_id)
        except CalibrationSessionError as error:
            diagnostics.record("calibration", "warning", "Calibration completion failed", {"error": str(error)})
            raise_calibration_error(error.code, str(error))
        tracking_state = "stopped"
        diagnostics.record("calibration", "info", f"Calibration session completed: {session.mode}")
        await broadcast_status_changed()
        return {
            "contract_version": 1,
            "session_id": session.session_id,
            "state": "complete",
            "mode": session.mode,
            "profile_id": profile.profile_id if profile else None,
            "validation": validation.to_json_dict() if validation is not None else None,
            "status": current_status().to_json_dict(),
            "error": None,
        }

    @app.delete("/calibration/sessions/{session_id}")
    async def cancel_calibration_session(
        session_id: str,
        authorization: str | None = Header(default=None),
    ):
        nonlocal tracking_state
        require_auth(authorization)
        try:
            session = calibration_store.cancel(session_id)
        except CalibrationSessionError as error:
            diagnostics.record("calibration", "warning", "Calibration cancellation failed", {"error": str(error)})
            raise_calibration_error(error.code, str(error))
        tracking_state = "stopped"
        diagnostics.record("calibration", "info", "Calibration session cancelled")
        await broadcast_status_changed()
        return {
            "contract_version": 1,
            "session_id": session.session_id,
            "state": "cancelled",
            "status": current_status().to_json_dict(),
            "error": None,
        }

    async def broadcast_calibration_changed(session: CalibrationSessionRecord) -> None:
        event = {
            "type": "calibration.changed",
            "contract_version": 1,
            "session_id": session.session_id,
            "state": session.state,
            "target_id": (
                session.targets[session.current_target_index].id
                if session.current_target_index < len(session.targets)
                else None
            ),
            "completed_targets": min(session.current_target_index, len(session.targets)),
            "total_targets": len(session.targets),
            "error": None,
        }
        disconnected: list[WebSocket] = []
        for client in ui_event_clients:
            try:
                await client.send_json(event)
            except RuntimeError:
                disconnected.append(client)
        for client in disconnected:
            ui_event_clients.discard(client)

    @app.post("/shutdown")
    async def shutdown(
        background_tasks: BackgroundTasks,
        authorization: str | None = Header(default=None),
    ):
        nonlocal camera_provider
        require_auth(authorization)
        diagnostics.record("core", "info", "Full runtime shutdown requested")
        close_camera_provider(camera_provider)
        camera_provider = None
        helper.stop()
        background_tasks.add_task(shutdown_callback or request_process_shutdown)
        return JSONResponse(
            status_code=202,
            content={
                "status": "shutting-down",
                "scope": "full-runtime",
                "ui_should_exit": True,
            },
        )

    @app.websocket("/events")
    async def events(websocket: WebSocket):
        nonlocal camera_provider, camera_state, camera_error, previous_camera_output, last_camera_gaze
        authorization = websocket.headers.get("authorization")
        if not is_authorized(authorization, state.token):
            await websocket.close(code=1008)
            return

        await websocket.accept()
        try:
            sequence = 0
            await websocket.send_json(
                CoreReadyEvent(sent_at_ms=now_ms(), sequence=sequence).to_json_dict()
            )
            sequence += 1
            await websocket.send_json(
                TrackingStatusEvent(
                    sent_at_ms=now_ms(),
                    sequence=sequence,
                    tracking="running" if tracking_state == "running" else "stopped",
                    overlay="visible" if tracking_state == "running" else "hidden",
                    reason="synthetic-startup" if settings.debug.synthetic_gaze_enabled else "camera-startup",
                ).to_json_dict()
            )
            sequence += 1
            while True:
                try:
                    helper_message = await asyncio.wait_for(websocket.receive_json(), timeout=0.001)
                    if isinstance(helper_message, dict):
                        response = await apply_helper_message(helper_message)
                        if response is not None:
                            await websocket.send_json(response.to_json_dict())
                except TimeoutError:
                    pass
                sent_at_ms = now_ms()
                if settings.debug.synthetic_gaze_enabled:
                    await websocket.send_json(
                        synthetic_gaze_path.sample(
                            sequence=sequence,
                            sent_at_ms=sent_at_ms,
                        ).to_json_dict()
                    )
                    sequence += 1
                elif tracking_state == "running":
                    try:
                        provider = ensure_camera_sample_provider()
                        sample = await asyncio.to_thread(provider.sample)
                    except CameraGazeError as error:
                        camera_state = "error"
                        camera_error = str(error)
                        diagnostics.record("camera", "error", "Camera stream failed", {"error": str(error)})
                        await websocket.send_json(
                            TrackingStatusEvent(
                                sent_at_ms=sent_at_ms,
                                sequence=sequence,
                                tracking="paused",
                                overlay="frozen",
                                reason="camera-unavailable",
                            ).to_json_dict()
                        )
                        sequence += 1
                        await asyncio.sleep(1)
                        continue

                    if sample is not None:
                        mapped = map_gaze_sample(
                            sample,
                            profile=calibration_store.profile,
                            previous_output=previous_camera_output,
                            smoothing_alpha=settings.tracking.smoothing,
                            confidence_threshold=settings.tracking.confidence_threshold,
                        )
                        if mapped.status in {"valid", "low-confidence"}:
                            previous_camera_output = (mapped.x, mapped.y)
                        last_camera_gaze = mapped.debug()
                        event = gaze_sample_event_from_mapping(
                            mapped,
                            display=synthetic_display_bounds(),
                            sent_at_ms=sent_at_ms,
                            sequence=sequence,
                        )
                        await websocket.send_json(event.to_json_dict())
                        camera_provider.metrics.record_sample_emitted()
                        sequence += 1
                else:
                    camera_state = "stopped"
                await asyncio.sleep(HELPER_FRAME_INTERVAL_MS / 1000)
        except WebSocketDisconnect:
            return

    @app.websocket("/ui/events")
    async def ui_events(websocket: WebSocket):
        authorization = websocket.headers.get("authorization")
        if not is_authorized(authorization, state.token):
            await websocket.close(code=1008)
            return

        await websocket.accept()
        ui_event_clients.add(websocket)
        await websocket.send_json(
            {
                "type": "ui.ready",
                "contract_version": CORE_UI_CONTRACT_VERSION,
            }
        )
        await websocket.send_json(status_changed_event())
        try:
            while True:
                await asyncio.sleep(60)
        except WebSocketDisconnect:
            return
        finally:
            ui_event_clients.discard(websocket)

    @app.get("/diagnostics/logs")
    async def get_diagnostic_logs(
        authorization: str | None = Header(default=None),
        component: str | None = None,
        limit: int = 200,
    ):
        require_auth(authorization)
        if component is not None and component not in DIAGNOSTIC_COMPONENTS:
            raise HTTPException(
                status_code=400,
                detail=ContractError(
                    code="invalid_diagnostics_filter",
                    message=f"Unknown diagnostic component: {component}",
                    recoverable=True,
                ).to_response(),
            )
        return diagnostics.to_response(component=component, limit=limit)

    @app.post("/diagnostics/logs")
    async def post_diagnostic_log(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise_diagnostics_error("Diagnostic log entry must be an object")
        component = payload.get("component")
        severity = payload.get("severity", "info")
        message = payload.get("message")
        details = payload.get("details")
        if component not in DIAGNOSTIC_COMPONENTS:
            raise_diagnostics_error("Diagnostic log entry requires a known component")
        if severity not in DIAGNOSTIC_SEVERITIES:
            raise_diagnostics_error("Diagnostic log entry requires a known severity")
        if not isinstance(message, str) or message.strip() == "":
            raise_diagnostics_error("Diagnostic log entry requires a non-empty message")
        if details is not None and not isinstance(details, dict):
            raise_diagnostics_error("Diagnostic log entry details must be an object")
        entry = diagnostics.record(component, severity, message, details)
        return {
            "contract_version": CORE_UI_CONTRACT_VERSION,
            "entry": entry.to_json_dict(),
        }

    return app


def application_support_config_path() -> Path:
    return application_support_dir() / "config.json"


def calibration_profile_path(config_path: Path) -> Path:
    return config_path.parent / "calibration.json"


def ensure_runtime_path(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def request_process_shutdown() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


def synthetic_display_bounds() -> DisplayBounds:
    return DisplayBounds(
        id=os.environ.get("GLANCE_SYNTHETIC_DISPLAY_ID", "main"),
        x=float(os.environ.get("GLANCE_SYNTHETIC_DISPLAY_X", "0")),
        y=float(os.environ.get("GLANCE_SYNTHETIC_DISPLAY_Y", "0")),
        width=float(os.environ.get("GLANCE_SYNTHETIC_DISPLAY_WIDTH", "1440")),
        height=float(os.environ.get("GLANCE_SYNTHETIC_DISPLAY_HEIGHT", "900")),
        scale=float(os.environ.get("GLANCE_SYNTHETIC_DISPLAY_SCALE", "2")),
    )


def camera_model_asset_path() -> Path:
    configured = os.environ.get("GLANCE_FACE_LANDMARKER_MODEL_PATH")
    if configured:
        return Path(configured)
    return application_support_dir() / "models" / "face_landmarker.task"


def close_camera_provider(provider: CameraSampleProvider | None) -> None:
    if provider is not None:
        provider.close()


def raise_calibration_error(code: str, message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=ContractError(code=code, message=message, recoverable=True).to_response(),
    )


def raise_diagnostics_error(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=ContractError(
            code="invalid_diagnostic_log",
            message=message,
            recoverable=True,
        ).to_response(),
    )


def helper_output_severity(default_severity: str, message: str) -> str:
    lowered = message.lower()
    if "error:" in lowered or "failed" in lowered:
        return "error"
    if "warning:" in lowered:
        return "warning"
    if (
        "build complete" in lowered
        or "building for debugging" in lowered
        or "planning build" in lowered
        or "write swift-version" in lowered
    ):
        return "info"
    return default_severity


def helper_command_args(repo_root: Path, command: str | None = None) -> list[str]:
    if command:
        return shlex.split(command)
    return [str(repo_root / "native" / "macos-helper" / "scripts" / "run-dev-app.sh")]


def find_available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run() -> None:
    runtime = runtime_dir()
    token = load_or_create_token(runtime / "core.token")
    port = int(os.environ.get("GLANCE_CORE_PORT") or find_available_port())

    config = uvicorn.Config(
        create_app(RuntimeState(token=token, port=port)),
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    server.run()
