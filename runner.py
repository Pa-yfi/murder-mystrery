#!/usr/bin/env python
"""اجراکننده‌ی همه‌ی بخش‌های پروژه — یک نقطه‌ی ورود برای همه‌چیز.

    python runner.py                 # فهرست کارها
    python runner.py all             # check + selftest + test
    python runner.py bot             # ربات واقعی را بالا می‌آورد

هیچ زیرفرمانی جز `bot` به شبکه دست نمی‌زند و هیچ‌کدام `karagah.db` واقعی را
تغییر نمی‌دهند (همه روی دیتابیسِ حافظه کار می‌کنند).
"""
from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# کنسول ویندوز پیش‌فرض cp1252 است و فارسی/ایموجی را می‌شکند
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OK, WARN, FAIL = "✅", "⚠️", "⛔"
DIV = "─" * 60

# همه‌ی ماژول‌های پروژه — اگر یکی اضافه شد و اینجا نیامد، تستِ پوشش می‌افتد
MODULES = ["config", "models", "roles", "cases", "dialogue", "engine",
           "ui", "menus", "db", "bot", "cards", "strings", "telegram_app"]


def head(title: str) -> None:
    print(f"\n{DIV}\n{title}\n{DIV}")


# ───────────────────────── بررسی محیط ─────────────────────────
def cmd_check(_args) -> int:
    head("🩺 بررسی محیط")
    bad = 0

    v = sys.version_info
    print(f"{OK if v >= (3, 10) else WARN} پایتون {v.major}.{v.minor}.{v.micro}")

    deps = [("telegram", "python-telegram-bot", True),
            ("dotenv", "python-dotenv", True),
            ("PIL", "Pillow — کارت نقش PNG", True),
            ("apscheduler", "job-queue — تایمر خودکار فازها", True),
            ("pytest", "pytest — اجرای تست‌ها", False)]
    for mod, label, required in deps:
        try:
            importlib.import_module(mod)
            print(f"{OK} {label}")
        except ImportError:
            print(f"{FAIL if required else WARN} {label} نصب نیست")
            bad += int(required)

    # آیا JobQueue واقعاً ساخته می‌شود؟
    try:
        import warnings
        from telegram.ext import ApplicationBuilder
        with warnings.catch_warnings():       # خودمان داریم می‌سنجیم؛ هشدارش اضافی است
            warnings.simplefilter("ignore")
            app = ApplicationBuilder().token("1:x").build()
        if app.job_queue:
            print(f"{OK} JobQueue فعال است (تایمر فازها کار می‌کند)")
        else:
            print(f"{FAIL} JobQueue ساخته نشد → تایمر فازها بی‌صدا اجرا نمی‌شود")
            print('   نصب: pip install "python-telegram-bot[job-queue]"')
            bad += 1
    except Exception as e:
        print(f"{WARN} بررسی JobQueue ممکن نشد: {e}")

    head("🔑 پیکربندی")
    env = ROOT / ".env"
    print(f"{OK if env.exists() else WARN} فایل .env "
          f"{'پیدا شد' if env.exists() else 'نیست — از .env.example کپی کن'}")
    from karagah import config
    tok = config.BOT_TOKEN
    if not tok:
        print(f"{WARN} BOT_TOKEN خالی است (برای `runner.py bot` لازم است)")
    elif tok == "your_telegram_bot_token_here":
        print(f"{FAIL} BOT_TOKEN هنوز مقدار نمونه است")
        bad += 1
    else:
        print(f"{OK} BOT_TOKEN تنظیم شده ({tok[:4]}…{len(tok)} نویسه)")
    print(f"{OK} BOT_USERNAME = {config.BOT_USERNAME}")
    if config.ADMIN_IDS:
        print(f"{OK} ADMIN_IDS = {config.ADMIN_IDS}")
    else:
        print(f"{WARN} ADMIN_IDS خالی است → هیچ‌کس به پنل ادمین دسترسی ندارد")
    print(f"{OK} بازیکن: {config.MIN_PLAYERS} تا {config.MAX_PLAYERS} | "
          f"مهلت فازها: {config.PHASE_SECONDS}")

    head("💾 پایگاه‌داده")
    dbf = ROOT / os.getenv("DB_PATH", "karagah.db")
    if dbf.exists():
        import re
        import sqlite3
        from karagah import db as dbmod
        con = sqlite3.connect(dbf)
        tabs = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        wanted = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", dbmod.SCHEMA))
        print(f"{OK} {dbf.name} ({dbf.stat().st_size // 1024} KB) — "
              f"{len(tabs)} جدول: {'، '.join(sorted(tabs))}")
        missing = sorted(wanted - tabs)
        if missing:
            # اسکیما با IF NOT EXISTS اجرا می‌شود، پس خودش ساخته می‌شود
            print(f"{WARN} جدول‌های تازه هنوز ساخته نشده‌اند: {'، '.join(missing)}"
                  f"\n   با اولین اجرای ربات خودکار ساخته می‌شوند.")
    else:
        print(f"{WARN} {dbf.name} هنوز ساخته نشده (اولین اجرا می‌سازدش)")

    print(f"\n{OK + ' محیط سالم است' if not bad else FAIL + f' {bad} مشکل جدی'}")
    return 1 if bad else 0


