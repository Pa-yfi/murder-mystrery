# 🧪 گزارش QA — همه‌ی گونه‌های آزمونِ بازی

حالت: **سریع (--quick)** · نتیجه: **✅ همه سبز**

اجرای دوباره: `python -m playtest.qa` (سریع، چند دقیقه) یا `python -m playtest.qa --full`.
محیط: پایتون 3.11.15 روی linux؛ CI همین را روی ۳.۱۰ تا ۳.۱۳ اجرا می‌کند (`.github/workflows/ci.yml`).

| گونه‌ی آزمون | نتیجه | زمان (ث) | خلاصه |
|---|---|---|---|
| Unit & Integration | ✅ | 11.73 | pytest: 413 passed, 1 skipped, 3 warnings in 11.16s |
| Smoke & Sanity | ✅ | 0.53 | modules: 17 |
| Functional & Gameplay | ✅ | 4.35 | games: 21 |
| Regression (chaos players) | ✅ | 3.59 | chaos_games_finished: 21/21 |
| Performance | ✅ | 24.15 | handle_calls: 3485 |
| Soak / Longevity | ✅ | 90.76 | games_per_run: 300 |
| Network & Multiplayer | ✅ | 5.19 | concurrent_vote_calls: 6000 |
| Platform & Compatibility | ✅ | 3.46 | messages_checked: 2217 |
| Automated gameplay & balance | ✅ | 51.46 | games: 1260 |
| Localization & I18n | ✅ | 1.4 | messages_scanned: 1729 |
| Playtest & UX | ✅ | 2.64 | presses_total: 2694 |

## ✅ Unit & Integration
_pytest: منطقِ خالص (واحد) + ربات/موتور/SQLite/آداپتور با هم (یکپارچگی)_

- **pytest:** 413 passed, 1 skipped, 3 warnings in 11.16s
- **tests_passed:** 413
- **test_files:** 22

## ✅ Smoke & Sanity
_دود: import، ساختِ برنامه، همه‌ی اندپوینت‌ها، یک بازی، ذخیره/بازیابی_

- **modules:** 17
- **telegram_handlers:** 77
- **endpoints_checked:** 73
- **smoke_game:** killers در 2 روز
- **snapshot_bytes:** 9890

## ✅ Functional & Gameplay
_agentهایی که Markdownها را خوانده‌اند و فقط با دکمه بازی می‌کنند؛ داورِ مستقل_

- **games:** 21
- **button_presses:** 4287
- **referee_checks_passed:** 1817
- **referee_findings:** 0

## ✅ Regression (chaos players)
_بازیکن‌های شلوغ‌کار: هر دکمه در هر لحظه، /start وسط بازی، پرشِ ساعت_

- **chaos_games_finished:** 21/21

## ✅ Performance
_کارایی: تأخیرِ هر تپ، دورِ تایمر با ۲۰۰ میز، اسنپ‌شات_

- **handle_calls:** 3485
- **handle_ms_p50/p95/p99:** 0.44 / 1.39 / 1.83
- **slowest_cmds_p99_ms:** startgame 2.2, act 1.8, pass 1.7, closevote 1.6, closejury 1.2
- **handle_ms_on_disk_p50/p95/p99:** 4.77 / 11.22 / 18.32
- **db_file_kb:** 264.0
- **timer_round_200_tables_s:** 0.032
- **timer_round_200_tables_on_disk_s:** 0.009
- **snapshot_kb:** 18.8
- **snapshot_save_ms:** 0.23
- **board_render_ms:** 0.2
- **board_chars:** 2800

## ✅ Soak / Longevity
_ماندگاری: هزاران بازی در یک پروسه، با و بدون پاک‌سازی_

- **games_per_run:** 300
- **without_gc: MB / GAMES / _LAST_CALL / snapshots:** 12.8 / 300 / 7241 / 300
- **with_gc: MB / GAMES / _LAST_CALL / snapshots:** 2.0 / 50 / 5 / 50
- **peak_growth_second_vs_first_half (with gc):** 0%
- **leak_per_game_without_gc_KB:** 43.8
- **memory_curve_MB (with gc):** 1.1 → 0.4 → 1.6 → 0.8 → 2.0 → 1.2 → 0.5 → 1.7 → 0.8 → 2.0

