# 🧪 گزارش QA — همه‌ی گونه‌های آزمونِ بازی

حالت: **کامل (--full)** · نتیجه: **✅ همه سبز**

اجرای دوباره: `python -m playtest.qa` (سریع، چند دقیقه) یا `python -m playtest.qa --full`.
محیط: پایتون 3.11.15 روی linux؛ CI همین را روی ۳.۱۰ تا ۳.۱۳ اجرا می‌کند (`.github/workflows/ci.yml`).

| گونه‌ی آزمون | نتیجه | زمان (ث) | خلاصه |
|---|---|---|---|
| Unit & Integration | ✅ | 5.45 | pytest: 354 passed, 1 skipped in 5.03s |
| Smoke & Sanity | ✅ | 0.4 | modules: 16 |
| Functional & Gameplay | ✅ | 78.85 | games: 189 |
| Regression (chaos players) | ✅ | 7.49 | chaos_games_finished: 105/105 |
| Performance | ✅ | 38.4 | handle_calls: 24132 |
| Soak / Longevity | ✅ | 595.93 | games_per_run: 3000 |
| Network & Multiplayer | ✅ | 4.97 | concurrent_vote_calls: 6000 |
| Platform & Compatibility | ✅ | 7.77 | messages_checked: 19298 |
| Automated gameplay & balance | ✅ | 151.22 | games: 6300 |
| Localization & I18n | ✅ | 2.09 | messages_scanned: 5661 |
| Playtest & UX | ✅ | 9.29 | presses_total: 18878 |

## ✅ Unit & Integration
_pytest: منطقِ خالص (واحد) + ربات/موتور/SQLite/آداپتور با هم (یکپارچگی)_

- **pytest:** 354 passed, 1 skipped in 5.03s
- **tests_passed:** 354
- **test_files:** 20

## ✅ Smoke & Sanity
_دود: import، ساختِ برنامه، همه‌ی اندپوینت‌ها، یک بازی، ذخیره/بازیابی_

- **modules:** 16
- **telegram_handlers:** 77
- **endpoints_checked:** 73
- **smoke_game:** killers در 2 روز
- **snapshot_bytes:** 9890

## ✅ Functional & Gameplay
_agentهایی که Markdownها را خوانده‌اند و فقط با دکمه بازی می‌کنند؛ داورِ مستقل_

- **games:** 189
- **button_presses:** 39276
- **referee_checks_passed:** 15332
- **referee_findings:** 0
- **crawl:** 107872 تپ در 40 وضعیت، 0 یافته → playtest/dead_ends.json

## ✅ Regression (chaos players)
_بازیکن‌های شلوغ‌کار: هر دکمه در هر لحظه، /start وسط بازی، پرشِ ساعت_

- **chaos_games_finished:** 105/105

## ✅ Performance
_کارایی: تأخیرِ هر تپ، دورِ تایمر با ۲۰۰ میز، اسنپ‌شات_

- **handle_calls:** 24132
- **handle_ms_p50/p95/p99:** 0.26 / 0.70 / 1.05
- **slowest_cmds_p99_ms:** startgame 1.5, pass 1.3, act 1.2, dawn 1.2, closejury 0.6
- **handle_ms_on_disk_p50/p95/p99:** 3.45 / 8.29 / 13.50
- **db_file_kb:** 1348.0
- **timer_round_200_tables_s:** 0.018
- **timer_round_200_tables_on_disk_s:** 0.006
- **snapshot_kb:** 18.8
- **snapshot_save_ms:** 0.09
- **board_render_ms:** 0.2
- **board_chars:** 2808

## ✅ Soak / Longevity
_ماندگاری: هزاران بازی در یک پروسه، با و بدون پاک‌سازی_

- **games_per_run:** 3000
- **without_gc: MB / GAMES / _LAST_CALL / snapshots:** 120.6 / 3000 / 72696 / 3000
- **with_gc: MB / GAMES / _LAST_CALL / snapshots:** 1.8 / 50 / 10 / 50
- **peak_growth_second_vs_first_half (with gc):** 2%
- **leak_per_game_without_gc_KB:** 41.2
- **memory_curve_MB (with gc):** 1.8 → 1.8 → 1.9 → 1.8 → 1.9 → 1.8 → 1.9 → 1.8 → 1.8 → 1.8

**مشاهده‌ها:**
- بدون پاک‌سازی (قبل از نسخه ۸) هر بازیِ تمام‌شده، قفلش، ورودی‌های نرخ‌محدودساز و اسنپ‌شاتش برای همیشه می‌ماند — حافظه خطی رشد می‌کرد و بعد از ری‌استارت همه‌ی بازی‌های قدیمی دوباره بار می‌شدند.

## ✅ Network & Multiplayer
_هم‌روندی، خرابیِ تلگرام/شبکه، callbackِ تکراری، فازینگِ ضدتقلب، میزبانِ غایب_

- **concurrent_vote_calls:** 6000
- **concurrent_dawn_calls:** 480
- **long_message_chunks:** 7
- **failure_scenarios_survived:** 8
- **host_gone_game:** قاتل‌ها 🔪 در 2 روز
- **fuzz_calls:** 11900

## ✅ Platform & Compatibility
_سقف‌های Bot API، Markdown، ری‌استارت در هر فاز، ارتقای گروه، توقف/ادامه_

- **messages_checked:** 19298
- **longest_message_chars:** 1668
- **messages_over_4096 (sent in chunks):** 0
- **distinct_callback_data / max_bytes:** 232 / 16
- **markdown_unbalanced:** 0
- **longest_board_chars (12 long chaos games):** 3508
- **hostile_text_messages:** 20
- **restart_ok_in_phases:** اتاق بازجویی، رای‌گیری، شب، صبح، هیئت منصفه، گفتگو

