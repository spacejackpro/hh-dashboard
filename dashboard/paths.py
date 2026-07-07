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
