import sqlite3
import os
import json
from datetime import datetime, timedelta

from src.config import HISTORY_DB_PATH

DB_PATH = HISTORY_DB_PATH


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa o banco de dados SQLite com as tabelas necessárias da Fase 2."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Habilita suporte a chaves estrangeiras
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # Tabela de canais monitorados do Bilibili
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,      -- 'shorts' ou 'longos' (obsoleto/all)
            content_type TEXT NOT NULL,  -- 'anime' ou 'manhwa'
            last_video_ref TEXT,         -- BVID do último post de referência
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de vídeos processados/mapeados (Fase 2 / Carrinho)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_videos (
            bvid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            channel_uid TEXT,
            source TEXT NOT NULL,         -- 'channel' (canal cadastrado), 'search' (busca geral) ou 'manual'
            category TEXT NOT NULL,       -- 'shorts' ou 'longos'
            content_type TEXT NOT NULL,   -- 'anime' ou 'manhwa'
            status TEXT NOT NULL,         -- 'pending' (mapeado), 'downloaded' (no Drive), 'posted' (publicado)
            published_at TIMESTAMP,
            posted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (channel_uid) REFERENCES channels(uid) ON DELETE CASCADE
        )
    """)
    
    # Tabela de atualizações temporárias dos canais mapeados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_updates (
            bvid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            pic TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            views INTEGER NOT NULL,
            likes INTEGER NOT NULL,
            published_at TIMESTAMP,
            content_type TEXT NOT NULL,   -- 'anime' ou 'manhwa'
            channel_uid TEXT,
            status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'ignored', 'in_cart'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (channel_uid) REFERENCES channels(uid) ON DELETE CASCADE
        )
    """)
    
    # Tabela de resultados de busca geral para triagem no painel web (com suporte a content_type)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_results (
            bvid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            pic TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            views INTEGER NOT NULL,
            likes INTEGER NOT NULL,
            hype_score INTEGER NOT NULL,
            published_at TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'downloaded', 'ignored', 'in_cart'
            content_type TEXT NOT NULL DEFAULT 'anime', -- 'anime' ou 'manhwa'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Executa migrações de colunas caso o banco já existisse sem elas
    try:
        cursor.execute("ALTER TABLE channels ADD COLUMN last_video_ref TEXT")
    except sqlite3.OperationalError:
        pass # A coluna já existe, ignora o erro
        
    try:
        cursor.execute("ALTER TABLE search_results ADD COLUMN content_type TEXT NOT NULL DEFAULT 'anime'")
    except sqlite3.OperationalError:
        pass # A coluna já existe, ignora o erro
        
    # Tabela de termos de busca customizados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL,
            content_type TEXT NOT NULL, -- 'anime' ou 'manhwa'
            UNIQUE(term, content_type)
        )
    """)
    
    # Se a tabela de termos estiver vazia, insere os termos padrão
    cursor.execute("SELECT COUNT(*) as count FROM search_terms")
    row = cursor.fetchone()
    if row and row["count"] == 0:
        cursor.execute("INSERT OR IGNORE INTO search_terms (term, content_type) VALUES ('新番解说', 'anime')")
        cursor.execute("INSERT OR IGNORE INTO search_terms (term, content_type) VALUES ('韩漫解说', 'manhwa')")
        
    # Tabela de controle de sessões da triagem web
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS web_sessions (
            token TEXT PRIMARY KEY,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de configurações do perfil/sistema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO user_settings (key, value) VALUES ('daily_post_rate', '2')")
    
    # Tabela de Perfis Monitorados do Douyin
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS douyin_profiles (
            sec_uid TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            avatar_url TEXT,
            profile_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela de Coleções/Playlists do Douyin (Nativas ou Virtuais)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS douyin_collections (
            mix_id TEXT PRIMARY KEY,
            title_pt TEXT NOT NULL,
            title_zh TEXT,
            author TEXT,
            cover_url TEXT,
            total_episodes INTEGER DEFAULT 0,
            autoposting INTEGER DEFAULT 1,
            is_virtual INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Episódios da Coleção
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mix_id TEXT NOT NULL,
            episode_num INTEGER,
            aweme_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            duration_seconds INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            cover_url TEXT,
            video_url TEXT,
            status TEXT DEFAULT 'pending',
            is_compilation INTEGER DEFAULT 0,
            posting_guide TEXT,
            scheduled_at TIMESTAMP,
            posted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (mix_id) REFERENCES douyin_collections(mix_id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


# ----------------- OPERAÇÕES DE CANAIS -----------------

def add_channel(uid, name, category="all", content_type="anime", last_video_ref=None):
    """Adiciona um novo canal para monitoramento com referência do último vídeo."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO channels (uid, name, category, content_type, last_video_ref)
            VALUES (?, ?, ?, ?, ?)
        """, (str(uid).strip(), name.strip(), category, content_type, last_video_ref))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao adicionar canal: {e}")
        return False
    finally:
        conn.close()

def remove_channel(uid):
    """Remove um canal."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM channels WHERE uid = ?", (str(uid).strip(),))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao remover canal: {e}")
        return False
    finally:
        conn.close()

