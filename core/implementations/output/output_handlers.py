"""
Output Handler Implementations
Platform-specific handlers for typing transcribed text.
"""

import subprocess
import platform
from typing import List

from core.interfaces.output_handler import AbstractOutputHandler


class ConsoleOutputHandler(AbstractOutputHandler):
    """Simple console output handler."""
    
    def __init__(self, config=None):
        self.config = config
        self._platform = platform.system()
    
    def output(self, text: str, **kwargs) -> None:
        """Print text to console."""
        # Silent - output is shown via UI.show_result()
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
    """Clipboard output handler (cross-platform)."""
    
    def __init__(self, config=None):
        self.config = config
        self._platform = platform.system()
    
    def output(self, text: str, **kwargs) -> None:
        """Copy text to clipboard."""
        try:
            if self._platform == "Windows":
                import win32clipboard
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text)
                win32clipboard.CloseClipboard()
            elif self._platform == "Darwin":
                subprocess.run(["pbcopy"], input=text.encode(), check=True)
            else:  # Linux
                subprocess.run(["xclip", "-selection", "clipboard"], 
                             input=text.encode(), check=True)
            pass  # Silent operation
        except Exception as e:
            print(f"Clipboard error: {e}")
    
    def is_available(self) -> bool:
        """Clipboard is available on most platforms."""
        try:
            if self._platform == "Windows":
                import win32clipboard
            elif self._platform == "Darwin":
                pass  # pbcopy is built-in
            else:  # Linux
                pass  # xclip should be available
            return True
        except ImportError:
            return False
    
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
            # Set to maximum speed (no delay between keystrokes)
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
            except:
                pass  # Clipboard might be empty or inaccessible
            
            # Copy to clipboard
            self.pyperclip.copy(text)
            
            # Small delay to ensure clipboard is ready
            import time
            time.sleep(0.05)
            
            # Paste using Ctrl+V (or Cmd+V on macOS)
            if self._platform == "Darwin":
                self.pyautogui.hotkey('command', 'v')
            else:
                self.pyautogui.hotkey('ctrl', 'v')
            
            # Small delay before restoring clipboard
            time.sleep(0.05)
            
            # Restore original clipboard content
            if original_clipboard is not None:
                self.pyperclip.copy(original_clipboard)
            
            pass  # Silent operation
        except Exception as e:
            print(f"PyAutoGUI error: {e}")
    
    def is_available(self) -> bool:
        """PyAutoGUI is available on all platforms."""
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
        except ImportError:
            raise ImportError("pyautoit is required. Install: pip install pyautoit")
    
    def output(self, text: str, **kwargs) -> None:
        """Type text using AutoIt."""
        try:
            self.autoit.send(text)
            pass  # Silent operation
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
    
    def output(self, text: str, **kwargs) -> None:
        """Type text using AppleScript."""
        try:
            # Escape quotes properly BEFORE the f-string
            escaped_text = text.replace('"', '\\"')
            script = f'''
            tell application "System Events"
                keystroke "{escaped_text}"
            end tell
            '''
            subprocess.run(["osascript", "-e", script], check=True)
            pass  # Silent operation
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
    
    def output(self, text: str, **kwargs) -> None:
        """Type text using xdotool."""
        try:
            subprocess.run(["xdotool", "type", text], check=True)
            pass  # Silent operation
        except Exception as e:
            print(f"Xdotool error: {e}")
    
    def is_available(self) -> bool:
        """xdotool is available on Linux."""
        return self._platform == "Linux"
    
    @property
    def platform(self) -> str:
        """Get the platform name."""
        return self._platform
    
    @property
    def supported_platforms(self) -> List[str]:
        """Get supported platforms."""
        return ["Linux"]
