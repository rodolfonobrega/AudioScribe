"""Resumable, safe downloader for the managed local model catalog."""

from __future__ import annotations

import json
import hashlib
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict

from core.local_models import LOCAL_MODELS, LocalModel, model_cache_dir


MAX_ARCHIVE_MEMBERS = 4096
MAX_EXTRACTED_BYTES = 12 * 1024 * 1024 * 1024


class _DownloadCancelled(Exception):
    def __init__(self, downloaded: int, total: int):
        super().__init__("download_cancelled")
        self.downloaded = downloaded
        self.total = total


def _safe_extract(archive: Path, destination: Path, max_bytes: int = MAX_EXTRACTED_BYTES) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, "r:*", errorlevel=2) as tar:
        members = tar.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError("model_archive_too_many_files")
        extracted_bytes = 0
        for member in members:
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError("model_archive_path_traversal")
            target = (destination / member.name).resolve()
            if target != destination and destination not in target.parents:
                raise ValueError("model_archive_path_traversal")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ValueError("model_archive_unsafe_member")
            if not (member.isdir() or member.isfile()):
                raise ValueError("model_archive_unsafe_member")
            extracted_bytes += member.size
            if extracted_bytes > max_bytes:
                raise ValueError("model_archive_too_large")

        # Extract regular files manually. This avoids the Python 3.11
        # extractall fallback, which can still create unsafe link/device types.
        for member in members:
            target = (destination / member.name).resolve()
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise ValueError("model_archive_member_unreadable")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def _required_files_present(root: Path, required: tuple[str, ...]) -> bool:
    return all(any(path.name == filename for path in root.rglob(filename)) for filename in required)


def _notify(callback, downloaded: int, total: int, **metadata) -> None:
    if not callable(callback):
        return
    try:
        callback(downloaded, total, **metadata)
    except TypeError:
        # Keep compatibility with the original two-argument callback contract.
        callback(downloaded, total)


def _content_length(response) -> int:
    try:
        return max(0, int(response.headers.get("Content-Length", "0")))
    except (TypeError, ValueError):
        return 0


def _stream_download(
    url: str,
    part_path: Path,
    progress_callback,
    cancel_event,
    overall_before: int,
    overall_total: int,
    resumed: bool = False,
    max_bytes: int | None = None,
) -> tuple[int, int]:
    """Download one URL into a .part file and return cumulative progress."""
    part_path.parent.mkdir(parents=True, exist_ok=True)
    existing = part_path.stat().st_size if part_path.exists() else 0
    headers = {"User-Agent": "AudioScribe/1.0", "Accept-Encoding": "identity"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=headers)

    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        if existing and exc.code == 416:
            # The server considers the partial file complete. Let the caller validate it.
            return overall_before + existing, overall_total or existing
        raise

    response_status = getattr(response, "status", None) or response.getcode()
    append = bool(existing and response_status == 206)
    start = existing if append else 0
    if not append and existing:
        part_path.unlink(missing_ok=True)

    response_length = _content_length(response)
    file_total = start + response_length if append else response_length
    total = overall_total or (overall_before + file_total)
    if file_total and overall_total and overall_total < overall_before + file_total:
        total = overall_before + file_total
    downloaded = start
    if max_bytes is not None and start > max_bytes:
        raise ValueError("model_download_too_large")
    _notify(progress_callback, overall_before + downloaded, total, resumed=resumed or append)

    mode = "ab" if append else "wb"
    with response, part_path.open(mode) as output:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise _DownloadCancelled(overall_before + downloaded, total)
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if max_bytes is not None and downloaded > max_bytes:
                raise ValueError("model_download_too_large")
            _notify(progress_callback, overall_before + downloaded, total, resumed=resumed or append)

    return overall_before + downloaded, total


