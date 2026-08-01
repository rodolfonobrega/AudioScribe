# AudioScribe — Plano de correção após auditoria

**Data:** 2026-08-01  
**Status:** plano técnico  
**Escopo:** CLI Python, engine Python, integração IPC, aplicativo Electron, provedores cloud, Ollama, custos, testes e empacotamento.

## 1. Objetivo

Tornar o AudioScribe confiável antes de uma nova release. A aplicação só deve mostrar “pronto”, “Ollama disponível” ou “modelo disponível” quando tiver verificado o componente real que será usado na execução.

O plano também cria uma fonte única de verdade para:

- configuração do provedor e do modelo;
- estado do engine;
- disponibilidade de microfone e endpoint;
- modelos instalados ou acessíveis;
- eventos de gravação e transcrição;
- consumo, tokens, duração e custo de API.

## 2. Diagnóstico executivo

O problema principal não é apenas um bug isolado. O projeto possui dois caminhos de execução parcialmente independentes:

```text
Electron UI
  ├── validação superficial em JavaScript
  ├── configurações em localStorage
  └── comandos IPC

Python
  ├── configuração YAML/.env
  ├── LiteLLM
  ├── microfone
  └── processamento e saída
```

A UI não controla necessariamente a configuração utilizada pelo Python. Por isso, ela pode dizer que o provedor está disponível enquanto o engine está offline, usando outro modelo ou sem credencial válida.

### Evidências verificadas

- Os endpoints locais do Ollama (`/api/tags`, `/v1/models` e `/api/version`) não responderam nesta máquina durante a auditoria.
- `load_config(use_env=True)` retornou literalmente `'${GROQ_API_KEY}'` sem chave configurada.
- `PreflightChecker.check_api_keys()` retornou zero erros nesse cenário.
- A factory falhou com `NameError: SoundDeviceInput is not defined`.
- `pytest tests` passou com 18 testes; a execução ampla de `pytest` também tentou coletar um teste experimental em `scratch/` e abortou por dependência ausente.
- A sintaxe dos arquivos JavaScript principais e a compilação dos módulos Python passaram.

**Decisão recomendada:** manter o Electron como interface e usar o Python como único engine de áudio, provedores, modelos, eventos e custos. A implementação `electron/src/transcriber.js` deve ser removida ou transformada em um adaptador explicitamente utilizado, mas não deve continuar como segundo caminho oculto.

## 3. Critérios de severidade

- **P0 — bloqueador:** pode impedir o uso, gerar estado falso ou invalidar uma release.
- **P1 — alto:** fluxo importante quebra em determinadas condições ou produz diagnóstico enganoso.
- **P2 — médio:** dívida técnica, segurança limitada, inconsistência ou manutenção difícil.
- **P3 — baixo:** melhoria de qualidade, documentação ou ergonomia.

## 4. Registro de problemas e soluções

### P0-01 — Placeholder de chave de API passa pelo preflight

**Evidência:** `config/defaults.yaml:22` e `config/defaults.yaml:36` usam `${GROQ_API_KEY}`. A expansão com `os.path.expandvars()` deixa o texto literal quando a variável não existe. Em seguida, `load_config()` preserva esse valor em `config/settings.py:148-160`.

**Impacto:** sem nenhuma chave, o preflight pode não acusar erro; o sistema tenta autenticar usando `${GROQ_API_KEY}`.

**Solução:**

1. Remover credenciais dos defaults YAML.
2. Tratar placeholders não resolvidos como `None`.
3. Criar uma função única `resolve_secret()` que diferencie valor vazio, placeholder e segredo real.
4. Validar o provedor escolhido, não apenas a existência de alguma chave.
5. Nunca imprimir a chave; mostrar somente provedor e status mascarado.

**Aceite:** com todas as chaves ausentes, o preflight falha explicitamente e explica como configurar o provedor.

### P0-02 — A UI declara Ollama disponível sem testar

**Evidência:** `electron/ui/app.js:99-118` considera qualquer URL local como disponível. Não há chamada a `/api/version`, `/api/tags`, `/v1/models` ou a um health check do engine.

