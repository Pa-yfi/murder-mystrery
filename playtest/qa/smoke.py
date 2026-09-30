"""🚬 Smoke & Sanity: چند ده ثانیه، روی هر build — مسیرهای حیاتی سالم‌اند؟

- همه‌ی ماژول‌ها import می‌شوند؛ برنامه‌ی تلگرام با همه‌ی هندلرها ساخته می‌شود (بی‌شبکه)
- هر اندپوینت در لابی و وسط بازی، در گروه و پیوی، جواب می‌دهد و «خطای داخلی» نمی‌دهد
- یک بازیِ کامل تا پایان؛ اسنپ‌شات ذخیره و بازیابی می‌شود و بازی از همان‌جا ادامه دارد
"""
from __future__ import annotations

import importlib
import pickle
import pkgutil

from karagah import bot, db
from karagah.bot import GAMES, handle
from karagah.models import Phase

from .common import Section, fresh, timed
from .driver import play_fast

INTERNAL = "خطای داخلی"


def run(quick: bool = True) -> Section:
    sec = Section("Smoke & Sanity", "دود: import، ساختِ برنامه، همه‌ی اندپوینت‌ها، یک بازی، ذخیره/بازیابی")
    with timed(sec):
        import karagah
        mods = [m.name for m in pkgutil.iter_modules(karagah.__path__)]
        for m in mods:
            try:
                importlib.import_module(f"karagah.{m}")
            except Exception as e:                        # noqa: BLE001
                sec.fail(f"import karagah.{m}: {e}")
        sec.metrics["modules"] = len(mods)

        from karagah import telegram_app
        app = telegram_app.build_app("123456:TEST-TOKEN-offline")
        n_handlers = sum(len(h) for h in app.handlers.values())
        sec.check(n_handlers >= len(bot.ENDPOINTS) + 3, f"هندلرها کم‌اند: {n_handlers}")
        sec.metrics["telegram_handlers"] = n_handlers

        fresh()
        G = -424242
        handle("new", G, 1, "Host")
        for u in range(2, 7):
            handle("join", G, u, f"P{u}")
        bad = []
        for stage in ("lobby", "night"):
            if stage == "night":
                handle("startgame", G, 1, "force")
            for ep in sorted(bot.ENDPOINTS):
                if ep in ("new", "blitz", "startgame", "end", "leave", "admin_ban"):
                    continue
                for chat, uid in ((G, 2), (2, 2)):          # گروه و پیویِ بازیکن
                    r = handle(ep, chat, uid, "P2", "")
                    if INTERNAL in (r.get("text") or ""):
                        bad.append(f"{stage}:{ep}@{'group' if chat < 0 else 'dm'}")
        sec.check(not bad, "اندپوینت‌های با خطای داخلی: " + "، ".join(bad[:10]))
        sec.metrics["endpoints_checked"] = len(bot.ENDPOINTS)

        fresh()
        r = play_fast(-777001, 7, "classic", 1)
        sec.check(r["finished"] and not r["errors"], f"بازیِ دود تمام نشد/خطا داشت: {r}")
        sec.metrics["smoke_game"] = f"{r['team']} در {r['days']} روز"

        fresh()
        handle("new", G, 1, "Host")
        for u in range(2, 8):
            handle("join", G, u, f"P{u}")
        handle("startgame", G, 1, "force")
        g = GAMES[G]
        db.save_snapshot(G, g)
        GAMES.clear()
        n = bot.restore_games()
        g2 = GAMES.get(G)
        sec.check(n >= 1 and g2 is not None and g2.s.phase is Phase.NIGHT, "اسنپ‌شات بازیابی نشد")
        if g2:
            handle("dawn", G)
            sec.check(g2.s.phase in (Phase.MORNING, Phase.JURY, Phase.END), "بازیِ بازیابی‌شده جلو نرفت")
            sec.metrics["snapshot_bytes"] = len(pickle.dumps(g2))
    return sec
