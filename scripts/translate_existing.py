"""
Script para traduzir episódios existentes no banco de dados SQLite.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent if "__file__" in globals() else Path(".").resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src import database
from src.translator import translate_zh_to_pt

def translate_db():
    database.init_db()
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM collection_episodes")
    rows = cursor.fetchall()
    count = 0
    for r in rows:
        ep_id = r["id"]
        old_title = r["title"]
        new_title = translate_zh_to_pt(old_title)
        if new_title != old_title:
            cursor.execute("UPDATE collection_episodes SET title = ? WHERE id = ?", (new_title, ep_id))
            count += 1
    conn.commit()
    conn.close()
    print(f"✅ {count} episódios traduzidos com sucesso no banco SQLite!")

if __name__ == "__main__":
    translate_db()