**مشاهده‌ها:**
- بدون پاک‌سازی (قبل از نسخه ۸) هر بازیِ تمام‌شده، قفلش، ورودی‌های نرخ‌محدودساز و اسنپ‌شاتش برای همیشه می‌ماند — حافظه خطی رشد می‌کرد و بعد از ری‌استارت همه‌ی بازی‌های قدیمی دوباره بار می‌شدند.

## ✅ Network & Multiplayer
_هم‌روندی، خرابیِ تلگرام/شبکه، callbackِ تکراری، فازینگِ ضدتقلب، میزبانِ غایب_

- **concurrent_vote_calls:** 6000
- **concurrent_dawn_calls:** 480
- **long_message_chunks:** 7
- **failure_scenarios_survived:** 8
- **host_gone_game:** قاتل‌ها 🔪 در 2 روز
- **fuzz_calls:** 4200

## ✅ Platform & Compatibility
_سقف‌های Bot API، Markdown، ری‌استارت در هر فاز، ارتقای گروه، توقف/ادامه_

- **messages_checked:** 2217
- **longest_message_chars:** 1504
- **messages_over_4096 (sent in chunks):** 0
- **distinct_callback_data / max_bytes:** 175 / 16
- **markdown_unbalanced:** 0
- **longest_board_chars (12 long chaos games):** 3500
- **hostile_text_messages:** 20
- **restart_ok_in_phases:** اتاق بازجویی، رای‌گیری، شب، صبح، هیئت منصفه، گفتگو

## ✅ Automated gameplay & balance
_هزاران بازیِ ربات‌ها؛ نرخ برد با فاصله‌ی اطمینان ۹۵٪_

- **games:** 1260
- **internal_errors:** 0
- **unfinished (day cap):** 0
**balance_table:**

| سناریو | نفر | شهر (۹۵٪ CI) | قاتل‌ها | جانی | سپر بلا | میانگین روز |
|---|---|---|---|---|---|---|
| classic | 4 | 85% (74–92) | 15% | 0% | 0% | 3.9 |
| classic | 5 | 95% (86–98) | 5% | 0% | 0% | 4.1 |
| classic | 6 | 87% (76–93) | 0% | 0% | 13% | 4.1 |
| classic | 7 | 20% (12–32) | 80% | 0% | 0% | 4.6 |
| classic | 8 | 15% (8–26) | 38% | 0% | 47% | 5.4 |
| classic | 9 | 25% (16–37) | 35% | 0% | 40% | 6.0 |
| classic | 10 | 3% (1–11) | 97% | 0% | 0% | 4.5 |
| court | 4 | 95% (86–98) | 5% | 0% | 0% | 3.9 |
| court | 5 | 88% (78–94) | 12% | 0% | 0% | 4.0 |
| court | 6 | 95% (86–98) | 2% | 0% | 3% | 4.1 |
| court | 7 | 25% (16–37) | 75% | 0% | 0% | 4.9 |
| court | 8 | 32% (21–44) | 68% | 0% | 0% | 5.9 |
| court | 9 | 15% (8–26) | 85% | 0% | 0% | 5.5 |
| court | 10 | 10% (5–20) | 52% | 0% | 38% | 5.6 |
| chaos | 4 | 48% (36–61) | 52% | 0% | 0% | 3.2 |
| chaos | 5 | 68% (56–79) | 32% | 0% | 0% | 4.2 |
| chaos | 6 | 40% (29–53) | 13% | 45% | 0% | 4.0 |
| chaos | 7 | 12% (6–22) | 88% | 0% | 0% | 4.0 |
| chaos | 8 | 22% (13–34) | 55% | 20% | 0% | 4.3 |
| chaos | 9 | 23% (14–35) | 58% | 18% | 0% | 5.1 |
| chaos | 10 | 23% (14–35) | 53% | 22% | 0% | 5.3 |
- **cells_flagged:** 7

