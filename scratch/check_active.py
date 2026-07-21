import sqlite3

db_path = "/app/scrapper_douyin/data/history.db"
conn = sqlite3.connect(db_path)

# Zera os 3 episódios que estão com processing_dubbing (ids 1, 17, 18)
ids_to_reset = [1, 17, 18]
for ep_id in ids_to_reset:
    conn.execute("UPDATE collection_episodes SET status='pending' WHERE id=?", (ep_id,))
    print(f"Episódio #{ep_id} -> status RESETADO para 'pending'")

conn.commit()
conn.close()
print("\nPronto! Todos os episódios foram zerados para 'pending'.")
