import sqlite3
import os
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

