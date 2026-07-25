"""Реестр профилей (аккаунтов hh.ru) для мультиаккаунта.

Профили физически изолированы папками (см. paths.profile_dir): у каждого
свой токен, база откликов, письмо и фильтры. Здесь — только их список,
ярлыки и служебные операции (добавить/удалить/переключить).
"""

from __future__ import annotations

import json
import shutil
import time
from typing import Any

from . import paths

MAX_PROFILES = 5
REGISTRY_FILE = paths.CONFIG_ROOT / "dashboard-profiles.json"


def _load() -> dict[str, str]:
    """Возвращает {profile_id: label}."""
    if REGISTRY_FILE.exists():
        try:
            data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save(reg: dict[str, str]) -> None:
    paths.CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _default_label(pid: str, index: int) -> str:
    return "Аккаунт 1" if pid == paths.DEFAULT_PROFILE else f"Аккаунт {index + 1}"


def list_profiles() -> list[dict[str, Any]]:
    reg = _load()
    # профиль по умолчанию существует всегда, даже если его нет в реестре
    ids = [paths.DEFAULT_PROFILE]
    ids += [pid for pid in reg if pid != paths.DEFAULT_PROFILE]
    active = paths.active_profile()
    result = []
    for i, pid in enumerate(ids):
        result.append(
            {
                "id": pid,
                "label": reg.get(pid) or _default_label(pid, i),
                "active": pid == active,
            }
        )
    return result


def set_label(pid: str, label: str) -> None:
    label = (label or "").strip()
    if not label:
        return
    reg = _load()
    reg[pid] = label
    _save(reg)


def add_profile() -> dict[str, Any]:
    """Создаёт новый пустой профиль и делает его активным.

    Вход в аккаунт запускается отдельно (тем же механизмом, что и обычный
    вход) — сюда пользователь попадает уже с активным пустым профилем.
    """
    existing = list_profiles()
    if len(existing) >= MAX_PROFILES:
        raise ValueError(f"Максимум {MAX_PROFILES} аккаунтов")

    pid = f"acc-{int(time.time())}"
    reg = _load()
    reg[pid] = f"Аккаунт {len(existing) + 1}"
    _save(reg)
    paths.profile_dir(pid).mkdir(parents=True, exist_ok=True)
    paths.set_active_profile(pid)
    return {"id": pid, "label": reg[pid]}


def switch_profile(pid: str) -> None:
    known = {p["id"] for p in list_profiles()}
    if pid not in known:
        raise ValueError("Неизвестный аккаунт")
    paths.set_active_profile(pid)


def delete_profile(pid: str) -> None:
    if pid == paths.DEFAULT_PROFILE:
        raise ValueError("Первый аккаунт удалить нельзя")
    known = {p["id"] for p in list_profiles()}
    if pid not in known:
        raise ValueError("Неизвестный аккаунт")

    # физически удаляем папку профиля со всеми его данными
    pdir = paths.profile_dir(pid)
    if pdir != paths.CONFIG_ROOT and pdir.exists():
        shutil.rmtree(pdir, ignore_errors=True)

    reg = _load()
    reg.pop(pid, None)
    _save(reg)

    if paths.active_profile() == pid:
        paths.set_active_profile(paths.DEFAULT_PROFILE)
