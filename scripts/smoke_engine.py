"""Start the local IPC engine and verify its first real command response."""

from __future__ import annotations

import json
import hashlib
import hmac
import secrets
import socket
import shutil
import subprocess
import sys
import tempfile
import os
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def signed_request(token: str, request_id: str, sequence: int, command: str, params: dict[str, object]) -> bytes:
    material = ":".join(("request", "3", str(sequence), request_id, command, canonical_json(params)))
    auth = hmac.new(token.encode("utf-8"), material.encode("utf-8"), hashlib.sha256).hexdigest()
    return (canonical_json({
        "protocol_version": 3,
        "id": request_id,
        "sequence": sequence,
        "command": command,
        "params": params,
        "auth": auth,
    }) + "\n").encode("utf-8")


def main() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = int(reservation.getsockname()[1])
    token = secrets.token_urlsafe(32)
    smoke_data_dir = tempfile.mkdtemp(prefix="audioscribe-smoke-")
    command = [
        sys.executable,
        str(ROOT / "main.py"),
        "--server",
        "--no-keyboard",
        "--output",
        "stdout",
        "--port",
        str(port),
        "--session-token-stdin",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.PIPE,
        env={**os.environ, "AUDIOSCRIBE_DATA_DIR": smoke_data_dir},
    )
    try:
        assert process.stdin is not None
        process.stdin.write(f"{token}\n")
        process.stdin.flush()
        deadline = time.monotonic() + 10
        response = None
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5) as client:
                    client.sendall(signed_request(token, "smoke", 1, "ping", {}))
                    data = b""
                    while b"\n" not in data:
                        chunk = client.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    if data:
                        envelope = json.loads(data.splitlines()[0].decode("utf-8"))
                        response = json.loads(envelope["payload"])
                        break
            except (ConnectionRefusedError, TimeoutError, OSError, json.JSONDecodeError):
                time.sleep(0.2)

        if not response or response.get("status") != "ok" or not response.get("engine_running"):
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            output = process.stdout.read() if process.stdout else ""
            print(f"Engine smoke test failed. Response={response!r}\nEngine output:\n{output}", file=sys.stderr)
            return 1

        print("Engine smoke test passed: ping returned engine_running=true")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        shutil.rmtree(smoke_data_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
