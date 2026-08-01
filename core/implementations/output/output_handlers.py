"""
Output Handler Implementations
Platform-specific handlers for typing transcribed text.
"""

import os
import shutil
import subprocess
import platform
from typing import List, Optional

from core.interfaces.output_handler import AbstractOutputHandler


class ConsoleOutputHandler(AbstractOutputHandler):
    """Simple console output handler."""
    
    def __init__(self, config=None):
        self.config = config
        self._platform = platform.system()
    
    def output(self, text: str, **kwargs) -> None:
        """Print text to console."""
        # Output is managed via UI.show_result()
        pass
    
    def is_available(self) -> bool:
        """Console is always available."""
        return True
    
    @property
    def platform(self) -> str:
        """Get the platform name."""
        return self._platform
    
    @property
    def supported_platforms(self) -> List[str]:
        """Get supported platforms."""
        return ["Windows", "Darwin", "Linux"]


class ClipboardOutputHandler(AbstractOutputHandler):
    """Clipboard output handler (cross-platform using pyperclip with native fallbacks)."""
    
    def __init__(self, config=None):
        self.config = config
        self._platform = platform.system()
        
        # Try importing pyperclip
        try:
            import pyperclip
            self.pyperclip = pyperclip
        except ImportError:
            self.pyperclip = None
    
    def output(self, text: str, **kwargs) -> None:
        """Copy text to clipboard."""
        try:
            if self.pyperclip is not None:
                self.pyperclip.copy(text)
                return

            # Native fallback if pyperclip is not available
            if self._platform == "Windows":
                try:
                    import win32clipboard
                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(text)
                    win32clipboard.CloseClipboard()
                except ImportError:
                    # Read from stdin instead of interpolating transcription
                    # text into a shell command.
                    cmd = 'Set-Clipboard -Value ([Console]::In.ReadToEnd())'
                    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], input=text, text=True, check=True)
            elif self._platform == "Darwin":
                subprocess.run(["pbcopy"], input=text.encode('utf-8'), check=True)
            else:  # Linux
                if shutil.which("xclip"):
                    subprocess.run(["xclip", "-selection", "clipboard"], 
                                 input=text.encode('utf-8'), check=True)
                elif shutil.which("xsel"):
                    subprocess.run(["xsel", "--clipboard", "--input"],
                                 input=text.encode('utf-8'), check=True)
                else:
                    raise RuntimeError("Neither xclip nor xsel found on Linux.")
        except Exception as e:
            print(f"Clipboard output error: {e}")
    
    def is_available(self) -> bool:
        """Check the actual clipboard backend instead of assuming availability."""
        if self.pyperclip is not None:
            try:
                return bool(self.pyperclip.is_available())
            except Exception:
                return True
        if self._platform == "Windows":
            return shutil.which("powershell") is not None
        if self._platform == "Darwin":
            return shutil.which("pbcopy") is not None
        return shutil.which("xclip") is not None or shutil.which("xsel") is not None
    
    @property
    def platform(self) -> str:
        """Get the platform name."""
        return self._platform
    
    @property
    def supported_platforms(self) -> List[str]:
        """Get supported platforms."""
        return ["Windows", "Darwin", "Linux"]


class PyAutoGUIOutputHandler(AbstractOutputHandler):
    """PyAutoGUI output handler (cross-platform)."""
    
    def __init__(self, config=None):
        self.config = config
        self._platform = platform.system()
        
        try:
            import pyautogui
            import pyperclip
            self.pyautogui = pyautogui
            self.pyperclip = pyperclip
            self.pyautogui.PAUSE = 0
        except ImportError as e:
            raise ImportError(f"pyautogui and pyperclip are required. Install: pip install pyautogui pyperclip ({e})")
    
    def output(self, text: str, **kwargs) -> None:
        """Type text using PyAutoGUI via clipboard (supports Unicode)."""
        try:
            # Save original clipboard content
            original_clipboard = None
            try:
                original_clipboard = self.pyperclip.paste()
            except Exception:
                pass
            
            # Copy to clipboard
            self.pyperclip.copy(text)
            
            import time
            time.sleep(0.05)
            
            # Paste using Ctrl+V (or Cmd+V on macOS)
            if self._platform == "Darwin":
                self.pyautogui.hotkey('command', 'v')
            else:
                self.pyautogui.hotkey('ctrl', 'v')
            
            time.sleep(0.05)
            
            # Restore original clipboard content
            if original_clipboard is not None:
                try:
                    self.pyperclip.copy(original_clipboard)
                except Exception:
                    pass
        except Exception as e:
            print(f"PyAutoGUI error: {e}")
    
    def is_available(self) -> bool:
        """PyAutoGUI is available on all platforms (with Wayland warning on Linux)."""
        if self._platform == "Linux":
            session_type = os.getenv("XDG_SESSION_TYPE", "").lower()
            if session_type == "wayland":
                # PyAutoGUI may have limitations under Wayland
                pass
        return True
    
    @property
    def platform(self) -> str:
        """Get the platform name."""
        return self._platform
    
    @property
    def supported_platforms(self) -> List[str]:
        """Get supported platforms."""
        return ["Windows", "Darwin", "Linux"]


