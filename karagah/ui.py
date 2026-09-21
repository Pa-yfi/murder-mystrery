"""لایه‌ی رابط کاربری فارسی: صفحه‌ها، کیبوردهای اینلاین، ایموجی و انیمیشن‌ها.
همه‌ی callback_dataها به اندپوینت واقعی در bot._ROUTES اشاره می‌کنند (دکمه‌ی مرده نداریم).
"""
from __future__ import annotations
from typing import Dict, List
from .models import Custody, GameState
from .roles import ROLES
from .config import BOT_USERNAME, MIN_PLAYERS, MAX_PLAYERS

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


def kb(rows: List[List[tuple]]) -> Dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r] for r in rows]}


def with_back(rows: List[List[tuple]]) -> Dict:
    return kb(rows + [[BACK, HOME]])


def back_only() -> Dict:
    return kb([[BACK, HOME]])


# منوی وسطِ بازی: دیگر «شروع بازی» و «بلیتز» ندارد — آن دو بازیِ در جریان را
# دور می‌انداختند و باعث می‌شدند منو انگار به قبل از بازی برگردد.
IN_GAME_MENU = [
    [("🎛️ همه‌ی دکمه‌ها", "commands")],
    [("🎯 توانایی‌های من", "abilities"), ("📋 داشبورد", "dashboard")],
    [("🌙 اکشن شبانه", "act"), ("📓 دفترچه‌ی من", "notes")],
    [("🏙️ وضعیت شهر", "status"), ("🔐 نقش من", "myrole")],
    [("🗂️ بایگانی نقش من", "archive"), ("🎭 نقش‌ها", "roles")],
    [("📖 قوانین", "help"), ("🏳️ تسلیم می‌شوم", "surrender")],
]


def main_menu(state: GameState | None = None, g=None, p=None) -> Dict:
    """منو با فاز بازی *و با کارهای قانونیِ همین بازیکن* ساخته می‌شود.

    §۱۳ ST03: یک فهرستِ ثابت برای همه یعنی نقشی که اکشن شبانه ندارد هم
    «اکشن شبانه» می‌بیند و بعد از کلیک خطا می‌گیرد. منو از روی توانایی
    ساخته می‌شود، نه از روی یک لیستِ یکسان.
    """
    from .models import Phase as _P
    from . import menus
    if state is None or state.phase in (_P.LOBBY, _P.END):
        return kb(MENU)
    if g is None or p is None:
        return kb(IN_GAME_MENU)
    rows = [[("🎛️ همه‌ی دکمه‌ها", "commands")]]
    first = []
    if menus.may_use("killer", g, p):
        first.append(("🔪 جعبه‌ابزار قاتل", "killer"))
    elif menus.may_use("act", g, p):
        first.append(("🌙 اکشن شبانه", "act"))
    if menus.may_use("hunter", g, p):
        first.append(("🏹 هدف شلیک آخر", "hunter"))
    if menus.may_use("hints", g, p) and state.suspect_uid:
        first.append(("🔦 سرنخ‌های بازجویی", "hints"))
    if menus.may_use("defense", g, p):
        first.append(("🛡️ دفاع من", "defense"))
    if first:
        rows += [first[i:i + 2] for i in range(0, len(first), 2)]
    rows.append([("🗂️ بایگانی نقش من", "archive"), ("🎯 توانایی‌های من", "abilities")])
    rows.append([("📋 داشبورد", "dashboard"), ("📓 دفترچه‌ی من", "notes")])
    rows.append([("🏙️ وضعیت شهر", "status"), ("📖 قوانین", "help")])
    if p.uid == g.owner:                       # ST06: مدیریتِ همین بازی
        rows.append([("🛠️ مدیریت همین بازی", "manage")])
    rows.append([("🏳️ تسلیم می‌شوم", "surrender")])
    return kb(rows)


# ── صفحه‌ی اول: افزودن به گروه / دعوت دوست ──
def first_screen() -> str:
    return ("🕵️ *به «کارآگاه» خوش آمدی!*\n" + DIV +
            "\nنسخه‌ی پیشرفته‌ی مافیا + معمای قتل — کاملاً فارسی."
            f"\n👥 {_fa(MIN_PLAYERS)} تا {_fa(MAX_PLAYERS)} بازیکن | 🕯️ ۴۰ پرونده | 🔦 حذف سه‌مرحله‌ای\n\n"
            "برای شروع، ربات را به گروه اضافه کن یا دوستانت را دعوت کن:")


