"""لایه‌ی اندپوینت ربات — مستقل از شبکه، پس کاملاً تست‌پذیر.
هر هندلر یک dict برمی‌گرداند: {ok, text, keyboard?, anim?, private?}
اتصال به python-telegram-bot فقط با map کردن این هندلرها انجام می‌شود.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

from . import ui, db, cards, menus
from .strings import t
from .config import ADMIN_IDS
from .engine import Game, RuleError
from .models import Custody, Phase
from .roles import ROLES

import time as _time
import threading

log = logging.getLogger("karagah.bot")
GAMES: Dict[int, Game] = {}
LAST_ROSTER: Dict[int, list] = {}   # ایده ۲۴: دور دوباره
_LOCKS: Dict[int, threading.RLock] = {}          # ایده ۱: قفل هر چت (ضد ریس)
_LAST_CALL: Dict[tuple, float] = {}              # ایده ۹: نرخ‌محدودساز
_LAST_CB: Dict[tuple, float] = {}                # ایده ۲: حذف callback تکراری
RATE_WINDOW = 0.6                                # ثانیه بین دو فرمانِ یک کاربر
RATE_LIMIT_ENABLED = False                       # فقط آداپتور تلگرام روشنش می‌کند
REQUIRE_READY = False                            # بهبود ۲ — همان الگو: فقط در محیط واقعی
DEDUP_WINDOW = 1.5                               # ثانیه: تپ تکراری روی یک دکمه


def _lock(chat: int) -> threading.RLock:
    return _LOCKS.setdefault(chat, threading.RLock())


def _sanitize(text: str) -> str:
    """ایده ۸: خنثی‌سازی نویسه‌های Markdown برای جلوگیری از تزریق/خرابی رندر."""
    if not text:
        return ""
    for ch in ("*", "_", "`", "[", "]", "(", ")", "~", ">", "#", "|", "{", "}"):
        text = text.replace(ch, "")
    return text[:120].strip()


def is_dup_callback(chat: int, uid: int, cb: str) -> bool:
    """ایده ۲: اگر همان کاربر همان دکمه را در پنجره‌ی کوتاه دوباره زد → نادیده."""
    key = (chat, uid, cb)
    now = _time.time()
    last = _LAST_CB.get(key, 0)
    _LAST_CB[key] = now
    return (now - last) < DEDUP_WINDOW


def restore_games() -> int:
    """بعد از ری‌استارت، بازی‌های ناتمام را از SQLite برمی‌گرداند."""
    loaded = db.load_snapshots()
    GAMES.update(loaded)
    if loaded:
        log.info("♻️ %d بازی از اسنپ‌شات بازیابی شد: %s", len(loaded), list(loaded))
    return len(loaded)


def _name(name: str, uid: int) -> str:
    n = _sanitize(name)
    return n if n else f"کارآگاه {uid}"


def board_of(g):
    """تابلوی زنده‌ی همین فاز: لابی یا رای‌گیری. None یعنی این فاز تابلو ندارد."""
    if g.s.phase is Phase.LOBBY:
        return ui.lobby_screen(g.s), ui.lobby_kb(g.s.chat_id)
    if g.s.phase is Phase.VOTE:
        return ui.vote_board(g.s), ui.vote_board_kb()
    return None


def _ok(text, keyboard=None, anim=None, private=False, edit=False, dm=None,
        board=False, refresh=False):
    """edit=True یعنی آداپتور به‌جای پیام جدید، همان پیام را ویرایش کند.
    dm = [(uid, text, keyboard)] — پیام‌های خصوصیِ جداگانه‌ای که آداپتور می‌فرستد
    (uid=0 یعنی همان گروه). این تنها راهی است که یک فرمان می‌تواند به
    چند نفر، هر کدام چیزِ متفاوت، بگوید — بدون آنکه چیزی در گروه لو برود.

    board=True  → این پیام، تابلوی زنده‌ی گروه است؛ آداپتور آیدی‌اش را نگه دارد.
    refresh=True → تابلوی گروه را همان‌جا که هست ویرایش کن (ساعت‌شنی → ✅).
                   لازم است چون «آماده‌ام» و «رای» هر دو از پیوی زده می‌شوند و
                   آن پیام اصلاً پیامِ گروه نیست که بشود ویرایشش کرد."""
    return {"ok": True, "text": text, "keyboard": keyboard, "anim": anim,
            "private": private, "edit": edit, "dm": list(dm or []),
            "board": board, "refresh": refresh}


def _broadcast(g, text, keyboard=None, only_voters=False, only=None):
    """همان پیام برای چند بازیکن، هر کدام در پیویِ خودش."""
    out = []
    for p in g.s.alive_players():
        if only is not None and p.uid not in only:
            continue
        if only_voters and not p.can_vote:
            continue
        out.append((p.uid, text, keyboard))
    return out


def _night_prompts(g):
    """آغاز شب: پنل اکشن هر نقش مستقیم به پیویِ خودش می‌رود.

    تا وقتی بازیکن باید در گروه دنبال دکمه بگردد، هم شب کِش می‌آید و هم
    زدنِ دکمه خودش نشان می‌دهد چه کسی نقشِ اکشن‌دار دارد.
    """
    out = []
    for p in g.s.alive_players():
        if not p.can_speak or p.custody is Custody.INTERROGATION:
            continue
        ab = ROLES[p.role].ability if p.role else ""
        if p.align.value == "قاتل‌ها" and ab == "kill":
            out.append((p.uid, ui.killer_panel(g.s, p), ui.killer_kb(g.s, p)))
        elif ab and ab != "hunter":
            out.append((p.uid, ui.action_panel(g.s, p, g.chosen_target(p.uid)),
                        ui.action_kb(g.s, p, g.legal_targets(p.uid),
                                     g.chosen_target(p.uid))))
    return out


def _err(msg):
    return {"ok": False, "text": f"⛔ {msg}", "keyboard": ui.back_only(),
            "edit": False, "dm": []}


def _g(chat: int) -> Game:
    if chat not in GAMES:
        raise RuleError("بازی فعالی وجود ندارد. با «🎮 شروع بازی» یک لابی بساز.")
    return GAMES[chat]


def _player(chat: int, uid: int):
    """بازیکن را برمی‌گرداند یا خطای دوستانه — دیگر KeyError خام نداریم."""
    g = _g(chat)
    if uid not in g.s.players:
        raise RuleError("تو هنوز وارد این بازی نشده‌ای. اول «➕ ورود» را بزن.")
    return g, g.s.players[uid]


# فرمان‌هایی که به بازی وابسته نیستند و در پیوی همان‌جا اجرا می‌شوند
# «menu»/«back» عمداً اینجا نیستند: §۱۳ ST04 — اگر جهانی باشند، در پیوی
# chat_id خودِ کاربر برگردانده می‌شود، بازی پیدا نمی‌شود و منوی پیش از بازی
# وسطِ یک بازیِ زنده ظاهر می‌شود.
GLOBAL_CMDS = {"start", "help", "roles", "tutorial", "share",
               "balance",
               "sharelink", "top", "league", "season", "missions", "achv",
               "new", "blitz", "newtable", "table",
               "admin", "admin_games", "admin_users", "admin_stats", "admin_ban"}

_ACTIVE_TABLE: Dict[int, int] = {}        # uid → چتِ بازیِ انتخاب‌شده
_PENDING: Dict[int, tuple] = {}           # uid → (chat, cmd) — منتظر متنِ کاربر
TEXT_CMDS = tuple(menus.PROMPTS)          # تنها فرمان‌هایی که متن می‌خواهند


def await_text(uid: int, chat: int, cmd: str) -> None:
    _PENDING[uid] = (chat, cmd)


def take_pending(uid: int):
    """اگر منتظرِ متنیم، برش دار (یک‌بارمصرف)."""
    return _PENDING.pop(uid, None)


def games_of(uid: int) -> list:
    """چت‌های بازی‌های تمام‌نشده‌ای که این کاربر در آن‌هاست."""
    return [c for c, g in GAMES.items()
            if uid in g.s.players and g.s.phase is not Phase.END]


def route_chat(cmd: str, chat: int, uid: int, private: bool) -> int:
    """در پیوی، chat_id خودِ کاربر است و بازی گروه را پیدا نمی‌کند.
    بازیِ فعالِ کاربر را برمی‌گرداند؛ ۰ یعنی مبهم/پیدا نشد."""
    if not private or cmd in GLOBAL_CMDS:
        return chat
    if chat in GAMES and uid in GAMES[chat].s.players:
        return chat                       # پیویِ خودش واقعاً یک میز است
    pinned = _ACTIVE_TABLE.get(uid)
    if pinned in GAMES and uid in GAMES[pinned].s.players:
        return pinned
    found = games_of(uid)
    if len(found) == 1:
        return found[0]
    return 0 if found else chat           # هیچ بازی‌ای نداری → خطای عادی


def h_table(chat, uid, name, arg):
    """انتخاب میز برای فرمان‌های پیوی وقتی کاربر در چند بازی است."""
    found = games_of(uid)
    if arg:
        target = int(arg)
        if target not in found:
            raise RuleError("در این بازی عضو نیستی.")
        _ACTIVE_TABLE[uid] = target
        return _ok(f"✅ میز فعالت: `{target}`", ui.back_only(), private=True)
    if not found:
        raise RuleError("در هیچ بازی فعالی نیستی.")
    rows = [[(f"🎲 میز {c}", f"table:{c}")] for c in found]
    return _ok("🎲 *کدام میز؟* برای فرمان‌های خصوصی یکی را انتخاب کن:",
               ui.kb(rows + [[ui.BACK, ui.HOME]]), private=True)


def _ensure(chat: int, uid: int, name: str) -> Game:
    """اگر لابی نبود (یا بازی قبلی تمام شده)، بسازش تا دکمه‌ای بی‌واکنش نماند."""
    g = GAMES.get(chat)
    if g is None or g.s.phase is Phase.END:
        GAMES[chat] = Game(chat, seed=chat or 1, owner=uid)
    return GAMES[chat]


# فرمان‌هایی که نرخ‌محدود نمی‌شوند (خواندنی/بی‌ضرر)
_NO_RATE = {"status", "dashboard", "tick", "help", "roles", "menu", "back", "profile"}

# دکمه‌هایی که کسی هم که بازیکن نیست می‌تواند بزند: منو، راهنما، تماشا، و
# راه‌های ورود. هر چیز دیگری روی یک بازیِ زنده اثر می‌گذارد و باید عضو باشی.
_OPEN_CMDS = GLOBAL_CMDS | {
    "join", "ready", "status", "spectate", "dashboard", "tick", "remind",
    "commands", "group", "roleinfo", "cancel", "rolecard", "end",
}


def _is_member(chat: int, uid: int) -> bool:
    g = GAMES.get(chat)
    return g is None or uid in g.s.players


def handle(cmd: str, chat: int, uid: int = 0, name: str = "", arg: str = "") -> Dict:
    """تنها نقطه‌ی ورود. هرگز استثنا پرت نمی‌کند و هرگز بی‌پاسخ نمی‌ماند.
    ایمن در برابر: ریس (قفل هر چت)، اسپم (نرخ‌محدود)، تزریق (پاکسازی)، دستور ناشناخته."""
    db.touch_user(uid, _sanitize(name))
    if cmd not in _ROUTES:                      # ایده ۳: دستور/کالبک نامعتبر
        _gm = GAMES.get(chat)
        return _ok(t("unknown"), ui.main_menu(_gm.s if _gm else None))
    # ایده ۹: نرخ‌محدودساز
    if RATE_LIMIT_ENABLED and uid and cmd not in _NO_RATE:
        key = (uid, cmd)
        now = _time.time()
        if now - _LAST_CALL.get(key, 0) < RATE_WINDOW:
            return {"ok": False, "text": "⏳ کمی آرام‌تر! چند لحظه صبر کن.",
                    "keyboard": None, "edit": True}
        _LAST_CALL[key] = now
    # یک نگهبان برای همه: غریبه‌ای که وارد بازی نشده نباید بتواند فاز را جلو
    # ببرد، رای بدهد یا درخواست هیئت منصفه کند. قبلاً هر کدام از این‌ها
    # مستقیم به players[uid] می‌رفت و با KeyError کل فرمان را می‌ترکاند.
    # uid=۰ یعنی خودِ سیستم (تایمر خودکار و تست‌ها)، نه یک آدم.
    if uid and cmd not in _OPEN_CMDS and not _is_member(chat, uid):
        return _err("تو در این بازی نیستی. با «🙋 منم بازی می‌کنم!» وارد شو، "
                    "یا «📺 تماشاچی» را بزن.")
    with _lock(chat):                           # ایده ۱: قفل هر چت
        try:
            res = _ROUTES[cmd](chat, uid, name, arg)
            if chat in GAMES:                 # پیام‌هایی که خودِ موتور ساخته
                res.setdefault("dm", [])
                res["dm"] += [(u, txt, None) for u, txt in GAMES[chat].drain()]
            # ۰ یعنی «در گروهِ بازی». همین‌جا به chat_id واقعی تبدیلش می‌کنیم،
            # وگرنه وقتی دکمه از داخل پیوی زده شود، «گروه» همان پیوی می‌شود.
            if res.get("dm"):
                res["dm"] = [(dest or chat, txt, k) for dest, txt, k in res["dm"]]
            # تابلوی زنده: متنِ تازه را همین‌جا می‌سازیم تا آداپتور فقط ویرایش کند
            if res.get("refresh") and chat in GAMES:
                res["refresh"] = board_of(GAMES[chat])
            db.log_event(chat, uid, cmd, arg[:40])   # ایده ۷: audit log
            if chat in GAMES:
                g = GAMES[chat]
                db.save_game(g)
                if g.s.phase is Phase.END:
                    # نتیجه فقط یک بار ثبت می‌شود، ولی خودِ بازی در حافظه می‌ماند
                    # تا /end بتواند نقش‌ها، MVP و بازسازی پرونده را نشان بدهد.
                    if not g.s.finalized:
                        g.s.finalized = True
                        db.record_results(g)
                        LAST_ROSTER[chat] = [(p.uid, p.name) for p in g.s.players.values()]
                        db.drop_snapshot(chat)
                else:
                    db.save_snapshot(chat, g)
            return res
        except RuleError as e:
            return _err(str(e))
        except (ValueError, TypeError):
            return _err("ورودی نامعتبر است؛ یک عدد/آیدی درست بده.")
        except Exception:
            log.exception("handler %s failed", cmd)
            return _err(f"خطای داخلی هنگام اجرای «{cmd}». دوباره /start بزن.")


# ================= منو و شروع =================
def h_start(chat, uid, name, arg):
    """/start همیشه یا لابیِ دعوت را باز می‌کند یا منوی اصلی را نشان می‌دهد."""
    if arg.startswith("ready_"):                # بهبود ۲: تاییدِ «پیویم باز است»
        try:
            target = int(arg[6:])
        except ValueError:
            return _ok(ui.first_screen(), ui.first_kb(chat, GAMES[chat].s if chat in GAMES else None))
        if target not in GAMES:
            return _err("این لابی دیگر فعال نیست.")
        return h_ready(target, uid, name, "")
    if arg.startswith("join_"):                 # دیپ‌لینک دعوت
        try:
            target = int(arg[5:])
        except ValueError:
            return _ok(ui.first_screen(), ui.first_kb(chat, GAMES[chat].s if chat in GAMES else None))
        if target not in GAMES:
            return _err("این لابی دیگر فعال نیست. با «🎮 شروع بازی» لابی تازه بساز.")
        g = GAMES[target]
        if uid == g.owner:                      # فرستنده‌ی لینک → پنل میزبان
            return _ok(ui.owner_panel(g.s), ui.owner_kb(target))
        if uid not in g.s.players:
            try:
                g.join(uid, _name(name, uid))
            except RuleError as e:
                return _err(str(e))
        return _ok(ui.newbie_guide() + "\n\n" + ui.lobby_screen(g.s), ui.back_only())
    return _ok(ui.first_screen(), ui.first_kb(chat, GAMES[chat].s if chat in GAMES else None))


def _head(g) -> str:
    """سرصفحه‌ی مشترک §۱۳.۵: دورِ جاری و آخرین شبی که واقعاً حل شده."""
    last = g.s.last_report_night
    tail = f" · آخرین گزارش: شب {ui._fa(last)}" if last else " · هنوز گزارشی نیست"
    title = g.s.case.title if g.s.case else "کارآگاه"
    return f"🗂️ *{title}* · دور {ui._fa(g.s.day)} · {g.s.phase.value}{tail}"


def h_menu(chat, uid, name, arg):
    """منو با فاز بازی عوض می‌شود؛ وسط بازی به صفحه‌ی «شروع بازی» برنمی‌گردد."""
    g = GAMES.get(chat)
    if g and g.s.phase not in (Phase.LOBBY, Phase.END):
        me = g.s.players.get(uid)
        return _ok(_head(g) + f"\n➡️ {g.next_step()}",
                   ui.main_menu(g.s, g, me) if me else ui.main_menu(g.s))
    return _ok("🏠 *منوی اصلی*", ui.main_menu(g.s if g else None))


def h_manage(chat, uid, name, arg):
    """ST06: کنترل‌های میزبان برای همین بازی — بدون گزینه‌ی ساختِ بازی تازه."""
    g = _g(chat)
    if uid != g.owner:
        raise RuleError("فقط میزبان به مدیریت این بازی دسترسی دارد.")
    return _ok(_head(g) + "\n🛠️ *مدیریت همین بازی*", ui.manage_kb(g), private=True)


def _guard_replace(chat, uid):
    """بازی در جریان را فقط میزبانش می‌تواند دور بیندازد."""
    g = GAMES.get(chat)
    if g is None:
        return
    if g.s.phase in (Phase.LOBBY, Phase.END):
        return
    if uid != g.owner:
        raise RuleError("یک بازی در جریان است؛ فقط میزبان می‌تواند آن را لغو کند.")
    db.record_abandoned(g)      # بهبود ۸: بازیِ نیمه‌کاره در آمار رهاشدگی بماند


def h_new(chat, uid, name, arg):
    _guard_replace(chat, uid)
    GAMES[chat] = Game(chat, seed=chat or 1, owner=uid)
    if uid:
        GAMES[chat].join(uid, _name(name, uid))     # سازنده خودکار عضو می‌شود
    return _ok(ui.owner_panel(GAMES[chat].s), ui.owner_kb(chat))


def h_join(chat, uid, name, arg):
    g = _ensure(chat, uid, name)                # دکمه هرگز بی‌واکنش نماند
    g.join(uid, _name(name, uid))
    # قدم بعدی را خودِ ربات در پیوی یادآوری می‌کند تا کسی سرگردان نشود.
    dm = [(uid, "🙋 وارد لابی شدی.\n\n"
                "قدم بعد: دکمه‌ی زیر را بزن تا مطمئن شویم پیویت باز است — "
                "نقش محرمانه‌ات همین‌جا می‌آید.",
           ui.kb([[("✅ آماده‌ام", "ready")], [("🏛️ وضعیت لابی", "status")]]))]
    # ویرایش همان پیام لابی؛ پیام جدید فرستاده نمی‌شود تا چت شلوغ نشود
    return _ok(ui.lobby_screen(g.s), ui.lobby_kb(chat), edit=True, dm=dm,
               board=True)


def h_leave(chat, uid, name, arg):
    g = _g(chat)
    g.leave(uid)
    return _ok(ui.lobby_screen(g.s), ui.lobby_kb(chat), edit=True, board=True)


def h_startgame(chat, uid, name, arg):
    g = _g(chat)
    asked = "force" in (arg or "").lower()
    case = (arg or "").replace("force", "").strip()
    g.start(int(case) if case else None, force=asked or not REQUIRE_READY)
    db.log_event(chat, uid, "start", g.s.case.title if g.s.case else "")
    dm = [(p.uid, ui.role_card(p.role, p.knows),
           ui.kb([[("🎯 توانایی‌های من", "abilities")]]))
          for p in g.s.players.values()]
    dm += _night_prompts(g)      # نقش + پنل اکشن، هر دو در پیویِ خودِ بازیکن
    return _ok(ui.case_intro(g.s) + "\n\n" + ui.status_board(g.s) +
               "\n\n🔐 نقش‌ها و پنل اکشن شبانه به پیوی هر بازیکن رفت.",
               ui.kb([[("🔐 نقش من", "myrole")], [("🌅 پایان شب", "dawn")], [ui.BACK, ui.HOME]]),
               anim=ui.ANIM["night"], dm=dm)


def h_myrole(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not p.role:
        return _err("بازی هنوز شروع نشده؛ نقش‌ها پخش نشده‌اند.")
    return _ok(ui.role_card(p.role, p.knows), private=True)


# ================= شب / روز =================
def h_act(chat, uid, name, arg):
    """پنل اکشن شبانه: بدون آرگومان = فهرست هدف‌ها با نام؛ با آرگومان = ثبت."""
    g, p = _player(chat, uid)
    if not p.role:      # هنوز نقشی پخش نشده → خطای دوستانه، نه KeyError
        raise RuleError("بازی هنوز شروع نشده؛ نقش‌ها پخش نشده‌اند.")
    if arg:
        res = g.night_action(uid, int(arg))
        tgt = g.s.players[int(arg)].name
        return _ok(f"✅ ثبت شد — هدف: *{tgt}*\n{res}",
                   ui.action_kb(g.s, p, g.legal_targets(uid), chosen=int(arg)),
                   private=True)
    chosen = g.chosen_target(uid)
    if ROLES[p.role].ability == "hunter":
        targets = [t for t in g.s.players
                   if t != uid and g.s.players[t].in_game]
        chosen = p.hunter_target
    else:
        targets = g.legal_targets(uid)
    return _ok(ui.action_panel(g.s, p, chosen),
               ui.action_kb(g.s, p, targets, chosen), private=True)


def h_night(chat, uid, name, arg):
    """سازگاری با /night <id> — بدون آرگومان همان پنل دکمه‌ای را می‌دهد."""
    return h_act(chat, uid, name, arg)


def h_dawn(chat, uid, name, arg):
    g = _g(chat)
    r = g.resolve_night()
    dead = "، ".join(g.s.players[u].name for u in r["killed"]) or "هیچ‌کس"
    ev_line = f"\n🌩️ رویداد شب: {g.s.night_event}" if g.s.night_event else ""
    # بهبود ۵: ردهایی که از اکشن واقعیِ دیشب ساخته شده‌اند
    traces = ("\n\n🔬 *ردهای دیشب:*\n" + "\n".join(f"  • {t}" for t in g.s.traces)) \
        if g.s.traces else ""
    hints = g.today_hints()      # واقعی و جعلی، پهلوی هم و بی‌نشان
    hint_block = (f"\n\n🔎 *سرنخ‌های تازه‌ی روز {g.s.day}:*\n"
                  + "\n".join(f"  • {h}" for h in hints)) if hints else ""
    txt = (f"☀️ *صبح روز {g.s.day}*{ev_line}\n{ui.DIV}\n⚰️ کشته‌شده: {dead}\n\n"
           + ui.evidence_card(r["evidence"]) + hint_block + traces
           + "\n\n" + ui.status_board(g.s))
    return _ok(txt, ui.kb([[("💬 گفتگو", "discuss")], [ui.BACK, ui.HOME]]),
               anim=ui.ANIM["morning"])


def h_discuss(chat, uid, name, arg):
    g = _g(chat)
    g.open_discussion()
    return _ok("💬 *فاز گفتگو باز است.* بحث کنید، اتهام بزنید، دفاع کنید.",
               ui.kb([[("🗳️ شروع رای‌گیری", "vote")], [ui.BACK, ui.HOME]]))


def h_vote(chat, uid, name, arg):
    """رای‌گیری باز می‌شود و برگه‌ی رای به پیویِ هر رای‌دهنده می‌رود.

    رای دادن در گروه یعنی همه می‌بینند چه کسی اول رای داد و به که — و همین
    بقیه را دنباله‌رو می‌کند. برگه‌ی خصوصی این اثر را از بین می‌برد.
    """
    g = _g(chat)
    g.open_vote()
    dm = _broadcast(g, "🗳️ *برگه‌ی رای تو* — چه کسی به بازجویی برود؟",
                    ui.vote_kb(g.s), only_voters=True)
    # پیام گروه *همان تابلوی زنده* است؛ با هر رای ساعت‌شنی‌اش به ✅ می‌چرخد.
    return _ok(ui.vote_board(g.s), ui.vote_board_kb(),
               anim=ui.ANIM["vote"], dm=dm, board=True)


def h_castvote(chat, uid, name, arg):
    g = _g(chat)
    if not arg:            # /castvote بدون عدد → خودِ برگه‌ی رای، نه پیام خطا
        if g.s.phase is not Phase.VOTE:
            raise RuleError("الان رای‌گیری نیست.")
        return _ok("🗳️ *برگه‌ی رای تو* — چه کسی به بازجویی برود؟",
                   ui.vote_kb(g.s), private=True)
    target = int(arg)
    g.vote(uid, target)
    if target == 0:            # ⏭️ ممتنع: رای پس گرفته شد → ✅ دوباره ⏳ شود
        return _ok(f"⏭️ ممتنع ثبت شد؛ رایی از تو شمرده نمی‌شود "
                   f"({len(g.s.votes)} رای تا اینجا).",
                   ui.vote_kb(g.s), private=True, refresh=True)
    body = f"✅ رای تو به *{g.s.players[target].name}* ثبت شد ({len(g.s.votes)} رای)."
    dm = []
    if not g.s.vote_anon:           # حالت علنی → گروه فقط همین یک خط را می‌بیند
        dm = [(0, f"🗳️ {_name(name, uid)} به {g.s.players[target].name} رای داد.", None)]
    return _ok(body, ui.vote_kb(g.s), private=True, dm=dm, refresh=True)


def h_closevote(chat, uid, name, arg):
    g = _g(chat)
    who = g.close_vote()
    if who is None:
        if g.s.phase is Phase.VOTE:          # تساوی → دور دوم، رای‌گیری باز است
            return _ok("⚔️ *تساوی!* دور دومِ رای‌گیری — برگه‌ها دوباره فرستاده شد.",
                       ui.kb([[("📊 بستن رای‌گیری", "closevote")], [ui.BACK, ui.HOME]]),
                       dm=_broadcast(g, "⚔️ *دور دوم* — دوباره رای بده.",
                                     ui.vote_kb(g.s), only_voters=True))
        return _ok("🤷 بدون نتیجه — کسی بازداشت نشد. شب فرا می‌رسد.",
                   ui.kb([[("🌅 پایان شب", "dawn")], [ui.BACK, ui.HOME]]),
                   anim=ui.ANIM["night"], dm=_night_prompts(g))
    p = g.s.players[who]
    db.log_event(chat, who, "interrogation", "رای گروه")
    # پنل بازجو *فقط* به پیویِ خودِ بازجو می‌رود. اگر در گروه بیفتد، همه
    # می‌فهمند بازجو کیست — و قاتل اولین کاری که می‌کند کشتنِ اوست.
    dm = [(g.s.officer_uid, ui.officer_panel(g.s), ui.officer_kb(who, g.s))]
    dm += [(p.uid, "🔦 *تو در اتاق بازجویی‌ای.*\nامشب اکشن شبانه نداری. "
                   "می‌توانی «🛡️ دفاع من» را بفرستی.",
            ui.kb([[("🛡️ دفاع من", "defense")], [ui.BACK, ui.HOME]]))]
    dm += _night_prompts(g)          # بقیه شبشان را در پیوی ادامه می‌دهند
    return _ok(f"🔦 *{p.name}* به اتاق بازجویی منتقل شد.\n"
               f"بازجو امشب در خلوت سؤال می‌پرسد؛ حکم فردا صبح صادر می‌شود.\n"
               f"بقیه اکشن شبانه‌شان را در پیوی دارند — بعد «🌅 پایان شب».",
               ui.kb([[("🌅 پایان شب", "dawn")], [ui.BACK, ui.HOME]]),
               anim=ui.ANIM["interrogation"], dm=dm)


# ================= بازجویی =================
def h_hints(chat, uid, name, arg):
    g = _g(chat)
    hs = g.officer_hints(uid)
    sus = g.s.players[g.s.suspect_uid].name
    return _ok(f"🔦 *سرنخ‌های بازجویی از {sus} — شب {g.s.day}*\n{ui.DIV}\n"
               + "\n".join(f"  • {h}" for h in hs) +
               "\n\n❗ هیچ‌کدام اثبات نیست؛ هر شب سرنخ‌ها عوض می‌شوند.",
               ui.officer_kb(g.s.suspect_uid, g.s), private=True)


def h_ask(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        # دکمه‌ی قبلی آیدیِ متهم را به‌جای متنِ سؤال می‌فرستاد؛ حالا متن می‌گیریم.
        return _ask_text(chat, uid, "ask")
    # R08: جواب را ربات نمی‌سازد؛ پرسش به پیویِ متهم می‌رود و خودش می‌نویسد.
    msg = g.ask(uid, arg)
    if g.s.suspect_uid:
        await_text(g.s.suspect_uid, chat, "reply")
    return _ok(msg, ui.officer_kb(g.s.suspect_uid, g.s), private=True)


def h_verdict(chat, uid, name, arg):
    g = _g(chat)
    if arg not in ("0", "1"):
        if g.s.suspect_uid is None:
            raise RuleError("کسی در بازجویی نیست.")
        return _ok("⚖️ *حکم تو چیست؟*", menus.verdict_kb(g.s))
    msg = g.officer_verdict(uid, arg == "1")
    db.log_event(chat, g.s.suspect_uid or 0, "verdict", "حبس موقت" if arg == "1" else "آزادی")
    anim = ui.ANIM["jail"] if arg == "1" else None
    # شبِ بازجویی قبلاً گذشته؛ روز از همین‌جا ادامه می‌دهد.
    return _ok(msg + "\n\n" + ui.status_board(g.s),
               ui.kb([[("💬 گفتگو", "discuss")], [ui.BACK, ui.HOME]]), anim=anim)


def h_clear(chat, uid, name, arg):
    """R07.4: آزادی از حبس موقت با رای شهر است، نه تصمیمِ یک‌طرفه‌ی بازجو."""
    g = _g(chat)
    openr = g.open_releases()
    if not openr:
        raise RuleError("بازبینی آزادی‌ای باز نیست. این فرصت وقتی باز می‌شود "
                        "که متهمِ تازه‌ای وارد بازجویی شود.")
    if not arg:
        rows = [[(f"🕊️ آزادی {g.s.players[u].name}", f"clear:{u}:1"),
                 (f"🔒 ادامه‌ی حبس {g.s.players[u].name}", f"clear:{u}:0")]
                for u in openr]
        return _ok("🗳️ *بازبینی آزادی* — رای تو چیست؟",
                   ui.kb(rows + [[("📊 بستن بازبینی", "closerelease")],
                                 [ui.BACK, ui.HOME]]), private=True)
    pid, _, choice = arg.partition(":")
    return _ok(g.release_vote(uid, int(pid), choice == "1"),
               ui.back_only(), private=True)


def h_closerelease(chat, uid, name, arg):
    g = _g(chat)
    openr = g.open_releases()
    if not openr:
        raise RuleError("بازبینی‌ای باز نیست.")
    out = [g.close_release(u) for u in list(openr)]
    return _ok("\n".join(out) + "\n\n" + ui.status_board(g.s), ui.back_only())


def h_reply(chat, uid, name, arg):
    """پاسخِ واقعیِ متهم به پرسش بازجو (R08)."""
    g = _g(chat)
    if not arg:
        if g.s.suspect_uid != uid or not g.s.room_pending_q:
            raise RuleError("پرسشی در انتظار پاسخ تو نیست.")
        return _ask_text(chat, uid, "reply")
    return _ok(g.reply(uid, arg), ui.kb([[("📕 پایان گفتگو", "closeroom")],
                                         [ui.BACK, ui.HOME]]), private=True)


def h_closeroom(chat, uid, name, arg):
    g = _g(chat)
    msg = g.close_room(uid)
    kbd = (ui.kb([[("🔦 سرنخ پایانی", "hints")], [ui.BACK, ui.HOME]])
           if uid == g.s.officer_uid else ui.back_only())
    return _ok(msg, kbd, private=True)


# ================= هیئت منصفه =================
def h_jury(chat, uid, name, arg):
    """دکمه‌ی هیئت منصفه هیچ‌وقت «هیچ‌کاری نمی‌کند»: یا تشکیل می‌دهد، یا
    درخواست را ثبت می‌کند، یا دقیقاً می‌گوید چه چیزی کم است."""
    g = _g(chat)
    if g.s.phase is Phase.JURY:            # باز است → مستقیم برگه‌ی رای
        return _ok("⚖️ *هیئت منصفه باز است* — رای بده.", ui.jury_kb(),
                   private=True)
    # v2: هیئت را بازجو تشکیل می‌دهد («⚖️ ارجاع به هیئت دو نفره»)،
    # نه درخواستِ عمومیِ بازیکن‌ها.
    return _ok(f"⚖️ *هیئت دو نفره*\n{ui.DIV}\n{g.jury_state()}",
               ui.jury_wait_kb(g.s))


def h_juryvote(chat, uid, name, arg):
    g = _g(chat)
    g.jury_vote(uid, arg == "1")
    total = len([p for p in g.s.alive_players() if p.can_vote])
    return _ok(f"🗳️ رای تو ثبت شد ({len(g.s.jury_votes)}/{total}).",
               ui.kb([[("📊 نتیجه‌ی هیئت", "closejury")], [ui.BACK, ui.HOME]]),
               private=True)


def h_closejury(chat, uid, name, arg):
    g = _g(chat)
    return _ok(g.close_jury() + "\n\n" + ui.status_board(g.s), ui.back_only())


# ================= وضعیت / پایان / پروفایل =================
def h_status(chat, uid, name, arg):
    return _ok(ui.status_board(_g(chat).s), ui.back_only())


def h_end(chat, uid, name, arg):
    g = _g(chat)
    if g.s.phase is not Phase.END:
        return _err("بازی هنوز تمام نشده؛ تا آخر بازی معلوم نمی‌شود قاتل کیست.")
    return _ok(g.ending_report(),
               ui.kb([[("🔁 همین ترکیب، دور جدید", "rematch")], [("🎮 بازی جدید", "new")], [ui.HOME]]),
               anim=ui.ANIM["court"])


def h_profile(chat, uid, name, arg):
    g, p = _player(chat, uid)
    return _ok(f"📊 *{p.name}*\n{ui.DIV}\n⭐ XP: {p.xp}\n🪙 سکه: {p.coins}\n🎖️ رتبه: {g.rank_of(p)}",
               ui.back_only(), private=True)


def h_help(chat, uid, name, arg):
    return _ok(ui.help_text(), ui.back_only())


def h_roles(chat, uid, name, arg):
    """کاتالوگ نقش‌ها = یک دکمه برای هر نقش؛ تپ → توانایی‌های همان نقش."""
    return _ok("🎭 *کاتالوگ نقش‌ها*\n" + ui.DIV +
               "\nروی هر نقش بزن تا تیم، کار شبانه و شرط بردش را ببینی.",
               menus.roles_kb())


# ================= اشتراک‌گذاری =================
def h_share(chat, uid, name, arg):
    g = _ensure(chat, uid, name)
    return _ok(ui.share_screen(chat, len(g.s.players)), ui.share_kb(chat))


def h_sharelink(chat, uid, name, arg):
    return _ok("🔗 لینک دعوت:\n`" + ui.share_links(chat)["join"] + "`", ui.back_only())


# ================= پنل ادمین (روی SQL) =================
def _admin(uid):
    # فهرست خالی = هیچ‌کس ادمین نیست (قبلاً یعنی «همه ادمین‌اند»).
    if uid not in ADMIN_IDS:
        raise RuleError("دسترسی ادمین لازم است.")


def h_admin(chat, uid, name, arg):
    _admin(uid)
    return _ok("🛠️ *پنل ادمین* (داده‌ها از پایگاه‌داده‌ی SQL)", ui.admin_menu())


def h_admin_games(chat, uid, name, arg):
    _admin(uid)
    return _ok(ui.admin_games_sql(db.q_active_games()), ui.back_only())


def h_admin_stats(chat, uid, name, arg):
    _admin(uid)
    return _ok(ui.admin_stats_sql(db.q_stats()), ui.back_only())


def h_admin_users(chat, uid, name, arg):
    """بدون آرگومان: فهرست کاربران از SQL. با آیدی: کارت کامل + خلاصه‌ی بازی‌ها."""
    _admin(uid)
    if not arg:
        return _ok(ui.admin_users_sql(db.q_users()),
                   menus.users_kb(db.q_users(), "admin_users"))
    t = int(arg)
    u = db.q_user(t)
    if not u:
        return _err("کاربری با این آیدی در پایگاه‌داده نیست.")
    return _ok(ui.admin_user_card_sql(u, db.q_user_games(t), db.q_user_events(t)), ui.back_only())


def h_admin_ban(chat, uid, name, arg):
    _admin(uid)
    if not arg:
        return _ok("🚫 *کدام کاربر مسدود شود؟*",
                   menus.users_kb(db.q_users(), "admin_ban"))
    t = int(arg)
    db.ban(t, True)
    db.log_event(chat, t, "ban", f"by {uid}")
    return _ok(f"🚫 کاربر `{t}` مسدود شد.", ui.back_only())



# ================= ایده ۱: تایمر =================
def h_tick(chat, uid, name, arg):
    g = _g(chat)
    msg = g.tick()
    if msg is None:
        rem = g.remaining()
        res = _ok(f"{t('timer')}: {rem if rem is not None else '—'} ثانیه | فاز: {g.s.phase.value}",
                  edit=True)
        res["advanced"] = False
        return res
    # advanced=True یعنی فاز واقعاً جلو رفت — آداپتور فقط این را پخش می‌کند.
    res = _ok(msg + "\n\n" + ui.status_board(g.s), ui.back_only())
    res["advanced"] = True
    return res


def h_dashboard(chat, uid, name, arg):            # ایده ۲۶ + بهبود ۳
    g = _g(chat)
    return _ok(ui.dashboard(g.s, g.remaining(), g.pending_actors(), g.next_step()),
               ui.dashboard_kb(g.s), edit=True)


# ================= ایده‌های ۲/۵/۹ =================
def h_defense(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        return _ask_text(chat, uid, "defense")
    return _ok(g.defense(uid, arg))


def _ask_text(chat, uid, cmd):
    """دکمه زده شد ولی متن لازم است → منتظر پیام بعدیِ همین کاربر می‌مانیم."""
    await_text(uid, chat, cmd)
    return _ok(menus.prompt_text(cmd), menus.prompt_kb(), private=True)


def h_will(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not arg:
        return _ask_text(chat, uid, "will")
    g.set_will(uid, arg)
    return _ok("📜 وصیت‌نامه ثبت شد؛ اگر کشته شوی صبح خوانده می‌شود.",
               menus.commands_menu(g.s, g, p), private=True)


def h_note(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not arg:
        return _ask_text(chat, uid, "note")
    g.add_note(uid, arg)
    return _ok("📝 یادداشت خصوصی ثبت شد — فعلاً فقط خودت می‌بینی.",
               ui.kb([[("📥 سپردن یادداشت به گروه", "share_note")],
                      [("📓 دفترچه‌ی من", "notes")], [menus.BACK, menus.HOME]]),
               private=True)


def h_notes(chat, uid, name, arg):
    g, p = _player(chat, uid)
    found = "\n".join(f"  • {n}" for n in p.notes) or "  — هنوز چیزی نرسیده —"
    mine = "\n".join(f"  • {n}" for n in p.private_notes) or "  — خالی —"
    return _ok(f"🔎 *یافته‌های نقش تو:*\n{found}\n\n📝 *یادداشت‌های خودت:*\n{mine}",
               ui.back_only(), private=True)


# ================= ایده‌های ۶/۱۰/۱۱/۱۲ =================
def h_sos(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        return _ok("🚨 *رای اضطراری شهر* — علیه چه کسی؟\n"
                   "با ۸۰٪ رای، مستقیم به حبس موقت می‌رود. فقط یک بار در بازی.",
                   menus.player_kb(g.s, "sos", exclude=(uid,)))
    return _ok(g.sos(uid, int(arg)))


def h_lab(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        _need_case(g)
        return _ok("🧪 *کدام مدرک به آزمایشگاه برود؟*\nنتیجه دو شب دیگر می‌رسد.",
                   menus.evidence_kb(g.s, "lab"))
    return _ok(g.submit_lab(arg.upper()), menus.evidence_kb(g.s, "lab"))


def h_interp(chat, uid, name, arg):               # interp ← مدرک ← تفسیر
    g = _g(chat)
    _need_case(g)
    arg = (arg or "").upper()
    if not arg:
        return _ok("🧠 *تفسیر کدام مدرک؟*", menus.evidence_kb(g.s, "interp"))
    if ":" not in arg:                          # مدرک انتخاب شد → تفسیرها
        ev = next((e for e in g.s.case.evidence if e["code"] == arg), None)
        if not ev:
            raise RuleError("کد مدرک نامعتبر است.")
        return _ok(ui.evidence_card(ev) + "\n🗳️ کدام تفسیر را قبول داری؟",
                   menus.interp_kb(ev))
    code, idx = arg.split(":", 1)
    return _ok(g.vote_interp(uid, code, int(idx)), menus.evidence_kb(g.s, "interp"))


def h_expose(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        _need_case(g)
        return _ok("🔍 *اصالت کدام مدرک را بسنجم؟*\nاین کار اکشن شبانه‌ات را خرج می‌کند.",
                   menus.evidence_kb(g.s, "expose"), private=True)
    code = arg.upper()
    return _ok(f"🔍 اصالت مدرک {code}: {g.expose(uid, code)}",
               menus.evidence_kb(g.s, "expose"), private=True)


# ================= ایده‌های ۱۵/۱۶/۱۸/۱۹/۲۰/۲۵ =================
def h_top(chat, uid, name, arg):
    rows = db.q_top()
    body = "\n".join(f"  {i+1}. {r['name']} — ⭐{r['xp']} ({r['wins']}/{r['games']})"
                     for i, r in enumerate(rows)) or "  —"
    return _ok(f"🏆 *برترین‌ها*\n{ui.DIV}\n{body}", ui.back_only())


def h_league(chat, uid, name, arg):
    rows = db.q_league()
    body = "\n".join(f"  {i+1}. گروه `{r['chat_id']}` — 👥{r['n']} — ⭐{r['sx']}"
                     for i, r in enumerate(rows)) or "  —"
    return _ok(f"🌍 *لیگ گروه‌ها*\n{ui.DIV}\n{body}", ui.back_only())


def h_season(chat, uid, name, arg):
    rows = db.q_season()
    body = "\n".join(f"  {i+1}. {r['name']} — ⭐{r['xp']}" for i, r in enumerate(rows)) or "  —"
    return _ok(f"📅 *رتبه‌بندی این فصل*\n{ui.DIV}\n{body}", ui.back_only())


def h_missions(chat, uid, name, arg):
    body = "\n".join(f"  {'✅' if done else '⬜'} {title} (+{coin}🪙)"
                     for _k, title, coin, done in db.q_missions(uid))
    return _ok(f"🎯 *ماموریت‌های امروز*\n{ui.DIV}\n{body}", ui.back_only(), private=True)


def h_achv(chat, uid, name, arg):
    keys = db.q_achievements(uid)
    body = "\n".join(f"  {db.ACHIEVEMENTS[k]}" for k in keys if k in db.ACHIEVEMENTS) or "  — هنوز هیچ —"
    acc = db.q_accuracy(uid)
    acc_line = (f"\n🎯 دقت رای: {acc['hits']}/{acc['total']}" if acc and acc["total"] else "")
    return _ok(f"🏅 *دستاوردها*\n{ui.DIV}\n{body}{acc_line}", ui.back_only(), private=True)


# ================= ایده‌های ۲۱/۲۲/۲۳/۲۴/۲۷/۲۸ =================
def h_newtable(chat, uid, name, arg):             # ایده ۲۱: میز موازی در همان گروه
    for slot in range(1, 4):
        vid = chat * 100 + slot
        if vid not in GAMES:
            GAMES[vid] = Game(vid, seed=vid, owner=uid)
            GAMES[vid].join(uid, _name(name, uid))
            return _ok(f"🎲 *میز شماره {slot}* ساخته شد.\n\n" + ui.lobby_screen(GAMES[vid].s),
                       ui.lobby_kb(vid))
    return _err("هر گروه حداکثر ۳ میز هم‌زمان دارد.")


def h_spectate(chat, uid, name, arg):             # ایده ۲۲: تماشاچی بدون اسپویل
    g = _g(chat)
    tail = "\n".join(f"  • {l}" for l in g.s.log[-6:]) or "  —"
    return _ok(ui.status_board(g.s) + f"\n{ui.DIV}\n📺 آخرین رویدادها:\n{tail}",
               ui.back_only(), private=True)


def h_voteanon(chat, uid, name, arg):             # ایده ۲۳
    g = _g(chat)
    if uid != g.owner:
        raise RuleError("فقط میزبان می‌تواند حالت رای را عوض کند.")
    g.s.vote_anon = not g.s.vote_anon
    mode = "ناشناس 🕶️" if g.s.vote_anon else "علنی 📢"
    return _ok(f"🗳️ حالت رای‌گیری: {mode}")


def h_rematch(chat, uid, name, arg):              # ایده ۲۴
    roster = LAST_ROSTER.get(chat)
    if not roster:
        raise RuleError("بازی قبلی‌ای برای تکرار نیست.")
    _guard_replace(chat, uid)
    GAMES[chat] = Game(chat, seed=chat + len(roster), owner=roster[0][0])
    for u, n in roster:
        GAMES[chat].join(u, n)
    return _ok("🔁 *دور جدید با همان ترکیب!*\n\n" + ui.lobby_screen(GAMES[chat].s),
               ui.lobby_kb(chat))


def h_rolecard(chat, uid, name, arg):             # ایده ۲۷: کارت PNG
    g, p = _player(chat, uid)
    if not p.role:
        raise RuleError("بازی هنوز شروع نشده.")
    path = cards.render_role_card(p.role, p.name)
    res = _ok(ui.role_card(p.role, p.knows), private=True)
    res["photo"] = path
    return res


def h_tutorial(chat, uid, name, arg):             # ایده ۲۸
    return _ok(ui.tutorial_text(), ui.kb([[("📖 قوانین کامل", "help")], [ui.BACK, ui.HOME]]))


def h_blitz(chat, uid, name, arg):                # ایده ۳: لابی سریع
    _guard_replace(chat, uid)
    GAMES[chat] = Game(chat, seed=chat or 1, owner=uid, blitz=True)
    if uid:
        GAMES[chat].join(uid, _name(name, uid))
    return _ok("⚡ *حالت بلیتز* — همه‌ی مهلت‌ها نصف!\n\n" + ui.owner_panel(GAMES[chat].s),
               ui.owner_kb(chat))


def h_ready(chat, uid, name, arg):                # بهبود ۲
    """«آماده‌ام» خودش هم عضو می‌کند.

    قبلاً ترتیب مهم بود: اول «ورود»، بعد «آماده‌ام» — و هر کس برعکس می‌زد
    خطای «اول وارد لابی شو» می‌گرفت. حالا هر کدام را اول بزنی، کار می‌کند.
    """
    g = _g(chat)
    if uid not in g.s.players:
        g.join(uid, _name(name, uid))
    msg = g.mark_ready(uid)
    left = g.not_ready()
    if left:
        names = "، ".join(g.s.players[u].name for u in left)
        tail = f"\n⏳ مانده: {names}"
    else:
        tail = "\n🟢 همه آماده‌اند — میزبان می‌تواند شروع کند."
    # ساعت‌شنیِ کنار اسم این بازیکن در تابلوی گروه همین حالا ✅ می‌شود
    return _ok(msg + tail, ui.back_only(), private=True, refresh=True)


def h_remind(chat, uid, name, arg):               # بهبود ۷
    g = _g(chat)
    # در شب نه نام می‌بریم نه تعداد: هر دو می‌گویند چه کسی نقشِ اکشن‌دار دارد،
    # و تغییرِ عدد بین دو یادآوری، زمانِ اکشنِ آن نفر را لو می‌دهد.
    if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
        return _ok("⏰ *یادآوری* — هر کسی اکشن شبانه دارد، «🌙 اکشن شبانه» را بزند.\n"
                   f"➡️ {g.next_step()}", ui.dashboard_kb(g.s))
    left = g.pending_actors()
    if not left:
        return _ok("✅ همه کارشان را کرده‌اند.", ui.back_only())
    names = "، ".join(g.s.players[u].name for u in left)
    return _ok(f"⏰ *یادآوری* — منتظر: {names}\n➡️ {g.next_step()}",
               ui.dashboard_kb(g.s))


def h_pause(chat, uid, name, arg):                # بهبود ۷
    g = _g(chat)
    if uid != g.owner:
        raise RuleError("فقط میزبان می‌تواند بازی را متوقف کند.")
    return _ok(g.pause(), ui.kb([[("▶️ ادامه", "resume")], [ui.BACK, ui.HOME]]))


def h_resume(chat, uid, name, arg):               # بهبود ۷
    g = _g(chat)
    if uid != g.owner:
        raise RuleError("فقط میزبان می‌تواند بازی را ادامه دهد.")
    return _ok(g.resume(), ui.dashboard_kb(g.s))


def h_host(chat, uid, name, arg):                 # بهبود ۷: انتقال میزبانی
    g = _g(chat)
    owner = g.s.players.get(g.owner)
    # میزبانِ حاضر خودش واگذار می‌کند؛ اگر از بازی بیرون است، هر بازیکنی می‌تواند بگیرد.
    if uid != g.owner and owner is not None and owner.in_game:
        raise RuleError("فقط میزبان فعلی می‌تواند میزبانی را واگذار کند.")
    if not arg:
        return _ok("👑 *میزبانی به چه کسی برسد؟*", menus.player_kb(g.s, "host"))
    return _ok(g.transfer_host(int(arg)), ui.back_only())


def h_balance(chat, uid, name, arg):              # بهبود ۸
    _admin(uid)
    return _ok(ui.balance_report_sql(db.q_balance(), db.q_balance_by_seats(),
                                     db.q_abandonment()), ui.back_only())


def h_hunter(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not arg:                 # بدون آرگومان دیگر نمی‌ترکد: فهرست هدف‌ها را بده
        if not p.role or ROLES[p.role].ability != "hunter":
            raise RuleError("فقط شکارچی هدف شلیک آخر دارد.")
        return _ok("🏹 *هدف شلیک آخر*\nاگر کشته شوی یا حبس ابد بگیری، "
                   "چه کسی را با خودت می‌بری؟",
                   menus.player_kb(g.s, "hunter", exclude=(uid,)), private=True)
    return _ok(g.set_hunter(uid, int(arg)),
               menus.player_kb(g.s, "hunter", exclude=(uid,)), private=True)


# ================= جعبه‌ابزار قاتل — همه در پیوی =================
def h_killer(chat, uid, name, arg):
    """پنل شبانه‌ی تیم قاتل: کشتن، نکشتن، پاپوش، سرنخ جعلی، تهدید، دعوت."""
    g, p = _player(chat, uid)
    g._killer(uid)                                # همین‌جا دسترسی را چک می‌کند
    if not arg:
        return _ok(ui.killer_panel(g.s, p), ui.killer_kb(g.s, p), private=True)
    kind, _, rest = arg.partition(":")
    if kind == "skip":
        return _ok(g.skip_kill(uid), ui.killer_kb(g.s, p), private=True)
    if kind in ("plant", "threat", "recruit", "plate"):
        if not rest:
            title = {"plant": "🖐️ *اثر انگشت جعلی روی چه کسی؟*",
                     "threat": "😈 *چه کسی را تهدید می‌کنی؟*",
                     "recruit": "🤝 *به چه کسی پیشنهاد همکاری می‌دهی؟*",
                     "plate": "🚗 *سند خودرو به نام چه کسی بخورد؟*"}[kind]
            return _ok(title, menus.player_kb(g.s, f"killer:{kind}", exclude=(uid,)),
                       private=True)
        fn = {"plant": g.plant_print, "threat": g.threaten,
              "recruit": g.offer_recruit, "plate": g.swap_plate}[kind]
        return _ok(fn(uid, int(rest)), ui.killer_kb(g.s, p), private=True)
    if kind == "clue":
        if not rest:
            return _ask_text(chat, uid, "fakeclue")
        return _ok(g.plant_clue(uid, rest), ui.killer_kb(g.s, p), private=True)
    raise RuleError("این کار را نمی‌شناسم.")


def h_fakeclue(chat, uid, name, arg):
    """ورودی متنیِ سرنخ جعلی (از راه _PENDING)."""
    g, p = _player(chat, uid)
    if not arg:
        return _ask_text(chat, uid, "fakeclue")
    return _ok(g.plant_clue(uid, arg), ui.killer_kb(g.s, p), private=True)


def h_recruit(chat, uid, name, arg):
    """جوابِ کسی که دعوت قاتل را گرفته: پذیرفتن یا رد کردن."""
    g, p = _player(chat, uid)
    if arg not in ("0", "1"):
        return _ok("🤝 *دعوت را می‌پذیری؟*", ui.recruit_kb(), private=True)
    return _ok(g.answer_recruit(uid, arg == "1"), ui.back_only(), private=True)


# ================= یادداشتِ سپرده به گروه =================
def h_share_note(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not arg:
        return _ask_text(chat, uid, "share_note")
    return _ok(g.share_note(uid, arg),
               ui.kb([[("📓 دفترچه‌ی من", "notes")], [menus.BACK, menus.HOME]]),
               private=True)


# ================= بازجو: ارجاع به هیئت منصفه =================
def h_refer(chat, uid, name, arg):
    """R05.1: ربات خودش دو داورِ شهریِ تبدیل‌نشده را برمی‌دارد."""
    g = _g(chat)
    msg = g.refer_jury(uid)
    dm = [(u, "⚖️ *برگه‌ی رای تو*", ui.jury_kb()) for u in g.s.jury_panel]
    return _ok(msg, ui.back_only(), private=True, dm=dm)


def h_archive(chat, uid, name, arg):
    """بایگانی اختصاصی نقش — همان داده‌ای که کارت نقش وعده داده، در پیوی."""
    g, p = _player(chat, uid)
    if not p.role:
        raise RuleError("بازی هنوز شروع نشده؛ نقش‌ها پخش نشده‌اند.")
    title, lines = g.archive(uid)
    return _ok(f"{title}\n{ui.DIV}\n" + "\n".join(lines),
               ui.archive_kb(g.s, p), private=True)


def h_plate(chat, uid, name, arg):
    """استعلام مالک پلاک — فقط از پرونده‌ی پلیس."""
    g, p = _player(chat, uid)
    return _ok(g.plate_lookup(uid), ui.archive_kb(g.s, p), private=True)


def h_surrender(chat, uid, name, arg):
    """تسلیم — چون برگشت‌ناپذیر است، دو مرحله‌ای است."""
    g, p = _player(chat, uid)
    if arg != "yes":
        if g.s.phase in (Phase.LOBBY, Phase.END):
            raise RuleError("بازی در جریان نیست؛ «🚪 خروج از لابی» را بزن.")
        if not p.in_game:
            raise RuleError("همین حالا هم از بازی بیرونی.")
        return _ok("🏳️ *مطمئنی می‌خواهی تسلیم شوی؟*\n" + ui.DIV +
                   "\nاز بازی کنار می‌کشی و دیگر نمی‌توانی برگردی."
                   "\nنقشت تا پایان بازی فاش نمی‌شود.",
                   ui.kb([[("🏳️ بله، تسلیم می‌شوم", "surrender:yes")],
                          [("↩️ نه، ادامه می‌دهم", "abilities")]]), private=True)
    msg = g.surrender(uid)
    db.log_event(chat, uid, "surrender", "")
    return _ok(msg, ui.back_only(), private=True, refresh=True)


def _need_case(g):
    if not g.s.case:
        raise RuleError("بازی هنوز شروع نشده؛ مدرکی وجود ندارد.")


# ================= همه‌ی فرمان‌ها = دکمه =================
def h_commands(chat, uid, name, arg):
    """تابلوی دکمه‌ها — وسط بازی فقط دسته‌های مربوط به همین دور."""
    g = GAMES.get(chat)
    st = g.s if g else None
    me = g.s.players.get(uid) if g else None
    head = menus.commands_screen()
    if g and g.s.phase not in (Phase.LOBBY, Phase.END):
        head = (f"🎛️ *دکمه‌های همین دور* — روز {ui._fa(g.s.day)} | "
                f"فاز: {g.s.phase.value}\n" + "─" * 18 +
                f"\n➡️ {g.next_step()}")
    return _ok(head, menus.commands_menu(st, g, me))


def h_group(chat, uid, name, arg):
    g = GAMES.get(chat)
    st = g.s if g else None
    me = g.s.players.get(uid) if g else None
    keys = [k for k, _t, _i in menus.visible_groups(st, g, me)]
    if arg not in keys:
        return _ok(menus.commands_screen(), menus.commands_menu(st, g, me))
    return _ok(f"*{menus.group_title(arg)}*", menus.group_kb(arg, st, g, me))


def h_roleinfo(chat, uid, name, arg):
    try:
        role = menus.ROLE_NAMES[int(arg)]
    except (ValueError, IndexError):
        return _ok("🎭 *کاتالوگ نقش‌ها* — یکی را بزن:", menus.roles_kb())
    return _ok(menus.role_detail(role), menus.role_detail_kb())


def h_abilities(chat, uid, name, arg):
    g, p = _player(chat, uid)
    return _ok(menus.abilities_text(g, p), menus.abilities_kb(g, p), private=True)


def h_cancel(chat, uid, name, arg):
    """لغو هم باید به همان منوی بازی برگردد، نه به فهرستِ پیش از بازی."""
    take_pending(uid)
    g = GAMES.get(chat)
    me = g.s.players.get(uid) if g else None
    return _ok("✖️ باشه، بی‌خیال.", menus.commands_menu(g.s if g else None, g, me))


_ROUTES = {
    "start": h_start, "menu": h_menu, "back": h_menu, "new": h_new,
    "join": h_join, "leave": h_leave, "startgame": h_startgame, "myrole": h_myrole,
    "night": h_night, "dawn": h_dawn, "discuss": h_discuss, "vote": h_vote,
    "castvote": h_castvote, "closevote": h_closevote, "hints": h_hints, "ask": h_ask,
    "verdict": h_verdict, "clear": h_clear, "jury": h_jury, "juryvote": h_juryvote,
    "closejury": h_closejury, "status": h_status, "end": h_end, "profile": h_profile,
    "help": h_help, "roles": h_roles, "share": h_share, "sharelink": h_sharelink,
    "admin": h_admin, "admin_games": h_admin_games, "admin_users": h_admin_users,
    "admin_stats": h_admin_stats, "admin_ban": h_admin_ban,
    # نسخه ۲: ۳۰ ایده
    "tick": h_tick, "dashboard": h_dashboard, "defense": h_defense,
    "will": h_will, "note": h_note, "notes": h_notes, "sos": h_sos,
    "lab": h_lab, "interp": h_interp, "expose": h_expose,
    "top": h_top, "league": h_league, "season": h_season,
    "missions": h_missions, "achv": h_achv, "newtable": h_newtable,
    "spectate": h_spectate, "voteanon": h_voteanon, "rematch": h_rematch,
    "rolecard": h_rolecard, "tutorial": h_tutorial, "blitz": h_blitz,
    "hunter": h_hunter, "table": h_table, "act": h_act,
    "ready": h_ready, "remind": h_remind, "pause": h_pause,
    "commands": h_commands, "group": h_group, "roleinfo": h_roleinfo,
    "abilities": h_abilities, "cancel": h_cancel,
    "resume": h_resume, "host": h_host, "balance": h_balance,
    # جعبه‌ابزار قاتل، یادداشت سپرده، و مسیر دومِ بازجو
    "killer": h_killer, "fakeclue": h_fakeclue, "recruit": h_recruit,
    "share_note": h_share_note, "refer": h_refer, "surrender": h_surrender,
    "archive": h_archive, "plate": h_plate, "manage": h_manage,
    "reply": h_reply, "closeroom": h_closeroom, "closerelease": h_closerelease,
}

# دستورهایی که به BotFather معرفی می‌شوند (زیرمجموعه‌ی امن برای منوی دستورها)
COMMANDS = ["start", "menu", "new", "join", "startgame", "myrole", "act",
            "dashboard", "status", "table", "notes", "help", "roles",
            "ready", "remind", "pause", "resume", "host",
            "share", "admin"]
ENDPOINTS = sorted(_ROUTES)
