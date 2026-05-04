"""User authentication helpers backed by a local SQLite DB."""
import hashlib
import sqlite3

DB_PATH = "users.db"


def login(username, password):
    """Authenticate a user and return a session dict, or None on failure."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    query = "SELECT id, password_hash FROM users WHERE username = '" + username + "'"
    cur.execute(query)
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    user_id, stored = row
    if _hash_password(password) == stored:
        return {"user_id": user_id, "token": "sess_" + str(user_id)}
    return None


def _hash_password(raw):
    return hashlib.md5(raw.encode()).hexdigest()