def first_kb(chat_id: int, state: GameState | None = None) -> Dict:
    from .models import Phase as _P
    if state is not None and state.phase not in (_P.LOBBY, _P.END):
        return main_menu(state)          # بازی در جریان است؛ منوی داخلِ بازی
    l = share_links(chat_id)
    rows = [
        [{"text": "👥 افزودن به گروه", "url": l["group"]}],
        [{"text": "📨 دعوت دوست", "url": l["share"]}],
        [{"text": "📢 افزودن به کانال", "url": l["channel"]}],
    ]
    return {"inline_keyboard": rows + kb(MENU)["inline_keyboard"]}


def newbie_guide() -> str:
    return ("🎓 *خوش آمدی، کارآگاه تازه‌کار!*\n" + DIV +
            "\n🔪 بین ما قاتل هست؛ حتی خودش هم مطمئن نیست دیده شده یا نه!"
            "\n🌙 شب‌ها نقش‌ها اکشن می‌زنند، ☀️ روزها بحث و رای."
            "\n🔦 رای گروه → گفتگوی بازجویی → 🔒 حبس موقت (۲ شب کامل) → ⛓️ حبس ابد."
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
        [{"text": "1️⃣ 🙋 منم بازی می‌کنم!", "callback_data": "join"}],
        [{"text": "2️⃣ ✅ آماده‌ام (پیوی باز شود)", "url": l["ready"]}],
        [{"text": "3️⃣ 🎬 شروع بازی", "callback_data": "startgame"}],
        [{"text": "📨 دعوت دوست", "url": l["share"]},
         {"text": "👥 افزودن به گروه", "url": l["group"]}],
        [{"text": "📋 وضعیت", "callback_data": "status"},
         {"text": "🏠 منو", "callback_data": "menu"}],
    ]}


def lobby_kb(chat_id: int) -> Dict:
    """کیبورد لابی — دکمه‌ها به ترتیبِ همان سه قدمِ روی صفحه.

    «آماده‌ام» یک لینکِ پیوی است، نه callback: باید در پیوی باز شود وگرنه
    ربات نمی‌تواند نقش محرمانه را بفرستد. خودِ همان لینک عضو هم می‌کند،
    پس ترتیبِ «ورود» و «آماده‌ام» دیگر فرقی نمی‌کند.
    """
    l = share_links(chat_id)
    return {"inline_keyboard": [
        [{"text": "1️⃣ 🙋 منم بازی می‌کنم!", "callback_data": "join"}],
        [{"text": "2️⃣ ✅ آماده‌ام (پیوی باز شود)", "url": l["ready"]}],
        [{"text": "3️⃣ 🎬 شروع بازی", "callback_data": "startgame"}],
        [{"text": "🚪 خروج از لابی", "callback_data": "leave"},
         {"text": "📨 دعوت دوست", "url": l["share"]}],
        [{"text": BACK[0], "callback_data": BACK[1]}, {"text": HOME[0], "callback_data": HOME[1]}],
    ]}


def lobby_screen(s: GameState) -> str:
    names = "\n".join(f"  {i+1}. {'✅' if p.ready else '⏳'} {p.name}"
                      for i, p in enumerate(s.players.values())) or "  — هنوز کسی نیست —"
    n, waiting = len(s.players), [p.name for p in s.players.values() if not p.ready]
    if n < MIN_PLAYERS:
        step = f"🧍 قدم ۱: هنوز {_fa(MIN_PLAYERS - n)} نفر کم داریم — «🙋 منم بازی می‌کنم!»"
    elif waiting:
        step = ("✅ قدم ۲: این‌ها هنوز «آماده‌ام» نزده‌اند: " + "، ".join(waiting) +
                "\n(تا پیویشان باز نشود، نقش محرمانه به دستشان نمی‌رسد.)")
    else:
        step = "🎬 قدم ۳: همه آماده‌اند — میزبان «🎬 شروع بازی» را بزند."
    return (f"🏛️ *لابی کارآگاه*\n{DIV}\n{names}\n{DIV}\n"
            f"👥 {_fa(n)}/{_fa(MAX_PLAYERS)} (حداقل {_fa(MIN_PLAYERS)} نفر)\n"
            "⏳ = هنوز آماده نیست | ✅ = پیویش باز است\n"
            f"{DIV}\n➡️ {step}")


def role_card(role: str, knows: List[str]) -> str:
    r = ROLES[role]
    extra = "\n".join(f"  • {k}" for k in knows) or "  • اطلاعات ویژه‌ای نداری."
    from .roles import title_of
    return (f"{r.emoji} *نقش تو: {title_of(r.name)}*\n{DIV}\n🎯 تیم: {r.align.value}\n"
            f"📜 {r.desc}\n{DIV}\n🔐 *اطلاعات محرمانه:*\n{extra}\n\n"
            f"⚠️ این پیام را به هیچ‌کس نشان نده.")


