"""آداپتور تلگرام — توکن از متغیر محیطی BOT_TOKEN خوانده می‌شود (هرگز داخل کد ننویس).

اجرا:
    pip install python-telegram-bot python-dotenv
    export BOT_TOKEN="123456:AA..."     # یا در فایل .env
    python -m karagah.telegram_app       # یا: python run.py
"""
from __future__ import annotations
import asyncio
import logging
import os
import os.path as osp

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.error import InvalidToken
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          MessageHandler, ContextTypes, filters)

try:
    from . import theme
    from . import bot as botmod
    from .bot import GAMES
    from .bot import (handle, ENDPOINTS, COMMANDS, restore_games,
                      is_dup_callback, route_chat, take_pending)
    from .config import BOT_TOKEN as CONFIG_BOT_TOKEN
except ImportError:
    import theme
    import bot as botmod
    from bot import GAMES
    from bot import (handle, ENDPOINTS, COMMANDS, restore_games,
                     is_dup_callback, route_chat, take_pending)
    from config import BOT_TOKEN as CONFIG_BOT_TOKEN

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx هر getUpdates را با آدرسِ کامل (همراه توکن) در INFO لاگ می‌کند → روی سرور هر چند ثانیه یک خط و توکن در لاگ
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("karagah.telegram")

TOKEN = CONFIG_BOT_TOKEN

# نگاشت callback_data کوتاه → اندپوینت
CB_MAP = {"vote": "castvote", "ver": "verdict", "jury": "juryvote", "ask": "ask"}


def parse_callback(data: str):
    """callback_data → (اندپوینت، آرگومان). بازیکن‌های شبیه‌سازی (playtest) هم
    از همین تابع رد می‌شوند تا دکمه‌ها دقیقاً مثل تلگرام واقعی تفسیر شوند."""
    if ":" in data:                       # اکشن پارامتری: vote:5 ، ver:5:1 ، ask:5
        head, rest = data.split(":", 1)
        # ver:<متهم>:<حکم> کامل به h_verdict می‌رسد تا دکمه‌ی کهنه روی متهمِ تازه اجرا نشود
        return CB_MAP.get(head, head), rest
    return data, ""                       # دکمه‌ی ساده = نام اندپوینت (بدون نگاشت)


ICONS_OK = True           # اگر تلگرام آیکونِ ایموجیِ سفارشی را رد کرد (صاحبِ ربات Premium ندارد) → خاموش


def _kb(k, icons: bool = True):
    if not k:
        return None
    rows = []
    for row in k["inline_keyboard"]:
        r = []
        for b in row:
            if "url" in b:
                r.append(InlineKeyboardButton(b["text"], url=b["url"]))
            else:
                # style: danger 🔴 / success 🟢 / primary 🔵 (Bot API ≥ 9.4؛ کلاینت قدیمی نادیده می‌گیرد)
                # icon_custom_emoji_id: ایموجیِ متحرکِ سفارشی کنارِ متن (theme.BUTTON_EMOJI در .env)
                icon = theme.button_icon(b["callback_data"]) if icons and ICONS_OK else None
                kw = {"icon_custom_emoji_id": icon} if icon else {}
                r.append(InlineKeyboardButton(b["text"], callback_data=b["callback_data"],
                                              style=b.get("style"), **kw))
        rows.append(r)
    return InlineKeyboardMarkup(rows)


