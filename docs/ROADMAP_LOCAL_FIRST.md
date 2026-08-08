# AudioScribe — Plano de implementação local-first

## Status da implementacao

Ja implementado no AudioScribe:

- historico local em SQLite com copiar, excluir e limpar;
- dicionario local e snippets com expansao por limite de palavra;
- colagem segura no Electron com fila, fallback para clipboard e restauracao condicional;
- providers locais `local_whisper` e `parakeet`, com GPU CUDA/MPS e Parakeet via sherpa-onnx;
- registro de modelos, download opcional do Parakeet e validacao contra path traversal;
- selecao de provider/modelo e caminho local pela interface;
- configuracao padrao sem cloud e sem chave de API;
- testes unitarios para persistencia, snippets, preflight e arquivos de modelo.

Ainda requer validacao manual por maquina/plataforma:

- instalar o runtime opcional (`faster-whisper` ou `sherpa-onnx`) e medir CUDA/CPU;
- testar o atalho de colagem em editores, navegador e terminal no Windows, macOS e Linux;
- executar o onboarding visual completo e ajustar permissoes do sistema;
- definir licencas, checksums e empacotamento dos modelos antes de uma release.

## Objetivo

Transformar o AudioScribe em um aplicativo de ditado desktop local-first, gratuito para sempre e sem nuvem própria.

O aplicativo deve continuar funcionando sem conta, sem servidor do AudioScribe e sem API paga. A internet poderá ser usada apenas para baixar modelos, runtimes e atualizações, quando o usuário optar por isso.

Este documento consolida a análise do repositório OpenWhispr e define o que devemos aproveitar, adaptar ou rejeitar.

## Princípios do produto

1. **Local por padrão**: áudio e transcrições não saem da máquina no modo padrão.
2. **Sem conta**: o primeiro uso não pode exigir login, e-mail ou cadastro.
3. **Sem cloud própria**: não haverá API, sincronização, billing, telemetry ou armazenamento remoto mantido pelo AudioScribe.
4. **Offline depois da instalação**: após baixar os modelos, o ditado deve funcionar sem internet.
5. **Degradação graciosa**: se GPU, colagem automática ou modelo avançado falhar, o aplicativo deve continuar útil com CPU, clipboard ou modelo menor.
6. **Dados do usuário locais**: histórico, dicionário, snippets, configurações e metadados ficam em SQLite ou arquivos locais exportáveis.
7. **Componentes substituíveis**: transcrição, pós-processamento, colagem e armazenamento devem continuar atrás de interfaces.

## O que foi encontrado no OpenWhispr

Clone analisado em:

```text
C:\Users\rodol\AppData\Local\Temp\AudioScribe-openwhispr-review-24fa2191e4394613a3406f0f61e86c29
```

Arquivos principais para referência:

- `src/helpers/clipboard.js` — clipboard, colagem automática, restauração e detecção de ferramentas.
- `src/helpers/database.js` — histórico, dicionário, snippets e retenção local.
- `src/components/HistoryView.tsx` — interface do histórico.
- `src/components/SnippetsView.tsx` — interface de snippets.
- `src/utils/snippets.ts` — matching e expansão dos snippets.
- `src/helpers/parakeet.js` e `src/helpers/parakeetServer.js` — execução local do Parakeet.
- `src/helpers/gpuBinaryManager.js` — download, integridade e ciclo de vida dos runtimes GPU.
- `src/components/OnboardingFlow.tsx` — setup inicial persistente.
- `src/hooks/usePermissions.ts` — permissões por sistema operacional.

O OpenWhispr está sob MIT, mas modelos, bibliotecas nativas e binários baixados podem ter licenças próprias. Antes de empacotar qualquer modelo ou binário, registrar licença, origem, versão e checksum.

## 1. Setup inicial local-first

### Comportamento desejado

O onboarding deve ser retomável e não depender de serviços externos.

Fluxo proposto:

