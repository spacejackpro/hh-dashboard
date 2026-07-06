"""Локальный дашборд-надстройка над hh-applicant-tool.

Запуск:  .venv\\Scripts\\uvicorn.exe dashboard.app:app --port 8517
или через dashboard.cmd в корне проекта.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import hh
from .runner import runner
from .update import version_info

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="HH Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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


@app.get("/api/whoami")
def whoami() -> dict:
    try:
        return hh.get_whoami()
    except Exception as e:  # не авторизован / нет сети / API вернул ошибку
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/stats")
def stats() -> dict:
    return hh.fetch_stats()


@app.get("/api/resumes")
def resumes() -> list:
    return hh.fetch_resumes()


@app.get("/api/negotiations")
def negotiations(limit: int = 100) -> list:
    return hh.fetch_negotiations(limit)


@app.get("/api/skipped")
def skipped(limit: int = 100) -> list:
    return hh.fetch_skipped(limit)


class RunRequest(BaseModel):
    op: str
    params: dict = {}


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
