"""جمع‌آوری یافته‌ها (یکتا بر اساس کلید) و نوشتن گزارش Markdown/JSON."""
from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional

SEV_ORDER = {"بحرانی": 0, "بالا": 1, "متوسط": 2, "پایین": 3}


class Report:
    def __init__(self):
        self.findings: "OrderedDict[str, dict]" = OrderedDict()
        self.games: List[dict] = []
        self.context = ""                    # «۷ نفره، بذر ۳» — برای مثال‌ها
        self.checks: Dict[str, int] = {}     # چند بار هر توانایی درست سنجیده شد

    def ok(self, what: str) -> None:
        self.checks[what] = self.checks.get(what, 0) + 1

    def find(self, sev: str, area: str, title: str, detail: str = "",
             key: Optional[str] = None) -> None:
        key = key or title
        f = self.findings.get(key)
        if f is None:
            self.findings[key] = f = {"sev": sev, "area": area, "title": title,
                                      "detail": detail, "count": 0, "where": []}
        f["count"] += 1
        if self.context and len(f["where"]) < 4 and self.context not in f["where"]:
            f["where"].append(self.context)

    def extend(self, items: List[dict]) -> None:
        for it in items:
            self.find(it["sev"], it["area"], it["title"], it.get("detail", ""))

    def sorted(self) -> List[dict]:
        return sorted(self.findings.values(), key=lambda f: (SEV_ORDER.get(f["sev"], 9), f["area"]))

    # ── خروجی ──
    def to_markdown(self) -> str:
        n = len(self.games)
        done = sum(1 for g in self.games if g["finished"])
        lines = ["# 🧪 گزارش بازیکن‌های شبیه‌سازی (playtest)", "",
                 f"- بازی‌ها: **{n}** (تمام‌شده تا افشای نقش‌ها: **{done}**)",
                 f"- تعداد تپ روی دکمه‌ها: **{sum(g['presses'] for g in self.games)}**",
                 f"- یافته‌های یکتا: **{len(self.findings)}**", ""]
        lines += ["## بازی‌ها", "", "| سناریو | بازیکن | بذر | پرونده | برنده | روزها | تپ‌ها | پایان | مسیر پیشروی |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for g in self.games:
            lines.append(f"| {g.get('scenario', '—')} | {g['players']} | {g['seed']} | {g['case']} | {g['winner'] or '—'} | "
                         f"{g['days']} | {g['presses']} | {'✅' if g['finished'] else '⛔ ' + g['stuck']} | "
                         f"{g['mode']} |")
        lines += ["", "## توانایی‌هایی که داور درست بودنشان را سنجید", "",
                  "| بررسی | دفعات |", "|---|---|"]
        for k, v in sorted(self.checks.items()):
            lines.append(f"| {k} | {v} |")
        lines += ["", "## یافته‌ها (از شدیدترین)", ""]
        for i, f in enumerate(self.sorted(), 1):
            where = f" — مثال: {'؛ '.join(f['where'])}" if f["where"] else ""
            lines.append(f"### {i}. [{f['sev']}] {f['title']}")
            lines.append(f"*حوزه:* {f['area']} · *تکرار:* {f['count']}{where}")
            if f["detail"]:
                lines.append("")
                lines.append(f["detail"])
            lines.append("")
        return "\n".join(lines)

    def write(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        md = folder / "REPORT.md"
        md.write_text(self.to_markdown(), encoding="utf-8")
        (folder / "report.json").write_text(
            json.dumps({"games": self.games, "checks": self.checks,
                        "findings": self.sorted()}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        return md
