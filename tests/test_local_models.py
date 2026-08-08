import io
import tarfile

import pytest

from core.model_downloader import _safe_extract


def test_model_archive_rejects_path_traversal(tmp_path):
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as tar:
        data = io.BytesIO(b"bad")
        info = tarfile.TarInfo("../../outside.txt")
        info.size = len(data.getvalue())
        tar.addfile(info, data)
    with pytest.raises(ValueError, match="path_traversal"):
        _safe_extract(archive, tmp_path / "output")


def test_model_archive_extracts_nested_files_safely(tmp_path):
    archive = tmp_path / "safe.tar"
    with tarfile.open(archive, "w") as tar:
        data = io.BytesIO(b"tokens")
        info = tarfile.TarInfo("model/tokens.txt")
        info.size = len(data.getvalue())
        tar.addfile(info, data)
    output = tmp_path / "output"
    output.mkdir()
    _safe_extract(archive, output)
    assert (output / "model" / "tokens.txt").read_text() == "tokens"
