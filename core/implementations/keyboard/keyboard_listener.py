"""
Keyboard Listener Implementation
Uses the keyboard library or pynput for cross-platform keyboard hotkey detection without requiring root.
"""

import threading
import platform
from typing import Callable, Optional

# Try importing keyboard and pynput
try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import pynput
    from pynput.keyboard import Key, Listener as PynputListener
except ImportError:
    pynput = None

from core.interfaces.keyboard_listener import AbstractKeyboardListener


class KeyboardListener(AbstractKeyboardListener):
    """Keyboard listener implementation with pynput fallback for unprivileged execution."""
    
    def __init__(self, config):
        """
        Initialize keyboard listener.
        
        Args:
            config: Keyboard configuration
        """
        self.config = config
        self.hotkey = config.hotkey.lower().strip()
        self.mode = config.mode
        
        self._is_running = False
        self._is_recording = False
        self._callback = None
        self._hotkey_registered = False
        self._lock = threading.Lock()
        self._backend = None  # 'keyboard' or 'pynput'
        self._pynput_listener = None
    
    def _on_key_down(self, event=None):
        """Internal callback when key is pressed down."""
        if self.mode == "push_to_talk":
            with self._lock:
                if not self._is_recording:
                    self._is_recording = True
                    if self._callback:
                        self._callback()
        else:  # toggle mode
            with self._lock:
                self._is_recording = not self._is_recording
            if self._callback:
                self._callback()

    def _on_key_up(self, event=None):
        """Internal callback when key is released."""
        if self.mode == "push_to_talk":
            with self._lock:
                if self._is_recording:
                    self._is_recording = False
                    if self._callback:
                        self._callback()

    def start(self, on_press: Callable[[], None]) -> None:
        """
        Start listening for keyboard events.
        
        Args:
            on_press: Callback when hotkey is pressed
        """
        if self._is_running:
            print("Keyboard listener already running")
            return
        
        self._callback = on_press
        self._is_running = True
        
        # Try running listener with 'keyboard' module first, fallback to 'pynput'
        self._listener_thread = threading.Thread(target=self._run_listener, daemon=True)
        self._listener_thread.start()

    def _run_listener(self):
        """Run keyboard listener thread with fallback."""
        # Try keyboard library if available
        if keyboard is not None:
            try:
                keyboard.on_press_key(self.hotkey, self._on_key_down, suppress=False)
                keyboard.on_release_key(self.hotkey, self._on_key_up, suppress=False)
                self._hotkey_registered = True
                self._backend = 'keyboard'
                keyboard.wait()
                return
            except Exception as e:
                print(f"Notice: 'keyboard' backend initialization failed ({e}). Trying 'pynput' fallback...")

        # Fallback to pynput
        if pynput is not None:
            try:
                self._backend = 'pynput'
                target_key = self._parse_pynput_key(self.hotkey)
                
                def on_press(key):
                    if self._matches_pynput_key(key, target_key):
                        self._on_key_down()

                def on_release(key):
                    if self._matches_pynput_key(key, target_key):
                        self._on_key_up()

                self._pynput_listener = PynputListener(on_press=on_press, on_release=on_release)
                self._pynput_listener.start()
                self._pynput_listener.join()
                return
            except Exception as e:
                print(f"Error running pynput listener: {e}")

        print("⚠️ Warning: Could not initialize any keyboard listener backend (install keyboard or pynput).")

    def _parse_pynput_key(self, hotkey_str: str):
        """Convert string hotkey representation to pynput Key or char."""
        key_str = hotkey_str.lower().strip()
        if hasattr(Key, key_str):
            return getattr(Key, key_str)
        return key_str

    def _matches_pynput_key(self, key, target_key):
        """Check if pressed key matches target key."""
        if isinstance(target_key, Key):
            return key == target_key
        if hasattr(key, 'char') and key.char:
            return key.char.lower() == str(target_key).lower()
        return False

    def stop(self) -> None:
        """Stop listening for keyboard events."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._backend == 'keyboard' and keyboard is not None:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        elif self._backend == 'pynput' and self._pynput_listener:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        """Check if listener is running."""
        return self._is_running
    
    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        with self._lock:
            return self._is_recording
    
    @is_recording.setter
    def is_recording(self, value: bool):
        """Set recording state."""
        with self._lock:
            self._is_recording = value
    
    @property
    def platform(self) -> str:
        """Get the platform name."""
        return platform.system()