def get_channels(category=None, content_type=None):
    """Retorna a lista de canais (ignora a categoria para unificação de canais)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if content_type:
            cursor.execute("""
                SELECT * FROM channels 
                WHERE content_type = ?
                ORDER BY name ASC
            """, (content_type,))
        else:
            cursor.execute("SELECT * FROM channels ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# ----------------- OPERAÇÕES DE HISTÓRICO DE VÍDEOS (FILA / MAPS) -----------------

def is_video_processed(bvid):
    """Verifica se um vídeo já foi mapeado/processado."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM processed_videos WHERE bvid = ?", (bvid,))
        return cursor.fetchone() is not None
    finally:
        conn.close()

def register_video(bvid, title, channel_uid=None, source="channel", category="shorts", content_type="anime", status="pending", published_at=None):
    """Registra um vídeo no histórico."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO processed_videos (bvid, title, channel_uid, source, category, content_type, status, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (bvid, title, channel_uid, source, category, content_type, status, published_at))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao registrar vídeo: {e}")
        return False
    finally:
        conn.close()

def get_pending_videos(category, content_type):
    """Retorna os vídeos prontos (baixados/no Drive) para postagem, ou seja, na fila 'Próximo a Postar'."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT pv.*, c.name as channel_name 
            FROM processed_videos pv
            LEFT JOIN channels c ON pv.channel_uid = c.uid
            WHERE pv.category = ? AND pv.content_type = ? AND pv.status = 'downloaded'
            ORDER BY pv.created_at ASC
        """, (category, content_type))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_unposted_videos(category, content_type):
    """Retorna todos os vídeos mapeados/baixados que ainda não foram postados (status != 'posted')."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT pv.*, c.name as channel_name 
            FROM processed_videos pv
            LEFT JOIN channels c ON pv.channel_uid = c.uid
            WHERE pv.category = ? AND pv.content_type = ? AND pv.status != 'posted'
            ORDER BY CASE WHEN pv.status = 'downloaded' THEN 0 ELSE 1 END, pv.created_at ASC
        """, (category, content_type))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def mark_video_as_posted(bvid):
    """Marca um vídeo da fila como 'posted' (já publicado pelo usuário nas redes)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE processed_videos 
            SET status = 'posted', posted_at = ? 
            WHERE bvid = ?
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bvid))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao marcar vídeo como postado: {e}")
        return False
    finally:
        conn.close()

