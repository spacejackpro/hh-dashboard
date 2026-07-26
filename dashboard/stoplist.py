"""Общий стоп-лист вакансий между всеми аккаунтами.

Единый журнал «на эту вакансию уже откликались» — общий для всех профилей.
Перед откликом любой аккаунт сверяется с ним, чтобы не дублировать отклик
на одну вакансию с разных аккаунтов. Лежит в корне (не в папке профиля),
поэтому общий.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from . import paths

STOPLIST_FILE = paths.CONFIG_ROOT / "shared-applied.json"


def _load() -> dict[str, dict[str, Any]]:
    if STOPLIST_FILE.exists():
        try:
            data = json.loads(STOPLIST_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save(data: dict[str, dict[str, Any]]) -> None:
    STOPLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOPLIST_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def applied_ids() -> set[str]:
    return set(_load().keys())


def add(vacancy_id: str, profile_label: str, name: str = "", url: str = "") -> None:
    data = _load()
    vid = str(vacancy_id)
    if vid in data:
        return  # первый отклик уже зафиксирован, время не перетираем
    data[vid] = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "profile": profile_label,
        "name": name,
        "url": url,
    }
    _save(data)


def items() -> list[dict[str, Any]]:
    data = _load()
    rows = [{"vacancy_id": k, **v} for k, v in data.items()]
    rows.sort(key=lambda r: r.get("at", ""), reverse=True)
    return rows


def count() -> int:
    return len(_load())


def clear() -> None:
    if STOPLIST_FILE.exists():
        STOPLIST_FILE.unlink()