async def _send_photo_or_voice(update: Update, res: dict):
    """ایده ۲۷/۲۹: اگر پاسخ photo دارد یا انیمیشن فاز فایل صوتی دارد، بفرست."""
    bot = update.get_bot()
    chat = update.effective_user.id if res.get("private") else update.effective_chat.id
    # صدای فازِ یک اعلام عمومی همراه خودِ اعلام به گروه می‌رود
    voice_chat = res.get("_target") if res.get("announce") and res.get("_target") \
        else update.effective_chat.id
    if res.get("photo") and osp.exists(res["photo"]):
        try:
            with open(res["photo"], "rb") as f:
                await bot.send_photo(chat, f, caption="🔐 کارت نقش تو")
        except Exception as e:
            log.warning("photo failed: %s", e)
    anim = res.get("anim")
    if anim:
        try:
            from .config import VOICE_DIR
            from .ui import ANIM, VOICE
        except ImportError:
            from config import VOICE_DIR
            from ui import ANIM, VOICE
        for key, frames in ANIM.items():
            if frames is anim and key in VOICE:
                vp = osp.join(VOICE_DIR, VOICE[key])
                if osp.exists(vp):
                    try:
                        with open(vp, "rb") as f:
                            await bot.send_voice(voice_chat, f)
                    except Exception as e:
                        log.warning("voice failed: %s", e)
                break


TG_LIMIT = 4096            # سقفِ طولِ یک پیامِ تلگرام


def chunks(text: str, limit: int = TG_LIMIT - 96) -> list:
    """پیامِ بلند (پرونده‌ی روز ۱۵ با ۳۰ سرنخ…) را سرِ خط‌ها تکه می‌کند؛ تلگرام بیش از ۴۰۹۶ نمی‌پذیرد."""
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:                 # یک خطِ غول‌آسا
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


async def _send(bot, dest: int, text: str, keyboard=None, effect: str = None):
    """Markdown، و اگر خراب شد متن ساده. پیامِ بلند تکه‌تکه؛ کیبورد زیرِ تکه‌ی آخر.
    effect: افکتِ پیام (🎉 🔥 …) فقط در پیوی (dest > 0)؛ اگر تلگرام رد کرد، بی‌افکت.
    خروجی: آخرین پیامِ فرستاده‌شده (truthy) یا None."""
    global ICONS_OK
    parts = chunks(text)
    last = None
    ok = True
    eff = theme.effect_id(effect) if dest and dest > 0 else None
    for i, part in enumerate(parts):
        final = i == len(parts) - 1
        sent = None
        attempts = [("Markdown", True, eff), ("Markdown", False, None), (None, False, None)]
        for pm, icons, e in attempts:
            try:
                kw = {"reply_markup": _kb(keyboard, icons) if final else None}
                if pm:
                    kw["parse_mode"] = pm
                if e and final:
                    kw["message_effect_id"] = e
                sent = await bot.send_message(dest, part, **kw) or True
                break
            except Exception as ex:
                err = str(ex).lower()
                if "emoji" in err and icons:
                    ICONS_OK = False                 # آیکونِ سفارشی مجاز نیست؛ دیگر امتحان نکن
                log.warning("send to %s failed (%s): %s", dest, pm or "plain", ex)
        ok = ok and bool(sent)
        last = sent or last
    return last if ok else None


async def _flush_outbox(bot, res: dict) -> None:
    """پیام‌هایی که هندلر برای دیگران گذاشته (پرسش بازجو به متهم، نتیجه‌ی شب، کارت نقش)."""
    for m in res.get("outbox") or []:
        await _send(bot, m["chat"], m["text"], m.get("keyboard"), m.get("effect"))


ANIM_DELAY = 0.6        # ثانیه بین فریم‌های ایموجیِ متحرک


async def _animate(bot, chat: int, frames) -> None:
    """ایموجیِ متحرک: یک پیام کوتاه که چند فریم عوض می‌شود (🌆→🌃→🌌→🔪) و بعد پاک می‌شود."""
    if not frames or not chat:
        return
    try:
        msg = await bot.send_message(chat, frames[0])
        for f in frames[1:]:
            await asyncio.sleep(ANIM_DELAY)
            await msg.edit_text(f)
        await asyncio.sleep(ANIM_DELAY)
        await msg.delete()
    except Exception as e:                        # انیمیشن تزئین است؛ هرگز جلوی پیام اصلی را نگیرد
        log.debug("animation skipped: %s", e)


