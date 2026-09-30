"""لایه‌ی رابط کاربری فارسی: صفحه‌ها، کیبوردهای اینلاین، ایموجی و انیمیشن‌ها.
همه‌ی callback_dataها به اندپوینت واقعی در bot._ROUTES اشاره می‌کنند (دکمه‌ی مرده نداریم).
"""
from __future__ import annotations
from typing import Dict, List, Optional
from .models import Custody, GameState
from .roles import ROLES, scenario_card
from .config import (BOT_USERNAME, MIN_PLAYERS, MAX_PLAYERS, PHASE_SECONDS,
                     JURY_ACQUIT_PERCENT, MAX_DAYS)

def _fa(n) -> str:
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

DIV = "─" * 18

ANIM: Dict[str, List[str]] = {
    "night": ["🌆 شهر می‌خوابد…", "🌃 چراغ‌ها خاموش شد…", "🌌 سکوت مطلق…", "🔪 چیزی در تاریکی حرکت کرد…"],
    "morning": ["🌅 سپیده زد…", "📰 شهر بیدار شد…", "🚨 خبر بد…"],
    "vote": ["🗳️ صندوق باز شد…", "🗳️▫️ شمارش…", "🗳️✅ نتیجه!"],
    "interrogation": ["🚪 در اتاق بازجویی بسته شد…", "🔦 چراغ روی صورت متهم…", "🎙️ ضبط شروع شد."],
    "jail": ["⛓️ صدای زنجیر…", "🔒 در سلول قفل شد.", "🤫 نقشش فاش نمی‌شود."],
    "court": ["⚖️ دادگاه رسمی است…", "📜 پرونده باز شد…", "👨‍⚖️ حکم نهایی!"],
}

CUSTODY_ICON = {
    Custody.FREE: "🟢", Custody.INTERROGATION: "🔦",
    Custody.TEMP_JAIL: "🔒", Custody.LIFE_JAIL: "⛓️",
}

BACK = ("🔙 بازگشت", "menu")
HOME = ("🏠 منوی اصلی", "menu")

MENU = [
    [("🎛️ همه‌ی دکمه‌ها", "commands")],
    [("🎮 شروع بازی همین‌جا", "new"), ("⚡ بلیتز", "blitz")],
    [("🌙 اکشن شبانه", "act"), ("🎯 توانایی‌های من", "abilities")],
    [("🔗 دعوت دوستان", "share"), ("📋 داشبورد", "dashboard")],
    [("🎓 آموزش تعاملی", "tutorial"), ("🎭 نقش‌ها", "roles")],
    [("🏆 برترین‌ها", "top"), ("📅 فصل", "season")],
    [("🎯 ماموریت‌ها", "missions"), ("🏅 دستاوردها", "achv")],
    [("📊 پروفایل", "profile"), ("🛠️ پنل ادمین", "admin")],
]


# ── رنگ دکمه‌ها (Bot API: style = danger 🔴 / success 🟢 / primary 🔵) ──
_DANGER = ("sos", "pause", "leave", "admin_ban", "new:confirm", "blitz:confirm", "jury:0")
_SUCCESS = ("ready", "startgame", "join", "jury:1", "resume", "rematch", "answer", "discuss",
            "scenario:")
_PRIMARY = ("dawn", "vote", "closevote", "closejury", "end", "board", "act", "dashboard", "lab:",
            "hunter:", "expose:")


def style_for(cb: str) -> Optional[str]:
    """رنگِ دکمه از روی معنای آن — یک جا برای کل بازی."""
    if not cb:
        return None
    if cb.endswith(":1") and cb.startswith(("ver:", "verdict:")):
        return "danger"                    # 🔒 حبس
    if cb.endswith(":0") and cb.startswith(("ver:", "verdict:")):
        return "success"                   # 🔓 آزادی
    if cb.startswith("interp:") and cb.count(":") == 2:
        return "success" if cb.endswith(":1") else "danger"
    if cb == "vote:0":
        return None
    if cb.startswith(_DANGER):
        return "danger"
    if cb.startswith(_SUCCESS):
        return "success"
    if cb.startswith(_PRIMARY):
        return "primary"
    return None


def button(t: str, d: str, style: Optional[str] = None) -> Dict:
    b = {"text": t, "callback_data": d}
    st = style or style_for(d)
    if st:
        b["style"] = st
    return b


def kb(rows: List[List[tuple]]) -> Dict:
    """هر دکمه (متن، callback) یا (متن، callback، رنگ)؛ رنگ پیش‌فرض از معنای callback."""
    return {"inline_keyboard": [[button(*b) for b in r] for r in rows]}


def with_back(rows: List[List[tuple]]) -> Dict:
    return kb(rows + [[BACK, HOME]])


def back_only() -> Dict:
    return kb([[BACK, HOME]])


