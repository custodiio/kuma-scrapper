"""
Douyin Anime Scraper — Configuração centralizada.
Carrega variáveis do .env e valida as obrigatórias.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env do diretório raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

log = logging.getLogger(__name__)


# ─── Validação ───────────────────────────────────────────────────────────────

def _require(var: str) -> str:
    """Retorna o valor da variável ou encerra com erro."""
    value = os.getenv(var)
    if not value:
        log.critical(f"❌ Variável de ambiente obrigatória não definida: {var}")
        log.critical(f"   Copie .env.example para .env e preencha os valores.")
        sys.exit(1)
    return value


# ─── Telegram ────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN: str = _require("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID: str = _require("TELEGRAM_CHAT_ID")
AUTHORIZED_USERS: list[str] = [
    uid.strip()
    for uid in os.getenv("AUTHORIZED_TELEGRAM_USERS", TELEGRAM_CHAT_ID).split(",")
    if uid.strip()
]


# ─── Douyin ──────────────────────────────────────────────────────────────────

DOUYIN_COOKIE: str = os.getenv("DOUYIN_COOKIE", "")
DOUYIN_API_BASE: str = os.getenv("DOUYIN_API_BASE", "http://localhost:5555")


# ─── Busca ───────────────────────────────────────────────────────────────────

SEARCH_TERM: str = os.getenv("SEARCH_TERM", "新番解说")
MAX_RESULTS: int = int(os.getenv("MAX_RESULTS", "30"))
MIN_LIKES: int = int(os.getenv("MIN_LIKES", "500"))


# ─── Duração (segundos) ─────────────────────────────────────────────────────

SHORT_MAX: int = 4 * 60      # < 4 min → candidato para Shorts
LONG_MIN: int = 4 * 60       # > 4 min
LONG_MAX: int = 10 * 60      # ≤ 10 min → candidato para recap


# ─── Banco de Dados ─────────────────────────────────────────────────────────

HISTORY_DB_PATH: str = os.getenv(
    "HISTORY_DB_PATH",
    str(PROJECT_ROOT / "data" / "history.db")
)


# ─── Logging ─────────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO):
    """Configura logging padrão do projeto."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
