# Changelog — Karagah (کارآگاه)

Every version below is one commit. Each commit message has the full detail, and this file is the map. Test numbers are the full pytest suite at that commit.

## v9: visual design, live lobby card, cleanup (`3db5cc0`)
**Design**
- New `karagah/theme.py`: ribbon headers (`🌙 ┈┈ شبِ ۲ ┈┈ 🌙`) on every announcement.
- Hourglass `⏳`/`⌛` that flips on each 5-second edit of the live card.
- Progress bar in the phase colour with a ✨ that moves each edit; it turns red in the last 20% of the time.
- Single-emoji transition frames (🌇→🌆→🌃→🌙, 🌌→🌄→🌅→☀️, 🔒→⛓️, 🏁→🎉), which Telegram shows big and animated.
- 🟢⚪ readiness meter.
- Based on Bot API 9.4–10.x research (sources in `playtest/DESIGN_V9.md`):
  - optional animated custom-emoji button icons (`BUTTON_EMOJI`, needs a Premium bot owner);
  - private-chat message effects: 🔥 on the role card, 🎉 for winners.
  - Both fall back automatically if Telegram rejects them.

**Lobby and "✅ آماده‌ام"**
- The new-game message *is* the live lobby card: players with ✅ or ⏳, the readiness meter and the next step. It updates after every tap, after "ready" in private chat, and every 5 s while the lobby is active.
- "Ready" also joins. After the game starts, it explains that the game is running.
- Idle lobbies stop animating after 10 minutes.

**Cleanup**
- "🔙 بازگشت" and "🏠 منوی اصلی" both went to the menu and sat side by side under more than 1,100 messages. They are now one "🏠 منو", and `ui.kb()` drops any repeated callback.
- The live card has no redundant refresh or menu buttons.
- The host panel no longer claims "only you see this" in a group.
- The main menu has no in-game dead buttons, and there is no channel button.
- Only-game wording:
  - help, tutorial and ability texts describe the current rules;
  - no file names, and no "ID" wording in errors;
  - admin pages answer privately;
  - join and share in a private chat no longer create invisible private tables.

**Gameplay fixes**
- The detective could check a clue, pass, then investigate: two actions in one night.
- A night with no free night role waited 60 s for nothing. It now ends at once.

**Testing**
- Agents with 4–10 players in all 3 scenarios, buttons only, now also pass ("🙅 امشب کاری نمی‌کنم") and change their minds. The report has a per-role move-coverage matrix.
- The referee requires every clue to come from a real event that night, and no clue on crime-free nights.
- 24 new tests (378 total). Full sweep 252/252 and chaos players 105/105 with 0 findings, crawler 0 dead ends, QA suite all green.

## v8: full QA suite (`191c882`)
- `python -m playtest.qa [--full]` runs every game-testing type:
  - unit & integration, smoke, functional, regression, performance, soak;
  - network & multiplayer, platform & compatibility, automated bots & balance;
  - localization & i18n, playtest & UX.
- It writes `playtest/QA_REPORT.md`.
- CI in `.github/workflows/ci.yml`: pytest on Python 3.10–3.13, the quick QA suite on push and PR, the full suite nightly.
- **Fixed:**
  - Persian digits everywhere, and a right-to-left mark on Latin-first messages;
  - a Python list leak in the end-of-game recap;
  - names stripped of bidi-override and invisible characters and capped at 32;
  - player free text can no longer break Markdown;
  - a memory and disk leak (about 41 KB per game): `bot.gc()`;
  - idle timer ticks no longer write to disk;
  - thread-safe SQLite;
  - long messages are split under 4096 characters;
  - a supergroup migration keeps the game;
  - the lab chooser hides clues already in the lab.
- Details: `playtest/QA_FINDINGS.md`.

## v7: live game panel, self-editing clock, night waits for everyone (`1a07c5b`)
- Calling the bot mid-game (start, menu, back, private-chat text) shows the current game, not the bot menu.
- **Night rules:**
  - The night ends only when every night role has acted or pressed "🙅 not tonight".
  - The last decision brings the morning immediately.
  - Interrogation nights also wait for the officer's "✅ interrogation finished".
  - The host can't close the night early.
  - At the deadline, undecided roles get one grace period with private reminders.
- One clock message per phase, edited every 5 s. It never names anyone at night.
- New chaos-player tester (`playtest/monkey.py`) and `playtest/FLOW_AUDIT.md`.

## v5/v6: clues and scenario scenes (`b5bd894`)
- **Clues:** true clues come from the real attacker's traits and connect, narrowing to one person. False clues (frames, decoys) never match any culprit of that night or any killer-team member. The lab, the detective's clue check and the forensic doctor reveal the truth, and the case board ranks suspects.
- **Scenes:** each scenario has its own cases, six locations, clue wording and a sixth trait. Every clue has a location and a daily detail that never repeats.
- Per-scenario rules: starting clues, decoy rate, lab nights, jury threshold (court 50%), night events.
- Talking agents: claims, fake claims, frame pushing and lie detection (`playtest/talk.py`).

## Playtest crawler and game audit (`02c229c`)
- `playtest/crawl.py` presses every reachable button in 43 game states.
- `playtest/GAME_AUDIT.md` documents the whole game and every dead end found.

## Referee false positive (`77bc4e0`)
- A first-dawn win is only flagged when the killers win it. A 6-player chaos town win, where the killer and the serial killer killed each other, was legitimate.

## v4: precise scenario rules (`e6650e8`)
- Three scenarios (classic, court, chaos) that deal all 18 roles.
- **Interrogation and custody:**
  - two-way interrogation, where questions reach the suspect and answers return to the officer;
  - an automatic jury when the officer can't rule;
  - detained players are immune at night.
- **Killers and win conditions:**
  - kill succession to the accomplice, then poisoner, then spy;
  - a strict win order;
  - one `is_winner()` for XP and stats.
- **Votes and announcements:**
  - vote runoff between tied players only;
  - public events always reach the group;
  - timer messages equal button messages.
- `RULES.md` is the rulebook and is checked against the code. 294 tests at this point.

## Playtest agents (`d375fba`)
- Agents fill 4–10-player tables, read every Markdown file first, and play only by pressing the buttons the bot shows them.
- An independent referee predicts each dawn and compares it with the bot.
