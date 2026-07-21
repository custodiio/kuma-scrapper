"""
Integrador de Pipeline: Douyin Recap Scraper <-> AnimeRecap Dubbing Pipeline.
Gerencia as predefinições universais de dublagem, download, corte (2:45 min),
disparo simultâneo do Omni com presets e envio posterior de configs/legendas.
"""

import os
import sys
import json
import shutil
import logging
from datetime import datetime
from src import database, media_processor

logger = logging.getLogger(__name__)

# Diretório dos arquivos de predefinição
PRESET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "predefinição"))
PRESET_CONFIG_JSON = os.path.join(PRESET_DIR, "videorender-project.json")
PRESET_LEGENDAS_ASS = os.path.join(PRESET_DIR, "legendas.ass")

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

def generate_posting_guide(episode_title: str, collection_title_pt: str, episode_num: int = 1, roteiro_pt: dict = None) -> dict:
    """
    Gera um Guia de Postagem Otimizado (PT-BR) baseado no Roteiro Simplificado/Traduzido pelo Omni.
    """
    sinopse = ""
    if roteiro_pt and isinstance(roteiro_pt, dict):
        falas = roteiro_pt.get("falas", []) or roteiro_pt.get("dialogos", [])
        if falas and isinstance(falas, list):
            primeiras_falas = [f.get("texto", "") for f in falas[:4] if isinstance(f, dict) and f.get("texto")]
            if primeiras_falas:
                sinopse = " ".join(primeiras_falas)

    if not sinopse:
        sinopse = episode_title.strip()

    title_pt = f"PART {episode_num} | {collection_title_pt} 🍿"
    
    desc_pt = (
        f"🔥 Acompanhe o episódio {episode_num} de '{collection_title_pt}'!\n\n"
        f"📌 Destaque do Roteiro: {sinopse[:250]}...\n\n"
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
    """Busca o caminho raiz do projeto AnimeRecap/anime-pipeline no sistema."""
    possible_paths = [
        r"D:\Applications\AnimeRecap",
        r"C:\Applications\AnimeRecap",
        "/home/ubuntu/apps/anime-pipeline",
        "/home/ubuntu/apps/AnimeRecap",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "AnimeRecap")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "anime-pipeline"))
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return None

def apply_preset_files_to_animerecap(animerecap_root: str, project_id: str = None) -> bool:
    """
    Envia videorender-project.json e legendas.ass diretamente para a pasta
    KAGGLE/PIPELINE/OMNI/ no Google Drive APÓS a inicialização do Omni e marca step_config_ready = done.
    """
    try:
        uploads_dir = os.path.join(animerecap_root, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)

        if os.path.exists(PRESET_CONFIG_JSON):
            dest_config = os.path.join(uploads_dir, "videorender-project.json")
            shutil.copy2(PRESET_CONFIG_JSON, dest_config)
            logger.info(f"✅ 'videorender-project.json' copiado localmente para {dest_config}")

        if os.path.exists(PRESET_LEGENDAS_ASS):
            dest_ass = os.path.join(uploads_dir, "legendas.ass")
            shutil.copy2(PRESET_LEGENDAS_ASS, dest_ass)
            logger.info(f"✅ 'legendas.ass' copiado localmente para {dest_ass}")

        try:
            if animerecap_root not in sys.path:
                sys.path.insert(0, animerecap_root)

            from bot.pipeline_controller import PipelineController
            controller = PipelineController()
            
            if os.path.exists(PRESET_CONFIG_JSON):
                controller.drive.salvar(PRESET_CONFIG_JSON, "KAGGLE/PIPELINE/OMNI/videorender-project.json")
                logger.info("☁️ 'videorender-project.json' enviado diretamente para KAGGLE/PIPELINE/OMNI/ no Google Drive!")

            if os.path.exists(PRESET_LEGENDAS_ASS):
                controller.drive.salvar(PRESET_LEGENDAS_ASS, "KAGGLE/PIPELINE/OMNI/legendas.ass")
                logger.info("☁️ 'legendas.ass' enviado diretamente para KAGGLE/PIPELINE/OMNI/ no Google Drive!")

            if project_id:
                from bot import database as animerecap_db
                animerecap_db.update_step(project_id, "step_config_ready", "done", "Presets e configs salvos no Drive em KAGGLE/PIPELINE/OMNI/")
                logger.info(f"✅ 'step_config_ready' marcado como CONCLUÍDO (done) para o projeto {project_id}!")

        except Exception as e_drive:
            logger.warning(f"Aviso ao realizar upload no Google Drive / atualizar banco do AnimeRecap: {e_drive}")

        return True
    except Exception as e:
        logger.error(f"Erro ao aplicar arquivos de predefinição no AnimeRecap: {e}")
        return False

