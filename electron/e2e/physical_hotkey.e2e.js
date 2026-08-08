const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');

const appDirectory = path.resolve(__dirname, '..');

function delay(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

async function waitForDebugEndpoint(port) {
    const deadline = Date.now() + 15_000;
    while (Date.now() < deadline) {
        const ready = await new Promise((resolve) => {
            const request = http.get(`http://127.0.0.1:${port}/json/version`, (response) => {
                response.resume();
                resolve(response.statusCode === 200);
            });
            request.on('error', () => resolve(false));
        });
        if (ready) return;
        await delay(100);
    }
    throw new Error('Electron DevTools endpoint did not become available.');
}

async function firstRendererPage(context) {
    const deadline = Date.now() + 15_000;
    while (Date.now() < deadline) {
        const page = context.pages().find((candidate) => candidate.url().startsWith('file:'));
        if (page) return page;
        await delay(100);
    }
    throw new Error('Electron renderer page did not open.');
}

function injectF9() {
    const script = path.join(__dirname, 'inject_key.ps1');
    return new Promise((resolve, reject) => {
        const child = spawn('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', script, '-VirtualKey', '120'], { windowsHide: true });
        child.once('error', reject);
        child.once('exit', (code) => code === 0 ? resolve() : reject(new Error(`Keyboard injector exited with ${code}.`)));
    });
}

async function main() {
    if (process.platform !== 'win32') throw new Error('Physical hotkey E2E runs only on Windows.');
    const env = { ...process.env, AUDIOSCRIBE_E2E: '1', AUDIOSCRIBE_E2E_PHYSICAL_HOTKEY: '1' };
    delete env.ELECTRON_RUN_AS_NODE;
    const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'audioscribe-hotkey-e2e-'));
    const port = 9700 + Math.floor(Math.random() * 200);
    const app = spawn(require('electron'), [`--remote-debugging-port=${port}`, `--user-data-dir=${userData}`, appDirectory], { cwd: appDirectory, env, stdio: 'pipe', windowsHide: true });
    let browser;

    try {
        await waitForDebugEndpoint(port);
        browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
        const page = await firstRendererPage(browser.contexts()[0]);
        page.setDefaultTimeout(15_000);
        await page.locator('#onboarding-skip').click();

        await injectF9();
        await page.locator('#record-btn-label').getByText('Recording now', { exact: true }).waitFor();

        await injectF9();
        await page.locator('#record-btn-label').getByText('Start recording', { exact: true }).waitFor();
        console.log('Windows physical hotkey E2E: injected F9 reached native listener, Electron, and renderer.');
    } finally {
        await browser?.close();
        if (!app.killed) app.kill();
        await Promise.race([new Promise((resolve) => app.once('close', resolve)), delay(5_000)]);
        try { fs.rmSync(userData, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 }); } catch (_) {}
    }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
