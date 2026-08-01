/**
 * Pure Node.js Universal Transcription & LLM Client for Electron.
 * Uses native fetch() to call Groq, OpenAI, Gemini, or Localhost Ollama.
 */

const fs = require('fs');
const path = require('path');

class NativeTranscriber {
    constructor(config = {}) {
        this.apiKey = config.apiKey || process.env.GROQ_API_KEY;
        this.baseUrl = config.baseUrl || 'https://api.groq.com/openai/v1';
        this.model = config.model || 'whisper-large-v3-turbo';
        this.llmModel = config.llmModel || 'meta-llama/llama-4-maverick-17b-128e-instruct';
    }

    validatePreflight(apiKeyOverride = null) {
        const keyToTest = apiKeyOverride || this.apiKey || process.env.GROQ_API_KEY;
        const errors = [];

        if (!keyToTest && !this.baseUrl.includes('localhost')) {
            errors.push("Missing Groq API Key. Please enter your API key (starts with gsk_...) in Settings.");
        }

        return {
            valid: errors.length === 0,
            errors: errors
        };
    }

    async transcribe(audioBuffer) {
        if (!this.apiKey && !this.baseUrl.includes('localhost')) {
            throw new Error("GROQ_API_KEY is missing. Please enter your API key in Settings.");
        }

        const formData = new FormData();
        const blob = new Blob([audioBuffer], { type: 'audio/wav' });
        formData.append('file', blob, 'recording.wav');
        formData.append('model', this.model);
        formData.append('temperature', '0.0');

        const headers = {};
        if (this.apiKey) {
            headers['Authorization'] = `Bearer ${this.apiKey}`;
        }

        const response = await fetch(`${this.baseUrl}/audio/transcriptions`, {
            method: 'POST',
            headers,
            body: formData
        });

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`Transcription API error (${response.status}): ${errText}`);
        }

        const data = await response.json();
        return data.text ? data.text.trim() : '';
    }

    async processLLM(text, systemPrompt = null) {
        if (!text) return '';

        const defaultPrompt = "You are a professional voice dictation assistant. " +
            "Your task is to fix grammar, remove filler words (um, ah, like), correct phonetic spelling errors, " +
            "and output ONLY the polished text. Do not add conversational intro/outro text.";

        const headers = { 'Content-Type': 'application/json' };
        if (this.apiKey) {
            headers['Authorization'] = `Bearer ${this.apiKey}`;
        }

        const payload = {
            model: this.llmModel,
            messages: [
                { role: 'system', content: systemPrompt || defaultPrompt },
                { role: 'user', content: text }
            ],
            temperature: 0.3
        };

        const response = await fetch(`${this.baseUrl}/chat/completions`, {
            method: 'POST',
            headers,
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            return text; // Fallback to raw transcription on LLM failure
        }

        const data = await response.json();
        if (data.choices && data.choices[0] && data.choices[0].message) {
            return data.choices[0].message.content.trim();
        }
        return text;
    }
}

module.exports = NativeTranscriber;