def main_menu(private: bool = False, admin: bool = True) -> Dict:
    """منوی اصلی — در پیوی به‌جای «شروع بازی» دکمه‌ی افزودن به گروه؛ دکمه‌ی ادمین فقط برای ادمین."""
    rows = []
    for row in MENU:
        r = [b for b in row if admin or b[1] != "admin"]
        if private and any(b[1] == "new" for b in r):
            rows.append([("🗂️ پرونده‌ی بازی من", "board"), ("🔐 نقش من", "myrole")])
            continue
        if r:
            rows.append(r)
    out = kb(rows)
    if private:
        out["inline_keyboard"].insert(1, [{"text": "👥 افزودن ربات به گروه و شروع بازی",
                                           "url": share_links(0)["group"]}])
    return out


def add_to_group_kb() -> Dict:
    return {"inline_keyboard": [[{"text": "👥 افزودن ربات به گروه", "url": share_links(0)["group"]}],
                                [{"text": HOME[0], "callback_data": HOME[1]}]]}


def role_kb(p) -> Dict:
    """زیر کارت نقش: کارِ بعدیِ همین نقش."""
    rows = []
    if p.role and ROLES[p.role].ability:
        rows.append([("🌙 اکشن شبانه", "act"), ("🎯 توانایی‌های من", "abilities")])
    else:
        rows.append([("🎯 توانایی‌های من", "abilities")])
    rows.append([("🗂️ پرونده", "board"), ("📓 دفترچه", "notes")])
    rows.append([BACK, HOME])
    return kb(rows)


# ── صفحه‌ی اول: افزودن به گروه / دعوت دوست ──
def first_screen(private: bool = False) -> str:
    return ("🕵️ *به «کارآگاه» خوش آمدی!*\n" + DIV +
            "\nنسخه‌ی پیشرفته‌ی مافیا + معمای قتل — کاملاً فارسی."
            f"\n👥 {_fa(MIN_PLAYERS)} تا {_fa(MAX_PLAYERS)} بازیکن | 🕯️ ۴۰ پرونده | 🔦 حذف سه‌مرحله‌ای\n\n"
            "برای شروع، ربات را به گروه اضافه کن یا دوستانت را دعوت کن:")


def first_kb(chat_id: int, private: bool = False, admin: bool = True) -> Dict:
    """در پیوی لینکِ «دعوت به لابی» معنا ندارد (لابی در گروه است) — فقط افزودن به گروه (بن‌بست A4)."""
    l = share_links(chat_id)
    rows = [[{"text": "👥 افزودن به گروه", "url": l["group"]}]]
    if not private:
        rows.append([{"text": "📨 دعوت دوست به همین لابی", "url": l["share"]}])
    rows.append([{"text": "📢 افزودن به کانال", "url": l["channel"]}])
    menu = main_menu(private, admin)["inline_keyboard"]
    if private:
        menu = [r for r in menu if not any("url" in b for b in r)]
    return {"inline_keyboard": rows + menu}


def newbie_guide() -> str:
    return ("🎓 *خوش آمدی، کارآگاه تازه‌کار!*\n" + DIV +
            "\n🔪 بین ما قاتل هست؛ حتی خودش هم مطمئن نیست دیده شده یا نه!"
            "\n🌙 شب‌ها نقش‌ها اکشن می‌زنند، ☀️ روزها بحث و رای."
            "\n🔦 رای گروه → بازجویی (۱ شب) → 🔒 حبس موقت (۲ شب) → ⛓️ حبس ابد."
            "\n⛓️ نقشِ حبس‌ابدی تا آخر بازی فاش نمی‌شود!"
            "\n\n۱) «🔐 نقش من» را بزن تا نقش محرمانه‌ات به پیوی بیاید."
            "\n۲) منتظر شروع بازی توسط میزبان بمان. موفق باشی! 🍀")


def owner_panel(s: GameState) -> str:
    return ("🎛️ *پنل میزبان — فقط تو این را می‌بینی*\n" + DIV + "\n" + lobby_screen(s) +
            "\n\n▫️ وقتی ۴+ نفر شدید «🎬 شروع بازی» را بزن."
            "\n▫️ «📨 دعوت دوست» برای فرستادن لینک به بقیه.")


def owner_kb(chat_id: int) -> Dict:
    l = share_links(chat_id)
    return {"inline_keyboard": [
        [{"text": "🙋 منم بازی می‌کنم!", "callback_data": "join"}],
        [{"text": "✅ آماده‌ام (در پیوی)", "url": l["ready"]}],
        [{"text": "🎬 شروع بازی", "callback_data": "startgame"},
         {"text": "🎭 سناریو", "callback_data": "scenario"}],
        [{"text": "📨 دعوت دوست", "url": l["share"]},
         {"text": "👥 افزودن به گروه", "url": l["group"]}],
        [{"text": "📋 وضعیت", "callback_data": "status"},
         {"text": "🏠 منو", "callback_data": "menu"}],
    ]}


