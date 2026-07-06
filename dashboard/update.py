"""Проверка наличия новой версии дашборда на GitHub.

Сравниваем локальный файл VERSION с таким же файлом в main-ветке репозитория.
Сам процесс обновления делает update.cmd — здесь только проверка.
"""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_DIR / "VERSION"

# owner/repo подставляется при публикации репозитория
REPO_SLUG = "OWNER/hh-dashboard"
REPO_URL = f"https://github.com/{REPO_SLUG}"
RAW_VERSION_URL = f"https://raw.githubusercontent.com/{REPO_SLUG}/main/VERSION"

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
