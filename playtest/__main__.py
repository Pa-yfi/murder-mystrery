"""python -m playtest [--seeds 6] [--min 4] [--max 10] [--out playtest]

برای هر تعداد بازیکن از کمینه تا بیشینه، چند بذر × سه حالت پیشروی فاز
(دکمه در گروه، تایمر، دکمه از پیوی) بازی می‌شود و گزارش نوشته می‌شود.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from karagah import config

from .docs import cross_check, read_all
from .game import run_session
from .probes import run_probes
from .report import Report

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="playtest")
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--min", type=int, default=config.MIN_PLAYERS)
    ap.add_argument("--max", type=int, default=config.MAX_PLAYERS)
    ap.add_argument("--modes", default="group,timer,dm")
    ap.add_argument("--scenarios", default="classic,court,chaos")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-talk", action="store_true", help="بدون گفتگو/بلوف (رای تصادفی‌تر، برای مقایسه)")
    ap.add_argument("--no-probes", action="store_true")
    args = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)          # هندلرها خطاها را لاگ می‌کنند؛ گزارش خودش می‌گیرد

    rb = read_all()                            # همه‌ی agentها همین کتاب قانون را می‌خوانند
    report = Report()
    report.context = "خواندن مستندات"
    report.extend(cross_check(rb))
    if not args.quiet:
        print(f"📚 مستندات خوانده‌شده: {', '.join(rb.files)}")

    modes = [m for m in args.modes.split(",") if m]
    scenarios = [s for s in args.scenarios.split(",") if s]
    for scen in scenarios:
        for n in range(args.min, args.max + 1):
            for seed in range(1, args.seeds + 1):
                for mode in modes:
                    g = run_session(n, seed, report, rb, mode, scen, not args.no_talk)
                    if not args.quiet:
                        mark = "✅" if g["finished"] else f"⛔ {g['stuck']}"
                        print(f"{g['scenario']:<7} | {n:>2} نفر | بذر {seed} | {g['mode']:<12} | "
                              f"{g['case']:<4} | برنده: {g['winner'] or '—':<14} | روز {g['days']:>2} | "
                              f"{g['presses']:>4} تپ | {mark}")
    if not args.no_probes:
        run_probes(report, rb)
    path = report.write(Path(args.out))
    finished = sum(1 for g in report.games if g["finished"])
    print(f"\n🏁 {finished}/{len(report.games)} بازی تا افشای نقش‌ها رسید · "
          f"{len(report.findings)} یافته‌ی یکتا → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
