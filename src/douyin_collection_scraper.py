"""
Mapeador de Coleções e Séries Virtuais do Douyin.
Consome a API local do Evil0ctal e armazena coleções e episódios no banco SQLite.
"""

import os
import re
import sys
import io
import httpx
import logging
from datetime import datetime
from src import database
from src.config import DOUYIN_API_BASE
from src.episode_detector import extract_episode
from src.translator import translate_zh_to_pt

logger = logging.getLogger(__name__)

def extract_ids(user_input: str) -> tuple[str | None, str | None]:
    """Extrai (mix_id, aweme_id) de URLs ou IDs numéricos."""
    user_input = user_input.strip()
    if user_input.isdigit():
        return user_input, None

    mix_match = re.search(r'collection/(\d+)', user_input)
    if mix_match:
        return mix_match.group(1), None

    video_match = re.search(r'video/(\d+)', user_input)
    if video_match:
        return None, video_match.group(1)

    numbers = re.findall(r'\d{15,22}', user_input)
    if numbers:
        return numbers[0], None

    return None, None

def get_mix_info_from_video(aweme_id: str) -> dict | None:
    """Obtém mix_info a partir de um vídeo avulso."""
    url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_one_video"
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, params={"aweme_id": aweme_id})
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                aweme_detail = data.get("aweme_detail", {})
                mix_info = aweme_detail.get("mix_info", {})
                if mix_info:
                    return {
                        "mix_id": str(mix_info.get("mix_id")),
                        "mix_name": mix_info.get("mix_name", ""),
                        "st_at": mix_info.get("st_at"),
                        "author": aweme_detail.get("author", {}).get("nickname", "Desconhecido")
                    }
    except Exception as e:
        logger.error(f"Erro ao obter mix_info do vídeo {aweme_id}: {e}")
    return None

