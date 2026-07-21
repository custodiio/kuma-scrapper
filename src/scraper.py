"""
Douyin Anime Scraper — Módulo principal de scraping.
Busca vídeos no Douyin via Evil0ctal API, filtra por duração/likes/duplicatas,
detecta continuação de episódios, e retorna candidatos categorizados.
"""

import os
import time
import logging
import httpx
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

from src.config import (
    DOUYIN_API_BASE, SEARCH_TERM, MAX_RESULTS,
    MIN_LIKES, SHORT_MAX, LONG_MIN, LONG_MAX,
)
from src import database
from src.episode_detector import extract_episode, is_continuation

log = logging.getLogger(__name__)


# ─── Resultado do scraping ───────────────────────────────────────────────────

@dataclass
class ScrapeResult:
    """Resultado categorizado de uma execução de scraping."""
    long_videos: list = field(default_factory=list)     # 4–10 min (recaps)
    short_videos: list = field(default_factory=list)    # < 4 min (Shorts)
    next_episode: Optional[dict] = None                 # Continuação do último ep
    total_raw: int = 0                                  # Total bruto retornado
    skipped_seen: int = 0                               # Pulados por já vistos
    skipped_likes: int = 0                              # Pulados por likes baixos


# ─── Busca e Download no Douyin via Evil0ctal API ────────────────────────────

