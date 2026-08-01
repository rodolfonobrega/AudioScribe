/**
 * Pure Node.js Output Handler for Electron Desktop App.
 * Copies text to system clipboard and simulates paste.
 */

const { clipboard } = require('electron');

class NativeOutputHandler {
    static copyToClipboard(text) {
        if (!text) return;
        clipboard.writeText(text);
    }
}

module.exports = NativeOutputHandler;
