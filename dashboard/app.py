"""Локальный дашборд-надстройка над hh-applicant-tool.

Запуск:  .venv\\Scripts\\uvicorn.exe dashboard.app:app --port 8517
или через dashboard.cmd в корне проекта.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import hh
from .login import login_flow
from .runner import HH_TOOL_EXE, runner
from .update import current_version, start_update, update_state, version_info

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="HH Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> HTMLResponse:
    # страница не кешируется, а ссылки на js/css получают номер версии —
    # после обновления браузер гарантированно загрузит свежий код
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{V}}", current_version())
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/status")
def status() -> dict:
    return {
        "token": hh.token_status(),
        "running": runner.running,
        "current_op": runner.label if runner.running else None,
    }


@app.get("/api/version")
def version() -> dict:
    return version_info()


@app.post("/api/update")
def update() -> dict:
    if runner.running:
        raise HTTPException(409, "Дождись окончания текущей операции")
    try:
        start_update()
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"started": True}


@app.get("/api/update/status")
def update_status() -> dict:
    return update_state()


@app.post("/api/login/start")
async def login_start() -> dict:
    if runner.running:
        raise HTTPException(409, "Дождись окончания текущей операции")
    try:
        await login_flow.start()
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"started": True}


@app.post("/api/login/continue")
def login_continue() -> dict:
    try:
        login_flow.proceed()
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/login/cancel")
def login_cancel() -> dict:
    return {"cancelled": login_flow.cancel()}


@app.get("/api/login/status")
def login_status() -> dict:
    return login_flow.status()


@app.post("/api/logout")
def logout() -> dict:
    if runner.running:
        raise HTTPException(409, "Дождись окончания текущей операции")
    try:
        # отзываем токен на стороне hh.ru
        subprocess.run([str(HH_TOOL_EXE), "logout"], timeout=60, capture_output=True)
    except Exception:
        pass  # даже если сервер hh.ru недоступен, локально всё равно выходим
    hh.clear_local_auth()
    return {"ok": True}


@app.get("/api/whoami")
def whoami() -> dict:
    try:
        return hh.get_whoami()
    except Exception as e:  # не авторизован / нет сети / API вернул ошибку
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/stats")
def stats(fresh: bool = False) -> dict:
    return hh.fetch_stats(fresh)


@app.get("/api/resumes")
def resumes() -> list:
    return hh.fetch_resumes()


@app.get("/api/negotiations")
def negotiations(limit: int = 100, fresh: bool = False) -> list:
    return hh.fetch_negotiations(limit, fresh)


@app.get("/api/skipped")
def skipped(limit: int = 100) -> list:
    return hh.fetch_skipped(limit)


class LetterRequest(BaseModel):
    text: str = ""


@app.get("/api/letter")
def get_letter() -> dict:
    return hh.get_letter()


@app.post("/api/letter")
def save_letter(req: LetterRequest) -> dict:
    return hh.save_letter(req.text)


class RunRequest(BaseModel):
    op: str
    params: dict = {}


@app.post("/api/preview")
def preview(req: RunRequest) -> dict:
    try:
        return hh.preview_apply(req.params)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/run")
async def run(req: RunRequest) -> dict:
    try:
        await runner.start(req.op, req.params)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"started": True, "op": req.op}


@app.post("/api/cancel")
def cancel() -> dict:
    return {"cancelled": runner.cancel()}


@app.get("/api/logs")
async def logs() -> StreamingResponse:
    """SSE-поток строк лога текущей (или последней) операции."""

    async def gen():
        idx = 0
        while True:
            while idx < len(runner.lines):
                yield f"data: {json.dumps(runner.lines[idx], ensure_ascii=False)}\n\n"
                idx += 1
            if not runner.running:
                yield f"event: done\ndata: {json.dumps(runner.returncode)}\n\n"
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
