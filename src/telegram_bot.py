import os
import re
import logging
import httpx
import asyncio
import time
import concurrent.futures
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from src import database, media_processor, drive_uploader
from src.config import DOUYIN_API_BASE

logger = logging.getLogger(__name__)

# Configurações do .env
AUTHORIZED_USERS = [
    u.strip() for u in os.getenv("AUTHORIZED_TELEGRAM_USERS", "").split(",") if u.strip()
]

# Diretório temporário para processamento de mídia
TEMP_DIR = os.path.join("data", "temp_media")

def is_authorized(update: Update) -> bool:
    """Verifica se o usuário é autorizado pelo ID de forma estrita."""
    user = update.effective_user
    if not user:
        return False
    return str(user.id) in AUTHORIZED_USERS

# Helper para obter o contexto ativo do usuário
def get_user_context(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, str]:
    """Retorna a categoria e o tipo ativo de conteúdo do usuário (padrão: shorts, anime)."""
    category = context.user_data.get("active_category", "shorts")
    content_type = context.user_data.get("active_content_type", "anime")
    return category, content_type

# Helper para limpar cache do Bot e da API do Evil0ctal
def deep_clean_cache():
    logger.info("Iniciando limpeza física profunda de mídias temporárias e caches...")
    
    # 1. Limpa data/temp_media/
    if os.path.exists(TEMP_DIR):
        for f in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, f)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Removido temp local: {file_path}")
                except Exception as e:
                    logger.warning(f"Erro ao remover temp local {file_path}: {e}")
                    
    # 2. Limpa cache de download da API local do Evil0ctal
    api_dirs = [
        os.path.join("douyin_api", "download", "bilibili_video"),
        os.path.join("douyin_api", "download", "douyin_video")
    ]
    for d in api_dirs:
        if os.path.exists(d):
            for f in os.listdir(d):
                file_path = os.path.join(d, f)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        logger.info(f"Removido cache API local: {file_path}")
                    except Exception as e:
                        logger.warning(f"Erro ao remover cache API {file_path}: {e}")

# ----------------- PIPELINE CENTRALIZADO DE DOWNLOAD -----------------