## ✅ Automated gameplay & balance
_هزاران بازیِ ربات‌ها؛ نرخ برد با فاصله‌ی اطمینان ۹۵٪_

- **games:** 6300
- **internal_errors:** 0
- **unfinished (day cap):** 0
**balance_table:**

| سناریو | نفر | شهر (۹۵٪ CI) | قاتل‌ها | جانی | سپر بلا | میانگین روز |
|---|---|---|---|---|---|---|
| classic | 4 | 87% (83–90) | 13% | 0% | 0% | 3.8 |
| classic | 5 | 98% (95–99) | 2% | 0% | 0% | 4.1 |
| classic | 6 | 85% (80–88) | 1% | 0% | 14% | 4.1 |
| classic | 7 | 22% (18–27) | 78% | 0% | 0% | 4.8 |
| classic | 8 | 23% (19–28) | 42% | 0% | 35% | 5.2 |
| classic | 9 | 23% (18–28) | 32% | 0% | 45% | 5.9 |
| classic | 10 | 6% (4–9) | 94% | 0% | 0% | 4.9 |
| court | 4 | 91% (87–93) | 9% | 0% | 0% | 3.9 |
| court | 5 | 93% (90–95) | 7% | 0% | 0% | 4.0 |
| court | 6 | 88% (84–91) | 0% | 0% | 11% | 4.1 |
| court | 7 | 27% (22–32) | 73% | 0% | 0% | 4.7 |
| court | 8 | 24% (20–29) | 75% | 0% | 0% | 5.7 |
| court | 9 | 14% (11–19) | 86% | 0% | 0% | 5.5 |
| court | 10 | 12% (9–17) | 54% | 0% | 34% | 5.8 |
| chaos | 4 | 53% (48–59) | 47% | 0% | 0% | 3.3 |
| chaos | 5 | 66% (60–71) | 34% | 0% | 0% | 4.1 |
| chaos | 6 | 43% (37–48) | 17% | 39% | 0% | 3.9 |
| chaos | 7 | 11% (8–15) | 89% | 0% | 0% | 3.9 |
| chaos | 8 | 20% (16–25) | 58% | 20% | 0% | 4.5 |
| chaos | 9 | 20% (16–25) | 60% | 19% | 0% | 5.0 |
| chaos | 10 | 24% (20–29) | 53% | 21% | 0% | 5.5 |
- **cells_flagged:** 13

**مشاهده‌ها:**
- نامتعادل (با ربات‌های ساده): classic 4 نفره: شهر 87% (CI 83–90)
- نامتعادل (با ربات‌های ساده): classic 5 نفره: شهر 98% (CI 95–99)
- نامتعادل (با ربات‌های ساده): classic 6 نفره: شهر 85% (CI 80–88)
- نامتعادل (با ربات‌های ساده): classic 10 نفره: شهر 6% (CI 4–9)
- نامتعادل (با ربات‌های ساده): classic 10 نفره: killers 94%
- نامتعادل (با ربات‌های ساده): court 4 نفره: شهر 91% (CI 87–93)
- نامتعادل (با ربات‌های ساده): court 5 نفره: شهر 93% (CI 90–95)
- نامتعادل (با ربات‌های ساده): court 6 نفره: شهر 88% (CI 84–91)
- نامتعادل (با ربات‌های ساده): court 9 نفره: شهر 14% (CI 11–19)
- نامتعادل (با ربات‌های ساده): court 9 نفره: killers 86%
- نامتعادل (با ربات‌های ساده): court 10 نفره: شهر 12% (CI 9–17)
- نامتعادل (با ربات‌های ساده): chaos 7 نفره: شهر 11% (CI 8–15)
- نامتعادل (با ربات‌های ساده): chaos 7 نفره: killers 89%

## ✅ Localization & I18n
_رقم فارسی، نشتِ انگلیسی/پایتون، mojibake، برچسب دکمه، نام‌های عجیب، UTF-8_

- **messages_scanned:** 5661
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

- **presses_total:** 18878
- **error_rate_overall:** 1.1%
- **error_heatmap (top):** startgame 50% of 168 | scenario 25% of 224 | closevote 9% of 444 | hints 8% of 203 | ask 4% of 390 | will 0% of 336
- **top_error_messages:** ⛔ این بازیکن‌ها هنوز پیوی ربات را باز نکرده‌اند: آرش، بهار، کاوه، دنیا ×84 | ⛔ فقط میزبان می‌تواند سناریو را عوض کند. ×56 | ⛔ بازجو الان نمی‌تواند کار کند (خودش متهم، زندانی یا بیرون از بازی است ×32 | ⛔ ⏳ هنوز همه رای نداده‌اند (ممتنع هم رای است)؛ ۸۲ ثانیه تا پایان مهلت. ×10
- **bot_group_msgs_per_player_day:** 2.09
- **group_chat_msgs_total:** 1469
- **taps_per_night_decision:** 1.0
- **game_length_days p50/p90/max:** 5 / 8 / 13
- **nights_needing_grace:** 0
- **games:** 84
- **tutorial_chars:** 634

**مشاهده‌ها:**
- دکمه‌ی «startgame» در 50% از 168 تپ خطا داد — یا جایی نشان داده می‌شود که کار نمی‌کند، یا توضیحش کافی نیست.
- دکمه‌ی «scenario» در 25% از 224 تپ خطا داد — یا جایی نشان داده می‌شود که کار نمی‌کند، یا توضیحش کافی نیست.

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