def lobby_kb(chat_id: int) -> Dict:
    """کیبورد لابی — هر کسی در گروه فوراً با یک تپ وارد می‌شود."""
    l = share_links(chat_id)
    return {"inline_keyboard": [
        [{"text": "🙋 منم بازی می‌کنم!", "callback_data": "join"}],
        [{"text": "✅ آماده‌ام (در پیوی)", "url": l["ready"]}],
        [{"text": "🎬 شروع بازی", "callback_data": "startgame"},
         {"text": "🚪 خروج از لابی", "callback_data": "leave"}],
        [{"text": "🎭 سناریو", "callback_data": "scenario"},
         {"text": "📨 دعوت دوست", "url": l["share"]}],
        [{"text": BACK[0], "callback_data": BACK[1]}, {"text": HOME[0], "callback_data": HOME[1]}],
    ]}


def lobby_screen(s: GameState) -> str:
    names = "\n".join(f"  {i+1}. {'✅' if p.ready else '⏳'} {p.name}"
                      for i, p in enumerate(s.players.values())) or "  — هنوز کسی نیست —"
    return (f"🏛️ *لابی کارآگاه*\n{DIV}\n{names}\n{DIV}\n"
            f"👥 {_fa(len(s.players))}/{_fa(MAX_PLAYERS)} (حداقل {_fa(MIN_PLAYERS)} نفر)\n"
            + scenario_card(getattr(s, "scenario", "classic"), len(s.players)) + "\n"
            "✅ = پیویِ ربات را باز کرده (نقش محرمانه آنجا می‌رود)\n"
            "🎬 میزبان «🎬 شروع بازی» را بزند.")


def role_card(role: str, knows: List[str]) -> str:
    r = ROLES[role]
    extra = "\n".join(f"  • {k}" for k in knows) or "  • اطلاعات ویژه‌ای نداری."
    goal = f"\n🏆 شرط برد: {r.goal}" if r.goal else ""
    return (f"{r.emoji} *نقش تو: {r.name}*\n{DIV}\n🎯 تیم: {r.align.value}\n"
            f"📜 {r.desc}{goal}\n{DIV}\n🔐 *اطلاعات محرمانه:*\n{extra}\n\n"
            f"⚠️ این پیام را به هیچ‌کس نشان نده.")


def status_board(s: GameState) -> str:
    rows = []
    for p in s.players.values():
        icon = CUSTODY_ICON[p.custody] if p.alive else "💀"
        tag = "" if p.custody is Custody.FREE else f" — {p.custody.value}"
        rows.append(f"{icon} {p.name}{tag}")
    return (f"📋 *وضعیت شهر — روز {s.day} | فاز: {s.phase.value}*\n{DIV}\n" +
            "\n".join(rows) + f"\n{DIV}\n" + clue_count(s))


def case_intro(s: GameState) -> str:
    from .roles import scenario_rules
    c = s.case
    tl = "\n".join(f"  • {t}" for t in c.timeline)
    story = scenario_rules(getattr(s, "scenario", "classic"))["story"]
    return (f"{story}\n{DIV}\n🕯️ *پرونده #{c.cid} — {c.title}*\n"
            f"⚰️ مقتول: {c.victim}\n📍 صحنه: {c.place}\n🔪 سلاح احتمالی: {c.weapon}\n"
            f"💰 انگیزه‌ی محتمل: {c.motive}\n🧩 گره‌ی پرونده: {c.twist}\n{DIV}\n🕰️ تایم‌لاین:\n{tl}\n{DIV}\n"
            + suspects_board(s) + "\n" + DIV + "\n🔎 *سرنخ‌های صحنه‌ی جرم* (بعضی راست، بعضی کاشته):\n"
            + "\n".join(clue_line(x) for x in s.clues))


def clue_count(s: GameState) -> str:
    cl = getattr(s, "clues", [])
    ok = sum(1 for c in cl if c["verified"] is True)
    bad = sum(1 for c in cl if c["verified"] is False)
    return f"🔎 سرنخ‌ها: {len(cl)} (✅{ok} ❌{bad} ❔{len(cl) - ok - bad})"


def suspects_board(s: GameState) -> str:
    """پرونده‌ی ظاهریِ عمومیِ همه — سرنخ‌ها با این‌ها سنجیده می‌شوند."""
    from .clues import trait_line
    rows = [f"  {'💀' if not p.alive else '⛓️' if p.custody is Custody.LIFE_JAIL else '👤'} "
            f"{p.name}: {trait_line(p.traits)}" for p in s.players.values() if getattr(p, "traits", None)]
    return "👥 *مظنونان (مشخصاتِ ظاهری، عمومی):*\n" + "\n".join(rows)