async def run_download_pipeline(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    is_douyin: bool,
    category: str,
    content_type: str,
    bvid: str = None,
    custom_title: str = None
) -> bool:
    """Executa o download de forma síncrona dentro de um job assíncrono para atualizar o bot do Telegram."""
    cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
    type_title = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
    
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📥 **Iniciando Download Pipeline...**\n"
             f"📋 **Contexto:** {cat_title} - {type_title}\n"
             f"🔗 **URL:** {url}\n"
             f"⏳ Conectando à API em {DOUYIN_API_BASE}...",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    temp_video_path = os.path.join(TEMP_DIR, "temp_download_original.mp4")
    
    # Limpa arquivos temporários antigos se houver
    if os.path.exists(temp_video_path):
        try: os.remove(temp_video_path)
        except: pass
        
    api_download_url = f"{DOUYIN_API_BASE}/api/download"
    download_success = False
    
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("GET", api_download_url, params={"url": url, "with_watermark": "false"}) as r:
                content_type = r.headers.get("Content-Type", "")
                if r.status_code == 200 and "application/json" not in content_type:
                    total_size = int(r.headers.get("Content-Length", 0))
                    downloaded = 0
                    last_update = 0.0
                    last_percent = 0
                    
                    with open(temp_video_path, "wb") as f:
                        async for chunk in r.aiter_bytes():
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = int((downloaded / total_size) * 100)
                                now = time.time()
                                if (percent - last_percent >= 20) or (now - last_update >= 10.0) or (percent == 100):
                                    last_percent = percent
                                    last_update = now
                                    try:
                                        await status_msg.edit_text(
                                            f"📥 **Baixando vídeo...**\n"
                                            f"📋 **Contexto:** {cat_title} - {type_title}\n"
                                            f"⏳ Progresso: **{percent}%** ({downloaded/(1024*1024):.1f}MB / {total_size/(1024*1024):.1f}MB)...",
                                            parse_mode="Markdown"
                                        )
                                    except: pass
                    download_success = os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) > 0
                else:
                    # Falha na API ou retorno de erro JSON
                    await r.aread()
                    try:
                        err_data = r.json()
                        err_msg = err_data.get("message", "Erro interno na API de Download")
                    except Exception:
                        err_msg = f"HTTP {r.status_code}: {r.text[:200]}"
                    
                    logger.error(f"Erro no download pela API local (bot) para {url}: {err_msg}")
                    await status_msg.edit_text(f"❌ **Falha ao realizar download** pela API local:\n`{err_msg}`", parse_mode="Markdown")
                    return False
    except Exception as e:
        logger.error(f"Exceção ao baixar vídeo da API: {e}")
        await status_msg.edit_text(f"❌ **Exceção no download** pela API local:\n`{str(e)}`", parse_mode="Markdown")
        return False
        
    if not download_success:
        await status_msg.edit_text("❌ **Falha ao realizar download** do vídeo pela API local. Verifique se a API está ativa.", parse_mode="Markdown")
        return False
        
    await status_msg.edit_text("✂️ **Vídeo baixado!** Executando processamento de mídia (FFmpeg duration/audio/cut)...", parse_mode="Markdown")
    
    final_video_path, final_audio_path, proc_success = media_processor.process_media_for_pipeline(
        temp_video_path, TEMP_DIR, category
    )
    
    if not proc_success:
        await status_msg.edit_text("❌ **Falha no processamento** do vídeo/áudio usando FFmpeg.", parse_mode="Markdown")
        try: os.remove(temp_video_path)
        except: pass
        return False
        
    await status_msg.edit_text("📤 **Mídia processada!** Iniciando upload para o Google Drive...", parse_mode="Markdown")
    
    loop = asyncio.get_running_loop()
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
            
            text = (
                f"📤 **Mídia processada!**\n"
                f"📋 **Contexto:** {cat_title} - {type_title}\n"
                f"⏳ Subindo **{file_type}** para o Google Drive: **{percent}%**..."
            )
            asyncio.run_coroutine_threadsafe(
                status_msg.edit_text(text, parse_mode="Markdown"),
                loop
            )
            
    with concurrent.futures.ThreadPoolExecutor() as executor:
        drive_success = await loop.run_in_executor(
            executor,
            drive_uploader.upload_pipeline_media,
            final_video_path,
            final_audio_path,
            drive_progress
        )
        
    if not drive_success:
        await status_msg.edit_text("❌ **Falha ao realizar o upload** para o Google Drive.", parse_mode="Markdown")
        for p in [temp_video_path, final_video_path, final_audio_path]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except: pass
        return False
        
    # Salva no banco de dados SQLite
    target_bvid = bvid or f"manual_{int(time.time())}"
    title_reg = custom_title or f"Download manual: {url[:30]}..."
    
    database.register_video(
        bvid=target_bvid,
        title=title_reg,
        source="channel" if bvid else "manual",
        category=category,
        content_type=content_type,
        status="downloaded"
    )
    
    success_text = (
        f"✅ **Sucesso! Vídeo enviado ao Drive!**\n\n"
        f"📝 **Título:** {title_reg}\n"
        f"📂 **Arquivos Enviados:**\n"
        f"├ 🎵 `KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3`\n"
        f"└ 🎥 `KAGGLE/PIPELINE/ATIVO/video_original.mp4`\n\n"
        f"O vídeo foi colocado na fila **Próximo a Postar**!"
    )
    await status_msg.edit_text(success_text, parse_mode="Markdown")
    
    # Se for Shorts e < 50MB, envia de volta no Telegram como prévia
    if category.lower() == "shorts" and os.path.exists(final_video_path):
        file_size_mb = os.path.getsize(final_video_path) / (1024 * 1024)
        if file_size_mb < 49.0:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="upload_video")
                with open(final_video_path, "rb") as video_file:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption="🎬 **Prévia do vídeo enviado ao Drive** (Sem marca d'água)"
                    )
            except Exception as ev:
                logger.warning(f"Erro ao enviar prévia do vídeo: {ev}")
                
    # Limpeza física de arquivos temporários e do cache do Evil0ctal
    deep_clean_cache()
    
    return True

# ----------------- MENUS INLINE -----------------

