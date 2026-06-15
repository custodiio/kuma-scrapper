import os
import sys
import io
import asyncio

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

from src import search_scrapper

async def test_search():
    print("=== TESTANDO BUSCA COM totalrank (CLASSIFICAÇÃO ABRANGENTE) ===")
    
    # Faz a busca bruta mudando o parâmetro de ordenação manualmente para totalrank
    # Vamos fazer a busca e listar os vídeos e suas datas
    import httpx
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"
    }
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
        await client.get("https://www.bilibili.com/")
        
        import time
        now_ts = int(time.time())
        one_week_ago_ts = now_ts - (7 * 24 * 3600)
        
        search_url = "https://api.bilibili.com/x/web-interface/search/type"
        params = {
            "search_type": "video",
            "keyword": "新番解说",
            "order": "totalrank",       # Classificação abrangente
            "duration": "1",           # Filtro nativo Bilibili: 1 = Menos de 10 min
            "pubtime_begin_s": str(one_week_ago_ts),  # Início dos últimos 7 dias
            "pubtime_end_s": str(now_ts),              # Fim (atual)
            "tids": "0",
            "page": "1"
        }
        
        response = await client.get(search_url, params=params)
        data = response.json()
        videos = data.get("data", {}).get("result", [])
        print(f"Total de vídeos retornados com filtros nativos (página 1): {len(videos)}")
        
        for idx, v in enumerate(videos[:10], 1):
            title = search_scrapper.clean_html_tags(v.get("title", ""))
            pubdate = v.get("pubdate", 0)
            from datetime import datetime
            pub_dt = datetime.fromtimestamp(pubdate)
            diff_days = (now_ts - pubdate) / (24 * 3600)
            
            is_recent = (now_ts - pubdate <= (7 * 24 * 3600))
            dur_str = v.get("duration", "0:00")
            dur_secs = search_scrapper.duration_str_to_seconds(dur_str)
            is_under_10min = dur_secs < 600
            
            print(f"{idx}. {title[:40]}...")
            print(f"   Duração: {dur_str} ({dur_secs}s | <10m? {is_under_10min})")
            print(f"   Publicado em: {pub_dt} ({diff_days:.1f} dias atrás | Recente? {is_recent})")

if __name__ == "__main__":
    asyncio.run(test_search())