def update_video_status(bvid, status):
    """Atualiza o status de um vídeo em processed_videos."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE processed_videos SET status = ? WHERE bvid = ?", (status, bvid))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao atualizar status do vídeo: {e}")
        return False
    finally:
        conn.close()

def get_video_by_bvid(bvid):
    """Retorna os dados de um vídeo em processed_videos."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM processed_videos WHERE bvid = ?", (bvid,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def remove_video_from_queue(bvid):
    """Remove o vídeo do histórico/fila completamente."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM processed_videos WHERE bvid = ?", (bvid,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao deletar vídeo da fila: {e}")
        return False
    finally:
        conn.close()

def get_posted_videos_count_since(days=7):
    """Retorna a quantidade de vídeos postados nos últimos X dias."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        date_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            SELECT COUNT(*) as count FROM processed_videos 
            WHERE status = 'posted' AND posted_at >= ?
        """, (date_limit,))
        row = cursor.fetchone()
        return row["count"] if row else 0
    finally:
        conn.close()

def get_downloaded_count_since_last_post(category, content_type):
    """
    Retorna quantos vídeos foram baixados (fila) desde a última postagem.
    Se não houver postagens anteriores, retorna todos os que estão baixados.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Pega a data da última postagem
        cursor.execute("""
            SELECT posted_at FROM processed_videos 
            WHERE category = ? AND content_type = ? AND status = 'posted'
            ORDER BY posted_at DESC LIMIT 1
        """, (category, content_type))
        row = cursor.fetchone()
        
        if row and row["posted_at"]:
            last_post_time = row["posted_at"]
            cursor.execute("""
                SELECT COUNT(*) as count FROM processed_videos 
                WHERE category = ? AND content_type = ? AND status = 'downloaded' AND created_at > ?
            """, (category, content_type, last_post_time))
        else:
            # Se nunca postou, conta todos na fila
            cursor.execute("""
                SELECT COUNT(*) as count FROM processed_videos 
                WHERE category = ? AND content_type = ? AND status = 'downloaded'
            """, (category, content_type))
            
        res = cursor.fetchone()
        return res["count"] if res else 0
    finally:
        conn.close()

# ----------------- OPERAÇÕES DE BUSCA GERAL (TRIAGEM WEB) -----------------

def add_search_results(results, content_type="anime"):
    """Adiciona novos resultados da busca geral na tabela de triagem."""
    conn = get_connection()
    cursor = conn.cursor()
    inserted = 0
    try:
        for r in results:
            cursor.execute("""
                INSERT OR IGNORE INTO search_results (
                    bvid, title, author, pic, duration_seconds, views, likes, hype_score, published_at, status, content_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (
                r["bvid"], r["title"], r["author"], r["pic"], r["duration_seconds"],
                r["views"], r["likes"], r["hype_score"], r["published_at"], content_type
            ))
            if cursor.rowcount > 0:
                inserted += 1
        conn.commit()
        return inserted
    except Exception as e:
        print(f"Erro ao salvar resultados da busca: {e}")
        return 0
    finally:
        conn.close()

def get_search_results(status="pending", content_type="anime"):
    """Retorna os resultados de busca para triagem ordenados pelo Hype Score de forma decrescente."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM search_results 
            WHERE status = ? AND content_type = ?
            ORDER BY hype_score DESC, published_at DESC
        """, (status, content_type))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def update_search_result_status(bvid, status):
    """Atualiza o status de triagem do vídeo ('downloaded', 'ignored')."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE search_results SET status = ? WHERE bvid = ?", (status, bvid))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao atualizar status de triagem: {e}")
        return False
    finally:
        conn.close()

def clear_old_search_results(days=14):
    """Remove resultados de busca pendentes mais antigos que X dias para economizar espaço."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        limit_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("DELETE FROM search_results WHERE status = 'pending' AND created_at < ?", (limit_date,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao limpar buscas antigas: {e}")
        return False
    finally:
        conn.close()

def delete_absent_search_results(active_bvids, content_type="anime"):
    """Remove resultados de busca pendentes que não estão na lista de bvids coletados."""
    if not active_bvids:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    try:
        placeholders = ",".join("?" for _ in active_bvids)
        query = f"""
            DELETE FROM search_results 
            WHERE status = 'pending' 
              AND content_type = ? 
              AND bvid NOT IN ({placeholders})
        """
        cursor.execute(query, [content_type] + active_bvids)
        deleted = cursor.rowcount
        conn.commit()
        return deleted
    except Exception as e:
        print(f"Erro ao remover resultados de busca ausentes: {e}")
        return 0
    finally:
        conn.close()

def clean_database():
    """Limpa todo o histórico, canais, buscas, atualizações de canais e sessões web."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM processed_videos")
        cursor.execute("DELETE FROM channels")
        cursor.execute("DELETE FROM search_results")
        cursor.execute("DELETE FROM channel_updates")
        cursor.execute("DELETE FROM web_sessions")
        conn.commit()
        return True
    finally:
        conn.close()

def update_channel_ref(uid, last_video_ref):
    """Atualiza a referência do último vídeo processado do canal."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE channels SET last_video_ref = ? WHERE uid = ?", (last_video_ref, str(uid).strip()))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao atualizar referência do canal: {e}")
        return False
    finally:
        conn.close()

# ----------------- OPERAÇÕES DE ATUALIZAÇÕES DOS CANAIS (TRIAGEM CANAIS) -----------------

def add_channel_update(bvid, title, author, pic, duration_seconds, views, likes, published_at, content_type, channel_uid):
    """Adiciona uma nova postagem de canal para triagem temporária."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO channel_updates (
                bvid, title, author, pic, duration_seconds, views, likes, published_at, content_type, channel_uid, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (bvid, title, author, pic, duration_seconds, views, likes, published_at, content_type, channel_uid))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Erro ao adicionar atualização de canal: {e}")
        return False
    finally:
        conn.close()

