"""
Script para rodar o scraper manualmente.
Uso: python scripts/run_scrape.py
"""

import sys
from pathlib import Path

# Adiciona a raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import HISTORY_DB_PATH, SEARCH_TERM, setup_logging
from src.scraper import run_scrape
from src.telegram_notifier import send_results


def main():
    setup_logging()

    try:
        from scripts.sync_cookie import sync
        sync()
    except Exception as e:
        print(f"⚠️ Não foi possível sincronizar o cookie com a API: {e}")

    result = run_scrape(HISTORY_DB_PATH)

    print(f"\n📊 Resultado:")
    print(f"   {result.total_raw} brutos analisados")
    print(f"   {result.skipped_seen} já vistos")
    print(f"   {result.skipped_likes} likes baixos")
    print(f"   {len(result.long_videos)} candidatos longos")
    print(f"   {len(result.short_videos)} candidatos shorts")

    if result.next_episode:
        print(f"   📌 Continuação: EP {result.next_episode['episode']}")

    # Envia ao Telegram
    print("\n📤 Enviando ao Telegram...")
    send_results(result)
    print("✅ Concluído!")


if __name__ == "__main__":
    main()
