import os, sqlite3
from pathlib import Path
DB_PATH = os.getenv('DATABASE_PATH', './data/mashhad.db')
def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c
def init_db():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS episodes(id INTEGER PRIMARY KEY, title TEXT NOT NULL, premise TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'idea', script TEXT, caption TEXT, hashtags TEXT, scheduled_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS metrics(id INTEGER PRIMARY KEY, day TEXT NOT NULL, followers INTEGER, reach INTEGER, reactions INTEGER, comments INTEGER, views INTEGER, watch_time REAL, source TEXT NOT NULL DEFAULT 'manual', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS story_bible(id INTEGER PRIMARY KEY CHECK(id=1), world_rules TEXT NOT NULL DEFAULT '', characters TEXT NOT NULL DEFAULT '', continuity TEXT NOT NULL DEFAULT '', forbidden_repeats TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS task_log(id INTEGER PRIMARY KEY, task TEXT NOT NULL, status TEXT NOT NULL, details TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        ''')
        c.execute("INSERT OR IGNORE INTO story_bible(id) VALUES(1)")
