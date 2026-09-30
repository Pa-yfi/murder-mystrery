"""⚡ Performance: «فریم‌ریتِ» یک ربات تلگرامی = زمانِ پاسخِ هر تپ و زمانِ هر دورِ تایمر.

- تأخیرِ handle() برای هر فرمان (p50/p95/p99) در صدها بازی
- یک دورِ تایمر (tick + ساعت) روی ۲۰۰ میزِ هم‌زمان — باید خیلی کمتر از CLOCK_INTERVAL (۵ ثانیه) باشد
- اندازه و زمانِ ذخیره‌ی اسنپ‌شات، زمانِ ساختِ پرونده (board) در بزرگ‌ترین بازی
بودجه‌ها سخاوتمندانه‌اند (CI کند است) ولی ۱۰× پسرفت را می‌گیرند.
"""
from __future__ import annotations

import pickle
import time
from collections import defaultdict

from karagah import bot, db, ui
from karagah.bot import GAMES, handle
from karagah.models import Phase

from .common import Section, fresh, pct, timed
from .driver import VClock, install_clock, play_fast, restore_clock

BUDGET_P99_MS = 50.0
BUDGET_TICK_200_S = 1.0
BUDGET_SNAPSHOT_KB = 200


def _t(fn, sink, *a):
    t = time.perf_counter()
    r = fn(*a)
    sink.append((time.perf_counter() - t) * 1000)
    return r


def run(quick: bool = True) -> Section:
    sec = Section("Performance", "کارایی: تأخیرِ هر تپ، دورِ تایمر با ۲۰۰ میز، اسنپ‌شات")
    with timed(sec):
        fresh()
        lat = defaultdict(list)
        orig = bot.handle

        def timed_handle(cmd, chat, uid=0, name="", arg=""):
            t = time.perf_counter()
            r = orig(cmd, chat, uid, name, arg)
            lat[cmd].append((time.perf_counter() - t) * 1000)
            return r

        from playtest.qa import driver as D
        D.handle = timed_handle
        clock = VClock()
        o = install_clock(clock)
        games = 60 if quick else 400
        try:
            for i in range(games):
                play_fast(-(900_000 + i), 4 + i % 7, ("classic", "court", "chaos")[i % 3], i, clock)
        finally:
            D.handle = orig
            restore_clock(o)
        allv = [v for vs in lat.values() for v in vs]
        sec.metrics["handle_calls"] = len(allv)
        sec.metrics["handle_ms_p50/p95/p99"] = f"{pct(allv, 50):.2f} / {pct(allv, 95):.2f} / {pct(allv, 99):.2f}"
        slow = sorted(((pct(v, 99), k) for k, v in lat.items() if len(v) >= 20), reverse=True)[:5]
        sec.metrics["slowest_cmds_p99_ms"] = ", ".join(f"{k} {v:.1f}" for v, k in slow)
        sec.check(pct(allv, 99) < BUDGET_P99_MS, f"p99 تأخیر {pct(allv, 99):.1f}ms > {BUDGET_P99_MS}ms")

        # همان، ولی با SQLiteِ روی دیسک (مثل تولید: هر تپ save_game + اسنپ‌شات)
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "karagah_perf.db")
        fresh(path)
        disk = []
        D.handle = lambda cmd, chat, uid=0, name="", arg="": _t(orig, disk, cmd, chat, uid, name, arg)
        clock = VClock()
        o = install_clock(clock)
        try:
            for i in range(10 if quick else 60):
                play_fast(-(960_000 + i), 4 + i % 7, ("classic", "court", "chaos")[i % 3], i, clock)
        finally:
            D.handle = orig
            restore_clock(o)
        sec.metrics["handle_ms_on_disk_p50/p95/p99"] = f"{pct(disk, 50):.2f} / {pct(disk, 95):.2f} / {pct(disk, 99):.2f}"
        sec.metrics["db_file_kb"] = round(os.path.getsize(path) / 1024, 1)
        sec.check(pct(disk, 99) < BUDGET_P99_MS * 4, f"p99 روی دیسک {pct(disk, 99):.1f}ms")

        # ۲۰۰ میزِ هم‌زمان در شب: یک دورِ کاملِ تایمر
        fresh()
        clock = VClock()
        o = install_clock(clock)
        try:
            for i in range(200):
                c = -(950_000 + i)
                handle("new", c, c * -10, "H")
                for u in range(2, 9):
                    handle("join", c, c * -10 + u, f"P{u}")
                handle("startgame", c, c * -10, "force")
            t = time.perf_counter()
            for c in list(GAMES):
                handle("tick", c)
                bot.clock_view(c)
            dt = time.perf_counter() - t
            bot.gc()
        finally:
            restore_clock(o)
        sec.metrics["timer_round_200_tables_s"] = round(dt, 3)
        # همان دور با دیسک: تیکِ بی‌اتفاق نباید چیزی بنویسد
        path2 = os.path.join(tempfile.mkdtemp(), "karagah_tick.db")
        fresh(path2)
        o = install_clock(VClock())
        try:
            for i in range(200):
                c = -(970_000 + i)
                handle("new", c, c * -10, "H")
                for u in range(2, 9):
                    handle("join", c, c * -10 + u, f"P{u}")
                handle("startgame", c, c * -10, "force")
            size0 = os.path.getsize(path2)
            t = time.perf_counter()
            for c in list(GAMES):
                handle("tick", c)
            dt2 = time.perf_counter() - t
        finally:
            restore_clock(o)
        sec.metrics["timer_round_200_tables_on_disk_s"] = round(dt2, 3)
        sec.check(dt2 < BUDGET_TICK_200_S, f"دورِ تایمر روی دیسک {dt2:.2f}s")
        sec.check(os.path.getsize(path2) == size0, "تیکِ بی‌اتفاق روی دیسک نوشت")
        sec.check(dt < BUDGET_TICK_200_S, f"دورِ تایمر برای ۲۰۰ میز {dt:.2f}s")

        # بزرگ‌ترین بازی: اسنپ‌شات و پرونده
        fresh()
        clock = VClock()
        o = install_clock(clock)
        try:
            play_fast(-990_001, 10, "chaos", 3, clock, smart=False)
        finally:
            restore_clock(o)
        g = GAMES[-990_001]
        blob = pickle.dumps(g)
        t = time.perf_counter()
        for _ in range(20):
            db.save_snapshot(-990_001, g)
        save_ms = (time.perf_counter() - t) / 20 * 1000
        t = time.perf_counter()
        board = ui.board(g.s)
        board_ms = (time.perf_counter() - t) * 1000
        sec.metrics["snapshot_kb"] = round(len(blob) / 1024, 1)
        sec.metrics["snapshot_save_ms"] = round(save_ms, 2)
        sec.metrics["board_render_ms"] = round(board_ms, 2)
        sec.metrics["board_chars"] = len(board)
        sec.check(len(blob) / 1024 < BUDGET_SNAPSHOT_KB, f"اسنپ‌شات {len(blob) // 1024}KB")
    return sec