def _install_directory(source: Path, destination: Path, model: LocalModel) -> Dict[str, object]:
    if not _required_files_present(source, model.required_files):
        return {
            "status": "error",
            "code": "model_files_missing",
            "id": model.id,
            "required_files": list(model.required_files),
            "resumable": True,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.parent / f".{model.id}.staged"
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(source, staged)
    if destination.exists():
        shutil.rmtree(destination)
    staged.replace(destination)
    return {"status": "ok", "id": model.id, "installed": True, "path": str(destination), "downloaded": True}


def _download_archive(model: LocalModel, progress_callback, cancel_event) -> Dict[str, object]:
    destination = model_cache_dir() / model.id
    work_root = model_cache_dir() / ".downloads" / model.id
    archive = work_root / "model.tar.bz2"
    part = work_root / "model.tar.bz2.part"
    total_hint = model.size_mb * 1024 * 1024
    max_bytes = max(50 * 1024 * 1024, int(total_hint * 1.5))
    resumed = part.exists() and part.stat().st_size > 0
    try:
        downloaded, total = _stream_download(
            model.download_url,
            part,
            progress_callback,
            cancel_event,
            0,
            total_hint,
            resumed=resumed,
            max_bytes=max_bytes,
        )
        part.replace(archive)
        with tempfile.TemporaryDirectory(prefix="audioscribe-model-") as temp:
            extracted = Path(temp) / "extracted"
            extracted.mkdir()
            _safe_extract(archive, extracted, max_bytes=max_bytes)
            result = _install_directory(extracted, destination, model)
        if result.get("status") == "ok":
            shutil.rmtree(work_root, ignore_errors=True)
        return {**result, "downloaded_bytes": downloaded, "download_total": total}
    except _DownloadCancelled as exc:
        return {
            "status": "cancelled", "code": "download_cancelled", "id": model.id,
            "downloaded_bytes": exc.downloaded, "download_total": exc.total,
            "resumable": True,
        }


def _safe_relative_file(name: str) -> Path:
    path = Path(name)
    if not name or path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        raise ValueError("model_manifest_unsafe_path")
    return path


def _fetch_huggingface_files(repo: str, requested_files: tuple[str, ...] = ()) -> tuple[str, list[dict]]:
    url = f"https://huggingface.co/api/models/{repo}"
    request = urllib.request.Request(url, headers={"User-Agent": "AudioScribe/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    revision = str(payload.get("sha") or "")
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision.lower()):
        raise ValueError("model_manifest_unpinned_revision")
    files = []
    for item in payload.get("siblings", []):
        name = item.get("rfilename") or ""
        if not name or name.startswith("."):
            continue
        _safe_relative_file(name)
        if requested_files:
            if name not in requested_files:
                continue
        elif Path(name).suffix.lower() not in {".bin", ".json", ".txt", ".model", ".safetensors"}:
            continue
        digest = (item.get("lfs") or {}).get("sha256")
        files.append({"name": name, "size": int(item.get("size") or 0), "sha256": digest})
    return revision, files


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_huggingface(model: LocalModel, progress_callback, cancel_event) -> Dict[str, object]:
    revision, files = _fetch_huggingface_files(model.download_repo, model.download_files)
    if not files:
        return {"status": "error", "code": "model_manifest_empty", "id": model.id, "resumable": False}

    work_root = model_cache_dir() / ".downloads" / model.id
    files_root = work_root / "files"
    total = sum(item["size"] for item in files) or model.size_mb * 1024 * 1024
    max_bytes = max(50 * 1024 * 1024, int(model.size_mb * 1024 * 1024 * 1.5))
    if total > max_bytes:
        return {"status": "error", "code": "model_manifest_too_large", "id": model.id, "resumable": False}
    downloaded = 0
    for item in files:
        relative = _safe_relative_file(item["name"])
        target = (files_root / relative).resolve()
        if target != files_root.resolve() and files_root.resolve() not in target.parents:
            return {"status": "error", "code": "model_manifest_unsafe_path", "id": model.id, "resumable": False}
        part = target.with_name(target.name + ".part")
        if target.exists():
            downloaded += target.stat().st_size
            _notify(progress_callback, downloaded, total, resumed=True, file=item["name"])
            continue
        before = downloaded
        encoded_name = urllib.parse.quote(item["name"], safe="/")
        url = f"https://huggingface.co/{model.download_repo}/resolve/{revision}/{encoded_name}?download=true"
        try:
            downloaded, total = _stream_download(
                url, part, progress_callback, cancel_event, before, total,
                resumed=part.exists() and part.stat().st_size > 0,
                max_bytes=max_bytes,
            )
        except _DownloadCancelled as exc:
            return {
                "status": "cancelled", "code": "download_cancelled", "id": model.id,
                "downloaded_bytes": exc.downloaded, "download_total": exc.total,
                "resumable": True,
            }
        part.replace(target)
        expected_sha256 = item.get("sha256")
        if expected_sha256 and _sha256(target) != expected_sha256:
            target.unlink(missing_ok=True)
            return {"status": "error", "code": "model_checksum_mismatch", "id": model.id, "resumable": False}

    destination = model_cache_dir() / model.id
    result = _install_directory(files_root, destination, model)
    if result.get("status") == "ok":
        shutil.rmtree(work_root, ignore_errors=True)
    return {**result, "downloaded_bytes": downloaded, "download_total": total, "revision": revision}


def download_model(model_id: str, progress_callback=None, cancel_event=None) -> Dict[str, object]:
    model = LOCAL_MODELS.get(model_id)
    if not model:
        return {"status": "error", "code": "unknown_model", "id": model_id}
    destination = model_cache_dir() / model.id
    if destination.is_dir() and (not model.required_files or _required_files_present(destination, model.required_files)):
        return {"status": "ok", "id": model.id, "installed": True, "path": str(destination), "downloaded": False}
    if not model.download_url and not model.download_repo:
        return {
            "status": "error", "code": "manual_install_required", "id": model.id,
            "hint": f"Install {model.package} and place the model in {destination}",
        }

    try:
        if model.download_repo:
            return _download_huggingface(model, progress_callback, cancel_event)
        return _download_archive(model, progress_callback, cancel_event)
    except _DownloadCancelled as exc:
        return {
            "status": "cancelled", "code": "download_cancelled", "id": model.id,
            "downloaded_bytes": exc.downloaded, "download_total": exc.total,
            "resumable": True,
        }
    except Exception as exc:
        return {
            "status": "error", "code": "download_failed", "id": model.id,
            "error": str(exc), "resumable": (model_cache_dir() / ".downloads" / model.id).exists(),
        }


def delete_model(model_id: str) -> Dict[str, object]:
    """Remove one managed model and any resumable partial download safely."""
    from core.local_models import huggingface_cache_root

    model = LOCAL_MODELS.get(model_id)
    if not model:
        return {"status": "error", "code": "unknown_model", "id": model_id}

    root = model_cache_dir().expanduser().resolve()
    destination = (root / model.id).resolve()
    partial = (root / ".downloads" / model.id).resolve()
    if destination.parent != root or partial.parent.parent != root:
        return {"status": "error", "code": "invalid_model_path", "id": model.id}

    deleted = False
    partial_deleted = False
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
        deleted = True
    if partial.exists():
        shutil.rmtree(partial)
        partial_deleted = True
    cache_deleted = False
    if model.download_repo:
        cache_root = huggingface_cache_root().expanduser().resolve()
        repository = (cache_root / f"models--{model.download_repo.replace('/', '--')}").resolve()
        if repository.parent == cache_root and repository.exists():
            shutil.rmtree(repository)
            cache_deleted = True
    return {
        "status": "ok", "id": model.id, "deleted": deleted,
        "partial_deleted": partial_deleted, "cache_deleted": cache_deleted,
        "installed": False, "path": str(destination),
    }