def download_douyin_video(video_url_or_id: str, output_path: str) -> bool:
    """
    Baixa o vídeo em alta definição sem marca d'água usando a API local do Evil0ctal.
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        log.info(f"📥 Baixando vídeo do Douyin ({video_url_or_id}) para {output_path}...")
        
        # 1. Tenta via endpoint /api/download
        api_download_url = f"{DOUYIN_API_BASE}/api/download"
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(api_download_url, params={"url": video_url_or_id, "prefix": "true", "with_watermark": "false"})
            if resp.status_code == 200 and len(resp.content) > 10000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                log.info(f"✅ Vídeo baixado com sucesso via /api/download ({os.path.getsize(output_path)} bytes)!")
                return True
                
        # 2. Fallback: busca url_list direta via fetch_one_video
        aweme_id = video_url_or_id.split("/")[-1] if "/" in video_url_or_id else video_url_or_id
        if aweme_id.isdigit():
            fetch_url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_one_video"
            with httpx.Client(timeout=30.0) as client:
                r_one = client.get(fetch_url, params={"aweme_id": aweme_id})
                if r_one.status_code == 200:
                    aweme_detail = r_one.json().get("data", {}).get("aweme_detail", {})
                    play_addr = aweme_detail.get("video", {}).get("play_addr", {}).get("url_list", [])
                    if play_addr:
                        real_vid_url = play_addr[0]
                        r_vid = client.get(real_vid_url, headers={"User-Agent": "Mozilla/5.0"})
                        if r_vid.status_code == 200 and len(r_vid.content) > 10000:
                            with open(output_path, "wb") as f:
                                f.write(r_vid.content)
                            log.info(f"✅ Vídeo baixado via fallback play_addr ({os.path.getsize(output_path)} bytes)!")
                            return True

        log.error(f"❌ Não foi possível baixar o vídeo {video_url_or_id}")
        return False
    except Exception as e:
        log.error(f"❌ Erro ao baixar vídeo {video_url_or_id}: {e}")
        return False

def search_douyin(keyword: str, count: int = 30, sort_type: int = 2) -> list[dict]:
    """
    Busca vídeos no Douyin via Evil0ctal Douyin_TikTok_Download_API.

    Args:
        keyword: Termo de busca em chinês
        count: Quantidade máxima de resultados

    Returns:
        Lista de vídeos brutos (aweme_list)
    """
    try:
        log.info(f"🔍 Buscando '{keyword}' (count={count})...")
        resp = httpx.post(
            f"{DOUYIN_API_BASE}/api/douyin/web/search",
            json={
                "keyword": keyword,
                "count": count,
                "sort_type": sort_type,   # Usa o sort_type correto se passado
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("data", {}).get("aweme_list", [])
        log.info(f"  → {len(results)} resultados brutos")
        return results

    except httpx.TimeoutException:
        log.error("⏱ Timeout ao buscar no Douyin (30s)")
        return []
    except httpx.HTTPStatusError as e:
        log.error(f"🚫 HTTP {e.response.status_code} do Douyin API")
        return []
    except Exception as e:
        log.error(f"❌ Erro ao buscar no Douyin: {e}")
        return []


def parse_video(raw: dict, search_term: str = "") -> dict:
    """
    Normaliza o resultado bruto da API para o formato interno.

    Args:
        raw: Vídeo bruto retornado pela API
        search_term: Termo de busca usado (para rastreamento)

    Returns:
        Dicionário normalizado com campos padronizados
    """
    aweme_id = raw.get("aweme_id", "")
    desc = raw.get("desc", "")
    duration = raw.get("video", {}).get("duration", 0) // 1000  # ms → s
    author = raw.get("author", {})
    stats = raw.get("statistics", {})

    # Data de publicação
    create_time = raw.get("create_time", 0)
    published_at = ""
    if create_time:
        published_at = datetime.fromtimestamp(
            create_time, tz=timezone.utc
        ).isoformat()

    return {
        "video_id": aweme_id,
        "title": desc,
        "creator": author.get("unique_id") or author.get("nickname", "?"),
        "duration_s": duration,
        "likes": stats.get("digg_count", 0),
        "url": f"https://www.douyin.com/video/{aweme_id}",
        "published_at": published_at,
        "episode": extract_episode(desc),
        "search_term": search_term,
    }


# ─── Lógica principal de scraping ────────────────────────────────────────────

def run_scrape(db_path: str) -> ScrapeResult:
    """
    Executa o ciclo completo de scraping:
    1. Busca vídeos por SEARCH_TERM
    2. Filtra já vistos, likes baixos
    3. Classifica por duração (LONGO vs SHORT)
    4. Detecta continuação de episódio
    5. Ordena por likes desc

    Args:
        db_path: Caminho do banco SQLite

    Returns:
        ScrapeResult com candidatos categorizados
    """
    conn = init_db(db_path)
    result = ScrapeResult()

    log.info(f"🎌 Iniciando scraping: '{SEARCH_TERM}'")
    log.info(f"   Filtros: likes ≥ {MIN_LIKES} | short < {SHORT_MAX//60}min | "
             f"longo {LONG_MIN//60}-{LONG_MAX//60}min")

    # Busca
    raw_videos = search_douyin(SEARCH_TERM, MAX_RESULTS)
    result.total_raw = len(raw_videos)

    if not raw_videos:
        log.warning("⚠️ Nenhum resultado retornado. Verifique o cookie do Douyin.")
        conn.close()
        return result

    # Último episódio postado
    last_ep = get_last_posted_episode(conn)
    if last_ep:
        log.info(f"📺 Último episódio postado: EP {last_ep}")
    else:
        log.info("📺 Nenhum episódio postado anteriormente")

    # Processa cada vídeo
    for raw in raw_videos:
        time.sleep(0.5)  # Rate limit gentil
        v = parse_video(raw, SEARCH_TERM)

        # Pula se já visto
        if already_seen(conn, v["video_id"]):
            result.skipped_seen += 1
            continue

        # Pula se likes insuficientes
        if v["likes"] < MIN_LIKES:
            result.skipped_likes += 1
            continue

        # Salva no histórico
        save_video(conn, v)

        dur = v["duration_s"]

        # Classifica por duração
        if LONG_MIN < dur <= LONG_MAX:
            v["type"] = "LONGO"
            result.long_videos.append(v)

            # Detecta continuação de episódio
            if is_continuation(v["episode"], last_ep):
                result.next_episode = v
                log.info(
                    f"  ✅ Continuação detectada: EP {v['episode']} "
                    f"— {v['title'][:50]}"
                )

        elif dur <= SHORT_MAX:
            v["type"] = "SHORT"
            result.short_videos.append(v)

    # Ordena por likes (melhores primeiro)
    result.long_videos.sort(key=lambda x: x["likes"], reverse=True)
    result.short_videos.sort(key=lambda x: x["likes"], reverse=True)

    log.info(
        f"✅ Scraping concluído: {len(result.long_videos)} longos, "
        f"{len(result.short_videos)} shorts "
        f"({result.skipped_seen} já vistos, {result.skipped_likes} likes baixos)"
    )

    conn.close()
    return result
