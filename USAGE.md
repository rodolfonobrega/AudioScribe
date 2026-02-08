# AudioScribe v1.0 - Atualizações

## O que foi corrigido:

1. **Saída limpa e organizada**
   - Removida saída detalhada poluda com "=" e "======================================================"
   - Adicionada saída compacta e limpa no estilo solicitado
   - Removidos nomes de componentes da saída (GroqTranscriber, LiteLLMProcessor, etc.)

2. **LLM desligado por padrão**
   - `config/defaults.yaml`: `enabled: false`
   - Adicionado argumento `--no-llm` para desativar via CLI
   - LLM só é ativado se `enabled: true` no config E não passar `--no-llm`

3. **Nome do dispositivo**
   - Mostra "Device Default" quando não especifica `--device`
   - Mostra "Device X (Nome do dispositivo)" quando especifica `--device X`

4. **Arquivos de teste removidos**
   - Todos os arquivos `test_*.py` foram apagados

## Como usar:

### Uso básico (LLM desligado, output console)
```bash
python main.py --no-keyboard
```

### Com LLM ativado
Edite `config/defaults.yaml` e mude `enabled: false` para `enabled: true`:
```yaml
llm:
  enabled: true
```

Depois execute:
```bash
python main.py
```

### Com diferentes outputs
```bash
python main.py --output clipboard
python main.py --output autoit
python main.py --output pyautogui
```

### Com dispositivo específico
```bash
python main.py --device 1
```

### Desativar LLM via CLI (mantém config com enabled=true)
```bash
python main.py --no-llm
```

## Saída esperada:

```
AudioScribe v1.0
----------------------------------------
Transcription: litellm / groq/whisper-large-v3-turbo
             (lang=auto, temp=0.0)
Audio        : 16000 // 1kHz | mono
Runtime      : LLM=off | Output=console
----------------------------------------
Hotkey: f9 | Ctrl+C to exit
```

## Argumentos disponíveis:

- `--config PATH` - Caminho para arquivo de configuração
- `--output TYPE` - Tipo de saída (console, clipboard, pyautogui, autoit, applescript, xdotool)
- `--device INDEX` - Índice do dispositivo de áudio
- `--no-keyboard` - Desativar listener de teclado
- `--file PATH` - Processar arquivo de áudio em vez de gravar
- `--text TEXT` - Processar texto diretamente (para pós-processamento LLM)
- `--no-llm` - Desativar pós-processamento LLM
- `--help` - Mostrar ajuda

## Hotkey padrão:
- Pressione F9 para gravar (push-to-talk)
- Ctrl+C para sair

Nota: O modo e hotkey podem ser configurados em `config/defaults.yaml`
