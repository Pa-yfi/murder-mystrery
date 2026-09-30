"""اسکلتِ مشترکِ ماژول‌های QA: هر ماژول یک Section برمی‌گرداند."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from karagah import bot, db


@dataclass
class Section:
    kind: str                      # نوعِ آزمون (Smoke، Soak، …)
    title: str
    passed: bool = True
    metrics: Dict[str, Any] = field(default_factory=dict)
    findings: List[str] = field(default_factory=list)       # مشکلِ واقعی (شکست)
    notes: List[str] = field(default_factory=list)          # توضیح/مشاهده
    seconds: float = 0.0

    def fail(self, msg: str) -> None:
        self.passed = False
        self.findings.append(msg)

    def check(self, ok: bool, msg: str) -> bool:
        if not ok:
            self.fail(msg)
        return ok


def fresh(path: str = ":memory:") -> None:
    """وضعیتِ سراسریِ ربات را صفر کن (مثل ری‌استارت)."""
    logging.disable(logging.CRITICAL)
    db.reset(path)
    bot.GAMES.clear()
    for d in (bot._PENDING, bot._ACTIVE_TABLE, bot._LAST_CB, bot._LAST_CALL, bot.LAST_ROSTER, bot._LOCKS):
        d.clear()
    bot.RATE_LIMIT_ENABLED = False
    bot.REQUIRE_READY = False


class timed:
    def __init__(self, sec: Section):
        self.sec = sec

    def __enter__(self):
        self.t = time.perf_counter()
        return self.sec

    def __exit__(self, *exc):
        self.sec.seconds = round(time.perf_counter() - self.t, 2)
        return False


def pct(vals: List[float], q: float) -> float:
    if not vals:
        return 0.0
    v = sorted(vals)
    k = min(len(v) - 1, max(0, int(round(q / 100 * (len(v) - 1)))))
    return v[k]


class Capture:
    """همه‌ی پیام‌ها و تپ‌های جلسه‌های شبیه‌سازِ تلگرام (playtest.table) را جمع می‌کند."""

    def __init__(self):
        self.msgs = []           # Message
        self.presses = []        # (cmd, ok, text, t)
        self.edits = 0

    def __enter__(self):
        from playtest import table
        self._t = table
        self._init = table.Message.__init__
        self._press = table.Telegram.press
        cap = self

        def init(msg, *a, **k):
            cap._init(msg, *a, **k)
            cap.msgs.append(msg)

        def press(tg, uid, msg, button):
            r = cap._press(tg, uid, msg, button)
            data = button.get("callback_data") or button.get("url", "url")
            cap.presses.append((data.split(":")[0], bool(r and r.ok), (r.text[:120] if r else ""),
                                tg.clock.now))
            return r

        table.Message.__init__ = init
        table.Telegram.press = press
        return self

    def __exit__(self, *exc):
        self._t.Message.__init__ = self._init
        self._t.Telegram.press = self._press
        return False

    def bot_msgs(self):
        return [m for m in self.msgs if not m.cause.startswith("chat:")]


def capture_sessions(configs, talk: bool = True):
    """configs: [(n, seed, scenario, mode)] → Capture + خلاصه‌ی بازی‌ها."""
    from playtest.docs import read_all
    from playtest.game import run_session
    from playtest.report import Report
    rb = read_all()
    rep = Report()
    games = []
    with Capture() as cap:
        for n, seed, scen, mode in configs:
            games.append(run_session(n, seed, rep, rb, mode, scen, talk))
    return cap, games, rep
