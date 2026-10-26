# coding=utf-8
"""Build a single-file Windows executable with PyInstaller.

Usage:
    python -m pip install pyinstaller
    python package2exe.py

The output is ``dist/WaveDromGen.exe``.  Both the application icon and the
WaveDrom skin data are bundled as data files.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is required: python -m pip install pyinstaller", file=sys.stderr)
        return 1

    sep = ";" if os.name == "nt" else ":"
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
    ]
    if os.name == "nt":
        args += ["--icon", str(ROOT / "asset" / "app.ico")]
    args += [
        "--name",
        "WaveDromGen",
        "--add-data",
        f"{ROOT / 'asset' / 'app.ico'}{sep}asset",
        "--add-data",
        f"{ROOT / 'WaveDromGen' / 'resources'}{sep}WaveDromGen/resources",
        "--hidden-import",
        "PySide6.QtSvg",
        str(ROOT / "main.py"),
    ]
    print(" ".join(args))
    return subprocess.call(args, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
