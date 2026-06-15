import os
import re
import time
import httpx
import logging
import asyncio
from fastapi import FastAPI, BackgroundTasks, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from src import database, search_scrapper, media_processor, drive_uploader
from src.config import DOUYIN_API_BASE

logger = logging.getLogger(__name__)

ROOT_PATH = os.getenv("ROOT_PATH", "")
app = FastAPI(title="Kuma Scrapper - Painel de Triagem Web", root_path=ROOT_PATH)


# Diretório temporário para downloads locais
TEMP_DIR = os.path.join("data", "temp_media")

# Helper para apagar cache físico local após upload
def clean_local_mids_and_api_cache(temp_video_path, final_video_path, final_audio_path, bvid_or_videoid=None):
    """Limpa fisicamente a pasta temporária do bot e a pasta de downloads da API do Evil0ctal."""
    logger.info("Iniciando limpeza física de arquivos temporários e cache da API...")
    
    # 1. Limpa arquivos locais temporários do Bot
    for p in [temp_video_path, final_video_path, final_audio_path]:
        if p and os.path.exists(p):
            try:
                os.remove(p)
                logger.info(f"Removido temporário local: {p}")
            except Exception as e:
                logger.warning(f"Erro ao remover temporário local {p}: {e}")
                
    # 2. Limpa cache de download da API local do Evil0ctal (conforme bvid/video_id informado)
    if bvid_or_videoid:
        api_download_dir_bili = os.path.join("douyin_api", "download", "bilibili_video")
        api_download_dir_douyin = os.path.join("douyin_api", "download", "douyin_video")
        
        # Remove do Bilibili se houver
        if os.path.exists(api_download_dir_bili):
            for f in os.listdir(api_download_dir_bili):
                if bvid_or_videoid in f:
                    try:
                        os.remove(os.path.join(api_download_dir_bili, f))
                        logger.info(f"Removido cache Bilibili da API: {f}")
                    except Exception as e: logger.warning(f"Erro ao remover cache Bilibili: {e}")
                    
        # Remove do Douyin se houver
        if os.path.exists(api_download_dir_douyin):
            for f in os.listdir(api_download_dir_douyin):
                if bvid_or_videoid in f:
                    try:
                        os.remove(os.path.join(api_download_dir_douyin, f))
                        logger.info(f"Removido cache Douyin da API: {f}")
                    except Exception as e: logger.warning(f"Erro ao remover cache Douyin: {e}")

