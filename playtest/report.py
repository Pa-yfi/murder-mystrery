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
        lines += self.balance_md()
        lines += self.moves_md()
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

    def moves_md(self) -> List[str]:
        """ماتریسِ پوششِ حرکت‌ها: هر نقش هر حرکتی را که می‌تواند، واقعاً با دکمه انجام داد؟"""
        tot: Dict[str, Dict[str, int]] = {}
        for g in self.games:
            for key, c in (g.get("moves") or {}).items():
                role, move = key.split("|", 1)
                tot.setdefault(role, {})[move] = tot.setdefault(role, {}).get(move, 0) + c
        if not tot:
            return []
        out = ["", "## پوششِ حرکت‌ها (فقط با دکمه)", "", "| نقش | حرکت‌ها (تعداد) |", "|---|---|"]
        for role in sorted(tot):
            out.append(f"| {role} | " + " · ".join(f"{m} {c}" for m, c in sorted(tot[role].items(),
                                                                                key=lambda x: -x[1])) + " |")
        return out

    def balance_md(self) -> List[str]:
        """برد هر تیم در هر سناریو + آمار گفتگو/بلوف + دقت بازداشت‌ها + سرنخ‌ها."""
        out = ["", "## تعادل، گفتگو و سرنخ‌ها", ""]
        scen: Dict[str, Dict[str, int]] = {}
        for g in self.games:
            d = scen.setdefault(g.get("scenario", "—"), {})
            d[g.get("winner_team", "none")] = d.get(g.get("winner_team", "none"), 0) + 1
            d["n"] = d.get("n", 0) + 1
        out += ["| سناریو | بازی | شهر | قاتل‌ها | جانی سریالی | سپر بلا |", "|---|---|---|---|---|---|"]
        for k, d in scen.items():
            pc = lambda t: f"{100 * d.get(t, 0) // max(1, d['n'])}٪"
            out.append(f"| {k} | {d['n']} | {pc('city')} | {pc('killers')} | {pc('serial')} | {pc('scapegoat')} |")
        talk: Dict[str, int] = {}
        arr: Dict[str, int] = {}
        clu: Dict[str, int] = {}
        src: Dict[str, int] = {}
        rum = [0, 0]
        for g in self.games:
            for k, v in (g.get("talk") or {}).items():
                talk[k] = talk.get(k, 0) + v
            for k, v in (g.get("arrests") or {}).items():
                arr[k] = arr.get(k, 0) + v
            for k, v in (g.get("clues") or {}).items():
                if k == "by_source":
                    for s2, n in v.items():
                        src[s2] = src.get(s2, 0) + n
                else:
                    clu[k] = clu.get(k, 0) + v
            r = g.get("rumors") or [0, 0]
            rum = [rum[0] + r[0], rum[1] + r[1]]
        pct = lambda a, b: f"{100 * a // b}٪" if b else "—"
        if talk:
            out += ["", "**گفتگو سر میز (مجموع همه‌ی بازی‌ها):**", "",
                    f"- پیام‌های چت: {talk.get('messages', 0)} · ادعای راست: {talk.get('honest_claims', 0)} · "
                    f"دروغ/بلوف: {talk.get('lies', 0)}",
                    f"- ترفندها: کارآگاهِ قلابی {talk.get('fake_detective', 0)} · پزشک قانونیِ قلابی "
                    f"{talk.get('fake_forensic', 0)} · «پاک» جا زدنِ هم‌تیمی {talk.get('vouch', 0)} · "
                    f"هل دادنِ پاپوش {talk.get('frame_push', 0)}",
                    f"- دروغ‌های لو رفته با آزمایشگاه: {talk.get('lies_caught', 0)} · ادعای متقابل "
                    f"(«کارآگاه/پزشک قانونی منم»): {talk.get('counter_claims', 0)}",
                    f"- رای‌های شهر روی تیم قاتل/جانی: {pct(talk.get('city_votes_on_killer', 0), talk.get('city_votes', 0))}"
                    f" ({talk.get('city_votes_on_killer', 0)}/{talk.get('city_votes', 0)})",
                    f"- ربات به چتِ عادی جواب داد: {talk.get('bot_replied_to_chat', 0)} بار"]
        if arr:
            out += [f"- بازجویی‌شده‌ها که واقعاً شرور بودند: {pct(arr.get('interrogated_evil', 0), arr.get('interrogated', 0))}"
                    f" · زندانی‌های شرور: {pct(arr.get('jailed_evil', 0), arr.get('jailed', 0))}"]
        if clu:
            out += ["", "**سرنخ‌ها:**", "",
                    f"- کل: {clu.get('total', 0)} · راست: {clu.get('true', 0)} · دروغ/کاشته: {clu.get('false', 0)}",
                    f"- تاییدشده (آزمایشگاه): {clu.get('verified', 0)} · حکمِ درست: "
                    f"{pct(clu.get('verified_right', 0), clu.get('verified', 0))}",
                    "- منبع: " + " · ".join(f"{k} {v}" for k, v in sorted(src.items(), key=lambda x: -x[1])),
                    f"- شایعه‌ی بقال درست بود: {pct(rum[0], rum[1])} ({rum[0]}/{rum[1]})"]
        return out

    def write(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        md = folder / "REPORT.md"
        md.write_text(self.to_markdown(), encoding="utf-8")
        (folder / "report.json").write_text(
            json.dumps({"games": self.games, "checks": self.checks,
                        "findings": self.sorted()}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        return md
