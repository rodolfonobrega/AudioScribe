"""
Step 2: Standalone Global Hotkey Listener Test using pynput GlobalHotKeys
Detects global shortcut press (e.g. 'ctrl+windows' or 'f9') with 400ms debounce.
"""

import sys
import time
from pynput import keyboard

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("--- Standalone Hotkey Listener Test ---")
print("Press 'ctrl+windows' or 'f9' on your keyboard to test detection.")
print("Press Ctrl+C in terminal to exit.\n")

last_press_time = 0.0

def on_hotkey_pressed():
    global last_press_time
    now = time.perf_counter()
    if (now - last_press_time) < 0.4:
        return
    last_press_time = now
    
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [OK] HOTKEY DETECTED: Hotkey triggered successfully!")

try:
    hotkey_map = {
        '<ctrl>+<cmd>': on_hotkey_pressed,
        'f9': on_hotkey_pressed,
    }
    listener = keyboard.GlobalHotKeys(hotkey_map)
    listener.start()
    print("[OK] Hotkeys '<ctrl>+<cmd>' and 'f9' registered with pynput!")
    listener.join()
except KeyboardInterrupt:
    print("\n[OK] Hotkey listener test finished.")
except Exception as e:
    print(f"[X] ERROR registering hotkey: {e}")
