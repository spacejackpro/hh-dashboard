"""Пути, зависящие от операционной системы (Windows / macOS / Linux).

Собрано в одном месте, чтобы весь остальной код был кроссплатформенным.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

_SYSTEM = platform.system()  # 'Windows' | 'Darwin' | 'Linux'
IS_WINDOWS = _SYSTEM == "Windows"


def config_dir() -> Path:
    """Папка с данными hh-applicant-tool (токен, база, письмо).

    Совпадает с логикой самой утилиты (utils/config.py get_config_path):
    у каждой ОС своё стандартное место для конфигов приложений.
    """
    if IS_WINDOWS:
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif _SYSTEM == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "hh-applicant-tool"


def _venv_bin() -> Path:
    # внутри venv папка со скриптами называется по-разному
    return PROJECT_DIR / ".venv" / ("Scripts" if IS_WINDOWS else "bin")


def hh_tool_exe() -> Path:
    exe = "hh-applicant-tool" + (".exe" if IS_WINDOWS else "")
    return _venv_bin() / exe


CONFIG_DIR = config_dir()
HH_TOOL_EXE = hh_tool_exe()

# ---------- Профили (мультиаккаунт) ----------
# Каждый аккаунт hh.ru — отдельный «профиль» со своей папкой данных.
# Профиль по умолчанию (первый аккаунт) живёт прямо в корне CONFIG_DIR —
# там же, где утилита держала единственный аккаунт до мультиаккаунта.
# Остальные — в подпапках CONFIG_DIR/<id>. Служебные файлы дашборда
# (активный профиль, реестр, общий стоп-лист) лежат в корне и общие.
CONFIG_ROOT = CONFIG_DIR
DEFAULT_PROFILE = "default"
ACTIVE_FILE = CONFIG_ROOT / "dashboard-active.txt"


def active_profile() -> str:
    try:
        return ACTIVE_FILE.read_text(encoding="utf-8").strip() or DEFAULT_PROFILE
    except OSError:
        return DEFAULT_PROFILE


def set_active_profile(pid: str) -> None:
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(pid, encoding="utf-8")


def profile_dir(pid: str | None = None) -> Path:
    pid = pid or active_profile()
    return CONFIG_ROOT if pid == DEFAULT_PROFILE else CONFIG_ROOT / pid


def profile_cli_id(pid: str | None = None) -> str:
    """Идентификатор профиля для флага --profile-id движка.

    Движок хранит профиль по умолчанию в подкаталоге «.» (корень).
    """
    pid = pid or active_profile()
    return "." if pid == DEFAULT_PROFILE else pid
