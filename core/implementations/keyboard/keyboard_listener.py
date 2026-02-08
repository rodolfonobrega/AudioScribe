"""
Keyboard Listener Implementation
Uses the keyboard library for cross-platform keyboard hotkey detection.
"""

import threading
import queue
from typing import Callable

import keyboard

from core.interfaces.keyboard_listener import AbstractKeyboardListener


class KeyboardListener(AbstractKeyboardListener):
    """Keyboard listener implementation using the keyboard library."""
    
    def __init__(self, config):
        """
        Initialize keyboard listener.
        
        Args:
            config: Keyboard configuration
        """
        self.config = config
        self.hotkey = config.hotkey
        self.mode = config.mode
        
        self._is_running = False
        self._is_recording = False
        self._callback = None
        self._hotkey_registered = False
        self._lock = threading.Lock()
    
    def _on_key_down(self, event):
        """Internal callback when key is pressed down."""
        if self.mode == "push_to_talk":
            with self._lock:
                if not self._is_recording:
                    self._is_recording = True
                    if self._callback:
                        self._callback()
        else:  # toggle mode
            # Only toggle on initial press, not on key repeat
            if not event.name in getattr(self, '_pressed_keys', set()):
                if not hasattr(self, '_pressed_keys'):
                    self._pressed_keys = set()
                self._pressed_keys.add(event.name)
                
                with self._lock:
                    if self._is_recording:
                        self._is_recording = False
                    else:
                        self._is_recording = True
                
                if self._callback:
                    self._callback()
    
    def _on_key_up(self, event):
        """Internal callback when key is released."""
        # Clean up pressed keys tracking for toggle mode
        if hasattr(self, '_pressed_keys') and event.name in self._pressed_keys:
            self._pressed_keys.remove(event.name)
        
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
        self._pressed_keys = set()
        
        # Register hotkey in a separate thread
        self._listener_thread = threading.Thread(target=self._run_listener, daemon=True)
        self._listener_thread.start()
    
    def _run_listener(self):
        """Run keyboard listener in a separate thread."""
        try:
            # Register key down and up handlers
            keyboard.on_press_key(self.hotkey, self._on_key_down, suppress=False)
            keyboard.on_release_key(self.hotkey, self._on_key_up, suppress=False)
            self._hotkey_registered = True
            
            # Keep thread alive
            keyboard.wait()
        except Exception as e:
            print(f"Keyboard listener error: {e}")
    
    def stop(self) -> None:
        """Stop listening for keyboard events."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        # Remove hotkey
        if self._hotkey_registered:
            try:
                keyboard.remove_hotkey(self.hotkey)
                self._hotkey_registered = False
            except Exception as e:
                print(f"Error removing hotkey: {e}")
        
        # Unhook all keyboard hooks
        try:
            keyboard.unhook_all()
        except Exception as e:
            print(f"Error unhooking keyboard: {e}")
    
    def register_hotkey(self, hotkey: str, callback: Callable) -> None:
        """Register a hotkey."""
        try:
            keyboard.add_hotkey(hotkey, callback)
        except Exception as e:
            print(f"Error registering hotkey '{hotkey}': {e}")
    
    def unregister_hotkey(self, hotkey: str) -> None:
        """Unregister a hotkey."""
        try:
            keyboard.remove_hotkey(hotkey)
        except Exception as e:
            print(f"Error unregistering hotkey '{hotkey}': {e}")
    
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
        import platform
        return platform.system()
