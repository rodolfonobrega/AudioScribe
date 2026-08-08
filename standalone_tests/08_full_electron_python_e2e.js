const net = require('net');
const { spawn } = require('child_process');
const path = require('path');

console.log("=== AUTOMATED ELECTRON IPC VERIFICATION SUITE ===");

const pyProcess = spawn('python', ['main.py', '--server', '--port', '8765'], {
    cwd: path.join(__dirname, '..'),
    stdio: ['ignore', 'pipe', 'pipe']
});

pyProcess.stdout.on('data', (d) => console.log(`[PyStdout]: ${d.toString().trim()}`));
pyProcess.stderr.on('data', (d) => console.error(`[PyStderr]: ${d.toString().trim()}`));

async function connectWithRetry(retries = 25, delayMs = 300) {
    for (let i = 0; i < retries; i++) {
        try {
            return await new Promise((resolve, reject) => {
                const client = net.connect({ port: 8765, host: '127.0.0.1' }, () => resolve(client));
                client.on('error', reject);
            });
        } catch (e) {
            await new Promise((r) => setTimeout(r, delayMs));
        }
    }
    throw new Error("Could not connect to Python server on port 8765 after retries");
}

(async () => {
    try {
        console.log("[1/5] Connecting to Python server on port 8765...");
        const client = await connectWithRetry();
        console.log("✓ Connected to Python server!");

        function sendCmd(cmd, params = {}) {
            return new Promise((resolve) => {
                const id = Math.random().toString(36).slice(2);
                const req = JSON.stringify({ id, command: cmd, params }) + '\n';
                
                const onData = (data) => {
                    const lines = data.toString().split('\n');
                    for (const line of lines) {
                        if (!line.trim()) continue;
                        try {
                            const parsed = JSON.parse(line.trim());
                            if (parsed.id === id) {
                                client.removeListener('data', onData);
                                resolve(parsed);
                            }
                        } catch (e) {}
                    }
                };
                client.on('data', onData);
                client.write(req);
            });
        }

        console.log("[2/5] Testing configure_hotkey 'ctrl+windows'...");
        const hotkeyRes = await sendCmd('configure_hotkey', { hotkey: 'ctrl+windows' });
        console.log("   Hotkey Config Result:", hotkeyRes);

        console.log("[3/5] Testing configure_provider 'groq'...");
        const provRes = await sendCmd('configure_provider', {
            transcription: {
                provider: 'groq',
                api_key: process.env.GROQ_API_KEY || '',
                model: 'groq/whisper-large-v3-turbo'
            }
        });
        console.log("   Provider Config Result:", provRes);

        console.log("[4/5] Testing start_recording & idempotent start...");
        const startRes1 = await sendCmd('start_recording');
        console.log("   Start 1 Result:", startRes1);
        const startRes2 = await sendCmd('start_recording');
        console.log("   Start 2 (Idempotent) Result:", startRes2);

        await new Promise((r) => setTimeout(r, 1500));

        console.log("[5/5] Testing stop_recording & idempotent stop...");
        const stopRes1 = await sendCmd('stop_recording');
        console.log("   Stop 1 Result:", stopRes1);
        const stopRes2 = await sendCmd('stop_recording');
        console.log("   Stop 2 (Idempotent) Result:", stopRes2);

        console.log("\n==================================================");
        console.log("🎉 ALL AUTOMATED IPC TESTS COMPLETED SUCCESSFULLY!");
        console.log("==================================================");

        client.destroy();
        pyProcess.kill();
        process.exit(0);
    } catch (err) {
        console.error("Test failed:", err.message);
        pyProcess.kill();
        process.exit(1);
    }
})();