1. Boas-vindas e explicação de privacidade.
2. Verificação do sistema operacional e arquitetura.
3. Permissão do microfone.
4. Detecção de dispositivos de áudio.
5. Detecção de GPU e runtimes disponíveis.
6. Seleção do modelo local.
7. Download do modelo, se necessário.
8. Teste curto de gravação e transcrição.
9. Configuração da hotkey global.
10. Configuração do destino: colar automaticamente, copiar para clipboard ou salvar em arquivo.
11. Finalização e abertura do aplicativo.

### O que remover em relação ao OpenWhispr

- autenticação;
- verificação de e-mail;
- OpenWhispr Cloud;
- health check cloud;
- API keys obrigatórias;
- etapas de agente de IA;
- sincronização de onboarding entre dispositivos.

### Persistência do onboarding

Persistir localmente:

```text
onboarding_completed
onboarding_current_step
selected_transcriber
selected_model
microphone_permission_status
paste_capability_status
global_hotkey
```

O botão de avançar deve permitir continuar quando a capacidade for opcional. A única dependência obrigatória para ditar é ter uma entrada de áudio funcional e um transcriber disponível.

### Preflight local

Criar um preflight com checks independentes:

```text
audio_input
microphone_permission
transcriber_runtime
selected_model
gpu_runtime, quando selecionado
global_hotkey
clipboard
automatic_paste, opcional
disk_space
```

Cada check deve retornar:

```json
{
  "component": "microphone",
  "status": "ok | warning | error",
  "message": "...",
  "remediation": "..."
}
```

## 2. Colagem automática: análise e desenho

### Pipeline descoberto

O OpenWhispr não apenas escreve no clipboard. O fluxo é:

```text
texto final
  ↓
salva clipboard atual
  ↓
escreve texto no clipboard
  ↓
detecta o sistema e a janela alvo
  ↓
simula Cmd+V, Ctrl+V, Shift+Insert ou equivalente
  ↓
aguarda a aplicação processar
  ↓
restaura o clipboard original se ele ainda contiver o texto inserido
```

### Proteções importantes

- Uma fila impede duas colagens simultâneas de corromperem o clipboard.
- O clipboard anterior pode conter texto, HTML, RTF ou imagem.
- A restauração só ocorre se o clipboard ainda tiver o texto inserido pelo aplicativo.
- Se o usuário copiar outra coisa durante o atraso, a restauração é cancelada.
- O clipboard primário do Linux também é tratado separadamente.
- Existe fallback para copiar apenas, sem bloquear o ditado.
- A operação registra método, plataforma, duração e erro sem registrar o conteúdo completo em logs.

### Estratégias por plataforma

#### Windows

Ordem de preferência encontrada:

1. binário nativo usando `SendInput`;
2. `nircmd`, quando disponível;
3. PowerShell/SendKeys;
4. clipboard com instrução para colagem manual.

O binário nativo é importante para reduzir problemas em terminais, editores e aplicações que não respondem bem a PowerShell.

#### macOS

Ordem de preferência encontrada:

1. binário nativo baseado em eventos de teclado;
2. AppleScript simulando `Cmd+V`;
3. clipboard com colagem manual.

A colagem automática depende da permissão de Accessibility. O microfone e Accessibility devem ser verificados separadamente.

#### Linux

O OpenWhispr diferencia X11, Wayland, XWayland, GNOME, KDE e compositores wlroots.

Estratégias encontradas:

- binário nativo com `uinput`;
- portal RemoteDesktop;
- XTest/XWayland;
- `wtype` para Wayland/wlroots;
- `xdotool` para X11/XWayland;
- `ydotool` com daemon ativo;
- `Shift+Insert` em terminais;
- `Ctrl+Shift+V` em terminais quando necessário;
- fallback de digitação via `xdotool type`.

### Implementação no AudioScribe

Criar uma camada única, por exemplo:

```text
core/interfaces/output_handler.py
core/implementations/output/clipboard_handler.py
core/implementations/output/auto_paste_handler.py
electron/src/paste/
```

O Electron deve ser responsável pela automação do desktop. O Python deve enviar um evento estruturado com o texto final e as opções, sem montar comandos shell concatenando o texto.

Contrato sugerido:

