"""Build the Python sidecar expected by electron-builder."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "electron" / "bin"


def main() -> int:
    BIN.mkdir(parents=True, exist_ok=True)
    separator = os.pathsep
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "audioscribe_engine",
        "--paths",
        str(ROOT),
        "--add-data",
        f"{ROOT / 'config'}{separator}config",
        "--collect-data",
        "litellm",
        "--collect-all",
        "tiktoken",
        "--hidden-import",
        "tiktoken_ext.openai_public",
        str(ROOT / "main.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    executable = ROOT / "dist" / ("audioscribe_engine.exe" if os.name == "nt" else "audioscribe_engine")
    if not executable.exists():
        raise FileNotFoundError(f"PyInstaller did not create {executable}")
    destination = BIN / executable.name
    shutil.copy2(executable, destination)
    print(f"Built sidecar: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