class AutoItOutputHandler(AbstractOutputHandler):
    """AutoIt output handler (Windows only)."""

    def __init__(self, config=None):
        self.config = config
        self._platform = platform.system()
        if self._platform != "Windows":
            raise RuntimeError("AutoItOutputHandler is Windows-only")

        try:
            import autoit
            self.autoit = autoit
            self.autoit.opt("SendKeyDelay", 0)
            self.autoit.opt("SendKeyDownDelay", 0)
        except ImportError:
            raise ImportError("pyautoit is required. Install: pip install pyautoit")

    def output(self, text: str, **kwargs) -> None:
        """Type text using AutoIt with maximum speed."""
        try:
            self.autoit.send(text, 1)
        except Exception as e:
            print(f"AutoIt error: {e}")
    
    def is_available(self) -> bool:
        """AutoIt is available on Windows."""
        return self._platform == "Windows"
    
    @property
    def platform(self) -> str:
        """Get the platform name."""
        return self._platform
    
    @property
    def supported_platforms(self) -> List[str]:
        """Get supported platforms."""
        return ["Windows"]


class AppleScriptOutputHandler(AbstractOutputHandler):
    """macOS AppleScript output handler."""
    
    def __init__(self, config=None):
        self.config = config
        self._platform = platform.system()
        if self._platform != "Darwin":
            raise RuntimeError("AppleScriptOutputHandler is macOS-only")
    
    def _escape_for_applescript(self, text: str) -> str:
        """Properly escape text for AppleScript string literal."""
        # Escape backslashes first, then double quotes
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')
        return escaped

    def output(self, text: str, **kwargs) -> None:
        """Type text using AppleScript with proper character and newline escaping."""
        try:
            # Handle multi-line strings properly by splitting lines or sending return key code
            lines = text.split('\n')
            applescript_lines = []
            
            for i, line in enumerate(lines):
                escaped_line = self._escape_for_applescript(line)
                applescript_lines.append(f'keystroke "{escaped_line}"')
                if i < len(lines) - 1:
                    applescript_lines.append('key code 36')  # Return key in AppleScript
            
            script_body = "\n".join(applescript_lines)
            script = f'''
            tell application "System Events"
                {script_body}
            end tell
            '''
            subprocess.run(["osascript", "-e", script], check=True)
        except subprocess.CalledProcessError as e:
            print(f"AppleScript execution error: {e}")
            print("💡 DICA (macOS): Verifique se o Terminal tem permissão em 'Ajustes do Sistema > Privacidade e Segurança > Acessibilidade'.")
        except Exception as e:
            print(f"AppleScript error: {e}")
    
    def is_available(self) -> bool:
        """AppleScript is available on macOS."""
        return self._platform == "Darwin"
    
    @property
    def platform(self) -> str:
        """Get the platform name."""
        return self._platform
    
    @property
    def supported_platforms(self) -> List[str]:
        """Get supported platforms."""
        return ["Darwin"]


class XdotoolOutputHandler(AbstractOutputHandler):
    """Linux xdotool output handler."""
    
    def __init__(self, config=None):
        self.config = config
        self._platform = platform.system()
        if self._platform != "Linux":
            raise RuntimeError("XdotoolOutputHandler is Linux-only")
        if not shutil.which("xdotool"):
            raise RuntimeError("xdotool binary not found. Install it with `sudo apt install xdotool`.")
    
    def output(self, text: str, **kwargs) -> None:
        """Type text using xdotool."""
        try:
            subprocess.run(["xdotool", "type", "--delay", "12", text], check=True)
        except Exception as e:
            print(f"Xdotool error: {e}")
    
    def is_available(self) -> bool:
        """xdotool is available on Linux if binary exists."""
        return self._platform == "Linux" and shutil.which("xdotool") is not None
    
    @property
    def platform(self) -> str:
        """Get the platform name."""
        return self._platform
    
    @property
    def supported_platforms(self) -> List[str]:
        """Get supported platforms."""
        return ["Linux"]
