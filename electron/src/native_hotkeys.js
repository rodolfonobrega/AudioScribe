"use strict";

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { uIOhook, UiohookKey } = require("uiohook-napi");

const MODIFIER_KEYCODES = new Set([
    UiohookKey.Ctrl,
    UiohookKey.CtrlRight,
    UiohookKey.Alt,
    UiohookKey.AltRight,
    UiohookKey.Shift,
    UiohookKey.ShiftRight,
    UiohookKey.Meta,
    UiohookKey.MetaRight,
]);

const MODIFIER_ALIASES = new Map([
    ["ctrl", "ctrl"],
    ["control", "ctrl"],
    ["commandorcontrol", "ctrl"],
    ["alt", "alt"],
    ["option", "alt"],
    ["shift", "shift"],
    ["meta", "meta"],
    ["command", "meta"],
    ["super", "meta"],
    ["win", "meta"],
    ["windows", "meta"],
]);

let hookStarted = false;
let activeShortcut = null;
let windowsListener = null;
const pressedKeycodes = new Set();

function resolveWindowsListenerScript() {
    const fileName = "windows-key-listener.ps1";
    const candidates = [
        process.resourcesPath ? path.join(process.resourcesPath, "bin", fileName) : null,
        path.join(__dirname, "..", "bin", fileName),
    ].filter(Boolean);
    return candidates.find((candidate) => {
        try { return fs.statSync(candidate).isFile(); } catch (_) { return false; }
    }) || null;
}

function stopWindowsListener() {
    if (!windowsListener) return;
    const child = windowsListener;
    windowsListener = null;
    try { child.kill(); } catch (_) { /* already exited */ }
}

function configureWindowsListener(shortcut, state) {
    const script = resolveWindowsListenerScript();
    if (!script) return null;

    stopWindowsListener();
    const powershell = process.env.SystemRoot
        ? path.join(process.env.SystemRoot, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        : "powershell.exe";
    const child = spawn(powershell, [
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-File", script,
        "-Hotkey", String(shortcut),
    ], { stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    windowsListener = child;

    let lineBuffer = "";
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
        lineBuffer += chunk;
        const lines = lineBuffer.split(/\r?\n/);
        lineBuffer = lines.pop();
        for (const raw of lines) {
            const line = raw.trim();
            if (line === "KEY_DOWN" && !state.active) {
                state.active = true;
                state.onPress();
            } else if (line === "KEY_UP" && state.active) {
                state.active = false;
                state.onRelease();
            }
        }
    });
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk) => {
        const message = String(chunk || "").trim();
        if (message) console.warn(`[NativeHotkey] Windows listener: ${message}`);
    });
    child.on("error", (error) => {
        if (windowsListener === child) windowsListener = null;
        console.error("[NativeHotkey] Windows listener failed:", error.message);
    });
    child.on("exit", (code, signal) => {
        if (windowsListener === child) windowsListener = null;
        if (state.active) {
            state.active = false;
            state.onRelease();
        }
        if (code !== 0 && code !== null) {
            console.error(`[NativeHotkey] Windows listener exited with code ${code}${signal ? ` (${signal})` : ""}`);
        }
    });
    return { status: "ok", shortcut, backend: "windows-low-level-hook" };
}

function normalizeKeyName(value) {
    const key = String(value || "").trim();
    if (key === " ") return "Space";
    if (key.toLowerCase() === "esc") return "Escape";
    if (key.toLowerCase() === "return") return "Enter";
    return key.length === 1 ? key.toUpperCase() : key;
}

function parseShortcut(shortcut) {
    const parts = String(shortcut || "F9")
        .split("+")
        .map((part) => part.trim())
        .filter(Boolean);
    const modifiers = new Set();
    let triggerKey = null;

    for (const part of parts) {
        const normalized = part.toLowerCase();
        const modifier = MODIFIER_ALIASES.get(normalized);
        if (modifier) {
            modifiers.add(modifier);
            continue;
        }

        const keyName = normalizeKeyName(part);
        const keycode = UiohookKey[keyName];
        if (keycode === undefined) {
            throw new Error(`Unsupported global hotkey key: ${part}`);
        }
        if (triggerKey !== null) {
            throw new Error(`Global hotkey has more than one non-modifier key: ${shortcut}`);
        }
        triggerKey = { name: keyName, keycode };
    }

    return { modifiers, triggerKey };
}

