"""🧭 Playtest & UX telemetry: کجا بازیکن‌ها گیر می‌کنند، کدام دکمه‌ها خطا می‌دهند، چقدر پیام می‌آید.

از بازی‌های agentهای گفتگوکننده (playtest.talk) با تلگرامِ شبیه‌سازی‌شده اندازه می‌گیرد:
- «نقشه‌ی گرما»ی خطا: هر دکمه چند بار زده شد و چند درصد «⛔» گرفت، و رایج‌ترین پیام‌های خطا
- تپ برای هر تصمیمِ شبانه (از بازکردنِ پنل تا ثبت)، پیام برای هر بازیکن در هر روز (شلوغیِ گروه)
- طولِ هر فاز (ثانیه‌ی ساعتِ مجازی)، چند بار شب به «فرصتِ اضافه» کشید، طولِ بازی
- آموزش: آیا تازه‌وارد با «/start» به راهنما و لابی می‌رسد؟
آستانه‌ها «بو» هستند نه قانون: خطای دکمه‌ای بالای ۲۰٪ یعنی دکمه جایی نشان داده می‌شود که کار نمی‌کند.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from karagah.bot import handle

from .common import Section, capture_sessions, fresh, pct, timed

ERR_SMELL = 0.20


def run(quick: bool = True) -> Section:
    sec = Section("Playtest & UX", "تله‌متری: خطای هر دکمه، تپ برای هر تصمیم، شلوغیِ گروه، طولِ فازها، آموزش")
    with timed(sec):
        configs = [(n, s, sc, m) for sc in ("classic", "court", "chaos") for n in ((5, 8) if quick else range(4, 11))
                   for s in ((1,) if quick else (1, 2)) for m in ("group", "dm")]
        cap, games, rep = capture_sessions(configs, talk=True)
        by = defaultdict(lambda: [0, 0])
        errs = Counter()
        for cmd, ok, text, _t in cap.presses:
            by[cmd][0] += 1
            if not ok:
                by[cmd][1] += 1
                errs[text.split("\n")[0][:70]] += 1
        heat = sorted(((f / n, cmd, n) for cmd, (n, f) in by.items() if n >= 20), reverse=True)
        sec.metrics["presses_total"] = len(cap.presses)
        sec.metrics["error_rate_overall"] = f"{sum(f for _, f in by.values()) / max(1, len(cap.presses)) * 100:.1f}%"
        sec.metrics["error_heatmap (top)"] = " | ".join(f"{c} {r * 100:.0f}% of {n}" for r, c, n in heat[:6])
        sec.metrics["top_error_messages"] = " | ".join(f"{t} ×{c}" for t, c in errs.most_common(4))
        smelly = [(c, r, n) for r, c, n in heat if r > ERR_SMELL]
        for c, r, n in smelly:
            sec.notes.append(f"دکمه‌ی «{c}» در {r * 100:.0f}% از {n} تپ خطا داد — "
                             "یا جایی نشان داده می‌شود که کار نمی‌کند، یا توضیحش کافی نیست.")
        # شلوغیِ گروه: پیامِ ربات در گروه به ازای هر بازیکن در هر روز
        grp = [m for m in cap.bot_msgs() if m.chat < 0]
        pdays = sum(g["players"] * max(1, g["days"]) for g in games)
        sec.metrics["bot_group_msgs_per_player_day"] = round(len(grp) / max(1, pdays), 2)
        sec.metrics["group_chat_msgs_total"] = len([m for m in cap.msgs if m.cause.startswith("chat:")])
        # تپ تا هر تصمیمِ شبانه
        taps = sum(1 for c, *_ in cap.presses if c in ("act", "pass"))
        decided = sum(1 for c, ok, *_ in cap.presses if c in ("act", "pass") and ok) or 1
        sec.metrics["taps_per_night_decision"] = round(taps / decided, 2)
        days = [g["days"] for g in games]
        sec.metrics["game_length_days p50/p90/max"] = f"{pct(days, 50)} / {pct(days, 90)} / {max(days)}"
        grace = sum(1 for m in cap.bot_msgs() if "فرصتِ اضافه" in m.text and m.chat < 0)
        sec.metrics["nights_needing_grace"] = grace
        sec.metrics["games"] = len(games)
        sec.check(all(g["finished"] for g in games), "بازیِ تمام‌نشده در تله‌متری")
        # آموزش: تازه‌وارد
        fresh()
        r = handle("start", 90_001, 90_001, "تازه‌وارد")
        cbs = [b.get("callback_data") or b.get("url", "") for row in r["keyboard"]["inline_keyboard"] for b in row]
        sec.check(any("tutorial" in c or "help" in c for c in cbs) or "راهنما" in r["text"],
                  "صفحه‌ی اول راهی به آموزش/راهنما ندارد")
        sec.check(any("startgroup" in c or "add" in c for c in cbs), "صفحه‌ی اول راهی به افزودن به گروه ندارد")
        t = handle("tutorial", 90_001, 90_001)
        sec.metrics["tutorial_chars"] = len(t["text"])
    return sec
