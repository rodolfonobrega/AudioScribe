"""
Interactive Step-by-Step Validation Script for Ctrl+Win Hotkey & Audio Flow.
"""

import sys
import time
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=========================================================")
print("   AUDIOSCRIBE INTERACTIVE STEP-BY-STEP TEST SUITE")
print("=========================================================")

print("\n--- TEST 1: HOTKEY & AUDIO RECORDING INTERACTION ---")
print("INSTRUÇÕES:")
print("1. Pressione o atalho [ Ctrl + Win ] no seu teclado.")
print("2. Fale alguma frase no seu microfone (ex: 'Testando AudioScribe').")
print("3. Pressione [ Ctrl + Win ] novamente para parar e transcrever.\n")

try:
    from config.settings import load_config
    from core.factory import TranscriptionFactory
    
    cfg = load_config()
    cfg.keyboard.hotkey = "ctrl+windows"
    
    is_recording = False
    transcription_done = False
    transcribed_text = ""

    def on_event(event_type, data):
        global is_recording, transcription_done, transcribed_text
        if event_type == "status_changed":
            status = data.get("status")
            if status == "recording":
                is_recording = True
                print("\n>>> [1/3 OK] HOTKEY DETECTADA! 🔴 GRAVANDO ÁUDIO (Fale agora!)...\n")
            elif status == "processing":
                print("\n>>> [2/3 OK] HOTKEY DETECTADA! ⚡ PROCESSANDO E TRANSCREVENDO ÁUDIO...\n")
        elif event_type == "transcription_result":
            transcribed_text = data.get("text", "")
            transcription_done = True
            print(f"\n>>> [3/3 OK] TRANSCRIÇÃO CONCLUÍDA EM {data.get('latency_ms', 0)}ms! <<<")
            print(f"Texto Transcrito: \"{transcribed_text}\"\n")

    orchestrator = TranscriptionFactory.create_orchestrator(cfg)
    orchestrator.add_event_listener(on_event)
    orchestrator.start()
    
    print("[STATUS] Escutador do atalho [ Ctrl + Win ] ATIVO.")
    print("Aguardando você pressionar [ Ctrl + Win ]...\n")
    
    start_wait = time.time()
    last_tick = time.time()
    while not transcription_done and (time.time() - start_wait) < 180:
        time.sleep(0.2)
        if (time.time() - last_tick) > 10.0 and not is_recording:
            last_tick = time.time()
            print("[Aguardando] Pressione [ Ctrl + Win ] para iniciar a gravação...")

    orchestrator.stop()

    if transcription_done:
        print("=========================================================")
        print("🎉 TESTE INTERATIVO PASSOU COM 100% DE SUCESSO!")
        print(f"Atalho Ctrl+Win: FUNCIONOU")
        print(f"Gravação de Áudio: FUNCIONOU")
        print(f"Transcrição STT: FUNCIONOU (\"{transcribed_text}\")")
        print("=========================================================")
    else:
        print("\n[ERRO] Tempo limite de 180s atingido. Nenhuma gravação/transcrição foi finalizada.")
        sys.exit(1)

except Exception as e:
    print(f"\n[ERRO] Falha no teste interativo: {e}")
    sys.exit(1)
