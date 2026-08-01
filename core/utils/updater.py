"""
Version and Update Checker for AudioScribe CLI and Engine.
Queries GitHub Releases API to detect new releases.
"""

import json
import urllib.request
from typing import Dict, Any, Optional

CURRENT_VERSION = "1.1.1"
GITHUB_REPO = "rodolfonobrega/AudioScribe"


class VersionChecker:
    """Check for new AudioScribe version on GitHub Releases."""

    def __init__(self, current_version: str = CURRENT_VERSION, repo: str = GITHUB_REPO):
        self.current_version = current_version.lstrip("v")
        self.repo = repo

    def check_for_updates(self, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
        """
        Check GitHub API for latest release.
        Returns dict with release info if newer version exists, else None.
        """
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AudioScribe-Update-Checker"}
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    latest_tag = data.get("tag_name", "").lstrip("v")
                    html_url = data.get("html_url", f"https://github.com/{self.repo}/releases/latest")

                    if self._is_newer(latest_tag, self.current_version):
                        return {
                            "current_version": self.current_version,
                            "latest_version": latest_tag,
                            "release_url": html_url,
                            "release_notes": data.get("body", "")
                        }
        except Exception:
            pass  # Silent failure on connection timeout / no internet

        return None

    def _is_newer(self, latest: str, current: str) -> bool:
        """Compare semver strings (e.g. '1.1.0' > '1.0.0')."""
        try:
            latest_parts = [int(p) for p in latest.split(".")]
            current_parts = [int(p) for p in current.split(".")]
            return latest_parts > current_parts
        except ValueError:
            return latest > current
