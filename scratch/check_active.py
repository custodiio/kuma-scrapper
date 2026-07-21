import sqlite3

db = "/app/scrapper_douyin/data/history.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT id, episode_num, aweme_id, video_url FROM collection_episodes "
    "WHERE mix_id='7661474265041045567' ORDER BY id LIMIT 5"
).fetchall()

for r in rows:
    print(f"id={r['id']} ep={r['episode_num']} aweme_id={r['aweme_id']} video_url={r['video_url']}")

conn.close()