# ───────────────────────── خودآزمایی ─────────────────────────
def _memory_db():
    from karagah import db
    db.reset(":memory:")          # دست به karagah.db واقعی نمی‌زنیم
    return db


def cmd_selftest(_args) -> int:
    head("🧪 خودآزمایی (بدون شبکه، روی دیتابیس حافظه)")
    from karagah import bot, menus
    failures = []

    def step(label, fn):
        try:
            detail = fn()
            print(f"{OK} {label}{f' — {detail}' if detail else ''}")
        except Exception as e:
            failures.append(label)
            print(f"{FAIL} {label} — {type(e).__name__}: {e}")
            traceback.print_exc(limit=2)

    def _imports():
        for m in MODULES:
            importlib.import_module(f"karagah.{m}")
        return f"{len(MODULES)} ماژول"
    step("ایمپورت همه‌ی ماژول‌ها", _imports)

    def _routes():
        missing = [e for e in bot.ENDPOINTS if not callable(bot._ROUTES[e])]
        assert not missing, missing
        return f"{len(bot.ENDPOINTS)} اندپوینت"
    step("هر اندپوینت هندلر دارد", _routes)

    def _buttons():
        direct, indirect = set(menus.all_buttons()), set(menus.REACHES)
        orphan = [e for e in bot.ENDPOINTS if e not in direct and e not in indirect]
        assert not orphan, f"بدون دکمه: {orphan}"
        dead = [c for c in menus.all_buttons() if c not in bot._ROUTES]
        assert not dead, f"دکمه‌ی مرده: {dead}"
        return f"{len(direct)} دکمه‌ی مستقیم + {len(indirect)} غیرمستقیم"
    step("هر فرمان دکمه دارد و هر دکمه زنده است", _buttons)

    def _roles():
        from karagah.roles import ROLES, COMPOSITIONS, validate_composition
        for n in COMPOSITIONS:
            assert validate_composition(n), n
        return f"{len(ROLES)} نقش، ترکیب‌های {min(COMPOSITIONS)}..{max(COMPOSITIONS)}"
    step("تعادل همه‌ی ترکیب‌ها", _roles)

    def _cases():
        from karagah.cases import CASES
        assert len({c.title for c in CASES}) == len(CASES)
        for c in CASES:
            assert len(c.evidence) == 6
            assert all(len(e["interpretations"]) >= 2 for e in c.evidence)
        return f"{len(CASES)} پرونده"
    step("یکتایی و کاملی پرونده‌ها", _cases)

    def _fuzz():
        _memory_db(); bot.GAMES.clear()
        junk = ["", "0", "-1", "99999999999999999999", "abc", "E9:9", "؛*_`",
                "../../etc/passwd", "1" * 300]
        internal = []
        for cmd in bot.ENDPOINTS:
            for a in junk:
                r = bot.handle(cmd, 424242, 7, "فازر", a)
                assert isinstance(r, dict) and "ok" in r, (cmd, a)
                # ورودی خرابِ عادی باید پیام قانون بگیرد، نه «خطای داخلی»
                if "خطای داخلی" in r.get("text", ""):
                    internal.append(f"{cmd}({a!r})")
        bot.GAMES.clear()
        assert not internal, "خطای داخلی به‌جای پیام قانون: " + "، ".join(internal[:5])
        return f"{len(bot.ENDPOINTS)}×{len(junk)} فراخوانی"
    step("هیچ اندپوینتی با ورودی خراب نمی‌ترکد", _fuzz)

    def _full_game():
        from karagah.models import Phase
        _memory_db(); bot.GAMES.clear()
        chat = 99001
        bot.handle("new", chat, 1, "میزبان")
        for i in range(2, 9):
            bot.handle("join", chat, i, f"بازیکن{i}")
        bot.handle("startgame", chat, 1, arg="3")
        g = bot.GAMES[chat]
        for _ in range(40):
            if g.s.phase is Phase.END:
                break
            _advance(bot, g, chat)
        assert g.s.phase is Phase.END, f"در فاز {g.s.phase.value} گیر کرد"
        assert bot.handle("end", chat, 1)["ok"]
        return f"برنده: {g.s.winner} در روز {g.s.day}"
    step("یک بازی کامل تا افشای نقش‌ها", _full_game)

    def _no_leak():
        _memory_db(); bot.GAMES.clear()
        chat = 99002
        bot.handle("new", chat, 1, "میزبان")
        for i in range(2, 9):
            bot.handle("join", chat, i, f"بازیکن{i}")
        bot.handle("startgame", chat, 1, arg="4")
        g = bot.GAMES[chat]
        for cmd in ("status", "dashboard", "remind", "spectate"):
            txt = bot.handle(cmd, chat, 1)["text"]
            for p in g.s.players.values():
                assert p.role not in txt, f"{cmd} نقش {p.name} را لو داد"
        for p in g.s.players.values():
            assert bot.handle("myrole", chat, p.uid)["private"]
        bot.GAMES.clear()
        return "نقش‌ها در خروجی عمومی نیستند"
    step("خروجی عمومی نقش لو نمی‌دهد", _no_leak)

    print()
    if failures:
        print(f"{FAIL} {len(failures)} بخش خراب: {'، '.join(failures)}")
        return 1
    print(f"{OK} همه‌ی بخش‌ها سالم‌اند.")
    return 0