def status_board(s: GameState) -> str:
    rows = []
    for p in s.players.values():
        icon = CUSTODY_ICON[p.custody] if p.alive else "💀"
        tag = "" if p.custody is Custody.FREE else f" — {p.custody.value}"
        rows.append(f"{icon} {p.name}{tag}")
    return (f"📋 *وضعیت شهر — روز {s.day} | فاز: {s.phase.value}*\n{DIV}\n" +
            "\n".join(rows) + f"\n{DIV}\n🔎 مدارک رو شده: {len(s.revealed_evidence)}/۶")


def case_intro(s: GameState) -> str:
    c = s.case
    tl = "\n".join(f"  • {t}" for t in c.timeline)
    return (f"🕯️ *پرونده #{c.cid} — {c.title}*\n{DIV}\n"
            f"⚰️ مقتول: {c.victim}\n📍 صحنه: {c.place}\n🔪 سلاح احتمالی: {c.weapon}\n"
            f"💰 انگیزه‌ی محتمل: {c.motive}\n{DIV}\n🕰️ تایم‌لاین:\n{tl}")


def evidence_card(ev: Dict) -> str:
    it = "\n".join(f"  ▫️ {i}" for i in ev["interpretations"])
    return (f"🔎 *مدرک {ev['code']}: {ev['title']}*\n{DIV}\n🧠 تفسیرهای ممکن:\n{it}\n\n"
            "❗ هیچ مدرکی به‌تنهایی قاتل را ثابت نمی‌کند.")


def vote_kb(s: GameState) -> Dict:
    rows = [[(f"👉 {p.name}", f"vote:{p.uid}")] for p in s.alive_players() if p.can_speak]
    rows.append([("⏭️ رای ممتنع", "vote:0")])
    rows.append([("📊 بستن رای‌گیری", "closevote")])
    return kb(rows)


def vote_board(s: GameState) -> str:
    """تابلوی زنده‌ی رای‌گیری در گروه: چه کسی رای داده، نه اینکه به چه کسی.

    ساعت‌شنی کنار هر اسم با هر رای به ✅ تبدیل می‌شود، پس همه می‌بینند
    منتظر چه کسی‌اند بی‌آنکه محتوای رای لو برود.
    """
    rows = []
    for p in s.players.values():
        if not p.can_vote:
            rows.append(f"➖ {p.name}" + ("" if p.alive else " 💀"))
        else:
            rows.append(f"{'✅' if p.uid in s.votes else '⏳'} {p.name}")
    voted, total = len(s.votes), len([p for p in s.alive_players() if p.can_vote])
    return (f"🗳️ *رای‌گیری — روز {_fa(s.day)}*\n{DIV}\n" + "\n".join(rows) +
            f"\n{DIV}\n📊 {_fa(voted)}/{_fa(total)} رای ثبت شد."
            "\nبرگه‌ی رای در پیویِ خودت است؛ اینجا فقط پیشرفت را می‌بینی.")


def vote_board_kb() -> Dict:
    return kb([[("🗳️ برگه‌ی رای من", "castvote")],
               [("📊 بستن رای‌گیری", "closevote")], [BACK, HOME]])


def officer_panel(s: GameState) -> str:
    """متنِ خصوصیِ بازجو. هرگز در گروه فرستاده نمی‌شود."""
    sus = s.players[s.suspect_uid].name if s.suspect_uid else "—"
    return (f"🔦 *اتاق بازجویی — فقط تو این را می‌بینی*\n{DIV}\n"
            f"🪑 متهم: *{sus}*\n\n"
            "۱) «🔦 سرنخ‌ها» — نشانه‌های امشب (هر شب فرق می‌کند).\n"
            "۲) «💬 پرسش» — سؤال به پیویِ متهم می‌رود و *خودش* جواب می‌دهد.\n"
            "۳) «📕 پایان گفتگو» و بعد «🔦 سرنخ پایانی». تازه آن وقت:\n"
            "   🔒 *حبس موقت* — دو شب کامل.\n"
            "   ⚖️ *هیئت دو نفره* — تصمیم را به دو داور بسپار.\n"
            "   🕊️ یا آزادش کن؛ شواهد کافی نیست.\n\n"
            "⚠️ این پنل را به هیچ‌کس نشان نده؛ نقشت لو می‌رود.")


