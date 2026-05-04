"""SQLite-backed task metadata store.

The two query functions accept caller-provided strings and embed them directly
into SQL. Bandit will flag both — but the actual untrusted input enters the
system several files upstream.
"""
import sqlite3

DB_PATH = "tasks.db"


def _conn():
    return sqlite3.connect(DB_PATH)


def get_task_by_name(task_name):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, payload FROM tasks WHERE name = '" + task_name + "'")
    row = cur.fetchone()
    conn.close()
    return row


def list_tasks_for_user(user_id):
    conn = _conn()
    cur = conn.cursor()
    query = "SELECT id, name FROM tasks WHERE user_id = '%s'" % user_id
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    return rows


def mark_running(task_id):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET status='running' WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