def _advance(bot, g, chat) -> None:
    """یک قدم بازی را با همان دستورهای عمومی جلو می‌برد."""
    from karagah.models import Phase
    ph = g.s.phase
    if ph in (Phase.NIGHT, Phase.INTERROGATION):
        for uid in list(g.pending_actors()):
            targets = g.legal_targets(uid)
            if targets:
                bot.handle("act", chat, uid, arg=str(targets[0]))
        bot.handle("dawn", chat)
    elif ph is Phase.MORNING:
        if g.s.suspect_uid is not None:
            bot.handle("verdict", chat, g.s.officer_uid, arg="1")
        else:
            bot.handle("discuss", chat)
    elif ph is Phase.DISCUSSION:
        bot.handle("vote", chat)
    elif ph is Phase.VOTE:
        target = next((p.uid for p in g.s.alive_players()
                       if p.can_vote and p.uid != g.s.officer_uid), None)
        if target:
            for p in g.s.alive_players():
                if p.can_vote and p.uid != target:
                    bot.handle("castvote", chat, p.uid, arg=str(target))
        bot.handle("closevote", chat)
    elif ph is Phase.JURY:
        for p in g.s.alive_players():
            if p.can_vote:
                bot.handle("juryvote", chat, p.uid, arg="1")
        bot.handle("closejury", chat)


