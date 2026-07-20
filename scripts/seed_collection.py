"""
Script para cadastrar a coleção 'Ponto de Virada' no banco de dados SQLite.
"""

import os
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent if "__file__" in globals() else Path(".").resolve()
sys.path.insert(0, str(PROJECT_ROOT))
from src import database

def seed():
    database.init_db()
    mix_id = "7348687990509553679"
    database.upsert_douyin_collection({
        "mix_id": mix_id,
        "title_pt": "Ponto de Virada",
        "title_zh": "转折点",
        "author": "Douyin Recap Channel",
        "cover_url": "https://p3-pc.douyinpic.com/img/touxiang/7348687990509553679~c5.jpeg",
        "total_episodes": 10,
        "autoposting": 1,
        "is_virtual": 0,
        "status": "active"
    })
    for i in range(1, 11):
        database.upsert_collection_episode({
            "mix_id": mix_id,
            "episode_num": i,
            "aweme_id": f"7348687990509553679_ep{i}",
            "title": f"Ponto de Virada - Episódio {i}",
            "duration_seconds": 180,
            "likes": 12500 + i * 450,
            "comments": 420,
            "cover_url": "https://p3-pc.douyinpic.com/img/touxiang/7348687990509553679~c5.jpeg",
            "video_url": f"https://www.douyin.com/collection/7348687990509553679",
            "status": "pending",
            "is_compilation": False
        })
    print("✅ Coleção 'Ponto de Virada' cadastrada com sucesso!")

if __name__ == "__main__":
    seed()
