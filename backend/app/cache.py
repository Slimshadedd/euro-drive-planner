"""Tiny SQLite key/value cache with expiry, plus a table of collected live fares."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "var" / "cache.db"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, expires REAL)")
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS fares (
                route_id TEXT, travel_date TEXT, profile TEXT,
                price REAL, currency TEXT, departure TEXT, detail TEXT,
                fetched_at REAL,
                PRIMARY KEY (route_id, travel_date, profile))"""
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS collector_log (
                ts REAL, operator TEXT, route_id TEXT, travel_date TEXT, ok INTEGER, message TEXT)"""
        )
        _conn.commit()
    return _conn


def get(key: str):
    with _lock:
        row = _db().execute("SELECT v, expires FROM kv WHERE k=?", (key,)).fetchone()
    if not row or row[1] < time.time():
        return None
    return json.loads(row[0])


def put(key: str, value, ttl_s: float) -> None:
    with _lock:
        _db().execute(
            "INSERT OR REPLACE INTO kv (k, v, expires) VALUES (?,?,?)",
            (key, json.dumps(value), time.time() + ttl_s),
        )
        _db().commit()


def put_fare(route_id: str, travel_date: str, profile: str, price: float, currency: str,
             departure: str | None, detail: str | None) -> None:
    with _lock:
        _db().execute(
            "INSERT OR REPLACE INTO fares VALUES (?,?,?,?,?,?,?,?)",
            (route_id, travel_date, profile, price, currency, departure, detail, time.time()),
        )
        _db().commit()


def get_fare(route_id: str, travel_date: str, profile: str, max_age_s: float):
    with _lock:
        row = _db().execute(
            "SELECT price, currency, departure, detail, fetched_at FROM fares "
            "WHERE route_id=? AND travel_date=? AND profile=?",
            (route_id, travel_date, profile),
        ).fetchone()
    if not row or time.time() - row[4] > max_age_s:
        return None
    return {"price": row[0], "currency": row[1], "departure": row[2], "detail": row[3], "fetched_at": row[4]}


def log_collector(operator: str, route_id: str, travel_date: str, ok: bool, message: str) -> None:
    with _lock:
        _db().execute(
            "INSERT INTO collector_log VALUES (?,?,?,?,?,?)",
            (time.time(), operator, route_id, travel_date, int(ok), message[:500]),
        )
        _db().commit()


def recent_collector_log(limit: int = 50):
    with _lock:
        rows = _db().execute(
            "SELECT ts, operator, route_id, travel_date, ok, message FROM collector_log "
            "ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(zip(["ts", "operator", "route_id", "travel_date", "ok", "message"], r)) for r in rows]
