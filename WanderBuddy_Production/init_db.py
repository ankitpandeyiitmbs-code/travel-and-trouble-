import sqlite3
import os

DB_PATH = 'wanderbuddy.db'
SCHEMA_PATH = 'schema.sql'

def init():
    print("🛠️ Initializing Database...")
    
    if os.path.exists(DB_PATH):
        print(f"⚠️ Removing existing database at {DB_PATH}")
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    
    conn.commit()
    conn.close()
    print("✅ Database schema initialized successfully.")

if __name__ == '__main__':
    init()
