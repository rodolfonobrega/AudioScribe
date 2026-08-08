"""
Step 4: Standalone Auto-Paste Test (Direct Win32 API)
Copies text to clipboard and simulates desktop paste (Ctrl+V) using Win32 keybd_event without spawning child processes.
"""

import sys
import time
import ctypes
import pyperclip

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def win32_paste_direct():
    """Simulate Ctrl+V keystroke directly via Win32 API (no focus stealing)."""
    user32 = ctypes.windll.user32
    VK_CONTROL = 0x11
    VK_V = 0x56
    KEYEVENTF_KEYUP = 0x0002

    user32.keybd_event(VK_CONTROL, 0, 0, 0)       # Ctrl down
    time.sleep(0.05)
    user32.keybd_event(VK_V, 0, 0, 0)             # V down
    time.sleep(0.05)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0) # V up
    time.sleep(0.05)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0) # Ctrl up

def copy_and_paste(text="[AudioScribe Auto-Paste Test Message]"):
    """Copy text to clipboard and simulate Ctrl+V keystroke on Windows."""
    print("--- Standalone Auto-Paste Test ---")
    print(f"Text to paste: \"{text}\"")
    
    # 1. Copy to clipboard
    pyperclip.copy(text)
    print("[OK] Text copied to system clipboard.")
    
    # 2. Give user 5 seconds to click into Notepad or any active text box
    print("\n[!] IMPORTANT: Click into any text field (Notepad, Word, Browser, etc.) in the next 5 seconds!")
    for i in range(5, 0, -1):
        print(f"   Pasting in {i}...")
        time.sleep(1)
        
    try:
        win32_paste_direct()
        print("[OK] Sent Win32 Ctrl+V keypress successfully!")
        return True
    except Exception as e:
        print(f"[X] ERROR simulating paste: {e}")
        return False

if __name__ == '__main__':
    copy_and_paste()