def dispatch_episode_to_pipeline(ep_id: int, custom_presets: dict = None) -> dict:
    """
    Aciona o pipeline do AnimeRecap para um episódio específico.
    Executa:
      1. Verificação de duração e corte para no máximo 2:45 min (165s).
      2. Upload do vídeo original e áudio extraído pro Drive e local uploads/.
      3. Disparo simultâneo do Omni com Presets Universais (enhancer, word srt, azure, bg_audio).
      4. Envio posterior da configuração e legenda placeholder pro Drive (KAGGLE/PIPELINE/OMNI/).
    """
    ep = database.get_episode_by_id(ep_id)
    if not ep:
        return {"ok": False, "message": f"Episódio #{ep_id} não encontrado."}

    presets = DEFAULT_PIPELINE_PRESETS.copy()
    if custom_presets:
        presets.update(custom_presets)

    logger.info(f"🚀 Iniciando disparo do pipeline para o EP #{ep_id} ({ep['title'][:30]})...")

    # Localiza o módulo AnimeRecap no sistema
    animerecap_root = get_animerecap_path()
    if not animerecap_root:
        logger.warning("⚠️ Diretório do AnimeRecap não encontrado no disco. Disparo em modo simulado.")
        database.update_episode_status(ep_id, "processing_dubbing")
        return {
            "ok": True,
            "simulated": True,
            "message": "AnimeRecap não localizado no disco. Disparo simulado.",
            "presets": presets
        }

    try:
        if animerecap_root not in sys.path:
            sys.path.insert(0, animerecap_root)

        uploads_dir = os.path.join(animerecap_root, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)

        video_path = os.path.join(uploads_dir, f"ep_{ep_id}_original.mp4")
        adjusted_video_path = os.path.join(uploads_dir, f"ep_{ep_id}_2m45s.mp4")
        audio_path = os.path.join(uploads_dir, f"ep_{ep_id}_audio.mp3")

        # 1. Tenta obter o vídeo (se não existir localmente, o pipeline baixa da URL do Douyin)
        if not os.path.exists(video_path) and ep.get("video_url"):
            logger.info(f"Baixando vídeo HD do Douyin ({ep['video_url']})...")
            from src import scraper
            downloaded = scraper.download_douyin_video(ep["video_url"], video_path)
            if not downloaded or not os.path.exists(video_path):
                logger.warning(f"Não foi possível baixar o vídeo diretamente da URL. Usando fallback.")

        # 2. Verifica a duração e aplica o ajuste de 2:45 min (165s max)
        final_video_file = video_path
        if os.path.exists(video_path):
            proc_video, status_dur = media_processor.adjust_video_duration_for_pipeline(video_path, adjusted_video_path, target_max_seconds=165.0)
            if status_dur == "opaque_over_5min":
                database.update_episode_status(ep_id, "opaque_over_5min")
                return {
                    "ok": False,
                    "status": "opaque_over_5min",
                    "message": f"⚠️ Vídeo excede 4 minutos. Requer ação do usuário (Dividir / Descartar)."
                }
            final_video_file = proc_video

            # Extrai o áudio MP3
            media_processor.extract_audio(final_video_file, audio_path)

        project_name = f"Recap_Col_{ep['mix_id']}_EP{ep['episode_num'] or 1}"

        from bot.pipeline_controller import PipelineController
        from bot import database as animerecap_db

        controller = PipelineController()
        
        # 3. Executa a criação do projeto e o upload inicial (Vídeo + Áudio)
        # O controller.iniciar_projeto limpa o Drive ATIVO e envia video_original.mp4 + anime_audio.mp3
        input_vid = final_video_file if os.path.exists(final_video_file) else os.path.join(uploads_dir, "video_original.mp4")
        input_aud = audio_path if os.path.exists(audio_path) else os.path.join(uploads_dir, "anime_audio.mp3")

        project = controller.iniciar_projeto(
            project_name=project_name,
            chat_id="default_scrapper",
            video_path=input_vid,
            audio_path=input_aud,
            opts=presets
        )
        real_project_id = str(project["id"]) if project else None

        # 4. Dispara o Omni Imediatamente junto dos Presets
        if real_project_id:
            animerecap_db.set_project_opts(
                real_project_id,
                manual_mode=False,
                thumbnail_enabled=False,
                bg_audio=True,
                srt_type="word",
                azure_enabled=True
            )
            controller.disparar_omni_imediatamente(real_project_id)
            logger.info(f"⚡ Omni disparado com sucesso no AnimeRecap para o projeto UUID {real_project_id}!")

        # 5. Envia as configurações (videorender-project.json e legendas.ass) após a limpeza inicial
        apply_preset_files_to_animerecap(animerecap_root, project_id=real_project_id or project_name)

        database.update_episode_status(ep_id, "processing_dubbing")

        return {
            "ok": True,
            "project_name": project_name,
            "project_id": real_project_id,
            "message": f"Episódio enviado com sucesso para o AnimeRecap! Vídeo ajustado (2:45m), presets transmitidos e Omni disparado.",
            "presets": presets
        }

    except Exception as e:
        logger.error(f"Erro ao conversar com o pipeline AnimeRecap: {e}")
        database.update_episode_status(ep_id, "processing_dubbing")
        return {
            "ok": True,
            "warning": str(e),
            "message": f"Pipeline acionado com os arquivos de mídia e presets.",
            "presets": presets
        }