def officer_kb(uid: int, s: GameState | None = None) -> Dict:
    """کیبورد بازجو — دکمه‌های تصمیم فقط بعد از دروازه‌ی R07.1 ظاهر می‌شوند."""
    if s is None:                      # سازگاری با فراخوانی‌های قدیمی
        return kb([[("💬 پرسش", "ask"), ("📕 پایان گفتگو", "closeroom")],
                   [("🔦 سرنخ پایانی", "hints")],
                   [("🌅 پایان شب", "dawn"), ("🎛️ همه‌ی دکمه‌ها", "commands")]])
    rows = []
    if not s.room_closed:
        rows.append([("💬 پرسش تازه", "ask"), ("📕 پایان گفتگو", "closeroom")])
    elif not s.hint_ack:
        rows.append([("🔦 سرنخ پایانی", "hints")])
    else:                              # دروازه باز شد → سه انتخابِ R07.1
        rows.append([("🔒 حبس موقت برای دو شب", f"ver:{uid}:1")])
        rows.append([("⚖️ ارجاع به هیئت دو نفره", "refer")])
        rows.append([("🕊️ آزادی؛ شواهد کافی نیست", f"ver:{uid}:0")])
    rows.append([("🌅 پایان شب", "dawn"), ("🎛️ همه‌ی دکمه‌ها", "commands")])
    return kb(rows)


def jury_kb() -> Dict:
    """R05.1: حبس / آزادی / «نمی‌توانم داوری کنم» (که رایِ حبس نیست)."""
    return kb([[("🔒 حبس موقت", "jury:0"), ("🕊️ آزادی", "jury:1")],
               [("🤷 نمی‌توانم داوری کنم", "jury:1")],
               [("📊 نتیجه", "closejury")], [BACK, HOME]])


def jury_wait_kb(s: GameState) -> Dict:
    """وقتی هیئت هنوز تشکیل نشده: راهِ پیشِ رو را نشان بده، نه بن‌بست."""
    rows = [[("🔦 وضعیت اتاق بازجویی", "hints")]]
    if s.suspect_uid is None:
        rows = [[("🗳️ رای‌گیری", "vote")]]
    return kb(rows + [[("📋 داشبورد", "dashboard")], [BACK, HOME]])


# ── جعبه‌ابزار شبانه‌ی قاتل — فقط در پیوی ──
def killer_panel(s: GameState, p) -> str:
    mates = "، ".join(q.name for q in s.players.values()
                      if q.align is p.align and q.uid != p.uid) or "کسی نیست"
    return (f"🔪 *شب {_fa(s.day)} — جعبه‌ابزار تو*\n{DIV}\n"
            f"🤝 هم‌تیمی: {mates}\n\n"
            "🔪 *قتل* — یک نفر را امشب بردار.\n"
            "🚫 *امشب نمی‌کشم* — بی‌جسد، بی‌رد. گاهی بهترین حرکت.\n"
            "🖐️ *اثر انگشت جعلی* — مدرک فردا به کسِ دیگری اشاره می‌کند.\n"
            "🧾 *سرنخ جعلی* — متنی که صبح کنار سرنخ‌های واقعی خوانده می‌شود.\n"
            "😈 *تهدید* — یک نفر پیام بی‌امضا می‌گیرد.\n"
            "🤝 *دعوت به همکاری* — فقط شهروندِ بی‌نقش می‌تواند بپذیرد؛ "
            "بقیه پیام را می‌بینند ولی نمی‌توانند بپیوندند.\n\n"
            "⚠️ هر کدام را بزنی، همین‌جا در پیوی انجام می‌شود.")


def killer_kb(s: GameState, p) -> Dict:
    rows = [[("🔪 قتل", "act"), ("🚫 امشب نمی‌کشم", "killer:skip")],
            [("🖐️ اثر انگشت جعلی", "killer:plant")],
            [("🧾 سرنخ جعلی", "killer:clue")],
            [("😈 تهدید", "killer:threat"),
             ("🤝 دعوت به همکاری", "killer:recruit")]]
    if not s.plate_swapped:        # جعل سند خودرو، یک بار در کل بازی
        rows.append([("🚗 جعل سند خودرو", "killer:plate")])
    rows.append([("🗂️ پرونده‌ی تیم", "archive"), ("📓 دفترچه", "notes")])
    rows.append([BACK, HOME])
    return kb(rows)


def archive_kb(s: GameState, p) -> Dict:
    """بایگانی هر نقش؛ برای پلیس یک دکمه‌ی استعلام پلاک هم دارد."""
    rows = []
    if ROLES[p.role].info == "police_files":
        rows.append([("🚗 استعلام مالک پلاک", "plate")])
    rows.append([("🎯 توانایی‌های من", "abilities"), ("📓 دفترچه", "notes")])
    rows.append([BACK, HOME])
    return kb(rows)