```json
{
  "text": "texto final",
  "automatic": true,
  "restore_clipboard": true,
  "allow_clipboard_fallback": true,
  "source": "dictation"
}
```

Resposta sugerida:

```json
{
  "status": "pasted | copied | failed",
  "method": "sendinput | applescript | xdotool | clipboard",
  "restored_clipboard": true,
  "error_code": null
}
```

### Critérios de aceite da colagem

- Texto simples é colado em editor, navegador, terminal e campo de diálogo.
- Clipboard anterior é restaurado sem destruir uma cópia feita pelo usuário durante a operação.
- A falha de colagem não perde o texto: ele permanece disponível no clipboard.
- O conteúdo não é passado como comando shell.
- Existem testes unitários para seleção de estratégia e restauração.
- Existem testes manuais por plataforma e sessão gráfica.

## 3. Histórico de transcrições

### O que o OpenWhispr faz

O histórico é persistido em SQLite, não apenas mantido na memória da interface.

A tabela principal começa com:

```sql
CREATE TABLE transcriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Depois recebe metadados para status, texto bruto, áudio, descarte, retenção e rota de transcrição.

Funcionalidades relevantes:

- salvar cada transcrição concluída;
- manter texto bruto e texto processado separadamente;
- listar por data, mais recente primeiro;
- copiar novamente;
- excluir um item;
- limpar todo o histórico;
- marcar transcrição descartada sem necessariamente apagar imediatamente o áudio;
- retenção configurável;
- reprocessamento/retry;
- agrupamento visual por data;
- indicação de modelo, duração e origem;
- armazenamento opcional do áudio associado.

### Estado atual do AudioScribe

O AudioScribe já tem uma lista visual de transcrições no Electron, mas a persistência e o contrato de histórico ainda não estão estruturados como um banco local completo. O `TranscriptionOrchestrator` já produz eventos de transcrição e deve ser o ponto de integração.

### Modelo local proposto

```sql
CREATE TABLE transcriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id TEXT NOT NULL UNIQUE,
  text TEXT NOT NULL,
  raw_text TEXT,
  status TEXT NOT NULL DEFAULT 'completed',
  source TEXT NOT NULL DEFAULT 'dictation',
  model TEXT,
  provider TEXT,
  language TEXT,
  duration_ms INTEGER,
  audio_path TEXT,
  error_code TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);
```

Não incluir `cloud_id`, `sync_status` ou qualquer coluna necessária somente para sincronização remota.

### Interface mínima

```text
save_transcription()
list_transcriptions(limit, offset, filters)
get_transcription(id)
copy_transcription(id)
delete_transcription(id)
clear_transcriptions()
purge_expired_transcriptions()
retry_transcription(id)
```

### Critérios de aceite do histórico

- Toda transcrição finalizada aparece após reiniciar o aplicativo.
- Texto bruto e texto final podem ser consultados separadamente.
- Histórico não depende de internet.
- Usuário consegue copiar, excluir e limpar itens.
- Retenção pode ser desativada ou configurada.
- Falhas não geram registros indistinguíveis de transcrições concluídas.
- Áudios temporários são removidos conforme a política configurada.

## 4. Snippets inspirados no WhisperFlow/OpenWhispr

### Conceito

Um snippet associa uma expressão falada a um texto maior:

```text
gatilho: "minha assinatura"
texto: "Atenciosamente,\nRodolfo"
```

Durante o pós-processamento, o gatilho é substituído antes da colagem.

### Comportamento encontrado

- snippets têm `trigger` e `replacement`;
- gatilhos duplicados são rejeitados sem diferenciar maiúsculas/minúsculas;
- o matching usa limites de palavra, evitando substituir dentro de outra palavra;
- gatilhos mais longos têm prioridade sobre gatilhos menores;
- normalização Unicode é aplicada;
- edição e remoção ocorrem pela interface;
- snippets podem ser incluídos como palavras de dica para o transcriber/pós-processador;
- existe busca por gatilho e conteúdo de substituição;
- o texto de substituição pode ter múltiplas linhas.

### Modelo local

```sql
CREATE TABLE snippets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trigger TEXT NOT NULL,
  replacement TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX snippets_trigger_ci
  ON snippets(lower(trigger));