def send_telegram_status(text: str, message_id: int = None) -> int:
    """Envia ou edita uma mensagem de status no Telegram de forma síncrona usando a API HTTP do Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return None
        
    try:
        if message_id:
            url = f"https://api.telegram.org/bot{token}/editMessageText"
            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
        else:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url, json=payload)
            if r.status_code == 200:
                res_data = r.json()
                if message_id:
                    return message_id
                else:
                    return res_data.get("result", {}).get("message_id")
    except Exception as e:
        logger.error(f"Erro ao enviar status do Telegram: {e}")
    return message_id

# Lógica de processamento de download em Background
def perform_background_download(bvid: str, url: str, is_douyin: bool, category: str, content_type: str):
    """Executa o download de forma assíncrona/background e notifica o Telegram com progresso em tempo real."""
    logger.info(f"Iniciando download em background para bvid={bvid}, is_douyin={is_douyin}, cat={category}")
    
    cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
    type_title = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
    origin_label = "Douyin" if is_douyin else "Bilibili"
    
    # 1. Envia mensagem inicial ao Telegram
    tg_text = (
        f"📥 **Triagem Web: Download Iniciado!**\n"
        f"📋 **Contexto:** {cat_title} - {type_title}\n"
        f"🔗 **BVID/URL:** `{bvid}`\n"
        f"⏳ Baixando vídeo do {origin_label} pela API local..."
    )
    tg_msg_id = send_telegram_status(tg_text)
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    temp_video_path = os.path.join(TEMP_DIR, f"{bvid}_raw.mp4")
    
    # Exclui temporários se existirem
    if os.path.exists(temp_video_path):
        try: os.remove(temp_video_path)
        except: pass
        
    api_url = f"{DOUYIN_API_BASE}/api/download"
    download_success = False
    
    # 1. Faz o download do stream de vídeo
    try:
        with httpx.Client(timeout=180.0) as client:
            with client.stream("GET", api_url, params={"url": url, "with_watermark": "false"}) as r:
                content_type = r.headers.get("Content-Type", "")
                if r.status_code == 200 and "application/json" not in content_type:
                    total_size = int(r.headers.get("Content-Length", 0))
                    downloaded = 0
                    last_update = 0.0
                    last_percent = 0
                    
                    with open(temp_video_path, "wb") as f:
                        for chunk in r.iter_bytes():
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = int((downloaded / total_size) * 100)
                                now = time.time()
                                # Atualiza o Telegram a cada 20% ou a cada 10 segundos
                                if (percent - last_percent >= 20) or (now - last_update >= 10.0) or (percent == 100):
                                    last_percent = percent
                                    last_update = now
                                    if tg_msg_id:
                                        tg_text = (
                                            f"📥 **Triagem Web: Baixando vídeo...**\n"
                                            f"📋 **Contexto:** {cat_title} - {type_title}\n"
                                            f"⏳ Progresso: **{percent}%** ({downloaded/(1024*1024):.1f}MB / {total_size/(1024*1024):.1f}MB)..."
                                        )
                                        send_telegram_status(tg_text, tg_msg_id)
                                        
                    download_success = os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) > 0
                else:
                    # Erro retornado pela API ou JSON com erro
                    r.read()
                    try:
                        err_data = r.json()
                        err_msg = err_data.get("message", "Erro interno da API local")
                    except Exception:
                        err_msg = f"HTTP {r.status_code}: {r.text[:200]}"
                    
                    logger.error(f"Erro no download pela API local para {bvid}: {err_msg}")
                    if tg_msg_id:
                        send_telegram_status(f"❌ **Falha ao realizar download** do vídeo para BVID `{bvid}` na API local:\n`{err_msg}`", tg_msg_id)
                    database.update_search_result_status(bvid, "pending")
                    return
    except Exception as e:
        logger.error(f"Erro ao baixar vídeo na API em background: {e}")
        if tg_msg_id:
            send_telegram_status(f"❌ **Falha na requisição** do download para BVID `{bvid}`:\n`{str(e)}`", tg_msg_id)
        database.update_search_result_status(bvid, "pending")
        return
        
    if not download_success:
        logger.error(f"Falha no download para bvid={bvid}")
        if tg_msg_id:
            send_telegram_status(f"❌ **Falha ao salvar o vídeo** do BVID `{bvid}` localmente.", tg_msg_id)
        database.update_search_result_status(bvid, "pending")
        return
        
    if tg_msg_id:
        send_telegram_status(f"✂️ **Vídeo baixado!** Executando processamento de mídia (FFmpeg duration/audio/cut)...", tg_msg_id)
        
    # 2. Processa com FFmpeg (corte e áudio)
    final_video_path, final_audio_path, proc_success = media_processor.process_media_for_pipeline(
        temp_video_path, TEMP_DIR, category
    )
    
    if not proc_success:
        logger.error(f"Falha no processamento do vídeo/áudio com FFmpeg para bvid={bvid}")
        if tg_msg_id:
            send_telegram_status(f"❌ **Falha no processamento** do vídeo/áudio usando FFmpeg para BVID `{bvid}`.", tg_msg_id)
        try: os.remove(temp_video_path)
        except: pass
        database.update_search_result_status(bvid, "pending")
        return
        
    if tg_msg_id:
        send_telegram_status(f"📤 **Mídia processada!** Iniciando upload para o Google Drive...", tg_msg_id)
        
    # 3. Faz o upload para o Google Drive com callback de progresso integrado no Telegram
    progress_state = {"last_update": 0.0, "last_percent": 0, "last_file_type": ""}
    
    def drive_progress(file_type, percent):
        now = time.time()
        if (percent - progress_state["last_percent"] >= 20) or \
           (now - progress_state["last_update"] >= 10.0) or \
           (percent == 100) or \
           (file_type != progress_state["last_file_type"]):
            
            progress_state["last_percent"] = percent
            progress_state["last_update"] = now
            progress_state["last_file_type"] = file_type
            
            if tg_msg_id:
                text = (
                    f"📤 **Triagem Web: Subindo para o Drive...**\n"
                    f"📋 **Contexto:** {cat_title} - {type_title}\n"
                    f"⏳ Subindo **{file_type}** para o Google Drive: **{percent}%**..."
                )
                send_telegram_status(text, tg_msg_id)
                
    drive_success = drive_uploader.upload_pipeline_media(final_video_path, final_audio_path, progress_callback=drive_progress)
    
    if drive_success:
        logger.info(f"Upload bem-sucedido para o Drive: bvid={bvid}!")
        # Atualiza o status do vídeo no SQLite
        database.update_search_result_status(bvid, "downloaded")
        
        # Procura o título correto do vídeo no SQLite
        original_title = f"Busca Geral: {bvid}"
        # Acha nos pendentes
        for item in database.get_search_results(status="pending", content_type=content_type) + database.get_search_results(status="downloaded", content_type=content_type):
            if item["bvid"] == bvid:
                original_title = item["title"]
                break
                
        database.register_video(
            bvid=bvid,
            title=original_title,
            source="search",
            category=category,
            content_type=content_type,
            status="downloaded"
        )
        
        if tg_msg_id:
            success_text = (
                f"✅ **Sucesso! Mídia de Triagem Web enviada ao Drive!**\n\n"
                f"📝 **Título:** {original_title}\n"
                f"📂 **Arquivos Enviados:**\n"
                f"├ 🎵 `KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3`\n"
                f"└ 🎥 `KAGGLE/PIPELINE/ATIVO/video_original.mp4`\n\n"
                f"O vídeo foi colocado na fila **Próximo a Postar**!"
            )
            send_telegram_status(success_text, tg_msg_id)
            
            # Se for Shorts e < 50MB, envia a prévia no Telegram
            if category.lower() == "shorts" and os.path.exists(final_video_path):
                file_size_mb = os.path.getsize(final_video_path) / (1024 * 1024)
                if file_size_mb < 49.0:
                    try:
                        url_send_video = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendVideo"
                        with open(final_video_path, "rb") as video_file:
                            files = {"video": video_file}
                            data = {
                                "chat_id": os.getenv("TELEGRAM_CHAT_ID"),
                                "caption": f"🎬 **Prévia do vídeo de Triagem enviado ao Drive** (Sem marca d'água)"
                            }
                            httpx.post(url_send_video, data=data, files=files, timeout=60.0)
                    except Exception as ev:
                        logger.warning(f"Erro ao enviar prévia do vídeo via HTTP: {ev}")
    else:
        logger.error(f"Falha no upload do Drive para bvid={bvid}")
        if tg_msg_id:
            send_telegram_status(f"❌ **Falha ao enviar os arquivos** para o Google Drive para BVID `{bvid}`.", tg_msg_id)
        database.update_search_result_status(bvid, "pending")
        
    # 4. Limpeza física estrita de mídias e cache do Evil0ctal
    video_id_filter = bvid
    if is_douyin:
        match_id = re.search(r"video/(\d+)", url)
        if match_id:
            video_id_filter = match_id.group(1)
            
    clean_local_mids_and_api_cache(temp_video_path, final_video_path, final_audio_path, video_id_filter)

# ----------------- ROTAS WEB DO FastAPI -----------------

@app.post("/api/sync")
async def sync_search():
    """Rota para acionamento manual da busca geral do Bilibili."""
    try:
        inserted = await search_scrapper.run_search_scraping()
        return JSONResponse(content={"ok": True, "message": f"Busca sincronizada! {inserted} novos vídeos inseridos para triagem."})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "message": str(e)})

@app.post("/api/ignore/{bvid}")
async def ignore_video(bvid: str):
    """Marca o vídeo como ignorado para ocultar da triagem."""
    success = database.update_search_result_status(bvid, "ignored")
    return {"ok": success}

@app.post("/api/download")
async def download_video(
    background_tasks: BackgroundTasks,
    bvid: str = Form(...),
    url: str = Form(...),
    is_douyin: int = Form(...), # 1 = Douyin, 0 = Bilibili
    category: str = Form(...),  # 'shorts' ou 'longos'
    content_type: str = Form(...) # 'anime' ou 'manhwa'
):
    """Agenda o download, corte e envio ao Drive em background."""
    is_douyin_bool = bool(is_douyin)
    
    # Registra estado provisório no banco para atualizar o status visual imediatamente
    database.update_search_result_status(bvid, "processing")
    
    # Agenda a tarefa de processamento em background
    background_tasks.add_task(
        perform_background_download,
        bvid=bvid,
        url=url,
        is_douyin=is_douyin_bool,
        category=category,
        content_type=content_type
    )
    return {"ok": True, "message": "Download e processamento iniciados em background!"}

@app.get("/api/status")
async def get_status(bvids: str):
    """Retorna o status de processamento dos BVIDs no SQLite."""
    bvid_list = [b.strip() for b in bvids.split(",") if b.strip()]
    if not bvid_list:
        return {}
        
    res = {}
    conn = database.get_connection()
    cursor = conn.cursor()
    try:
        # 1. Verifica processed_videos
        placeholders = ",".join("?" for _ in bvid_list)
        cursor.execute(f"SELECT bvid, status FROM processed_videos WHERE bvid IN ({placeholders})", bvid_list)
        for r in cursor.fetchall():
            res[r["bvid"]] = r["status"]
            
        # 2. Para os restantes, verifica search_results (triagem web)
        missing = [b for b in bvid_list if b not in res]
        if missing:
            placeholders_m = ",".join("?" for _ in missing)
            cursor.execute(f"SELECT bvid, status FROM search_results WHERE bvid IN ({placeholders_m})", missing)
            for r in cursor.fetchall():
                res[r["bvid"]] = r["status"]
    except Exception as e:
        logger.error(f"Erro ao buscar status na API status: {e}")
    finally:
        conn.close()
        
    # Default para pending se não encontrado em nenhum
    for b in bvid_list:
        if b not in res:
            res[b] = "pending"
            
    return res

@app.get("/", response_class=HTMLResponse)
async def index(type: str = "anime"):
    """Página HTML Premium do painel de triagem."""
    if type not in ["anime", "manhwa"]:
        type = "anime"
        
    results = database.get_search_results(status="pending", content_type=type)
    
    # Também busca os em processamento para manter o estado
    processing_results = database.get_search_results(status="processing", content_type=type)
    results = processing_results + results # coloca os em processamento no topo
    
    cards_html = ""
    for r in results:
        status_badge = ""
        action_buttons = ""
        
        # Formata a duração em minutos:segundos
        duration_min = r['duration_seconds'] // 60
        duration_sec = r['duration_seconds'] % 60
        duration_str = f"{duration_min}:{duration_sec:02d}"
        
        # Define categoria provável com base na duração (se < 4 min (240s) = shorts, senão = longos)
        default_category = "shorts" if r['duration_seconds'] < 240 else "longos"
        
        if r['status'] == "processing":
            status_badge = '<span class="badge badge-processing">⚙️ Processando...</span>'
            action_buttons = '<button class="btn btn-disabled" disabled>Aguarde...</button>'
        else:
            status_badge = '<span class="badge badge-pending">⏳ Pendente</span>'
            action_buttons = f"""
                <div class="actions-grid">
                    <button class="btn btn-bili" onclick="downloadBilibili('{r['bvid']}', '{default_category}')">📥 Baixar Bilibili</button>
                    <button class="btn btn-douyin" onclick="showDouyinModal('{r['bvid']}', '{default_category}')">🔗 Link Douyin</button>
                    <button class="btn btn-ignore" onclick="ignoreVideo('{r['bvid']}')">🗑️ Ocultar</button>
                </div>
            """
            
        cards_html += f"""
        <div class="card" id="card-{r['bvid']}">
            <div class="card-image-container">
                <img src="{r['pic']}" class="card-image" alt="Capa do vídeo" onerror="this.src='https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png'">
                <span class="card-duration">{duration_str}</span>
            </div>
            <div class="card-content">
                <h3 class="card-title" title="{r['title']}">{r['title']}</h3>
                <p class="card-author">👤 {r['author']}</p>
                <div class="card-meta">
                    <span>👁️ {r['views']:,}</span>
                    <span>👍 {r['likes']:,}</span>
                    <span class="score-badge">🔥 Hype: {r['hype_score']:,}</span>
                </div>
                <div class="card-status-row">
                    {status_badge}
                    <a href="https://www.bilibili.com/video/{r['bvid']}" target="_blank" class="link-watch">🔗 Assistir Bilibili</a>
                </div>
                <div class="card-actions" id="actions-{r['bvid']}">
                    {action_buttons}
                </div>
            </div>
        </div>
        """
        
    if not cards_html:
        cards_html = f"""
        <div class="no-results">
            <p>📭 Nenhum vídeo pendente na triagem de {"Anime" if type == "anime" else "Manhwa"}.</p>
            <p class="hint">Clique em "Sincronizar Busca" acima para buscar novidades do Bilibili.</p>
        </div>
        """

    tab_anime_active = "active" if type == "anime" else ""
    tab_manhwa_active = "active" if type == "manhwa" else ""

    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="referrer" content="no-referrer">
        <title>Kuma Scrapper - Triagem de Busca Geral</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }}
            body {{
                background-color: #080811;
                color: #e2e8f0;
                min-height: 100vh;
                padding: 24px;
            }}
            header {{
                max-width: 1200px;
                margin: 0 auto 32px auto;
                display: flex;
                justify-content: space-between;
                align-items: center;
                background: rgba(20, 20, 35, 0.6);
                backdrop-filter: blur(12px);
                padding: 20px 32px;
                border-radius: 16px;
                border: 1px solid rgba(187, 134, 252, 0.15);
                box-shadow: 0 8px 32px rgba(0,0,0,0.5);
            }}
            .logo-section h1 {{
                font-size: 1.8rem;
                background: linear-gradient(90deg, #bb86fc, #03dac6);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-weight: 700;
            }}
            .logo-section p {{
                font-size: 0.85rem;
                color: #888;
                margin-top: 4px;
            }}
            .btn-sync {{
                background: linear-gradient(135deg, #6200ee, #3700b3);
                color: #fff;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: 600;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(98,0,238,0.3);
            }}
            .btn-sync:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(98,0,238,0.5);
            }}
            main {{
                max-width: 1200px;
                margin: 0 auto;
            }}
            
            /* Estilo das Abas de Tipo de Conteúdo */
            .tabs-row {{
                display: flex;
                gap: 16px;
                margin-bottom: 24px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding-bottom: 12px;
            }}
            .tab-link {{
                padding: 10px 24px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                font-size: 0.95rem;
                color: #a0aec0;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.05);
                transition: all 0.2s ease;
            }}
            .tab-link:hover {{
                color: #fff;
                background: rgba(255, 255, 255, 0.06);
            }}
            .tab-link.active {{
                color: #fff;
                background: linear-gradient(135deg, #bb86fc, #6200ee);
                border-color: #bb86fc;
                box-shadow: 0 4px 15px rgba(187, 134, 252, 0.25);
            }}

            .filter-row {{
                margin-bottom: 24px;
                display: flex;
                gap: 12px;
            }}
            .filter-btn {{
                background: rgba(30, 30, 50, 0.5);
                color: #a0aec0;
                border: 1px solid rgba(255,255,255,0.05);
                padding: 8px 18px;
                border-radius: 20px;
                cursor: pointer;
                transition: all 0.2s;
                font-size: 0.9rem;
            }}
            .filter-btn:hover, .filter-btn.active {{
                background: #bb86fc;
                color: #080811;
                border-color: #bb86fc;
                font-weight: 600;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 24px;
            }}
            .card {{
                background: rgba(18, 18, 32, 0.7);
                backdrop-filter: blur(8px);
                border-radius: 14px;
                overflow: hidden;
                border: 1px solid rgba(255,255,255,0.06);
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                transition: all 0.3s ease;
                display: flex;
                flex-direction: column;
            }}
            .card:hover {{
                transform: translateY(-6px);
                border-color: rgba(3, 218, 198, 0.3);
                box-shadow: 0 10px 25px rgba(3, 218, 198, 0.15);
            }}
            .card-image-container {{
                position: relative;
                width: 100%;
                padding-top: 56.25%; /* 16:9 Aspect Ratio */
                background-color: #10101a;
            }}
            .card-image {{
                position: absolute;
                top: 0; left: 0; width: 100%; height: 100%;
                object-fit: cover;
            }}
            .card-duration {{
                position: absolute;
                bottom: 8px; right: 8px;
                background: rgba(0,0,0,0.85);
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 0.75rem;
                font-weight: 600;
            }}
            .card-content {{
                padding: 16px;
                display: flex;
                flex-direction: column;
                flex-grow: 1;
            }}
            .card-title {{
                font-size: 1rem;
                font-weight: 600;
                margin-bottom: 8px;
                line-height: 1.4;
                height: 2.8rem;
                overflow: hidden;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
            }}
            .card-author {{
                font-size: 0.8rem;
                color: #a0aec0;
                margin-bottom: 12px;
            }}
            .card-meta {{
                display: flex;
                justify-content: space-between;
                font-size: 0.8rem;
                color: #718096;
                margin-bottom: 12px;
                align-items: center;
            }}
            .score-badge {{
                color: #ff5722;
                font-weight: 600;
            }}
            .card-status-row {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 16px;
                font-size: 0.8rem;
            }}
            .badge {{
                padding: 3px 8px;
                border-radius: 4px;
                font-weight: 600;
            }}
            .badge-pending {{
                background: rgba(251, 191, 36, 0.1);
                color: #fbbf24;
            }}
            .badge-processing {{
                background: rgba(59, 130, 246, 0.15);
                color: #60a5fa;
                animation: pulse 1.5s infinite;
            }}
            @keyframes pulse {{
                0% {{ opacity: 0.6; }}
                50% {{ opacity: 1; }}
                100% {{ opacity: 0.6; }}
            }}
            .link-watch {{
                color: #03dac6;
                text-decoration: none;
                font-weight: 600;
            }}
            .link-watch:hover {{
                text-decoration: underline;
            }}
            .card-actions {{
                margin-top: auto;
            }}
            .actions-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 8px;
            }}
            .actions-grid .btn-ignore {{
                grid-column: span 2;
            }}
            .btn {{
                padding: 8px 12px;
                border: none;
                border-radius: 6px;
                font-size: 0.8rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
            }}
            .btn-bili {{
                background: #00a1d6;
                color: #fff;
            }}
            .btn-bili:hover {{ background: #008ebe; }}
            .btn-douyin {{
                background: #ff0050;
                color: #fff;
            }}
            .btn-douyin:hover {{ background: #d60043; }}
            .btn-ignore {{
                background: rgba(255,255,255,0.05);
                color: #e2e8f0;
                border: 1px solid rgba(255,255,255,0.08);
            }}
            .btn-ignore:hover {{
                background: rgba(244, 63, 94, 0.1);
                color: #f43f5e;
                border-color: rgba(244, 63, 94, 0.3);
            }}
            .btn-disabled {{
                background: rgba(255,255,255,0.05);
                color: #718096;
                cursor: not-allowed;
                width: 100%;
            }}
            .no-results {{
                grid-column: 1 / -1;
                text-align: center;
                padding: 64px 32px;
                background: rgba(20, 20, 35, 0.4);
                border-radius: 12px;
                border: 1px dashed rgba(255,255,255,0.08);
            }}
            .no-results p {{ font-size: 1.1rem; color: #a0aec0; margin-bottom: 8px; }}
            .no-results .hint {{ font-size: 0.85rem; color: #718096; }}
            
            /* Modal simples */
            .modal {{
                display: none;
                position: fixed;
                top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.8);
                backdrop-filter: blur(8px);
                z-index: 1000;
                justify-content: center;
                align-items: center;
            }}
            .modal-content {{
                background: #121220;
                border: 1px solid rgba(187, 134, 252, 0.2);
                border-radius: 14px;
                padding: 24px;
                width: 90%;
                max-width: 480px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.8);
            }}
            .modal h3 {{ margin-bottom: 12px; color: #bb86fc; }}
            .modal p {{ font-size: 0.85rem; color: #a0aec0; margin-bottom: 16px; }}
            .modal input[type="text"] {{
                width: 100%;
                padding: 10px;
                background: #080811;
                border: 1px solid rgba(255,255,255,0.1);
                color: #fff;
                border-radius: 6px;
                margin-bottom: 16px;
            }}
            .modal-row {{
                display: flex;
                gap: 12px;
                margin-bottom: 16px;
            }}
            .modal-row select {{
                flex-grow: 1;
                padding: 10px;
                background: #080811;
                color: #fff;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
            }}
            .modal-buttons {{
                display: flex;
                justify-content: flex-end;
                gap: 12px;
            }}
            .modal-btn {{
                padding: 10px 18px;
                border-radius: 6px;
                border: none;
                cursor: pointer;
                font-weight: 600;
            }}
            .modal-btn-cancel {{ background: rgba(255,255,255,0.08); color: #fff; }}
            .modal-btn-send {{ background: #ff0050; color: #fff; }}
        </style>
    </head>
    <body>
        <header>
            <div class="logo-section">
                <h1>🦊 Kuma Scrapper</h1>
                <p>Triagem de Vídeos Populares de Anime e Manhwa (新番解说 / 韩漫解说)</p>
            </div>
            <button class="btn-sync" onclick="syncSearch()">🔄 Sincronizar Busca</button>
        </header>
        
        <main>
            <!-- Abas Principais de Triagem -->
            <div class="tabs-row">
                <a href="{ROOT_PATH}/?type=anime" class="tab-link {tab_anime_active}">🌸 Triagem Anime</a>
                <a href="{ROOT_PATH}/?type=manhwa" class="tab-link {tab_manhwa_active}">🇰🇷 Triagem Manhwa</a>
            </div>
            
            <div class="filter-row">
                <button class="filter-btn active" onclick="filterCards('all', this)">Todos ({len(results)})</button>
                <button class="filter-btn" onclick="filterCards('shorts', this)">📱 Shorts (&lt; 4m)</button>
                <button class="filter-btn" onclick="filterCards('longos', this)">🎬 Vídeos Longos (&ge; 4m)</button>
            </div>
            
            <div class="grid" id="cards-grid">
                {cards_html}
            </div>
        </main>
        
        <!-- Modal do Douyin -->
        <div id="douyinModal" class="modal">
            <div class="modal-content">
                <h3>🔗 Download via Link do Douyin</h3>
                <p>Cole abaixo o link do Douyin correspondente a este vídeo do Bilibili.</p>
                <input type="text" id="douyinUrlInput" placeholder="https://v.douyin.com/..." required>
                
                <div class="modal-row">
                    <select id="douyinCategory">
                        <option value="shorts">📱 Categoria: Shorts</option>
                        <option value="longos">🎬 Categoria: Vídeos Longos</option>
                    </select>
                    <select id="douyinType">
                        <option value="anime" {"selected" if type == "anime" else ""}>🌸 Conteúdo: Anime</option>
                        <option value="manhwa" {"selected" if type == "manhwa" else ""}>🇰🇷 Conteúdo: Manhwa</option>
                    </select>
                </div>
                
                <input type="hidden" id="modalBvid">
                
                <div class="modal-buttons">
                    <button class="modal-btn modal-btn-cancel" onclick="closeModal()">Cancelar</button>
                    <button class="modal-btn modal-btn-send" onclick="submitDouyinDownload()">Enviar e Baixar</button>
                </div>
            </div>
        </div>
        
        <!-- Modal de Confirmação Bilibili -->
        <div id="biliModal" class="modal">
            <div class="modal-content">
                <h3>📥 Download via Bilibili</h3>
                <p>Confirme a categoria e o conteúdo de destino para o vídeo.</p>
                
                <div class="modal-row" style="margin-top: 10px;">
                    <select id="biliCategory">
                        <option value="shorts">📱 Categoria: Shorts</option>
                        <option value="longos">🎬 Categoria: Vídeos Longos</option>
                    </select>
                    <select id="biliType">
                        <option value="anime" {"selected" if type == "anime" else ""}>🌸 Conteúdo: Anime</option>
                        <option value="manhwa" {"selected" if type == "manhwa" else ""}>🇰🇷 Conteúdo: Manhwa</option>
                    </select>
                </div>
                
                <input type="hidden" id="biliModalBvid">
                
                <div class="modal-buttons" style="margin-top: 20px;">
                    <button class="modal-btn modal-btn-cancel" onclick="closeBiliModal()">Cancelar</button>
                    <button class="modal-btn modal-btn-send" style="background:#00a1d6;" onclick="submitBiliDownload()">Confirmar e Baixar</button>
                </div>
            </div>
        </div>

        <script>
            const ROOT_PATH = "{ROOT_PATH}";

            function filterCards(type, btn) {{
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                const cards = document.querySelectorAll('.card');
                cards.forEach(card => {{
                    const durationText = card.querySelector('.card-duration').textContent;
                    const parts = durationText.split(':');
                    const mins = parseInt(parts[0]);
                    
                    if (type === 'all') {{
                        card.style.display = 'flex';
                    }} else if (type === 'shorts') {{
                        if (mins < 4) card.style.display = 'flex';
                        else card.style.display = 'none';
                    }} else if (type === 'longos') {{
                        if (mins >= 4) card.style.display = 'flex';
                        else card.style.display = 'none';
                    }}
                }});
            }}

            async function syncSearch() {{
                const btn = document.querySelector('.btn-sync');
                btn.textContent = "⏳ Sincronizando...";
                btn.disabled = true;
                try {{
                    const response = await fetch(ROOT_PATH + '/api/sync', {{ method: 'POST' }});
                    const data = await response.json();
                    alert(data.message);
                    window.location.reload();
                }} catch (e) {{
                    alert("Erro ao sincronizar busca: " + e);
                }} finally {{
                    btn.textContent = "🔄 Sincronizar Busca";
                    btn.disabled = false;
                }}
            }}

            async function ignoreVideo(bvid) {{
                if (confirm("Deseja ocultar este vídeo da triagem?")) {{
                    try {{
                        const response = await fetch(ROOT_PATH + '/api/ignore/' + bvid, {{ method: 'POST' }});
                        const data = await response.json();
                        if (data.ok) {{
                            document.getElementById('card-' + bvid).style.opacity = '0';
                            setTimeout(() => document.getElementById('card-' + bvid).remove(), 300);
                        }}
                    }} catch(e) {{
                        alert("Erro ao ignorar vídeo: " + e);
                    }}
                }}
            }}

            function showDouyinModal(bvid, defaultCat) {{
                document.getElementById('modalBvid').value = bvid;
                document.getElementById('douyinCategory').value = defaultCat;
                document.getElementById('douyinUrlInput').value = "";
                document.getElementById('douyinModal').style.display = 'flex';
            }}

            function closeModal() {{
                document.getElementById('douyinModal').style.display = 'none';
            }}

            function downloadBilibili(bvid, defaultCat) {{
                document.getElementById('biliModalBvid').value = bvid;
                document.getElementById('biliCategory').value = defaultCat;
                document.getElementById('biliModal').style.display = 'flex';
            }}

            function closeBiliModal() {{
                document.getElementById('biliModal').style.display = 'none';
            }}

            async function submitBiliDownload() {{
                const bvid = document.getElementById('biliModalBvid').value;
                const cat = document.getElementById('biliCategory').value;
                const type = document.getElementById('biliType').value;
                
                closeBiliModal();
                updateCardToProcessing(bvid);

                const formData = new FormData();
                formData.append('bvid', bvid);
                formData.append('url', 'https://www.bilibili.com/video/' + bvid);
                formData.append('is_douyin', '0');
                formData.append('category', cat);
                formData.append('content_type', type);

                try {{
                    const response = await fetch(ROOT_PATH + '/api/download', {{ method: 'POST', body: formData }});
                    const data = await response.json();
                    if (data.ok) {{
                        alert("Download do Bilibili iniciado em background! O vídeo sumirá da lista quando terminar.");
                    }}
                }} catch(e) {{
                    alert("Erro ao iniciar download: " + e);
                    window.location.reload();
                }}
            }}

            async function submitDouyinDownload() {{
                const bvid = document.getElementById('modalBvid').value;
                const url = document.getElementById('douyinUrlInput').value.trim ? document.getElementById('douyinUrlInput').value.trim() : document.getElementById('douyinUrlInput').value;
                const cat = document.getElementById('douyinCategory').value;
                const type = document.getElementById('douyinType').value;
                
                if (!url) {{
                    alert("Por favor, cole a URL do Douyin.");
                    return;
                }}

                closeModal();
                updateCardToProcessing(bvid);

                const formData = new FormData();
                formData.append('bvid', bvid);
                formData.append('url', url);
                formData.append('is_douyin', '1');
                formData.append('category', cat);
                formData.append('content_type', type);

                try {{
                    const response = await fetch(ROOT_PATH + '/api/download', {{ method: 'POST', body: formData }});
                    const data = await response.json();
                    if (data.ok) {{
                        alert("Download do Douyin iniciado em background! O vídeo sumirá da lista quando terminar.");
                    }}
                }} catch(e) {{
                    alert("Erro ao iniciar download: " + e);
                    window.location.reload();
                }}
            }}

            function updateCardToProcessing(bvid) {{
                const card = document.getElementById('card-' + bvid);
                if (card) {{
                    const badgeRow = card.querySelector('.card-status-row');
                    badgeRow.innerHTML = '<span class="badge badge-processing">⚙️ Processando...</span><a href="https://www.bilibili.com/video/' + bvid + '" target="_blank" class="link-watch">🔗 Assistir Bilibili</a>';
                    
                    const actions = card.querySelector('.card-actions');
                    actions.innerHTML = '<button class="btn btn-disabled" disabled>Aguarde...</button>';
                }}
            }}

            // Polling para os cards que estão em estado de processamento
            function startProcessingPolling() {{
                setInterval(async () => {{
                    const cards = document.querySelectorAll('.card');
                    const bvids = [];
                    cards.forEach(card => {{
                        const badge = card.querySelector('.badge-processing');
                        if (badge) {{
                            const bvid = card.id.replace('card-', '');
                            bvids.push(bvid);
                        }}
                    }});

                    if (bvids.length === 0) return;

                    try {{
                        const response = await fetch(ROOT_PATH + '/api/status?bvids=' + bvids.join(','));
                        const data = await response.json();
                        
                        for (const bvid of bvids) {{
                            const status = data[bvid];
                            if (status !== 'processing') {{
                                if (status === 'downloaded' || status === 'ignored') {{
                                    // Remove o card com animação suave
                                    const card = document.getElementById('card-' + bvid);
                                    if (card) {{
                                        card.style.transition = 'all 0.5s ease';
                                        card.style.opacity = '0';
                                        card.style.transform = 'scale(0.9)';
                                        setTimeout(() => {{
                                            card.remove();
                                            // Se não sobrar nenhum card, exibe a mensagem de sem resultados
                                            const grid = document.getElementById('cards-grid');
                                            if (grid.querySelectorAll('.card').length === 0) {{
                                                grid.innerHTML = `
                                                    <div class="no-results">
                                                        <p>📭 Nenhum vídeo pendente na triagem.</p>
                                                        <p class="hint">Clique em "Sincronizar Busca" acima para buscar novidades.</p>
                                                    </div>
                                                `;
                                            }}
                                        }}, 500);
                                    }}
                                }} else if (status === 'pending') {{
                                    // Voltou a ser pendente (falhou o processamento)
                                    restoreCardToPending(bvid);
                                }}
                            }}
                        }}
                    }} catch (e) {{
                        console.error("Erro no polling de status:", e);
                    }}
                }}, 3000);
            }}

            function restoreCardToPending(bvid) {{
                const card = document.getElementById('card-' + bvid);
                if (card) {{
                    const badgeRow = card.querySelector('.card-status-row');
                    badgeRow.innerHTML = '<span class="badge badge-pending">⏳ Pendente</span><a href="https://www.bilibili.com/video/' + bvid + '" target="_blank" class="link-watch">🔗 Assistir Bilibili</a>';
                    
                    const durationText = card.querySelector('.card-duration').textContent;
                    const parts = durationText.split(':');
                    const mins = parseInt(parts[0]);
                    const defaultCategory = mins < 4 ? 'shorts' : 'longos';
                    
                    const actions = card.querySelector('.card-actions');
                    actions.innerHTML = `
                        <div class="actions-grid">
                            <button class="btn btn-bili" onclick="downloadBilibili('` + bvid + `', '` + defaultCategory + `')">📥 Baixar Bilibili</button>
                            <button class="btn btn-douyin" onclick="showDouyinModal('` + bvid + `', '` + defaultCategory + `')">🔗 Link Douyin</button>
                            <button class="btn btn-ignore" onclick="ignoreVideo('` + bvid + `')">🗑️ Ocultar</button>
                        </div>
                    `;
                }}
            }}

            // Inicia o polling ao carregar a página
            window.addEventListener('DOMContentLoaded', startProcessingPolling);
        </script>
    </body>
    </html>

    """
    return html_content

def run_panel():
    import uvicorn
    # Inicializa banco de dados SQLite caso necessário
    database.init_db()
    print("Iniciando Painel Web de Triagem na porta 5556 (http://localhost:5556)...")
    uvicorn.run(app, host="0.0.0.0", port=5556, log_level="warning")
