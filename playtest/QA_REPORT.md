# 🧪 گزارش QA — همه‌ی گونه‌های آزمونِ بازی

حالت: **سریع (--quick)** · نتیجه: **✅ همه سبز**

اجرای دوباره: `python -m playtest.qa` (سریع، چند دقیقه) یا `python -m playtest.qa --full`.
محیط: پایتون 3.11.15 روی linux؛ CI همین را روی ۳.۱۰ تا ۳.۱۳ اجرا می‌کند (`.github/workflows/ci.yml`).

| گونه‌ی آزمون | نتیجه | زمان (ث) | خلاصه |
|---|---|---|---|
| Unit & Integration | ✅ | 5.5 | pytest: 378 passed, 1 skipped in 5.12s |
| Smoke & Sanity | ✅ | 0.35 | modules: 17 |
| Functional & Gameplay | ✅ | 2.42 | games: 21 |
| Regression (chaos players) | ✅ | 2.02 | chaos_games_finished: 21/21 |
| Performance | ✅ | 19.54 | handle_calls: 3485 |
| Soak / Longevity | ✅ | 61.46 | games_per_run: 300 |
| Network & Multiplayer | ✅ | 3.67 | concurrent_vote_calls: 6000 |
| Platform & Compatibility | ✅ | 2.12 | messages_checked: 2618 |
| Automated gameplay & balance | ✅ | 30.03 | games: 1260 |
| Localization & I18n | ✅ | 0.89 | messages_scanned: 1837 |
| Playtest & UX | ✅ | 1.98 | presses_total: 2693 |

## ✅ Unit & Integration
_pytest: منطقِ خالص (واحد) + ربات/موتور/SQLite/آداپتور با هم (یکپارچگی)_

- **pytest:** 378 passed, 1 skipped in 5.12s
- **tests_passed:** 378
- **test_files:** 21

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
- **button_presses:** 4375
- **referee_checks_passed:** 1835
- **referee_findings:** 0

## ✅ Regression (chaos players)
_بازیکن‌های شلوغ‌کار: هر دکمه در هر لحظه، /start وسط بازی، پرشِ ساعت_

- **chaos_games_finished:** 21/21

## ✅ Performance
_کارایی: تأخیرِ هر تپ، دورِ تایمر با ۲۰۰ میز، اسنپ‌شات_

- **handle_calls:** 3485
- **handle_ms_p50/p95/p99:** 0.27 / 0.76 / 1.17
- **slowest_cmds_p99_ms:** startgame 1.5, act 1.4, pass 1.2, closevote 1.1, castvote 0.6
- **handle_ms_on_disk_p50/p95/p99:** 4.11 / 10.75 / 16.93
- **db_file_kb:** 264.0
- **timer_round_200_tables_s:** 0.018
- **timer_round_200_tables_on_disk_s:** 0.006
- **snapshot_kb:** 18.8
- **snapshot_save_ms:** 0.09
- **board_render_ms:** 0.16
- **board_chars:** 2808

## ✅ Soak / Longevity
_ماندگاری: هزاران بازی در یک پروسه، با و بدون پاک‌سازی_

- **games_per_run:** 300
- **without_gc: MB / GAMES / _LAST_CALL / snapshots:** 12.1 / 300 / 7241 / 300
- **with_gc: MB / GAMES / _LAST_CALL / snapshots:** 1.9 / 50 / 5 / 50
- **peak_growth_second_vs_first_half (with gc):** 0%
- **leak_per_game_without_gc_KB:** 41.4
- **memory_curve_MB (with gc):** 1.1 → 0.4 → 1.5 → 0.8 → 1.9 → 1.2 → 0.4 → 1.6 → 0.8 → 1.9

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