```

### Ordem do pipeline

```text
áudio
  ↓
transcrição bruta
  ↓
correção/dicionário opcional
  ↓
expansão de snippets
  ↓
formatação final
  ↓
salvar no histórico
  ↓
colar/copiar
```

O histórico deve armazenar o texto final e, quando possível, o texto bruto antes das expansões para permitir auditoria e retry.

### Cuidados

- Não substituir gatilhos dentro de palavras maiores.
- Evitar expansão em loop quando um replacement contém outro trigger.
- Definir limite de tamanho para gatilho e replacement.
- Permitir desligar snippets globalmente.
- Mostrar uma prévia da expansão.
- Testar português, acentos, Unicode e pontuação.
- Não enviar snippets para nenhum serviço remoto no modo local.

### Interface sugerida

- campo rápido para adicionar gatilho;
- editor de texto para expansão;
- lista pesquisável;
- editar, ativar/desativar e remover;
- importar/exportar JSON ou TXT;
- exemplos iniciais opcionais, nunca obrigatórios.

## 5. Dicionário local

O dicionário deve ser separado dos snippets.

```text
dicionário = palavras e nomes que ajudam o reconhecimento
snippet = gatilho que vira um texto maior
```

Tabela sugerida:

```sql
CREATE TABLE dictionary_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  word TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  use_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(word COLLATE NOCASE)
);
```

Implementar:

- adicionar/remover palavra;
- origem `manual` ou `learned`;
- importação por vírgula ou linha;
- exportação;
- deduplicação case-insensitive;
- aprendizado de correções, se o usuário ativar;
- SQLite como fonte da verdade;
- cache somente para leitura rápida.

## 6. GPU, Whisper e Parakeet

### Registro de modelos

Criar um registro local declarativo contendo:

```text
id
nome
provider
runtime
idiomas
tamanho
URL
arquivos esperados
checksum
streaming
requisitos de hardware
licença
```

### Backends

```text
Whisper CPU
Whisper CUDA — NVIDIA
Whisper Vulkan — AMD/Intel/NVIDIA compatível
Whisper Metal — macOS, se aplicável ao runtime escolhido
Parakeet ONNX — inicialmente CPU/local
```

Não afirmar que Parakeet usa GPU apenas por ser um modelo NVIDIA. No OpenWhispr, Parakeet é executado via sherpa-onnx e servidor WebSocket local; a aceleração CUDA/Vulkan está mais claramente ligada aos binários de Whisper.cpp.

### Gerenciador de runtime

O download deve:

- detectar plataforma e arquitetura;
- verificar espaço em disco;
- baixar para arquivo temporário;
- mostrar progresso;
- permitir cancelamento;
- verificar SHA-256;
- extrair com segurança;
- validar arquivos esperados;
- instalar atomicamente;
- limpar temporários;
- remover runtime/modelo pela interface.

### Fallback

```text
GPU configurada
  ↓ falhou
CPU com o mesmo modelo
  ↓ falhou
modelo menor
  ↓ falhou
backend alternativo disponível
```

O usuário deve ser avisado, mas não perder a transcrição por causa de uma falha de GPU.

## 7. Permissões e capacidade de saída

### Obrigatórias

- microfone;
- hotkey global, quando o modo de hotkey estiver ativado;
- pelo menos uma saída: clipboard ou arquivo.

### Opcionais

- Accessibility no macOS;
- colagem automática;
- ferramentas específicas do Linux;
- captura de áudio do sistema.

### API de capacidade

Criar um diagnóstico como:

```json
{
  "microphone": { "granted": true },
  "clipboard": { "available": true },
  "automatic_paste": {
    "available": false,
    "platform": "linux",
    "method": null,
    "recommended_install": "xdotool"
  }
}
```

O usuário deve sempre poder escolher “copiar para clipboard” quando a colagem automática não estiver disponível.

## 8. Arquitetura alvo

```text
Electron UI
  ├── onboarding
  ├── history
  ├── snippets
  ├── dictionary
  ├── model settings
  └── diagnostics
        ↓ IPC estruturado
