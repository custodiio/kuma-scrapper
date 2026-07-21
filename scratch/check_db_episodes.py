import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import database

def main():
    cols = database.get_douyin_collections()
    print(f"Active collections count: {len(cols)}")
    for c in cols:
        mix_id = c.get("mix_id")
        title = c.get("title_pt")
        eps = database.get_collection_episodes(mix_id)
        print(f"Collection: '{title}' (mix_id: {mix_id}) -> {len(eps)} episodes")
        if eps:
            for ep in eps[:3]:
                print(f"  - EP {ep.get('episode_num')}: ID #{ep.get('id')} | Status: {ep.get('status')} | Title: {ep.get('title')[:40]}")

if __name__ == "__main__":
    main()
