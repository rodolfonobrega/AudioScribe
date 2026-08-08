import io
import tarfile
import threading

from core.local_models import LocalModel
from core import model_downloader


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.headers = {"Content-Length": str(len(payload))}
        self._offset = 0

    def getcode(self):
        return self.status

    def read(self, size=-1):
        if size < 0:
            size = len(self.payload)
        if self._offset >= len(self.payload):
            return b""
        end = min(len(self.payload), self._offset + min(size, 7))
        chunk = self.payload[self._offset:end]
        self._offset = end
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _model_archive():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:bz2") as archive:
        payload = b"encoder"
        info = tarfile.TarInfo("parakeet/encoder.int8.onnx")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return stream.getvalue()


def test_cancelled_archive_download_is_resumable(monkeypatch, tmp_path):
    archive_bytes = _model_archive()
    model = LocalModel(
        "test-parakeet", "Test Parakeet", "parakeet", "en", 1, "sherpa-onnx", "test",
        download_url="https://example.test/model.tar.bz2",
        required_files=("encoder.int8.onnx",),
    )
    monkeypatch.setenv("AUDIOSCRIBE_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setitem(model_downloader.LOCAL_MODELS, model.id, model)

    def fake_urlopen(request, timeout=60):
        range_header = request.headers.get("Range")
        if range_header:
            offset = int(range_header.split("=")[1].split("-")[0])
            response = _FakeResponse(archive_bytes[offset:], status=206)
            response.headers["Content-Range"] = f"bytes {offset}-{len(archive_bytes) - 1}/{len(archive_bytes)}"
            return response
        return _FakeResponse(archive_bytes)

    monkeypatch.setattr(model_downloader.urllib.request, "urlopen", fake_urlopen)
    cancel = threading.Event()

    def cancel_after_first_chunk(downloaded, _total, **_metadata):
        if downloaded:
            cancel.set()

    first = model_downloader.download_model(model.id, cancel_event=cancel, progress_callback=cancel_after_first_chunk)
    assert first["status"] == "cancelled"
    partial = tmp_path / "models" / ".downloads" / model.id / "model.tar.bz2.part"
    assert partial.exists()

    second = model_downloader.download_model(model.id, cancel_event=threading.Event())
    assert second["status"] == "ok"
    installed_file = next((tmp_path / "models" / model.id).rglob("encoder.int8.onnx"))
    assert installed_file.read_bytes() == b"encoder"
    assert not partial.exists()


def test_safe_extract_rejects_symbolic_links(tmp_path):
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, mode="w") as tar:
        link = tarfile.TarInfo("model-link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        tar.addfile(link)

    try:
        model_downloader._safe_extract(archive, tmp_path / "destination")
    except ValueError as exc:
        assert str(exc) == "model_archive_path_traversal" or str(exc) == "model_archive_unsafe_member"
    else:
        raise AssertionError("symbolic link archive member must be rejected")
