"""
Unit tests for VersionChecker update checking module.
"""

import pytest
from unittest.mock import patch, MagicMock
from core.utils.updater import VersionChecker


@pytest.mark.unit
def test_version_checker_semver_comparison():
    checker = VersionChecker(current_version="1.0.0")

    assert checker._is_newer("1.1.0", "1.0.0") is True
    assert checker._is_newer("2.0.0", "1.9.9") is True
    assert checker._is_newer("1.0.0", "1.0.0") is False
    assert checker._is_newer("0.9.0", "1.0.0") is False


@pytest.mark.unit
@patch("urllib.request.urlopen")
def test_version_checker_github_api_update_found(mock_urlopen):
    checker = VersionChecker(current_version="1.0.0")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"tag_name": "v1.1.0", "html_url": "https://github.com/rodolfonobrega/AudioScribe/releases/tag/v1.1.0", "body": "Notes"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    res = checker.check_for_updates()

    assert res is not None
    assert res["latest_version"] == "1.1.0"
    assert res["release_url"] == "https://github.com/rodolfonobrega/AudioScribe/releases/tag/v1.1.0"
