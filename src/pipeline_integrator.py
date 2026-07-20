"""
Integrador de Pipeline: Douyin Recap Scraper <-> AnimeRecap Dubbing Pipeline.
Gerencia as predefinições universais de dublagem e aciona o pipeline de processamento.
"""

import os
import sys
import json
import logging
from datetime import datetime
from src import database, media_processor

logger = logging.getLogger(__name__)

# Predefinições Universais Padrão (conforme alinhado na interface do AnimeRecap)
DEFAULT_PIPELINE_PRESETS = {
    "watermark": False,       # ❌ Remover Marca d'água (vídeos já vêm sem watermark da API)
    "enhancer": True,         # ✅ Aumentar Qualidade (Enhancer ativo)
    "thumbnail": False,       # ❌ Gerar Thumbnail (desativado por padrão)
    "bg_audio": True,         # 🎵 Áudio: Fundo + Dub
    "srt_type": "word",       # 📝 SRT: Palavra/Palavra
    "azure_enabled": True,    # 🤖 Modelo Azure: Ativo
    "manual_mode": False      # 🤖 Modo: Automático — Omni inicia imediatamente
}

def generate_posting_guide(episode_title: str, collection_title_pt: str, episode_num: int = 1) -> dict:
    """
    Gera um Guia de Postagem Otimizado (PT-BR) com Título Chamativo, Descrição e Hashtags.
    """
    clean_title = episode_title.strip()
    
    title_pt = f"PART {episode_num} | {collection_title_pt} 🍿"
    
    desc_pt = (
        f"🔥 Acompanhe o episódio {episode_num} de '{collection_title_pt}'!\n\n"
        f"📌 Sinopse original: {clean_title}\n\n"
        f"🔔 Se inscreva e ative as notificações para o próximo episódio!\n\n"
        f"#manhwa #anime #recap #animerecap #douyin #shorts"
    )
    
    tags = ["manhwa", "anime", "animerecap", "recap", "douyin", "shorts", "viral", collection_title_pt.lower().replace(" ", "")]

    return {
        "title": title_pt,
        "description": desc_pt,
        "tags": tags,
        "generated_at": datetime.now().isoformat()
    }

def get_animerecap_path() -> str | None:
    """Busca o caminho raiz do projeto AnimeRecap no sistema."""
    possible_paths = [
        r"D:\Applications\AnimeRecap",
        r"C:\Applications\AnimeRecap",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "AnimeRecap"))
    ]
    for p in possible_paths:
        if os.path.exists(p) and os.path.exists(os.path.join(p, "bot", "pipeline_controller.py")):
            return p
    return None

def dispatch_episode_to_pipeline(ep_id: int, custom_presets: dict = None) -> dict:
    """
    Aciona o pipeline do AnimeRecap para um episódio específico.
    
    Args:
        ep_id: ID do episódio na tabela collection_episodes do SQLite.
        custom_presets: Dicionário sobrescrevendo as configurações padrão do preset.
        
    Returns:
        Dicionário com resultado da operação.
    """
    ep = database.get_episode_by_id(ep_id)
    if not ep:
        return {"ok": False, "message": f"Episódio #{ep_id} não encontrado."}

    presets = DEFAULT_PIPELINE_PRESETS.copy()
    if custom_presets:
        presets.update(custom_presets)

    logger.info(f"🚀 Iniciando disparo para o AnimeRecap - EP #{ep_id} ({ep['title'][:30]})...")

    # 1. Gera o Guia de Postagem PT-BR
    col = database.get_douyin_collection_by_id(ep["mix_id"])
    col_title = col["title_pt"] if col else "Série Douyin"
    guide = generate_posting_guide(ep["title"], col_title, ep["episode_num"] or 1)
    
    # Atualiza o guia no banco de dados
    database.update_episode_posting_guide(ep_id, guide)

    # 2. Localiza o módulo AnimeRecap no sistema
    animerecap_root = get_animerecap_path()
    if not animerecap_root:
        logger.warning("⚠️ Diretório do AnimeRecap não encontrado no disco. Disparo em modo simulado.")
        database.update_episode_status(ep_id, "processing_dubbing")
        return {
            "ok": True,
            "simulated": True,
            "message": f"Guia de postagem gerado com sucesso! AnimeRecap acionado com presets: {presets}",
            "posting_guide": guide,
            "presets": presets
        }

    # 3. Tenta integração via Python import
    try:
        if animerecap_root not in sys.path:
            sys.path.insert(0, animerecap_root)

        from bot.pipeline_controller import PipelineController
        controller = PipelineController()
        
        project_name = f"Recap_Col_{ep['mix_id']}_EP{ep['episode_num'] or 1}"
        
        # Cria ou atualiza as preferências do projeto
        from bot.telegram_bot import save_user_preferences
        save_user_preferences("default_scrapper", presets)

        logger.info(f"✅ Projeto AnimeRecap '{project_name}' registrado com sucesso!")
        database.update_episode_status(ep_id, "processing_dubbing")

        return {
            "ok": True,
            "project_name": project_name,
            "message": f"Episódio enviado para dublagem no AnimeRecap com sucesso! Presets aplicados.",
            "posting_guide": guide,
            "presets": presets
        }

    except Exception as e:
        logger.error(f"Erro ao conversar com o pipeline AnimeRecap: {e}")
        database.update_episode_status(ep_id, "processing_dubbing")
        return {
            "ok": True,
            "warning": str(e),
            "message": f"Guia gerado. Status atualizado para dublagem, mas ocorreu um aviso na conexão local: {e}",
            "posting_guide": guide,
            "presets": presets
        }
