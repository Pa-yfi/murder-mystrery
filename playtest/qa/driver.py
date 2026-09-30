"""رانندهٔ سریع و بی‌سر (headless): کلِ بازی از راهِ همان handle() — بدون شبیه‌سازِ دکمه‌ها.

صد برابر سریع‌تر از agentهای دکمه‌زن؛ برای soak، کارایی، تعادل (هزاران بازی) و هم‌روندی.
بازیکن‌ها ساده ولی معقول‌اند: نقش‌ها هدف می‌زنند یا عبور می‌کنند، شهر به مظنون‌ترین از روی سرنخ‌ها
رای می‌دهد (پرونده‌ی عمومی)، کارآگاه به نتیجه‌ی استعلامش، قاتل‌ها به بی‌گناه.
"""
from __future__ import annotations

import random
from typing import Dict, Optional

from karagah import bot
from karagah.bot import GAMES, handle
from karagah.clues import board_ranking
from karagah.models import Align, Phase


class VClock:
    """ساعتِ مجازی (جایگزینِ ماژول time در bot و engine)."""

    def __init__(self, start: float = 1_700_000_000.0):
        self.now = start

    def time(self) -> float:
        return self.now

    def advance(self, sec: float) -> None:
        self.now += sec


def install_clock(clock: VClock):
    from karagah import engine
    orig = (bot._time, engine._time)
    bot._time = clock
    engine._time = clock
    return orig


def restore_clock(orig) -> None:
    from karagah import engine
    bot._time, engine._time = orig


WIN_KEYS = (("شهر", "city"), ("قاتل", "killers"), ("جانی", "serial"), ("سپر", "scapegoat"))


def team_of(winner: Optional[str]) -> str:
    for k, v in WIN_KEYS:
        if winner and k in winner:
            return v
    return "none"


def play_fast(chat: int, n: int, scenario: str = "classic", seed: int = 0,
              clock: Optional[VClock] = None, max_steps: int = 400, smart: bool = True) -> Dict:
    """یک بازیِ کامل. خروجی: {winner, team, days, steps, errors}."""
    rng = random.Random(seed * 7919 + n * 31 + abs(chat) % 997)
    base = abs(chat) * 100
    uids = [base + i for i in range(1, n + 1)]
    errors = []

    def call(cmd, uid=0, arg=""):
        r = handle(cmd, chat, uid, f"P{uid % 100}", arg)
        if "خطای داخلی" in (r.get("text") or ""):
            errors.append((cmd, arg, r["text"][:80]))
        if clock:
            clock.advance(1)
        return r

    call("new", uids[0])
    if scenario != "classic":
        call("scenario", uids[0], scenario)
    for u in uids[1:]:
        call("join", u)
    call("startgame", uids[0], "force")
    g = GAMES.get(chat)
    if g is None or g.s.phase is not Phase.NIGHT:
        return {"winner": None, "team": "none", "days": 0, "steps": 0, "errors": errors + [("start", "", "")]}
    dirty: Dict[int, set] = {}
    steps = 0
    while g.s.phase is not Phase.END and steps < max_steps:
        steps += 1
        ph = g.s.phase
        if ph in (Phase.NIGHT, Phase.INTERROGATION):
            for u in list(g.pending_actors()):
                if g.s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
                    break
                legal = g.legal_targets(u)
                p = g.s.players[u]
                if g._officer_on_duty(u):
                    if g.s.suspect_uid:
                        call("ask", u, "دیشب کجا بودی؟")
                    call("pass", u)
                elif legal and rng.random() < 0.9:
                    if p.align is Align.KILLER:
                        legal = [t for t in legal if g.s.players[t].align is not Align.KILLER] or legal
                    call("act", u, str(rng.choice(legal)))
                else:
                    call("pass", u)
            if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
                call("dawn")                         # سیستم (uid=0)
            for p in g.s.players.values():            # یافته‌های کارآگاه
                for note in p.notes:
                    if "→ مشکوک" in note:
                        name = note.split(": ", 1)[1].split(" →")[0]
                        dirty.setdefault(p.uid, set()).update(
                            q.uid for q in g.s.players.values() if q.name == name)
        elif ph is Phase.MORNING:
            if g.awaiting_verdict():
                off = g.s.officer_uid
                sus = g.s.suspect_uid
                if g.officer_can_judge():
                    guilty = _suspicion(g, sus, dirty) >= 1 or rng.random() < 0.3
                    call("verdict", off, f"{sus}:{1 if guilty else 0}")
                else:
                    g.s.deadline = 0
                    call("tick")
            else:
                call("discuss")
        elif ph is Phase.DISCUSSION:
            call("vote")
        elif ph is Phase.VOTE:
            voters = [p for p in g.s.alive_players() if p.can_vote]
            cands = [p.uid for p in g.s.alive_players() if p.can_speak]
            if g.s.tie_break and g.s.tie_leaders:
                cands = list(g.s.tie_leaders)
            for v in voters:
                pool = [c for c in cands if c != v.uid]
                if not pool:
                    continue
                if v.align is Align.KILLER:
                    pool = [c for c in pool if g.s.players[c].align is not Align.KILLER] or pool
                    t = rng.choice(pool)
                elif smart:
                    t = max(pool, key=lambda c: (_suspicion(g, c, dirty, v.uid), rng.random()))
                    if _suspicion(g, t, dirty, v.uid) <= 0 and rng.random() < 0.5:
                        t = 0
                else:
                    t = rng.choice(pool + [0])
                call("castvote", v.uid, str(t))
            call("closevote")
        elif ph is Phase.JURY:
            sus = g.s.suspect_uid
            for p in g.s.alive_players():
                if p.can_vote and p.uid != sus:
                    acquit = _suspicion(g, sus, dirty, p.uid) < 1 if p.align is not Align.KILLER else \
                        g.s.players[sus].align is Align.KILLER
                    call("juryvote", p.uid, "1" if acquit else "0")
            call("closejury")
        else:
            break
    return {"winner": g.s.winner, "team": team_of(g.s.winner), "days": g.s.day,
            "steps": steps, "errors": errors, "finished": g.s.phase is Phase.END}


def _suspicion(g, uid, dirty, viewer: Optional[int] = None) -> float:
    if uid is None:
        return 0
    rank = {u: (sure, open_) for u, sure, open_ in board_ranking(g.s)}
    sure, open_ = rank.get(uid, (0, 0))
    sc = 2 * sure + 0.5 * open_
    if viewer is not None and uid in dirty.get(viewer, set()):
        sc += 5
    if any(uid in d for d in dirty.values()):
        sc += 1
    return sc