def get_channel_updates(status="pending", content_type="anime"):
    """Retorna as atualizações recentes de canais pendentes de triagem."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM channel_updates 
            WHERE status = ? AND content_type = ?
            ORDER BY published_at DESC, created_at DESC
        """, (status, content_type))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def update_channel_update_status(bvid, status):
    """Atualiza o status do vídeo mapeado do canal (ex: 'ignored', 'in_cart')."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE channel_updates SET status = ? WHERE bvid = ?", (status, bvid))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao atualizar status do update de canal: {e}")
        return False
    finally:
        conn.close()

def remove_channel_update(bvid):
    """Remove a atualização da tabela temporária."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM channel_updates WHERE bvid = ?", (bvid,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao remover update do canal: {e}")
        return False
    finally:
        conn.close()

# ----------------- OPERAÇÕES DE TERMOS DE BUSCA -----------------

def add_search_term(term, content_type):
    """Adiciona um novo termo de busca para um tipo de conteúdo."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO search_terms (term, content_type)
            VALUES (?, ?)
        """, (term.strip(), content_type.strip()))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Erro ao adicionar termo de busca: {e}")
        return False
    finally:
        conn.close()

def remove_search_term(term_id):
    """Remove um termo de busca pelo ID."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM search_terms WHERE id = ?", (term_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Erro ao remover termo de busca: {e}")
        return False
    finally:
        conn.close()

def get_search_terms(content_type=None):
    """Retorna os termos de busca cadastrados."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if content_type:
            cursor.execute("SELECT * FROM search_terms WHERE content_type = ? ORDER BY term ASC", (content_type,))
        else:
            cursor.execute("SELECT * FROM search_terms ORDER BY content_type, term ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# ----------------- OPERAÇÕES DE SESSÃO WEB -----------------

def create_web_session(token, duration_minutes=30):
    """Cria uma nova sessão web ativa com expiração em X minutos."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        expires_at = (datetime.now() + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT OR REPLACE INTO web_sessions (token, expires_at)
            VALUES (?, ?)
        """, (token, expires_at))
        conn.commit()
        # Limpa as sessões expiradas ao mesmo tempo para manter o banco limpo
        cleanup_expired_sessions()
        return True
    except Exception as e:
        print(f"Erro ao criar sessão web: {e}")
        return False
    finally:
        conn.close()

