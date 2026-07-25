import sqlite3
conn = sqlite3.connect("data/signals.db")
conn.execute("DELETE FROM signals")
conn.commit()
conn.close()
print("DB cleared")