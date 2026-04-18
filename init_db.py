"""
init_db.py — Initialize and seed the WanderBuddy database.
Run once: python init_db.py
"""
import sqlite3
import os

DB_PATH = os.environ.get("DATABASE_URL", "wanderbuddy.db")
SCHEMA  = "schema.sql"

def init_db():
    print(f"[init_db] Creating database: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    with open(SCHEMA, "r") as f:
        con.executescript(f.read())
    con.commit()
    con.close()
    print("[init_db] Schema applied ✓")

def seed():
    import seed_db
    seed_db.seed()
    print("[init_db] Seed data inserted ✓")

if __name__ == "__main__":
    init_db()
    seed()
    print("\n✅  Database ready! Run: python app.py")
    print("   Admin:  admin@travelandtrouble.com / Admin@123")
    print("   User:   user@test.com / User@123")
    print("   Vendor: vendor@test.com / Vendor@123")
