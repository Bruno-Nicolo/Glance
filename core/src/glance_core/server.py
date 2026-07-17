from __future__ import annotations

import os
import shlex
import signal
import socket
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect

from .paths import runtime_dir
from .security import is_authorized, load_or_create_token


@dataclass(frozen=True)
class RuntimeState:
    token: str
    port: int


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


def create_app(state: RuntimeState) -> FastAPI:
    helper = HelperProcess(token=state.token, port=state.port)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = runtime_dir()
        (runtime / "core.pid").write_text(str(os.getpid()), encoding="utf-8")
        (runtime / "core.port").write_text(str(state.port), encoding="utf-8")
        helper.start()
        yield
        helper.stop()

    app = FastAPI(title="Glance Core", version="0.1.0", lifespan=lifespan)

    def require_auth(authorization: str | None) -> None:
        if not is_authorized(authorization, state.token):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    async def health(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return {"status": "ok"}

    @app.get("/status")
    async def status(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return {
            "core": "running",
            "helper": helper.status,
            "tracking": "stopped",
        }

    @app.post("/shutdown")
    async def shutdown(
        background_tasks: BackgroundTasks,
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        background_tasks.add_task(os.kill, os.getpid(), signal.SIGTERM)
        return {"status": "shutting-down"}

    @app.websocket("/events")
    async def events(websocket: WebSocket):
        authorization = websocket.headers.get("authorization")
        if not is_authorized(authorization, state.token):
            await websocket.close(code=1008)
            return

        await websocket.accept()
        try:
            await websocket.send_json({"type": "core.ready"})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            return

    return app


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
