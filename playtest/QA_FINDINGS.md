# QA round (v8): what each testing type found

Run everything with `python -m playtest.qa` (quick) or `--full`. CI runs the quick suite on every push and PR, and the full suite nightly (`.github/workflows/ci.yml`). The latest numbers are in `playtest/QA_REPORT.md`.

## Bugs found and fixed

| # | Found by | Severity | Bug | Fix |
|---|---|---|---|---|
| 1 | Localization | medium | Player text mixed Latin and Persian digits: "صبح روز 1" next to "صبحِ روز ۱", about 1,000 occurrences in 9 games. | `karagah/l10n.py` runs once on every reply, outbox message and clock. Digits become Persian; `C12`, links, code spans and callback data are left alone. |
| 2 | Localization | medium | A Python list leaked into the end-of-game recap (`کشته‌ها=['…']`). | The night log line uses a joined Persian list. |
| 3 | Localization | low | 30 messages started with a Latin letter (clue codes), so Telegram laid out the whole message left-to-right. | An invisible right-to-left mark is added when the first strong character is Latin. |
| 4 | Localization / security | medium | Player names kept right-to-left override and zero-width characters, which can spoof or flip nearby text in group messages. Names could be 120 characters long. | Invisible and bidi-control characters are stripped (the Persian half-space U+200C is kept), whitespace is collapsed, and names are capped at 32 characters. |
| 5 | Localization / UX | low | The "not everyone is ready" error told the host to type `/startgame force`: English, and a typed command in a buttons-only bot. | A "⚡ شروع بدون آن‌ها" button replaces it. |
| 6 | UX | low | Clue buttons were about 40 characters, so phones truncated them. | Short labels: `❔ C3 · 💍 انگشتر: طلا`. |
| 7 | UX telemetry | low | The lab chooser offered clues that were already in the lab, so 6% of lab taps failed. | Queued clues are hidden. |
| 8 | Soak | high | Memory and disk leak. Every finished game, its lock, the rate-limit entries and its snapshot stayed forever (about 41 KB per game), and a restart re-loaded every old game. | `bot.gc()` runs from the timer. It evicts finished games after `ENDED_TTL` (6 h) and idle or abandoned tables after `IDLE_TTL` (24 h), prunes stale dictionaries, and drops their snapshots. Timer ticks don't count as activity. |
| 9 | Performance | medium | Every 5-second timer tick rewrote every table's snapshot and audit row, even when nothing happened (200 tables means 40 disk writes per second). | Idle ticks write nothing. The 200-table timer round on disk went to 5 ms. |
| 10 | Network / multiplayer | high | The shared SQLite connection wasn't thread-safe. Concurrent commits raised "cannot commit – no transaction is active" or SystemError, and because `touch_user` ran outside the guard, the exception escaped `handle()`, which must never throw. | A re-entrant lock is applied to every public db function, and `touch_user` moved inside the guard. Now 6,000 concurrent vote calls and 480 concurrent dawn calls produce 0 errors. |
| 11 | Platform (Markdown) | medium | Free text (officer question, answer, defense, will, note) was stored raw. A `*`, `_` or backtick broke Telegram Markdown, and the message fell back to plain text. | Free text is cleaned on entry (`_clean`). |
| 12 | Platform (limits) | medium | Messages over Telegram's 4096 limit failed with no split. The board reaches 3.5K characters in long games and keeps growing. | `telegram_app.chunks()` splits on line boundaries with the keyboard on the last chunk; long edits fall back to chunked sends. |
| 13 | Platform | medium | When a group is upgraded to a supergroup, the chat id changes and the running game was orphaned. | A migrate-status handler plus `bot.migrate_chat` move the game, snapshot, pending prompts and clock to the new id. |

Harness-only issue (not a game bug): the referee compared expected notes using Latin digits after the game started sending Persian digits.

## Checked and green
- **Unit and integration:** 354 tests pass on Python 3.10, 3.11, 3.12 and 3.13.
- **Smoke:** 16 modules import, the Telegram app builds offline with 77 handlers, all 73 endpoints answer in lobby and mid-game (group and DM), a full game completes, and a snapshot restores and continues.
- **Functional:** button-driven agents with a referee, plus a crawler that presses every button in 40 game states.
- **Regression:** chaos players press any button, stale or not, at any moment.
- **Performance:** p99 is about 1 ms per tap in memory and about 11–15 ms per tap on disk. A timer round for 200 tables takes 5–60 ms against a 5-second interval, and a snapshot is about 19 KB.
- **Network and multiplayer:** these all pass:
  - a user who blocked the bot (private text is never leaked to the group);
  - broken Markdown;
  - network timeouts and outages;
  - deleted clock messages and flood limits;
  - duplicate callbacks;
  - 11,900 hostile fuzz calls in the full run (injection strings, huge numbers, strangers, the dead, jailed players, killers targeting teammates);
  - a game finishing without its host.
- **Platform:** callback data is at most 16 bytes, keyboards fit Telegram's limits, a restart mid-phase resumes and finishes in all 6 phases, and pause/resume keeps the remaining time.

## Balance observations (not bugs; decisions for the designer)
These come from simple, non-talking bots over thousands of games. See the table in `QA_REPORT.md`.
- **4–6 players (classic, court):** the town wins about 85–98% (full run, 300 games per cell). One killer against a detective loses fast.
- **Three-killer tables (court 9–10, classic 10):** the town wins 6–14% with these bots, and chaos 7 is 11%.
- **Talking agents:** in the earlier simulation with claims and bluffs (`playtest/talk.py`), the same scenarios were much closer (classic 47/39, court 57/36, chaos 44/34 overall). Skill and communication shift the balance a lot. Suggestion: consider a weaker detective for 4–5 players, and only two killers at 9 players in court.