def get_main_menu_keyboard():
    """Gera o teclado do menu principal."""
    keyboard = [
        [InlineKeyboardButton("📱 Mapeamento Shorts", callback_data="menu:shorts")],
        [InlineKeyboardButton("🎬 Mapeamento Vídeos Longos", callback_data="menu:longos")],
        [InlineKeyboardButton("📋 Fila 'Próximo a Postar'", callback_data="menu_queue:select")],
        [InlineKeyboardButton("🌐 Triagem de Busca Web", callback_data="menu:search_web")],
        [InlineKeyboardButton("⚙️ Configurações / Status", callback_data="menu:config")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_type_menu_keyboard(category):
    """Gera o teclado para selecionar Anime ou Manhwa."""
    keyboard = [
        [
            InlineKeyboardButton("🌸 Anime", callback_data=f"submenu:{category}:anime"),
            InlineKeyboardButton("🇰🇷 Manhwa", callback_data=f"submenu:{category}:manhwa"),
        ],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_panel_keyboard(category, content_type):
    """Gera o teclado do painel de controle do canal."""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Mapear Novos Vídeos", callback_data=f"map:{category}:{content_type}"),
            InlineKeyboardButton("📋 Listar Canais", callback_data=f"list_ch:{category}:{content_type}"),
        ],
        [
            InlineKeyboardButton("➕ Adicionar Canal", callback_data=f"add_ch_prompt:{category}:{content_type}"),
            InlineKeyboardButton("❌ Remover Canal", callback_data=f"del_ch_list:{category}:{content_type}"),
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data=f"menu:{category}")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_queue_category_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📱 Shorts", callback_data="queue_cat:shorts"),
            InlineKeyboardButton("🎬 Vídeos Longos", callback_data="queue_cat:longos"),
        ],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_queue_type_keyboard(category):
    keyboard = [
        [
            InlineKeyboardButton("🌸 Anime", callback_data=f"queue_type:{category}:anime"),
            InlineKeyboardButton("🇰🇷 Manhwa", callback_data=f"queue_type:{category}:manhwa"),
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_queue:select")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ----------------- COMANDOS DO BOT -----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o bot e apresenta o menu principal."""
    if not is_authorized(update):
        await update.message.reply_text("Desculpe, você não está autorizado a usar este bot.")
        return

    context.user_data["active_category"] = "shorts"
    context.user_data["active_content_type"] = "anime"
    
    text = (
        "👋 **Bem-vindo ao Scrapper Douyin/Bilibili Bot!**\n\n"
        "💡 **Como usar:** Envie diretamente qualquer link do **Douyin** ou **Bilibili** no chat a qualquer momento "
        "para baixar sem marca d'água, cortar automaticamente (se Shorts > 3min) e enviar direto para o seu Google Drive!\n\n"
        "Selecione uma opção abaixo para navegar:"
    )
    await update.message.reply_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra ajuda básica."""
    if not is_authorized(update): return
    help_text = (
        "📖 **Como usar o Bot:**\n\n"
        "1. Selecione a categoria no menu principal para configurar o contexto.\n"
        "2. Cadastre perfis do Bilibili usando a opção de adicionar canal.\n"
        "3. Clique em **Mapear Novos Vídeos** para mapear posts de canais cadastrados.\n"
        "4. Acesse a fila **Próximo a Postar** para ver todos os posts não publicados (inclusive mapeados pendentes).\n"
        "5. Pela própria Fila, baixe do Bilibili ou envie o link correspondente do Douyin."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ----------------- FILA "PRÓXIMO A POSTAR" -----------------

async def show_queue_list(message, context, category, content_type):
    posted_7d = database.get_posted_videos_count_since(7)
    since_last = database.get_downloaded_count_since_last_post(category, content_type)
    
    cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
    type_title = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
    
    header_text = (
        f"📋 **Fila 'Próximo a Postar' — {cat_title} - {type_title}**\n\n"
        f"📊 **Estatísticas de Postagem:**\n"
        f"├ 📅 Vídeos publicados nos últimos 7 dias: **{posted_7d}**\n"
        f"└ 📥 Baixados desde sua última publicação: **{since_last}**\n\n"
        f"Abaixo estão os vídeos mapeados (pendentes de download ou prontos no Drive)."
    )
    
    await message.reply_text(header_text, parse_mode="Markdown")
    
    # Busca todos os vídeos não postados (pending e downloaded)
    unposted_items = database.get_unposted_videos(category, content_type)
    
    if not unposted_items:
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_queue:select")]]
        await message.reply_text(
            "📭 Nenhum vídeo mapeado ou pendente de postagem nesta categoria.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
        
    for item in unposted_items:
        origin_label = "👤 Criador"
        if item.get("source") == "search":
            origin_label = "🔍 Busca Geral"
        elif item.get("source") == "manual":
            origin_label = "✍️ Manual"
            
        channel_info = f" ({item['channel_name']})" if item.get("channel_name") else ""
        
        # Formata o status visual do item
        if item["status"] == "downloaded":
            status_visual = "🟢 **[PRONTO NO DRIVE]** (Aguardando Publicação)"
            keyboard = [
                [
                    InlineKeyboardButton("✅ Marcar como Postado", callback_data=f"post:{item['bvid']}:{category}:{content_type}"),
                    InlineKeyboardButton("❌ Remover da Fila", callback_data=f"remove_q:{item['bvid']}:{category}:{content_type}")
                ]
            ]
        else:
            status_visual = "⏳ **[APENAS MAPEADO]** (Aguardando Download)"
            keyboard = [
                [
                    InlineKeyboardButton("📥 Baixar Bilibili", callback_data=f"dl_bili:{item['bvid']}:{category}:{content_type}"),
                    InlineKeyboardButton("🔗 Enviar Link Douyin", callback_data=f"dl_douyin_prompt:{item['bvid']}:{category}:{content_type}")
                ],
                [
                    InlineKeyboardButton("❌ Descartar", callback_data=f"discard:{item['bvid']}:{category}:{content_type}")
                ]
            ]
            
        card_text = (
            f"{status_visual}\n\n"
            f"🎥 **{item['title']}**\n"
            f"├ 🔗 BVID: `{item['bvid']}`\n"
            f"├ 📁 Origem: {origin_label}{channel_info}\n"
            f"└ 🕒 Mapeado em: {item['created_at']}\n\n"
            f"🔗 [Ver no Bilibili](https://www.bilibili.com/video/{item['bvid']})"
        )
        
        await message.reply_text(
            card_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        
    keyboard = [
        [InlineKeyboardButton("🌐 Visualizar Triagem de Busca Web", callback_data="menu:search_web")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu da Fila", callback_data="menu_queue:select")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")]
    ]
    await message.reply_text("Fim da Fila.", reply_markup=InlineKeyboardMarkup(keyboard))

# ----------------- TRATAMENTO DE CALLBACKS (BOTÕES INLINE) -----------------

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa cliques nos botões inline do menu."""
    query = update.callback_query
    await query.answer()
    
    if not is_authorized(update):
        await query.message.reply_text("Você não está autorizado.")
        return

    data = query.data
    logger.info(f"Callback recebido: {data}")

    # Cancela qualquer estado de digitação pendente ao navegar
    context.user_data.pop("waiting_for_channel_uid", None)
    context.user_data.pop("waiting_for_douyin_url", None)
    context.user_data.pop("waiting_for_search_term", None)

    # Menu Principal
    if data == "main_menu":
        await query.edit_message_text(
            "Selecione uma categoria de gerenciamento abaixo:",
            reply_markup=get_main_menu_keyboard(),
        )
        
    # Categoria selecionada
    elif data.startswith("menu:"):
        category = data.split(":")[1]
        
        # Direciona para a triagem web
        if category == "search_web":
            text = (
                "🌐 **Painel de Triagem Web**\n\n"
                "O painel web permite triar a busca geral de forma visual, com capas e pontuações de Hype!\n\n"
                "👉 Acesse o painel pelo seu navegador local:\n"
                "🔗 http://localhost:5556\n\n"
                "💡 **Dica:** Os vídeos baixados pelo painel web também aparecerão na fila **Próximo a Postar** do seu Telegram bot!"
            )
            keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        context.user_data["active_category"] = category
        cat_text = "📱 Shorts (Reels/TikTok)" if category == "shorts" else "🎬 Vídeos Longos"
        await query.edit_message_text(
            f"Selecione o tipo de conteúdo para **{cat_text}**:",
            reply_markup=get_type_menu_keyboard(category),
            parse_mode="Markdown"
        )
        
    # Tipo de Conteúdo selecionado
    elif data.startswith("submenu:"):
        _, category, content_type = data.split(":")
        context.user_data["active_category"] = category
        context.user_data["active_content_type"] = content_type
        
        cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
        type_title = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
        
        await query.edit_message_text(
            f"📂 **Painel: {cat_title} - {type_title}**\n\n"
            f"Gerencie os canais cadastrados ou mapeie novas postagens recentes no Bilibili.",
            reply_markup=get_panel_keyboard(category, content_type),
            parse_mode="Markdown"
        )
        
    # Listar Canais Mapeados
    elif data.startswith("list_ch:"):
        _, category, content_type = data.split(":")
        channels = database.get_channels(category, content_type)
        cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
        type_title = "Anime" if content_type == "anime" else "Manhwa"
        
        if not channels:
            text = f"📭 Nenhum canal do Bilibili cadastrado em **{cat_title} - {type_title}**."
        else:
            text = f"📋 **Canais cadastrados ({cat_title} - {type_title}):**\n\n"
            for c in channels:
                text += f"👤 **{c['name']}**\n└ UID: `{c['uid']}`\n\n"
                
        keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data=f"submenu:{category}:{content_type}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Prompt para Adicionar Canal
    elif data.startswith("add_ch_prompt:"):
        _, category, content_type = data.split(":")
        context.user_data["waiting_for_channel_uid"] = (category, content_type)
        
        text = (
            "➕ **Adicionar Canal do Bilibili**\n\n"
            "Envie no chat o UID do canal e o nome do canal separados por hífen.\n"
            "Exemplo:\n"
            "`178360345 - Nome do Criador`\n\n"
            "O UID é o número presente no link do perfil (ex: `space.bilibili.com/178360345`)."
        )
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data=f"submenu:{category}:{content_type}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Listar Canais para Remover
    elif data.startswith("del_ch_list:"):
        _, category, content_type = data.split(":")
        channels = database.get_channels(category, content_type)
        
        if not channels:
            keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data=f"submenu:{category}:{content_type}")]]
            await query.edit_message_text("Nenhum canal cadastrado para remover.", reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        text = "❌ **Selecione o canal que deseja remover:**"
        keyboard = []
        for c in channels:
            keyboard.append([InlineKeyboardButton(f"❌ {c['name']} (UID: {c['uid']})", callback_data=f"del_ch_exec:{category}:{content_type}:{c['uid']}")])
        keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"submenu:{category}:{content_type}")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Executar Remoção de Canal
    elif data.startswith("del_ch_exec:"):
        _, category, content_type, uid = data.split(":")
        success = database.remove_channel(uid)
        
        text = "✅ Canal removido com sucesso!" if success else "❌ Falha ao remover o canal."
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data=f"submenu:{category}:{content_type}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # Mapear e Buscar Novos Vídeos do Bilibili (Apenas Notifica)
    elif data.startswith("map:"):
        _, category, content_type = data.split(":")
        channels = database.get_channels(category, content_type)
        
        if not channels:
            keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data=f"submenu:{category}:{content_type}")]]
            await query.edit_message_text("Nenhum canal cadastrado para mapear. Cadastre canais primeiro.", reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        await query.edit_message_text("🔄 Buscando vídeos recentes dos canais no Bilibili... Por favor, aguarde.")
        
        new_videos_found = []
        api_url = f"{DOUYIN_API_BASE}/api/bilibili/web/fetch_user_post_videos"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for ch in channels:
                try:
                    logger.info(f"Mapeando canal: {ch['name']} (UID: {ch['uid']})")
                    response = await client.get(api_url, params={"uid": ch["uid"], "pn": 1})
                    
                    if response.status_code != 200:
                        logger.error(f"Erro HTTP {response.status_code} para UID {ch['uid']}")
                        continue
                        
                    res_json = response.json()
                    if res_json.get("code") != 200:
                        continue
                        
                    vlist = res_json.get("data", {}).get("list", {}).get("vlist", [])
                    
                    for video in vlist[:5]:
                        bvid = video.get("bvid")
                        title = video.get("title")
                        created_ts = video.get("created")
                        
                        if not bvid or not title: continue
                        
                        # Se não foi processado/notificado ainda
                        if not database.is_video_processed(bvid):
                            pub_date = None
                            if created_ts:
                                try:
                                    pub_date = datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M:%S")
                                except:
                                    pass
                                    
                            new_videos_found.append(title)
                            
                            # Registra no SQLite com status='pending'
                            database.register_video(
                                bvid=bvid,
                                title=title,
                                channel_uid=ch["uid"],
                                source="channel",
                                category=category,
                                content_type=content_type,
                                status="pending",
                                published_at=pub_date
                            )
                except Exception as e:
                    logger.error(f"Erro ao mapear canal {ch['name']}: {e}")
                    continue
                    
        cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
        type_title = "Anime" if content_type == "anime" else "Manhwa"
        
        if not new_videos_found:
            text = f"✅ **Tudo atualizado!** Nenhum vídeo novo encontrado nos canais de **{cat_title} - {type_title}**."
        else:
            text = (
                f"✨ **Mapeamento concluído com sucesso!**\n\n"
                f"Foram identificados **{len(new_videos_found)}** novos vídeos nos canais de **{cat_title} - {type_title}**.\n\n"
                f"📋 Eles já foram adicionados na fila **Próximo a Postar**! Vá até o menu correspondente para baixá-los."
            )
            
        keyboard = [
            [InlineKeyboardButton("📋 Ir para a Fila", callback_data=f"queue_type:{category}:{content_type}")],
            [InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data=f"submenu:{category}:{content_type}")]
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Configurações / Status
    elif data == "menu:config":
        api_status = "🔴 Offline"
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{DOUYIN_API_BASE}/docs")
                if res.status_code == 200:
                    api_status = "🟢 Online"
        except:
            pass
            
        text = (
            "⚙️ **Painel de Configurações e Status**\n\n"
            f"🔌 **API Evil0ctal:** {api_status} ({DOUYIN_API_BASE})\n"
            f"📁 **Diretório Temp:** `{TEMP_DIR}`\n\n"
            "Selecione uma opção de manutenção ou gerencie os termos de busca:"
        )
        keyboard = [
            [InlineKeyboardButton("🔍 Termos de Busca (Anime/Manhwa)", callback_data="menu:search_terms")],
            [InlineKeyboardButton("🧹 Limpar Arquivos Físicos e Cache", callback_data="config_clear_cache")],
            [InlineKeyboardButton("❌ Limpar Banco de Dados (Limpar Tudo)", callback_data="config_clear_db")],
            [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "config_clear_cache":
        deep_clean_cache()
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu:config")]]
        await query.edit_message_text("✅ Caches físicos e diretório temporário apagados com sucesso!", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "config_clear_db":
        success = database.clean_database()
        text = "✅ Banco de dados limpo com sucesso!" if success else "❌ Falha ao limpar o banco de dados."
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu:config")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # ─── GERENCIAMENTO DE TERMOS DE BUSCA ───
    elif data == "menu:search_terms":
        anime_terms = database.get_search_terms("anime")
        manhwa_terms = database.get_search_terms("manhwa")
        
        anime_list = "\n".join(f"• `{t['term']}`" for t in anime_terms) if anime_terms else "_Nenhum termo cadastrado_"
        manhwa_list = "\n".join(f"• `{t['term']}`" for t in manhwa_terms) if manhwa_terms else "_Nenhum termo cadastrado_"
        
        text = (
            "🔍 **Gerenciamento de Termos de Busca**\n\n"
            "Aqui estão os termos cadastrados para a triagem automatizada no Bilibili:\n\n"
            f"🌸 **Anime:**\n{anime_list}\n\n"
            f"🇰🇷 **Manhwa:**\n{manhwa_list}\n\n"
            "Selecione uma opção abaixo para gerenciar:"
        )
        keyboard = [
            [
                InlineKeyboardButton("➕ Add Anime", callback_data="add_term_prompt:anime"),
                InlineKeyboardButton("➕ Add Manhwa", callback_data="add_term_prompt:manhwa")
            ],
            [
                InlineKeyboardButton("❌ Del Anime", callback_data="del_term_list:anime"),
                InlineKeyboardButton("❌ Del Manhwa", callback_data="del_term_list:manhwa")
            ],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu:config")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("add_term_prompt:"):
        content_type = data.split(":")[1]
        context.user_data["waiting_for_search_term"] = content_type
        
        type_label = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
        
        text = (
            f"➕ **Adicionar Termo de Busca - {type_label}**\n\n"
            "Envie agora no chat o termo que deseja adicionar à busca do Bilibili.\n"
            "Exemplo:\n`韩漫解说` ou o nome de um anime em chinês."
        )
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="menu:search_terms")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("del_term_list:"):
        content_type = data.split(":")[1]
        terms = database.get_search_terms(content_type)
        
        type_label = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
        
        if not terms:
            keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu:search_terms")]]
            await query.edit_message_text(f"Não há termos de busca cadastrados para {type_label} para remover.", reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        text = f"❌ **Selecione o termo de {type_label} que deseja remover:**"
        keyboard = []
        for t in terms:
            keyboard.append([InlineKeyboardButton(f"❌ {t['term']}", callback_data=f"del_term_exec:{content_type}:{t['id']}")])
        keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu:search_terms")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("del_term_exec:"):
        _, content_type, term_id = data.split(":")
        success = database.remove_search_term(int(term_id))
        
        text = "✅ Termo de busca removido com sucesso!" if success else "❌ Falha ao remover o termo de busca."
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu:search_terms")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # Callbacks da fila "Próximo a Postar"
    elif data == "menu_queue:select":
        await query.edit_message_text(
            "📋 **Fila 'Próximo a Postar'**\n\nSelecione a categoria de visualização:",
            reply_markup=get_queue_category_keyboard(),
            parse_mode="Markdown"
        )

    elif data.startswith("queue_cat:"):
        category = data.split(":")[1]
        await query.edit_message_text(
            "Selecione o tipo de conteúdo para a Fila:",
            reply_markup=get_queue_type_keyboard(category),
            parse_mode="Markdown"
        )

    elif data.startswith("queue_type:"):
        _, category, content_type = data.split(":")
        await query.edit_message_text("🔄 Carregando fila de postagem... Por favor, aguarde.")
        await show_queue_list(query.message, context, category, content_type)

    # Ações da fila (Marcar como Postado)
    elif data.startswith("post:"):
        _, bvid, category, content_type = data.split(":")
        success = database.mark_video_as_posted(bvid)
        if success:
            await query.edit_message_text("✅ Vídeo marcado como publicado e removido da fila!")
        else:
            await query.edit_message_text("❌ Falha ao atualizar o status do vídeo no banco.")

    # Ações da fila (Remover/Descartar da fila)
    elif data.startswith("remove_q:") or data.startswith("discard:"):
        _, bvid, category, content_type = data.split(":")
        success = database.remove_video_from_queue(bvid)
        if success:
            await query.edit_message_text("❌ Vídeo removido/descartado com sucesso da fila!")
        else:
            await query.edit_message_text("❌ Falha ao remover o vídeo do banco.")

    # Download direto do Bilibili na fila
    elif data.startswith("dl_bili:"):
        _, bvid, category, content_type = data.split(":")
        url = f"https://www.bilibili.com/video/{bvid}"
        
        await query.edit_message_text("📥 Download do Bilibili iniciado! Aguarde o processamento...")
        
        asyncio.create_task(
            run_download_pipeline(
                chat_id=query.message.chat_id,
                context=context,
                url=url,
                is_douyin=False,
                category=category,
                content_type=content_type,
                bvid=bvid,
                custom_title=f"Mapeado: {bvid}"
            )
        )
        
    # Solicitar link Douyin na fila
    elif data.startswith("dl_douyin_prompt:"):
        _, bvid, category, content_type = data.split(":")
        context.user_data["waiting_for_douyin_url"] = (bvid, category, content_type)
        
        await query.edit_message_text(
            f"🔗 **Enviar Link Douyin para BVID `{bvid}`**\n\n"
            f"Envie agora no chat o link do Douyin sem marca d'água correspondente a este vídeo."
        )

# ----------------- TRATAMENTO DE MENSAGENS DE TEXTO -----------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trata mensagens de texto enviadas no chat (links ou cadastro de canais)."""
    if not is_authorized(update):
        await update.message.reply_text("Desculpe, você não está autorizado a usar este bot.")
        return

    text = update.message.text.strip()
    logger.info(f"Mensagem recebida: {text}")

    # 0. Adicionar termo de busca
    if "waiting_for_search_term" in context.user_data:
        content_type = context.user_data["waiting_for_search_term"]
        term = text.strip()
        
        success = database.add_search_term(term, content_type)
        context.user_data.pop("waiting_for_search_term", None)
        
        keyboard = [[InlineKeyboardButton("⬅️ Voltar aos Termos", callback_data="menu:search_terms")]]
        if success:
            await update.message.reply_text(
                f"✅ Termo de busca **{term}** adicionado com sucesso para **{content_type}**!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                f"❌ Erro ao adicionar o termo de busca (ou o termo já existe).",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    # 1. Cadastro de canal
    if "waiting_for_channel_uid" in context.user_data:
        category, content_type = context.user_data["waiting_for_channel_uid"]
        
        match = re.match(r"^(\d+)\s*-\s*(.+)$", text)
        if match:
            uid = match.group(1).strip()
            name = match.group(2).strip()
            success = database.add_channel(uid, name, category, content_type)
            
            context.user_data.pop("waiting_for_channel_uid", None)
            
            keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data=f"submenu:{category}:{content_type}")]]
            if success:
                await update.message.reply_text(f"✅ Canal **{name}** (UID: {uid}) adicionado com sucesso!", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text("❌ Erro ao salvar o canal no banco de dados.", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(
                "⚠️ Formato inválido! Envie no formato:\n"
                "`UID - Nome do Criador`\n\n"
                "Exemplo:\n`178360345 - Azulsolitan`"
            )
        return

    # 2. Upload associado ao Douyin sob demanda
    if "waiting_for_douyin_url" in context.user_data:
        bvid, category, content_type = context.user_data["waiting_for_douyin_url"]
        
        douyin_match = re.search(r"(https?://\S*douyin\.com\S*)", text)
        if not douyin_match:
            await update.message.reply_text(
                "⚠️ Link do Douyin inválido! Por favor, envie um link válido do Douyin para associar a este vídeo."
            )
            return
            
        url = douyin_match.group(1)
        context.user_data.pop("waiting_for_douyin_url", None)
        
        await update.message.reply_text("✅ Link do Douyin recebido! Iniciando pipeline de download...")
        
        asyncio.create_task(
            run_download_pipeline(
                chat_id=update.effective_chat.id,
                context=context,
                url=url,
                is_douyin=True,
                category=category,
                content_type=content_type,
                bvid=bvid,
                custom_title=f"Douyin associado ao BVID: {bvid}"
            )
        )
        return

    # 3. Downloads manuais avulsos
    douyin_match = re.search(r"(https?://\S*douyin\.com\S*)", text)
    bilibili_match = re.search(r"(https?://\S*(bilibili\.com|b23\.tv)\S*)", text)
    
    if douyin_match or bilibili_match:
        url = (douyin_match or bilibili_match).group(1)
        category, content_type = get_user_context(context)
        is_douyin = bool(douyin_match)
        
        asyncio.create_task(
            run_download_pipeline(
                chat_id=update.effective_chat.id,
                context=context,
                url=url,
                is_douyin=is_douyin,
                category=category,
                content_type=content_type,
                bvid=f"manual_{int(time.time())}",
                custom_title=f"Manual: {url[:30]}..."
            )
        )
        return

    await update.message.reply_text(
        "❓ Comando ou link não reconhecido. Envie um link válido do Douyin ou Bilibili, "
        "ou utilize o menu abaixo para navegar pelas opções.",
        reply_markup=get_main_menu_keyboard()
    )

# ----------------- INICIALIZAÇÃO DO BOT -----------------

def run_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERRO: TELEGRAM_BOT_TOKEN não configurado no arquivo .env!")
        return
        
    database.init_db()
    
    app = ApplicationBuilder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Iniciando Bot de Download do Douyin/Bilibili...")
    app.run_polling()
