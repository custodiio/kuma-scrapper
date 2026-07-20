import os
import re
import sys
import time
import httpx
import logging
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, Form, HTTPException, Request, Response, Cookie, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from src import (
    database, search_scrapper, media_processor, drive_uploader,
    douyin_collection_scraper, episode_scheduler, douyin_profile_scraper, pipeline_integrator
)
from src.config import DOUYIN_API_BASE

logger = logging.getLogger(__name__)

ROOT_PATH = os.getenv("ROOT_PATH", "/scrapper")

app = FastAPI(title="Douyin Scrapper & Vitrine", docs_url=None, redoc_url=None)

# --- ROTAS DE API PARA COLEÇÕES, PERFIS E CONFIGURAÇÕES ---

@app.get("/api/douyin/collections")
@app.get("/scrapper/api/douyin/collections")
async def get_douyin_collections_api():
    cols = database.get_douyin_collections()
    daily_rate = episode_scheduler.get_daily_post_rate()
    times = episode_scheduler.get_autopost_times()
    return {"ok": True, "collections": cols, "daily_post_rate": daily_rate, "times": times}

@app.get("/api/douyin/collections/{mix_id}")
@app.get("/scrapper/api/douyin/collections/{mix_id}")
async def get_douyin_collection_detail_api(mix_id: str):
    col = database.get_douyin_collection_by_id(mix_id)
    if not col:
        raise HTTPException(status_code=404, detail="Coleção não encontrada.")
    eps = database.get_collection_episodes(mix_id)
    return {"ok": True, "collection": col, "episodes": eps}

@app.post("/api/douyin/collections/add")
@app.post("/scrapper/api/douyin/collections/add")
async def add_douyin_collection_api(
    url: str = Form(...),
    title_pt: str = Form(None),
    autoposting: int = Form(1)
):
    autoposting_bool = bool(autoposting)
    res = douyin_collection_scraper.fetch_and_store_collection(url, title_pt, autoposting_bool)
    return res

@app.post("/api/douyin/collections/{mix_id}/toggle-autoposting")
@app.post("/scrapper/api/douyin/collections/{mix_id}/toggle-autoposting")
async def toggle_autoposting_api(mix_id: str):
    success = database.toggle_collection_autoposting(mix_id)
    col = database.get_douyin_collection_by_id(mix_id)
    return {"ok": success, "autoposting": col["autoposting"] if col else 0}

@app.post("/api/douyin/collections/{mix_id}/delete")
@app.post("/scrapper/api/douyin/collections/{mix_id}/delete")
async def delete_collection_api(mix_id: str):
    success = database.delete_douyin_collection(mix_id)
    return {"ok": success}

@app.post("/api/douyin/episodes/{ep_id}/action")
@app.post("/scrapper/api/douyin/episodes/{ep_id}/action")
async def apply_episode_action_api(ep_id: int, action: str = Form(...)):
    res = episode_scheduler.apply_episode_action(ep_id, action)
    return res

@app.post("/api/douyin/settings/daily-post-rate")
@app.post("/scrapper/api/douyin/settings/daily-post-rate")
async def set_daily_post_rate_api(rate: int = Form(...)):
    success = episode_scheduler.set_daily_post_rate(rate)
    return {"ok": success, "daily_post_rate": rate, "times": episode_scheduler.get_autopost_times()}

@app.post("/api/douyin/settings/autopost-times")
@app.post("/scrapper/api/douyin/settings/autopost-times")
async def set_autopost_times_api(times: str = Form(...)):
    time_list = [t.strip() for t in times.split(",") if t.strip()]
    success = episode_scheduler.set_autopost_times(time_list)
    return {"ok": success, "times": episode_scheduler.get_autopost_times()}

@app.get("/api/douyin/settings/cookie")
@app.get("/scrapper/api/douyin/settings/cookie")
async def get_cookie_api():
    cookie = os.getenv("DOUYIN_COOKIE", "").strip()
    return {"ok": True, "cookie": cookie}

