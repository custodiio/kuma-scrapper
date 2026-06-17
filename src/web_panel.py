import os
import re
import time
import httpx
import logging
from fastapi import FastAPI, BackgroundTasks, Form, HTTPException, Request, Response, Cookie, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from src import database, search_scrapper, media_processor, drive_uploader
from src.config import DOUYIN_API_BASE

logger = logging.getLogger(__name__)

ROOT_PATH = os.getenv("ROOT_PATH", "")
app = FastAPI(title="Kuma Scrapper - Painel de Triagem Web", root_path=ROOT_PATH)

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Se for uma rota de API, valida o token do cookie
    if request.url.path.startswith("/api/"):
        token = request.cookies.get("scrapper_session")
        if not database.validate_web_session(token):
            return JSONResponse(
                status_code=401,
                content={"ok": False, "message": "Sessão inválida ou expirada. Reabra o link no bot do Telegram."}
            )
    response = await call_next(request)
    return response

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
                resp_content_type = r.headers.get("Content-Type", "")
                if r.status_code == 200 and "application/json" not in resp_content_type:
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
                    r.read()
                    try:
                        err_data = r.json()
                        err_msg = err_data.get("message", "Erro interno da API local")
                    except Exception:
                        err_msg = f"HTTP {r.status_code}: {r.text[:200]}"
                    
                    logger.error(f"Erro no download pela API local para {bvid}: {err_msg}")
                    if tg_msg_id:
                        send_telegram_status(f"❌ **Falha ao realizar download** do vídeo para BVID `{bvid}` na API local:\n`{err_msg}`", tg_msg_id)
                    database.update_video_status(bvid, "pending")
                    database.update_search_result_status(bvid, "pending")
                    database.update_channel_update_status(bvid, "pending")
                    return
    except Exception as e:
        logger.error(f"Erro ao baixar vídeo na API em background: {e}")
        if tg_msg_id:
            send_telegram_status(f"❌ **Falha na requisição** do download para BVID `{bvid}`:\n`{str(e)}`", tg_msg_id)
        database.update_video_status(bvid, "pending")
        database.update_search_result_status(bvid, "pending")
        database.update_channel_update_status(bvid, "pending")
        return
        
    if not download_success:
        logger.error(f"Falha no download para bvid={bvid}")
        if tg_msg_id:
            send_telegram_status(f"❌ **Falha ao salvar o vídeo** do BVID `{bvid}` localmente.", tg_msg_id)
        database.update_video_status(bvid, "pending")
        database.update_search_result_status(bvid, "pending")
        database.update_channel_update_status(bvid, "pending")
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
        database.update_video_status(bvid, "pending")
        database.update_search_result_status(bvid, "pending")
        database.update_channel_update_status(bvid, "pending")
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
        
        # Procura o título correto do vídeo no SQLite
        original_title = f"Mapeado: {bvid}"
        pv_data = database.get_video_by_bvid(bvid)
        if pv_data:
            original_title = pv_data["title"]
        else:
            for item in database.get_search_results(status="pending", content_type=content_type) + database.get_search_results(status="downloaded", content_type=content_type):
                if item["bvid"] == bvid:
                    original_title = item["title"]
                    break
                    
        # Atualiza o status do vídeo no SQLite
        database.update_video_status(bvid, "downloaded")
        database.update_search_result_status(bvid, "downloaded")
        database.update_channel_update_status(bvid, "downloaded")
        
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
        database.update_video_status(bvid, "pending")
        database.update_search_result_status(bvid, "pending")
        database.update_channel_update_status(bvid, "pending")
        
    # 4. Limpeza física de mídias e cache do Evil0ctal
    video_id_filter = bvid
    if is_douyin:
        match_id = re.search(r"video/(\d+)", url)
        if match_id:
            video_id_filter = match_id.group(1)
            
    clean_local_mids_and_api_cache(temp_video_path, final_video_path, final_audio_path, video_id_filter)

# ----------------- APIs DO FastApi -----------------

@app.post("/api/sync")
async def sync_search():
    """Rota para acionamento manual da busca geral do Bilibili."""
    try:
        inserted = await search_scrapper.run_search_scraping()
        return JSONResponse(content={"ok": True, "message": f"Busca geral sincronizada! {inserted} novos vídeos inseridos para triagem."})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "message": str(e)})

@app.post("/api/channels/sync")
async def sync_channels(content_type: str = Form(...)):
    """Varre os canais cadastrados buscando novas postagens."""
    try:
        inserted = await search_scrapper.track_channels_updates(content_type)
        return {"ok": True, "message": f"Mapeamento concluído! {inserted} novos posts encontrados e adicionados à aba de Atualizações."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "message": str(e)})

@app.post("/api/channels/add")
async def api_add_channel(uid: str = Form(...), name: str = Form(...), content_type: str = Form(...)):
    """Adiciona um novo canal buscando imediatamente seu post recente como referência inicial."""
    uid = uid.strip()
    name = name.strip()
    if not uid or not name:
        raise HTTPException(status_code=400, detail="UID e Nome são obrigatórios.")
        
    latest_video = await search_scrapper.get_latest_video_for_channel(uid)
    last_ref = latest_video["bvid"] if latest_video else None
    
    success = database.add_channel(uid, name, category="all", content_type=content_type, last_video_ref=last_ref)
    if success:
        ref_info = f"Vídeo de referência inicial: {last_ref}" if last_ref else "Sem postagem recente como referência inicial."
        return {"ok": True, "message": f"Canal '{name}' cadastrado! {ref_info}"}
    else:
        raise HTTPException(status_code=500, detail="Erro ao salvar o canal no banco de dados.")

@app.delete("/api/channels/delete/{uid}")
async def api_delete_channel(uid: str):
    """Remove um canal monitorado."""
    success = database.remove_channel(uid)
    return {"ok": success}

@app.post("/api/ignore/{bvid}")
async def ignore_video(bvid: str, source: str = Form("search")):
    """Marca o vídeo como ignorado para ocultar da triagem correspondente."""
    if source == "channel":
        success = database.update_channel_update_status(bvid, "ignored")
    else:
        success = database.update_search_result_status(bvid, "ignored")
    return {"ok": success}

