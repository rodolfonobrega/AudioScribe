param(
    [Parameter(Mandatory = $true)]
    [string]$Hotkey
)

# Windows low-level keyboard listener based on the OpenWhispr listener model.
# It emits READY, KEY_DOWN and KEY_UP lines for the requested combination.
# GetAsyncKeyState is used to repair modifier state when Windows drops a key-up
# event (a common case when the Windows key opens the Start menu or Win+L fires).
$source = @"
using System;
using System.Runtime.InteropServices;

namespace AudioScribeNative {
    public static class WindowsKeyListener {
        private const int WhKeyboardLl = 13;
        private const int HcAction = 0;
        private const int WmKeyDown = 0x0100;
        private const int WmSysKeyDown = 0x0104;
        private const int WmKeyUp = 0x0101;
        private const int WmSysKeyUp = 0x0105;
        private const uint KeyUpFlag = 0x80000000;
        private const uint VkControl = 0x11;
        private const uint VkMenu = 0x12;
        private const uint VkShift = 0x10;
        private const uint VkLWin = 0x5B;
        private const uint VkRWin = 0x5C;

        [StructLayout(LayoutKind.Sequential)]
        private struct KbdLlHookStruct {
            public uint VkCode;
            public uint ScanCode;
            public uint Flags;
            public uint Time;
            public UIntPtr DwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct Point { public int X; public int Y; }

        [StructLayout(LayoutKind.Sequential)]
        private struct Msg {
            public IntPtr Hwnd;
            public uint Message;
            public UIntPtr WParam;
            public IntPtr LParam;
            public uint Time;
            public Point Point;
        }

        private delegate IntPtr HookProc(int code, IntPtr wParam, IntPtr lParam);
        private static HookProc _hookProc = HookCallback;
        private static IntPtr _hook;
        private static uint _target;
        private static bool _modifiersOnly;
        private static bool _needCtrl;
        private static bool _needAlt;
        private static bool _needShift;
        private static bool _needWin;
        private static bool _ctrlDown;
        private static bool _altDown;
        private static bool _shiftDown;
        private static bool _leftWinDown;
        private static bool _rightWinDown;
        private static bool _active;

        [DllImport("user32.dll", SetLastError = true)]
        private static extern IntPtr SetWindowsHookEx(int idHook, HookProc callback, IntPtr module, uint threadId);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool UnhookWindowsHookEx(IntPtr hook);

        [DllImport("user32.dll")]
        private static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern short GetAsyncKeyState(int key);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr GetModuleHandle(string name);

        [DllImport("user32.dll")]
        private static extern int GetMessage(out Msg message, IntPtr hwnd, uint min, uint max);

        [DllImport("user32.dll")]
        private static extern bool TranslateMessage(ref Msg message);

        [DllImport("user32.dll")]
        private static extern IntPtr DispatchMessage(ref Msg message);

        private static bool IsCtrl(uint vk) { return vk == VkControl || vk == 0xA2 || vk == 0xA3; }
        private static bool IsAlt(uint vk) { return vk == VkMenu || vk == 0xA4 || vk == 0xA5; }
        private static bool IsShift(uint vk) { return vk == VkShift || vk == 0xA0 || vk == 0xA1; }
        private static bool IsWin(uint vk) { return vk == VkLWin || vk == VkRWin; }
        private static bool IsModifier(uint vk) { return IsCtrl(vk) || IsAlt(vk) || IsShift(vk) || IsWin(vk); }
        private static bool IsRequiredModifier(uint vk) {
            return (_needCtrl && IsCtrl(vk)) || (_needAlt && IsAlt(vk)) ||
                   (_needShift && IsShift(vk)) || (_needWin && IsWin(vk));
        }

        private static void SyncModifiers(uint current) {
            if (!IsCtrl(current)) _ctrlDown = (GetAsyncKeyState((int)VkControl) & 0x8000) != 0;
            if (!IsAlt(current)) _altDown = (GetAsyncKeyState((int)VkMenu) & 0x8000) != 0;
            if (!IsShift(current)) _shiftDown = (GetAsyncKeyState((int)VkShift) & 0x8000) != 0;
            if (current != VkLWin) _leftWinDown = (GetAsyncKeyState((int)VkLWin) & 0x8000) != 0;
            if (current != VkRWin) _rightWinDown = (GetAsyncKeyState((int)VkRWin) & 0x8000) != 0;
        }

        private static bool RequiredPressed() {
            if (_needCtrl && !_ctrlDown) return false;
            if (_needAlt && !_altDown) return false;
            if (_needShift && !_shiftDown) return false;
            if (_needWin && !_leftWinDown && !_rightWinDown) return false;
            return true;
        }

        private static void Emit(string value) {
            Console.WriteLine(value);
            Console.Out.Flush();
        }

