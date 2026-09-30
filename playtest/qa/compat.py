"""📱 Platform & Compatibility (Telegram Bot API «certification»):

- سقف‌ها: متن ≤ ۴۰۹۶ (یا تکه‌تکه با chunks)، callback_data ≤ ۶۴ بایت، ≤ ۸ دکمه در سطر، ≤ ۱۰۰ دکمه
- Markdownِ قدیمیِ تلگرام: هر پیام باید *، _، ` و [ ] متوازن داشته باشد — حتی وقتی بازیکن در دفاع/وصیت/پرسش
  کاراکترهای ویژه تایپ کرده؛ وگرنه آداپتور به متن ساده برمی‌گردد (قالب‌بندی می‌پرد)
- «Suspend/Resume»: ری‌استارتِ ربات در هر فاز (اسنپ‌شات → بازیابی → ادامه تا پایان)
- ارتقای گروه به سوپرگروه (عوض شدنِ chat_id) وسط بازی
- توقف/ادامه‌ی میزبان مهلتِ باقی‌مانده را نگه می‌دارد
"""
from __future__ import annotations

import random
import re

from karagah import bot, db, ui
from karagah.bot import GAMES, handle
from karagah.models import Phase

from .common import Section, capture_sessions, fresh, timed
from .driver import VClock, install_clock, play_fast, restore_clock

LIMIT_TEXT, LIMIT_CB, LIMIT_ROW, LIMIT_BUTTONS = 4096, 64, 8, 100


def md_ok(text: str) -> bool:
    """اعتبارسنجِ ساده‌ی Markdownِ قدیمیِ تلگرام (parse_mode=Markdown)."""
    t = re.sub(r"`[^`]*`", "", text)                     # کدِ درون‌خطی
    t = re.sub(r"\[[^\]]*\]\([^)]*\)", "", t)            # لینک
    t = t.replace("\\*", "").replace("\\_", "")
    return t.count("*") % 2 == 0 and t.count("_") % 2 == 0 and t.count("`") % 2 == 0 \
        and t.count("[") == t.count("]")


def limits(sec: Section, msgs) -> None:
    from karagah.telegram_app import chunks
    too_long = [m for m in msgs if len(m.text) > LIMIT_TEXT]
    bad_chunks = [m for m in too_long if any(len(c) > LIMIT_TEXT for c in chunks(m.text))]
    cbs, rows_bad, many = set(), 0, 0
    for m in msgs:
        kb = (m.keyboard or {}).get("inline_keyboard") or []
        rows_bad += sum(1 for r in kb if len(r) > LIMIT_ROW)
        many += int(sum(len(r) for r in kb) > LIMIT_BUTTONS)
        for r in kb:
            for b in r:
                if b.get("callback_data"):
                    cbs.add(b["callback_data"])
                if not b.get("text"):
                    sec.fail(f"دکمه‌ی بی‌متن: {b}")
    big_cb = [c for c in cbs if len(c.encode()) > LIMIT_CB]
    sec.metrics["messages_checked"] = len(msgs)
    sec.metrics["longest_message_chars"] = max((len(m.text) for m in msgs), default=0)
    sec.metrics["messages_over_4096 (sent in chunks)"] = len(too_long)
    sec.metrics["distinct_callback_data / max_bytes"] = f"{len(cbs)} / {max((len(c.encode()) for c in cbs), default=0)}"
    sec.check(not bad_chunks, f"{len(bad_chunks)} پیام حتی تکه‌تکه هم بیش از ۴۰۹۶")
    sec.check(not big_cb, f"callback_data بیش از ۶۴ بایت: {big_cb[:3]}")
    sec.check(rows_bad == 0 and many == 0, f"سطرِ بیش از ۸ دکمه: {rows_bad}، کیبوردِ بیش از ۱۰۰: {many}")
    md_bad = [m for m in msgs if not md_ok(m.text)]
    sec.metrics["markdown_unbalanced"] = len(md_bad)
    sec.check(not md_bad, f"{len(md_bad)} پیام Markdownِ نامتوازن دارد (مثال: {md_bad[0].text[:80]!r})"
              if md_bad else "")


def worst_board(sec: Section) -> None:
    """بلندترین بازیِ ممکن: پرونده‌ی روزهای آخر چقدر بلند می‌شود؟"""
    fresh()
    clock = VClock()
    o = install_clock(clock)
    longest = 0
    try:
        for i in range(12):
            play_fast(-(880_000 + i), 10, "chaos", i, clock, smart=False, max_steps=800)
            g = GAMES[-(880_000 + i)]
            longest = max(longest, len(ui.board(g.s)), len(ui.case_intro(g.s)))
    finally:
        restore_clock(o)
    sec.metrics["longest_board_chars (12 long chaos games)"] = longest


def hostile_text(sec: Section) -> None:
    """بازیکن در دفاع/وصیت/پرسش/یادداشت کاراکترهای Markdown تایپ می‌کند؛ پیام‌های عمومی سالم می‌مانند؟"""
    fresh()
    G = -660066
    handle("new", G, 1, "Host")
    for u in range(2, 8):
        handle("join", G, u, f"P{u}")
    handle("startgame", G, 1, "force")
    g = GAMES[G]
    nasty = "*bold _it `code [link](http://x) ~~ ||spoiler|| \\"
    outs = []
    for u in g.s.players:
        bot.await_text(u, G, "will")
        outs.append(handle("will", G, u, "", nasty))
    handle("dawn", G)
    handle("discuss", G)
    handle("vote", G)
    sus = next(p.uid for p in g.s.alive_players() if p.uid != g.s.officer_uid)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != sus:
            handle("castvote", G, p.uid, "", str(sus))
    outs.append(handle("closevote", G))
    outs.append(handle("defense", G, sus, "", nasty))
    outs.append(handle("ask", G, g.s.officer_uid, "", nasty))
    outs.append(handle("answer", G, sus, "", nasty))
    handle("dawn", G)
    outs.append(handle("dashboard", G))
    outs.append(handle("end", G))
    texts = [o.get("text", "") for o in outs] + [m["text"] for o in outs for m in o.get("outbox") or []]
    texts += g.s.log
    bad = [t for t in texts if not md_ok(t)]
    sec.metrics["hostile_text_messages"] = len(texts)
    sec.check(not bad, f"متنِ بازیکن Markdown را شکست ({len(bad)}): {bad[0][:90]!r}" if bad else "")


