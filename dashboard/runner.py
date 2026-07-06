"""Запуск операций hh-applicant-tool сабпроцессом со стримом логов.

Одновременно выполняется не больше одной операции — так же работает и сама
утилита (лимиты hh.ru всё равно не дают параллелить).
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

PROJECT_DIR = Path(__file__).resolve().parent.parent
HH_TOOL_EXE = PROJECT_DIR / ".venv" / "Scripts" / "hh-applicant-tool.exe"


def build_argv(op: str, params: dict[str, Any]) -> list[str]:
    """Собирает argv для CLI из параметров формы. Неизвестные операции — ошибка."""
    argv = [str(HH_TOOL_EXE), "-v"]  # -v: INFO-логи, чтобы был виден прогресс

    if op == "authorize":
        # -m: пользователь входит сам в открывшемся окне браузера,
        # утилита лишь перехватывает OAuth-токен
        argv += ["authorize", "-m"]
    elif op == "apply":
        argv.append("apply-vacancies")
        if params.get("resume_id"):
            argv += ["--resume-id", str(params["resume_id"])]
        if params.get("search"):
            argv += ["--search", str(params["search"])]
        if params.get("salary"):
            argv += ["--salary", str(int(params["salary"]))]
        if params.get("only_with_salary"):
            argv.append("--only-with-salary")
        if params.get("max_responses"):
            argv += ["--max-responses", str(int(params["max_responses"]))]
        if params.get("skip_tests"):
            argv.append("--skip-tests")
        if params.get("dry_run"):
            argv.append("--dry-run")
    elif op == "update":
        argv.append("update-resumes")
    elif op == "whoami":
        argv.append("whoami")
    else:
        raise ValueError(f"Неизвестная операция: {op}")

    return argv


class Runner:
    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._pump_task: asyncio.Task | None = None
        self.lines: list[str] = []
        self.label: str | None = None
        self.returncode: int | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, op: str, params: dict[str, Any]) -> None:
        if self.running:
            raise RuntimeError("Операция уже выполняется")

        argv = build_argv(op, params)
        self.lines = [f"$ {' '.join(argv[1:])}"]
        self.label = op
        self.returncode = None

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            env=env,
        )
        self._pump_task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        assert self._proc and self._proc.stdout
        async for raw in self._proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            self.lines.append(ANSI_RE.sub("", line))
        self.returncode = await self._proc.wait()
        self.lines.append(
            f"--- завершено (код {self.returncode}) ---"
            if self.returncode == 0
            else f"--- ошибка (код {self.returncode}) ---"
        )

    def cancel(self) -> bool:
        if not self.running:
            return False
        self._proc.terminate()
        return True


runner = Runner()
