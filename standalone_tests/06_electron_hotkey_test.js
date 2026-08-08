const { app, globalShortcut } = require('electron');
const { spawn } = require('child_process');
const net = require('net');
const path = require('path');

console.log("=== STANDALONE ELECTRON HOTKEY & IPC TEST ===");

let pyProcess = null;

function startPythonServerIfNeeded(onReady) {
    const testSocket = net.connect({ port: 8765, host: '127.0.0.1' }, () => {
        testSocket.destroy();
        console.log("    [OK] Python IPC server is already running on port 8765.");
        onReady();
    });

    testSocket.on('error', () => {
        console.log("    [+] Spawning Python IPC server (python main.py --server)...");
        const rootDir = path.resolve(__dirname, '..');
        pyProcess = spawn('python', ['main.py', '--server'], { cwd: rootDir, stdio: 'inherit' });
        
        let attempts = 0;
        const interval = setInterval(() => {
            attempts++;
            const s = net.connect({ port: 8765, host: '127.0.0.1' }, () => {
                s.destroy();
                clearInterval(interval);
                console.log("    [OK] Python IPC server started and connected!");
                onReady();
            });
            s.on('error', () => {
                if (attempts > 30) {
                    clearInterval(interval);
                    console.error("    [X] Python IPC server failed to start within 15 seconds.");
                }
            });
        }, 500);
    });
}

app.whenReady().then(() => {
    console.log("[1/2] Testing Electron Native globalShortcut for 'F9'...");
    try {
        const resF9 = globalShortcut.register('F9', () => {
            console.log("\n>>> [SUCCESS] F9 DETECTED BY ELECTRON NATIVE! <<<\n");
        });
        console.log("    Native F9 registration:", resF9 ? 'SUCCESS' : 'FAILED');
    } catch (err) {
        console.log("    Native F9 error:", err.message);
    }

    console.log("\n[2/2] Checking Python IPC Server for 'ctrl+windows' detection...");
    startPythonServerIfNeeded(() => {
        const client = net.connect({ port: 8765, host: '127.0.0.1' }, () => {
            console.log("    [OK] Connected to Python IPC socket.");
            
            // Configure Python to listen for ctrl+windows
            const payload = JSON.stringify({
                id: 'test_hotkey_1',
                command: 'configure_hotkey',
                params: { hotkey: 'ctrl+windows' }
            }) + '\n';
            client.write(payload);
        });

        let buffer = '';
        client.on('data', (data) => {
            buffer += data.toString();
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const evt = JSON.parse(line.trim());
                    if (evt.event === 'status_changed' && evt.data?.status === 'recording') {
                        console.log("\n>>> [SUCCESS] CTRL + WIN DETECTED BY PYTHON ENGINE! (RECORDING TRIGGERED) <<<\n");
                    } else if (evt.status === 'ok') {
                        console.log("    [OK] Engine confirmed hotkey configuration:", evt);
                        console.log("\n=======================================================");
                        console.log(">>> NOW PRESS 'Ctrl + Win' OR 'F9' ON YOUR KEYBOARD! <<<");
                        console.log("=======================================================\n");
                    }
                } catch (e) {
                    console.log("[RAW ENGINE DATA]:", line);
                }
            }
        });

        client.on('error', (err) => {
            console.error("    [X] Socket error:", err.message);
        });
    });
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
    if (pyProcess) {
        pyProcess.kill();
    }
});
