"""python -m playtest.qa [--full] [--only smoke,perf,...]

همه‌ی گونه‌های آزمونِ بازی روی ربات «کارآگاه» و گزارشِ playtest/QA_REPORT.md:
  Unit & Integration  → pytest (tests/)
  Functional/Gameplay → agentهای دکمه‌زن در تلگرامِ شبیه‌سازی‌شده (playtest.game) + crawl (--full)
  Smoke & Sanity      → playtest/qa/smoke.py
  Regression          → pytest (هر باگِ درست‌شده یک تست دارد) + بازیکن‌های شلوغ‌کار (playtest.monkey)
  Performance         → playtest/qa/perf.py
  Soak / Longevity    → playtest/qa/soak.py
  Network & Multiplayer → playtest/qa/net.py
  Platform & Compat   → playtest/qa/compat.py
  Automated bots & balance → playtest/qa/balance.py
  Localization & I18n → playtest/qa/l10n.py
  Playtest & UX       → playtest/qa/ux.py
خروجیِ غیرصفر یعنی دست‌کم یک بخش شکست خورد (برای CI).
"""
from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

from . import balance, compat, l10n, net, perf, smoke, soak, ux
from .common import Section, timed

ROOT = Path(__file__).resolve().parents[2]


def unit_integration(quick: bool) -> Section:
    sec = Section("Unit & Integration", "pytest: منطقِ خالص (واحد) + ربات/موتور/SQLite/آداپتور با هم (یکپارچگی)")
    with timed(sec):
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                           capture_output=True, text=True)
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        sec.metrics["pytest"] = tail
        m = re.search(r"(\d+) passed", tail)
        sec.metrics["tests_passed"] = int(m.group(1)) if m else 0
        sec.check(r.returncode == 0, f"pytest شکست خورد: {tail}")
        tests = sorted(p.name for p in (ROOT / "tests").glob("test_*.py"))
        sec.metrics["test_files"] = len(tests)
    return sec


def functional(quick: bool) -> Section:
    sec = Section("Functional & Gameplay", "agentهایی که Markdownها را خوانده‌اند و فقط با دکمه بازی می‌کنند؛ داورِ مستقل")
    from playtest.docs import read_all
    from playtest.game import run_session
    from playtest.report import Report
    with timed(sec):
        rb = read_all()
        rep = Report()
        n = 0
        modes = ("group",) if quick else ("group", "timer", "dm")
        for scen in ("classic", "court", "chaos"):
            for size in range(4, 11):
                for seed in ((1,) if quick else (1, 2, 3)):
                    for mode in modes:
                        g = run_session(size, seed, rep, rb, mode, scen)
                        n += 1
                        sec.check(g["finished"], f"{scen} {size} نفره بذر {seed} {mode}: تمام نشد ({g['stuck']})")
        sec.metrics["games"] = n
        sec.metrics["button_presses"] = sum(g["presses"] for g in rep.games)
        sec.metrics["referee_checks_passed"] = sum(rep.checks.values())
        sec.metrics["referee_findings"] = len(rep.findings)
        for f in rep.sorted():
            sec.fail(f"[{f['sev']}] {f['title']} ×{f['count']}")
        if not quick:
            from playtest import crawl
            crawl_out = subprocess.run([sys.executable, "-m", "playtest.crawl"], cwd=ROOT,
                                       capture_output=True, text=True)
            sec.metrics["crawl"] = (crawl_out.stdout.strip().splitlines() or ["—"])[-1]
            sec.check("0 یافته" in sec.metrics["crawl"], "crawl بن‌بست پیدا کرد")
    return sec


def regression_monkey(quick: bool) -> Section:
    sec = Section("Regression (chaos players)", "بازیکن‌های شلوغ‌کار: هر دکمه در هر لحظه، /start وسط بازی، پرشِ ساعت")
    from playtest.docs import read_all
    from playtest.monkey import Monkey
    from playtest.report import Report
    with timed(sec):
        rb = read_all()
        rep = Report()
        done = total = 0
        for scen in ("classic", "court", "chaos"):
            for n in range(4, 11):
                for seed in ((1,) if quick else (1, 2, 3, 4, 5)):
                    rep.context = f"{scen} {n} نفره بذر {seed}"
                    r = Monkey(n, seed, scen, rep, rb).run()
                    total += 1
                    done += bool(r.get("ok"))
        sec.metrics["chaos_games_finished"] = f"{done}/{total}"
        sec.check(done == total, f"{total - done} بازیِ شلوغ‌کار تمام نشد")
        for f in rep.sorted():
            sec.fail(f"[{f['sev']}] {f['title']} ×{f['count']} — {'؛ '.join(f['where'][:1])}")
    return sec


