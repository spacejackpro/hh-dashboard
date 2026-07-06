"""Проверка наличия новой версии дашборда на GitHub.

Сравниваем локальный файл VERSION с таким же файлом в main-ветке репозитория.
Сам процесс обновления делает update.cmd — здесь только проверка.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_DIR / "VERSION"

REPO_SLUG = "spacejackpro/hh-dashboard"
REPO_URL = f"https://github.com/{REPO_SLUG}"
RAW_VERSION_URL = f"https://raw.githubusercontent.com/{REPO_SLUG}/main/VERSION"
ZIP_URL = f"https://codeload.github.com/{REPO_SLUG}/zip/refs/heads/main"

# по этому коду dashboard.cmd понимает, что нужен перезапуск, а не выход
RESTART_EXIT_CODE = 42
# маркер для dashboard.cmd: перед стартом обновить движок через pip
PENDING_MARKER = PROJECT_DIR / ".update-pending"

_CACHE_TTL = 3600  # не дёргать GitHub чаще раза в час
_cache: dict = {"at": 0.0, "latest": None}


def current_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.strip().split("."))


def latest_version() -> str | None:
    now = time.time()
    if now - _cache["at"] < _CACHE_TTL:
        return _cache["latest"]
    latest = None
    try:
        with urllib.request.urlopen(RAW_VERSION_URL, timeout=5) as resp:
            latest = resp.read().decode("utf-8").strip()
    except Exception:
        pass  # нет сети / репозиторий ещё не создан — просто нет данных
    _cache.update(at=now, latest=latest)
    return latest


def version_info() -> dict:
    cur = current_version()
    latest = latest_version()
    update_available = False
    if latest:
        try:
            update_available = _parse(latest) > _parse(cur)
        except ValueError:
            pass
    return {
        "current": cur,
        "latest": latest,
        "update_available": update_available,
        "repo": REPO_URL,
    }


# ---------- Обновление из интерфейса ----------

_update_state: dict = {"running": False, "error": None}


def update_state() -> dict:
    return dict(_update_state)


def start_update() -> None:
    if _update_state["running"]:
        raise RuntimeError("Обновление уже идёт")
    _update_state.update(running=True, error=None)
    threading.Thread(target=_do_update, daemon=True).start()


def _do_update() -> None:
    """Скачивает свежий код с GitHub, копирует поверх и перезапускает сервер.

    Обновление движка (pip install -U) делает dashboard.cmd после
    перезапуска — пока сервер работает, pip не может заменить занятые файлы.
    dashboard.cmd не трогаем: перезаписывать выполняющийся батник опасно,
    его обновляет только update.cmd.
    """
    try:
        tmp = Path(tempfile.mkdtemp(prefix="hhdash-update-"))
        zip_path = tmp / "src.zip"
        with urllib.request.urlopen(ZIP_URL, timeout=60) as resp, open(
            zip_path, "wb"
        ) as f:
            shutil.copyfileobj(resp, f)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        src = next(p for p in tmp.iterdir() if p.is_dir())

        for item in src.rglob("*"):
            rel = item.relative_to(src)
            if len(rel.parts) == 1 and rel.name == "dashboard.cmd":
                continue
            dest = PROJECT_DIR / rel
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                shutil.copy2(item, dest)

        PENDING_MARKER.write_text("1", encoding="utf-8")
        # даём серверу секунду ответить клиенту и выходим на перезапуск
        threading.Timer(1.5, lambda: os._exit(RESTART_EXIT_CODE)).start()
    except Exception as e:
        _update_state.update(running=False, error=str(e))
