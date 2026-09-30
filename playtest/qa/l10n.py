"""🌍 Localization (L10n) & Internationalization (I18n): بازی فارسی و راست‌به‌چپ است.

- رقم‌ها: هیچ رقمِ لاتین در متنِ بازیکن (جز کدهای C12، لینک و `کد`)
- هیچ کلمه‌ی انگلیسی/اثرِ پایتون (None، True، Phase.، [' …) به بازیکن نمی‌رسد
- بدون mojibake (Ø، Ù، �) — کدگذاریِ UTF-8 سالم؛ همه‌ی فایل‌های مخزن UTF-8 و بدون BOM
- برچسب دکمه‌ها کوتاه (بریده نشود) و فارسی
- نامِ بازیکن‌ها: خیلی بلند، فقط ایموجی، لاتین با _ و *، کاراکترهای کنترلیِ جهت (RLO) که متن را
  وارونه/جعل می‌کنند، نیم‌فاصله (باید بماند)
- جهت: پیام با حرفِ لاتین شروع نشود (در تلگرام چپ‌چین می‌شد)
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from karagah.bot import GAMES, handle

from .common import Section, capture_sessions, fresh, timed

ALLOWED_LATIN = {"MVP", "XP", "PNG", "Bot", "API", "RTL"}
DIGITS = re.compile(r"(https?://\S+|t\.me/\S+|`[^`]*`)|(?<![A-Za-z_\d])([0-9]+)(?![A-Za-z_])")
LATIN_WORD = re.compile(r"(https?://\S+|t\.me/\S+|`[^`]*`)|\b([A-Za-z]{3,})\b")
PY_LEAK = re.compile(r"\bNone\b|\bTrue\b|\bFalse\b|Phase\.|Custody\.|Align\.|\['|\{'|<built-in|Traceback")
MOJIBAKE = re.compile(r"[ØÙÃÂ]\S|�")
BIDI = re.compile(r"[‪-‮⁦-⁩]")
PERSIAN = re.compile(r"[؀-ۿ]")


def scan_messages(sec: Section, msgs) -> None:
    digits, words, leaks, moj, ltr = Counter(), Counter(), Counter(), 0, 0
    long_labels, non_fa_labels = Counter(), Counter()
    for m in msgs:
        t = m.text or ""
        for keep, d in DIGITS.findall(t):
            if d:
                digits[d] += 1
        for keep, w in LATIN_WORD.findall(t):
            if w and w not in ALLOWED_LATIN:
                words[w] += 1
        leaks.update(PY_LEAK.findall(t))
        moj += bool(MOJIBAKE.search(t))
        import unicodedata
        strong = next((unicodedata.bidirectional(ch) for ch in t
                       if unicodedata.bidirectional(ch) in ("L", "R", "AL")), "")
        ltr += strong == "L"                       # پاراگراف در تلگرام چپ‌چین می‌شد
        for row in (m.keyboard or {}).get("inline_keyboard") or []:
            for b in row:
                lab = b.get("text", "")
                if len(lab) > 34:
                    long_labels[lab] += 1
                if not PERSIAN.search(lab) and not re.fullmatch(r"[\W\d_C]+", lab):
                    non_fa_labels[lab] += 1
    sec.metrics["latin_digits_in_player_text"] = sum(digits.values())
    sec.metrics["english_words"] = ", ".join(f"{w}×{c}" for w, c in words.most_common(6)) or "—"
    sec.metrics["python_artifacts"] = sum(leaks.values())
    sec.metrics["mojibake_messages"] = moj
    sec.metrics["messages_starting_ltr"] = ltr
    sec.metrics["button_labels_over_34_chars"] = len(long_labels)
    sec.check(not digits, f"رقمِ لاتین در متن: {digits.most_common(5)}")
    sec.check(not leaks, f"اثرِ پایتون در متن: {dict(leaks)}")
    sec.check(moj == 0, f"{moj} پیام mojibake دارد")
    sec.check(ltr == 0, f"{ltr} پیام با حرفِ لاتین شروع می‌شود")
    if words:
        sec.notes.append("کلمه‌های لاتینِ باقی‌مانده (بیشتر نام نقش/واژه‌ی رایج): "
                         + ", ".join(w for w, _ in words.most_common(10)))
    if long_labels:
        sec.notes.append("برچسب‌های بلند (روی موبایل ممکن است بریده شوند): "
                         + " | ".join(list(long_labels)[:5]))
    sec.check(not non_fa_labels, f"دکمه‌ی بدون فارسی: {list(non_fa_labels)[:5]}")


def names(sec: Section) -> None:
    fresh()
    G = -313_313
    weird = {2: "A" * 80, 3: "🙂🙂🙂", 4: "John_Doe*[x](y)", 5: "‮خانم‬ رضایی",
             6: "زهرا‌سادات", 7: "   ", 8: "<b>x</b>", 9: "‏‎"}
    handle("new", G, 1, "Host")
    for u, nm in weird.items():
        handle("join", G, u, nm)
    g = GAMES[G]
    got = {u: g.s.players[u].name for u in weird if u in g.s.players}
    sec.metrics["weird_names_joined"] = f"{len(got)}/{len(weird)}"
    sec.check(all(len(n) <= 64 for n in got.values()), "نامِ بیش از ۶۴ نویسه")
    sec.check(not any(BIDI.search(n) for n in got.values()), "کاراکترِ کنترلِ جهت (RLO) در نام ماند — جعلِ متن")
    sec.check("‌" in got.get(6, ""), "نیم‌فاصله‌ی نام حذف شد")
    sec.check(all(n.strip() for n in got.values()), "نامِ خالی پذیرفته شد")
    r = handle("startgame", G, 1, "force")
    sec.check("خطای داخلی" not in r["text"], "شروع با نام‌های عجیب خطا داد")


def repo_files(sec: Section) -> None:
    root = Path(__file__).resolve().parents[2]
    bad, bom = [], []
    for p in list(root.glob("karagah/**/*.py")) + list(root.glob("playtest/**/*.py")) + list(root.glob("*.md")):
        raw = p.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            bom.append(p.name)
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            bad.append(p.name)
    sec.check(not bad, f"فایلِ غیر UTF-8: {bad}")
    sec.check(not bom, f"BOM در: {bom}")
    sec.metrics["repo_files_utf8"] = "بله"


def run(quick: bool = True) -> Section:
    sec = Section("Localization & I18n", "رقم فارسی، نشتِ انگلیسی/پایتون، mojibake، برچسب دکمه، نام‌های عجیب، UTF-8")
    with timed(sec):
        configs = [(n, 2, sc, "group") for sc in ("classic", "court", "chaos") for n in ((5, 9) if quick else range(4, 11))]
        cap, _g, _r = capture_sessions(configs)
        msgs = cap.bot_msgs()
        sec.metrics["messages_scanned"] = len(msgs)
        scan_messages(sec, msgs)
        for fn in (names, repo_files):
            try:
                fn(sec)
            except Exception as e:                       # noqa: BLE001
                sec.fail(f"{fn.__name__}: {e!r}")
    return sec