def validate_web_session(token):
    """Verifica se a sessão é válida e não está expirada."""
    if not token:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            SELECT 1 FROM web_sessions 
            WHERE token = ? AND expires_at > ?
        """, (token, now_str))
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"Erro ao validar sessão web: {e}")
        return False
    finally:
        conn.close()

def renew_web_session(token, duration_minutes=30):
    """Estende a expiração de uma sessão ativa por mais X minutos."""
    if not token:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Primeiro verifica se a sessão ainda é válida (só renovamos sessões ativas)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("SELECT 1 FROM web_sessions WHERE token = ? AND expires_at > ?", (token, now_str))
        if not cursor.fetchone():
            return False
            
        new_expires_at = (datetime.now() + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE web_sessions SET expires_at = ? WHERE token = ?", (new_expires_at, token))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao renovar sessão web: {e}")
        return False
    finally:
        conn.close()

def cleanup_expired_sessions():
    """Remove sessões expiradas do banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("DELETE FROM web_sessions WHERE expires_at <= ?", (now_str,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao limpar sessões expiradas: {e}")
        return False
    finally:
        conn.close()


# ----------------- OPERAÇÕES DE CONFIGURAÇÕES DE PERFIL -----------------

def get_user_setting(key: str, default: str = None) -> str:
    """Retorna o valor de uma configuração em user_settings."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM user_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default
    except Exception as e:
        print(f"Erro ao obter configuração '{key}': {e}")
        return default
    finally:
        conn.close()

def set_user_setting(key: str, value: str) -> bool:
    """Define/atualiza o valor de uma configuração em user_settings."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO user_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (key, str(value), now_str))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao salvar configuração '{key}': {e}")
        return False
    finally:
        conn.close()


# ----------------- OPERAÇÕES DE COLEÇÕES DO DOUYIN -----------------

def upsert_douyin_collection(col: dict) -> bool:
    """Insere ou atualiza uma coleção do Douyin no banco."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO douyin_collections (
                mix_id, title_pt, title_zh, author, cover_url, total_episodes, autoposting, is_virtual, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mix_id) DO UPDATE SET
                title_pt = COALESCE(excluded.title_pt, douyin_collections.title_pt),
                title_zh = COALESCE(excluded.title_zh, douyin_collections.title_zh),
                author = COALESCE(excluded.author, douyin_collections.author),
                cover_url = COALESCE(excluded.cover_url, douyin_collections.cover_url),
                total_episodes = MAX(excluded.total_episodes, douyin_collections.total_episodes),
                autoposting = excluded.autoposting,
                status = excluded.status
        """, (
            str(col["mix_id"]),
            col.get("title_pt", col.get("title_zh", f"Coleção #{col['mix_id']}")),
            col.get("title_zh", ""),
            col.get("author", "Desconhecido"),
            col.get("cover_url", ""),
            col.get("total_episodes", 0),
            1 if col.get("autoposting", True) else 0,
            1 if col.get("is_virtual", False) else 0,
            col.get("status", "active")
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao inserir/atualizar coleção {col.get('mix_id')}: {e}")
        return False
    finally:
        conn.close()

def get_douyin_collections(status_filter: str = None) -> list[dict]:
    """Retorna todas as coleções cadastradas com estatísticas de episódios."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query = """
            SELECT 
                c.*,
                COUNT(e.id) as total_episodes_mapped,
                SUM(CASE WHEN e.status = 'posted' THEN 1 ELSE 0 END) as posted_count,
                SUM(CASE WHEN e.status = 'opaque_over_5min' THEN 1 ELSE 0 END) as opaque_count
            FROM douyin_collections c
            LEFT JOIN collection_episodes e ON c.mix_id = e.mix_id
        """
        params = []
        if status_filter:
            query += " WHERE c.status = ?"
            params.append(status_filter)

        query += " GROUP BY c.mix_id ORDER BY c.created_at DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Erro ao buscar coleções do Douyin: {e}")
        return []
    finally:
        conn.close()

def get_douyin_collection_by_id(mix_id: str) -> dict | None:
    """Retorna uma coleção específica pelo mix_id."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                c.*,
                COUNT(e.id) as total_episodes_mapped,
                SUM(CASE WHEN e.status = 'posted' THEN 1 ELSE 0 END) as posted_count,
                SUM(CASE WHEN e.status = 'opaque_over_5min' THEN 1 ELSE 0 END) as opaque_count
            FROM douyin_collections c
            LEFT JOIN collection_episodes e ON c.mix_id = e.mix_id
            WHERE c.mix_id = ?
            GROUP BY c.mix_id
        """, (str(mix_id),))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Erro ao buscar coleção {mix_id}: {e}")
        return None
    finally:
        conn.close()

def toggle_collection_autoposting(mix_id: str, new_state: bool = None) -> bool:
    """Inverte ou define o estado de autoposting (ON/OFF) da coleção."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if new_state is None:
            cursor.execute("UPDATE douyin_collections SET autoposting = CASE WHEN autoposting = 1 THEN 0 ELSE 1 END WHERE mix_id = ?", (str(mix_id),))
        else:
            val = 1 if new_state else 0
            cursor.execute("UPDATE douyin_collections SET autoposting = ? WHERE mix_id = ?", (val, str(mix_id)))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao alterar autoposting da coleção {mix_id}: {e}")
        return False
    finally:
        conn.close()

def update_collection_cover(mix_id: str, cover_url: str) -> bool:
    """Atualiza a imagem de capa de uma coleção."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE douyin_collections SET cover_url = ? WHERE mix_id = ?", (cover_url, str(mix_id)))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao atualizar capa da coleção {mix_id}: {e}")
        return False
    finally:
        conn.close()

def delete_douyin_collection(mix_id: str) -> bool:
    """Deleta uma coleção e seus episódios do banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM douyin_collections WHERE mix_id = ?", (str(mix_id),))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao deletar coleção {mix_id}: {e}")
        return False
    finally:
        conn.close()


# ----------------- OPERAÇÕES DE EPISÓDIOS DA COLEÇÃO -----------------

def upsert_collection_episode(ep: dict) -> bool:
    """Insere ou atualiza um episódio de uma coleção."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO collection_episodes (
                mix_id, episode_num, aweme_id, title, duration_seconds, likes, comments, cover_url, video_url, status, is_compilation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(aweme_id) DO UPDATE SET
                episode_num = COALESCE(excluded.episode_num, collection_episodes.episode_num),
                title = excluded.title,
                duration_seconds = excluded.duration_seconds,
                likes = excluded.likes,
                comments = excluded.comments,
                cover_url = COALESCE(excluded.cover_url, collection_episodes.cover_url),
                video_url = excluded.video_url,
                is_compilation = excluded.is_compilation
        """, (
            str(ep["mix_id"]),
            ep.get("episode_num"),
            str(ep["aweme_id"]),
            ep.get("title", ""),
            ep.get("duration_seconds", 0),
            ep.get("likes", 0),
            ep.get("comments", 0),
            ep.get("cover_url", ""),
            ep.get("video_url", ""),
            ep.get("status", "pending"),
            1 if ep.get("is_compilation", False) else 0
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao inserir/atualizar episódio {ep.get('aweme_id')}: {e}")
        return False
    finally:
        conn.close()

def get_collection_episodes(mix_id: str) -> list[dict]:
    """Retorna todos os episódios de uma coleção ordenados por número do episódio."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM collection_episodes
            WHERE mix_id = ?
            ORDER BY CASE WHEN episode_num IS NULL THEN 999999 ELSE episode_num END ASC, id ASC
        """, (str(mix_id),))
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Erro ao buscar episódios da coleção {mix_id}: {e}")
        return []
    finally:
        conn.close()

def get_episode_by_id(ep_id: int) -> dict | None:
    """Retorna um episódio pelo seu ID interno."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM collection_episodes WHERE id = ?", (ep_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Erro ao buscar episódio #{ep_id}: {e}")
        return None
    finally:
        conn.close()

def get_episodes_by_status(status: str) -> list:
    """Retorna todos os episódios com o status informado."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM collection_episodes WHERE status = ?", (status,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Erro ao buscar episódios com status '{status}': {e}")
        return []
    finally:
        conn.close()

def update_episode_status(ep_id: int, status: str, scheduled_at: str = None, posted_at: str = None) -> bool:
    """Atualiza o status e as datas de agendamento/publicação de um episódio."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        fields = ["status = ?"]
        params = [status]

        if scheduled_at:
            fields.append("scheduled_at = ?")
            params.append(scheduled_at)
        if posted_at:
            fields.append("posted_at = ?")
            params.append(posted_at)

        params.append(ep_id)
        query = f"UPDATE collection_episodes SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao atualizar status do episódio #{ep_id}: {e}")
        return False
    finally:
        conn.close()

def update_episode_posting_guide(ep_id: int, guide_data) -> bool:
    """Salva o guia de postagem (título PT, descrição, hashtags) no episódio."""
    if isinstance(guide_data, (dict, list)):
        guide_json_str = json.dumps(guide_data, ensure_ascii=False)
    else:
        guide_json_str = str(guide_data)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE collection_episodes SET posting_guide = ? WHERE id = ?", (guide_json_str, ep_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao atualizar guia de postagem do episódio #{ep_id}: {e}")
        return False
    finally:
        conn.close()

def upsert_douyin_profile(sec_uid: str, nickname: str, avatar_url: str = "", profile_url: str = "") -> bool:
    """Insere ou atualiza um perfil monitorado do Douyin."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO douyin_profiles (sec_uid, nickname, avatar_url, profile_url, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(sec_uid) DO UPDATE SET
                nickname = excluded.nickname,
                avatar_url = excluded.avatar_url,
                profile_url = excluded.profile_url,
                updated_at = CURRENT_TIMESTAMP
        """, (sec_uid, nickname, avatar_url, profile_url))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao inserir/atualizar perfil Douyin {sec_uid}: {e}")
        return False
    finally:
        conn.close()

def get_douyin_profiles() -> list[dict]:
    """Retorna todos os perfis monitorados do Douyin."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM douyin_profiles ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Erro ao buscar perfis Douyin: {e}")
        return []
    finally:
        conn.close()

def delete_douyin_profile(sec_uid: str) -> bool:
    """Deleta um perfil do Douyin."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM douyin_profiles WHERE sec_uid = ?", (sec_uid,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao deletar perfil Douyin {sec_uid}: {e}")
        return False
    finally:
        conn.close()