**Impacto:** “Localhost Ollama disponível” pode aparecer quando o processo não está instalado, está parado ou não possui o modelo necessário.

**Solução:** o status deve ser resultado de uma sequência real:

```text
engine conectado
  → endpoint responde
  → modelo é listado
  → capacidade necessária existe
  → teste mínimo é executado
  → pronto
```

Para Ollama:

1. consultar o endpoint configurado;
2. listar modelos instalados;
3. validar o modelo escolhido;
4. testar chat para LLM;
5. para transcrição, usar um adaptador suportado, como Whisper local, whisper.cpp ou outro servidor de speech-to-text.

O endpoint de transcrição não deve ser presumido apenas porque o servidor possui compatibilidade OpenAI para chat. A documentação oficial do Ollama documenta `/v1/models` e chat completions, mas não apresenta `/v1/audio/transcriptions` como endpoint compatível.

**Aceite:** se Ollama estiver parado, a UI mostra `offline`; se estiver ativo sem o modelo, mostra `modelo ausente`; se o modelo existir mas o teste falhar, mostra `erro de capacidade`.

### P0-03 — Configuração do Electron não chega ao Python

**Evidência:** `app.js:140-146` salva provider, chave e URL somente em `localStorage`. O sidecar Python iniciado em `main.js:193-232` recebe apenas `--server --port`.

**Impacto:** o usuário configura Groq, OpenAI ou Ollama na UI, mas o Python continua usando `.env` e `config/defaults.yaml`.

**Solução:** criar comandos IPC de configuração:

```json
{
  "command": "configure_provider",
  "params": {
    "provider": "ollama",
    "base_url": "http://127.0.0.1:11434",
    "transcription_model": "whisper-local",
    "llm_model": "qwen3:8b",
    "api_key": null
  }
}
```

O Python deve validar, aplicar em memória e responder com o estado efetivo. A chave deve ser enviada por canal protegido do Electron e armazenada no armazenamento seguro do sistema, não no `localStorage`.

**Aceite:** o modelo e provedor exibidos na UI são exatamente os retornados pelo engine Python.

### P0-04 — Factory quebra ao criar o microfone

**Evidência:** `core/factory.py:40` usa `SoundDeviceInput`, mas o módulo não importa essa classe.

**Impacto:** a criação normal do orchestrator falha com `NameError` depois do preflight.

**Solução:** importar explicitamente `SoundDeviceInput` e adicionar teste de criação da factory.

**Aceite:** `TranscriptionFactory.create_orchestrator(load_config(...))` cria o componente em ambiente com dependências instaladas.

### P0-05 — Dockerfile e Compose pertencem a outra arquitetura

**Evidência:** o Dockerfile referencia `pyproject.toml`, `src/`, `config.yaml`, `.env.example` e `AGENTS.md`, que não existem. O Compose usa o target `audioscribe`, mas o Dockerfile não possui esse estágio.

**Impacto:** build e execução dockerizada não são confiáveis.

**Solução:** reescrever o empacotamento para a estrutura atual ou remover o Docker legado. Para este projeto, a opção recomendada é:

1. `python:3.12-slim` como imagem de build/runtime;
2. copiar `main.py`, `config/`, `core/`, `requirements.txt` e arquivos necessários;
3. instalar dependências de áudio explicitamente;
4. definir um comando de engine coerente;
5. documentar que captura de microfone em Docker depende do sistema operacional;
6. adicionar health check real, não apenas `sys.exit(0)`.

O Docker não deve ser apresentado como solução para a aplicação Electron desktop sem um desenho específico de acesso ao áudio do host.

**Aceite:** `docker build` e um smoke test do container são executados em CI; o health check falha quando o engine não inicializa.

### P0-06 — Aplicativo empacotado pode ficar sem engine

**Evidência:** `main.js:197-204` procura um binário Python em `resources/bin`, mas o fluxo de release em `.github/workflows/release.yml` só instala dependências Node e executa `electron-builder`. `electron/package.json` não declara `extraResources` para o sidecar.

**Impacto:** o instalador pode abrir a UI sem backend funcional.

**Solução:** escolher uma estratégia única:

- **Recomendada:** gerar o engine Python com PyInstaller/Nuitka e incluí-lo em `extraResources`.
- **Alternativa:** exigir Python instalado e iniciar o script, com diagnóstico explícito.
- **Alternativa de longo prazo:** portar todo o engine para Node, incluindo áudio, provedores, custos e health checks.

Não deixar um fallback silencioso que apenas registra “Pure Native Node.js mode” sem realmente inicializar o `NativeTranscriber`.

**Aceite:** o instalador em cada sistema inicia UI e engine, e a UI bloqueia gravação quando o engine não estiver conectado.

### P1-01 — Resultado de transcrição não é publicado pelo servidor

**Evidência:** `core/api/server.py` publica apenas `status_changed`. A UI espera `transcription_result` em `electron/ui/app.js:476-495`.

**Impacto:** histórico, métricas e colagem automática não recebem resultado.

**Solução:** o orchestrator deve publicar eventos de domínio, não a UI de terminal. Criar um callback/event bus:

```json
{
  "event": "transcription_result",
  "data": {
    "request_id": "...",
    "raw_text": "...",
    "final_text": "...",
    "provider": "groq",
    "model": "whisper-large-v3-turbo",
    "latency_ms": 842,
    "cost": 0.0012
  }
}
```

**Aceite:** uma gravação completa gera eventos de início, processamento, resultado ou erro, sempre com `request_id`.

### P1-02 — Diagnóstico IPC usa método inexistente

**Evidência:** `server.py:109-116` chama `run_all_checks()`, mas `PreflightChecker` possui `check_all()`.

**Solução:** centralizar o preflight em um serviço que recebe a configuração efetiva do engine e retorna um objeto estruturado. Não duplicar a lógica no JavaScript.

### P1-03 — `get_status` chama `is_recording` incorretamente

**Evidência:** `server.py:136` usa `self.orchestrator.audio_input.is_recording()`; a implementação define `is_recording` como property.

**Solução:** corrigir o acesso e adicionar teste IPC para `get_status` com gravação ligada e desligada.

### P1-04 — Dois componentes controlam o atalho global

**Evidência:** Electron registra F9 em `main.js:275-281`; o Python também cria `KeyboardListener` pela factory.

**Impacto:** um pressionamento pode alternar dois estados ou gerar start/stop duplicado.

**Solução:** no modo Electron, o Electron é o único dono do atalho. O Python deve iniciar com `keyboard.enabled = false` e aceitar comandos IPC. No modo CLI, o Python continua dono do teclado.

**Aceite:** F9 produz exatamente uma transição de estado por pressionamento.

### P1-05 — Resposta IPC pode ficar pendurada

**Evidência:** `main.js:327-350` cria listeners individuais por requisição, sem timeout e sem parser compartilhado para mensagens fragmentadas.

**Solução:** criar um único cliente JSON Lines com:

- buffer compartilhado;
- correlação por `id`;
- timeout por requisição;
- rejeição de promessas quando o socket fecha;
- reconexão com backoff limitado;
- remoção garantida de listeners.

### P1-06 — Seleção de múltiplos outputs não funciona

**Evidência:** a factory cria uma lista, mas `create_orchestrator()` mantém somente `handlers[0]`.

**Solução:** criar `CompositeOutputHandler` que executa todos os handlers e reporta falhas individualmente.

```text
resultado
  ├── clipboard
  ├── arquivo
  └── auto-paste
```

### P1-07 — Modelos padrão podem ficar obsoletos

**Evidência:** `config/defaults.yaml:31` usa `meta-llama/llama-4-maverick-17b-128e-instruct`. A documentação atual da Groq informa a depreciação desse modelo.

**Solução:** não depender de um modelo fixo sem validação. Manter uma tabela de modelos por provedor, com data de atualização, capacidades, preço e status. Validar o modelo via API antes de selecioná-lo.

### P1-08 — Integração Ollama mistura chat e transcrição

**Problema:** Ollama pode atender o pós-processamento LLM via chat, mas isso não garante speech-to-text.

**Solução:** separar interfaces:

```text
TranscriberProvider
  ├── GroqSpeechToText
  ├── OpenAISpeechToText
  ├── WhisperNative
  └── WhisperCppServer

LLMProvider
  ├── GroqChat
  ├── OpenAIChat
  └── OllamaChat
```

Ollama só deve aparecer como opção de transcrição se houver um adaptador de speech-to-text instalado e testado.

## 5. Observabilidade e custos de API

### 5.1 Evento de uso

Criar um `UsageRecord` persistido em SQLite local:

```text
id
created_at
request_id
operation                 transcription | llm
provider
model
audio_seconds
input_tokens
output_tokens
status                    success | error | fallback
latency_ms
estimated_cost_usd
price_source
error_code
```

Não armazenar áudio por padrão. O texto deve ser opcional e separado do registro financeiro.

### 5.2 Cálculo

- Transcrição: `audio_seconds / 3600 * price_per_hour`.
- LLM: `(input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)`.
- Fallback: registrar cada tentativa, não somente a final.
- Ollama/local: custo de API `0`, com possibilidade futura de estimativa de energia separada.
- Resposta sem usage: custo `unknown`, nunca zero silencioso.

### 5.3 Interface

Adicionar uma seção “Uso e custos” com:

- custo da sessão;
- custo hoje;
- custo no mês;
- chamadas por provedor/modelo;
- tokens de entrada/saída;
- minutos de áudio;
- falhas e fallbacks;
- aviso de que o valor é estimado quando a API não fornece cobrança oficial.

As métricas atuais de palavras e latência continuam úteis, mas não devem ser apresentadas como custo.

## 6. Segurança e robustez

### P1-09 — Segredos no localStorage

Substituir por armazenamento seguro do sistema operacional, como `safeStorage` do Electron ou equivalente. O renderer nunca deve receber mais segredo do que precisa.

### P1-10 — Uso inseguro de `innerHTML`

Os textos da transcrição e prompts de perfil entram no DOM por interpolação. Substituir por `textContent` e criação de nós DOM. Validar e limitar tamanho dos prompts.

### P1-11 — Comando PowerShell construído com texto transcrito

O fallback de clipboard concatena texto no comando. Usar stdin, APIs nativas ou argumentos sem interpolação de shell.

### P1-12 — Erros são engolidos

Substituir `except Exception: pass` por erros estruturados, logs com contexto e mensagens seguras para o usuário. Cada erro deve informar:

- componente;
- operação;
- código classificável;
- tentativa/fallback;
- ação recomendada.

### P1-13 — Suíte de testes pode coletar código experimental

**Evidência:** a execução ampla de `pytest` coletou um arquivo de teste em `scratch/` e abortou durante a importação por dependência ausente, enquanto `pytest tests` passou.

**Impacto:** o comando padrão de CI pode falhar por código que não pertence à suíte do produto ou esconder a cobertura real.

**Solução:** manter `testpaths = tests`, excluir `scratch/` explicitamente, separar testes experimentais e fazer o CI executar `python -m pytest tests`.

### P2-01 — Documentação, configuração e release estão divergentes

**Evidência:** Docker, README, QUICKSTART, RELEASE e workflow descrevem estruturas e comandos diferentes dos arquivos existentes.

**Impacto:** instalação, Docker e release podem parecer suportados sem terem sido validados no código atual.

**Solução:** após cada correção, atualizar a documentação a partir de comandos testados. O README deve conter uma matriz clara de suporte: CLI, Electron, Ollama LLM, transcrição local, Docker e plataformas.

## 7. Configurações sem efeito ou inconsistentes

Auditar e remover ou implementar:

- `min_duration`;
- `chunk_size`;
- `vad_silence_duration`;
- `file_path` e `output_file`;
- `keyboard.enabled`;
- perfis de pós-processamento no Electron;
- seleção de microfone na UI;
- parâmetros de idioma e temperatura no fluxo Electron.

Toda configuração visível deve ter efeito real ou ser removida da interface.

## 8. Plano de execução

### Fase 0 — Baseline e proteção