Desktop runtime
  ├── permission manager
  ├── paste manager
  ├── history repository
  ├── snippets repository
  ├── dictionary repository
  └── model manager
        ↓ interfaces Python
AudioScribe engine
  ├── audio input
  ├── local transcriber
  ├── optional post-processor
  ├── orchestrator
  └── output events
```

O banco local pode ser acessado pelo processo desktop, evitando concorrência direta entre Python e renderer.

## 9. Plano de execução por fases

### Fase 0 — contratos e segurança

- definir eventos de transcrição;
- definir contrato de paste;
- definir diretório de dados local;
- definir política de retenção;
- definir testes de segurança para comandos e paths;
- registrar licenças dos componentes externos.

### Fase 1 — histórico local

- criar repositório SQLite;
- persistir transcrições;
- conectar eventos do orchestrator;
- implementar listagem, cópia, exclusão e limpeza;
- persistir após reinício;
- adicionar testes.

### Fase 2 — paste manager

- fila de colagem;
- salvar/restaurar clipboard;
- fallback para cópia;
- Windows;
- macOS;
- Linux X11;
- Linux Wayland;
- diagnóstico e mensagens de remediação.

### Fase 3 — onboarding local-first

- fluxo retomável;
- preflight;
- seleção de modelo;
- teste de gravação;
- configuração da hotkey;
- conclusão sem conta ou rede.

### Fase 4 — snippets

- tabela SQLite;
- CRUD;
- matcher Unicode;
- expansão no pipeline;
- busca, edição, ativação e remoção;
- importação/exportação;
- testes de limites de palavra e prioridade.

### Fase 5 — dicionário

- tabela SQLite;
- importação/exportação;
- integração com prompt/hints;
- aprendizado opcional;
- prevenção de sobrescrita por cache antigo.

### Fase 6 — modelos locais

- registro de modelos;
- downloader;
- checksums;
- Whisper CPU;
- Parakeet local;
- status e diagnósticos;
- cache e remoção.

### Fase 7 — GPU

- detecção NVIDIA;
- CUDA;
- detecção Vulkan;
- fallback CPU;
- métricas de latência;
- validação real do suporte GPU do Parakeet antes de prometer a capacidade.

## 10. Fora de escopo

Não implementar como parte do produto gratuito local-first:

- conta obrigatória;
- servidor próprio de transcrição;
- sincronização de histórico;
- sincronização de snippets/dicionário;
- billing;
- limite artificial de uso;
- telemetry obrigatória;
- upload automático de áudio;
- dependência de API paga para o caminho padrão.

## 11. Testes mínimos

### Unitários

- normalização e matching de snippets;
- prioridade de gatilhos;
- deduplicação do dicionário;
- reconciliação do histórico;
- seleção de backend;
- fallback GPU → CPU;
- restauração segura do clipboard;
- seleção de ferramentas Linux;
- parsing do registro de modelos.

### Integração

- gravação → transcrição → snippet → histórico → clipboard;
- reinício do aplicativo preservando histórico;
- modelo ausente acionando download;
- download cancelado sem deixar instalação parcial;
- clipboard alterado pelo usuário não sendo sobrescrito;
- ausência de Accessibility resultando em cópia manual;
- falha do transcriber gerando status de erro e retry.

### Manual por plataforma

- Windows 10/11;
- macOS com e sem Accessibility;
- Linux X11;
- Linux Wayland GNOME;
- Linux Wayland KDE;
- Linux wlroots/Hyprland/Sway;
- terminal, navegador, editor e aplicações Electron.

## Definição de pronto do produto local

O AudioScribe estará pronto para a primeira versão local quando o usuário conseguir:

1. instalar sem criar conta;
2. escolher ou baixar um modelo local;
3. gravar sem internet após a instalação;
4. transcrever usando CPU;
5. colar automaticamente quando o sistema permitir;
6. copiar manualmente quando não permitir;
7. consultar o histórico depois de reiniciar;
8. usar snippets e dicionário local;
9. apagar/exportar seus dados;
10. entender claramente quando algo depende de internet, GPU ou ferramenta externa.