def fetch_and_store_collection(user_input: str, title_pt: str = None, autoposting: bool = True) -> dict:
    """
    Mapeia uma coleção completa do Douyin e salva no banco de dados SQLite.
    
    Args:
        user_input: URL da coleção, URL de um vídeo ou mix_id numérico.
        title_pt: Título traduzido/personalizado em português.
        autoposting: Define se o autoposting estará ON ou OFF.
        
    Returns:
        Dicionário com resumo da coleção e episódios salvos.
    """
    mix_id, aweme_id = extract_ids(user_input)

    if aweme_id and not mix_id:
        info = get_mix_info_from_video(aweme_id)
        if info:
            mix_id = info["mix_id"]
        else:
            return {"ok": False, "message": "O vídeo informado não pertence a nenhuma coleção do Douyin."}

    if not mix_id:
        return {"ok": False, "message": "Link ou ID de coleção inválido."}

    logger.info(f"📡 Mapeando coleção Douyin MIX_ID: {mix_id}...")

    url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_user_mix_videos"
    cursor = 0
    all_episodes = []
    mix_name = ""
    author_name = ""
    cover_url = ""
    has_more = True

    cookie_val = database.get_user_setting("DOUYIN_COOKIE") or os.getenv("DOUYIN_COOKIE", "")
    headers = {"cookie": cookie_val} if cookie_val else {}

    with httpx.Client(timeout=30.0) as client:
        while has_more and len(all_episodes) < 200:
            params = {"mix_id": mix_id, "max_cursor": cursor, "counts": 20}
            try:
                resp = client.get(url, params=params, headers=headers)
                if resp.status_code != 200:
                    logger.error(f"Erro HTTP {resp.status_code} na API local para mix {mix_id}")
                    break

                res_json = resp.json()
                data = res_json.get("data", {})

                if data and data.get("status_code") == 5:
                    logger.warning("⚠️ Douyin retornou status_code 5 (Cookie expirado ou ausente).")
                    return {
                        "ok": False,
                        "message": "⚠️ O Douyin bloqueou a requisição (Cookie expirado ou ausente). Por favor, atualize o Cookie do Douyin na aba ⚙️ Configurações."
                    }

                aweme_list = data.get("aweme_list", []) if data else []
                has_more = bool(data.get("has_more", 0)) if data else False
                cursor = data.get("cursor", 0) if data else 0

                if not aweme_list:
                    break

                for item in aweme_list:
                    aid = str(item.get("aweme_id"))
                    desc = item.get("desc", "")
                    mix_info = item.get("mix_info", {})
                    author = item.get("author", {})
                    video = item.get("video", {})
                    stats = item.get("statistics", {})

                    if not mix_name and mix_info:
                        mix_name = mix_info.get("mix_name", "")
                    if not author_name and author:
                        author_name = author.get("nickname", "")

                    # Tenta obter a melhor imagem de capa
                    cover = ""
                    cover_list = video.get("origin_cover", {}).get("url_list", []) or video.get("cover", {}).get("url_list", [])
                    if cover_list:
                        cover = cover_list[0]
                    if not cover_url and cover:
                        cover_url = cover

                    duration_s = video.get("duration", 0) // 1000  # ms -> s
                    ep_num = mix_info.get("st_at") or extract_episode(desc)
                    title_translated = translate_zh_to_pt(desc)

                    all_episodes.append({
                        "mix_id": mix_id,
                        "episode_num": ep_num,
                        "aweme_id": aid,
                        "title": title_translated if title_translated else desc,
                        "duration_seconds": duration_s,
                        "likes": stats.get("digg_count", 0),
                        "comments": stats.get("comment_count", 0),
                        "cover_url": cover,
                        "video_url": f"https://www.douyin.com/video/{aid}",
                    })

            except Exception as e:
                logger.error(f"Erro ao buscar página do mix {mix_id} (cursor={cursor}): {e}")
                break

    if not all_episodes:
        return {"ok": False, "message": "Nenhum episódio retornado pela API. Verifique a validade do cookie."}

    # Ordena episódios sequencialmente (EP 1 primeiro)
    all_episodes.sort(key=lambda x: x["episode_num"] if x["episode_num"] is not None else 999999)

    # Identifica se já existem episódios curtos para filtrar resumos de 50 min
    has_short_eps = any(ep["duration_seconds"] <= 300 for ep in all_episodes)

    # Salva no banco de dados
    col_data = {
        "mix_id": mix_id,
        "title_pt": title_pt or mix_name or f"Série #{mix_id}",
        "title_zh": mix_name,
        "author": author_name,
        "cover_url": cover_url or (all_episodes[0]["cover_url"] if all_episodes else ""),
        "total_episodes": len(all_episodes),
        "autoposting": autoposting,
        "is_virtual": False,
        "status": "active"
    }
    database.upsert_douyin_collection(col_data)

    opaque_count = 0
    saved_count = 0

    for ep in all_episodes:
        dur = ep["duration_seconds"]
        is_compilation = False

        # Política de Duração > 5 min (300s)
        if dur > 300:
            # Se for > 10 min (600s) e já temos os episódios curtos de 3 min, ignora como resumo
            if dur > 600 and has_short_eps:
                status = "ignored"
                is_compilation = True
            else:
                status = "opaque_over_5min"
                opaque_count += 1
        else:
            status = "pending"

        ep["status"] = status
        ep["is_compilation"] = is_compilation

        if database.upsert_collection_episode(ep):
            saved_count += 1

    return {
        "ok": True,
        "mix_id": mix_id,
        "title_pt": col_data["title_pt"],
        "title_zh": mix_name,
        "author": author_name,
        "total_mapped": len(all_episodes),
        "saved_count": saved_count,
        "opaque_count": opaque_count,
        "message": f"Coleção '{col_data['title_pt']}' mapeada com sucesso! {len(all_episodes)} episódios ({opaque_count} requerem ação por >5min)."
    }
