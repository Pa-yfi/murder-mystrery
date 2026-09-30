"""🕰️ Soak / Longevity: ربات هفته‌ها روشن است. هزاران بازی در یک پروسه، ساعتِ مجازی جلو می‌رود.

دو اجرا:
  A) بدون پاک‌سازی (رفتارِ قبل از نسخه ۸) — نشان می‌دهد چه چیزی نشت می‌کرد
  B) با bot.gc() در تایمر — حافظه و دیکشنری‌های سراسری باید تخت بمانند
اندازه‌گیری: tracemalloc، اندازه‌ی GAMES/_LOCKS/_LAST_CALL/_LAST_CB/_PENDING/LAST_ROSTER،
تعداد اسنپ‌شات‌ها در SQLite (بعد از ری‌استارت همه برمی‌گشتند).
"""
from __future__ import annotations

import gc as pygc
import tracemalloc

from karagah import bot, config, db

from .common import Section, fresh, timed
from .driver import VClock, install_clock, play_fast, restore_clock


def _sizes():
    return {"GAMES": len(bot.GAMES), "_LOCKS": len(bot._LOCKS), "_LAST_CALL": len(bot._LAST_CALL),
            "_LAST_CB": len(bot._LAST_CB), "_PENDING": len(bot._PENDING), "LAST_ROSTER": len(bot.LAST_ROSTER),
            "snapshots": len(db.load_snapshots())}


def _soak(games: int, with_gc: bool, rate_limit: bool = True):
    fresh()
    bot.RATE_LIMIT_ENABLED = rate_limit            # مثل تولید: _LAST_CALL پر می‌شود
    clock = VClock()
    o = install_clock(clock)
    tracemalloc.start()
    samples = []
    try:
        for i in range(games):
            clock.advance(120)                      # بین دو بازی دو دقیقه
            play_fast(-(1_000_000 + i), 4 + i % 7, ("classic", "court", "chaos")[i % 3], i, clock)
            if with_gc:
                bot.gc()
            if (i + 1) % max(1, games // 10) == 0:
                pygc.collect()
                cur, _peak = tracemalloc.get_traced_memory()
                samples.append((i + 1, cur / 1024 / 1024, _sizes()))
            if with_gc and (i + 1) % 50 == 0:
                clock.advance(config.ENDED_TTL + 1)   # گذشتِ چند ساعت: میزهای تمام‌شده کهنه می‌شوند
    finally:
        tracemalloc.stop()
        restore_clock(o)
        bot.RATE_LIMIT_ENABLED = False
    return samples


def run(quick: bool = True) -> Section:
    sec = Section("Soak / Longevity", "ماندگاری: هزاران بازی در یک پروسه، با و بدون پاک‌سازی")
    games = 300 if quick else 3000
    with timed(sec):
        a = _soak(games, with_gc=False)
        b = _soak(games, with_gc=True)
        a_last, b_last = a[-1], b[-1]
        sec.metrics["games_per_run"] = games
        sec.metrics["without_gc: MB / GAMES / _LAST_CALL / snapshots"] = (
            f"{a_last[1]:.1f} / {a_last[2]['GAMES']} / {a_last[2]['_LAST_CALL']} / {a_last[2]['snapshots']}")
        sec.metrics["with_gc: MB / GAMES / _LAST_CALL / snapshots"] = (
            f"{b_last[1]:.1f} / {b_last[2]['GAMES']} / {b_last[2]['_LAST_CALL']} / {b_last[2]['snapshots']}")
        sec.notes.append("بدون پاک‌سازی (قبل از نسخه ۸) هر بازیِ تمام‌شده، قفلش، ورودی‌های نرخ‌محدودساز و اسنپ‌شاتش "
                         "برای همیشه می‌ماند — حافظه خطی رشد می‌کرد و بعد از ری‌استارت همه‌ی بازی‌های قدیمی دوباره بار می‌شدند.")
        # حافظه با پاک‌سازی دندانه‌اره‌ای است (هر پاک‌سازی پایین می‌آورد)؛ معیار: قله‌ها بالا نروند
        first = max(m for _, m, _ in b[:len(b) // 2])
        second = max(m for _, m, _ in b[len(b) // 2:])
        growth = (second - first) / max(0.5, first)
        leak_rate = (a_last[1] - a[0][1]) / max(1, a_last[0] - a[0][0]) * 1024
        sec.metrics["peak_growth_second_vs_first_half (with gc)"] = f"{growth * 100:.0f}%"
        sec.metrics["leak_per_game_without_gc_KB"] = round(leak_rate, 1)
        sec.metrics["memory_curve_MB (with gc)"] = " → ".join(f"{m:.1f}" for _, m, _ in b)
        sec.check(b_last[2]["GAMES"] <= 60, f"با gc هنوز {b_last[2]['GAMES']} بازی در حافظه")
        sec.check(b_last[2]["snapshots"] <= 60, f"با gc هنوز {b_last[2]['snapshots']} اسنپ‌شات")
        sec.check(growth < 0.5, f"حافظه در نیمه‌ی دوم {growth * 100:.0f}% رشد کرد")
        sec.check(a_last[2]["GAMES"] == games, "اجرای بدون gc باید نشت را نشان دهد (خودِ آزمون خراب است)")
    return sec
