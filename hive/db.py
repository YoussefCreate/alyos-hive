"""SQLite store shared by every agent. One file, no server."""

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    summary TEXT,
    fetched_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new'          -- new | scouted
);
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY,
    signal_id INTEGER REFERENCES signals(id),
    title TEXT NOT NULL,
    problem TEXT,
    buyer TEXT,
    offer_type TEXT,
    evidence TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new'          -- new | scored | built | parked
);
CREATE TABLE IF NOT EXISTS scores (
    opportunity_id INTEGER PRIMARY KEY REFERENCES opportunities(id),
    demand INTEGER, competition INTEGER, cost INTEGER, fit INTEGER, speed INTEGER,
    total REAL NOT NULL,
    rationale TEXT
);
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER REFERENCES opportunities(id),
    channel TEXT,
    title TEXT NOT NULL,
    pitch TEXT,
    deliverables TEXT,
    price_usd REAL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',     -- pending | approved | rejected
    reviewed_at TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    agent TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def log(conn, agent, message):
    conn.execute("INSERT INTO events (ts, agent, message) VALUES (?, ?, ?)", (now(), agent, message))
    conn.commit()


def add_signal(conn, source, title, url, summary):
    cur = conn.execute(
        "INSERT OR IGNORE INTO signals (source, title, url, summary, fetched_at) VALUES (?, ?, ?, ?, ?)",
        (source, title, url, summary, now()),
    )
    conn.commit()
    return cur.rowcount == 1
