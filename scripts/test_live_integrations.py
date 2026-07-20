"""
Script de Validação Real: Conexão Direta com AnimeRecap e Post_recap.
"""

import os
import sys
import sqlite3
from datetime import datetime

print("--- 1. VERIFICANDO CONEXÃO COM ANIMERECAP ---")
animerecap_dir = r"D:\Applications\AnimeRecap"
if os.path.exists(animerecap_dir):
    print(f"✅ Diretório AnimeRecap encontrado em: {animerecap_dir}")
    if animerecap_dir not in sys.path:
        sys.path.insert(0, animerecap_dir)
    
    try:
        from bot import database as animerecap_db
        print("✅ Módulo bot.database do AnimeRecap importado com sucesso!")
        
        # Testa leitura do banco do AnimeRecap
        db_file = os.path.join(animerecap_dir, "bot", "pipeline.db")
        if os.path.exists(db_file):
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall()]
            conn.close()
            print(f"✅ Banco pipeline.db lido com sucesso! Tabelas encontradas: {tables}")
        else:
            print("ℹ️ Banco pipeline.db ainda não foi criado fisicamente.")
    except Exception as e:
        print(f"❌ Erro ao conectar ao AnimeRecap: {e}")
else:
    print("❌ Diretório AnimeRecap não encontrado.")

print("\n--- 2. VERIFICANDO CONEXÃO COM POST_RECAP ---")
post_recap_dir = r"D:\Applications\Post_recap"
if os.path.exists(post_recap_dir):
    print(f"✅ Diretório Post_recap encontrado em: {post_recap_dir}")
    if post_recap_dir not in sys.path:
        sys.path.insert(0, post_recap_dir)
        
    try:
        import db as post_db
        print("✅ Módulo db.py do Post_recap importado com sucesso!")
        
        # Testa leitura da tabela scheduled_posts no posts.db
        posts_db_file = os.path.join(post_recap_dir, "posts.db")
        if os.path.exists(posts_db_file):
            conn = sqlite3.connect(posts_db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM scheduled_posts;")
            count = cursor.fetchone()[0]
            cursor.execute("SELECT id, title_youtube, scheduled_time, status FROM scheduled_posts ORDER BY id DESC LIMIT 3;")
            recent = cursor.fetchall()
            conn.close()
            print(f"✅ Banco posts.db do Post_recap lido com SUCESSO! Total de agendamentos: {count}")
            print(f"📌 Últimos agendamentos registrados no Post_recap:")
            for r in recent:
                print(f"   - ID #{r[0]} | Título: '{r[1]}' | Horário: {r[2]} | Status: {r[3]}")
    except Exception as e:
        print(f"❌ Erro ao conectar ao Post_recap: {e}")
else:
    print("❌ Diretório Post_recap não encontrado.")