@app.post("/api/cart/add")
async def add_to_cart(
    bvid: str = Form(...),
    title: str = Form(...),
    duration_seconds: int = Form(...),
    content_type: str = Form(...),
    pic: str = Form(...),
    source: str = Form(...) # 'search' ou 'channel'
):
    """Adiciona um vídeo de triagem para a fila/carrinho (processed_videos)."""
    category = "shorts" if duration_seconds < 240 else "longos"
    
    # Adiciona em processed_videos com status pending
    success = database.register_video(
        bvid=bvid,
        title=title,
        source=source,
        category=category,
        content_type=content_type,
        status="pending"
    )
    
    if success:
        if source == "channel":
            database.update_channel_update_status(bvid, "in_cart")
        else:
            database.update_search_result_status(bvid, "in_cart")
            
    return {"ok": success}

@app.post("/api/cart/remove/{bvid}")
async def remove_from_cart(bvid: str):
    """Remove um vídeo do carrinho e restaura seu estado na triagem de origem."""
    database.update_search_result_status(bvid, "pending")
    database.update_channel_update_status(bvid, "pending")
    success = database.remove_video_from_queue(bvid)
    return {"ok": success}

@app.post("/api/cart/mark_posted/{bvid}")
async def mark_posted(bvid: str):
    """Marca o vídeo da fila como postado."""
    success = database.mark_video_as_posted(bvid)
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
    """Agenda o download em background a partir do carrinho."""
    is_douyin_bool = bool(is_douyin)
    
    # Atualiza status provisório
    database.update_video_status(bvid, "processing")
    database.update_search_result_status(bvid, "processing")
    database.update_channel_update_status(bvid, "processing")
    
    # Agenda a tarefa de processamento em background
    background_tasks.add_task(
        perform_background_download,
        bvid=bvid,
        url=url,
        is_douyin=is_douyin_bool,
        category=category,
        content_type=content_type
    )
    return {"ok": True, "message": "Processamento e download iniciados em background!"}

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
        # 1. Verifica processed_videos (Carrinho)
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
                
        # 3. Para os restantes, verifica channel_updates (atualizações)
        missing_updates = [b for b in bvid_list if b not in res]
        if missing_updates:
            placeholders_u = ",".join("?" for _ in missing_updates)
            cursor.execute(f"SELECT bvid, status FROM channel_updates WHERE bvid IN ({placeholders_u})", missing_updates)
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

@app.post("/api/terms/add")
async def api_add_term(term: str = Form(...), content_type: str = Form(...)):
    """Adiciona um novo termo de busca."""
    term = term.strip()
    if not term:
        raise HTTPException(status_code=400, detail="O termo não pode ser vazio.")
    success = database.add_search_term(term, content_type)
    return {"ok": success}

@app.delete("/api/terms/delete/{term_id}")
async def api_delete_term(term_id: int):
    """Remove um termo de busca pelo ID."""
    success = database.remove_search_term(term_id)
    return {"ok": success}

@app.post("/api/session/renew")
async def api_renew_session(request: Request):
    """Renova a validade da sessão ativa do usuário."""
    token = request.cookies.get("scrapper_session")
    if not token:
        raise HTTPException(status_code=401, detail="Nenhum token encontrado.")
    
    success = database.renew_web_session(token, 30)
    if success:
        return {"ok": True, "message": "Sessão renovada com sucesso!"}
    else:
        raise HTTPException(status_code=401, detail="Sessão expirada ou inválida. Reabra o link no bot.")

# ─── PÁGINA HTML PRINCIPAL ───────────────────────────────────────────────────