# ───────────────────────── نمایش یک بازی ─────────────────────────
def cmd_demo(args) -> int:
    head("🎬 نمایش یک بازی کامل")
    from karagah import bot
    from karagah.models import Phase
    _memory_db(); bot.GAMES.clear()
    chat, n = 99100, args.players
    bot.handle("new", chat, 1, "میزبان")
    for i in range(2, n + 1):
        bot.handle("join", chat, i, f"بازیکن{i}")
    bot.handle("startgame", chat, 1, arg=str(args.case))
    g = bot.GAMES[chat]
    print(f"🕯️ پرونده: {g.s.case.title} — مقتول {g.s.case.victim}")
    print("🎭 نقش‌ها (فقط در این نمایش آشکار است):")
    for p in g.s.players.values():
        print(f"   {p.name}: {p.role}")
    last = None
    for _ in range(40):
        if g.s.phase is Phase.END:
            break
        if g.s.phase is not last:
            print(f"\n▶️ فاز: {g.s.phase.value} (روز {g.s.day})")
            last = g.s.phase
        _advance(bot, g, chat)
    print("\n" + bot.handle("end", chat, 1)["text"])
    bot.GAMES.clear()
    return 0


# ───────────────────────── نمایشگرها ─────────────────────────
def cmd_buttons(_args) -> int:
    head("🎛️ درخت کامل دکمه‌ها")
    from karagah import bot, menus
    total = 0
    for _key, title, items in menus.GROUPS:
        print(f"\n{title}")
        for label, cb in items:
            mark = OK if cb in bot._ROUTES else FAIL
            print(f"   {mark} {label:<28} → /{cb}")
            total += 1
    print(f"\n↪️ از دل دکمه‌های دیگر: "
          + "، ".join(f"{e}←{v}" for e, v in menus.REACHES.items()))
    print(f"\nجمع: {total} دکمه برای {len(bot.ENDPOINTS)} اندپوینت")
    return 0


def cmd_roles(_args) -> int:
    head("🎭 نقش‌ها")
    from karagah.roles import ROLES, COMPOSITIONS
    from karagah.menus import ABILITY_FA
    for r in ROLES.values():
        print(f"{r.emoji} {r.name:<12} {r.align.value:<9} "
              f"{ABILITY_FA.get(r.ability, r.ability)}")
    print(f"\nترکیب‌ها:")
    for n, comp in sorted(COMPOSITIONS.items()):
        killers = sum(1 for x in comp if ROLES[x].align.value == "قاتل‌ها")
        print(f"   {n} نفره: {killers} قاتل — {'، '.join(comp)}")
    return 0


def cmd_cases(_args) -> int:
    head("🕯️ پرونده‌ها")
    from karagah.cases import CASES
    for c in CASES:
        print(f"#{c.cid:>2} {c.title} — {c.victim} | {c.weapon} | {c.motive}")
    print(f"\nجمع: {len(CASES)} پرونده × ۶ مدرک")
    return 0


