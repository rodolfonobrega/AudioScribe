"""Build the Python sidecar expected by electron-builder."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "electron" / "bin"
REQUIRED_MODULES = ("sounddevice", "soundfile", "numpy", "litellm", "tiktoken")


def validate_build_environment() -> None:
    missing = []
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:
            missing.append(f"{module}: {exc}")
    if missing:
        details = "\n".join(f" - {item}" for item in missing)
        raise RuntimeError(
            "Cannot build a functional AudioScribe engine because required runtime "
            f"dependencies are missing:\n{details}\n"
            "Install them with: python -m pip install -r requirements-docker.txt"
        )


def main() -> int:
    validate_build_environment()
    BIN.mkdir(parents=True, exist_ok=True)
    separator = os.pathsep
    litellm_spec = importlib.util.find_spec("litellm")
    litellm_root = Path(next(iter(litellm_spec.submodule_search_locations), "")) if litellm_spec else None
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
        "--additional-hooks-dir",
        str(ROOT / "scripts" / "pyinstaller_hooks"),
        "--add-data",
        f"{ROOT / 'config'}{separator}config",
        "--collect-all",
        "tiktoken",
        "--hidden-import",
        "tiktoken_ext.openai_public",
        str(ROOT / "main.py"),
    ]
    # LiteLLM resolves its default tiktoken cache relative to its own package.
    # Include every LiteLLM data file explicitly so extensionless BPE files are
    # preserved byte-for-byte and are not collected twice by different hooks.
    tokenizer_dir = litellm_root / "litellm_core_utils" / "tokenizers" if litellm_root else None
    if tokenizer_dir and tokenizer_dir.is_dir():
        for data_file in sorted(tokenizer_dir.iterdir()):
            if data_file.is_file():
                command.extend(
                    [
                        "--add-data",
                        f"{data_file}{separator}litellm/litellm_core_utils/tokenizers",
                    ]
                )

    # Keep LiteLLM's model metadata available to usage/model discovery code,
    # without collecting its tokenizer directory a second time.
    if litellm_root:
        for metadata_name in (
            "model_prices_and_context_window.json",
            "model_prices_and_context_window_backup.json",
        ):
            metadata_file = litellm_root / metadata_name
            if metadata_file.is_file():
                command.extend(["--add-data", f"{metadata_file}{separator}litellm"])
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
