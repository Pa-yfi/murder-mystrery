"""لایه‌ی دیتابیس (SQLite/SQL) — پنل ادمین کاملاً روی SQL کار می‌کند."""
from __future__ import annotations
import os
import sqlite3
import time
from typing import Dict, List, Optional

DB_PATH = os.getenv("DB_PATH", "karagah.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    uid        INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    first_seen INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL,
    games      INTEGER DEFAULT 0,
    wins       INTEGER DEFAULT 0,
    xp         INTEGER DEFAULT 0,
    coins      INTEGER DEFAULT 0,
    banned     INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS games (
    chat_id    INTEGER PRIMARY KEY,
    owner      INTEGER,
    case_id    INTEGER,
    case_title TEXT,
    phase      TEXT,
    day        INTEGER DEFAULT 0,
    players    INTEGER DEFAULT 0,
    winner     TEXT,
    started_at INTEGER,
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS players (
    chat_id  INTEGER NOT NULL,
    uid      INTEGER NOT NULL,
    name     TEXT,
    role     TEXT,
    align    TEXT,
    custody  TEXT,
    alive    INTEGER DEFAULT 1,
    stress   INTEGER DEFAULT 0,
    xp       INTEGER DEFAULT 0,
    coins    INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, uid)
);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    uid     INTEGER,
    kind    TEXT,
    detail  TEXT,
    ts      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(uid);
CREATE INDEX IF NOT EXISTS idx_players_uid ON players(uid);
CREATE TABLE IF NOT EXISTS season_xp (          -- ایده ۲۰
    uid INTEGER NOT NULL, season TEXT NOT NULL, xp INTEGER DEFAULT 0,
    PRIMARY KEY (uid, season)
);
CREATE TABLE IF NOT EXISTS achievements (       -- ایده ۱۸
    uid INTEGER NOT NULL, key TEXT NOT NULL, ts INTEGER,
    PRIMARY KEY (uid, key)
);
CREATE TABLE IF NOT EXISTS missions (           -- ایده ۱۹
    uid INTEGER NOT NULL, day TEXT NOT NULL, key TEXT NOT NULL, done INTEGER DEFAULT 0,
    PRIMARY KEY (uid, day, key)
);
CREATE TABLE IF NOT EXISTS accuracy (           -- ایده ۱۶
    uid INTEGER PRIMARY KEY, hits INTEGER DEFAULT 0, total INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS snapshots (
    chat_id INTEGER PRIMARY KEY,
    blob    BLOB NOT NULL,
    ts      INTEGER NOT NULL
);
"""

_conn: Optional[sqlite3.Connection] = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def reset(path: str = ":memory:") -> None:
    """برای تست: دیتابیس تازه در حافظه."""
    global _conn, DB_PATH
    if _conn:
        _conn.close()
    _conn = None
    DB_PATH = path
    conn()


def _now() -> int:
    return int(time.time())


# ---------------- نوشتن ----------------
def touch_user(uid: int, name: str) -> None:
    if not uid:
        return
    conn().execute(
        "INSERT INTO users(uid,name,first_seen,last_seen) VALUES(?,?,?,?) "
        "ON CONFLICT(uid) DO UPDATE SET name=excluded.name, last_seen=excluded.last_seen",
        (uid, name or f"user{uid}", _now(), _now()))
    conn().commit()


def save_game(g) -> None:
    """کل وضعیت بازی را در SQL آینه می‌کند تا پنل ادمین همیشه به‌روز باشد."""
    s = g.s
    conn().execute(
        "INSERT INTO games(chat_id,owner,case_id,case_title,phase,day,players,winner,started_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET "
        "owner=excluded.owner, phase=excluded.phase, day=excluded.day, players=excluded.players, "
        "winner=excluded.winner, case_id=excluded.case_id, case_title=excluded.case_title, "
        "updated_at=excluded.updated_at",
        (s.chat_id, getattr(g, "owner", 0), s.case.cid if s.case else None,
         s.case.title if s.case else None, s.phase.value, s.day,
         len(s.players), s.winner, _now(), _now()))
    for p in s.players.values():
        conn().execute(
            "INSERT INTO players(chat_id,uid,name,role,align,custody,alive,stress,xp,coins) "
            "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(chat_id,uid) DO UPDATE SET "
            "name=excluded.name, role=excluded.role, align=excluded.align, custody=excluded.custody, "
            "alive=excluded.alive, stress=excluded.stress, xp=excluded.xp, coins=excluded.coins",
            (s.chat_id, p.uid, p.name, p.role, p.align.value, p.custody.value,
             int(p.alive), p.stress, p.xp, p.coins))
        touch_user(p.uid, p.name)
    conn().commit()


def log_event(chat_id: int, uid: int, kind: str, detail: str = "") -> None:
    conn().execute("INSERT INTO events(chat_id,uid,kind,detail,ts) VALUES(?,?,?,?,?)",
                   (chat_id, uid, kind, detail[:300], _now()))
    conn().commit()


def ban(uid: int, flag: bool = True) -> None:
    conn().execute("UPDATE users SET banned=? WHERE uid=?", (int(flag), uid))
    conn().commit()


def is_banned(uid: int) -> bool:
    r = conn().execute("SELECT banned FROM users WHERE uid=?", (uid,)).fetchone()
    return bool(r and r["banned"])


# ---------------- کوئری‌های پنل ادمین (SQL خالص) ----------------
def q_active_games() -> List[sqlite3.Row]:
    return conn().execute(
        "SELECT chat_id, owner, phase, day, players, case_title, winner "
        "FROM games ORDER BY updated_at DESC LIMIT 50").fetchall()


def q_users(limit: int = 50) -> List[sqlite3.Row]:
    return conn().execute(
        "SELECT u.uid, u.name, u.xp, u.coins, u.banned, "
        "  (SELECT COUNT(*) FROM players p WHERE p.uid=u.uid) AS in_games "
        "FROM users u ORDER BY u.last_seen DESC LIMIT ?", (limit,)).fetchall()


def q_user(uid: int) -> Optional[sqlite3.Row]:
    return conn().execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()


def q_user_games(uid: int) -> List[sqlite3.Row]:
    return conn().execute(
        "SELECT p.chat_id, p.role, p.align, p.custody, p.alive, p.stress, p.xp, "
        "       g.phase, g.day, g.case_title, g.winner "
        "FROM players p JOIN games g ON g.chat_id = p.chat_id "
        "WHERE p.uid = ? ORDER BY g.updated_at DESC LIMIT 10", (uid,)).fetchall()


def q_user_events(uid: int, limit: int = 8) -> List[sqlite3.Row]:
    return conn().execute(
        "SELECT kind, detail, ts FROM events WHERE uid=? ORDER BY id DESC LIMIT ?",
        (uid, limit)).fetchall()


def q_stats() -> Dict:
    c = conn()
    one = lambda sql: c.execute(sql).fetchone()[0]
    return {
        "users": one("SELECT COUNT(*) FROM users"),
        "games": one("SELECT COUNT(*) FROM games"),
        "active": one("SELECT COUNT(*) FROM games WHERE winner IS NULL"),
        "events": one("SELECT COUNT(*) FROM events"),
        "banned": one("SELECT COUNT(*) FROM users WHERE banned=1"),
        "top": c.execute("SELECT name, xp FROM users ORDER BY xp DESC LIMIT 3").fetchall(),
    }


# ---------------- بازیابی بعد از ری‌استارت (Crash Recovery) ----------------
import pickle


def save_snapshot(chat_id: int, game) -> None:
    """کل شیء بازی را ذخیره می‌کند تا بعد از ری‌استارتِ ربات، بازی گم نشود."""
    blob = pickle.dumps(game, protocol=pickle.HIGHEST_PROTOCOL)
    conn().execute(
        "INSERT INTO snapshots(chat_id, blob, ts) VALUES(?,?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET blob=excluded.blob, ts=excluded.ts",
        (chat_id, blob, _now()))
    conn().commit()


def load_snapshots() -> Dict[int, object]:
    """در استارتاپ: همه‌ی بازی‌های ناتمام را برمی‌گرداند."""
    out = {}
    for r in conn().execute("SELECT chat_id, blob FROM snapshots").fetchall():
        try:
            out[r["chat_id"]] = pickle.loads(r["blob"])
        except Exception:
            pass                      # اسنپ‌شات خراب → نادیده
    return out


def drop_snapshot(chat_id: int) -> None:
    conn().execute("DELETE FROM snapshots WHERE chat_id=?", (chat_id,))
    conn().commit()


# ---------------- ایده‌های ۱۵-۲۰ و ۲۵ ----------------
import datetime

ACHIEVEMENTS = {
    "first_win": "🏆 اولین برد",
    "mvp": "⭐ MVP بازی",
    "scapegoat_win": "🎭 سپر بلای موفق",
    "sharp_eye": "🎯 چشم تیز (رای درست به قاتل)",
}
DAILY_MISSIONS = {"play": ("🎮 یک بازی کامل کن", 20), "win": ("🏆 یک برد بگیر", 40)}


def _season() -> str:
    d = datetime.date.today()
    return f"{d.year}-{d.month:02d}"


def _today() -> str:
    return datetime.date.today().isoformat()


def record_results(g) -> None:
    """در پایان بازی: برد/باخت، فصل، دقت رای، دستاورد و ماموریت‌ها را ثبت می‌کند."""
    s = g.s
    killers = {p.uid for p in s.players.values() if p.align.value == "قاتل‌ها"}
    for p in s.players.values():
        won = bool(s.winner) and (s.winner.startswith(p.align.value[:3]) or
                                  (p.role == "سپر بلا" and s.winner.startswith("سپر")))
        conn().execute("UPDATE users SET games=games+1, wins=wins+?, xp=xp+?, coins=coins+? WHERE uid=?",
                       (int(won), p.xp, p.coins, p.uid))
        conn().execute("INSERT INTO season_xp(uid,season,xp) VALUES(?,?,?) "
                       "ON CONFLICT(uid,season) DO UPDATE SET xp=xp+excluded.xp",
                       (p.uid, _season(), p.xp))
        hits = sum(1 for _, v, t in s.vote_history if v == p.uid and t in killers)
        total = sum(1 for _, v, _t in s.vote_history if v == p.uid)
        conn().execute("INSERT INTO accuracy(uid,hits,total) VALUES(?,?,?) "
                       "ON CONFLICT(uid) DO UPDATE SET hits=hits+excluded.hits, total=total+excluded.total",
                       (p.uid, hits, total))
        _mission_done(p.uid, "play")
        if won:
            _mission_done(p.uid, "win")
            _award(p.uid, "first_win")
        if hits:
            _award(p.uid, "sharp_eye")
        if p.role == "سپر بلا" and s.winner and s.winner.startswith("سپر"):
            _award(p.uid, "scapegoat_win")
    if s.mvp:
        _award(s.mvp, "mvp")
    conn().commit()


def _award(uid: int, key: str) -> None:
    conn().execute("INSERT OR IGNORE INTO achievements(uid,key,ts) VALUES(?,?,?)", (uid, key, _now()))


def _mission_done(uid: int, key: str) -> None:
    row = conn().execute("SELECT done FROM missions WHERE uid=? AND day=? AND key=?",
                         (uid, _today(), key)).fetchone()
    if row and row["done"]:
        return
    conn().execute("INSERT INTO missions(uid,day,key,done) VALUES(?,?,?,1) "
                   "ON CONFLICT(uid,day,key) DO UPDATE SET done=1", (uid, _today(), key))
    conn().execute("UPDATE users SET coins=coins+? WHERE uid=?", (DAILY_MISSIONS[key][1], uid))


def q_top(limit: int = 10):                       # ایده ۱۵
    return conn().execute("SELECT name, xp, wins, games FROM users ORDER BY xp DESC LIMIT ?",
                          (limit,)).fetchall()


def q_league(limit: int = 10):                    # ایده ۲۵
    return conn().execute(
        "SELECT chat_id, COUNT(DISTINCT uid) n, SUM(xp) sx FROM players "
        "GROUP BY chat_id ORDER BY sx DESC LIMIT ?", (limit,)).fetchall()


def q_season(limit: int = 10):                    # ایده ۲۰
    return conn().execute(
        "SELECT u.name, s.xp FROM season_xp s JOIN users u ON u.uid=s.uid "
        "WHERE s.season=? ORDER BY s.xp DESC LIMIT ?", (_season(), limit)).fetchall()


def q_accuracy(uid: int):                         # ایده ۱۶
    return conn().execute("SELECT hits, total FROM accuracy WHERE uid=?", (uid,)).fetchone()


def q_achievements(uid: int):
    return [r["key"] for r in conn().execute(
        "SELECT key FROM achievements WHERE uid=?", (uid,)).fetchall()]


def q_missions(uid: int):
    rows = conn().execute("SELECT key, done FROM missions WHERE uid=? AND day=?",
                          (uid, _today())).fetchall()
    done = {r["key"] for r in rows if r["done"]}
    return [(k, DAILY_MISSIONS[k][0], DAILY_MISSIONS[k][1], k in done) for k in DAILY_MISSIONS]
