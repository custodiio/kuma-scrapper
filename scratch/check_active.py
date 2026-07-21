import sqlite3

db = "/app/scrapper_douyin/data/history.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

print("=== Episódios da coleção 绘制地下城的画家 (mix_id=7661474265041045567) ===")
rows = conn.execute(
    "SELECT id, episode_num, status, title FROM collection_episodes "
    "WHERE mix_id='7661474265041045567' ORDER BY id"
).fetchall()
for r in rows:
    print(f"  DB id=#{r['id']} | episode_num={r['episode_num']} | status={r['status']} | titulo={r['title'][:50]}")

conn.close()