async def _reply(update: Update, res: dict):
    if res.get("anim") and not res.get("private"):
        dest = res.get("_target") if res.get("announce") and res.get("_target") else update.effective_chat.id
        await _animate(update.get_bot(), dest, res["anim"])
    sent = await _deliver(update, res)
    await _flush_outbox(update.get_bot(), res)
    # نسخه ۹: کارتِ زنده (لابی/ساعتِ فاز) همین حالا به‌روز شود، نه ۵ ثانیه بعد
    game_chat = res.get("refresh") or res.get("_target") or update.effective_chat.id
    if game_chat in GAMES and game_chat < 0:
        if res.get("clock") and sent is not None and hasattr(sent, "message_id"):
            view = botmod.clock_view(game_chat)
            if view:
                old = CLOCKS.pop(game_chat, None)
                if old:
                    try:
                        await update.get_bot().delete_message(game_chat, old["mid"])
                    except Exception:
                        pass
                CLOCKS[game_chat] = {"key": view["key"], "mid": sent.message_id, "text": res["text"]}
        await _update_clock(update.get_bot(), game_chat)


async def _deliver(update: Update, res: dict):
    """هرگز بی‌صدا نماند: اگر Markdown یا پیوی خطا داد، ساده و در همان چت بفرست.
    اگر res["edit"] و پیام callback داریم → همان پیام ویرایش می‌شود (چت شلوغ نمی‌شود).
    اعلامِ عمومیِ بازی (announce) که از پیوی زده شده، به گروهِ بازی می‌رود نه همان پیوی."""
    kb = _kb(res.get("keyboard"))
    bot = update.get_bot()
    q = update.callback_query
    target = res.get("_target")
    here = update.effective_chat.id
    if res.get("announce") and target and target != here and not res.get("private"):
        m = await _send(bot, target, res["text"], res.get("keyboard"))
        if m:
            await _send(bot, here, "📣 در گروهِ بازی اعلام شد.")
            return m
    if res.get("edit") and q and q.message and not res.get("private") and len(res["text"]) <= TG_LIMIT:
        for pm in ("Markdown", None):
            try:
                await q.edit_message_text(res["text"], parse_mode=pm, reply_markup=kb)
                return q.message
            except Exception as e:
                if "not modified" in str(e).lower():
                    return q.message            # همان محتوا؛ ویرایش لازم نیست
        # اگر ویرایش نشد (پیام پاک شده و ...) → به ارسال عادی برگرد
    private = bool(res.get("private"))
    dest = update.effective_user.id if private else update.effective_chat.id
    m = await _send(bot, dest, res["text"], res.get("keyboard"), res.get("effect") if private else None)
    if m:
        return m
    # پیوی شکست خورد. متن محرمانه (نقش/سرنخ) هرگز نباید در گروه بیفتد —
    # فقط یک تذکر بی‌محتوا می‌فرستیم.
    if private:
        try:
            await bot.send_message(
                update.effective_chat.id,
                "⚠️ نتوانستم پیام خصوصی‌ات را بفرستم. اول در پیوی ربات را /start کن، بعد دوباره امتحان کن.")
        except Exception as e:
            log.warning("private notice failed: %s", e)
        return
    log.error("delivery failed for chat %s", update.effective_chat.id)


AMBIGUOUS = ("🎲 در چند بازی هستی. اول با /table میز فعالت را انتخاب کن.")


def _dispatch(update: Update, cmd: str, arg: str) -> dict:
    """در پیوی، chat_id بازی گروه نیست — اول میز کاربر را پیدا کن."""
    chat = update.effective_chat.id
    uid = update.effective_user.id
    private = update.effective_chat.type == "private"
    target = route_chat(cmd, chat, uid, private)
    if not target:
        return {"ok": False, "text": AMBIGUOUS, "keyboard": None,
                "private": True, "edit": False}
    res = handle(cmd, target, uid, update.effective_user.first_name or "", arg)
    res["_target"] = target            # اعلامِ عمومی به همین چتِ بازی می‌رود
    return res