function hasRequiredModifiers(modifiers) {
    const modifierPressed = (name) => {
        if (name === "ctrl") return pressedKeycodes.has(UiohookKey.Ctrl) || pressedKeycodes.has(UiohookKey.CtrlRight);
        if (name === "alt") return pressedKeycodes.has(UiohookKey.Alt) || pressedKeycodes.has(UiohookKey.AltRight);
        if (name === "shift") return pressedKeycodes.has(UiohookKey.Shift) || pressedKeycodes.has(UiohookKey.ShiftRight);
        if (name === "meta") return pressedKeycodes.has(UiohookKey.Meta) || pressedKeycodes.has(UiohookKey.MetaRight);
        return false;
    };
    return [...modifiers].every(modifierPressed);
}

function isRequiredModifierKey(keycode, modifiers) {
    if (modifiers.has("ctrl") && (keycode === UiohookKey.Ctrl || keycode === UiohookKey.CtrlRight)) return true;
    if (modifiers.has("alt") && (keycode === UiohookKey.Alt || keycode === UiohookKey.AltRight)) return true;
    if (modifiers.has("shift") && (keycode === UiohookKey.Shift || keycode === UiohookKey.ShiftRight)) return true;
    if (modifiers.has("meta") && (keycode === UiohookKey.Meta || keycode === UiohookKey.MetaRight)) return true;
    return false;
}

function eventStartsShortcut(event, shortcut) {
    if (!hasRequiredModifiers(shortcut.modifiers)) return false;
    if (shortcut.triggerKey) return event.keycode === shortcut.triggerKey.keycode;
    return MODIFIER_KEYCODES.has(event.keycode) && isRequiredModifierKey(event.keycode, shortcut.modifiers);
}

function eventEndsShortcut(event, shortcut) {
    if (shortcut.triggerKey && event.keycode === shortcut.triggerKey.keycode) return true;
    return isRequiredModifierKey(event.keycode, shortcut.modifiers);
}

function ensureHookStarted() {
    if (hookStarted) return;
    uIOhook.start();
    hookStarted = true;
}

function configure(shortcut, { onPress, onRelease } = {}) {
    const parsed = parseShortcut(shortcut);
    const state = {
        ...parsed,
        active: false,
        onPress: typeof onPress === "function" ? onPress : () => {},
        onRelease: typeof onRelease === "function" ? onRelease : () => {},
    };

    if (process.platform === "win32") {
        const windowsResult = configureWindowsListener(shortcut, state);
        if (windowsResult) {
            activeShortcut = state;
            return windowsResult;
        }
    }

    pressedKeycodes.clear();
    if (activeShortcut) activeShortcut.active = false;
    activeShortcut = state;
    ensureHookStarted();
    return { status: "ok", shortcut, backend: "uiohook-napi" };
}

uIOhook.on("keydown", (event) => {
    pressedKeycodes.add(event.keycode);
    const shortcut = activeShortcut;
    if (!shortcut || shortcut.active || !eventStartsShortcut(event, shortcut)) return;
    shortcut.active = true;
    shortcut.onPress(event);
});

uIOhook.on("keyup", (event) => {
    const shortcut = activeShortcut;
    if (shortcut && shortcut.active && eventEndsShortcut(event, shortcut)) {
        shortcut.active = false;
        shortcut.onRelease(event);
    }
    pressedKeycodes.delete(event.keycode);
});

function stop() {
    stopWindowsListener();
    activeShortcut = null;
    pressedKeycodes.clear();
    if (!hookStarted) return;
    uIOhook.stop();
    hookStarted = false;
}

module.exports = {
    configure,
    parseShortcut,
    stop,
};
