# 👑 AI Empire — Como usar

**Você acabou de baixar um agente de IA local, completo, com interface conversacional.**

## 🚀 Em 30 segundos (instalar + usar)

```bash
unzip ai-empire.zip
cd ai-empire
./install.sh              # one-command install
```

O `install.sh` faz tudo:
- ✅ Verifica Docker, Python, espaço em disco
- ✅ Pede pra você escolher o profile (core / agents / all)
- ✅ Sobe os containers
- ✅ Baixa o modelo Ollama (llama3.3)
- ✅ Instala deps Python pro agent CLI
- ✅ Roda 104 testes pra confirmar que tá tudo OK
- ✅ Abre o chat pra você

## 💬 Três formas de usar

### 1. Chat no terminal (CLI)
```bash
./empire chat
```

Você digita, o agent responde. Exemplos do que falar:
```
👑 > find me 20 SaaS CTOs in Brazil
👑 > send a cold email to that lead
👑 > generate an Instagram post about AI agents
👑 > test the circuit breaker
👑 > how is everything
👑 > help
```

### 2. Chat no browser (Web UI)
```bash
./empire ui
```

Abre um chat visual em **http://localhost:7777** com botões de ação rápida, sidebar com skills, indicador de "thinking", etc. Conecta via WebSocket — você vê cada resposta em tempo real.

### 3. Testes em linguagem natural
```bash
./empire test the circuit breaker
./empire test self healing
./empire test all
```

Não é "smoke test". O agent parseia o que você falou, mapeia pra suite de pytest correta, roda, e te dá um resumo em linguagem natural:

```
**✅ All 18 tests passed**

Ran: `tests/test_circuit_breaker.py`

tests/test_circuit_breaker.py ..................                         [100%]
============================== 18 passed in 1.23s ==============================
```

## 🎯 O que você consegue fazer

| Fala isso | O agent faz |
|---|---|
| "find 50 fintech CEOs in France" | Roda lead-sourcing |
| "qualify these leads" | Score 0-100 cada um |
| "send a cold email to that lead" | Draft personalizado |
| "generate an Instagram post about X" | Pede pro ComfyUI gerar |
| "publish this to Twitter and LinkedIn" | Posta via n8n |
| "go to this URL and find the email" | browser-use navega |
| "watch this YouTube and summarize" | yt-dlp + Whisper |
| "test the failover" | Roda suite de testes |
| "how is everything" | Health check de 6+ serviços |
| "help" | Lista tudo que ele faz |

## 🛠️ Outros comandos úteis

```bash
./empire health          # status dos serviços
./empire start all       # sobe TUDO (38+ serviços)
./empire start design    # sobe só design (ComfyUI, Penpot, etc)
./empire stop            # para tudo
./empire                 # menu interativo
```

## 🔧 Como funciona (resumo)

```
Você fala em linguagem natural
        ↓
   agent.parse_intent()        ← entende o que você quer
        ↓
   skill handler               ← executa a skill certa
        ↓
   HTTP call ao serviço        ← LangGraph / n8n / ComfyUI / etc
        ↓
   resposta formatada          ← texto natural de volta
```

## 📚 Skills disponíveis (18)

Todas carregadas como tools. Você não precisa aprender a chamar cada uma — o agent faz isso.

| Skill | O que faz |
|---|---|
| `lead-sourcing` | Acha leads em LinkedIn, Maps, Reddit, Quora |
| `lead-qualification` | Score 0-100 + tags |
| `outreach-email/whatsapp/linkedin` | Outreach multi-canal |
| `design-image/video` | Gera imagens e vídeos (ComfyUI, Open-Sora) |
| `browser-automation` | LLM dirige browser (navega, clica, preenche) |
| `video-research` | yt-dlp + Whisper + LLM summary |
| `publishing-social` | Posta em X, LinkedIn, IG, FB, etc |
| `inbox-management` | Inbox unificado (Chatwoot + LLM drafts) |
| `client-approach` | Pipeline SDR completo (autônomo) |
| `lead-pipeline` | One-button end-to-end |
| `ai-gateway` | LiteLLM + OmniRoute (multi-provider) |
| `self-healing` | Agente se conserta quando falha |
| `self-learning` | Aprende com feedback (A/B tests, UCB1) |
| `failover` | Auto-promote quando servidor cai |

## 🧪 Testes (104 reais)

```bash
./empire test all
```

104 testes reais (não smoke). Eles:
- Sobem HTTP servers reais em portas livres
- Matam serviços e verificam recuperação
- Fazem requests HTTP reais
- Verificam timing real (backoff)
- Testam concorrência (50 calls simultâneas)
- Validam probabilidades (z-test em A/B)

## ❓ Troubleshooting

**"docker not found"** → instale Docker Desktop

**"pytest not found"** → o install.sh instala. Se der erro, rode: `pip install --break-system-packages pytest pytest-asyncio httpx fastapi uvicorn pydantic`

**Web UI não abre** → `./empire ui` no terminal, espera 2s, vai em http://localhost:7777

**ComfyUI/Penpot/etc não respondem** → `./empire start design` pra subir o profile de design

**Quero parar tudo** → `./empire stop`

## 📂 Estrutura

```
ai-empire/
├── bin/empire               ← CLI entry point
├── web/                     ← Web UI (FastAPI + chat.html)
├── empire/                  ← Agent core (Python)
│   ├── agent/core.py        ← NL parsing + intent dispatch
│   └── nl/test_runner.py    ← Natural language → pytest
├── orchestrator/            ← LangGraph + CrewAI (Python)
├── skills/                  ← Skill implementations
├── workflows/               ← n8n starter workflows
├── .skills/                 ← Skill descriptions (Mavis)
├── docker-compose.yml       ← 38+ services
├── install.sh               ← one-command installer
└── README.md / TESTS.md / HOW-TO-USE.md
```

## 🎉 That's it

`./install.sh` e você tem um agente de IA conversacional, local, com 18 skills e 104 testes, em menos de 5 minutos.

Se algo não funcionar, fala "help" no chat e o agent te diz o que tá errado.
