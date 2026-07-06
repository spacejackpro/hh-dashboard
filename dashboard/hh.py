"""Чтение данных hh-applicant-tool: конфиг с токеном и SQLite-база.

Дашборд ничего не пишет в базу утилиты — только читает. Все изменения
делаются самой утилитой (запускается сабпроцессом, см. runner.py).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

CONFIG_DIR = (
    Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    / "hh-applicant-tool"
)
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_FILE = CONFIG_DIR / "data"

DAILY_LIMIT = 200  # лимит откликов hh.ru в сутки


def read_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def token_status() -> dict[str, Any]:
    token = read_config().get("token") or {}
    expires_at = token.get("access_expires_at")
    expires_iso = None
    expired = None
    if isinstance(expires_at, (int, float)):
        dt = datetime.fromtimestamp(expires_at)
        expires_iso = dt.isoformat(timespec="seconds")
        expired = dt < datetime.now()
    return {
        "authorized": bool(token.get("access_token")),
        "expires_at": expires_iso,
        "expired": expired,
        "config_dir": str(CONFIG_DIR),
        "db_exists": DB_FILE.exists(),
    }


def _connect() -> sqlite3.Connection:
    # read-only, чтобы не мешать утилите и ничего случайно не испортить
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    if not DB_FILE.exists():
        return []
    with _connect() as conn:
        try:
            return [dict(row) for row in conn.execute(sql, params)]
        except sqlite3.OperationalError:
            # таблицы ещё не созданы (до первого запуска утилиты)
            return []


def fetch_resumes() -> list[dict[str, Any]]:
    rows = _query(
        """
        SELECT id, title, status_name, total_views, new_views,
               alternate_url, can_publish_or_update, updated_at
        FROM resumes ORDER BY updated_at DESC
        """
    )
    if rows:
        return rows
    # база пуста до первого запуска рассылки — берём резюме живым запросом
    if not token_status()["authorized"]:
        return []
    try:
        tool = _make_tool()
        items = tool.get_resumes()
        tool.save_token()
    except Exception:
        return []
    return [
        {
            "id": r.get("id"),
            "title": r.get("title"),
            "status_name": (r.get("status") or {}).get("name"),
            "total_views": (r.get("counters") or {}).get("total_views", 0),
            "new_views": (r.get("counters") or {}).get("new_views", 0),
            "alternate_url": r.get("alternate_url"),
            "can_publish_or_update": r.get("can_publish_or_update"),
            "updated_at": r.get("updated_at"),
        }
        for r in items
    ]


def fetch_negotiations(limit: int = 100) -> list[dict[str, Any]]:
    return _query(
        """
        SELECT n.id, n.state, n.vacancy_id, n.created_at, n.updated_at,
               v.name AS vacancy_name, v.alternate_url, v.area_name,
               v.salary_from, v.salary_to, v.currency,
               e.name AS employer_name
        FROM negotiations n
        LEFT JOIN vacancies v ON v.id = n.vacancy_id
        LEFT JOIN employers e ON e.id = n.employer_id
        ORDER BY n.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def fetch_skipped(limit: int = 100) -> list[dict[str, Any]]:
    return _query(
        """
        SELECT vacancy_id, name, employer_name, reason,
               alternate_url, created_at
        FROM skipped_vacancies ORDER BY created_at DESC LIMIT ?
        """,
        (limit,),
    )


def fetch_stats() -> dict[str, Any]:
    def scalar(sql: str) -> int:
        rows = _query(sql)
        return list(rows[0].values())[0] if rows else 0

    return {
        "today": scalar(
            "SELECT COUNT(*) FROM negotiations "
            "WHERE date(created_at, 'localtime') = date('now', 'localtime')"
        ),
        "daily_limit": DAILY_LIMIT,
        "total": scalar("SELECT COUNT(*) FROM negotiations"),
        "skipped": scalar("SELECT COUNT(*) FROM skipped_vacancies"),
        "vacancies": scalar("SELECT COUNT(*) FROM vacancies"),
        "employers": scalar("SELECT COUNT(*) FROM employers"),
    }


def _make_tool():
    """HHApplicantTool, готовый к использованию как библиотека.

    Конструктор сам по себе не заполняет config_dir и прочие атрибуты —
    это делает parse_args + _assign_args внутри CLI, повторяем то же самое
    с пустым argv (все значения по умолчанию).
    """
    from hh_applicant_tool import HHApplicantTool
    from hh_applicant_tool.main import BaseNamespace

    tool = HHApplicantTool()
    tool._assign_args(tool._parser.parse_args([], namespace=BaseNamespace()))
    return tool


def clear_local_auth() -> None:
    """Убирает токен из config.json и куки — локальная часть выхода."""
    cfg = read_config()
    if "token" in cfg:
        cfg.pop("token")
        CONFIG_FILE.write_text(
            json.dumps(cfg, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
    cookies = CONFIG_DIR / "cookies.txt"
    if cookies.exists():
        cookies.unlink()


def get_whoami() -> dict[str, Any]:
    """Живой запрос /me через библиотеку (медленнее, чем чтение базы)."""
    tool = _make_tool()
    me = tool.get_me()
    tool.save_token()  # токен мог обновиться
    return me
