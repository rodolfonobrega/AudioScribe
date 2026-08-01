"""
Unit tests for Output Handlers.
"""

import pytest
from unittest.mock import patch, MagicMock
from core.implementations.output.output_handlers import (
    ConsoleOutputHandler,
    ClipboardOutputHandler,
    AppleScriptOutputHandler
)


@pytest.mark.unit
def test_console_output_handler():
    handler = ConsoleOutputHandler()
    assert handler.is_available() is True
    assert handler.platform in ["Windows", "Darwin", "Linux"]
    # Console handler output should run silently
    handler.output("Test string")


@pytest.mark.unit
def test_clipboard_output_handler_mocked():
    handler = ClipboardOutputHandler()
    with patch.object(handler, 'pyperclip') as mock_pyperclip:
        handler.output("Hello World")
        mock_pyperclip.copy.assert_called_once_with("Hello World")


@pytest.mark.unit
def test_applescript_escaping():
    if AppleScriptOutputHandler.__module__:
        with patch("platform.system", return_value="Darwin"):
            handler = AppleScriptOutputHandler.__new__(AppleScriptOutputHandler)
            handler._platform = "Darwin"
            escaped = handler._escape_for_applescript('Text with "quotes" and \\backslashes\\')
            assert '\\"' in escaped
            assert '\\\\' in escaped
