"""Optional local transcription backends.

Imports are lazy so cloud-only installations keep working without downloading
large ML runtimes. Errors include the exact optional package needed.
"""

from __future__ import annotations

import os
import io
import tempfile
from pathlib import Path
from typing import Optional

from core.interfaces.transcriber import AbstractTranscriber
from core.local_models import model_cache_dir


class LocalWhisperTranscriber(AbstractTranscriber):
    def __init__(self, config):
        self.config = config
        self.model = getattr(config, "model", "whisper-base")
        self.model_id = self.model.removeprefix("local_whisper/")
        self.device = getattr(config, "device", "auto")
        self.compute_type = getattr(config, "compute_type", "auto")
        self.language = getattr(config, "language", "auto")
        self._backend = None
        self._load_backend()

    def _load_backend(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ImportError("Local Whisper requires the optional package 'faster-whisper'. Install it with: pip install faster-whisper") from exc
        device = self.device
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        compute_type = self.compute_type if self.compute_type != "auto" else ("float16" if device == "cuda" else "int8")
        model_name = {
            "whisper-tiny": "tiny",
            "whisper-base": "base",
            "whisper-small": "small",
            "whisper-medium": "medium",
            "whisper-large-v3": "large-v3",
            "whisper-large-v3-turbo": "large-v3-turbo",
        }.get(self.model_id, self.model_id)
        model_dir = getattr(self.config, "model_path", None)
        if not model_dir and Path(model_cache_dir() / self.model).exists():
            model_dir = str(model_cache_dir() / self.model)
        self._backend = WhisperModel(model_dir or model_name, device=device, compute_type=compute_type)
        self.device = device

    def transcribe(self, audio_data: bytes) -> Optional[str]:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                handle.write(audio_data)
                temp_path = handle.name
            segments, _ = self._backend.transcribe(
                temp_path,
                language=None if self.language in {None, "", "auto"} else self.language,
                vad_filter=True,
            )
            return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip() or None
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    pass

    @property
    def supports_streaming(self) -> bool:
        return False

    def health_check(self) -> None:
        if self._backend is None:
            raise RuntimeError("Local Whisper model is not loaded")


class ParakeetTranscriber(AbstractTranscriber):
    """Parakeet TDT backend using the optional sherpa-onnx Python package."""

    def __init__(self, config):
        self.config = config
        self.model = getattr(config, "model", "parakeet-tdt-0.6b-v3")
        self.language = getattr(config, "language", "auto")
        self.model_path = getattr(config, "model_path", None) or str(model_cache_dir() / self.model)
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise ImportError("Parakeet requires the optional package 'sherpa-onnx'. Install it with: pip install sherpa-onnx") from exc
        if not self.model_path:
            raise RuntimeError("Parakeet model files are not configured. Set TRANSCRIPTION_MODEL_PATH to a sherpa-onnx Parakeet model directory.")
        model_dir = Path(self.model_path)
        files = {}
        for name in ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"):
            found = list(model_dir.rglob(name))
            if found:
                files[name] = found[0]

        missing = [name for name in ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt") if name not in files]
        if missing:
            raise FileNotFoundError(f"Parakeet model is missing required files in {model_dir}: {', '.join(missing)}")
        provider = "cuda" if getattr(config, "device", "auto") == "cuda" else "cpu"
        self.device = provider
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(files["encoder.int8.onnx"]),
            decoder=str(files["decoder.int8.onnx"]),
            joiner=str(files["joiner.int8.onnx"]),
            tokens=str(files["tokens.txt"]),
            num_threads=max(1, min(8, (os.cpu_count() or 2) - 1)),
            provider=provider,
        )

    def transcribe(self, audio_data: bytes) -> Optional[str]:
        import soundfile as sf
        samples, sample_rate = sf.read(io.BytesIO(audio_data), dtype="float32", always_2d=True)
        mono = samples[:, 0]
        stream = self._recognizer.create_stream()
        stream.accept_waveform(sample_rate, mono)
        self._recognizer.decode_stream(stream)
        text = getattr(getattr(stream, "result", None), "text", "") or ""
        return text.strip() or None

    def transcribe_file(self, file_path: str) -> Optional[str]:
        try:
            with open(file_path, "rb") as f:
                return self.transcribe(f.read())
        except Exception:
            return None

    @property
    def supports_streaming(self) -> bool:
        return False

    def health_check(self) -> None:
        if not getattr(self, "_recognizer", None):
            raise RuntimeError("Parakeet recognizer is not loaded")
