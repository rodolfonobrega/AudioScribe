"""Provider model discovery over OpenAI-compatible and native Ollama endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _get_json(url: str, api_key: Optional[str] = None, timeout: float = 3.0) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_models(base_url: Optional[str], api_key: Optional[str], provider: str) -> List[Dict[str, Any]]:
    if not base_url:
        return []
    normalized = base_url.rstrip("/")
    if provider.lower() == "ollama" or "11434" in normalized:
        url = normalized[:-2] + "api/tags" if normalized.endswith("/v1") else normalized + "/api/tags"
        payload = _get_json(url, api_key)
        return [
            {
                "id": item.get("name") or item.get("model"),
                "name": item.get("name") or item.get("model"),
                "provider": "ollama",
                "local": True,
                "details": item.get("details", {}),
            }
            for item in payload.get("models", [])
            if item.get("name") or item.get("model")
        ]

    url = normalized + "/models" if not normalized.endswith("/v1") else normalized + "/models"
    payload = _get_json(url, api_key)
    return [
        {"id": item.get("id"), "name": item.get("id"), "provider": provider, "local": False}
        for item in payload.get("data", [])
        if item.get("id")
    ]


def discovery_error(exc: Exception) -> Dict[str, str]:
    if isinstance(exc, HTTPError):
        message = f"endpoint respondeu HTTP {exc.code}"
    elif isinstance(exc, URLError):
        message = "não foi possível conectar ao endpoint"
    else:
        message = str(exc)
    return {"code": "model_discovery_failed", "message": message}