1. Criar testes de regressão para os bugs confirmados.
2. Registrar a versão atual e não publicar nova release.
3. Corrigir descoberta do pytest para ignorar `scratch/` e artefatos experimentais.
4. Adicionar CI com `pytest tests`, `compileall` e `node --check`.

### Fase 1 — Fonte única de configuração

1. Criar `EffectiveConfig` com provider, URL, modelos e credenciais resolvidos.
2. Remover placeholders de credenciais dos defaults.
3. Fazer o Python retornar a configuração efetiva por IPC.
4. Desabilitar keyboard listener quando o engine estiver em modo Electron.

### Fase 2 — Engine e health check

1. Corrigir a factory.
2. Criar `HealthReport` estruturado.
3. Validar microfone, engine, endpoint, credencial, modelo e capacidade.
4. Implementar descoberta de modelos.
5. Separar transcriber de LLM provider.

### Fase 3 — IPC e UI

1. Corrigir servidor e eventos.
2. Implementar cliente JSON Lines robusto.
3. Fazer a UI consumir apenas o estado retornado pelo engine.
4. Exibir modelos disponíveis, modelo selecionado e capacidade.
5. Bloquear gravação enquanto o engine estiver offline ou não pronto.

### Fase 4 — Custos

1. Criar tabela de preços versionada.
2. Capturar usage real das respostas.
3. Registrar duração e tentativas de áudio.
4. Persistir usage em SQLite.
5. Implementar dashboard de custo.

### Fase 5 — Empacotamento

1. Definir empacotamento do sidecar Python.
2. Corrigir `extraResources` do Electron Builder.
3. Reescrever Dockerfile ou removê-lo.
4. Validar instaladores em Windows, macOS e Linux.
5. Executar smoke test após instalação.

### Fase 6 — Segurança, testes e release

1. Remover `innerHTML` para dados externos.
2. Remover interpolação em shell.
3. Migrar secrets para armazenamento seguro.
4. Criar testes de falha: Ollama offline, modelo ausente, API inválida, fallback, socket interrompido e microfone indisponível.
5. Publicar somente com checklist de aceite completo.

## 9. Testes obrigatórios

### Unitários

- placeholder de chave não resolvido;
- seleção de provider;
- cálculo de custo por hora;
- cálculo de custo por tokens;
- modelo ausente;
- health report;
- composite output;
- transições de estado;
- parser JSON Lines fragmentado.

### Integração

- engine inicia e aceita `ping`;
- `get_status` funciona;
- `get_devices` funciona;
- `preflight` retorna relatório;
- configuração do Electron chega ao Python;
- gravação gera resultado;
- erro gera evento de erro;
- fallback registra ambas as tentativas;
- custo é persistido.

### Smoke tests por provedor

- Groq com chave válida e modelo disponível;
- OpenAI com chave válida e modelo disponível;
- Ollama ativo com modelo LLM instalado;
- Ollama parado;
- endpoint customizado inválido;
- transcriber local sem capacidade de áudio.

## 10. Critérios para considerar o projeto pronto

- Nenhum estado “disponível” é baseado somente em URL, presença de chave ou configuração local.
- A UI e o engine exibem a mesma configuração efetiva.
- O modelo utilizado aparece no resultado e no painel de uso.
- Um modelo ausente impede a gravação com mensagem clara.
- O resultado chega ao Electron e pode ser colado sem duplicação.
- O custo da sessão é calculado ou explicitamente marcado como desconhecido.
- O instalador contém ou inicia o engine real.
- Docker build e smoke test passam, quando Docker for mantido.
- `pytest tests` passa sem depender de `scratch/`.
- Não há segredos em `localStorage` nem interpolação insegura de texto em shell.

## 11. Entregáveis esperados

1. Engine Python corrigido.
2. Contrato IPC documentado.
3. Health check estruturado.
4. Descoberta e seleção de modelos.
5. Adaptadores separados de transcrição e LLM.
6. Telemetria local de uso e custos.
7. Dashboard de custos no Electron.
8. Empacotamento reproduzível.
9. Suíte de testes de regressão e integração.
10. README, QUICKSTART, Docker e RELEASE.md atualizados para refletir o comportamento real.