def clue_line(c: Dict) -> str:
    from .clues import clue_line as _cl
    return "  " + _cl(c)


def clue_block(new: List[Dict]) -> str:
    if not new:
        return "🔎 امشب سرنخ تازه‌ای پیدا نشد."
    return ("🔎 *سرنخ‌های تازه* (راست یا کاشته؟ با 🧪 آزمایشگاه و 🗂️ پرونده بسنج):\n"
            + "\n".join(clue_line(c) for c in new))


def patrol_block(rows) -> str:
    """🗺️ گشتِ صبحگاهی: صحنه‌های قبلی امروز چه چیزِ تازه‌ای نشان می‌دهند (فضاسازی، نه سرنخ)."""
    if not rows:
        return ""
    return ("\n\n🗺️ *گشتِ صبحگاهی در صحنه‌های قبلی* (فقط حال‌وهوا، سرنخ نیست):\n"
            + "\n".join(f"  📍 {loc} — {d}" for loc, d in rows))


def scene_map(s: GameState) -> str:
    """🗺️ نقشه‌ی صحنه‌ها: هر مکانِ سرنخ‌دار و آنچه هر روز نشان داد — هیچ روزی تکراری نیست."""
    from .scenes import history
    hist = history(s)
    if not hist:
        return ""
    lines = ["🗺️ *نقشه‌ی صحنه‌ها* (هر روز چیزی تازه):"]
    for loc, rows in hist.items():
        codes = "، ".join(c["code"] for c in s.clues if c.get("place") == loc)
        lines.append(f"  📍 {loc}" + (f" — سرنخ‌ها: {codes}" if codes else ""))
        lines += [f"      روز {_fa(d)}: {t}" for d, t in rows[-4:]]
    return "\n".join(lines)


def board(s: GameState) -> str:
    """🗂️ پرونده: همه‌ی سرنخ‌ها + مظنونان به ترتیبِ جور بودن با سرنخ‌های تاییدشده."""
    from .clues import board_ranking, matches, trait_line
    lines = [f"🗂️ *پرونده‌ی {s.case.title}*" if s.case else "🗂️ *پرونده*", DIV,
             "🔎 *سرنخ‌ها* (✅ راستِ تاییدشده · ❌ دروغِ تاییدشده · ❔ هنوز معلوم نیست):"]
    for c in s.clues:
        yes = sum(1 for v in c["votes"].values() if v)
        no = len(c["votes"]) - yes
        who = "، ".join(p.name for p in s.alive_players() if matches(p, c)) or "هیچ‌کسِ زنده"
        lines.append(clue_line(c) + (f"  👍{yes} 👎{no}" if c["votes"] else "")
                     + f"\n      ↳ جور با: {who}")
    sm = scene_map(s)
    if sm:
        lines += [DIV, sm]
    rank = [r for r in board_ranking(s) if r[1] or r[2]]
    if rank:
        lines += [DIV, "🎯 *جور بودن با سرنخ‌ها* (✅ تاییدشده / ❔ تاییدنشده):"]
        for uid, sure, open_ in rank[:10]:
            p = s.players[uid]
            bar = "🟥" * sure + "🟨" * open_
            lines.append(f"  {bar or '▫️'} {p.name} — ✅{sure} ❔{open_}  ({trait_line(p.traits)})")
    lines += [DIV, "⚠️ سرنخِ راست حتماً به مجرم اشاره نمی‌کند (گزارش خبرنگار ممکن است درباره‌ی پزشک باشد)؛ "
              "و سرنخِ دروغ ممکن است عمداً به تو اشاره کند."]
    return "\n".join(lines)


def vote_kb(s: GameState) -> Dict:
    """در دور دوم (مرگ ناگهانی) فقط نامزدهای مساوی دکمه دارند."""
    leaders = set(getattr(s, "tie_leaders", []) or []) if s.tie_break else set()
    rows = [[(f"👉 {p.name}", f"vote:{p.uid}")] for p in s.alive_players()
            if p.can_speak and (not leaders or p.uid in leaders)]
    rows.append([("⏭️ رای ممتنع", "vote:0")])
    rows.append([("📊 بستن رای‌گیری", "closevote")])
    return kb(rows)


def officer_kb(uid: int) -> Dict:
    # «پرسش» بدون آرگومان می‌رود تا ربات متنِ سؤال را بپرسد.
    # ver:<uid>:<x> — آیدی متهم در دکمه می‌ماند تا دکمه‌ی پیامِ دیروز روی متهمِ امروز اجرا نشود.
    return kb([[("🔦 سرنخ‌ها", "hints"), ("💬 پرسش", "ask")],
               [("🔒 حبس موقت", f"ver:{uid}:1")],
               [("🔓 تایید بی‌گناهی و آزادی", f"ver:{uid}:0")],
               [("🌙 پایان شب", "dawn"), ("🎛️ همه‌ی دکمه‌ها", "commands")]])