**مشاهده‌ها:**
- نامتعادل (با ربات‌های ساده): classic 5 نفره: شهر 95% (CI 86–98)
- نامتعادل (با ربات‌های ساده): classic 6 نفره: شهر 87% (CI 76–93)
- نامتعادل (با ربات‌های ساده): classic 10 نفره: شهر 3% (CI 1–11)
- نامتعادل (با ربات‌های ساده): classic 10 نفره: killers 97%
- نامتعادل (با ربات‌های ساده): court 4 نفره: شهر 95% (CI 86–98)
- نامتعادل (با ربات‌های ساده): court 5 نفره: شهر 88% (CI 78–94)
- نامتعادل (با ربات‌های ساده): court 6 نفره: شهر 95% (CI 86–98)

## ✅ Localization & I18n
_رقم فارسی، نشتِ انگلیسی/پایتون، mojibake، برچسب دکمه، نام‌های عجیب، UTF-8_

- **messages_scanned:** 1729
- **latin_digits_in_player_text:** 0
- **english_words:** —
- **python_artifacts:** 0
- **mojibake_messages:** 0
- **messages_starting_ltr:** 0
- **button_labels_over_34_chars:** 0
- **weird_names_joined:** 8/8
- **repo_files_utf8:** بله

## ✅ Playtest & UX
_تله‌متری: خطای هر دکمه، تپ برای هر تصمیم، شلوغیِ گروه، طولِ فازها، آموزش_

- **presses_total:** 2694
- **error_rate_overall:** 1.0%
- **error_heatmap (top):** startgame 50% of 24 | scenario 25% of 32 | closevote 8% of 75 | will 0% of 44 | vote 0% of 313 | ver 0% of 21
- **top_error_messages:** ⛔ این بازیکن‌ها هنوز پیوی ربات را باز نکرده‌اند: آرش، بهار، کاوه، دنیا ×12 | ⛔ فقط میزبان می‌تواند سناریو را عوض کند. ×8 | ⛔ ⏳ هنوز همه رای نداده‌اند (ممتنع هم رای است)؛ ۸۰ ثانیه تا پایان مهلت. ×2 | ⛔ ⏳ هنوز همه رای نداده‌اند (ممتنع هم رای است)؛ ۸۶ ثانیه تا پایان مهلت. ×2
- **bot_group_msgs_per_player_day:** 1.88
- **group_chat_msgs_total:** 195
- **taps_per_night_decision:** 1.0
- **game_length_days p50/p90/max:** 5 / 8 / 9
- **nights_needing_grace:** 0
- **games:** 12
- **tutorial_chars:** 805

**مشاهده‌ها:**
- دکمه‌ی «startgame» در 50% از 24 تپ خطا داد — یا جایی نشان داده می‌شود که کار نمی‌کند، یا توضیحش کافی نیست.
- دکمه‌ی «scenario» در 25% از 32 تپ خطا داد — یا جایی نشان داده می‌شود که کار نمی‌کند، یا توضیحش کافی نیست.

### گونه‌هایی که در یک ربات تلگرامی معادل دارند (نه عیناً)
| در بازی‌های ویدئویی | اینجا |
|---|---|
| فریم‌ریت، draw call، GPU | تأخیرِ هر تپ (p50/p95/p99)، زمانِ هر دورِ تایمر برای ۲۰۰ میز، اندازه‌ی اسنپ‌شات |
| NavMesh و مرزهای نقشه | crawl: هر دکمه در ۴۰ وضعیتِ بازی؛ شلوغ‌کار: هر دکمه‌ی کهنه در هر لحظه |
| قطع‌شدنِ دسته/کنترلر | کاربری که ربات را بلاک کرده، پیامِ پاک‌شده، قطعیِ شبکه، RetryAfter |
| Suspend/Resume کنسول | ری‌استارتِ ربات در هر فاز (فقط SQLite می‌ماند) + توقف/ادامه‌ی میزبان |
| مهاجرتِ میزبان (host migration) | ارتقای گروه به سوپرگروه (chat_id عوض می‌شود) + بازی بدون میزبان تا پایان |
| رزولوشن/نسبت تصویر | سقف‌های Bot API: ۴۰۹۶ نویسه، callback ≤ ۶۴ بایت، طولِ برچسب دکمه روی موبایل، راست‌به‌چپ |
| صدا/زیرنویس | ندارد (ربات صدا ندارد؛ کارت نقشِ PNG با فونت فارسی در crawl سنجیده می‌شود) |
| TRC/XR/TCR | ندارد؛ معادلش قواعدِ Bot API بالاست |

