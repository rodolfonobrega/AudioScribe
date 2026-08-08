"use strict";

const assert = require("assert");
const {
    normalizeProfileAccelerator,
    registerProfileShortcuts,
} = require("../electron/src/profile_shortcuts");

function fakeGlobalShortcut(blocked = new Set()) {
    const registered = new Map();
    return {
        registered,
        register(accelerator, callback) {
            if (blocked.has(accelerator) || registered.has(accelerator)) return false;
            registered.set(accelerator, callback);
            return true;
        },
    };
}

assert.strictEqual(normalizeProfileAccelerator("Control + Alt + r"), "CommandOrControl+Alt+R");
assert.throws(() => normalizeProfileAccelerator("Control+Shift"), /non-modifier key/);
assert.throws(() => normalizeProfileAccelerator("Control+Win+R"), /Windows key/);

const globalShortcut = fakeGlobalShortcut();
const triggered = [];
const result = registerProfileShortcuts({
    globalShortcut,
    currentShortcut: "F9",
    profiles: [
        { id: "review", enabled: true, shortcut: "Control+Alt+R" },
        { id: "translate", enabled: true, shortcut: "Control+Shift+E" },
    ],
    onProfileShortcut: (profile) => triggered.push(profile.id),
});
assert.strictEqual(result.status, "ok");
assert.deepStrictEqual(result.registered, ["CommandOrControl+Alt+R", "CommandOrControl+Shift+E"]);
globalShortcut.registered.get("CommandOrControl+Alt+R")();
assert.deepStrictEqual(triggered, ["review"]);

const duplicate = registerProfileShortcuts({
    globalShortcut: fakeGlobalShortcut(),
    currentShortcut: "F9",
    profiles: [
        { id: "one", enabled: true, shortcut: "Control+Alt+R" },
        { id: "two", enabled: true, shortcut: "Ctrl+Alt+R" },
    ],
    onProfileShortcut: () => {},
});
assert.strictEqual(duplicate.status, "error");
assert.match(duplicate.failed[0].error, /another enabled profile/);

const mainConflict = registerProfileShortcuts({
    globalShortcut: fakeGlobalShortcut(),
    currentShortcut: "Control+Alt+R",
    profiles: [{ id: "review", enabled: true, shortcut: "Ctrl+Alt+R" }],
    onProfileShortcut: () => {},
});
assert.strictEqual(mainConflict.status, "error");
assert.match(mainConflict.failed[0].error, /main dictation/);

const noShortcut = registerProfileShortcuts({
    globalShortcut: fakeGlobalShortcut(),
    currentShortcut: "F9",
    profiles: [{ id: "review", enabled: true, shortcut: "" }],
    onProfileShortcut: () => {},
});
assert.deepStrictEqual(noShortcut, { status: "ok", registered: [], failed: [] });

const defaultProfileUsesNativeMainHotkey = registerProfileShortcuts({
    globalShortcut: fakeGlobalShortcut(),
    currentShortcut: "Control+Alt+R",
    profiles: [{ id: "default", isDefault: true, enabled: true, shortcut: "Control+Alt+R" }],
    onProfileShortcut: () => {},
});
assert.deepStrictEqual(defaultProfileUsesNativeMainHotkey, { status: "ok", registered: [], failed: [] });

const externalConflict = registerProfileShortcuts({
    globalShortcut: fakeGlobalShortcut(new Set(["CommandOrControl+Alt+R"])),
    currentShortcut: "F9",
    profiles: [{ id: "review", enabled: true, shortcut: "Control+Alt+R" }],
    onProfileShortcut: () => {},
});
assert.strictEqual(externalConflict.status, "error");
assert.match(externalConflict.failed[0].error, /another application/);

console.log("Profile shortcut registration checks passed.");
