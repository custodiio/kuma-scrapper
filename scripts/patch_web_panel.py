"""
Script para injetar o Frontend Vitrine Netflix no src/web_panel.py
"""

import re
from pathlib import Path

panel_path = Path("src/web_panel.py")
content = panel_path.read_text(encoding="utf-8")

# 1. Altera a aba padrão para 'collections'
content = content.replace('tab: str = "search"', 'tab: str = "collections"')
content = content.replace(
    'if tab not in ["search", "updates", "cart", "channels", "terms"]:',
    'if tab not in ["collections", "search", "updates", "cart", "channels", "terms"]:'
)
content = re.sub(
    r'if tab not in \["collections", "search", "updates", "cart", "channels", "terms"\]:\s*tab = "search"',
    'if tab not in ["collections", "search", "updates", "cart", "channels", "terms"]:\n        tab = "collections"',
    content
)

# 2. Adiciona tab_collections_active
content = content.replace(
    'tab_search_active = "active" if tab == "search" else ""',
    'tab_collections_active = "active" if tab == "collections" else ""\n    tab_search_active = "active" if tab == "search" else ""'
)

# 3. Adiciona a aba '🍿 Coleções Douyin' no cabeçalho de navegação
old_nav = '<a href="{ROOT_PATH}/?tab=search&type={type}&duration={duration}" class="tab-link {tab_search_active}">🔍 Busca Geral</a>'
new_nav = '<a href="{ROOT_PATH}/?tab=collections&type={type}&duration={duration}" class="tab-link {tab_collections_active}">🍿 Coleções Douyin</a>\n            ' + old_nav
content = content.replace(old_nav, new_nav)

# 4. Adiciona o bloco de renderização da ABA COLLECTIONS
collections_block = '''    # ─── ABA 0: COLEÇÕES DO DOUYIN (VITRINE NETFLIX) ─────────────────────────
    if tab == "collections":
        daily_rate = episode_scheduler.get_daily_post_rate()
        header_action_button = f"""
        <div style="display:flex; gap:12px; align-items:center;">
            <label style="font-size:0.85rem; color:#aaa; font-weight:600;">⚡ Ritmo Diário:</label>
            <select id="dailyPostRateSelect" onchange="updateDailyPostRate(this.value)" style="background:#1a1d24; color:#fff; border:1px solid #333; padding:8px 12px; border-radius:8px; font-weight:bold; cursor:pointer;">
                <option value="1" {'selected' if str(daily_rate) == '1' else ''}>1 vídeo / dia</option>
                <option value="2" {'selected' if str(daily_rate) == '2' else ''}>2 vídeos / dia (Recomendado)</option>
                <option value="3" {'selected' if str(daily_rate) == '3' else ''}>3 vídeos / dia</option>
            </select>
            <button class="btn-sync" onclick="openAddCollectionModal()" style="background: linear-gradient(135deg, #e50914, #b81d24);">➕ Cadastrar Coleção</button>
        </div>
        """
        cols = database.get_douyin_collections()
        cards_html = ""
        for c in cols:
            autopost_label = "🟢 Autoposting ON" if c.get("autoposting") else "🔴 Autoposting OFF"
            autopost_class = "badge-on" if c.get("autoposting") else "badge-off"
            opaque_count = c.get("opaque_count") or 0
            opaque_badge = f'<span class="badge-opaque-warn">⚠️ {opaque_count} Requer Ação</span>' if opaque_count > 0 else ""
            
            cards_html += f"""
            <div class="netflix-card" onclick="openSeriesModal('{c['mix_id']}')">
                <div class="netflix-cover-wrapper">
                    <img src="{c['cover_url']}" class="netflix-cover" alt="Capa" onerror="this.src='https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png'">
                    <div class="netflix-overlay">
                        <span class="btn-play">▶️ Ver Episódios</span>
                    </div>
                    <div class="netflix-badge-left {autopost_class}">{autopost_label}</div>
                    <div class="netflix-badge-right">{c.get('posted_count', 0)} / {c.get('total_episodes_mapped', 0)} EPs</div>
                    {opaque_badge}
                </div>
                <div class="netflix-card-info">
                    <h3 class="netflix-title-pt">{c['title_pt']}</h3>
                    <p class="netflix-title-zh">{c['title_zh'] or f"Coleção #{c['mix_id']}"} • 👤 {c.get('author', 'Desconhecido')}</p>
                </div>
            </div>
            """

        if not cards_html:
            cards_html = """
            <div class="no-results" style="grid-column: 1 / -1; text-align: center; padding: 60px 20px;">
                <p style="font-size: 1.3rem; font-weight: bold; margin-bottom: 10px;">📭 Nenhuma coleção cadastrada no momento.</p>
                <p style="color: #888; margin-bottom: 20px;">Cole o link de uma coleção do Douyin para iniciar a curadoria autônoma.</p>
                <button class="btn-sync" onclick="openAddCollectionModal()" style="background: linear-gradient(135deg, #e50914, #b81d24); padding: 12px 28px;">➕ Cadastrar Minha Primeira Coleção</button>
            </div>
            """
            
        content_html = f'<div class="netflix-grid">{cards_html}</div>'
'''

