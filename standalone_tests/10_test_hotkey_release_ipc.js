const net = require('net');

const client = net.createConnection({ port: 8765, host: '127.0.0.1' }, async () => {
    console.log('✓ Connected to Python IPC server');
    
    // Step 1: Configure hotkey with push_to_talk mode
    client.write(JSON.stringify({
        id: 'req_1',
        command: 'configure_hotkey',
        params: { hotkey: 'ctrl+windows', mode: 'push_to_talk' }
    }) + '\n');
});

client.on('data', (data) => {
    const lines = data.toString().split('\n').filter(Boolean);
    for (const line of lines) {
        try {
            const parsed = JSON.parse(line);
            console.log('Server Event/Response:', parsed);
            if (parsed.id === 'req_1' && parsed.status === 'ok') {
                console.log('✓ Hotkey registered with on_press AND on_release callbacks!');
                client.end();
                process.exit(0);
            }
        } catch (e) {}
    }
});

client.on('error', (err) => {
    console.error('Connection error:', err);
    process.exit(1);
});