        private static IntPtr HookCallback(int code, IntPtr wParam, IntPtr lParam) {
            if (code == HcAction) {
                var data = Marshal.PtrToStructure<KbdLlHookStruct>(lParam);
                uint vk = data.VkCode;
                bool down = wParam.ToInt32() == WmKeyDown || wParam.ToInt32() == WmSysKeyDown;
                bool up = wParam.ToInt32() == WmKeyUp || wParam.ToInt32() == WmSysKeyUp;

                if ((down || up) && IsModifier(vk)) {
                    if (IsCtrl(vk)) _ctrlDown = down;
                    else if (IsAlt(vk)) _altDown = down;
                    else if (vk == VkShift || vk == 0xA0 || vk == 0xA1) _shiftDown = down;
                    else if (vk == VkLWin) _leftWinDown = down;
                    else if (vk == VkRWin) _rightWinDown = down;
                    SyncModifiers(vk);
                }

                if (_active && up && IsRequiredModifier(vk) && !RequiredPressed()) {
                    _active = false;
                    Emit("KEY_UP");
                }

                if (_active && !_modifiersOnly && vk != _target &&
                    (GetAsyncKeyState((int)_target) & 0x8000) == 0) {
                    _active = false;
                    Emit("KEY_UP");
                }

                if (_modifiersOnly) {
                    if (down && !_active && RequiredPressed()) {
                        _active = true;
                        Emit("KEY_DOWN");
                    } else if (up && _active && !RequiredPressed()) {
                        _active = false;
                        Emit("KEY_UP");
                    }
                } else if (vk == _target) {
                    if (down && !_active && RequiredPressed()) {
                        _active = true;
                        Emit("KEY_DOWN");
                    } else if (up && _active) {
                        _active = false;
                        Emit("KEY_UP");
                    }
                }
            }
            return CallNextHookEx(_hook, code, wParam, lParam);
        }

        private static uint KeyCode(string value) {
            string key = value.Trim();
            if (key.Length == 1) return key[0];
            if (key.Equals("Space", StringComparison.OrdinalIgnoreCase)) return 0x20;
            if (key.Equals("Enter", StringComparison.OrdinalIgnoreCase)) return 0x0D;
            if (key.Equals("Tab", StringComparison.OrdinalIgnoreCase)) return 0x09;
            if (key.Equals("Escape", StringComparison.OrdinalIgnoreCase) || key.Equals("Esc", StringComparison.OrdinalIgnoreCase)) return 0x1B;
            uint f;
            if (key.StartsWith("F", StringComparison.OrdinalIgnoreCase) && uint.TryParse(key.Substring(1), out f) && f >= 1 && f <= 24) return 0x70 + f - 1;
            if (key.Equals("Pause", StringComparison.OrdinalIgnoreCase)) return 0x13;
            if (key.Equals("ScrollLock", StringComparison.OrdinalIgnoreCase)) return 0x91;
            if (key.Equals("Insert", StringComparison.OrdinalIgnoreCase)) return 0x2D;
            if (key.Equals("Delete", StringComparison.OrdinalIgnoreCase)) return 0x2E;
            if (key.Equals("Home", StringComparison.OrdinalIgnoreCase)) return 0x24;
            if (key.Equals("End", StringComparison.OrdinalIgnoreCase)) return 0x23;
            if (key.Equals("PageUp", StringComparison.OrdinalIgnoreCase)) return 0x21;
            if (key.Equals("PageDown", StringComparison.OrdinalIgnoreCase)) return 0x22;
            return 0;
        }

        private static void Parse(string hotkey) {
            _needCtrl = _needAlt = _needShift = _needWin = false;
            _target = 0;
            foreach (string raw in hotkey.Split('+')) {
                string part = raw.Trim();
                if (part.Equals("Ctrl", StringComparison.OrdinalIgnoreCase) || part.Equals("Control", StringComparison.OrdinalIgnoreCase) || part.Equals("CommandOrControl", StringComparison.OrdinalIgnoreCase)) _needCtrl = true;
                else if (part.Equals("Alt", StringComparison.OrdinalIgnoreCase) || part.Equals("Option", StringComparison.OrdinalIgnoreCase)) _needAlt = true;
                else if (part.Equals("Shift", StringComparison.OrdinalIgnoreCase)) _needShift = true;
                else if (part.Equals("Super", StringComparison.OrdinalIgnoreCase) || part.Equals("Win", StringComparison.OrdinalIgnoreCase) || part.Equals("Windows", StringComparison.OrdinalIgnoreCase) || part.Equals("Meta", StringComparison.OrdinalIgnoreCase)) _needWin = true;
                else _target = KeyCode(part);
            }
            _modifiersOnly = _target == 0 && (_needCtrl || _needAlt || _needShift || _needWin);
            if (_target == 0 && !_modifiersOnly) throw new ArgumentException("Unsupported hotkey: " + hotkey);
        }

        public static void Run(string hotkey) {
            Parse(hotkey);
            _hook = SetWindowsHookEx(WhKeyboardLl, _hookProc, GetModuleHandle(null), 0);
            if (_hook == IntPtr.Zero) throw new InvalidOperationException("Could not install Windows keyboard hook: " + Marshal.GetLastWin32Error());
            Console.CancelKeyPress += (sender, args) => { args.Cancel = true; if (_hook != IntPtr.Zero) UnhookWindowsHookEx(_hook); Environment.Exit(0); };
            Emit("READY");
            Msg message;
            while (GetMessage(out message, IntPtr.Zero, 0, 0) > 0) {
                TranslateMessage(ref message);
                DispatchMessage(ref message);
            }
            if (_hook != IntPtr.Zero) UnhookWindowsHookEx(_hook);
        }
    }
}
"@

Add-Type -TypeDefinition $source -Language CSharp
[AudioScribeNative.WindowsKeyListener]::Run($Hotkey)