def restart_every_phase(sec: Section) -> None:
    """برای هر فاز: وسطش ربات ری‌استارت می‌شود (فقط SQLite می‌ماند) و بازی تا پایان ادامه دارد."""
    seen = set()
    for i in range(18):
        fresh()
        clock = VClock()
        o = install_clock(clock)
        try:
            G = -(870_000 + i)
            rng = random.Random(i)
            handle("new", G, 1, "Host")
            for u in range(2, 9):
                handle("join", G, u, f"P{u}")
            handle("startgame", G, 1, "force")
            target = (Phase.NIGHT, Phase.INTERROGATION, Phase.MORNING, Phase.DISCUSSION,
                      Phase.VOTE, Phase.JURY)[i % 6]
            if target is Phase.NIGHT and i >= 6:          # شبِ دوم به بعد، نه فقط شبِ اول
                target = Phase.NIGHT
            g = GAMES[G]
            for _ in range(80):
                if g.s.phase is target or g.s.phase is Phase.END:
                    break
                g.s.deadline = 0
                g.s.grace_day = g.s.day
                if g.s.phase is Phase.VOTE:
                    alive = [p.uid for p in g.s.alive_players() if p.can_speak]
                    for p in g.s.alive_players():
                        if p.can_vote:
                            handle("castvote", G, p.uid, "", str(rng.choice(alive)))
                handle("tick", G)
                clock.advance(5)
            if g.s.phase is Phase.END:
                continue
            ph = g.s.phase
            db.save_snapshot(G, g)
            GAMES.clear()
            bot._LOCKS.clear()
            bot.restore_games()
            g = GAMES[G]
            for _ in range(200):
                if g.s.phase is Phase.END:
                    break
                g.s.deadline = 0
                g.s.grace_day = g.s.day
                r = handle("tick", G)
                sec.check("خطای داخلی" not in r["text"], f"بعد از ری‌استارت در {ph.value}: {r['text'][:80]}")
                clock.advance(5)
            if sec.check(g.s.phase is Phase.END, f"بعد از ری‌استارت در «{ph.value}» بازی تمام نشد"):
                seen.add(ph.value)
        finally:
            restore_clock(o)
    sec.metrics["restart_ok_in_phases"] = "، ".join(sorted(seen))


def migration(sec: Section) -> None:
    fresh()
    old, new = -100_1, -100_999_1
    handle("new", old, 1, "Host")
    for u in range(2, 7):
        handle("join", old, u, f"P{u}")
    handle("startgame", old, 1, "force")
    bot.migrate_chat(old, new)
    sec.check(old not in GAMES and new in GAMES, "بازی به آیدیِ سوپرگروه منتقل نشد")
    r = handle("dashboard", new)
    sec.check(r["ok"], "بعد از ارتقای گروه، داشبورد کار نکرد")
    handle("dawn", new)
    sec.check(GAMES[new].s.phase is not Phase.NIGHT, "بعد از ارتقای گروه بازی جلو نرفت")
    snaps = db.load_snapshots()
    sec.check(old not in snaps and new in snaps, "اسنپ‌شاتِ آیدیِ قدیم/جدید درست نیست")


def pause_resume(sec: Section) -> None:
    fresh()
    clock = VClock()
    o = install_clock(clock)
    try:
        G = -550055
        handle("new", G, 1, "Host")
        for u in range(2, 7):
            handle("join", G, u, f"P{u}")
        handle("startgame", G, 1, "force")
        g = GAMES[G]
        clock.advance(20)
        left = g.remaining()
        handle("pause", G, 1)
        clock.advance(3600)                              # یک ساعت «suspend»
        handle("tick", G)
        sec.check(g.s.phase is Phase.NIGHT, "در توقف، تایمر فاز را جلو برد")
        handle("resume", G, 1)
        sec.check(abs((g.remaining() or 0) - left) <= 1, f"مهلت بعد از ادامه عوض شد: {left}→{g.remaining()}")
    finally:
        restore_clock(o)


def run(quick: bool = True) -> Section:
    sec = Section("Platform & Compatibility", "سقف‌های Bot API، Markdown، ری‌استارت در هر فاز، ارتقای گروه، توقف/ادامه")
    with timed(sec):
        configs = [(n, s, sc, m) for sc in ("classic", "court", "chaos") for n in ((4, 7, 10) if quick else range(4, 11))
                   for s in (1,) for m in (("group",) if quick else ("group", "dm", "timer"))]
        cap, games, _rep = capture_sessions(configs)
        limits(sec, cap.bot_msgs())
        for fn in (worst_board, hostile_text, restart_every_phase, migration, pause_resume):
            try:
                fn(sec)
            except Exception as e:                        # noqa: BLE001
                sec.fail(f"{fn.__name__}: {e!r}")
    sec.findings = [f for f in sec.findings if f]
    sec.passed = not sec.findings
    return sec