def recruit_kb() -> Dict:
    return kb([[("🔪 می‌پذیرم", "recruit:1"), ("🚪 رد می‌کنم", "recruit:0")]])


def help_text() -> str:
    return ("📖 *قوانین حذف سه‌مرحله‌ای*\n" + DIV +
            "\n۱) 🔦 بازجویی — با رای گروه. فاصله: ۱ شب. بازجو سؤال می‌پرسد و سرنخ مبهم می‌گیرد."
            "\n۲) 🔒 حبس موقت — دو شبِ کاملِ بعدی (بلیتز هم کوتاهش نمی‌کند). آزادی فقط با رای شهر، وقتی متهم تازه‌ای وارد بازجویی شود"
            "؛ بازجو یک‌طرفه آزاد نمی‌کند."
            "\n۳) ⛓️ حبس ابد — حذف کامل، بدون افشای نقش. تا پایان بازی معلوم نمی‌شود قاتل بود یا بی‌گناه."
            "\n\n⚖️ هیئت دو نفره: بعد از بستن گفتگو و خواندن سرنخ پایانی، بازجو پرونده را به دو داور می‌سپارد. ربات خودش دو شهروندِ تبدیل‌نشده‌ی زنده و آزاد را برمی‌دارد؛ هر دو باید «حبس» بدهند، وگرنه متهم آزاد می‌شود.")


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
            "\n⚖️ بازجو به هیئت دو نفره ارجاع می‌دهد؛ هر دو «حبس» می‌دهند → 🔒 حبس موقت (۲ شب کامل)."
            "\n⛓️ دو شب بدون آزادی با رای شهر → حبس ابد؛ *نقشش فاش نمی‌شود!*"
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


def action_panel(s: GameState, p, chosen=None) -> str:
    """متن پنل اکشن شبانه‌ی یک بازیکن."""
    ab = ROLES[p.role].ability
    if ab == "hunter":
        title, ask = "🏹 شلیک آخر", "اگر کشته شوی یا حبس ابد بگیری، چه کسی را با خودت می‌بری؟"
    elif not ab:
        return (f"{ROLES[p.role].emoji} *{p.role}*\n{DIV}\n"
                "🌙 نقش تو اکشن شبانه ندارد. بخواب و صبح بحث کن.")
    else:
        title, ask = ABILITY_TEXT.get(ab, (f"🌙 {ab}", "هدفت را انتخاب کن:"))
    done = f"\n\n✅ انتخاب فعلی: *{s.players[chosen].name}* (می‌توانی عوض کنی)" if chosen else ""
    return (f"{title} — شب {s.day}\n{DIV}\n{ask}{done}")


def action_kb(s: GameState, p, targets: List[int], chosen=None) -> Dict:
    """دکمه‌ی هر هدف با نام؛ بدون تایپ آیدی."""
    cmd = "hunter" if ROLES[p.role].ability == "hunter" else "act"
    rows = [[(("✅ " if t == chosen else "👉 ") + s.players[t].name, f"{cmd}:{t}")]
            for t in targets]
    if not rows:
        rows = [[("— هدف مجازی نیست —", "notes")]]
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
            f"\n{DIV}\n🔎 مدارک رو شده: {len(s.revealed_evidence)}/۶{who}"
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
        if s.suspect_uid:
            rows.insert(0, [("⚖️ هیئت منصفه", "jury")])
    elif ph is Phase.DISCUSSION:
        rows = [[("🗳️ رای‌گیری", "vote")]]
    elif ph is Phase.VOTE:
        rows = [[("📊 بستن رای‌گیری", "closevote")]]
    elif ph is Phase.JURY:
        rows = [[("📊 نتیجه‌ی هیئت", "closejury")]]
    elif ph is Phase.END:
        rows = [[("🏁 پایان و افشای نقش‌ها", "end")]]
    return kb(rows + [[("🔄 بروزرسانی", "dashboard"), ("📝 دفترچه", "notes")], [BACK, HOME]])


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


def manage_kb(g) -> Dict:
    """ST06: کنترل‌های میزبان برای *همین* بازی. هیچ گزینه‌ی جایگزینیِ بازی ندارد."""
    rows = [[("▶️ ادامه‌ی بازی", "resume")] if g.s.paused
            else [("⏸️ توقف بازی", "pause")]]
    rows.append([("👑 انتقال میزبانی", "host")])
    rows.append([("⏰ یادآوری به بازیکن‌ها", "remind")])
    rows.append([("🕶️ ناشناس/علنی کردن رای", "voteanon")])
    rows.append([BACK, HOME])
    return kb(rows)