@app.post("/api/douyin/settings/cookie")
@app.post("/scrapper/api/douyin/settings/cookie")
async def save_cookie_api(cookie: str = Form(...)):
    cookie_val = cookie.strip()
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    
    try:
        env_text = ""
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                env_text = f.read()

        if "DOUYIN_COOKIE=" in env_text:
            env_text = re.sub(r'DOUYIN_COOKIE=.*', f'DOUYIN_COOKIE="{cookie_val}"', env_text)
        else:
            env_text += f'\nDOUYIN_COOKIE="{cookie_val}"\n'

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_text)

        os.environ["DOUYIN_COOKIE"] = cookie_val

        from scripts import sync_cookie
        sync_cookie.sync()

        return {"ok": True, "message": "Cookie salvo no .env e sincronizado!"}
    except Exception as e:
        return {"ok": False, "message": f"Erro ao salvar cookie: {e}"}

@app.get("/api/douyin/profiles")
@app.get("/scrapper/api/douyin/profiles")
async def get_douyin_profiles_api():
    profs = database.get_douyin_profiles()
    return {"ok": True, "profiles": profs}

@app.post("/api/douyin/profiles/add")
@app.post("/scrapper/api/douyin/profiles/add")
async def add_douyin_profile_api(url: str = Form(...)):
    res = douyin_profile_scraper.fetch_and_store_profile(url)
    return res

@app.post("/api/douyin/profiles/{sec_uid}/delete")
@app.post("/scrapper/api/douyin/profiles/{sec_uid}/delete")
async def delete_douyin_profile_api(sec_uid: str):
    success = database.delete_douyin_profile(sec_uid)
    return {"ok": success}

@app.post("/api/douyin/sync")
@app.post("/scrapper/api/douyin/sync")
async def sync_all_content_api(background_tasks: BackgroundTasks):
    background_tasks.add_task(douyin_profile_scraper.sync_all_profiles_and_collections)
    return {"ok": True, "message": "Varredura autônoma iniciada em background."}

@app.get("/api/status")
@app.get("/scrapper/api/status")
async def get_status(bvids: str):
    bvid_list = [b.strip() for b in bvids.split(",") if b.strip()]
    if not bvid_list:
        return {}
    res = {}
    conn = database.get_connection()
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(bvid_list))
    cursor.execute(f"SELECT bvid, status FROM processed_videos WHERE bvid IN ({placeholders})", bvid_list)
    rows = cursor.fetchall()
    for row in rows:
        res[row["bvid"]] = row["status"]
    conn.close()
    return res

