/**
 * Safe desktop output handler.
 *
 * The text is written to the clipboard first, then a fixed native paste
 * command is attempted. The text is never interpolated into a shell command.
 */

const { clipboard } = require('electron');
const { spawn, spawnSync } = require('child_process');

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function commandExists(command) {
    const probe = process.platform === 'win32' ? 'where.exe' : 'which';
    const result = spawnSync(probe, [command], { stdio: 'ignore', windowsHide: true });
    return result.status === 0;
}

function run(command, args, timeoutMs = 2000) {
    return new Promise((resolve, reject) => {
        const child = spawn(command, args, { stdio: 'ignore', windowsHide: true });
        let settled = false;
        const finish = (error) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            error ? reject(error) : resolve();
        };
        const timer = setTimeout(() => {
            child.kill();
            finish(new Error(`${command} timed out`));
        }, timeoutMs);
        child.once('error', finish);
        child.once('exit', (code) => code === 0 ? finish() : finish(new Error(`${command} exited with ${code}`)));
    });
}

function pasteStrategy() {
    if (process.platform === 'win32') {
        return { command: 'powershell.exe', args: [
            '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command',
            "Start-Sleep -Milliseconds 100; (New-Object -ComObject WScript.Shell).SendKeys('^v')"
        ], method: 'sendkeys' };
    }
    if (process.platform === 'darwin') {
        return { command: 'osascript', args: [
            '-e', 'tell application "System Events" to keystroke "v" using {command down}',
        ], method: 'osascript' };
    }
    if (process.env.WAYLAND_DISPLAY && commandExists('wtype')) {
        return { command: 'wtype', args: ['-M', 'CTRL', 'v', '-m', 'CTRL'], method: 'wtype' };
    }
    if (commandExists('xdotool')) {
        return { command: 'xdotool', args: ['key', '--clearmodifiers', 'ctrl+v'], method: 'xdotool' };
    }
    if (commandExists('ydotool')) {
        return { command: 'ydotool', args: ['key', '29:1', '47:1', '47:0', '29:0'], method: 'ydotool' };
    }
    return null;
}

function saveClipboardSnapshot() {
    try {
        const formats = clipboard.availableFormats();
        const data = {};

        const text = clipboard.readText();
        if (text) data.text = text;

        if (formats.includes('text/html')) {
            const html = clipboard.readHTML();
            if (html) data.html = html;
        }

        if (formats.includes('text/rtf') || formats.includes('public.rtf')) {
            const rtf = clipboard.readRTF();
            if (rtf) data.rtf = rtf;
        }

        if (formats.some((f) => f.startsWith('image/'))) {
            const image = clipboard.readImage();
            if (image && !image.isEmpty()) data.image = image;
        }

        const keys = Object.keys(data);
        if (keys.length === 1 && keys[0] === 'image') return { type: 'image', data: data.image };
        if (keys.length === 1 && keys[0] === 'text') return { type: 'text', data: data.text };
        if (keys.length > 0) return { type: 'formats', data };
        return { type: 'text', data: text || '' };
    } catch (_) {
        return null;
    }
}

function restoreClipboardSnapshot(original) {
    if (!original) return;
    try {
        if (original.type === 'formats') {
            clipboard.write(original.data);
        } else if (original.type === 'image') {
            clipboard.writeImage(original.data);
        } else {
            clipboard.writeText(original.data || '');
        }
    } catch (e) {
        console.warn('[OutputHandler] Clipboard restoration failed:', e);
    }
}

class NativeOutputHandler {
    constructor() {
        this.queue = Promise.resolve();
    }

    async copyAndPaste(text, options = {}) {
        if (!text || !text.trim()) return { status: 'ignored', method: null };
        const previous = this.queue.catch(() => {});
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        this.queue = previous.then(() => gate).catch(() => {});
        await previous;

        const shouldRestore = options.restoreClipboard !== false;
        const originalSnapshot = shouldRestore ? saveClipboardSnapshot() : null;

        try {
            clipboard.writeText(text);
            if (options.automatic === false) {
                return { status: 'copied', method: 'clipboard', restored: false };
            }
            const strategy = pasteStrategy();
            if (!strategy) return { status: 'copied', method: 'clipboard', restored: false };

            await delay(process.platform === 'darwin' ? 60 : 45);
            await run(strategy.command, strategy.args);
            await delay(process.platform === 'win32' ? 180 : 120);

            // Safety check: Only restore if clipboard still contains expected transcribed text
            if (shouldRestore && originalSnapshot && clipboard.readText() === text) {
                restoreClipboardSnapshot(originalSnapshot);
                return { status: 'pasted', method: strategy.method, restored: true };
            }
            return { status: 'pasted', method: strategy.method, restored: false };
        } catch (error) {
            // The text is intentionally left in the clipboard on failure.
            return { status: 'copied', method: 'clipboard', restored: false, error: error.message };
        } finally {
            release();
        }
    }

    capabilities() {
        const strategy = pasteStrategy();
        return {
            platform: process.platform,
            clipboard: true,
            automaticPaste: Boolean(strategy),
            method: strategy?.method || null,
        };
    }
}

const singleton = new NativeOutputHandler();
singleton.copyAndPaste = singleton.copyAndPaste.bind(singleton);
singleton.capabilities = singleton.capabilities.bind(singleton);

module.exports = singleton;
