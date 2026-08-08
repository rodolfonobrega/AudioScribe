"""
Keyboard Listener Implementation
Uses the keyboard library or pynput for cross-platform keyboard hotkey detection without requiring root.
"""

import threading
import platform
import time
from typing import Callable, Optional

from core.utils.preflight import safe_print

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


def _format_pynput_hotkey(hotkey_str: str) -> str:
    """Format hotkey string for pynput GlobalHotKeys (e.g. 'ctrl+windows' -> '<ctrl>+<cmd>')."""
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    formatted = []
    for p in parts:
        if p in ("ctrl", "control"):
            formatted.append("<ctrl>")
        elif p in ("win", "windows", "super", "cmd"):
            formatted.append("<cmd>")
        elif p in ("alt", "option"):
            formatted.append("<alt>")
        elif p in ("shift",):
            formatted.append("<shift>")
        else:
            formatted.append(p)
    return "+".join(formatted)


class KeyboardListener(AbstractKeyboardListener):
    """Keyboard listener implementation using pynput Listener for robust modifier state tracking."""
    
    def __init__(self, config):
        self.config = config
        self.hotkey = config.hotkey.lower().strip()
        self.mode = config.mode
        
        self._is_running = False
        self._is_recording = False
        self._callback_press = None
        self._callback_release = None
        self._hotkey_registered = False
        self._lock = threading.Lock()
        self._backend = None  # 'pynput' or 'keyboard'
        self._pynput_listener = None
    
    def _safe_dispatch_press(self):
        try:
            if self._callback_press:
                self._callback_press()
        except Exception as e:
            print(f"[KeyboardListener] Error in hotkey press callback: {e}")

    def _safe_dispatch_release(self):
        try:
            if self._callback_release:
                self._callback_release()
        except Exception as e:
            print(f"[KeyboardListener] Error in hotkey release callback: {e}")

    def _on_key_down(self, event=None):
        """Internal callback when hotkey is triggered."""
        mode = str(getattr(self, "mode", "")).lower()
        if mode in ("push_to_talk", "hold"):
            with self._lock:
                self._is_recording = True
            threading.Thread(target=self._safe_dispatch_press, daemon=True).start()
        else:
            with self._lock:
                self._is_recording = not self._is_recording
                is_rec = self._is_recording
            if is_rec:
                threading.Thread(target=self._safe_dispatch_press, daemon=True).start()
            else:
                threading.Thread(target=self._safe_dispatch_release, daemon=True).start()

    def _on_key_up(self, event=None):
        """Internal callback when key is released in push_to_talk mode."""
        mode = str(getattr(self, "mode", "")).lower()
        if mode in ("push_to_talk", "hold"):
            with self._lock:
                if self._is_recording:
                    self._is_recording = False
                    threading.Thread(target=self._safe_dispatch_release, daemon=True).start()

    def start(self, on_press: Callable[[], None], on_release: Optional[Callable[[], None]] = None) -> None:
        if self._is_running:
            return
        
        self._callback_press = on_press
        self._callback_release = on_release
        self._is_running = True
        self._listener_thread = threading.Thread(target=self._run_listener, daemon=True)
        self._listener_thread.start()

    def _create_pynput_listener(self, hotkey_str: str):
        if pynput is None:
            return None
        from pynput.keyboard import Key as PynputKey, Listener as PynputListener
        
        hk_clean = hotkey_str.lower().replace("control", "ctrl").replace("windows", "win").replace("super", "win")
        target_parts = set(p.strip() for p in hk_clean.split("+"))
        
        pressed_modifiers = set()
        last_trigger_time = 0.0

        def on_press_handler(key):
            nonlocal last_trigger_time
            if key in (PynputKey.ctrl, PynputKey.ctrl_l, PynputKey.ctrl_r):
                pressed_modifiers.add("ctrl")
            if key in (PynputKey.cmd, PynputKey.cmd_l, PynputKey.cmd_r):
                pressed_modifiers.add("win")
            if key in (PynputKey.alt, PynputKey.alt_l, PynputKey.alt_r, PynputKey.alt_gr):
                pressed_modifiers.add("alt")
            if key in (PynputKey.shift, PynputKey.shift_l, PynputKey.shift_r):
                pressed_modifiers.add("shift")
            
            key_name = None
            if hasattr(key, "name") and key.name:
                key_name = key.name.lower()
            elif hasattr(key, "char") and key.char:
                key_name = key.char.lower()
            else:
                key_name = str(key).lower()

            matched = True
            for part in target_parts:
                if part in ("ctrl", "win", "alt", "shift"):
                    if part not in pressed_modifiers:
                        matched = False
                        break
                elif part != key_name:
                    matched = False
                    break

            if matched:
                now = time.perf_counter()
                if (now - last_trigger_time) > 0.4:
                    last_trigger_time = now
                    self._on_key_down()

        def on_release_handler(key):
            released_mod = None
            if key in (PynputKey.ctrl, PynputKey.ctrl_l, PynputKey.ctrl_r):
                pressed_modifiers.discard("ctrl")
                released_mod = "ctrl"
            if key in (PynputKey.cmd, PynputKey.cmd_l, PynputKey.cmd_r):
                pressed_modifiers.discard("win")
                released_mod = "win"
            if key in (PynputKey.alt, PynputKey.alt_l, PynputKey.alt_r, PynputKey.alt_gr):
                pressed_modifiers.discard("alt")
                released_mod = "alt"
            if key in (PynputKey.shift, PynputKey.shift_l, PynputKey.shift_r):
                pressed_modifiers.discard("shift")
                released_mod = "shift"

            key_name = None
            if hasattr(key, "name") and key.name:
                key_name = key.name.lower()
            elif hasattr(key, "char") and key.char:
                key_name = key.char.lower()

            if str(getattr(self, "mode", "")).lower() in ("push_to_talk", "hold"):
                if (released_mod and released_mod in target_parts) or (key_name and key_name in target_parts):
                    self._on_key_up()

        return PynputListener(on_press=on_press_handler, on_release=on_release_handler)

    def _run_listener(self):
        """Run keyboard listener thread using pynput state listener with keyboard fallback."""
        if pynput is not None:
            try:
                self._backend = 'pynput'
                self._pynput_listener = self._create_pynput_listener(self.hotkey)
                if self._pynput_listener:
                    self._pynput_listener.start()
                    print(f"[KeyboardListener] Hotkey '{self.hotkey}' registered via pynput state listener.")
                    self._pynput_listener.join()
                    return
            except Exception as e:
                print(f"Notice: pynput listener initialization failed ({e}). Trying fallback...")

        # Fallback: keyboard module
        if keyboard is not None:
            try:
                hk = self.hotkey.lower().replace("control", "ctrl").replace("super", "windows")
                if "+" in hk:
                    keyboard.add_hotkey(hk, self._on_key_down, suppress=False)
                else:
                    keyboard.on_press_key(hk, self._on_key_down, suppress=False)
                    keyboard.on_release_key(hk, self._on_key_up, suppress=False)
                self._hotkey_registered = True
                self._backend = 'keyboard'
                keyboard.wait()
                return
            except Exception as e:
                print(f"Error running keyboard listener: {e}")

        safe_print("WARNING: Could not initialize any keyboard listener backend.")

    def stop(self) -> None:
        if not self._is_running:
            return
        self._is_running = False
        if self._pynput_listener:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass
        if keyboard is not None:
            try:
                keyboard.unhook_all()
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._is_recording
    
    @is_recording.setter
    def is_recording(self, value: bool):
        with self._lock:
            self._is_recording = value
    
    @property
    def platform(self) -> str:
        return platform.system()

    def register_hotkey(self, hotkey: str, callback: Optional[Callable] = None) -> None:
        """Register a new hotkey dynamically."""
        self.hotkey = hotkey.lower().strip()
        if callback:
            self._callback = callback
        
        # Stop existing listener and restart with new hotkey
        if self._pynput_listener:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass
            self._pynput_listener = None

        if keyboard is not None:
            try:
                keyboard.unhook_all()
            except Exception:
                pass

        if pynput is not None:
            try:
                self._backend = 'pynput'
                self._pynput_listener = self._create_pynput_listener(self.hotkey)
                if self._pynput_listener:
                    self._pynput_listener.start()
                    print(f"[KeyboardListener] Dynamic hotkey updated to '{self.hotkey}' via pynput state listener.")
                    return
            except Exception as e:
                print(f"[KeyboardListener] Error updating pynput hotkey: {e}")

        if keyboard is not None:
            try:
                hk = self.hotkey.replace("control", "ctrl").replace("super", "windows")
                if "+" in hk:
                    keyboard.add_hotkey(hk, self._on_key_down, suppress=False)
                else:
                    keyboard.on_press_key(hk, self._on_key_down, suppress=False)
                    keyboard.on_release_key(hk, self._on_key_up, suppress=False)
                print(f"[KeyboardListener] Dynamic hotkey updated to '{hk}' via keyboard module.")
            except Exception as e:
                print(f"[KeyboardListener] Error registering hotkey '{self.hotkey}': {e}")

    def unregister_hotkey(self, hotkey: str) -> None:
        """Unregister a hotkey."""
        if self.hotkey == hotkey.lower().strip():
            if keyboard is not None:
                try:
                    keyboard.unhook_all()
                except Exception:
                    pass
            self._callback = None
