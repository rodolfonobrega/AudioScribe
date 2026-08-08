"use strict";

function normalizeProfileAccelerator(shortcut) {
    const source = String(shortcut || "").trim();
    if (!source) throw new Error("A profile shortcut is required.");

    const parts = source.split("+").map((part) => part.trim()).filter(Boolean);
    const normalized = [];
    const modifiers = new Set(["commandorcontrol", "ctrl", "control", "shift", "alt", "meta", "super", "win", "windows"]);
    let hasKey = false;

    for (const part of parts) {
        const lower = part.toLowerCase();
        if (lower === "ctrl" || lower === "control" || lower === "commandorcontrol") {
            normalized.push("CommandOrControl");
        } else if (lower === "shift") {
            normalized.push("Shift");
        } else if (lower === "alt") {
            normalized.push("Alt");
        } else if (lower === "super" || lower === "win" || lower === "windows" || lower === "meta") {
            throw new Error("The Windows key cannot be used for a profile shortcut. Choose Ctrl, Alt, Shift, and a regular key.");
        } else {
            normalized.push(part.length === 1 ? part.toUpperCase() : part);
            hasKey = true;
        }
    }

    if (!hasKey || parts.every((part) => modifiers.has(part.toLowerCase()))) {
        throw new Error("Shortcuts must include a non-modifier key, such as F9, Space, or A-Z.");
    }
    return normalized.join("+");
}

function shortcutIdentity(shortcut) {
    return String(shortcut || "")
        .replace(/CommandOrControl/gi, "control")
        .replace(/ctrl/gi, "control")
        .replace(/\s*\+\s*/g, "+")
        .toLowerCase();
}

function registerProfileShortcuts({ globalShortcut, profiles, currentShortcut, onProfileShortcut }) {
    const previous = Array.isArray(profiles) ? profiles : [];
    // The primary profile is triggered by the native main hotkey, not by
    // Electron's globalShortcut registry. This also supports Ctrl+Win on
    // Windows, which globalShortcut cannot register reliably.
    const active = previous.filter((profile) => profile && !profile.isDefault && profile.enabled && profile.shortcut);
    const prepared = [];
    const failed = [];
    const seen = new Set();
    const mainShortcut = shortcutIdentity(currentShortcut);

    for (const profile of active) {
        try {
            const accelerator = normalizeProfileAccelerator(profile.shortcut);
            const identity = shortcutIdentity(accelerator);
            if (identity === mainShortcut) throw new Error("This shortcut is already used by the main dictation action.");
            if (seen.has(identity)) throw new Error("This shortcut is already used by another enabled profile.");
            seen.add(identity);
            prepared.push({ profile, accelerator });
        } catch (error) {
            failed.push({ profileId: profile.id, shortcut: profile.shortcut, error: error.message });
        }
    }

    if (failed.length) return { status: "error", registered: [], failed };

    const registered = [];
    for (const { profile, accelerator } of prepared) {
        try {
            if (!globalShortcut.register(accelerator, () => onProfileShortcut(profile))) {
                failed.push({ profileId: profile.id, shortcut: profile.shortcut, error: "This shortcut is already in use by another application." });
                break;
            }
            registered.push(accelerator);
        } catch (error) {
            failed.push({ profileId: profile.id, shortcut: profile.shortcut, error: error.message });
            break;
        }
    }

    return failed.length
        ? { status: "error", registered, failed }
        : { status: "ok", registered, failed: [] };
}

module.exports = { normalizeProfileAccelerator, registerProfileShortcuts, shortcutIdentity };
