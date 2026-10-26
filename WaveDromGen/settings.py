# coding=utf-8
"""Persistent application settings stored as JSON."""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

APP_DIR_NAME = "WaveDromGen"

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "language": "en",
    "theme": "light",
    "view_mode": "stacked",
    "live_json_sync": True,
    "auto_extend_clocks": True,
    "auto_advance_cell": True,
    "show_grid": True,
    "editor_wrap": False,
    "editor_font_size": 10.5,
    "editor_indent": 2,
    "json_indent": 2,
    "zoom": 1.0,
    "window_geometry": "",
    "window_state": "",
    "splitter": {"stacked": [0.46, 0.54], "side": [0.58, 0.42]},
    "recent_files": [],
    "last_directory": "",
    "shortcuts": {},
    "show_shortcut_help_on_start": False,
}


def config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


class Settings:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else config_dir() / "settings.json"
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                self.data = _deep_merge(copy.deepcopy(DEFAULTS), raw)
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            # Keep the defaults; preserve the corrupt file for inspection.
            try:
                self.path.replace(self.path.with_suffix(".bad"))
            except OSError:
                pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix="settings-", suffix=".json", dir=str(self.path.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any, *, save: bool = False) -> None:
        self.data[key] = value
        if save:
            self.save()

    def update(self, values: dict[str, Any], *, save: bool = False) -> None:
        self.data.update(values)
        if save:
            self.save()

    def shortcuts(self) -> dict[str, list[str]]:
        value = self.data.get("shortcuts", {})
        return value if isinstance(value, dict) else {}

    def set_shortcuts(self, mapping: dict[str, list[str]], *, save: bool = True) -> None:
        self.data["shortcuts"] = mapping
        if save:
            self.save()

    def add_recent(self, path: str) -> None:
        path = os.path.abspath(path)
        recent = [p for p in self.data.get("recent_files", []) if os.path.abspath(p) != path]
        recent.insert(0, path)
        self.data["recent_files"] = recent[:8]
        self.data["last_directory"] = os.path.dirname(path)
        self.save()

    def clear_recent(self) -> None:
        self.data["recent_files"] = []
        self.save()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
