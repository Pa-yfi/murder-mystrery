# 🕵️ کارآگاه — مافیای پیشرفته + معمای قتل (تلگرام، فارسی)

نسخه ۱.۱ — موتور کامل، ۴۰ پرونده، بدون LLM، **پنل ادمین روی SQLite**.

## راه‌اندازی (PowerShell / ویندوز)
```powershell
cd "مسیر پروژه"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # بعد BOT_TOKEN و BOT_USERNAME و ADMIN_IDS را داخلش بگذار
python -m pytest -q         # باید ۳۰ تست سبز شود
python run.py               # ربات بالا می‌آید
```
لینوکس/مک: `source .venv/bin/activate` و `cp .env.example .env`.

## اگر ربات جواب نمی‌دهد (چک‌لیست)
1. **در گروه ساکت است؟** BotFather → Bot Settings → **Group Privacy → Turn OFF**.
2. **دو نسخه هم‌زمان اجرا شده؟** خطای `Conflict: terminated by other getUpdates`. همه‌ی پایتون‌ها را ببند، یکی را اجرا کن.
3. **توکن درست است؟** در مرورگر: `https://api.telegram.org/bot<TOKEN>/getMe` باید `"ok":true` بدهد.
4. **BOT_USERNAME** باید دقیقاً یوزرنیم ربات باشد، وگرنه لینک‌های دعوت خراب‌اند.

## ساختار
```
run.py → karagah/telegram_app.py → karagah/bot.py (۳۳ اندپوینت)
                                        ├── engine.py  (قواعد + ماشین حالت)
                                        ├── roles.py / cases.py / dialogue.py / models.py
                                        ├── ui.py      (کیبورد، ایموجی، انیمیشن)
                                        └── db.py      (SQLite — پنل ادمین)
karagah/config.py ← .env
tests/test_all.py ← ۳۰ تست
```

## جریان بازی
`/start` → منوی اصلی → «🎮 شروع بازی» (پنل میزبان) → دعوت دوستان/گروه
→ ۴ تا ۸ نفر → «🎬 شروع» → «🔐 نقش من» (پیوی)
→ 🌙 شب → ☀️ صبح → 💬 گفتگو → 🗳️ رای
→ 🔦 بازجویی (سرنخ/پرسش/حکم) → 🔒 حبس موقت → ⛓️ حبس ابد (بدون افشای نقش)
→ ⚖️ هیئت منصفه → 🏁 پایان (نقش‌ها فاش می‌شود).

## پنل ادمین (SQL)
فقط آیدی‌های `ADMIN_IDS`: `/admin` ، `/admin_games` ، `/admin_users [id]` ، `/admin_stats` ، `/admin_ban <id>`.
همه‌ی داده‌ها از جدول‌های `users/games/players/events` در `karagah.db` خوانده می‌شوند.

## امنیت
توکن فقط در `.env` (داخل `.gitignore`). اگر لو رفت، در BotFather `/revoke` بزن.

## نسخه ۲.۰
۳۰ قابلیت جدید — فهرست کامل در PLAN.md. دستورهای تازه: /blitz /dashboard /will /note /lab /interp /expose /sos /top /season /league /missions /achv /rematch /newtable /spectate /voteanon /rolecard /tutorial
صدای فاز: فایل‌های ogg را در assets/voice بگذار (night.ogg, morning.ogg, ...).