content = content.replace('    # ─── ABA 1: BUSCA GERAL ──────────────────────────────────────────────────', collections_block + '\n    # ─── ABA 1: BUSCA GERAL ──────────────────────────────────────────────────')

# 5. Adiciona os estilos CSS e JS para a Vitrine Netflix e Modais
netflix_css = '''
        /* ESTILOS VITRINE NETFLIX & MODAIS */
        .netflix-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
            gap: 24px;
            margin-top: 15px;
        }
        .netflix-card {
            background: #14171d;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.06);
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            position: relative;
        }
        .netflix-card:hover {
            transform: translateY(-6px) scale(1.02);
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.6), 0 0 15px rgba(229, 9, 20, 0.3);
            border-color: rgba(229, 9, 20, 0.5);
        }
        .netflix-cover-wrapper {
            position: relative;
            width: 100%;
            padding-top: 133%; /* Proporção 3:4 */
            background: #0d0f12;
            overflow: hidden;
        }
        .netflix-cover {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            object-fit: cover;
            transition: transform 0.4s ease;
        }
        .netflix-card:hover .netflix-cover {
            transform: scale(1.06);
        }
        .netflix-overlay {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(180deg, rgba(0,0,0,0) 40%, rgba(0,0,0,0.85) 100%);
            display: flex;
            align-items: flex-end;
            justify-content: center;
            padding-bottom: 20px;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        .netflix-card:hover .netflix-overlay {
            opacity: 1;
        }
        .btn-play {
            background: #e50914;
            color: #fff;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.85rem;
            box-shadow: 0 4px 10px rgba(229, 9, 20, 0.4);
        }
        .netflix-badge-left {
            position: absolute;
            top: 10px; left: 10px;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.72rem;
            font-weight: bold;
            backdrop-filter: blur(8px);
        }
        .badge-on { background: rgba(46, 125, 50, 0.85); color: #e8f5e9; }
        .badge-off { background: rgba(198, 40, 40, 0.85); color: #ffebee; }
        .netflix-badge-right {
            position: absolute;
            top: 10px; right: 10px;
            background: rgba(0, 0, 0, 0.75);
            color: #fff;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.72rem;
            font-weight: bold;
            backdrop-filter: blur(8px);
        }
        .badge-opaque-warn {
            position: absolute;
            bottom: 10px; left: 10px;
            background: rgba(245, 124, 0, 0.9);
            color: #fff;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.72rem;
            font-weight: bold;
        }
        .netflix-card-info {
            padding: 14px;
        }
        .netflix-title-pt {
            font-size: 1.05rem;
            font-weight: 700;
            color: #fff;
            margin: 0 0 4px 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .netflix-title-zh {
            font-size: 0.8rem;
            color: #888;
            margin: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        /* MODAIS */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(8px);
            z-index: 9999;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .modal-container {
            background: #14171d;
            border-radius: 16px;
            max-width: 850px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8);
            position: relative;
        }
        .modal-close {
            position: absolute;
            top: 15px; right: 20px;
            font-size: 1.8rem;
            color: #aaa;
            cursor: pointer;
            z-index: 10;
            transition: color 0.2s;
        }
        .modal-close:hover { color: #fff; }
        .modal-hero {
            display: flex;
            gap: 20px;
            padding: 24px;
            background: linear-gradient(180deg, rgba(229, 9, 20, 0.15) 0%, transparent 100%);
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }
        .modal-hero-cover {
            width: 140px;
            height: 190px;
            object-fit: cover;
            border-radius: 10px;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.5);
        }
        .modal-hero-info { flex: 1; }
        .modal-episodes-list { padding: 24px; }
        .episode-row {
            display: flex;
            gap: 16px;
            align-items: center;
            padding: 12px;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            margin-bottom: 12px;
            transition: background 0.2s;
        }
        .episode-row:hover { background: rgba(255, 255, 255, 0.05); }
        .episode-row.opaque {
            opacity: 0.45;
            background: rgba(245, 124, 0, 0.05);
            border-color: rgba(245, 124, 0, 0.3);
        }
        .episode-row.opaque:hover { opacity: 0.85; }
        .ep-thumb { width: 90px; height: 55px; object-fit: cover; border-radius: 6px; }
        .ep-info { flex: 1; }
        .ep-title { font-weight: bold; font-size: 0.95rem; color: #fff; margin-bottom: 4px; }
        .ep-meta { font-size: 0.8rem; color: #888; }
        .ep-actions { display: flex; gap: 6px; flex-wrap: wrap; }
        .btn-ep { padding: 6px 12px; border-radius: 6px; border: none; font-size: 0.78rem; font-weight: bold; cursor: pointer; }
        .btn-post-now { background: #e50914; color: #fff; }
        .btn-next-queue { background: #0288d1; color: #fff; }
        .btn-accel { background: #f57c00; color: #fff; }
        .btn-split { background: #7b1fa2; color: #fff; }
        .btn-keep { background: #388e3c; color: #fff; }
        .btn-ignore { background: #424242; color: #aaa; }
'''

