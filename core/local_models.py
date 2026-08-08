"""Local model registry and runtime capability detection."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class LocalModel:
    id: str
    name: str
    provider: str
    languages: str
    size_mb: int
    package: str
    description: str
    download_url: Optional[str] = None
    required_files: tuple[str, ...] = ()
    download_repo: Optional[str] = None
    automatic_cache: bool = False
    download_files: tuple[str, ...] = ()


LOCAL_MODELS: Dict[str, LocalModel] = {
    "whisper-tiny": LocalModel(
        "whisper-tiny", "Whisper Tiny", "local_whisper", "multilingual", 75,
        "faster-whisper", "Smallest local model for fast dictation.",
        required_files=("model.bin",), download_repo="Systran/faster-whisper-tiny", automatic_cache=True,
    ),
    "whisper-base": LocalModel(
        "whisper-base", "Whisper Base", "local_whisper", "multilingual", 142,
        "faster-whisper", "Balanced local model for everyday dictation.",
        required_files=("model.bin",), download_repo="Systran/faster-whisper-base", automatic_cache=True,
    ),
    "whisper-small": LocalModel(
        "whisper-small", "Whisper Small", "local_whisper", "multilingual", 466,
        "faster-whisper", "Higher accuracy with more memory usage.",
        required_files=("model.bin",), download_repo="Systran/faster-whisper-small", automatic_cache=True,
    ),
    "whisper-medium": LocalModel(
        "whisper-medium", "Whisper Medium", "local_whisper", "multilingual", 1530,
        "faster-whisper", "High-quality multilingual local transcription.",
        required_files=("model.bin",), download_repo="Systran/faster-whisper-medium", automatic_cache=True,
    ),
    "whisper-large-v3": LocalModel(
        "whisper-large-v3", "Whisper Large v3", "local_whisper", "multilingual", 3070,
        "faster-whisper", "Highest-accuracy multilingual local transcription.",
        required_files=("model.bin",), download_repo="Systran/faster-whisper-large-v3", automatic_cache=True,
    ),
    "whisper-large-v3-turbo": LocalModel(
        "whisper-large-v3-turbo", "Whisper Large v3 Turbo", "local_whisper", "multilingual", 1620,
        "faster-whisper", "Best quality/speed balance for capable hardware.",
        required_files=("model.bin",), download_repo="mobiuslabsgmbh/faster-whisper-large-v3-turbo", automatic_cache=True,
    ),
    "parakeet-tdt-0.6b-v3": LocalModel(
        "parakeet-tdt-0.6b-v3", "Parakeet TDT 0.6B", "parakeet", "multilingual", 680,
        "sherpa-onnx", "Fast local multilingual ASR through sherpa-onnx.",
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2",
        ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"),
    ),
    "parakeet-tdt-1.1b": LocalModel(
        "parakeet-tdt-1.1b", "Parakeet TDT 1.1B", "parakeet", "en", 3900,
        "sherpa-onnx", "Large English Parakeet model; requires about 4 GB of storage.",
        download_repo="jenerallee78/parakeet-tdt-1.1b-onnx",
        required_files=("encoder.int8.onnx", "encoder.int8.weights", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"),
        download_files=("encoder.int8.onnx", "encoder.int8.weights", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"),
    ),
}


def model_cache_dir() -> Path:
    configured = os.getenv("AUDIOSCRIBE_MODEL_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(os.getenv("AUDIOSCRIBE_DATA_DIR", Path.home() / ".audioscribe")) / "models"


def huggingface_cache_root() -> Path:
    configured = os.getenv("HUGGINGFACE_HUB_CACHE")
    if configured:
        return Path(configured).expanduser()
    home = os.getenv("HF_HOME")
    if home:
        return Path(home).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def huggingface_model_path(model: LocalModel) -> Optional[Path]:
    if not model.download_repo:
        return None
    repo_root = huggingface_cache_root() / f"models--{model.download_repo.replace('/', '--')}"
    snapshots = repo_root / "snapshots"
    if not snapshots.exists():
        return None
    for snapshot in snapshots.iterdir():
        if snapshot.is_dir() and _required_files_present(snapshot, model.required_files):
            return snapshot
    return None


def _required_files_present(root: Path, required: tuple[str, ...]) -> bool:
    return all(any(path.name == filename for path in root.rglob(filename)) for filename in required)


def gpu_capabilities() -> Dict[str, object]:
    result = {"cuda": False, "mps": False, "vulkan": False, "device": "cpu", "details": []}
    try:
        import torch
        result["cuda"] = bool(torch.cuda.is_available())
        result["mps"] = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        if result["cuda"]:
            result["device"] = "cuda"
            result["details"].append(torch.cuda.get_device_name(0))
        elif result["mps"]:
            result["device"] = "mps"
    except Exception as exc:
        result["details"].append(f"torch unavailable: {exc}")
    if platform.system() in {"Windows", "Linux"} and shutil.which("vulkaninfo"):
        result["vulkan"] = True
        result["details"].append("Vulkan runtime detected")
    return result


def local_model_status(model_id: str) -> Dict[str, object]:
    model = LOCAL_MODELS.get(model_id)
    if not model:
        return {"id": model_id, "available": False, "error": "unknown_model"}
    package_available = bool(importlib.util.find_spec("faster_whisper" if model.provider == "local_whisper" else "sherpa_onnx"))
    path = model_cache_dir() / model.id
    cache_path = huggingface_model_path(model)
    download_dir = model_cache_dir() / ".downloads" / model.id
    managed_installed = path.is_dir() and (not model.required_files or _required_files_present(path, model.required_files))
    installed = managed_installed or cache_path is not None
    partial_files = []
    if download_dir.exists():
        partial_files = [item for item in download_dir.rglob("*") if item.is_file() and item.name.endswith(".part")]
        if model.download_repo:
            partial_files += [
                item for item in download_dir.rglob("*")
                if item.is_file() and not item.name.endswith(".part") and item.name != ".metadata.json"
            ]
    downloaded_bytes = sum(item.stat().st_size for item in partial_files if item.exists())
    download_total = max(0, int(model.size_mb * 1024 * 1024)) if partial_files else 0
    return {
        **asdict(model),
        "package_available": package_available,
        "installed": installed,
        "downloadable": bool(model.download_url or model.download_repo),
        "download_state": "installed" if installed else "partial" if partial_files else "available",
        "downloaded_bytes": downloaded_bytes,
        "download_total": download_total,
        "download_percent": min(99, int(downloaded_bytes * 100 / download_total)) if download_total else 0,
        "resumable": bool(partial_files),
        "path": str(path),
        "cache_path": str(cache_path) if cache_path else None,
        "cache_source": "managed" if managed_installed else "huggingface" if cache_path else None,
    }


def list_local_models() -> List[Dict[str, object]]:
    return [local_model_status(model_id) for model_id in LOCAL_MODELS]


def install_hint(model_id: str) -> Optional[str]:
    model = LOCAL_MODELS.get(model_id)
    if not model:
        return None
    return f"pip install {model.package}"
