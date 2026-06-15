import os
import re
import time
import httpx
import logging
from datetime import datetime
from src import database

logger = logging.getLogger(__name__)

def clean_html_tags(text: str) -> str:
    """Remove as tags HTML como <em class="keyword"> da string retornada pelo Bilibili."""
    return re.sub(r'<[^>]*>', '', text)

def duration_str_to_seconds(dur_str: str) -> int:
    """Converte strings de duração do Bilibili (ex: '4:44', '01:23:45') em segundos."""
    try:
        parts = list(map(int, dur_str.split(":")))
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return 0
    except:
        return 0

async def fetch_bilibili_search_videos(keyword: str, max_pages: int = 3) -> list:
    """
    Busca vídeos no Bilibili de forma pública usando sessão com cookies automáticos.
    Não exige login ou WBI signatures complexas.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"
    }
    
    results = []
    
    # Usando httpx.AsyncClient para manter cookies de visitante
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
        try:
            logger.info("Coletando cookies do Bilibili na home page...")
            await client.get("https://www.bilibili.com/")
        except Exception as ec:
            logger.warning(f"Falha ao coletar cookies de visitante na home do Bilibili: {ec}")
            
        import time
        now_ts = int(time.time())
        one_week_ago_ts = now_ts - (7 * 24 * 3600)
        
        search_url = "https://api.bilibili.com/x/web-interface/search/type"
        
        for page in range(1, max_pages + 1):
            params = {
                "search_type": "video",
                "keyword": keyword,
                "order": "totalrank",                     # Classificação abrangente
                "duration": "1",                          # Menos de 10 min
                "pubtime_begin_s": str(one_week_ago_ts),  # Início dos últimos 7 dias
                "pubtime_end_s": str(now_ts),              # Fim (atual)
                "tids": "0",
                "page": str(page)
            }
            try:
                logger.info(f"Buscando termo '{keyword}' no Bilibili - Página {page}...")
                response = await client.get(search_url, params=params)
                if response.status_code != 200:
                    logger.error(f"Erro HTTP {response.status_code} na busca do Bilibili")
                    break
                    
                data = response.json()
                if data.get("code") != 0:
                    logger.error(f"Erro na API de busca do Bilibili (code={data.get('code')}): {data.get('message')}")
                    break
                    
                videos = data.get("data", {}).get("result", [])
                if not videos:
                    logger.info("Nenhum vídeo adicional retornado.")
                    break
                    
                for v in videos:
                    bvid = v.get("bvid")
                    title = clean_html_tags(v.get("title", ""))
                    author = v.get("author", "Desconhecido")
                    pic = v.get("pic", "")
                    # Garante esquema HTTPS para a URL da capa
                    if pic and pic.startswith("//"):
                        pic = "https:" + pic
                        
                    duration_str = v.get("duration", "00:00")
                    duration_secs = duration_str_to_seconds(duration_str)
                    
                    # Views e Likes
                    views = int(v.get("play", 0))
                    likes = int(v.get("like", 0))
                    
                    # Score de Hype
                    hype_score = views + likes * 5
                    
                    pubdate = v.get("pubdate")
                    pubdate_dt = None
                    if pubdate:
                        try:
                            pubdate_dt = datetime.fromtimestamp(pubdate).strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            pass
                            
                    results.append({
                        "bvid": bvid,
                        "title": title,
                        "author": author,
                        "pic": pic,
                        "duration_seconds": duration_secs,
                        "views": views,
                        "likes": likes,
                        "hype_score": hype_score,
                        "published_at": pubdate_dt
                    })
            except Exception as e:
                logger.error(f"Erro ao buscar página {page}: {e}")
                break
                
    return results

async def run_single_scraping(keyword: str, content_type: str) -> int:
    """Roda a busca para um termo e tipo de conteúdo específicos e grava no banco."""
    logger.info(f"Executando busca no Bilibili por '{keyword}' ({content_type})...")
    raw_videos = await fetch_bilibili_search_videos(keyword, max_pages=3)
    if not raw_videos:
        logger.warning(f"Nenhum resultado obtido na busca por '{keyword}' ({content_type}).")
        return 0
        
    filtered_videos = []
    now_ts = time.time()
    one_week_secs = 7 * 24 * 3600
    
    for v in raw_videos:
        pubdate_dt = datetime.strptime(v["published_at"], "%Y-%m-%d %H:%M:%S") if v["published_at"] else None
        pubdate_ts = pubdate_dt.timestamp() if pubdate_dt else 0
        
        is_recent = (now_ts - pubdate_ts <= one_week_secs)
        is_under_10min = (v["duration_seconds"] < 600)
        
        if is_recent and is_under_10min:
            filtered_videos.append(v)
            
    logger.info(f"Filtro para '{keyword}': {len(filtered_videos)}/{len(raw_videos)} vídeos atendem aos critérios.")
    
    inserted = database.add_search_results(filtered_videos, content_type=content_type)
    logger.info(f"Triagem atualizada para '{content_type}': {inserted} novos vídeos adicionados.")
    return inserted

async def run_search_scraping():
    """
    Roda o fluxo completo de busca geral no Bilibili para todos os termos de busca cadastrados.
    """
    logger.info("Iniciando cron job de busca geral...")
    
    # Limpa resultados de busca antigos expirados (mais de 14 dias pendentes) para poupar espaço
    database.clear_old_search_results(days=14)
    
    anime_terms = database.get_search_terms("anime")
    manhwa_terms = database.get_search_terms("manhwa")
    
    # Fallbacks de segurança caso não existam termos no banco
    if not anime_terms:
        anime_terms = [{"term": "新番解说"}]
    if not manhwa_terms:
        manhwa_terms = [{"term": "韩漫解说"}]
        
    inserted_anime = 0
    for item in anime_terms:
        try:
            inserted_anime += await run_single_scraping(item["term"], "anime")
        except Exception as e:
            logger.error(f"Erro ao buscar termo '{item['term']}' (anime): {e}")
        
    inserted_manhwa = 0
    for item in manhwa_terms:
        try:
            inserted_manhwa += await run_single_scraping(item["term"], "manhwa")
        except Exception as e:
            logger.error(f"Erro ao buscar termo '{item['term']}' (manhwa): {e}")
        
    total_inserted = inserted_anime + inserted_manhwa
    logger.info(f"Busca geral concluída. Total de novos vídeos inseridos: {total_inserted}")
    return total_inserted