content = content.replace('        body {', netflix_css + '\n        body {')

# 6. Adiciona Modais HTML e Scripts JS antes do </body>
modals_and_js = '''
    <!-- MODAL CADASTRO DE COLEÇÃO -->
    <div id="addCollectionModal" class="modal-overlay">
        <div class="modal-container" style="max-width: 520px; padding: 24px;">
            <span class="modal-close" onclick="closeAddCollectionModal()">&times;</span>
            <h3 style="margin-top:0; font-size:1.3rem;">➕ Cadastrar Nova Coleção Douyin</h3>
            <p style="color:#888; font-size:0.88rem; margin-bottom:20px;">Cole a URL da coleção, URL de um vídeo da coleção ou o ID numérico (mix_id).</p>
            <form id="addCollectionForm" onsubmit="submitAddCollection(event)">
                <div style="margin-bottom: 16px;">
                    <label style="display:block; font-size:0.85rem; color:#ccc; margin-bottom:6px; font-weight:bold;">URL ou ID da Coleção:</label>
                    <input type="text" id="colUrlInput" placeholder="Ex: https://www.douyin.com/collection/7657384437071480866" required style="width:100%; padding:10px 14px; background:#1a1d24; border:1px solid #333; color:#fff; border-radius:8px;">
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display:block; font-size:0.85rem; color:#ccc; margin-bottom:6px; font-weight:bold;">Título em Português (Opcional):</label>
                    <input type="text" id="colTitlePtInput" placeholder="Ex: Ponto de Virada" style="width:100%; padding:10px 14px; background:#1a1d24; border:1px solid #333; color:#fff; border-radius:8px;">
                </div>
                <div style="margin-bottom: 24px; display:flex; align-items:center; gap:10px;">
                    <input type="checkbox" id="colAutopostInput" checked style="width:18px; height:18px; cursor:pointer;">
                    <label for="colAutopostInput" style="font-size:0.9rem; color:#fff; cursor:pointer;">Ativar Autoposting Imediatamente (ON)</label>
                </div>
                <button type="submit" id="btnAddColSubmit" class="btn-sync" style="width:100%; background: linear-gradient(135deg, #e50914, #b81d24); padding: 12px;">📡 Mapear e Salvar Coleção</button>
            </form>
        </div>
    </div>

    <!-- MODAL DETALHES DA SÉRIE / COLEÇÃO (NETFLIX STYLE) -->
    <div id="seriesDetailModal" class="modal-overlay">
        <div class="modal-container">
            <span class="modal-close" onclick="closeSeriesModal()">&times;</span>
            <div id="modalHeroContent" class="modal-hero"></div>
            <div class="modal-episodes-list">
                <h4 style="margin-top:0; margin-bottom:16px; font-size:1.1rem;">📋 Lista de Episódios Mapeados</h4>
                <div id="episodesContainer"></div>
            </div>
        </div>
    </div>

    <script>
        function updateDailyPostRate(rate) {
            const formData = new FormData();
            formData.append('rate', rate);
            fetch('/scrapper/api/douyin/settings/daily-post-rate', { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => { alert('✅ Ritmo diário atualizado para ' + rate + ' vídeos/dia!'); })
                .catch(err => alert('❌ Erro ao atualizar ritmo: ' + err));
        }

        function openAddCollectionModal() {
            document.getElementById('addCollectionModal').style.display = 'flex';
        }
        function closeAddCollectionModal() {
            document.getElementById('addCollectionModal').style.display = 'none';
        }

        function submitAddCollection(e) {
            e.preventDefault();
            const btn = document.getElementById('btnAddColSubmit');
            btn.disabled = true;
            btn.innerText = '📡 Mapeando... Aguarde...';

            const formData = new FormData();
            formData.append('url', document.getElementById('colUrlInput').value);
            formData.append('title_pt', document.getElementById('colTitlePtInput').value);
            formData.append('autoposting', document.getElementById('colAutopostInput').checked ? 1 : 0);

            fetch('/scrapper/api/douyin/collections/add', { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => {
                    btn.disabled = false;
                    btn.innerText = '📡 Mapear e Salvar Coleção';
                    if (data.ok) {
                        alert(data.message);
                        closeAddCollectionModal();
                        window.location.reload();
                    } else {
                        alert('❌ Erro: ' + data.message);
                    }
                })
                .catch(err => {
                    btn.disabled = false;
                    btn.innerText = '📡 Mapear e Salvar Coleção';
                    alert('❌ Erro ao mapear coleção: ' + err);
                });
        }

        function openSeriesModal(mixId) {
            fetch('/scrapper/api/douyin/collections/' + mixId)
                .then(r => r.json())
                .then(data => {
                    if (!data.ok) { alert('Erro ao carregar detalhes.'); return; }
                    const c = data.collection;
                    const eps = data.episodes;

                    const autopostBtnLabel = c.autoposting ? '🟢 Autoposting ON' : '🔴 Autoposting OFF';
                    const autopostBtnStyle = c.autoposting ? 'background:#2e7d32;' : 'background:#c62828;';

                    document.getElementById('modalHeroContent').innerHTML = `
                        <img src="${c.cover_url}" class="modal-hero-cover" onerror="this.src='https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png'">
                        <div class="modal-hero-info">
                            <h2 style="margin:0 0 6px 0; font-size:1.6rem;">${c.title_pt}</h2>
                            <p style="color:#aaa; margin:0 0 12px 0; font-size:0.9rem;">${c.title_zh || ''} • 👤 Author: ${c.author}</p>
                            <p style="color:#ccc; font-size:0.85rem; margin-bottom:16px;">📊 Total EPs: <strong>${eps.length}</strong> | Postados: <strong>${c.posted_count || 0}</strong></p>
                            <div style="display:flex; gap:10px; flex-wrap:wrap;">
                                <button class="btn-sync" style="${autopostBtnStyle} border:none; padding:8px 16px; cursor:pointer;" onclick="toggleAutoposting('${c.mix_id}')">${autopostBtnLabel}</button>
                                <button class="btn-sync" style="background:#424242; border:none; padding:8px 16px; cursor:pointer;" onclick="deleteCollection('${c.mix_id}')">🗑️ Excluir Coleção</button>
                            </div>
                        </div>
                    `;

                    let epsHtml = '';
                    eps.forEach((ep, idx) => {
                        const durM = Math.floor(ep.duration_seconds / 60);
                        const durS = ep.duration_seconds % 60;
                        const durStr = `${durM}:${durS < 10 ? '0' : ''}${durS}`;
                        const isOpaque = ep.status === 'opaque_over_5min';

                        let statusBadge = `<span style="color:#aaa;">⏳ Pendente</span>`;
                        if (ep.status === 'posted') statusBadge = `<span style="color:#4caf50; font-weight:bold;">✅ Postado</span>`;
                        if (ep.status === 'post_now') statusBadge = `<span style="color:#f44336; font-weight:bold;">⚡ Postar Agora</span>`;
                        if (ep.status === 'next_in_queue') statusBadge = `<span style="color:#0288d1; font-weight:bold;">🔝 Próximo da Fila</span>`;
                        if (isOpaque) statusBadge = `<span style="color:#f57c00; font-weight:bold;">⚠️ Requer Ação (>5min)</span>`;
                        if (ep.status === 'ignored') statusBadge = `<span style="color:#888;">🗑️ Ignorado</span>`;

                        let actionsHtml = '';
                        if (isOpaque) {
                            actionsHtml = `
                                <button class="btn-ep btn-accel" onclick="applyEpAction(${ep.id}, 'accelerate')">⚡ Acelerar (<3m)</button>
                                <button class="btn-ep btn-split" onclick="applyEpAction(${ep.id}, 'split')">✂️ Dividir</button>
                                <button class="btn-ep btn-keep" onclick="applyEpAction(${ep.id}, 'keep_original')">📹 Manter Original</button>
                                <button class="btn-ep btn-ignore" onclick="applyEpAction(${ep.id}, 'ignore')">🗑️ Descartar</button>
                            `;
                        } else if (ep.status === 'pending') {
                            actionsHtml = `
                                <button class="btn-ep btn-post-now" onclick="applyEpAction(${ep.id}, 'post_now')">⚡ Postar Agora</button>
                                <button class="btn-ep btn-next-queue" onclick="applyEpAction(${ep.id}, 'next_in_queue')">🔝 Próximo Fila</button>
                            `;
                        }

                        epsHtml += `
                            <div class="episode-row ${isOpaque ? 'opaque' : ''}">
                                <img src="${ep.cover_url}" class="ep-thumb" onerror="this.src='https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png'">
                                <div class="ep-info">
                                    <div class="ep-title">EP ${ep.episode_num || idx + 1}: ${ep.title}</div>
                                    <div class="ep-meta">⏱️ ${durStr} | ❤️ ${ep.likes} | Status: ${statusBadge}</div>
                                </div>
                                <div class="ep-actions">${actionsHtml}</div>
                            </div>
                        `;
                    });

                    document.getElementById('episodesContainer').innerHTML = epsHtml || '<p style="color:#888;">Nenhum episódio cadastrado.</p>';
                    document.getElementById('seriesDetailModal').style.display = 'flex';
                });
        }

        function closeSeriesModal() {
            document.getElementById('seriesDetailModal').style.display = 'none';
        }

        function toggleAutoposting(mixId) {
            fetch('/scrapper/api/douyin/collections/' + mixId + '/toggle-autoposting', { method: 'POST' })
                .then(r => r.json())
                .then(data => { openSeriesModal(mixId); });
        }

        function deleteCollection(mixId) {
            if (confirm('Tem certeza que deseja excluir esta coleção?')) {
                fetch('/scrapper/api/douyin/collections/' + mixId + '/delete', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => { closeSeriesModal(); window.location.reload(); });
            }
        }

        function applyEpAction(epId, action) {
            const formData = new FormData();
            formData.append('action', action);
            fetch('/scrapper/api/douyin/episodes/' + epId + '/action', { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => {
                    if (data.ok) {
                        alert('✅ Ação aplicada!');
                        closeSeriesModal();
                        window.location.reload();
                    } else {
                        alert('❌ Erro: ' + data.message);
                    }
                });
        }
    </script>
</body>
'''

content = content.replace('</body>', modals_and_js)

panel_path.write_text(content, encoding="utf-8")
print("✅ Frontend Vitrine Netflix injetado com sucesso no src/web_panel.py!")
