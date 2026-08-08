const net = require('net');

function createSineWavBase64(durationSec = 1.0, freq = 440, sampleRate = 16000) {
    const numSamples = Math.floor(durationSec * sampleRate);
    const buffer = Buffer.alloc(44 + numSamples * 2);
    
    // RIFF header
    buffer.write('RIFF', 0);
    buffer.writeUInt32LE(36 + numSamples * 2, 4);
    buffer.write('WAVE', 8);
    // fmt sub-chunk
    buffer.write('fmt ', 12);
    buffer.writeUInt32LE(16, 16);
    buffer.writeUInt16LE(1, 20); // PCM
    buffer.writeUInt16LE(1, 22); // Mono
    buffer.writeUInt32LE(sampleRate, 24);
    buffer.writeUInt32LE(sampleRate * 2, 28);
    buffer.writeUInt16LE(2, 32);
    buffer.writeUInt16LE(16, 34);
    // data sub-chunk
    buffer.write('data', 36);
    buffer.writeUInt32LE(numSamples * 2, 40);
    
    for (let i = 0; i < numSamples; i++) {
        const sample = Math.sin(2 * Math.PI * freq * (i / sampleRate));
        const val = Math.max(-32768, Math.min(32767, Math.floor(sample * 32767)));
        buffer.writeInt16LE(val, 44 + i * 2);
    }
    
    return buffer.toString('base64');
}

const client = net.createConnection({ port: 8765, host: '127.0.0.1' }, async () => {
    console.log('✓ Connected to Python server for transcribe_audio test');
    const audioB64 = createSineWavBase64(1.0);
    const payload = JSON.stringify({
        id: 'test_b64_req',
        command: 'transcribe_audio',
        params: { audio_base64: audioB64 }
    }) + '\n';
    client.write(payload);
});

client.on('data', (data) => {
    console.log('Server response:', data.toString().trim());
    client.end();
    process.exit(0);
});

client.on('error', (err) => {
    console.error('Connection error:', err);
    process.exit(1);
});