- **messages_checked:** 2618
- **longest_message_chars:** 1677
- **messages_over_4096 (sent in chunks):** 0
- **distinct_callback_data / max_bytes:** 197 / 16
- **markdown_unbalanced:** 0
- **longest_board_chars (12 long chaos games):** 3508
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
| classic | 4 | 92% (82–96) | 8% | 0% | 0% | 3.9 |
| classic | 5 | 98% (91–100) | 2% | 0% | 0% | 4.0 |
| classic | 6 | 82% (70–89) | 2% | 0% | 17% | 4.0 |
| classic | 7 | 27% (17–39) | 73% | 0% | 0% | 5.2 |
| classic | 8 | 22% (13–34) | 40% | 0% | 38% | 5.7 |
| classic | 9 | 23% (14–35) | 35% | 0% | 42% | 5.7 |
| classic | 10 | 10% (5–20) | 90% | 0% | 0% | 4.7 |
| court | 4 | 97% (89–99) | 3% | 0% | 0% | 4.0 |
| court | 5 | 88% (78–94) | 12% | 0% | 0% | 3.9 |
| court | 6 | 83% (72–91) | 0% | 0% | 17% | 4.1 |
| court | 7 | 18% (11–30) | 82% | 0% | 0% | 4.8 |
| court | 8 | 43% (32–56) | 57% | 0% | 0% | 5.5 |
| court | 9 | 15% (8–26) | 85% | 0% | 0% | 5.1 |
| court | 10 | 17% (9–28) | 57% | 0% | 27% | 6.0 |
| chaos | 4 | 53% (41–65) | 47% | 0% | 0% | 3.2 |
| chaos | 5 | 70% (57–80) | 30% | 0% | 0% | 4.1 |
| chaos | 6 | 57% (44–68) | 18% | 25% | 0% | 4.3 |
| chaos | 7 | 7% (3–16) | 93% | 0% | 0% | 3.5 |
| chaos | 8 | 15% (8–26) | 60% | 22% | 0% | 4.6 |
| chaos | 9 | 23% (14–35) | 52% | 23% | 0% | 4.9 |
| chaos | 10 | 32% (21–44) | 55% | 12% | 0% | 5.7 |
- **cells_flagged:** 6

**مشاهده‌ها:**
- نامتعادل (با ربات‌های ساده): classic 4 نفره: شهر 92% (CI 82–96)
- نامتعادل (با ربات‌های ساده): classic 5 نفره: شهر 98% (CI 91–100)
- نامتعادل (با ربات‌های ساده): court 4 نفره: شهر 97% (CI 89–99)
- نامتعادل (با ربات‌های ساده): court 5 نفره: شهر 88% (CI 78–94)
- نامتعادل (با ربات‌های ساده): chaos 7 نفره: شهر 7% (CI 3–16)
- نامتعادل (با ربات‌های ساده): chaos 7 نفره: killers 93%

## ✅ Localization & I18n
_رقم فارسی، نشتِ انگلیسی/پایتون، mojibake، برچسب دکمه، نام‌های عجیب، UTF-8_

- **messages_scanned:** 1837
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

- **presses_total:** 2693
- **error_rate_overall:** 0.9%
- **error_heatmap (top):** startgame 50% of 24 | scenario 25% of 32 | closevote 7% of 73 | will 0% of 45 | vote 0% of 315 | ver 0% of 23
- **top_error_messages:** ⛔ این بازیکن‌ها هنوز پیوی ربات را باز نکرده‌اند: آرش، بهار، کاوه، دنیا ×12 | ⛔ فقط میزبان می‌تواند سناریو را عوض کند. ×8 | ⛔ ⏳ هنوز همه رای نداده‌اند (ممتنع هم رای است)؛ ۸۰ ثانیه تا پایان مهلت. ×2 | ⛔ ⏳ هنوز همه رای نداده‌اند (ممتنع هم رای است)؛ ۸۶ ثانیه تا پایان مهلت. ×2
- **bot_group_msgs_per_player_day:** 2.96
- **group_chat_msgs_total:** 209
- **taps_per_night_decision:** 1.0
- **game_length_days p50/p90/max:** 5 / 8 / 9
- **nights_needing_grace:** 0
- **games:** 12
- **tutorial_chars:** 806

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

