"""Запуск операций hh-applicant-tool сабпроцессом со стримом логов.

Одновременно выполняется не больше одной операции — так же работает и сама
утилита (лимиты hh.ru всё равно не дают параллелить).
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from .hh import build_search_text, letter_file
from .paths import HH_TOOL_EXE, profile_cli_id

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# признаки того, что не удалось достучаться до hh.ru (нет сети / нужен VPN)
NETWORK_ERROR_MARKERS = (
    "NameResolutionError",
    "Failed to resolve",
    "Max retries exceeded",
    "Failed to establish a new connection",
    "Connection refused",
    "ConnectionError",
    "Connection aborted",
    "Read timed out",
    "timed out",
)
NETWORK_HINT = (
    "--- Похоже, нет связи с hh.ru. Проверь: открывается ли hh.ru в браузере? "
    "Если нет — дело в интернете или (если ты не в России) нужен VPN. "
    "Если открывается — просто запусти рассылку ещё раз. ---"
)


def build_argv(op: str, params: dict[str, Any]) -> list[str]:
    """Собирает argv для CLI из параметров формы. Неизвестные операции — ошибка."""
    # -v: INFO-логи; --profile-id направляет операцию в папку активного аккаунта
    argv = [str(HH_TOOL_EXE), "-v", "--profile-id", profile_cli_id()]

    if op == "authorize":
        # -m: пользователь входит сам в открывшемся окне браузера,
        # утилита лишь перехватывает OAuth-токен
        argv += ["authorize", "-m"]
    elif op == "apply":
        argv.append("apply-vacancies")
        if params.get("resume_id"):
            argv += ["--resume-id", str(params["resume_id"])]
        search = build_search_text(params.get("keywords") or [])
        if search:
            argv += ["--search", search]
        if params.get("search_fields"):
            argv += ["--search-field", *[str(f) for f in params["search_fields"]]]
        if params.get("areas"):
            argv += ["--area", *[str(a) for a in params["areas"]]]
        if params.get("salary"):
            argv += ["--salary", str(int(params["salary"]))]
        if params.get("only_with_salary"):
            argv.append("--only-with-salary")
        if letter_file().exists():
            argv += ["--letter-file", str(letter_file())]
        if params.get("force_message"):
            argv.append("--force-message")
        # ВНИМАНИЕ: --max-responses движку не передаём — у автора это
        # нереализованная заглушка с другим смыслом. Лимит откликов
        # обеспечивает Runner: считает строки «Отправили отклик» в логе
        # и останавливает процесс (см. _pump).
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
        self._response_limit: int | None = None
        self._response_count = 0
        self._stop_reason: str | None = None
        # своя рассылка (op == "apply") выполняется задачей, а не процессом
        self._apply_task: asyncio.Task | None = None
        self._cancel_flag = False

    @property
    def running(self) -> bool:
        if self._apply_task is not None and not self._apply_task.done():
            return True
        return self._proc is not None and self._proc.returncode is None

    async def start(self, op: str, params: dict[str, Any]) -> None:
        if self.running:
            raise RuntimeError("Операция уже выполняется")

        # рассылку откликов ведём своим кодом — ради общего стоп-листа
        if op == "apply":
            self.lines = ["$ рассылка откликов"]
            self.label = op
            self.returncode = None
            self._cancel_flag = False
            self._apply_task = asyncio.create_task(self._run_apply(params))
            return

        argv = build_argv(op, params)
        self.lines = [f"$ {' '.join(argv[1:])}"]
        self.label = op
        self.returncode = None
        self._response_count = 0
        self._stop_reason = None
        self._response_limit = None

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
        network_hint_shown = False
        async for raw in self._proc.stdout:
            line = ANSI_RE.sub(
                "", raw.decode("utf-8", errors="replace").rstrip()
            )
            self.lines.append(line)
            if not network_hint_shown and any(
                m in line for m in NETWORK_ERROR_MARKERS
            ):
                network_hint_shown = True
                self.lines.append(NETWORK_HINT)
            if (
                self._response_limit
                and self._stop_reason is None
                and "Отправили отклик" in line
            ):
                self._response_count += 1
                if self._response_count >= self._response_limit:
                    self._stop_reason = (
                        f"лимит {self._response_limit} откликов достигнут"
                    )
                    self.lines.append(
                        f"--- {self._stop_reason}, останавливаю рассылку ---"
                    )
                    self._proc.terminate()
        self.returncode = await self._proc.wait()
        if self._stop_reason:
            self.lines.append(f"--- остановлено: {self._stop_reason} ---")
        elif self.returncode == 0:
            self.lines.append("--- завершено (код 0) ---")
        else:
            self.lines.append(f"--- ошибка (код {self.returncode}) ---")

    async def _run_apply(self, params: dict[str, Any]) -> None:
        from . import apply

        try:
            await apply.run_apply(
                params,
                emit=self.lines.append,
                cancelled=lambda: self._cancel_flag,
            )
            self.returncode = 0
        except Exception as e:
            self.lines.append(f"--- ошибка рассылки: {e} ---")
            self.returncode = 1

    def cancel(self) -> bool:
        if not self.running:
            return False
        # своя рассылка останавливается флагом (проверяется в цикле),
        # subprocess-операции — сигналом terminate
        if self._apply_task is not None and not self._apply_task.done():
            self._cancel_flag = True
            return True
        self._stop_reason = "по кнопке «Остановить»"
        self._proc.terminate()
        return True


runner = Runner()
