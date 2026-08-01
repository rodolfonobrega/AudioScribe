/**
 * Pure Node.js Output Handler for Electron Desktop App.
 * Copies text to system clipboard and simulates native auto-paste.
 */

const { clipboard } = require('electron');
const { exec } = require('child_process');

class NativeOutputHandler {
    static copyAndPaste(text) {
        if (!text) return;

        // 1. Copy to clipboard
        clipboard.writeText(text);

        // 2. Simulate Paste into Active Window
        const platform = process.platform;
        if (platform === 'win32') {
            const vbsScript = 'Set WshShell = WScript.CreateObject("WScript.Shell")\nWScript.Sleep 50\nWshShell.SendKeys "^v"';
            exec(`powershell -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('^{v}')"`, (err) => {
                if (err) {
                    // Fallback to VBScript SendKeys
                    const cmd = `mshta vbscript:Execute("CreateObject(""WScript.Shell"").SendKeys(""^v""):close")`;
                    exec(cmd);
                }
            });
        } else if (platform === 'darwin') {
            const cmd = `osascript -e 'tell application "System Events" to keystroke "v" using command down'`;
            exec(cmd);
        } else if (platform === 'linux') {
            const cmd = `xdotool key ctrl+v`;
            exec(cmd);
        }
    }
}

module.exports = NativeOutputHandler;