def make_cmd(name: str):
    async def h(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        arg = " ".join(ctx.args) if ctx.args else ""
        res = _dispatch(update, name, arg)
        await _reply(update, res)
        await _send_photo_or_voice(update, res)
    return h


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()          # همیشه چرخ لودینگ تلگرام را قطع کن
    except Exception:
        pass
    data = q.data or "menu"
    if is_dup_callback(q.message.chat_id if q.message else 0, q.from_user.id, data):
        return                                 # ایده ۲: تپ تکراری نادیده
    cmd, arg = parse_callback(data)
    res = _dispatch(update, cmd, arg)
    await _reply(update, res)
    await _send_photo_or_voice(update, res)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """متن ساده فقط وقتی معنا دارد که ربات منتظر آن باشد (یادداشت/وصیت/پرسش/دفاع).
    وگرنه کاربر را به تابلوی دکمه‌ها می‌بریم تا مجبور به تایپ دستور نشود."""
    uid = update.effective_user.id
    private = update.effective_chat.type == "private"
    text = (update.effective_message.text or "").strip()
    if not private and not botmod._PENDING.get(uid):
        return        # گفتگوی عادیِ گروه مالِ بازیکن‌هاست؛ ربات وسط بحث منو نمی‌فرستد
    pending = take_pending(uid)
    if pending and text:
        chat, cmd = pending
        res = handle(cmd, chat, uid, update.effective_user.first_name or "", text)
        res["_target"] = chat
    else:
        res = _dispatch(update, "menu", "")     # وسط بازی: پنلِ بازیِ جاری؛ بیرون از بازی: منو
    await _reply(update, res)


async def on_migrate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """گروه → سوپرگروه: تلگرام آیدیِ چت را عوض می‌کند؛ بازی و ساعتش به آیدیِ تازه می‌روند."""
    msg = update.effective_message
    old, new = update.effective_chat.id, getattr(msg, "migrate_to_chat_id", None)
    if not new:
        old, new = getattr(msg, "migrate_from_chat_id", None), update.effective_chat.id
    if old and new and botmod.migrate_chat(old, new):
        CLOCKS.pop(old, None)
        await _send(ctx.bot, new, "🔁 گروه به سوپرگروه ارتقا یافت؛ بازی همین‌جا ادامه دارد.")


async def on_unknown(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """هر متن/دستور ناشناخته → منوی اصلی، نه سکوت."""
    res = _dispatch(update, "menu", "")
    await _reply(update, res)


async def _post_init(app):
    n = restore_games()
    if n:
        log.info("♻️ %d بازی ناتمام بازیابی شد.", n)
    await app.bot.set_my_commands([BotCommand(c, c) for c in COMMANDS])
    log.info("دستورها ثبت شد: %s", ", ".join(COMMANDS))


CLOCK_INTERVAL = 5          # ثانیه — پیامِ ساعت هر چند ثانیه خودش را ویرایش می‌کند
CLOCKS: dict = {}           # chat → {"key", "mid", "text"}: پیامِ ساعتِ فازِ فعلی


async def _update_clock(bot, chat: int) -> None:
    """نسخه ۷: یک پیامِ ساعت برای هر فاز (شبِ ۲، صبحِ روز ۲، …) که مدام ویرایش می‌شود.
    فاز عوض شد → پیامِ قبلی «✔️ تمام شد» می‌گیرد و پیامِ ساعتِ تازه پایینِ چت می‌آید."""
    view = botmod.clock_view(chat)
    cur = CLOCKS.get(chat)
    if cur and (view is None or cur["key"] != view["key"]):
        try:
            await bot.edit_message_text(chat_id=chat, message_id=cur["mid"],
                                        text=cur["text"] + "\n✔️ این مرحله تمام شد.", parse_mode="Markdown")
        except Exception as e:
            log.debug("clock close %s: %s", chat, e)
        CLOCKS.pop(chat, None)
        cur = None
    if view is None:
        return
    global ICONS_OK
    kb = _kb(view["keyboard"], ICONS_OK)
    if cur is None:
        try:
            msg = await bot.send_message(chat, view["text"], parse_mode="Markdown", reply_markup=kb)
            CLOCKS[chat] = {"key": view["key"], "mid": msg.message_id, "text": view["text"]}
        except Exception as e:
            if "emoji" in str(e).lower():
                ICONS_OK = False
            log.warning("clock send %s: %s", chat, e)
        return
    if cur["text"] == view["text"]:
        return
    try:
        await bot.edit_message_text(chat_id=chat, message_id=cur["mid"], text=view["text"],
                                    parse_mode="Markdown", reply_markup=kb)
        cur["text"] = view["text"]
    except Exception as e:
        err = str(e).lower()
        if "not modified" in err:
            cur["text"] = view["text"]
        elif "not found" in err or "can't be edited" in err:
            CLOCKS.pop(chat, None)            # پیام پاک شده → تیکِ بعدی ساعتِ تازه می‌فرستد
        else:
            log.debug("clock edit %s: %s", chat, e)   # محدودیت نرخ و … — تیکِ بعد دوباره


async def _timer_job(ctx: ContextTypes.DEFAULT_TYPE):
    """ایده ۱: هر ۱۵ ثانیه، فازهای منقضی‌شده را خودکار جلو می‌برد.

    از handle() رد می‌شود، نه مستقیم از موتور — وگرنه قفل چت، ذخیره‌ی
    اسنپ‌شات و ثبت نتیجه‌ی پایان بازی دور زده می‌شود.
    """
    for chat in list(GAMES):
        try:
            res = handle("tick", chat)
            if res.get("advanced"):
                # همان پیام کاملِ دکمه‌ها: کشته‌ها و مدرک صبح، کیبورد رای، هیئت منصفه…
                await _send(ctx.bot, chat, res["text"], res.get("keyboard"))
            await _flush_outbox(ctx.bot, res)
            await _update_clock(ctx.bot, chat)
        except Exception as e:
            log.warning("timer tick %s: %s", chat, e)
    try:
        botmod.gc()                                   # میزهای تمام‌شده/رهاشده و ورودی‌های کهنه
        for chat in [c for c in CLOCKS if c not in GAMES]:
            CLOCKS.pop(chat, None)
    except Exception as e:
        log.warning("gc: %s", e)


def build_app(token: str):
    """برنامه‌ی تلگرام با همه‌ی هندلرها — بدون اتصال به شبکه (تستِ دود از همین استفاده می‌کند)."""
    app = ApplicationBuilder().token(token).post_init(_post_init).concurrent_updates(True).build()
    for name in ENDPOINTS:
        app.add_handler(CommandHandler(name, make_cmd(name)))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.MIGRATE, on_migrate))
    app.add_handler(MessageHandler(filters.COMMAND, on_unknown))   # /هرچیزِ نامعلوم → منو
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main():
    botmod.RATE_LIMIT_ENABLED = True          # ایده ۹: ضد اسپم فقط در محیط واقعی
    botmod.REQUIRE_READY = True               # بهبود ۲: بدون پیویِ باز، بازی شروع نشود
    if not TOKEN or TOKEN == "your_telegram_bot_token_here":
        raise SystemExit("⛔ BOT_TOKEN تنظیم نشده یا هنوز مقدار نمونه را دارد. در فایل .env توکن واقعی BotFather را جایگزین کن.")
    app = build_app(TOKEN)
    if app.job_queue:
        app.job_queue.run_repeating(_timer_job, interval=CLOCK_INTERVAL, first=CLOCK_INTERVAL)
    else:
        # بی‌صدا رد نشو: بدون job-queue، مهلت فازها هرگز خودکار جلو نمی‌رود.
        log.warning("⚠️ JobQueue نصب نیست → تایمر خودکار فازها کار نمی‌کند. "
                    'نصب کن: pip install "python-telegram-bot[job-queue]"')
    log.info("🕵️ ربات کارآگاه بالا آمد.")
    try:
        app.run_polling(drop_pending_updates=True)
    except InvalidToken:
        raise SystemExit("⛔ توکن تلگرام نامعتبر است. در فایل .env مقدار BOT_TOKEN را با توکن واقعی جایگزین کن.")


if __name__ == "__main__":
    main()