def morning_kb(s: GameState, officer_can_judge: bool) -> Dict:
    """دکمه‌های پیام صبح، متناسب با وضعیت: هیئت منصفه / حکم / گفتگو / پایان."""
    from .models import Phase
    if s.phase is Phase.END:
        return kb([[("🏁 پایان و افشای نقش‌ها", "end")]])
    if s.phase is Phase.JURY:
        return jury_kb()
    sus = s.suspect_uid
    if sus is not None and s.players[sus].custody is Custody.INTERROGATION:
        rows = []
        if officer_can_judge:
            rows += [[("🔒 حبس موقت", f"ver:{sus}:1"), ("🔓 آزادی", f"ver:{sus}:0")]]
        rows += [[("⚖️ هیئت منصفه", "jury")], [("📋 داشبورد", "dashboard")]]
        return kb(rows)
    return kb([[("💬 گفتگو", "discuss")], [("🗂️ پرونده", "board"), ("🧪 آزمایشگاه", "lab")],
               [("📋 داشبورد", "dashboard")]])


def jury_kb() -> Dict:
    return kb([[("🕊️ تبرئه", "jury:1"), ("⚖️ ادامه‌ی بازجویی", "jury:0")],
               [("📊 نتیجه", "closejury")]])


def help_text() -> str:
    sec = {k: _fa(v) for k, v in PHASE_SECONDS.items()}
    return ("📖 *قوانین کارآگاه (خلاصه‌ی RULES.md)*\n" + DIV +
            f"\n🌙 *شب* ({sec['شب']} ثانیه): نقش‌های شبانه در پیوی اکشن می‌دهند. ترتیب: "
            "پنهان‌کاری → محافظت → پاپوش/سم → قتل → سمِ سررسیده → اطلاعات. شب وقتی تمام می‌شود که "
            "همه اکشن داده باشند یا مهلت تمام شود؛ کسی نمی‌تواند شب را زودتر ببندد."
            f"\n☀️ *صبح* ({sec['صبح']} ثانیه): کشته‌ها، مدرک روز و ردهای دیشب اعلام می‌شود. اگر متهمی "
            "هست، اول تکلیف او روشن می‌شود."
            f"\n💬 *گفتگو* ({sec['گفتگو']} ثانیه) → 🗳️ *رای* ({sec['رای‌گیری']} ثانیه): بیشترین رای → بازجویی. "
            "ممتنع مجاز است. تساوی → یک دور «مرگ ناگهانی» فقط بین نفرات مساوی؛ تساوی دوباره → بدون بازداشت."
            "\n\n*حذف سه‌مرحله‌ای*"
            "\n۱) 🔦 بازجویی — ۱ شب. بازجو می‌پرسد، متهم خودش جواب می‌دهد. متهم در بازداشت از قتل در امان است."
            "\n۲) 🔒 حبس موقت — با حکم بازجو، ۲ شب. آزادی فقط با تایید بازجو وقتی متهم جدیدی وارد بازجویی شده."
            "\n۳) ⛓️ حبس ابد — حذف کامل، بدون افشای نقش."
            f"\n⚖️ *هیئت منصفه:* صبحِ بعد از بازجویی، ۲ نفر (یا وکیل تنها) می‌خواهند؛ {_fa(JURY_ACQUIT_PERCENT)}٪ = تبرئه (سناریوی دادگاه: ۵۰٪). "
            "اگر بازجو خودش متهم، زندانی یا حذف شده باشد، هیئت منصفه خودکار تشکیل می‌شود و تبرئه‌نکردن = حبس موقت."
            "\n🚨 *رای اضطراری:* یک بار در بازی، فقط در روز؛ ۸۰٪ رای = حبس موقتِ مستقیم."
            "\n\n*برد*"
            "\n🕵️ شهر: هیچ قاتل و جانی سریالی‌ای در بازی نماند."
            "\n🔪 قاتل‌ها: جانی در بازی نباشد و قاتل‌ها ≥ بقیه."
            "\n🩸 جانی سریالی: تنها بماند یا با یک نفر دیگر."
            "\n🎭 سپر بلا: زنده حبس ابد بگیرد. 🏪🚬 بقال و قاچاقچی: تا آخر زنده بمانند."
            "\n🔪 اگر قاتل حذف شود چاقو به همدست → سم‌ساز → خبرچین می‌رسد."
            f"\n⌛ بعد از {_fa(MAX_DAYS)} روز بازی بن‌بست (بدون برنده) تمام می‌شود.")