def get_access_denied_page():
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Acesso Negado - Kuma Scrapper</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
        body {
            background-color: #060610;
            color: #e2e8f0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 24px;
        }
        .container {
            max-width: 500px;
            width: 100%;
            background: rgba(20, 20, 38, 0.7);
            backdrop-filter: blur(16px);
            border-radius: 24px;
            border: 1px solid rgba(255, 75, 75, 0.2);
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.8), 0 0 20px rgba(255, 75, 75, 0.05);
            padding: 40px;
            text-align: center;
        }
        .icon {
            font-size: 4rem;
            margin-bottom: 24px;
            animation: pulse 2s infinite;
        }
        h2 {
            font-size: 1.8rem;
            margin-bottom: 12px;
            font-weight: 700;
            background: linear-gradient(90deg, #ff4b4b, #bb86fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        p {
            font-size: 1rem;
            color: #a0aec0;
            line-height: 1.6;
            margin-bottom: 30px;
        }
        .instructions {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 16px;
            border-radius: 12px;
            font-size: 0.9rem;
            color: #cbd5e0;
            text-align: left;
            margin-bottom: 30px;
        }
        .instructions ol {
            padding-left: 20px;
        }
        .instructions li {
            margin-bottom: 8px;
        }
        .btn-bot {
            display: inline-block;
            background: linear-gradient(135deg, #6200ee, #3700b3);
            color: #fff;
            text-decoration: none;
            padding: 14px 28px;
            border-radius: 10px;
            font-weight: 600;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(98, 0, 238, 0.3);
        }
        .btn-bot:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(98, 0, 238, 0.5);
        }
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); text-shadow: 0 0 10px rgba(255,75,75,0.3); }
            100% { transform: scale(1); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🔒</div>
        <h2>Acesso Negado ou Expirado</h2>
        <p>Por motivos de segurança, você não pode acessar o painel de triagem diretamente sem uma sessão ativa.</p>
        <div class="instructions">
            <strong>Como obter acesso:</strong>
            <ol style="margin-top: 8px;">
                <li>Abra o Telegram e acesse o bot do <strong>Kuma Scrapper</strong>.</li>
                <li>No menu principal, clique em <strong>🌐 Visualizar Triagem de Busca Web</strong>.</li>
                <li>Um link de acesso seguro e temporário será gerado exclusivamente para você.</li>
            </ol>
        </div>
        <a href="https://t.me" target="_blank" class="btn-bot">🤖 Ir para o Telegram</a>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    response: Response,
    tab: str = "search",
    type: str = "anime",
    session: str = Query(None)
):
    """Renderiza o Painel de Triagem Web unificado de 5 abas com validação de sessão."""
    if type not in ["anime", "manhwa"]:
        type = "anime"
    if tab not in ["search", "updates", "cart", "channels", "terms"]:
        tab = "search"
        
    # 1. Verifica se foi passado token na query (login inicial a partir do Bot)
    if session:
        if database.validate_web_session(session):
            # Sessão válida! Define o cookie e redireciona para a rota limpa
            redirect_url = f"{ROOT_PATH}/?tab={tab}&type={type}"
            redir_resp = RedirectResponse(url=redirect_url, status_code=303)
            redir_resp.set_cookie(
                key="scrapper_session",
                value=session,
                max_age=1800, # 30 min
                httponly=True,
                samesite="lax",
                secure=False
            )
            return redir_resp
        else:
            return HTMLResponse(content=get_access_denied_page(), status_code=401)
            
    # 2. Se não veio na query, verifica se o cookie existente é válido
    cookie_token = request.cookies.get("scrapper_session")
    if not database.validate_web_session(cookie_token):
        return HTMLResponse(content=get_access_denied_page(), status_code=401)
        
    type_title = "Anime 🌸" if type == "anime" else "Manhwa 🇰🇷"
    
    content_html = ""
    header_action_button = ""
    
    # ─── ABA 1: BUSCA GERAL ──────────────────────────────────────────────────
    if tab == "search":
        header_action_button = '<button class="btn-sync" onclick="syncSearch()">🔄 Sincronizar Busca por Termos</button>'
        results = database.get_search_results(status="pending", content_type=type)
        processing = database.get_search_results(status="processing", content_type=type)
        all_items = processing + results
        
        cards_html = ""
        for r in all_items:
            duration_str = f"{r['duration_seconds'] // 60}:{r['duration_seconds'] % 60:02d}"
            
            if r['status'] == "processing":
                badge = '<span class="badge badge-processing">⚙️ Processando...</span>'
                actions = '<button class="btn btn-disabled" disabled>Aguarde...</button>'
            else:
                badge = '<span class="badge badge-pending">⏳ Triagem</span>'
                actions = f"""
                    <button class="btn btn-cart" onclick="addToCart('{r['bvid']}', `{r['title']}`, {r['duration_seconds']}, '{type}', '{r['pic']}', 'search')">🛒 Add ao Carrinho</button>
                    <button class="btn btn-ignore" onclick="ignoreVideo('{r['bvid']}', 'search')">🗑️ Ocultar</button>
                """
                
            cards_html += f"""
            <div class="card" id="card-{r['bvid']}">
                <div class="card-image-container">
                    <img src="{r['pic']}" class="card-image" alt="Capa" onerror="this.src='https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png'">
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
                        {badge}
                        <a href="https://www.bilibili.com/video/{r['bvid']}" target="_blank" class="link-watch">🔗 Link Bilibili</a>
                    </div>
                    <div class="card-actions" id="actions-{r['bvid']}">
                        {actions}
                    </div>
                </div>
            </div>
            """
            
        if not cards_html:
            cards_html = """
            <div class="no-results">
                <p>📭 Nenhum vídeo pendente na triagem de busca geral.</p>
                <p class="hint">Clique em "Sincronizar Busca" para coletar novos resultados.</p>
            </div>
            """
        content_html = f'<div class="grid" id="cards-grid">{cards_html}</div>'

    # ─── ABA 2: ATUALIZAÇÕES DOS CANAIS ──────────────────────────────────────
    elif tab == "updates":
        header_action_button = f'<button class="btn-sync" onclick="syncChannels(\'{type}\')">🔄 Mapear Postagens de Canais</button>'
        results = database.get_channel_updates(status="pending", content_type=type)
        processing = database.get_channel_updates(status="processing", content_type=type)
        all_items = processing + results
        
        cards_html = ""
        for r in all_items:
            duration_str = f"{r['duration_seconds'] // 60}:{r['duration_seconds'] % 60:02d}"
            
            if r['status'] == "processing":
                badge = '<span class="badge badge-processing">⚙️ Processando...</span>'
                actions = '<button class="btn btn-disabled" disabled>Aguarde...</button>'
            else:
                badge = '<span class="badge badge-pending">🔔 Novo Post</span>'
                actions = f"""
                    <button class="btn btn-cart" onclick="addToCart('{r['bvid']}', `{r['title']}`, {r['duration_seconds']}, '{type}', '{r['pic']}', 'channel')">🛒 Add ao Carrinho</button>
                    <button class="btn btn-ignore" onclick="ignoreVideo('{r['bvid']}', 'channel')">🗑️ Ocultar</button>
                """
                
            cards_html += f"""
            <div class="card" id="card-{r['bvid']}">
                <div class="card-image-container">
                    <img src="{r['pic']}" class="card-image" alt="Capa" onerror="this.src='https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png'">
                    <span class="card-duration">{duration_str}</span>
                </div>
                <div class="card-content">
                    <h3 class="card-title" title="{r['title']}">{r['title']}</h3>
                    <p class="card-author">📺 Canal: {r['author']}</p>
                    <div class="card-meta">
                        <span>👁️ {r['views']:,}</span>
                        <span>💬 Proxy Hype: {r['likes']:,}</span>
                    </div>
                    <div class="card-status-row">
                        {badge}
                        <a href="https://www.bilibili.com/video/{r['bvid']}" target="_blank" class="link-watch">🔗 Link Bilibili</a>
                    </div>
                    <div class="card-actions" id="actions-{r['bvid']}">
                        {actions}
                    </div>
                </div>
            </div>
            """
            
        if not cards_html:
            cards_html = """
            <div class="no-results">
                <p>📭 Nenhuma postagem recente de canais monitorados pendente.</p>
                <p class="hint">Clique em "Mapear Postagens de Canais" acima para buscar novidades.</p>
            </div>
            """
        content_html = f'<div class="grid" id="cards-grid">{cards_html}</div>'

    # ─── ABA 3: CARRINHO / FILA ──────────────────────────────────────────────
    elif tab == "cart":
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pv.*, c.name as channel_name 
            FROM processed_videos pv
            LEFT JOIN channels c ON pv.channel_uid = c.uid
            WHERE pv.content_type = ? AND pv.status != 'posted'
            ORDER BY CASE WHEN pv.status = 'downloaded' THEN 0 WHEN pv.status = 'processing' THEN 1 ELSE 2 END, pv.created_at DESC
        """, (type,))
        cart_items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        cards_html = ""
        for r in cart_items:
            if r['status'] == "downloaded":
                badge = '<span class="badge badge-downloaded">🟢 Pronto no Drive</span>'
                actions = f"""
                    <button class="btn btn-post" onclick="markAsPosted('{r['bvid']}')">✅ Postado</button>
                    <button class="btn btn-ignore" onclick="removeFromCart('{r['bvid']}')">🗑️ Remover</button>
                """
            elif r['status'] == "processing":
                badge = '<span class="badge badge-processing">⚙️ Baixando/Processando...</span>'
                actions = '<button class="btn btn-disabled" disabled>Processando...</button>'
            else:
                badge = '<span class="badge badge-pending">🛒 No Carrinho</span>'
                actions = f"""
                    <button class="btn btn-bili" onclick="downloadBilibili('{r['bvid']}', '{r['category']}')">📥 Bilibili</button>
                    <button class="btn btn-douyin" onclick="showDouyinModal('{r['bvid']}', '{r['category']}')">🔗 Douyin</button>
                    <button class="btn btn-ignore" style="grid-column: span 2" onclick="removeFromCart('{r['bvid']}')">🗑️ Remover</button>
                """
                
            channel_info = f"Canal: {r['channel_name']}" if r.get("channel_name") else f"Origem: {r['source'].capitalize()}"
            category_badge = "📱 Shorts" if r['category'] == "shorts" else "🎬 Longo"
            
            cards_html += f"""
            <div class="card" id="card-{r['bvid']}">
                <div class="card-content" style="padding: 20px; min-height: 180px;">
                    <span class="category-indicator">{category_badge}</span>
                    <h3 class="card-title" style="height: auto; max-height: 2.8rem; margin-top: 8px;" title="{r['title']}">{r['title']}</h3>
                    <p class="card-author" style="margin-top: 4px; margin-bottom: 12px;">👤 {channel_info} | ID: `{r['bvid']}`</p>
                    <div class="card-status-row" style="margin-bottom: 16px;">
                        {badge}
                        <a href="https://www.bilibili.com/video/{r['bvid']}" target="_blank" class="link-watch">🔗 Link Bilibili</a>
                    </div>
                    <div class="card-actions actions-grid" id="actions-{r['bvid']}">
                        {actions}
                    </div>
                </div>
            </div>
            """
            
        if not cards_html:
            cards_html = """
            <div class="no-results">
                <p>🛒 Seu carrinho de downloads está vazio.</p>
                <p class="hint">Navegue pelas abas "Busca Geral" ou "Atualizações" para triar vídeos e adicioná-los aqui.</p>
            </div>
            """
        content_html = f'<div class="grid" id="cards-grid">{cards_html}</div>'

    # ─── ABA 4: GERENCIAR CANAIS ─────────────────────────────────────────────
    elif tab == "channels":
        channels = database.get_channels(content_type=type)
        
        channel_rows = ""
        for c in channels:
            ref_badge = f'<code class="ref-badge">{c["last_video_ref"]}</code>' if c["last_video_ref"] else '<span class="ref-empty">Nenhum post de ref</span>'
            channel_rows += f"""
            <tr id="channel-row-{c['uid']}">
                <td><strong>{c['name']}</strong></td>
                <td><code>{c['uid']}</code></td>
                <td>{ref_badge}</td>
                <td>
                    <a href="https://space.bilibili.com/{c['uid']}" target="_blank" class="link-watch">🔗 Perfil</a>
                    <button class="btn-delete-channel" onclick="deleteChannel('{c['uid']}', '{c['name']}')">🗑️ Remover</button>
                </td>
            </tr>
            """
            
        if not channel_rows:
            channel_rows = f"""
            <tr>
                <td colspan="4" class="empty-table">Nenhum canal monitorado cadastrado para {type_title}.</td>
            </tr>
            """
            
        content_html = f"""
        <div class="admin-panel">
            <div class="admin-card">
                <h3>➕ Cadastrar Novo Canal no Bilibili ({type_title})</h3>
                <p class="hint">Os canais cadastrados servirão tanto para vídeos shorts quanto para vídeos longos.</p>
                <form id="addChannelForm" onsubmit="addChannel(event)">
                    <div class="form-row">
                        <input type="text" id="newChannelUid" placeholder="UID do Canal Bilibili (Ex: 178360345)" required>
                        <input type="text" id="newChannelName" placeholder="Nome do Canal / Criador" required>
                        <input type="hidden" id="newChannelType" value="{type}">
                        <button type="submit" class="btn btn-sync" style="box-shadow:none;">➕ Adicionar</button>
                    </div>
                </form>
            </div>
            
            <div class="admin-card" style="margin-top: 24px;">
                <h3>📺 Canais Cadastrados ({type_title})</h3>
                <table class="channel-table">
                    <thead>
                        <tr>
                            <th>Nome</th>
                            <th>UID do Perfil</th>
                            <th>Última Ref (BVID)</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {channel_rows}
                    </tbody>
                </table>
            </div>
        </div>
        """

    # ─── ABA 5: TERMOS DE BUSCA ──────────────────────────────────────────────
    elif tab == "terms":
        terms = database.get_search_terms(content_type=type)
        
        tags_html = ""
        for t in terms:
            tags_html += f"""
            <div class="tag-box" id="tag-{t['id']}">
                <span>{t['term']}</span>
                <button class="tag-delete-btn" onclick="deleteTerm({t['id']}, '{t['term']}')">×</button>
            </div>
            """
            
        if not tags_html:
            tags_html = "<p class='hint'>Nenhum termo de busca configurado.</p>"
            
        content_html = f"""
        <div class="admin-panel">
            <div class="admin-card">
                <h3>➕ Adicionar Termo de Busca ({type_title})</h3>
                <p class="hint">Termos em chinês usados pelo scrapper para varrer o Bilibili automaticamente por novidades.</p>
                <form id="addTermForm" onsubmit="addTerm(event)">
                    <div class="form-row">
                        <input type="text" id="newTermText" placeholder="Ex: 韩漫解说" required>
                        <input type="hidden" id="newTermType" value="{type}">
                        <button type="submit" class="btn btn-sync" style="box-shadow:none;">➕ Adicionar</button>
                    </div>
                </form>
            </div>
            
            <div class="admin-card" style="margin-top: 24px;">
                <h3>🔑 Tags e Termos Ativos ({type_title})</h3>
                <div class="tags-container">
                    {tags_html}
                </div>
            </div>
        </div>
        """

    tab_search_active = "active" if tab == "search" else ""
    tab_updates_active = "active" if tab == "updates" else ""
    tab_cart_active = "active" if tab == "cart" else ""
    tab_channels_active = "active" if tab == "channels" else ""
    tab_terms_active = "active" if tab == "terms" else ""
    
    sublink_anime = f"{ROOT_PATH}/?tab={tab}&type=anime"
    sublink_manhwa = f"{ROOT_PATH}/?tab={tab}&type=manhwa"
    tab_anime_active = "active" if type == "anime" else ""
    tab_manhwa_active = "active" if type == "manhwa" else ""

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="referrer" content="no-referrer">
    <title>Kuma Scrapper - Triagem & Downloads</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }}
        body {{
            background-color: #060610;
            color: #e2e8f0;
            min-height: 100vh;
            padding: 24px;
        }}
        .btn-renew-session {{
            background: rgba(3, 218, 198, 0.05);
            color: #03dac6;
            border: 1px solid rgba(3, 218, 198, 0.25);
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            margin-right: 8px;
        }}
        .btn-renew-session:hover {{
            background: rgba(3, 218, 198, 0.15);
            border-color: #03dac6;
            box-shadow: 0 0 15px rgba(3, 218, 198, 0.15);
        }}
        header {{
            max-width: 1200px;
            margin: 0 auto 32px auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(15, 15, 30, 0.75);
            backdrop-filter: blur(12px);
            padding: 20px 32px;
            border-radius: 16px;
            border: 1px solid rgba(187, 134, 252, 0.12);
            box-shadow: 0 8px 32px rgba(0,0,0,0.6);
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
        
        .context-row {{
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            justify-content: flex-end;
        }}
        .context-link {{
            padding: 8px 18px;
            border-radius: 20px;
            font-size: 0.85rem;
            text-decoration: none;
            font-weight: 600;
            color: #a0aec0;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            transition: all 0.2s;
        }}
        .context-link.active {{
            background: rgba(3, 218, 198, 0.15);
            color: #03dac6;
            border-color: #03dac6;
        }}

        .tabs-row {{
            display: flex;
            gap: 10px;
            margin-bottom: 28px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            padding-bottom: 12px;
            overflow-x: auto;
        }}
        .tab-link {{
            padding: 12px 24px;
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.95rem;
            color: #a0aec0;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            transition: all 0.2s ease;
            white-space: nowrap;
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
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 24px;
        }}
        .card {{
            background: rgba(20, 20, 38, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.05);
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            display: flex;
            flex-direction: column;
            position: relative;
        }}
        .card:hover {{
            transform: translateY(-6px);
            border-color: rgba(3, 218, 198, 0.25);
            box-shadow: 0 12px 30px rgba(3, 218, 198, 0.15);
        }}
        
        .category-indicator {{
            position: absolute;
            top: 12px;
            left: 12px;
            background: rgba(98, 0, 238, 0.85);
            color: #fff;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
            z-index: 5;
        }}
        
        .card-image-container {{
            position: relative;
            width: 100%;
            padding-top: 56.25%;
            background-color: #0d0d18;
        }}
        .card-image {{
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            object-fit: cover;
        }}
        .card-duration {{
            position: absolute;
            bottom: 8px; right: 8px;
            background: rgba(0,0,0,0.8);
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
            font-size: 0.95rem;
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
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: 600;
        }}
        .badge-pending {{
            background: rgba(251, 191, 36, 0.1);
            color: #fbbf24;
        }}
        .badge-downloaded {{
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
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
        
        .btn {{
            padding: 8px 12px;
            border: none;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
        }}
        .btn-cart {{
            background: linear-gradient(135deg, #03dac6, #018786);
            color: #000;
            grid-column: span 2;
        }}
        .btn-cart:hover {{ opacity: 0.9; }}
        
        .btn-post {{
            background: linear-gradient(135deg, #10b981, #059669);
            color: #fff;
            grid-column: span 2;
        }}
        .btn-post:hover {{ opacity: 0.9; }}
        
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
            background: rgba(255,255,255,0.04);
            color: #e2e8f0;
            border: 1px solid rgba(255,255,255,0.06);
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
            grid-column: span 2;
        }}
        .no-results {{
            grid-column: 1 / -1;
            text-align: center;
            padding: 64px 32px;
            background: rgba(15, 15, 30, 0.4);
            border-radius: 12px;
            border: 1px dashed rgba(255,255,255,0.08);
        }}
        .no-results p {{ font-size: 1.1rem; color: #a0aec0; margin-bottom: 8px; }}
        .no-results .hint {{ font-size: 0.85rem; color: #718096; }}
        
        .admin-panel {{
            max-width: 900px;
            margin: 0 auto;
        }}
        .admin-card {{
            background: rgba(15, 15, 30, 0.7);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 12px;
            padding: 24px;
        }}
        .admin-card h3 {{
            font-size: 1.2rem;
            color: #bb86fc;
            margin-bottom: 8px;
        }}
        .admin-card .hint {{
            font-size: 0.85rem;
            color: #718096;
            margin-bottom: 16px;
        }}
        .form-row {{
            display: flex;
            gap: 12px;
        }}
        .form-row input[type="text"] {{
            flex-grow: 1;
            background: #0d0d1b;
            border: 1px solid rgba(255,255,255,0.1);
            padding: 12px;
            color: #fff;
            border-radius: 8px;
            font-size: 0.9rem;
        }}
        .form-row input[type="text"]:focus {{
            border-color: #bb86fc;
            outline: none;
        }}
        .channel-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            text-align: left;
        }}
        .channel-table th, .channel-table td {{
            padding: 12px 16px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }}
        .channel-table th {{
            color: #a0aec0;
            font-weight: 600;
        }}
        .empty-table {{
            text-align: center;
            color: #718096;
            padding: 32px !important;
        }}
        .ref-badge {{
            background: rgba(187, 134, 252, 0.15);
            color: #bb86fc;
            padding: 3px 8px;
            border-radius: 4px;
        }}
        .ref-empty {{
            color: #718096;
            font-style: italic;
        }}
        .btn-delete-channel {{
            background: transparent;
            color: #f43f5e;
            border: 1px solid rgba(244,63,94,0.3);
            padding: 4px 10px;
            border-radius: 4px;
            cursor: pointer;
            margin-left: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .btn-delete-channel:hover {{
            background: rgba(244,63,94,0.1);
        }}
        
        .tags-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 10px;
        }}
        .tag-box {{
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            padding: 8px 16px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .tag-delete-btn {{
            background: transparent;
            border: none;
            color: #a0aec0;
            font-size: 1.2rem;
            cursor: pointer;
            line-height: 1;
        }}
        .tag-delete-btn:hover {{
            color: #f43f5e;
        }}
        
        .modal {{
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.85);
            backdrop-filter: blur(8px);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }}
        .modal-content {{
            background: #0f0f20;
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
            background: #050510;
            border: 1px solid rgba(255,255,255,0.1);
            color: #fff;
            border-radius: 6px;
            margin-bottom: 16px;
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
            <p>Gerenciador de Mapeamentos & Fila de Downloads (Bilibili / Douyin)</p>
        </div>
        <div id="header-action-container" style="display: flex; gap: 12px; align-items: center;">
            <button class="btn-renew-session" onclick="renewSession()">🔄 Estender Sessão</button>
            {header_action_button}
        </div>
    </header>
    
    <main>
        <div class="context-row">
            <a href="{sublink_anime}" class="context-link {tab_anime_active}">🌸 Anime</a>
            <a href="{sublink_manhwa}" class="context-link {tab_manhwa_active}">🇰🇷 Manhwa</a>
        </div>

        <div class="tabs-row">
            <a href="{ROOT_PATH}/?tab=search&type={type}" class="tab-link {tab_search_active}">🔍 Busca Geral</a>
            <a href="{ROOT_PATH}/?tab=updates&type={type}" class="tab-link {tab_updates_active}">🔔 Atualizações Canais</a>
            <a href="{ROOT_PATH}/?tab=cart&type={type}" class="tab-link {tab_cart_active}">🛒 Carrinho / Fila</a>
            <a href="{ROOT_PATH}/?tab=channels&type={type}" class="tab-link {tab_channels_active}">👥 Gerenciar Canais</a>
            <a href="{ROOT_PATH}/?tab=terms&type={type}" class="tab-link {tab_terms_active}">🔑 Termos de Busca</a>
        </div>
        
        <div id="main-content">
            {content_html}
        </div>
    </main>
    
    <div id="douyinModal" class="modal">
        <div class="modal-content">
            <h3>🔗 Download via Link do Douyin</h3>
            <p>Cole abaixo o link do Douyin correspondente a este vídeo.</p>
            <input type="text" id="douyinUrlInput" placeholder="https://v.douyin.com/..." required>
            <input type="hidden" id="modalBvid">
            <input type="hidden" id="modalCategory">
            
            <div class="modal-buttons">
                <button class="modal-btn modal-btn-cancel" onclick="closeModal()">Cancelar</button>
                <button class="modal-btn modal-btn-send" onclick="submitDouyinDownload()">Enviar e Baixar</button>
            </div>
        </div>
    </div>
    
    <script>
        const ROOT_PATH = "{ROOT_PATH}";
        const ACTIVE_TYPE = "{type}";
        const ACTIVE_TAB = "{tab}";

        // Interceptor de fetch para tratar 401 Unauthorized globalmente
        const originalFetch = window.fetch;
        window.fetch = async function(...args) {{
            const response = await originalFetch(...args);
            if (response.status === 401) {{
                alert("Sessão expirada ou inválida! Por favor, gere um novo link de acesso no Telegram.");
                window.location.reload();
                return new Promise(() => {{}}); // Interrompe fluxos subsequentes
            }}
            return response;
        }};

        async function renewSession() {{
            const btn = document.querySelector('.btn-renew-session');
            if (!btn) return;
            const originalText = btn.textContent;
            btn.textContent = "⏳ Estendendo...";
            btn.disabled = true;
            try {{
                const response = await fetch(ROOT_PATH + '/api/session/renew', {{ method: 'POST' }});
                const data = await response.json();
                if (response.ok && data.ok) {{
                    btn.textContent = "✅ Sessão Estendida!";
                    btn.style.borderColor = "#10b981";
                    btn.style.color = "#10b981";
                    setTimeout(() => {{
                        btn.textContent = originalText;
                        btn.style.borderColor = "rgba(3, 218, 198, 0.25)";
                        btn.style.color = "#03dac6";
                        btn.disabled = false;
                    }}, 3000);
                }} else {{
                    alert("Erro ao estender sessão: " + (data.message || "Sessão inválida. Reabra pelo bot."));
                    window.location.reload();
                }}
            }} catch(e) {{
                alert("Erro ao estender sessão: " + e);
                btn.textContent = originalText;
                btn.disabled = false;
            }}
        }}

        async function addToCart(bvid, title, duration, type, pic, source) {{
            const formData = new FormData();
            formData.append('bvid', bvid);
            formData.append('title', title);
            formData.append('duration_seconds', duration);
            formData.append('content_type', type);
            formData.append('pic', pic);
            formData.append('source', source);

            try {{
                const response = await fetch(ROOT_PATH + '/api/cart/add', {{ method: 'POST', body: formData }});
                const data = await response.json();
                if (data.ok) {{
                    const card = document.getElementById('card-' + bvid);
                    if (card) {{
                        card.style.transition = 'all 0.4s ease';
                        card.style.opacity = '0';
                        card.style.transform = 'scale(0.8) translateY(20px)';
                        setTimeout(() => card.remove(), 400);
                    }}
                }} else {{
                    alert("Erro ao adicionar ao carrinho.");
                }}
            }} catch(e) {{
                alert("Erro na requisição: " + e);
            }}
        }}

        async function ignoreVideo(bvid, source) {{
            if (confirm("Deseja ocultar este vídeo da triagem?")) {{
                const formData = new FormData();
                formData.append('source', source);
                try {{
                    const response = await fetch(ROOT_PATH + '/api/ignore/' + bvid, {{ method: 'POST', body: formData }});
                    const data = await response.json();
                    if (data.ok) {{
                        const card = document.getElementById('card-' + bvid);
                        if (card) {{
                            card.style.transition = 'all 0.3s ease';
                            card.style.opacity = '0';
                            setTimeout(() => card.remove(), 300);
                        }}
                    }}
                }} catch(e) {{
                    alert("Erro ao ocultar: " + e);
                }}
            }}
        }}

        async function removeFromCart(bvid) {{
            if (confirm("Deseja remover este vídeo do carrinho?")) {{
                try {{
                    const response = await fetch(ROOT_PATH + '/api/cart/remove/' + bvid, {{ method: 'POST' }});
                    const data = await response.json();
                    if (data.ok) {{
                        const card = document.getElementById('card-' + bvid);
                        if (card) {{
                            card.style.transition = 'all 0.3s ease';
                            card.style.opacity = '0';
                            setTimeout(() => card.remove(), 300);
                        }}
                    }}
                }} catch(e) {{
                    alert("Erro ao remover: " + e);
                }}
            }}
        }}

        async function markAsPosted(bvid) {{
            try {{
                const response = await fetch(ROOT_PATH + '/api/cart/mark_posted/' + bvid, {{ method: 'POST' }});
                const data = await response.json();
                if (data.ok) {{
                    const card = document.getElementById('card-' + bvid);
                    if (card) {{
                        card.style.transition = 'all 0.3s ease';
                        card.style.opacity = '0';
                        setTimeout(() => card.remove(), 300);
                    }}
                }}
            }} catch(e) {{
                alert("Erro ao salvar status: " + e);
            }}
        }}

        async function syncSearch() {{
            const btn = document.querySelector('.btn-sync');
            btn.textContent = "⏳ Buscando...";
            btn.disabled = true;
            try {{
                const response = await fetch(ROOT_PATH + '/api/sync', {{ method: 'POST' }});
                const data = await response.json();
                alert(data.message);
                window.location.reload();
            }} catch(e) {{
                alert("Erro: " + e);
            }} finally {{
                btn.textContent = "🔄 Sincronizar Busca por Termos";
                btn.disabled = false;
            }}
        }}

        async function syncChannels(type) {{
            const btn = document.querySelector('.btn-sync');
            btn.textContent = "⏳ Rastreando...";
            btn.disabled = true;
            
            const formData = new FormData();
            formData.append('content_type', type);
            try {{
                const response = await fetch(ROOT_PATH + '/api/channels/sync', {{ method: 'POST', body: formData }});
                const data = await response.json();
                alert(data.message);
                window.location.reload();
            }} catch(e) {{
                alert("Erro: " + e);
            }} finally {{
                btn.textContent = "🔄 Mapear Postagens de Canais";
                btn.disabled = false;
            }}
        }}

        async function addChannel(e) {{
            e.preventDefault();
            const uid = document.getElementById('newChannelUid').value;
            const name = document.getElementById('newChannelName').value;
            const type = document.getElementById('newChannelType').value;
            
            const formData = new FormData();
            formData.append('uid', uid);
            formData.append('name', name);
            formData.append('content_type', type);

            try {{
                const response = await fetch(ROOT_PATH + '/api/channels/add', {{ method: 'POST', body: formData }});
                const data = await response.json();
                if (response.ok) {{
                    alert(data.message);
                    window.location.reload();
                }} else {{
                    alert("Erro: " + data.detail);
                }}
            }} catch(err) {{
                alert("Erro de requisição: " + err);
            }}
        }}

        async function deleteChannel(uid, name) {{
            if (confirm("Deseja realmente remover o canal '" + name + "'?")) {{
                try {{
                    const response = await fetch(ROOT_PATH + '/api/channels/delete/' + uid, {{ method: 'DELETE' }});
                    const data = await response.json();
                    if (data.ok) {{
                        document.getElementById('channel-row-' + uid).remove();
                    }}
                }} catch(e) {{
                    alert("Erro ao deletar: " + e);
                }}
            }}
        }}

        async function addTerm(e) {{
            e.preventDefault();
            const termText = document.getElementById('newTermText').value;
            const type = document.getElementById('newTermType').value;
            
            const formData = new FormData();
            formData.append('term', termText);
            formData.append('content_type', type);

            try {{
                const response = await fetch(ROOT_PATH + '/api/terms/add', {{ method: 'POST', body: formData }});
                const data = await response.json();
                if (data.ok) {{
                    window.location.reload();
                }} else {{
                    alert("Erro ao adicionar termo (pode ser duplicado).");
                }}
            }} catch(err) {{
                alert("Erro: " + err);
            }}
        }}

        async function deleteTerm(id, text) {{
            if (confirm("Deseja remover o termo '" + text + "'?")) {{
                try {{
                    const response = await fetch(ROOT_PATH + '/api/terms/delete/' + id, {{ method: 'DELETE' }});
                    const data = await response.json();
                    if (data.ok) {{
                        document.getElementById('tag-' + id).remove();
                    }}
                }} catch(e) {{
                    alert("Erro ao remover: " + e);
                }}
            }}
        }}

        async function downloadBilibili(bvid, category) {{
            updateCardToProcessing(bvid);

            const formData = new FormData();
            formData.append('bvid', bvid);
            formData.append('url', 'https://www.bilibili.com/video/' + bvid);
            formData.append('is_douyin', '0');
            formData.append('category', category);
            formData.append('content_type', ACTIVE_TYPE);

            try {{
                const response = await fetch(ROOT_PATH + '/api/download', {{ method: 'POST', body: formData }});
                const data = await response.json();
                if (data.ok) {{
                    console.log("Download do Bilibili iniciado em background para: " + bvid);
                }}
            }} catch(e) {{
                alert("Erro ao iniciar download: " + e);
                window.location.reload();
            }}
        }}

        function showDouyinModal(bvid, category) {{
            document.getElementById('modalBvid').value = bvid;
            document.getElementById('modalCategory').value = category;
            document.getElementById('douyinUrlInput').value = "";
            document.getElementById('douyinModal').style.display = 'flex';
        }}
        function closeModal() {{
            document.getElementById('douyinModal').style.display = 'none';
        }}

        async function submitDouyinDownload() {{
            const bvid = document.getElementById('modalBvid').value;
            const category = document.getElementById('modalCategory').value;
            const url = document.getElementById('douyinUrlInput').value.trim();
            
            if (!url) {{
                alert("Insira uma URL do Douyin.");
                return;
            }}

            closeModal();
            updateCardToProcessing(bvid);

            const formData = new FormData();
            formData.append('bvid', bvid);
            formData.append('url', url);
            formData.append('is_douyin', '1');
            formData.append('category', category);
            formData.append('content_type', ACTIVE_TYPE);

            try {{
                const response = await fetch(ROOT_PATH + '/api/download', {{ method: 'POST', body: formData }});
                const data = await response.json();
                if (data.ok) {{
                    console.log("Download do Douyin iniciado para: " + bvid);
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
                if (badgeRow) {{
                    badgeRow.innerHTML = '<span class="badge badge-processing">⚙️ Processando...</span><a href="https://www.bilibili.com/video/' + bvid + '" target="_blank" class="link-watch">🔗 Link Bilibili</a>';
                }}
                const actions = card.querySelector('.card-actions');
                if (actions) {{
                    actions.innerHTML = '<button class="btn btn-disabled" disabled>Aguarde...</button>';
                }}
            }}
        }}

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
                            if (ACTIVE_TAB === 'cart') {{
                                if (status === 'downloaded') {{
                                    const card = document.getElementById('card-' + bvid);
                                    if (card) {{
                                        const badgeRow = card.querySelector('.card-status-row');
                                        badgeRow.innerHTML = '<span class="badge badge-downloaded">🟢 Pronto no Drive</span><a href="https://www.bilibili.com/video/' + bvid + '" target="_blank" class="link-watch">🔗 Link Bilibili</a>';
                                        
                                        const actions = card.querySelector('.card-actions');
                                        actions.innerHTML = `
                                            <button class="btn btn-post" onclick="markAsPosted('` + bvid + `')">✅ Postado</button>
                                            <button class="btn btn-ignore" onclick="removeFromCart('` + bvid + `')">🗑️ Remover</button>
                                        `;
                                    }}
                                }} else if (status === 'pending') {{
                                    restoreCardToPendingCart(bvid);
                                }}
                            }} else {{
                                if (status === 'downloaded' || status === 'ignored' || status === 'in_cart') {{
                                    const card = document.getElementById('card-' + bvid);
                                    if (card) {{
                                        card.style.transition = 'all 0.5s ease';
                                        card.style.opacity = '0';
                                        setTimeout(() => card.remove(), 500);
                                    }}
                                }} else if (status === 'pending') {{
                                    restoreCardToPendingTriagem(bvid);
                                }}
                            }}
                        }}
                    }}
                }} catch (e) {{
                    console.error("Erro no polling de status:", e);
                }}
            }}, 3000);
        }}

        function restoreCardToPendingCart(bvid) {{
            const card = document.getElementById('card-' + bvid);
            if (card) {{
                const badgeRow = card.querySelector('.card-status-row');
                badgeRow.innerHTML = '<span class="badge badge-pending">🛒 No Carrinho</span><a href="https://www.bilibili.com/video/' + bvid + '" target="_blank" class="link-watch">🔗 Link Bilibili</a>';
                
                const indicator = card.querySelector('.category-indicator');
                const category = indicator.textContent.includes("Shorts") ? 'shorts' : 'longos';
                
                const actions = card.querySelector('.card-actions');
                actions.innerHTML = `
                    <button class="btn btn-bili" onclick="downloadBilibili('` + bvid + `', '` + category + `')">📥 Bilibili</button>
                    <button class="btn btn-douyin" onclick="showDouyinModal('` + bvid + `', '` + category + `')">🔗 Douyin</button>
                    <button class="btn btn-ignore" style="grid-column: span 2" onclick="removeFromCart('` + bvid + `')">🗑️ Remover</button>
                `;
            }}
        }}

        function restoreCardToPendingTriagem(bvid) {{
            const card = document.getElementById('card-' + bvid);
            if (card) {{
                const badgeRow = card.querySelector('.card-status-row');
                const badgeText = ACTIVE_TAB === 'updates' ? '🔔 Novo Post' : '⏳ Triagem';
                badgeRow.innerHTML = '<span class="badge badge-pending">' + badgeText + '</span><a href="https://www.bilibili.com/video/' + bvid + '" target="_blank" class="link-watch">🔗 Bilibili Link</a>';
                
                const actions = card.querySelector('.card-actions');
                const source = ACTIVE_TAB === 'updates' ? 'channel' : 'search';
                actions.innerHTML = `
                    <button class="btn btn-cart" onclick="addToCart('` + bvid + `', 'Video', 0, '` + ACTIVE_TYPE + `', '', '` + source + `')">🛒 Add ao Carrinho</button>
                    <button class="btn btn-ignore" onclick="ignoreVideo('` + bvid + `', '` + source + `')">🗑️ Ocultar</button>
                `;
            }}
        }}

        window.addEventListener('DOMContentLoaded', startProcessingPolling);
    </script>
</body>
</html>"""
    return html_content

def run_panel():
    import uvicorn
    database.init_db()
    print("Iniciando Painel Web de Triagem na porta 5556 (http://localhost:5556)...")
    uvicorn.run(app, host="0.0.0.0", port=5556, log_level="warning")
