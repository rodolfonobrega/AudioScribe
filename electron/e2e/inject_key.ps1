param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 255)]
    [int]$VirtualKey
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class AudioScribeE2EKeyboard {
    [DllImport("user32.dll", SetLastError = true)]
    public static extern void keybd_event(byte key, byte scan, uint flags, UIntPtr extra);
    public const uint KEYEVENTF_KEYUP = 0x0002;
    public static void Tap(byte key) {
        keybd_event(key, 0, 0, UIntPtr.Zero);
        System.Threading.Thread.Sleep(80);
        keybd_event(key, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
    }
}
"@

[AudioScribeE2EKeyboard]::Tap([byte]$VirtualKey)
