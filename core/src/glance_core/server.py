from __future__ import annotations

import asyncio
import os
import shlex
import signal
import socket
import subprocess
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

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

from .helper_events import (
    HELPER_FRAME_INTERVAL_MS,
    CoreReadyEvent,
    DisplayBounds,
    SyntheticGazePath,
    TrackingStatusEvent,
    now_ms,
)
from .paths import application_support_dir, runtime_dir
from .security import is_authorized, load_or_create_token
from .ui_contract import (
    CORE_UI_CONTRACT_VERSION,
    ContractError,
    CoreUiStatus,
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


class HelperProcess:
    def __init__(self, token: str, port: int):
        self.token = token
        self.port = port
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
            return
        if self.process is not None and self.process.poll() is None:
            return

        repo_root = Path(__file__).resolve().parents[3]
        command = os.environ.get("GLANCE_HELPER_COMMAND")
        args = shlex.split(command) if command else [
            "swift",
            "run",
            "--package-path",
            str(repo_root / "native" / "macos-helper"),
            "GlanceHelper",
        ]

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
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self.process = None

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return

        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()


def create_app(
    state: RuntimeState,
    shutdown_callback: Callable[[], None] | None = None,
) -> FastAPI:
    helper = HelperProcess(token=state.token, port=state.port)
    synthetic_gaze_path = SyntheticGazePath(display=synthetic_display_bounds())
    settings_path = state.config_path or (application_support_config_path())
    settings = load_settings(settings_path)
    tracking_state = "stopped"
    ui_event_clients: set[WebSocket] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = ensure_runtime_path(state.runtime_path) if state.runtime_path else runtime_dir()
        (runtime / "core.pid").write_text(str(os.getpid()), encoding="utf-8")
        (runtime / "core.port").write_text(str(state.port), encoding="utf-8")
        helper.start()
        yield
        helper.stop()

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
        return CoreUiStatus(
            pid=os.getpid() if state.runtime_path is None else None,
            helper_state=helper.status,
            tracking_state=tracking_state,
            input_enabled=tracking_state == "running" and settings.input.space_click_enabled,
        )

    def status_changed_event() -> dict[str, object]:
        return {
            "type": "status.changed",
            "contract_version": CORE_UI_CONTRACT_VERSION,
            "status": current_status().to_json_dict(),
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
        except SettingsValidationError as error:
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
        await broadcast_status_changed()
        return current_status().to_json_dict()

    @app.post("/controls/stop")
    async def stop_tracking(authorization: str | None = Header(default=None)):
        nonlocal tracking_state
        require_auth(authorization)
        tracking_state = "stopped"
        await broadcast_status_changed()
        return current_status().to_json_dict()

    @app.post("/shutdown")
    async def shutdown(
        background_tasks: BackgroundTasks,
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
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
                    tracking="running",
                    overlay="visible",
                    reason="synthetic-startup",
                ).to_json_dict()
            )
            sequence += 1
            while True:
                sent_at_ms = now_ms()
                await websocket.send_json(
                    synthetic_gaze_path.sample(
                        sequence=sequence,
                        sent_at_ms=sent_at_ms,
                    ).to_json_dict()
                )
                sequence += 1
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

    return app


def application_support_config_path() -> Path:
    return application_support_dir() / "config.json"


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
