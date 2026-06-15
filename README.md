# 🎌 Douyin Anime Scraper

Scraper diário automatizado do Douyin para curadoria de vídeos de anime (recaps e estreias semanais), com filtragem inteligente por duração, rastreamento de histórico, e notificação via Telegram.

## Funcionalidades

- 🔍 **Busca automatizada** por termos em chinês no Douyin
- 📊 **Filtragem inteligente** por duração, likes, e duplicatas
- 🎌 **Vídeos longos** (4-10min) → candidatos para recaps
- ⚡ **Vídeos curtos** (<4min) → candidatos para Shorts
- 📺 **Detecção de episódios** — identifica continuação automática
- 📱 **Notificação Telegram** com cards formatados
- 🤖 **Bot Telegram** para marcar como postado e ver histórico
- 💾 **SQLite** para rastreamento de vídeos já vistos

## Setup Rápido

### 1. Clone e instale dependências

```bash
cd d:\Applications\scrapper_douyin
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure o .env

```bash
copy .env.example .env
```

Preencha as variáveis obrigatórias:
- `TELEGRAM_TOKEN` — Token do @BotFather ([criar novo bot](https://t.me/BotFather))
- `TELEGRAM_CHAT_ID` — Seu chat ID
- `DOUYIN_COOKIE` — Cookie do Douyin ([guia](docs/SETUP_COOKIE.md))

### 3. Suba o Evil0ctal API

```bash
git clone --depth=1 https://github.com/Evil0ctal/Douyin_TikTok_Download_API douyin_api
cd douyin_api
pip install -r requirements.txt
python main.py
```

A API roda em `http://localhost:5555`.

### 4. Rode o scraper

```bash
python scripts/run_scrape.py
```

### 5. (Opcional) Rode o bot Telegram

```bash
python scripts/run_bot.py
```

## Estrutura

```
├── .env.example          # Template de variáveis
├── requirements.txt      # Dependências Python
├── src/
│   ├── config.py             # Configuração centralizada
│   ├── database.py           # SQLite histórico
│   ├── episode_detector.py   # Regex para episódios chineses
│   ├── scraper.py            # Lógica principal de busca
│   ├── telegram_notifier.py  # Cards formatados
│   └── telegram_bot.py       # Bot com /postado, /historico, /status
├── scripts/
│   ├── run_scrape.py         # Execução manual
│   └── run_bot.py            # Bot Telegram local
├── docker/                   # Docker para deploy
└── docs/                     # Documentação
```

## Comandos do Bot Telegram

| Comando | Descrição |
|---------|-----------|
| `/postado <video_id>` | Marca vídeo como postado |
| `/historico` | Lista últimos 10 postados |
| `/status` | Estatísticas do banco |
| `/buscar <termo>` | Busca manual no Douyin |

## Filtros

| Filtro | Regra |
|--------|-------|
| **Já visto** | `video_id` em SQLite → pula |
| **Vídeo longo** | 4min < duração ≤ 10min → recap |
| **Vídeo curto** | duração < 4min → Shorts |
| **Episódio** | Próximo EP do último postado → prioridade |
| **Qualidade** | likes > 500 (configurável) |

## Documentação

- [📋 Termos de busca](docs/SEARCH_TERMS.md) — Lista de termos em chinês
- [🍪 Setup Cookie](docs/SETUP_COOKIE.md) — Como obter o cookie do Douyin
