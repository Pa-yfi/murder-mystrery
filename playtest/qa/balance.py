"""🤖 Automated gameplay (bots) — تله‌متریِ تعادل: هزاران بازیِ سریع برای هر سناریو × تعداد بازیکن.

بازیکن‌های رانندهٔ سریع (driver.play_fast) عمداً ساده‌اند؛ عدد مطلق «مهارت» را نمی‌سنجد، ولی
ترکیبی که یک طرف در آن ≥ ۸۰٪ می‌برد (با فاصله‌ی اطمینانِ ویلسون ۹۵٪) زیر هر مهارتی معیوب است.
بازه‌ی سالم برای شهر: ۲۰٪ تا ۷۵٪.
"""
from __future__ import annotations

import math
from collections import Counter

from .common import Section, fresh, timed
from .driver import VClock, install_clock, play_fast, restore_clock


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - r) / d, (c + r) / d


def run(quick: bool = True) -> Section:
    sec = Section("Automated gameplay & balance", "هزاران بازیِ ربات‌ها؛ نرخ برد با فاصله‌ی اطمینان ۹۵٪")
    per = 60 if quick else 300
    rows = []
    with timed(sec):
        fresh()
        clock = VClock()
        o = install_clock(clock)
        errors = unfinished = total = 0
        try:
            for scen in ("classic", "court", "chaos"):
                for n in range(4, 11):
                    c = Counter()
                    days = 0
                    for i in range(per):
                        chat = -(2_000_000 + hash((scen, n, i)) % 900_000)
                        r = play_fast(chat, n, scen, i, clock)
                        c[r["team"]] += 1
                        days += r["days"]
                        errors += len(r["errors"])
                        unfinished += not r["finished"]
                        total += 1
                        from karagah import bot
                        bot.GAMES.pop(chat, None)
                    lo, hi = wilson(c["city"], per)
                    rows.append((scen, n, c, lo, hi, days / per))
        finally:
            restore_clock(o)
        sec.metrics["games"] = total
        sec.metrics["internal_errors"] = errors
        sec.metrics["unfinished (day cap)"] = unfinished
        sec.check(errors == 0, f"{errors} خطای داخلی در بازی‌های ربات")
        table = ["| سناریو | نفر | شهر (۹۵٪ CI) | قاتل‌ها | جانی | سپر بلا | میانگین روز |", "|---|---|---|---|---|---|---|"]
        flagged = []
        for scen, n, c, lo, hi, d in rows:
            cp = c["city"] / per
            table.append(f"| {scen} | {n} | {cp * 100:.0f}% ({lo * 100:.0f}–{hi * 100:.0f}) | "
                         f"{c['killers'] / per * 100:.0f}% | {c['serial'] / per * 100:.0f}% | "
                         f"{c['scapegoat'] / per * 100:.0f}% | {d:.1f} |")
            if hi < 0.20 or lo > 0.75:
                flagged.append(f"{scen} {n} نفره: شهر {cp * 100:.0f}% (CI {lo * 100:.0f}–{hi * 100:.0f})")
            worst = max(("killers", "serial", "scapegoat"), key=lambda k: c[k])
            if wilson(c[worst], per)[0] > 0.80:
                flagged.append(f"{scen} {n} نفره: {worst} {c[worst] / per * 100:.0f}%")
        sec.metrics["balance_table"] = "\n" + "\n".join(table)
        sec.metrics["cells_flagged"] = len(flagged)
        for f in flagged:
            sec.notes.append("نامتعادل (با ربات‌های ساده): " + f)
    return sec