MODULES = [
    ("unit", unit_integration), ("smoke", smoke.run), ("functional", functional),
    ("regression", regression_monkey), ("perf", perf.run), ("soak", soak.run), ("net", net.run),
    ("compat", compat.run), ("balance", balance.run), ("l10n", l10n.run), ("ux", ux.run),
]

NOT_APPLICABLE = """
### گونه‌هایی که در یک ربات تلگرامی معادل دارند (نه عیناً)
| در بازی‌های ویدئویی | اینجا |
|---|---|
| فریم‌ریت، draw call، GPU | تأخیرِ هر تپ (p50/p95/p99)، زمانِ هر دورِ تایمر برای ۲۰۰ میز، اندازه‌ی اسنپ‌شات |
| NavMesh و مرزهای نقشه | crawl: هر دکمه در ۴۰ وضعیتِ بازی؛ شلوغ‌کار: هر دکمه‌ی کهنه در هر لحظه |
| قطع‌شدنِ دسته/کنترلر | کاربری که ربات را بلاک کرده، پیامِ پاک‌شده، قطعیِ شبکه، RetryAfter |
| Suspend/Resume کنسول | ری‌استارتِ ربات در هر فاز (فقط SQLite می‌ماند) + توقف/ادامه‌ی میزبان |
| مهاجرتِ میزبان (host migration) | ارتقای گروه به سوپرگروه (chat_id عوض می‌شود) + بازی بدون میزبان تا پایان |
| رزولوشن/نسبت تصویر | سقف‌های Bot API: ۴۰۹۶ نویسه، callback ≤ ۶۴ بایت، طولِ برچسب دکمه روی موبایل، راست‌به‌چپ |
| صدا/زیرنویس | ندارد (ربات صدا ندارد؛ کارت نقشِ PNG با فونت فارسی در crawl سنجیده می‌شود) |
| TRC/XR/TCR | ندارد؛ معادلش قواعدِ Bot API بالاست |
"""


def write_report(sections, quick: bool) -> Path:
    ok = all(s.passed for s in sections)
    lines = ["# 🧪 گزارش QA — همه‌ی گونه‌های آزمونِ بازی", "",
             f"حالت: **{'سریع (--quick)' if quick else 'کامل (--full)'}** · نتیجه: "
             f"**{'✅ همه سبز' if ok else '❌ دست‌کم یک بخش قرمز'}**", "",
             "اجرای دوباره: `python -m playtest.qa` (سریع، چند دقیقه) یا `python -m playtest.qa --full`.",
             f"محیط: پایتون {sys.version.split()[0]} روی {sys.platform}؛ CI همین را روی ۳.۱۰ تا ۳.۱۳ اجرا می‌کند "
             "(`.github/workflows/ci.yml`).", "",
             "| گونه‌ی آزمون | نتیجه | زمان (ث) | خلاصه |", "|---|---|---|---|"]
    for s in sections:
        key = next(iter(s.metrics.items()), ("", ""))
        lines.append(f"| {s.kind} | {'✅' if s.passed else '❌'} | {s.seconds} | {key[0]}: {str(key[1])[:60]} |")
    for s in sections:
        lines += ["", f"## {'✅' if s.passed else '❌'} {s.kind}", f"_{s.title}_", ""]
        for k, v in s.metrics.items():
            if isinstance(v, str) and v.startswith("\n|"):
                lines += [f"**{k}:**", v]
            else:
                lines.append(f"- **{k}:** {v}")
        if s.findings:
            lines += ["", "**شکست‌ها:**"] + [f"- ❌ {f}" for f in s.findings]
        if s.notes:
            lines += ["", "**مشاهده‌ها:**"] + [f"- {n}" for n in s.notes]
    lines.append(NOT_APPLICABLE)
    out = ROOT / "playtest" / "QA_REPORT.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="playtest.qa")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    quick = not args.full
    only = {x for x in args.only.split(",") if x}
    sections = []
    for key, fn in MODULES:
        if only and key not in only:
            continue
        try:
            sec = fn(quick)
        except Exception as e:                                # noqa: BLE001
            sec = Section(key, "خودِ ماژول افتاد")
            sec.fail(f"{type(e).__name__}: {e}")
        sections.append(sec)
        print(f"{'✅' if sec.passed else '❌'} {sec.kind:<32} {sec.seconds:>7}s  "
              + (sec.findings[0][:90] if sec.findings else ""), flush=True)
    path = write_report(sections, quick)
    print(f"→ {path}")
    return 0 if all(s.passed for s in sections) else 1


if __name__ == "__main__":
    sys.exit(main())