# ── اشتراک‌گذاری ──
def share_links(chat_id: int) -> Dict[str, str]:
    u = BOT_USERNAME
    return {
        "join": f"https://t.me/{u}?start=join_{chat_id}",
        "ready": f"https://t.me/{u}?start=ready_{chat_id}",
        "group": f"https://t.me/{u}?startgroup=play",
        "channel": f"https://t.me/{u}?startchannel=play",
        "share": ("https://t.me/share/url?url="
                  f"https://t.me/{u}?start=join_{chat_id}"
                  "&text=" + "بیا%20بازی%20کارآگاه%20🕵️"),
    }


def share_screen(chat_id: int, players: int) -> str:
    l = share_links(chat_id)
    return (f"🔗 *دعوت به بازی*\n{DIV}\n👥 {_fa(players)}/{_fa(MAX_PLAYERS)} نفر داخل لابی‌اند.\n\n"
            f"لینک دعوت مستقیم:\n`{l['join']}`\n\n"
            "با دکمه‌های زیر بفرست یا ربات را به گروه/کانال اضافه کن.")


def share_kb(chat_id: int) -> Dict:
    l = share_links(chat_id)
    return {"inline_keyboard": [
        [{"text": "📨 ارسال برای دوستان", "url": l["share"]}],
        [{"text": "👥 افزودن به گروه", "url": l["group"]},
         {"text": "📢 افزودن به کانال", "url": l["channel"]}],
        [{"text": "🔗 کپی لینک دعوت", "callback_data": "sharelink"}],
        [{"text": BACK[0], "callback_data": BACK[1]}, {"text": HOME[0], "callback_data": HOME[1]}],
    ]}


# ── پنل ادمین (رندر از ردیف‌های SQL) ──
def admin_menu() -> Dict:
    return with_back([[("🎲 بازی‌های فعال", "admin_games")],
                      [("👤 کاربران", "admin_users")],
                      [("📈 آمار کلی", "admin_stats")],
                      [("📊 تعادل نقش‌ها", "balance")]])


def admin_games_sql(rows) -> str:
    if not rows:
        return "🎲 هیچ بازی‌ای ثبت نشده است."
    out = []
    for r in rows:
        w = f" | 🏁 {r['winner']}" if r["winner"] else ""
        out.append(f"🆔 `{r['chat_id']}` | فاز: {r['phase']} | روز {r['day']} | "
                   f"👥 {r['players']} | 🕯️ {r['case_title'] or '—'}{w}")
    return "🎲 *بازی‌های ثبت‌شده*\n" + DIV + "\n" + "\n".join(out)


def admin_users_sql(rows) -> str:
    if not rows:
        return "👥 هنوز کاربری ثبت نشده."
    out = []
    for r in rows:
        b = " 🚫" if r["banned"] else ""
        out.append(f"👤 {r['name']} — 🆔 `{r['uid']}` — ⭐{r['xp']} — بازی‌ها: {r['in_games']}{b}")
    return ("👥 *کاربران*\n" + DIV + "\n" + "\n".join(out) +
            "\n\nبرای جزئیات: /admin_users <آیدی>")


def admin_user_card_sql(u, games, events) -> str:
    g = "\n".join(
        f"  • بازی `{r['chat_id']}` | {r['role'] or '—'} ({r['align'] or '—'}) | "
        f"{r['custody']} | {'زنده' if r['alive'] else 'کشته'} | فاز {r['phase']}"
        for r in games) or "  • در هیچ بازی‌ای نیست"
    e = "\n".join(f"  • {r['kind']}: {r['detail']}" for r in events) or "  • رویدادی ثبت نشده"
    b = " 🚫 (مسدود)" if u["banned"] else ""
    return (f"👤 *{u['name']}*{b}\n{DIV}\n"
            f"🆔 آیدی: `{u['uid']}`\n⭐ XP: {u['xp']} | 🪙 {u['coins']}\n"
            f"🎮 بازی‌ها: {u['games']} | 🏆 برد: {u['wins']}\n{DIV}\n"
            f"🎭 حضور در بازی‌ها:\n{g}\n{DIV}\n📝 رویدادهای اخیر:\n{e}\n\n"
            f"🚫 برای مسدودسازی: /admin_ban {u['uid']}")


def admin_stats_sql(st: Dict) -> str:
    top = "\n".join(f"  {i+1}. {r['name']} — ⭐{r['xp']}" for i, r in enumerate(st["top"])) or "  —"
    return (f"📈 *آمار کلی (SQL)*\n{DIV}\n"
            f"👥 کاربران: {st['users']} (مسدود: {st['banned']})\n"
            f"🎲 بازی‌ها: {st['games']} (فعال: {st['active']})\n"
            f"📝 رویدادها: {st['events']}\n{DIV}\n🏆 برترین‌ها:\n{top}")


