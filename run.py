import os
import sys
import io
import time
import threading
from datetime import datetime
from dotenv import load_dotenv

# Configura o stdout/stderr para UTF-8 no Windows para evitar crashes com emojis/chines
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

# Carrega variáveis de ambiente ANTES de importar módulos locais que dependem de configurações
load_dotenv()

from src import database, telegram_bot, web_panel, search_scrapper

def run_scheduler():
    """Roda a busca geral a cada 1 hora de forma assíncrona usando seu próprio loop de eventos."""
    import asyncio
    
    # Cria e define o loop de eventos para a thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    print("⏰ Scheduler de Busca Geral iniciado (intervalo: 1 hora)...")
    
    # Espera 15 segundos antes da primeira busca para deixar o bot e o web panel carregarem completamente
    time.sleep(15)
    
    while True:
        try:
            print(f"[{datetime.now()}] Iniciando busca geral automática do Bilibili ('新番解说')...")
            inserted = loop.run_until_complete(search_scrapper.run_search_scraping())
            print(f"[{datetime.now()}] Busca concluída. {inserted} novos vídeos adicionados para triagem.")
        except Exception as e:
            print(f"⚠️ Erro no Scheduler: {e}")
            
        # Dorme de acordo com o intervalo definido no .env (padrão: 3 horas)
        interval_hours = int(os.getenv("SCRAPE_INTERVAL_HOURS", "3"))
        time.sleep(interval_hours * 3600)


def main():
    print("=" * 60)
    print("  Scrapper Douyin/Bilibili - Pipeline & Bot Launcher (Fase 2)")
    print("=" * 60)

    # Inicializa o banco de dados
    print("Inicializando banco de dados...")
    database.init_db()

    # Sincroniza cookies com o Evil0ctal
    try:
        from scripts import sync_cookie
        print("Sincronizando cookies com a API local...")
        sync_cookie.sync()
    except Exception as e:
        print(f"⚠️ Alerta: Falha ao executar sincronização de cookies: {e}")

    # 1. Inicia o Painel Web em uma thread daemon
    print("Iniciando Painel Web (FastAPI/Uvicorn na porta 5556)...")
    web_thread = threading.Thread(target=web_panel.run_panel, daemon=True)
    web_thread.start()

    # 2. Inicia o Scheduler de Busca em uma thread daemon
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # 3. Roda o Bot do Telegram na thread principal (bloqueante)
    try:
        telegram_bot.run_bot()
    except KeyboardInterrupt:
        print("\nFinalizado pelo usuário.")
    except Exception as e:
        print(f"❌ Erro fatal ao rodar o Bot do Telegram: {e}")

if __name__ == "__main__":
    main()
