import os
import sys
import io
import asyncio
import sqlite3

# Configura o stdout/stderr para UTF-8 no Windows
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

# Garante o path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import database, search_scrapper

def show_db_status():
    print("=== ESTADO DO BANCO DE DADOS SQLite ===")
    conn = database.get_connection()
    cursor = conn.cursor()
    
    # Canais
    cursor.execute("SELECT COUNT(*) FROM channels")
    print(f"Canais cadastrados: {cursor.fetchone()[0]}")
    
    # Vídeos processados
    try:
        cursor.execute("SELECT status, COUNT(*) FROM processed_videos GROUP BY status")
        print("Vídeos na tabela processed_videos por status:")
        for row in cursor.fetchall():
            print(f"  - {row[0]}: {row[1]}")
    except Exception as e:
        print(f"Erro ao ler processed_videos: {e}")
        
    # Resultados de busca
    try:
        cursor.execute("SELECT status, COUNT(*) FROM search_results GROUP BY status")
        print("Vídeos na tabela search_results por status:")
        for row in cursor.fetchall():
            print(f"  - {row[0]}: {row[1]}")
    except Exception as e:
        print(f"Erro ao ler search_results: {e}")
        
    conn.close()

async def debug_bili_search():
    print("\n=== DEPURANDO BUSCA BILIBILI ===")
    raw_results = await search_scrapper.fetch_bilibili_search_videos("新番解说", max_pages=3)
    print(f"Total de vídeos retornados pela busca bruta do Bilibili: {len(raw_results)}")
    
    if len(raw_results) == 0:
        print("A busca bruta retornou 0 vídeos. Pode haver bloqueio por IP ou cookies inválidos.")
        return
        
    import time
    now_ts = time.time()
    one_week_secs = 7 * 24 * 3600
    
    print("\nPrimeiros 5 resultados da busca bruta:")
    for idx, v in enumerate(raw_results[:5], 1):
        from datetime import datetime
        pub_dt = datetime.strptime(v["published_at"], "%Y-%m-%d %H:%M:%S") if v["published_at"] else None
        pub_ts = pub_dt.timestamp() if pub_dt else 0
        diff_days = (now_ts - pub_ts) / (24 * 3600)
        
        is_recent = (now_ts - pub_ts <= one_week_secs)
        is_under_10min = (v["duration_seconds"] < 600)
        
        print(f"{idx}. {v['title'][:40]}...")
        print(f"   Duração: {v['duration_seconds']}s (<600s? {is_under_10min})")
        print(f"   Publicado em: {v['published_at']} ({diff_days:.1f} dias atrás | Recente? {is_recent})")
        
    inserted = await search_scrapper.run_search_scraping()
    print(f"\nTotal inserido/atualizado no banco pela busca geral: {inserted}")

async def main():
    show_db_status()
    await debug_bili_search()

if __name__ == "__main__":
    asyncio.run(main())