# ── ایده ۲۸: آموزش تعاملی (شبیه‌سازی یک دور مینی) ──
def tutorial_text() -> str:
    return ("🎓 *آموزش تعاملی — یک دور مینی با بات‌ها*\n" + DIV +
            "\n🌙 *شب:* سارا (قاتلِ فرضی) رضا را هدف می‌گیرد. پزشک از مریم محافظت می‌کند."
            "\n☀️ *صبح:* جسد رضا پیدا شد! مدرک E1: 🖐️ اثر انگشت — سه تفسیر دارد، هیچ‌کدام قطعی نیست."
            "\n💬 *گفتگو:* سارا می‌گوید «من خواب بودم». علی می‌گوید «سارا را نزدیک اتاق دیدم»."
            "\n🗳️ *رای:* اکثریت به سارا → 🔦 بازجویی (۱ شب)."
            "\n🔦 *بازجویی:* بازجو می‌پرسد «کجا بودی؟» و سرنخ مبهم می‌گیرد: «دستش می‌لرزد»."
            "\n⚖️ دو نفر هیئت منصفه می‌خواهند؛ رای نمی‌آورد → 🔒 حبس موقت (۲ شب)."
            "\n⛓️ دو شب بی‌تبرئه → حبس ابد؛ *نقشش فاش نمی‌شود!*"
            "\n🏁 پایان: معلوم می‌شود سارا واقعاً قاتل بود — شهر برد! ⭐ MVP: علی."
            "\n\nحالا خودت: «🎮 شروع بازی» را بزن!")


# ── ایده ۲۹: نگاشت صدای فاز (اگر فایل موجود باشد، آداپتور ویس می‌فرستد) ──
VOICE = {"night": "night.ogg", "morning": "morning.ogg", "vote": "vote.ogg",
         "interrogation": "interrogation.ogg", "jail": "jail.ogg", "court": "court.ogg"}


# ── بهبود ۱: پنل اکشن خصوصی — انتخاب هدف با نام، بدون آیدی عددی ──
ABILITY_TEXT = {
    "kill": ("🔪 قتل", "امشب چه کسی را هدف می‌گیری؟"),
    "investigate": ("🕵️ استعلام هویت", "هویت تیمیِ چه کسی را استعلام می‌کنی؟ نتیجه سحر می‌رسد."),
    "protect": ("💉 محافظت", "امشب از چه کسی محافظت می‌کنی؟"),
    "watch": ("🛡️ نگهبانی", "چه کسی را زیر نظر می‌گیری؟ تعداد ملاقات‌هایش را می‌بینی."),
    "poison": ("☠️ مسموم‌سازی", "چه کسی را مسموم می‌کنی؟ دو شب بعد می‌میرد مگر پزشک برسد."),
    "frame": ("🧤 پاپوش‌دوزی", "اثر انگشت جعلی روی چه کسی بگذارم؟"),
    "spy": ("📞 خبرچینی", "یک نفر را انتخاب کن؛ می‌فهمی بازجو سراغ چه کسی رفته."),
    "hide": ("🚬 مخفی‌کاری", "چه کسی را از دید کارآگاه و نگهبان پنهان می‌کنی؟"),
    "autopsy": ("🧪 آزمایشگاه", "یک نفر را انتخاب کن؛ اصالت مدرک امشب را می‌فهمی."),
    "reveal": ("📰 افشاگری", "یک نفر را انتخاب کن؛ یک مدرک اضافه برای کل شهر رو می‌شود."),
}


def action_panel(s: GameState, p, chosen=None, ab=None, targets=None) -> str:
    """متن پنل اکشن شبانه‌ی یک بازیکن. ab: توانایی مؤثر (جانشین قاتل «kill» دارد)."""
    ab = ROLES[p.role].ability if ab is None else ab
    if ab == "hunter":
        title, ask = "🏹 شلیک آخر", "اگر کشته شوی یا حبس ابد بگیری، چه کسی را با خودت می‌بری؟"
    elif not ab:
        return (f"{ROLES[p.role].emoji} *{p.role}*\n{DIV}\n"
                "🌙 نقش تو اکشن شبانه ندارد. بخواب و صبح بحث کن.")
    else:
        title, ask = ABILITY_TEXT.get(ab, (f"🌙 {ab}", "هدفت را انتخاب کن:"))
    done = f"\n\n✅ انتخاب فعلی: *{s.players[chosen].name}* (می‌توانی عوض کنی)" if chosen else ""
    if targets is not None and not targets:
        done += ("\n\n😶 امشب هدفِ مجازی نداری: بقیه یا در بازداشت‌اند (در امان)، یا هم‌تیمی‌ات‌اند، "
                 "یا قید «دو شب پیاپی» جلویت را گرفته. منتظرت نمی‌مانیم.")
    return (f"{title} — شب {s.day}\n{DIV}\n{ask}{done}")


