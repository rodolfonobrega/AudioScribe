const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');

const appDirectory = path.resolve(__dirname, '..');

function waitForDebugEndpoint(port, timeoutMs = 15_000) {
    const deadline = Date.now() + timeoutMs;
    return new Promise((resolve, reject) => {
        const attempt = () => {
            const request = http.get(`http://127.0.0.1:${port}/json/version`, (response) => {
                response.resume();
                if (response.statusCode === 200) return resolve();
                if (Date.now() >= deadline) return reject(new Error('Electron DevTools endpoint did not become available.'));
                setTimeout(attempt, 100);
            });
            request.on('error', () => {
                if (Date.now() >= deadline) return reject(new Error('Electron DevTools endpoint did not become available.'));
                setTimeout(attempt, 100);
            });
        };
        attempt();
    });
}

async function waitForPage(context, timeoutMs = 15_000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const page = context.pages().find((candidate) => candidate.url().startsWith('file:'));
        if (page) return page;
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error('Electron renderer page did not open.');
}

async function main() {
    const env = { ...process.env, AUDIOSCRIBE_E2E: '1' };
    delete env.ELECTRON_RUN_AS_NODE;
    const userDataDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'audioscribe-e2e-'));
    const debugPort = 9200 + Math.floor(Math.random() * 500);
    const app = spawn(require('electron'), [
        `--remote-debugging-port=${debugPort}`,
        `--user-data-dir=${userDataDirectory}`,
        appDirectory,
    ], { cwd: appDirectory, env, stdio: 'pipe', windowsHide: true });
    let browser;

    try {
        await waitForDebugEndpoint(debugPort);
        browser = await chromium.connectOverCDP(`http://127.0.0.1:${debugPort}`);
        const page = await waitForPage(browser.contexts()[0]);
        page.setDefaultTimeout(15_000);
        const pageErrors = [];
        page.on('pageerror', (error) => pageErrors.push(error.message));
        await page.locator('#onboarding-modal').waitFor({ state: 'visible' });

        // The fake renderer announces its engine-ready event, but the real
        // main process intentionally has no sidecar in E2E mode. A direct
        // invocation must be rejected there and must not put the UI into a
        // recording state.
        const offlineAttempt = await page.evaluate(() => window.api.toggleRecording());
        assert.equal(offlineAttempt?.status, 'error', `Offline recording was not rejected: ${JSON.stringify(offlineAttempt)}`);
        assert.equal(offlineAttempt?.code, 'engine_offline', `Unexpected offline rejection: ${JSON.stringify(offlineAttempt)}`);
        assert.equal(await page.locator('#record-btn-label').textContent(), 'Start recording');
        await page.waitForTimeout(150);
        assert.equal(await page.locator('#record-toggle-btn').isDisabled(), true, 'Recording control must be disabled without a microphone.');

        // Complete first-run setup with a deterministic mocked provider and
        // no optional LLM rule. It must create a raw default profile.
        await page.locator('#onboarding-next').click();
        await page.locator('[data-step="2"]').waitFor({ state: 'visible' });
        await page.locator('#ob-stt-key').fill('e2e-test-key');
        await page.locator('#onboarding-next').click();
        await page.waitForTimeout(100);
        const stepAfterProvider = await page.evaluate(() => ({
            active: document.querySelector('.onboarding-step.active')?.dataset.step,
            status: document.getElementById('onboarding-status')?.textContent,
        }));
        assert.equal(stepAfterProvider.active, '3', `Could not leave provider step: ${stepAfterProvider.status}`);
        await page.locator('#onboarding-next').click();
        await page.locator('[data-step="4"]').waitFor({ state: 'visible' });
        await page.locator('#onboarding-next').click();
        await page.locator('[data-step="5"]').waitFor({ state: 'visible' });
        await page.locator('#onboarding-next').click();
        await page.locator('#onboarding-modal').waitFor({ state: 'hidden' });

        const onboardingState = await page.evaluate(() => ({
            completed: localStorage.getItem('audioscribe_onboarding_completed'),
            profiles: JSON.parse(localStorage.getItem('audioscribe_profiles') || '[]'),
        }));
        assert.equal(onboardingState.completed, '1');
        assert.equal(onboardingState.profiles.length, 1);
        assert.equal(onboardingState.profiles[0].isDefault, true);
        assert.equal(onboardingState.profiles[0].prompt, '');
        assert.equal(onboardingState.profiles[0].enabled, true);

        await page.locator('[data-tab="settings"]').click();
        assert.equal(await page.locator('#audio-device-select').isDisabled(), true, 'Settings must report the same missing microphone as Dictate.');
        await page.locator('#audio-device-select option').filter({ hasText: 'No microphone detected' }).waitFor({ state: 'attached' });

        await page.locator('[data-tab="profiles"]').click();
        await page.locator('#profiles-list').getByText('Default dictation').waitFor();

        // Drive the real library controls and assert that the UI renders the
        // data returned through the Electron preload boundary.
        await page.locator('[data-tab="library"]').click();
        await page.locator('#snippet-trigger-input').fill(';mail');
        await page.locator('#snippet-replacement-input').fill('contato@empresa.com');
        await page.locator('#save-snippet-btn').click();
        await page.locator('#snippets-list').getByText(';mail').waitFor();
        await page.locator('#dictionary-word-input').fill('AudioScribe');
        await page.locator('#add-dictionary-btn').click();
        await page.locator('#dictionary-list').getByText('AudioScribe').waitFor();

        assert.deepEqual(pageErrors, [], `Renderer exceptions: ${pageErrors.join('\n')}`);
        console.log('Electron E2E: onboarding, default raw profile, snippets and dictionary passed.');
    } finally {
        await browser?.close();
        if (!app.killed) app.kill();
        await Promise.race([
            new Promise((resolve) => app.once('close', resolve)),
            new Promise((resolve) => setTimeout(resolve, 5_000)),
        ]);
        // Chromium can briefly retain cache files after the parent process
        // exits on Windows. A failed cleanup must never turn a passing UI
        // test into a false failure; the temporary profile contains no user
        // configuration or credentials.
        try {
            fs.rmSync(userDataDirectory, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 });
        } catch (_) {}
    }
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
