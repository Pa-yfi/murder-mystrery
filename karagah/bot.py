"""لایه‌ی اندپوینت ربات — مستقل از شبکه، پس کاملاً تست‌پذیر.
هر هندلر یک dict برمی‌گرداند: {ok, text, keyboard?, anim?, private?}
اتصال به python-telegram-bot فقط با map کردن این هندلرها انجام می‌شود.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

from . import ui, db, cards
from .strings import t
from .config import ADMIN_IDS
from .engine import Game, RuleError
from .models import Custody, Phase

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


def _ok(text, keyboard=None, anim=None, private=False, edit=False):
    """edit=True یعنی آداپتور به‌جای پیام جدید، همان پیام را ویرایش کند."""
    return {"ok": True, "text": text, "keyboard": keyboard, "anim": anim,
            "private": private, "edit": edit}


def _err(msg):
    return {"ok": False, "text": f"⛔ {msg}", "keyboard": ui.back_only(), "edit": False}


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


def _ensure(chat: int, uid: int, name: str) -> Game:
    """اگر لابی نبود (یا بازی قبلی تمام شده)، بسازش تا دکمه‌ای بی‌واکنش نماند."""
    g = GAMES.get(chat)
    if g is None or g.s.phase is Phase.END:
        GAMES[chat] = Game(chat, seed=chat or 1, owner=uid)
    return GAMES[chat]


# فرمان‌هایی که نرخ‌محدود نمی‌شوند (خواندنی/بی‌ضرر)
_NO_RATE = {"status", "dashboard", "tick", "help", "roles", "menu", "back", "profile"}


def handle(cmd: str, chat: int, uid: int = 0, name: str = "", arg: str = "") -> Dict:
    """تنها نقطه‌ی ورود. هرگز استثنا پرت نمی‌کند و هرگز بی‌پاسخ نمی‌ماند.
    ایمن در برابر: ریس (قفل هر چت)، اسپم (نرخ‌محدود)، تزریق (پاکسازی)، دستور ناشناخته."""
    db.touch_user(uid, _sanitize(name))
    if cmd not in _ROUTES:                      # ایده ۳: دستور/کالبک نامعتبر
        return _ok(t("unknown"), ui.main_menu())
    # ایده ۹: نرخ‌محدودساز
    if RATE_LIMIT_ENABLED and uid and cmd not in _NO_RATE:
        key = (uid, cmd)
        now = _time.time()
        if now - _LAST_CALL.get(key, 0) < RATE_WINDOW:
            return {"ok": False, "text": "⏳ کمی آرام‌تر! چند لحظه صبر کن.",
                    "keyboard": None, "edit": True}
        _LAST_CALL[key] = now
    with _lock(chat):                           # ایده ۱: قفل هر چت
        try:
            res = _ROUTES[cmd](chat, uid, name, arg)
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
    if arg.startswith("join_"):                 # دیپ‌لینک دعوت
        try:
            target = int(arg[5:])
        except ValueError:
            return _ok(ui.first_screen(), ui.first_kb(chat))
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
    return _ok(ui.first_screen(), ui.first_kb(chat))


def h_menu(chat, uid, name, arg):
    return _ok("🏠 *منوی اصلی*", ui.main_menu())


def _guard_replace(chat, uid):
    """بازی در جریان را فقط میزبانش می‌تواند دور بیندازد."""
    g = GAMES.get(chat)
    if g is None:
        return
    if g.s.phase in (Phase.LOBBY, Phase.END):
        return
    if uid != g.owner:
        raise RuleError("یک بازی در جریان است؛ فقط میزبان می‌تواند آن را لغو کند.")


def h_new(chat, uid, name, arg):
    _guard_replace(chat, uid)
    GAMES[chat] = Game(chat, seed=chat or 1, owner=uid)
    if uid:
        GAMES[chat].join(uid, _name(name, uid))     # سازنده خودکار عضو می‌شود
    return _ok(ui.owner_panel(GAMES[chat].s), ui.owner_kb(chat))


def h_join(chat, uid, name, arg):
    g = _ensure(chat, uid, name)                # دکمه هرگز بی‌واکنش نماند
    g.join(uid, _name(name, uid))
    # ویرایش همان پیام لابی؛ پیام جدید فرستاده نمی‌شود تا چت شلوغ نشود
    return _ok(ui.lobby_screen(g.s), ui.lobby_kb(chat), edit=True)


def h_leave(chat, uid, name, arg):
    g = _g(chat)
    g.leave(uid)
    return _ok(ui.lobby_screen(g.s), ui.lobby_kb(chat), edit=True)


def h_startgame(chat, uid, name, arg):
    g = _g(chat)
    g.start(int(arg) if arg else None)
    db.log_event(chat, uid, "start", g.s.case.title if g.s.case else "")
    return _ok(ui.case_intro(g.s) + "\n\n" + ui.status_board(g.s) +
               "\n\n🔐 هر کس /myrole را بزند نقش محرمانه‌اش به پیوی می‌رود.",
               ui.kb([[("🔐 نقش من", "myrole")], [("🌙 پایان شب", "dawn")], [ui.BACK, ui.HOME]]),
               anim=ui.ANIM["night"])


def h_myrole(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not p.role:
        return _err("بازی هنوز شروع نشده؛ نقش‌ها پخش نشده‌اند.")
    return _ok(ui.role_card(p.role, p.knows), private=True)


# ================= شب / روز =================
def h_night(chat, uid, name, arg):
    g, _ = _player(chat, uid)
    res = g.night_action(uid, int(arg))
    return _ok(f"🌙 اکشن شبانه ثبت شد: {res}", private=True)


def h_dawn(chat, uid, name, arg):
    g = _g(chat)
    r = g.resolve_night()
    dead = "، ".join(g.s.players[u].name for u in r["killed"]) or "هیچ‌کس"
    ev_line = f"\n🌩️ رویداد شب: {g.s.night_event}" if g.s.night_event else ""
    txt = (f"☀️ *صبح روز {g.s.day}*{ev_line}\n{ui.DIV}\n⚰️ کشته‌شده: {dead}\n\n"
           + ui.evidence_card(r["evidence"]) + "\n\n" + ui.status_board(g.s))
    return _ok(txt, ui.kb([[("💬 گفتگو", "discuss")], [ui.BACK, ui.HOME]]), anim=ui.ANIM["morning"])


def h_discuss(chat, uid, name, arg):
    g = _g(chat)
    g.open_discussion()
    return _ok("💬 *فاز گفتگو باز است.* بحث کنید، اتهام بزنید، دفاع کنید.",
               ui.kb([[("🗳️ شروع رای‌گیری", "vote")], [ui.BACK, ui.HOME]]))


def h_vote(chat, uid, name, arg):
    g = _g(chat)
    g.open_vote()
    return _ok("🗳️ *رای‌گیری آغاز شد* — چه کسی به بازجویی برود؟", ui.vote_kb(g.s), anim=ui.ANIM["vote"])


def h_castvote(chat, uid, name, arg):
    g = _g(chat)
    g.vote(uid, int(arg))
    who = "" if g.s.vote_anon else f" — {_name(name, uid)} به {g.s.players[int(arg)].name}"
    return _ok(f"✅ رای ثبت شد ({len(g.s.votes)} رای){who}.",
               ui.kb([[("📊 بستن رای‌گیری", "closevote")]]))


def h_closevote(chat, uid, name, arg):
    g = _g(chat)
    who = g.close_vote()
    if who is None:
        return _ok("🤷 تساوی/بدون رای — کسی بازداشت نشد. شب فرا می‌رسد.",
                   ui.kb([[("🌙 پایان شب", "dawn")]]), anim=ui.ANIM["night"])
    p = g.s.players[who]
    db.log_event(chat, who, "interrogation", "رای گروه")
    return _ok(f"🔦 *{p.name}* به اتاق بازجویی منتقل شد (فاصله: ۱ شب).\n"
               f"بازجو می‌تواند سؤال بپرسد و حکم بدهد.",
               ui.officer_kb(who), anim=ui.ANIM["interrogation"])


# ================= بازجویی =================
def h_hints(chat, uid, name, arg):
    g = _g(chat)
    hs = g.officer_hints(uid)
    return _ok("🔦 *سرنخ‌های بازجویی (مبهم و غیرقطعی):*\n" + "\n".join(f"  • {h}" for h in hs), private=True)


def h_ask(chat, uid, name, arg):
    g = _g(chat)
    d = f"\n🛡️ دفاع متهم: «{g.s.defense_text}»" if g.s.defense_text else ""
    return _ok(f"🗣️ متهم: «{g.ask(uid, arg or 'کجا بودی؟')}»{d}",
               ui.kb([[("💬 پرسش بعدی", f"ask:{g.s.suspect_uid or 0}")],
                      [("🔒 حبس موقت", f"ver:{g.s.suspect_uid or 0}:1"),
                       ("🔓 آزادی", f"ver:{g.s.suspect_uid or 0}:0")]]))


def h_verdict(chat, uid, name, arg):
    g = _g(chat)
    msg = g.officer_verdict(uid, arg == "1")
    db.log_event(chat, g.s.suspect_uid or 0, "verdict", "حبس موقت" if arg == "1" else "آزادی")
    anim = ui.ANIM["jail"] if arg == "1" else None
    return _ok(msg + "\n\n" + ui.status_board(g.s),
               ui.kb([[("🌙 پایان شب", "dawn")], [ui.BACK, ui.HOME]]), anim=anim)


def h_clear(chat, uid, name, arg):
    g = _g(chat)
    return _ok(g.clear_previous(uid, int(arg)) + "\n\n" + ui.status_board(g.s), ui.back_only())


# ================= هیئت منصفه =================
def h_jury(chat, uid, name, arg):
    g = _g(chat)
    formed = g.request_jury(uid)
    if not formed:
        return _ok("📝 درخواست هیئت منصفه ثبت شد؛ یک نفر دیگر هم لازم است.")
    return _ok("⚖️ *هیئت منصفه تشکیل شد!* رای بدهید.", ui.jury_kb())


def h_juryvote(chat, uid, name, arg):
    g = _g(chat)
    g.jury_vote(uid, arg == "1")
    return _ok(f"🗳️ رای هیئت منصفه ثبت شد ({len(g.s.jury_votes)}).",
               ui.kb([[("📊 نتیجه‌ی هیئت", "closejury")]]))


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
    rows = "\n".join(f"  {n} → {r} ({c})" for n, r, c in g.reveal())
    mvp = g.s.players[g.s.mvp].name if g.s.mvp else "—"
    return _ok(f"🏁 *پایان — برنده: {g.s.winner}*\n{ui.DIV}\n{rows}\n{ui.DIV}\n"
               f"⭐ MVP: {mvp}\n\n" + g.reconstruction(),
               ui.kb([[("🔁 همین ترکیب، دور جدید", "rematch")], [("🎮 بازی جدید", "new")], [ui.HOME]]),
               anim=ui.ANIM["court"])


def h_profile(chat, uid, name, arg):
    g, p = _player(chat, uid)
    return _ok(f"📊 *{p.name}*\n{ui.DIV}\n⭐ XP: {p.xp}\n🪙 سکه: {p.coins}\n🎖️ رتبه: {g.rank_of(p)}",
               ui.back_only(), private=True)


def h_help(chat, uid, name, arg):
    return _ok(ui.help_text(), ui.back_only())


def h_roles(chat, uid, name, arg):
    from .roles import ROLES
    lines = [f"{r.emoji} *{r.name}* ({r.align.value}) — {r.desc}" for r in ROLES.values()]
    return _ok("🎭 *کاتالوگ نقش‌ها*\n" + ui.DIV + "\n" + "\n".join(lines), ui.back_only())


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
        return _ok(ui.admin_users_sql(db.q_users()), ui.back_only())
    t = int(arg)
    u = db.q_user(t)
    if not u:
        return _err("کاربری با این آیدی در پایگاه‌داده نیست.")
    return _ok(ui.admin_user_card_sql(u, db.q_user_games(t), db.q_user_events(t)), ui.back_only())


def h_admin_ban(chat, uid, name, arg):
    _admin(uid)
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
        return _ok(f"{t('timer')}: {rem if rem is not None else '—'} ثانیه | فاز: {g.s.phase.value}",
                   edit=True)
    return _ok(msg + "\n\n" + ui.status_board(g.s), ui.back_only())


def h_dashboard(chat, uid, name, arg):            # ایده ۲۶: داشبورد تک‌پیامی
    g = _g(chat)
    rem = g.remaining()
    timer = f"\n{t('timer')}: {rem} ثانیه" if rem is not None else ""
    return _ok(ui.status_board(g.s) + timer, ui.kb([[("🔄 بروزرسانی", "dashboard")]]), edit=True)


# ================= ایده‌های ۲/۵/۹ =================
def h_defense(chat, uid, name, arg):
    g = _g(chat)
    return _ok(g.defense(uid, arg or "بی‌گناهم."))


def h_will(chat, uid, name, arg):
    g, p = _player(chat, uid)
    g.set_will(uid, arg or "")
    return _ok("📜 وصیت‌نامه ثبت شد؛ اگر کشته شوی صبح خوانده می‌شود.", private=True)


def h_note(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not arg:
        raise RuleError("متن یادداشت را بعد از دستور بنویس.")
    g.add_note(uid, arg)
    return _ok("📝 یادداشت خصوصی ثبت شد.", private=True)


def h_notes(chat, uid, name, arg):
    g, p = _player(chat, uid)
    body = "\n".join(f"  • {n}" for n in p.private_notes) or "  — خالی —"
    return _ok(f"📝 *دفترچه کارآگاهی تو:*\n{body}", ui.back_only(), private=True)


# ================= ایده‌های ۶/۱۰/۱۱/۱۲ =================
def h_sos(chat, uid, name, arg):
    g = _g(chat)
    return _ok(g.sos(uid, int(arg)))


def h_lab(chat, uid, name, arg):
    g = _g(chat)
    return _ok(g.submit_lab((arg or "").upper()))


def h_interp(chat, uid, name, arg):               # interp E2:1
    g = _g(chat)
    code, idx = (arg or "").upper().split(":", 1)
    return _ok(g.vote_interp(uid, code, int(idx)))


def h_expose(chat, uid, name, arg):
    g = _g(chat)
    return _ok(f"🔍 اصالت مدرک {(arg or '').upper()}: {g.expose(uid, (arg or '').upper())}",
               private=True)


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


def h_hunter(chat, uid, name, arg):
    g = _g(chat)
    return _ok(g.set_hunter(uid, int(arg)), private=True)


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
    "hunter": h_hunter,
}

# دستورهایی که به BotFather معرفی می‌شوند (زیرمجموعه‌ی امن برای منوی دستورها)
COMMANDS = ["start", "menu", "new", "join", "startgame", "myrole", "status",
            "help", "roles", "share", "admin"]
ENDPOINTS = sorted(_ROUTES)
