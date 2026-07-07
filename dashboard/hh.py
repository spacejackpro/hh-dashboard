"""Чтение данных hh-applicant-tool: конфиг с токеном и SQLite-база.

Дашборд ничего не пишет в базу утилиты — только читает. Все изменения
делаются самой утилитой (запускается сабпроцессом, см. runner.py).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
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


# Движок НЕ сохраняет отклики в свою базу (negotiations.save у автора
# закомментирован), поэтому отклики берём живьём из API hh.ru с кэшем.
_NEG_TTL = 60
_neg_cache: dict = {"at": 0.0, "items": None}


def _fetch_negotiations_raw() -> list[dict[str, Any]] | None:
    """Все отклики из API hh.ru (новые сверху); None — если API недоступен.

    Метод движка get_negotiations не используем: он передаёт status=active,
    из-за чего hh.ru возвращает лишь малую часть откликов.
    """
    now = time.time()
    if now - _neg_cache["at"] < _NEG_TTL:
        return _neg_cache["items"]
    items = None
    if token_status()["authorized"]:
        try:
            tool = _make_tool()
            items = []
            page = 0
            while True:
                r = tool.api_client.get(
                    "/negotiations",
                    page=page,
                    per_page=100,
                    order_by="created_at",
                    order="desc",
                )
                batch = r.get("items", [])
                items.extend(batch)
                if not batch or page + 1 >= r.get("pages", 0):
                    break
                page += 1
            tool.save_token()
        except Exception:
            items = None
    _neg_cache.update(at=now, items=items)
    return items


def fetch_negotiations(limit: int = 100) -> list[dict[str, Any]]:
    raw = _fetch_negotiations_raw()
    if raw is None:
        return []
    result = []
    for n in raw[:limit]:
        vacancy = n.get("vacancy") or {}
        salary = vacancy.get("salary") or {}
        result.append(
            {
                "id": n.get("id"),
                "state": (n.get("state") or {}).get("id"),
                "vacancy_id": vacancy.get("id"),
                "vacancy_name": vacancy.get("name"),
                "alternate_url": vacancy.get("alternate_url"),
                "area_name": (vacancy.get("area") or {}).get("name"),
                "salary_from": salary.get("from"),
                "salary_to": salary.get("to"),
                "currency": salary.get("currency"),
                "employer_name": (vacancy.get("employer") or {}).get("name"),
                "created_at": n.get("created_at"),
                "updated_at": n.get("updated_at"),
            }
        )
    return result


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

    today = total = 0
    raw = _fetch_negotiations_raw()
    if raw is not None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        today = sum(
            1 for n in raw if (n.get("created_at") or "").startswith(today_str)
        )
        total = len(raw)

    return {
        "today": today,
        "daily_limit": DAILY_LIMIT,
        "total": total,
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


def preview_apply(params: dict[str, Any]) -> dict[str, Any]:
    """Прикидка для «пробного запуска»: кого бы выбрала рассылка.

    Движок в --dry-run молчит (его сообщения — на уровне DEBUG), поэтому
    предпросмотр делаем сами: ищем вакансии тем же фильтром и сверяем
    с прошлыми откликами и списком пропущенных.
    """
    try:
        limit = int(params.get("max_responses") or 0) or 10
    except (TypeError, ValueError):
        limit = 10

    tool = _make_tool()
    query: dict[str, Any] = {"page": 0, "per_page": 50}
    if params.get("search"):
        query["text"] = str(params["search"])
    if params.get("salary"):
        query["salary"] = int(params["salary"])
    if params.get("only_with_salary"):
        query["only_with_salary"] = "true"
    r = tool.api_client.get("/vacancies", **query)
    tool.save_token()

    applied_ids = set()
    for n in _fetch_negotiations_raw() or []:
        vid = (n.get("vacancy") or {}).get("id")
        if vid:
            applied_ids.add(str(vid))
    skipped_ids = {
        str(row["vacancy_id"])
        for row in _query("SELECT vacancy_id FROM skipped_vacancies")
    }

    items = []
    would_apply = 0
    for v in r.get("items", []):
        vid = str(v.get("id"))
        salary = v.get("salary") or {}
        verdict: str = "apply"
        reason: str | None = None
        if vid in applied_ids or v.get("relations"):
            verdict, reason = "skip", "уже откликались"
        elif v.get("archived"):
            verdict, reason = "skip", "вакансия в архиве"
        elif params.get("skip_tests") and v.get("has_test"):
            verdict, reason = "skip", "вакансия с тестом"
        elif vid in skipped_ids:
            verdict, reason = "skip", "утилита уже пропускала её раньше"
        elif would_apply >= limit:
            verdict, reason = "over_limit", "не влезает в лимит"
        if verdict == "apply":
            would_apply += 1
        items.append(
            {
                "verdict": verdict,
                "reason": reason,
                "name": v.get("name"),
                "employer": (v.get("employer") or {}).get("name"),
                "salary_from": salary.get("from"),
                "salary_to": salary.get("to"),
                "currency": salary.get("currency"),
                "url": v.get("alternate_url"),
            }
        )

    return {
        "found": r.get("found", 0),
        "shown": len(items),
        "would_apply": would_apply,
        "limit": limit,
        "items": items,
    }


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