def get_access_denied_page():
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Acesso Negado | AnimeRecaps</title>
    <style>
        body { background:#0a0a0f; color:#fff; font-family:sans-serif; display:flex; height:100vh; align-items:center; justify-content:center; margin:0; }
        .box { text-align:center; padding:40px; background:#14141f; border-radius:12px; border:1px solid #e50914; max-width:400px; }
        h1 { color:#e50914; margin-top:0; }
    </style>
</head>
<body>
    <div class="box">
        <h1>🔒 Acesso Não Autorizado</h1>
        <p>Acesse o bot no Telegram e use o comando <code>/start</code> para gerar seu link de acesso seguro.</p>
    </div>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
@app.get("/scrapper", response_class=HTMLResponse)
@app.get("/scrapper/", response_class=HTMLResponse)
async def index(
    request: Request,
    session: str = Query(None),
    tab: str = Query("collections"),
    type: str = Query("anime"),
    duration: str = Query("all")
):
    if tab not in ["collections", "profiles", "search", "updates", "cart", "channels", "terms"]:
        tab = "collections"
    if duration not in ["all", "shorts", "longos"]:
        duration = "all"
        
    if session:
        if database.validate_web_session(session):
            cookie_path = "/scrapper"
            redirect_url = f"/scrapper/?tab={tab}&type={type}&duration={duration}"
            redir_resp = RedirectResponse(url=redirect_url, status_code=303)
            redir_resp.set_cookie(
                key="scrapper_session", value=session, max_age=1800,
                httponly=True, samesite="lax", secure=False, path="/"
            )
            return redir_resp
        else:
            return HTMLResponse(content=get_access_denied_page(), status_code=401)
            
    cookie_token = request.cookies.get("scrapper_session")
    if not database.validate_web_session(cookie_token):
        return HTMLResponse(content=get_access_denied_page(), status_code=401)

    tab_collections_active = "active" if tab == "collections" else ""
    tab_profiles_active = "active" if tab == "profiles" else ""
    tab_search_active = "active" if tab == "search" else ""
    tab_updates_active = "active" if tab == "updates" else ""
    tab_cart_active = "active" if tab == "cart" else ""
    tab_channels_active = "active" if tab == "channels" else ""
    tab_terms_active = "active" if tab == "terms" else ""

    daily_rate = episode_scheduler.get_daily_post_rate()
    times_list = episode_scheduler.get_autopost_times()
    times_formatted = ", ".join(times_list)

    opt1 = "selected" if str(daily_rate) == "1" else ""
    opt2 = "selected" if str(daily_rate) == "2" else ""
    opt3 = "selected" if str(daily_rate) == "3" else ""

    content_html = ""
    header_action_button = ""

    # ─── ABA 1: COLEÇÕES DO DOUYIN (NETFLIX VITRINE) ───────────────────────────
    if tab == "collections":
        header_action_button = f"""
        <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
            <label style="font-size:0.85rem; color:#aaa; font-weight:600;">⚡ Ritmo:</label>
            <select id="dailyPostRateSelect" onchange="updateDailyPostRate(this.value)" style="background:#1a1d24; color:#fff; border:1px solid #333; padding:8px 12px; border-radius:8px; font-weight:bold; cursor:pointer;">
                <option value="1" {opt1}>1/dia</option>
                <option value="2" {opt2}>2/dia (Padrão)</option>
                <option value="3" {opt3}>3/dia</option>
            </select>
            <button class="btn-sync" onclick="openTimesModal()" style="background:#2563eb;">⏰ Horários: [{times_formatted}]</button>
            <button class="btn-sync" onclick="openCookieModal()" style="background:#374151;">🍪 Cookie</button>
            <button class="btn-sync" onclick="openAddCollectionModal()" style="background: linear-gradient(135deg, #e50914, #b81d24);">➕ Nova Coleção</button>
        </div>
        """
        cols = [c for c in database.get_douyin_collections() if not c.get("is_virtual")]
        cards_html = ""
        for c in cols:
            autopost_label = "🟢 Autoposting ON" if c.get("autoposting") else "🔴 Autoposting OFF"
            autopost_class = "badge-on" if c.get("autoposting") else "badge-off"
            opaque_count = c.get("opaque_count") or 0
            opaque_badge = f'<span class="badge-opaque-warn">⚠️ {opaque_count} Requer Ação</span>' if opaque_count > 0 else ""

            cards_html += f"""
            <div class="card card-series" onclick="openSeriesModal('{c['mix_id']}')">
                <div class="card-cover-wrapper">
                    <img src="{c['cover_url']}" class="card-cover" onerror="this.src='https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png'">
                    <span class="badge {autopost_class}">{autopost_label}</span>
                </div>
                <div class="card-body">
                    <h3 class="card-title">{c['title_pt']}</h3>
                    <p class="card-author">{c.get('title_zh') or ''} • 👤 {c['author']}</p>
                    <div class="card-progress-bar"><div class="card-progress-fill" style="width: {min(100, int((c.get('posted_count', 0)/(c['total_episodes'] or 1))*100))}%"></div></div>
                    <div class="card-footer-info">
                        <span>📊 EPs: <strong>{c.get('posted_count', 0)}/{c['total_episodes']}</strong></span>
                        {opaque_badge}
                    </div>
                </div>
            </div>
            """

        content_html = f"""
        <div class="vitrine-container">
            <h2 class="section-title">🍿 Coleções Ativas do Douyin</h2>
            <div class="grid-series">{cards_html if cards_html else '<p style="color:#888;">Nenhuma coleção cadastrada. Clique em "➕ Nova Coleção".</p>'}</div>
        </div>
        """

    # ─── ABA 2: ÁREA EXCLUSIVA DE PERFIS (ISOLADA) ─────────────────────────────
    elif tab == "profiles":
        header_action_button = f"""
        <div style="display:flex; gap:10px; align-items:center;">
            <button class="btn-sync" onclick="openAddProfileModal()" style="background:#1e3a8a;">➕ Cadastrar Perfil</button>
            <button class="btn-sync" onclick="syncAllContentNow()" style="background:#065f46;">🔄 Sincronizar Agora</button>
        </div>
        """
        profs = database.get_douyin_profiles()
        prof_html = ""

        for p in profs:
            sec_uid = p["sec_uid"]
            nickname = p["nickname"]
            avatar = p["avatar_url"] or "https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png"
            virtual_mix_id = f"profile_{sec_uid[:15]}"
            eps = database.get_collection_episodes(virtual_mix_id)

            eps_cards = ""
            for ep in eps:
                dur_m = ep['duration_seconds'] // 60
                dur_s = ep['duration_seconds'] % 60
                dur_str = f"{dur_m}:{dur_s:02d}"

                eps_cards += f"""
                <div class="card card-video" style="background:#161922; border:1px solid #2a2e3d; border-radius:10px; overflow:hidden;">
                    <div style="position:relative; height:180px;">
                        <img src="{ep['cover_url']}" style="width:100%; height:100%; object-fit:cover;">
                        <span style="position:absolute; bottom:8px; right:8px; background:rgba(0,0,0,0.8); color:#fff; padding:2px 8px; border-radius:4px; font-size:0.75rem; font-weight:bold;">⏱️ {dur_str}</span>
                    </div>
                    <div style="padding:12px;">
                        <h4 style="margin:0 0 6px 0; font-size:0.92rem; color:#fff; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">{ep['title']}</h4>
                        <p style="margin:0 0 10px 0; font-size:0.8rem; color:#aaa;">❤️ {ep['likes']} likes</p>
                        <div style="display:flex; gap:6px;">
                            <button class="btn-ep btn-post-now" onclick="applyEpAction({ep['id']}, 'post_now')" style="flex:1;">⚡ Postar Agora</button>
                            <button class="btn-ep btn-next-queue" onclick="applyEpAction({ep['id']}, 'next_in_queue')" style="flex:1;">🔝 Fila</button>
                        </div>
                    </div>
                </div>
                """

            prof_html += f"""
            <div style="background:#12141c; border:1px solid #232736; border-radius:12px; padding:20px; margin-bottom:30px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                    <div style="display:flex; align-items:center; gap:14px;">
                        <img src="{avatar}" style="width:50px; height:50px; border-radius:50%; object-fit:cover; border:2px solid #0288d1;">
                        <div>
                            <h3 style="margin:0; font-size:1.2rem; color:#fff;">👤 {nickname}</h3>
                            <a href="{p['profile_url']}" target="_blank" style="color:#0288d1; font-size:0.82rem; text-decoration:none;">🔗 Ver Perfil no Douyin</a>
                        </div>
                    </div>
                    <button class="btn-sync" onclick="deleteProfile('{sec_uid}')" style="background:#b81d24; border:none; padding:8px 14px; cursor:pointer;">🗑️ Remover Perfil</button>
                </div>
                <h4 style="color:#aaa; font-size:0.9rem; margin-bottom:12px;">📅 Postagens dos Últimos 2 Meses ({len(eps)} vídeos):</h4>
                <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap:16px;">
                    {eps_cards if eps_cards else '<p style="color:#666; font-size:0.85rem;">Nenhum vídeo recente encontrado nos últimos 2 meses.</p>'}
                </div>
            </div>
            """

        content_html = f"""
        <div class="vitrine-container">
            <h2 class="section-title">👤 Perfis Monitorados do Douyin (Área Exclusiva)</h2>
            {prof_html if prof_html else '<p style="color:#888;">Nenhum perfil cadastrado. Clique em "➕ Cadastrar Perfil".</p>'}
        </div>
        """

    return HTMLResponse(content=get_full_html_page(
        tab=tab, type=type, duration=duration,
        header_action_button=header_action_button,
        content_html=content_html,
        tab_collections_active=tab_collections_active,
        tab_profiles_active=tab_profiles_active,
        tab_search_active=tab_search_active,
        tab_updates_active=tab_updates_active,
        tab_cart_active=tab_cart_active,
        tab_channels_active=tab_channels_active,
        tab_terms_active=tab_terms_active
    ))

def get_full_html_page(tab, type, duration, header_action_button, content_html,
                        tab_collections_active, tab_profiles_active, tab_search_active,
                        tab_updates_active, tab_cart_active, tab_channels_active, tab_terms_active):
    
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Douyin Scrapper & Vitrine Netflix</title>
    <style>
        body {{ background:#08090d; color:#e2e8f0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; margin:0; padding:0; }}
        header {{ background:#0f111a; border-bottom:1px solid #1e2230; padding:16px 32px; display:flex; justify-content:space-between; align-items:center; }}
        .brand {{ font-size:1.4rem; font-weight:800; color:#e50914; text-decoration:none; display:flex; align-items:center; gap:8px; }}
        .tabs-row {{ display:flex; gap:12px; padding:16px 32px; background:#0c0e14; border-bottom:1px solid #1a1d29; overflow-x:auto; }}
        .tab-link {{ padding:10px 18px; border-radius:8px; color:#a0aec0; text-decoration:none; font-weight:600; font-size:0.9rem; transition:all 0.2s; }}
        .tab-link.active, .tab-link:hover {{ background:#1e2333; color:#fff; }}
        .tab-link.active {{ border-bottom:3px solid #e50914; }}
        main {{ padding:24px 32px; }}
        .section-title {{ font-size:1.3rem; margin-top:0; margin-bottom:20px; color:#fff; }}
        .grid-series {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap:20px; }}
        .card-series {{ background:#121520; border:1px solid #1e2333; border-radius:12px; overflow:hidden; cursor:pointer; transition:transform 0.2s, border-color 0.2s; }}
        .card-series:hover {{ transform:translateY(-4px); border-color:#e50914; }}
        .card-cover-wrapper {{ position:relative; width:100%; height:320px; background:#000; }}
        .card-cover {{ width:100%; height:100%; object-fit:cover; }}
        .card-body {{ padding:14px; }}
        .card-title {{ font-size:1rem; font-weight:700; margin:0 0 6px 0; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
        .card-author {{ font-size:0.8rem; color:#888; margin:0 0 10px 0; }}
        .card-progress-bar {{ height:6px; background:#1e2333; border-radius:3px; overflow:hidden; margin-bottom:8px; }}
        .card-progress-fill {{ height:100%; background:linear-gradient(90deg, #e50914, #ff5252); }}
        .card-footer-info {{ display:flex; justify-content:space-between; font-size:0.8rem; color:#aaa; }}
        .badge {{ position:absolute; top:10px; right:10px; padding:4px 8px; border-radius:6px; font-size:0.75rem; font-weight:bold; }}
        .badge-on {{ background:rgba(46,125,50,0.9); color:#fff; }}
        .badge-off {{ background:rgba(198,40,40,0.9); color:#fff; }}
        .btn-sync {{ padding:8px 16px; border-radius:8px; border:none; color:#fff; font-weight:bold; font-size:0.85rem; cursor:pointer; }}
        .modal-overlay {{ display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.85); z-index:9999; justify-content:center; align-items:center; }}
        .modal-container {{ background:#121520; border:1px solid #2a2e3d; border-radius:14px; color:#fff; position:relative; max-height:90vh; overflow-y:auto; }}
        .modal-close {{ position:absolute; top:16px; right:20px; font-size:1.8rem; cursor:pointer; color:#aaa; }}
        .ep-row {{ display:flex; align-items:center; justify-content:space-between; padding:10px; border-bottom:1px solid #1a1d29; gap:12px; }}
        .btn-ep {{ padding:6px 12px; border-radius:6px; border:none; font-weight:bold; font-size:0.78rem; cursor:pointer; }}
        .btn-post-now {{ background:#e50914; color:#fff; }}
        .btn-next-queue {{ background:#0288d1; color:#fff; }}
    </style>
</head>
<body>
    <header>
        <a href="/scrapper/?tab=collections" class="brand">🍿 Douyin Scrapper</a>
        {header_action_button}
    </header>

    <div class="tabs-row">
        <a href="/scrapper/?tab=collections&type={type}&duration={duration}" class="tab-link {tab_collections_active}">🍿 Coleções Douyin</a>
        <a href="/scrapper/?tab=profiles&type={type}&duration={duration}" class="tab-link {tab_profiles_active}">👤 Perfis Douyin</a>
        <a href="/scrapper/?tab=search&type={type}&duration={duration}" class="tab-link {tab_search_active}">🔍 Busca Geral</a>
        <a href="/scrapper/?tab=updates&type={type}&duration={duration}" class="tab-link {tab_updates_active}">🔔 Atualizações</a>
        <a href="/scrapper/?tab=cart&type={type}&duration={duration}" class="tab-link {tab_cart_active}">🛒 Carrinho / Fila</a>
    </div>

    <main>{content_html}</main>

    <!-- MODAIS DO SISTEMA -->
    <div id="addCollectionModal" class="modal-overlay">
        <div class="modal-container" style="max-width:520px; padding:24px;">
            <span class="modal-close" onclick="closeAddCollectionModal()">&times;</span>
            <h3 style="margin-top:0;">➕ Cadastrar Coleção Douyin</h3>
            <form onsubmit="submitAddCollection(event)">
                <input type="text" id="colUrlInput" placeholder="URL da Coleção Douyin" required style="width:100%; padding:10px; margin-bottom:12px; background:#1a1d24; border:1px solid #333; color:#fff; border-radius:8px;">
                <input type="text" id="colTitlePtInput" placeholder="Título em Português (Opcional)" style="width:100%; padding:10px; margin-bottom:16px; background:#1a1d24; border:1px solid #333; color:#fff; border-radius:8px;">
                <button type="submit" id="btnAddColSubmit" class="btn-sync" style="width:100%; background:#e50914;">📡 Mapear e Salvar Coleção</button>
            </form>
        </div>
    </div>

    <div id="addProfileModal" class="modal-overlay">
        <div class="modal-container" style="max-width:520px; padding:24px;">
            <span class="modal-close" onclick="closeAddProfileModal()">&times;</span>
            <h3 style="margin-top:0;">👤 Cadastrar Perfil Douyin</h3>
            <form onsubmit="submitAddProfile(event)">
                <input type="text" id="profileUrlInput" placeholder="URL do Perfil Douyin" required style="width:100%; padding:10px; margin-bottom:16px; background:#1a1d24; border:1px solid #333; color:#fff; border-radius:8px;">
                <button type="submit" id="btnAddProfileSubmit" class="btn-sync" style="width:100%; background:#1e3a8a;">📡 Mapear Postagens (Últimos 2 Meses)</button>
            </form>
        </div>
    </div>

    <div id="timesModal" class="modal-overlay">
        <div class="modal-container" style="max-width:440px; padding:24px;">
            <span class="modal-close" onclick="closeTimesModal()">&times;</span>
            <h3 style="margin-top:0;">⏰ Horários Personalizados</h3>
            <p style="color:#aaa; font-size:0.85rem;">Defina os horários das suas postagens diárias (separados por vírgula):</p>
            <input type="text" id="timesInput" value="12:00, 18:00" style="width:100%; padding:10px; margin-bottom:16px; background:#1a1d24; border:1px solid #333; color:#fff; border-radius:8px;">
            <button onclick="saveAutopostTimes()" class="btn-sync" style="width:100%; background:#2563eb;">💾 Salvar Horários</button>
        </div>
    </div>

    <script>
        const ROOT_PATH = "/scrapper";

        function updateDailyPostRate(rate) {{
            const formData = new FormData();
            formData.append('rate', rate);
            fetch(ROOT_PATH + '/api/douyin/settings/daily-post-rate', {{ method: 'POST', body: formData }})
                .then(r => r.json())
                .then(data => {{ alert('✅ Ritmo diário salvo!'); window.location.reload(); }});
        }}

        function openTimesModal() {{ document.getElementById('timesModal').style.display = 'flex'; }}
        function closeTimesModal() {{ document.getElementById('timesModal').style.display = 'none'; }}
        function saveAutopostTimes() {{
            const times = document.getElementById('timesInput').value;
            const formData = new FormData();
            formData.append('times', times);
            fetch(ROOT_PATH + '/api/douyin/settings/autopost-times', {{ method: 'POST', body: formData }})
                .then(r => r.json())
                .then(data => {{ alert('✅ Horários salvos!'); closeTimesModal(); window.location.reload(); }});
        }}

        function openAddCollectionModal() {{ document.getElementById('addCollectionModal').style.display = 'flex'; }}
        function closeAddCollectionModal() {{ document.getElementById('addCollectionModal').style.display = 'none'; }}
        function submitAddCollection(e) {{
            e.preventDefault();
            const btn = document.getElementById('btnAddColSubmit');
            btn.disabled = true; btn.innerText = '📡 Mapeando... Aguarde...';
            const formData = new FormData();
            formData.append('url', document.getElementById('colUrlInput').value);
            formData.append('title_pt', document.getElementById('colTitlePtInput').value);
            fetch(ROOT_PATH + '/api/douyin/collections/add', {{ method: 'POST', body: formData }})
                .then(r => r.json())
                .then(data => {{ alert('✅ ' + data.message); closeAddCollectionModal(); window.location.reload(); }});
        }}

        function openAddProfileModal() {{ document.getElementById('addProfileModal').style.display = 'flex'; }}
        function closeAddProfileModal() {{ document.getElementById('addProfileModal').style.display = 'none'; }}
        function submitAddProfile(e) {{
            e.preventDefault();
            const btn = document.getElementById('btnAddProfileSubmit');
            btn.disabled = true; btn.innerText = '📡 Mapeando Perfil...';
            const formData = new FormData();
            formData.append('url', document.getElementById('profileUrlInput').value);
            fetch(ROOT_PATH + '/api/douyin/profiles/add', {{ method: 'POST', body: formData }})
                .then(r => r.json())
                .then(data => {{ alert('✅ ' + data.message); closeAddProfileModal(); window.location.reload(); }});
        }}

        function deleteProfile(secUid) {{
            if (confirm('Deseja remover este perfil monitorado?')) {{
                fetch(ROOT_PATH + '/api/douyin/profiles/' + secUid + '/delete', {{ method: 'POST' }})
                    .then(r => r.json())
                    .then(data => {{ alert('✅ Perfil removido!'); window.location.reload(); }});
            }}
        }}

        function applyEpAction(epId, action) {{
            const formData = new FormData();
            formData.append('action', action);
            fetch(ROOT_PATH + '/api/douyin/episodes/' + epId + '/action', {{ method: 'POST', body: formData }})
                .then(r => r.json())
                .then(data => {{ alert('✅ ' + data.message); window.location.reload(); }});
        }}

        function syncAllContentNow() {{
            fetch(ROOT_PATH + '/api/douyin/sync', {{ method: 'POST' }})
                .then(r => r.json())
                .then(data => {{ alert('✅ ' + data.message); }});
        }}
    </script>
</body>
</html>"""

def run_panel():
    import uvicorn
    database.init_db()
    print("Iniciando Painel Web na porta 5556 (http://localhost:5556)...")
    uvicorn.run(app, host="0.0.0.0", port=5556, log_level="warning")