def cmd_db(_args) -> int:
    head("💾 پایگاه‌داده")
    import sqlite3
    dbf = ROOT / os.getenv("DB_PATH", "karagah.db")
    if not dbf.exists():
        print(f"{WARN} {dbf.name} هنوز ساخته نشده.")
        return 0
    con = sqlite3.connect(dbf)
    con.row_factory = sqlite3.Row
    for (tab,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        n = con.execute(f"SELECT COUNT(*) FROM {tab}").fetchone()[0]
        print(f"   {tab:<14} {n:>6} ردیف")
    con.close()
    return 0


def cmd_stats(_args) -> int:
    head("📊 آمار و تعادل")
    from karagah import db, ui
    dbf = ROOT / os.getenv("DB_PATH", "karagah.db")
    if not dbf.exists():
        print(f"{WARN} هنوز داده‌ای نیست.")
        return 0
    db.reset(str(dbf))
    print(ui.admin_stats_sql(db.q_stats()))
    print()
    print(ui.balance_report_sql(db.q_balance(), db.q_balance_by_seats(),
                                db.q_abandonment()))
    return 0


# ───────────────────────── تست‌ها و ربات ─────────────────────────
def _pytest(paths, extra=()) -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", *paths, *extra]
    print("▶️ " + " ".join(cmd))
    sys.stdout.flush()        # وگرنه خروجی pytest جلوتر از تیترها چاپ می‌شود
    return subprocess.call(cmd, cwd=ROOT)


def cmd_test(_args) -> int:
    head("✅ سوئیت اصلی (باید سبز باشد)")
    return _pytest(["tests"], ["--ignore=tests/quality"])


def cmd_quality(_args) -> int:
    head("📋 دفترچه‌ی نقص (عمداً قرمز — هر شکست یک نقصِ شناخته‌شده است)")
    _pytest(["tests/quality"])
    return 0                      # قرمزیِ این سوئیت شکستِ اجرا نیست


def cmd_bot(_args) -> int:
    head("🤖 اجرای ربات تلگرام")
    from karagah.telegram_app import main
    main()
    return 0


def cmd_all(args) -> int:
    results = [("بررسی محیط", cmd_check(args)),
               ("خودآزمایی", cmd_selftest(args)),
               ("سوئیت تست", cmd_test(args))]
    head("🏁 نتیجه")
    for label, rc in results:
        print(f"{OK if rc == 0 else FAIL} {label}")
    bad = [l for l, rc in results if rc]
    print(f"\n{OK} همه‌چیز سبز." if not bad
          else f"\n{FAIL} خراب: {'، '.join(bad)}")
    return 1 if bad else 0


COMMANDS = {
    "check":    (cmd_check,    "بررسی محیط، وابستگی‌ها، .env و پایگاه‌داده"),
    "selftest": (cmd_selftest, "خودآزمایی: ماژول‌ها، دکمه‌ها، فاز، یک بازی کامل"),
    "test":     (cmd_test,     "سوئیت اصلی تست"),
    "quality":  (cmd_quality,  "دفترچه‌ی نقص (عمداً قرمز)"),
    "demo":     (cmd_demo,     "یک بازی کامل را چاپ می‌کند"),
    "buttons":  (cmd_buttons,  "درخت کامل دکمه‌ها"),
    "roles":    (cmd_roles,    "۱۸ نقش و ترکیب‌ها"),
    "cases":    (cmd_cases,    "۴۰ پرونده"),
    "db":       (cmd_db,       "جدول‌ها و تعداد ردیف‌ها"),
    "stats":    (cmd_stats,    "آمار کلی و تعادل نقش‌ها"),
    "bot":      (cmd_bot,      "اجرای ربات واقعی (به شبکه وصل می‌شود)"),
    "all":      (cmd_all,      "check + selftest + test"),
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="runner.py", description="اجراکننده‌ی همه‌ی بخش‌های کارآگاه",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:<9} {d}" for k, (_f, d) in COMMANDS.items()))
    parser.add_argument("command", nargs="?", choices=list(COMMANDS), help="کار موردنظر")
    parser.add_argument("--players", type=int, default=8, help="تعداد بازیکن در demo")
    parser.add_argument("--case", type=int, default=3, help="شماره‌ی پرونده در demo")
    args = parser.parse_args(argv)

    if not args.command:
        print("🕵️ کارآگاه — اجراکننده‌ی پروژه\n" + DIV)
        for k, (_f, d) in COMMANDS.items():
            print(f"  python runner.py {k:<9} {d}")
        return 0
    return COMMANDS[args.command][0](args) or 0


if __name__ == "__main__":
    sys.exit(main())
