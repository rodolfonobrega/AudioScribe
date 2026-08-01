"""Start the local IPC engine and verify its first real command response."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    port = 18765
    command = [
        sys.executable,
        str(ROOT / "main.py"),
        "--server",
        "--no-keyboard",
        "--output",
        "stdout",
        "--port",
        str(port),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        response = None
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5) as client:
                    client.sendall(b'{"id":"smoke","command":"ping"}\n')
                    data = b""
                    while b"\n" not in data:
                        chunk = client.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    if data:
                        response = json.loads(data.splitlines()[0].decode("utf-8"))
                        break
            except (ConnectionRefusedError, TimeoutError, OSError, json.JSONDecodeError):
                time.sleep(0.2)

        if not response or response.get("status") != "ok" or not response.get("engine_running"):
            print(f"Engine smoke test failed. Response={response!r}", file=sys.stderr)
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


if __name__ == "__main__":
    raise SystemExit(main())
