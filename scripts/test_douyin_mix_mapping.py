"""
Script de Teste de Mapeamento de Coleções (Mix / Playlists) do Douyin.

Uso:
  python scripts/test_douyin_mix_mapping.py [mix_id_ou_url]

Exemplos:
  python scripts/test_douyin_mix_mapping.py 7348687990509553679
  python scripts/test_douyin_mix_mapping.py https://www.douyin.com/collection/7348687990509553679
  python scripts/test_douyin_mix_mapping.py https://www.douyin.com/video/7348687990509553679
"""

import os
import sys
import re
import io
import httpx
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Configura encoding no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Tenta importar episode_detector local
try:
    from src.episode_detector import extract_episode
except ImportError:
    def extract_episode(title: str):
        match = re.search(r'(?:第|EP|Ep|ep)?\s*(\d{1,4})\s*(?:集|话|話|话)?', title)
        return int(match.group(1)) if match else None

DOUYIN_API_BASE = os.getenv("DOUYIN_API_BASE", "http://localhost:5555")

def extract_ids_from_input(user_input: str) -> tuple[str | None, str | None]:
    """
    Extrai (mix_id, aweme_id) a partir de uma URL ou ID numérico.
    """
    user_input = user_input.strip()
    
    # Se for apenas números
    if user_input.isdigit():
        return user_input, None

    # Tenta extrair mix_id de /collection/XXXXX
    mix_match = re.search(r'collection/(\d+)', user_input)
    if mix_match:
        return mix_match.group(1), None

    # Tenta extrair aweme_id de /video/XXXXX
    video_match = re.search(r'video/(\d+)', user_input)
    if video_match:
        return None, video_match.group(1)

    # Regex genérico de números
    numbers = re.findall(r'\d{15,22}', user_input)
    if numbers:
        return numbers[0], None

    return None, None

def get_mix_id_from_video(aweme_id: str) -> dict | None:
    """
    Consulta um vídeo para obter o mix_info (mix_id, mix_name, etc).
    """
    url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_one_video"
    try:
        print(f"🔍 Consultando detalhes do vídeo AWEME_ID: {aweme_id}...")
        resp = httpx.get(url, params={"aweme_id": aweme_id}, timeout=20.0)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        aweme_detail = data.get("aweme_detail", {})
        mix_info = aweme_detail.get("mix_info", {})
        if mix_info:
            return {
                "mix_id": mix_info.get("mix_id"),
                "mix_name": mix_info.get("mix_name"),
                "st_at": mix_info.get("st_at"), # total de episódios
                "author": aweme_detail.get("author", {}).get("nickname", "Desconhecido")
            }
        print("⚠️ Este vídeo não parece pertencer a uma coleção (mix_info não encontrado).")
        return None
    except Exception as e:
        print(f"❌ Erro ao consultar vídeo: {e}")
        return None

def fetch_mix_episodes(mix_id: str, max_count: int = 50) -> dict:
    """
    Busca todos os episódios de uma coleção (mix) com paginação por cursor.
    """
    url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_user_mix_videos"
    cursor = 0
    all_episodes = []
    mix_name = ""
    author_name = ""
    has_more = True

    print(f"\n📡 Mapeando coleção MIX_ID: {mix_id}...")
    
    with httpx.Client(timeout=30.0) as client:
        while has_more and len(all_episodes) < max_count:
            params = {
                "mix_id": mix_id,
                "max_cursor": cursor,
                "counts": 20
            }
            try:
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    print(f"❌ Erro HTTP {resp.status_code} na API local")
                    break

                res_json = resp.json()
                data = res_json.get("data", {})
                
                aweme_list = data.get("aweme_list", [])
                has_more = bool(data.get("has_more", 0))
                cursor = data.get("cursor", 0)

                if not aweme_list:
                    print("⚠️ Nenhum vídeo retornado nesta página.")
                    break

                for item in aweme_list:
                    aweme_id = item.get("aweme_id")
                    desc = item.get("desc", "")
                    mix_info = item.get("mix_info", {})
                    
                    if not mix_name and mix_info:
                        mix_name = mix_info.get("mix_name", "")

                    author = item.get("author", {})
                    if not author_name and author:
                        author_name = author.get("nickname", "")

                    duration = item.get("video", {}).get("duration", 0) // 1000 # ms -> s
                    stats = item.get("statistics", {})
                    
                    # Número do episódio (da API ou detectado do título)
                    ep_num = mix_info.get("st_at") or extract_episode(desc)

                    all_episodes.append({
                        "aweme_id": aweme_id,
                        "title": desc,
                        "episode": ep_num,
                        "duration_s": duration,
                        "likes": stats.get("digg_count", 0),
                        "comments": stats.get("comment_count", 0),
                        "url": f"https://www.douyin.com/video/{aweme_id}",
                        "create_time": item.get("create_time", 0)
                    })

                print(f"  → Coletados {len(all_episodes)} episódios até o momento (has_more={has_more})...")

            except Exception as e:
                print(f"❌ Erro ao buscar página do mix (cursor={cursor}): {e}")
                break

    return {
        "mix_id": mix_id,
        "mix_name": mix_name or f"Coleção #{mix_id}",
        "author": author_name or "Autor Desconhecido",
        "total_mapped": len(all_episodes),
        "episodes": all_episodes
    }

def main():
    print("=" * 65)
    print("  🧪 Teste de Mapeamento de Coleções (Mix) do Douyin")
    print("=" * 65)

    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = input("\n📌 Cole o Link da Coleção, Link do Vídeo ou Mix ID: ").strip()

    if not target:
        # Mix de teste fallback se o usuário apertar Enter
        target = "7348687990509553679"
        print(f"ℹ️ Nenhum alvo fornecido. Usando ID de teste padrão: {target}")

    mix_id, aweme_id = extract_ids_from_input(target)

    if aweme_id and not mix_id:
        info = get_mix_id_from_video(aweme_id)
        if info:
            mix_id = info["mix_id"]
            print(f"✅ Coleção encontrada a partir do vídeo! Mix ID: {mix_id} ({info['mix_name']})")
        else:
            print("❌ Não foi possível obter o Mix ID a partir do vídeo informado.")
            sys.exit(1)

    if not mix_id:
        print("❌ ID de coleção (mix_id) inválido ou não encontrado.")
        sys.exit(1)

    result = fetch_mix_episodes(mix_id)

    print("\n" + "=" * 65)
    print(f"📚 NOME DA COLEÇÃO: {result['mix_name']}")
    print(f"👤 AUTOR:          {result['author']}")
    print(f"📊 TOTAL MAPEADO:   {result['total_mapped']} episódios")
    print("=" * 65)

    if result["episodes"]:
        print("\n📋 LISTA DE EPISÓDIOS MAPEADOS:")
        print("-" * 65)
        for idx, ep in enumerate(result["episodes"], 1):
            dur_m = ep['duration_s'] // 60
            dur_s = ep['duration_s'] % 60
            ep_str = f"EP {ep['episode']}" if ep['episode'] is not None else f"#{idx}"
            print(f"[{ep_str:^6}] {ep['title'][:45]:<45} │ {dur_m:02d}:{dur_s:02d} │ ❤️ {ep['likes']:,}")
            print(f"         🔗 {ep['url']}")
            print("-" * 65)

        print(f"\n✅ Mapeamento concluído com SUCESSO! {len(result['episodes'])} episódios extraídos.")
    else:
        print("\n⚠️ Nenhum episódio foi encontrado nesta coleção. Verifique se a API local está rodando ou se o cookie é válido.")

if __name__ == "__main__":
    main()
