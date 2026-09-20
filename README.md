# 🕵️ کارآگاه — مافیای پیشرفته + معمای قتل (تلگرام، فارسی)

نسخه ۳.۱ — ۱۸ نقش، ۴۰ پرونده، ۴ تا ۱۰ بازیکن، بدون LLM، **پنل ادمین روی SQLite**.

## راه‌اندازی (PowerShell / ویندوز)
```powershell
cd "مسیر پروژه"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # بعد BOT_TOKEN و BOT_USERNAME و ADMIN_IDS را داخلش بگذار
python -m pytest -q tests --ignore=tests/quality   # ۱۸۴ تست سبز
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
run.py → karagah/telegram_app.py → karagah/bot.py (۶۴ اندپوینت)
                                        ├── engine.py  (قواعد + ماشین حالت)
                                        ├── roles.py / cases.py / dialogue.py / models.py
                                        ├── ui.py      (کیبورد، ایموجی، انیمیشن)
                                        └── db.py      (SQLite — پنل ادمین)
karagah/config.py ← .env
tests/        ← ۱۸۴ تست سبز
tests/quality/ ← قراردادهای کیفی، عمداً قرمز (دفترچه‌ی نقص)
```

## جریان بازی
`/start` → منوی اصلی → «🎮 شروع بازی» (پنل میزبان) → دعوت دوستان/گروه
→ ۴ تا ۱۰ نفر → «✅ آماده‌ام» (همه) → «🎬 شروع» → «🔐 نقش من» (پیوی)
→ 🌙 شب → ☀️ صبح → 💬 گفتگو → 🗳️ رای
→ 🔦 متهم یک **شب** در اتاق بازجویی (بقیه همان شب اکشن شبانه دارند)
→ ☀️ صبح: سرنخ/پرسش/حکم — یا ⚖️ هیئت منصفه (۶۰٪ = تبرئه)
→ 🔒 حبس موقت → ⛓️ حبس ابد (بدون افشای نقش)
→ 🏁 پایان (نقش‌ها فاش می‌شود).

**در پیوی:** فرمان‌های خصوصی (`/act` ، `/myrole` ، `/notes` …) خودشان بازیِ
گروهت را پیدا می‌کنند. اگر هم‌زمان در چند بازی باشی، با `/table` میز فعال را انتخاب کن.

## پنل ادمین (SQL)
فقط آیدی‌های `ADMIN_IDS`: `/admin` ، `/admin_games` ، `/admin_users [id]` ، `/admin_stats` ، `/admin_ban <id>` ، `/balance`.

⚠️ فهرست خالی `ADMIN_IDS` یعنی **هیچ‌کس** ادمین نیست (قبلاً یعنی «همه»).

جدول‌های `karagah.db`: `users` ، `games` ، `players` ، `events` ، `outcomes` (تعادل) ،
`snapshots` (بازیابی بعد از ری‌استارت) ، `season_xp` ، `achievements` ، `missions` ، `accuracy`.

## امنیت
توکن فقط در `.env` (داخل `.gitignore`). اگر لو رفت، در BotFather `/revoke` بزن.

## نسخه ۲.۰
۳۰ قابلیت جدید — فهرست کامل در PLAN.md. دستورهای تازه: /blitz /dashboard /will /note /lab /interp /expose /sos /top /season /league /missions /achv /rematch /newtable /spectate /voteanon /rolecard /tutorial
صدای فاز: فایل‌های ogg را در assets/voice بگذار (night.ogg, morning.ogg, ...).

## نسخه ۳.۱ — ۱۰ بهبود کیفیت
- **✅ آمادگی پیش از شروع:** لابی دکمه‌ی «آماده‌ام» دارد که دیپ‌لینک پیوی است؛
  تا ربات نتواند به کسی پیام خصوصی بدهد بازی شروع نمی‌شود (`/startgame force` برای رد شدن).
- **🎯 پنل اکشن خصوصی:** `/act` هدف‌ها را با **نام** نشان می‌دهد — دیگر آیدی عددی تایپ نمی‌کنی.
- **📋 داشبورد راهنما:** فاز، مهلت، وضعیت همه، «منتظر چه کسی هستیم» و «قدم بعدی» در یک پیام.
- **🔬 مدرکِ واقعی:** ملاقات‌های شبانه رد می‌گذارند؛ هم‌مکان‌ها خصوصی همدیگر را می‌بینند
  و می‌توانند شهادت بدهند — یا دروغ بگویند.
- **🏁 پایان قابل‌فهم:** چرا این تیم برد، سرنوشت هر نقش، بی‌گناهِ حبس‌ابدی، رای‌های درست، MVP.
- **⏸️ بازیکن غایب:** `/remind` ، `/pause` ، `/resume` ، `/host` (انتقال میزبانی)، شمارش شب‌های بی‌حرکت.
- **📊 تعادل بازی:** `/balance` (ادمین) — نرخ برد هر نقش، طول بازی به تفکیک تعداد بازیکن، نرخ رهاشدگی.
- **🧪 تست بازیِ کامل:** بازیِ سرتاسری، بازیِ تایمرمحور، هیئت منصفه، ری‌استارت، و شکست پیام خصوصی.

دستورهای تازه: `/act` `/ready` `/remind` `/pause` `/resume` `/host` `/table` `/balance`

## دو سوئیت تست
- `tests/` — رفتارِ موجود. باید همیشه سبز باشد.
- `tests/quality/` — قراردادِ رفتارِ مطلوب (از `improvement.md`). **عمداً قرمز است**؛ هر شکست یک نقصِ شناخته‌شده است، نه رگرسیون.
  فهرست نقص‌های باز در پایان `PLAN.md`.

```powershell
python -m pytest -q tests --ignore=tests/quality   # باید سبز باشد
python -m pytest -q tests/quality                  # دفترچه‌ی نقص
```
