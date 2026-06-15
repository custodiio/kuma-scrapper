"""
Script para rodar o bot Telegram em modo polling (teste local).
Uso: python scripts/run_bot.py
"""

import sys
from pathlib import Path

# Adiciona a raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.telegram_bot import run_bot


if __name__ == "__main__":
    print("🤖 Iniciando Douyin Scout Bot...")
    try:
        from scripts.sync_cookie import sync
        sync()
    except Exception as e:
        print(f"⚠️ Não foi possível sincronizar o cookie com a API: {e}")
    print("   Pressione Ctrl+C para parar\n")
    run_bot()