def action_kb(s: GameState, p, targets: List[int], chosen=None) -> Dict:
    """دکمه‌ی هر هدف با نام؛ بدون تایپ آیدی."""
    cmd = "hunter" if p.role == "شکارچی" else "act"
    rows = [[(("✅ " if t == chosen else "👉 ") + s.players[t].name, f"{cmd}:{t}")]
            for t in targets]
    if not rows:
        rows = [[("— امشب هدفِ مجازی نداری —", "notes")]]
    return kb(rows + [[("📋 داشبورد", "dashboard")], [BACK, HOME]])


# ── بهبود ۳: داشبورد راهنما ──
def dashboard(s: GameState, remaining=None, pending=(), next_step="") -> str:
    """در شب فقط *تعداد* منتظرها را می‌گوید.

    نام بردن از کسانی که اکشن شبانه نداده‌اند یعنی لو دادن اینکه چه کسانی
    اصلاً نقشِ اکشن‌دار دارند — و در نتیجه چه کسانی شهروند ساده‌اند.
    در رای‌گیری و هیئت منصفه این اطلاعات عمومی است، پس نام می‌آید.
    """
    from .models import Phase
    secret = s.phase in (Phase.NIGHT, Phase.INTERROGATION)
    rows = []
    for p in s.players.values():
        icon = CUSTODY_ICON[p.custody] if p.alive else "💀"
        tag = "" if p.custody is Custody.FREE or not p.alive else f" — {p.custody.value}"
        wait = " ⏳" if (not secret and p.uid in pending) else ""
        rows.append(f"{icon} {p.name}{tag}{wait}")
    timer = f"\n⏳ باقی‌مانده: {remaining} ثانیه" if remaining is not None else ""
    # در شب حتی *تعداد* را هم نمی‌گوییم: اگر کسی مدام داشبورد را ببیند،
    # لحظه‌ی کم‌شدن عدد می‌گوید چه وقت آن نقشِ مخفی اکشنش را داد.
    if secret:
        who = "\n🌙 شب در جریان است؛ پیشرفتِ اکشن‌ها محرمانه می‌ماند."
    elif pending:
        who = "\n⏳ منتظر: " + "، ".join(s.players[u].name for u in pending)
    else:
        who = ""
    return (f"📋 *داشبورد — روز {s.day} | فاز: {s.phase.value}*{timer}\n{DIV}\n"
            + "\n".join(rows) +
            f"\n{DIV}\n{clue_count(s)}{who}"
            f"\n➡️ *قدم بعدی:* {next_step}")


def dashboard_kb(s: GameState) -> Dict:
    """دکمه‌ی «کار بعدی» متناسب با فاز — بازیکن دنبال دستور نگردد."""
    from .models import Phase
    ph = s.phase
    rows = []
    if ph in (Phase.NIGHT, Phase.INTERROGATION):
        rows = [[("🌙 اکشن شبانه‌ی من", "act")], [("🌙 پایان شب", "dawn")]]
    elif ph is Phase.MORNING:
        rows = [[("💬 گفتگو", "discuss")]]
        if s.suspect_uid is not None:
            sus = s.suspect_uid
            rows = [[("⚖️ هیئت منصفه", "jury")],
                    [("🔒 حبس موقت", f"ver:{sus}:1"), ("🔓 آزادی", f"ver:{sus}:0")]]
    elif ph is Phase.DISCUSSION:
        rows = [[("🗳️ رای‌گیری", "vote")]]
    elif ph is Phase.VOTE:
        rows = [[("📊 بستن رای‌گیری", "closevote")]]
    elif ph is Phase.JURY:
        rows = [[("🕊️ تبرئه", "jury:1"), ("⚖️ ادامه‌ی بازجویی", "jury:0")],
                [("📊 نتیجه‌ی هیئت", "closejury")]]
    elif ph is Phase.END:
        rows = [[("🏁 پایان و افشای نقش‌ها", "end")]]
    return kb(rows + [[("🗂️ پرونده", "board"), ("🔄 بروزرسانی", "dashboard")],
                      [("📝 دفترچه", "notes"), BACK]])


# ── بهبود ۸: گزارش تعادل ──
def balance_report_sql(roles, seats, aband) -> str:
    if not roles:
        return "📊 هنوز بازیِ تمام‌شده‌ای ثبت نشده است."
    r = "\n".join(f"  {x['role']} ({x['align']}) — {x['pct']}٪ از {x['n']} بازی"
                  for x in roles)
    s = "\n".join(f"  {x['seats']} نفره — {x['games']} بازی | "
                  f"{x['avg_days']} روز | {x['avg_min']} دقیقه" for x in seats) or "  —"
    return (f"📊 *تعادل بازی*\n{DIV}\n🎭 نرخ برد هر نقش:\n{r}\n{DIV}\n"
            f"👥 بر اساس تعداد بازیکن:\n{s}\n{DIV}\n"
            f"🚪 رهاشدگی: {aband['abandoned']}/{aband['games']} ({aband['pct']}٪)")
