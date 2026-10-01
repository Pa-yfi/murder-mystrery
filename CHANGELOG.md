# Changelog — Karagah (کارآگاه)

Every version below is one commit. Each commit message has the full detail, and this file is the map. Test numbers are the full pytest suite at that commit.

## v10: one live card per phase, cleaner group, right-to-left names
Based on a captured full game: 27 group messages for 2 days, each phase posted twice, every vote posted its own message, and English names flipped lines. Popular Telegram werewolf bots use one message per phase, private actions by DM, and pop-up vote confirmations.

**One live card per phase**
- The phase announcement (morning report, voting, interrogation, jury…) *is* the live card. The countdown and progress bar sit at its bottom and update every second.
- When the phase ends, the card keeps its content but loses the timer and buttons, so old buttons can't be pressed later.
- Before, each phase was an announcement plus a separate timer message.
- Implemented once in the bot layer (`bot._phase_card`, `CARDS`, `clock_view` with `final`), so the Telegram adapter and the test harness share it.
- **Start:** the case file is its own message and is pinned when the bot is an admin. The night-1 card follows it.
- **Votes:** the voter gets a small pop-up ("✅ your vote: X") instead of a group message per vote. The card shows "n/m votes" and, for public votes, a live tally per candidate.
- **Result:** group messages per player per day went from 2.96 to 1.88 (−36%) in the UX telemetry. A 7-player game went from 27 to 16 group messages.

**Persian and English names together**
- Telegram picks each *line's* direction from its first strong letter, so a line starting with "Ali" became left-aligned.
- Neutral characters (":", "·", numbers) between two English names flipped order.
- `l10n.rtl_lines` adds an invisible right-to-left mark at the start of such lines and after an English run only where it's followed by punctuation, a number, an emoji, another English name or the line end. It's idempotent, and links and `code` are untouched.

**Tidier texts**
- The night report starts with its "☀️ Morning N" header; the reason the night ended early comes under it.
- The dashboard uses the compact three-per-line list.
- One divider everywhere, including the end report and menus.
- Cards never carry the dashboard/menu buttons, which would have replaced the card's text.
- Finished games' cards are cleaned up, and cards follow a group when it is upgraded to a supergroup.

**Tests:** card adoption and closing, per-second edits on the same message, pop-up votes, and line direction. The "night clock names nobody" secrecy check now looks at the live part of the card, which is the part that could leak. 413 tests pass; the quick QA suite is all green.

## Timers and tidier messages
**Timers**
- Night and day (discussion) are now **7 minutes** each (`NIGHT_SECONDS=420`, `DISCUSS_SECONDS=420`, still overridable).
- The live clock card edits itself **every second** (`CLOCK_SECONDS=1`): the countdown shows every second, and the hourglass and ✨ move each second.
- Telegram limits how often a bot may edit messages in a group. When it answers `RetryAfter`, only that group's clock waits the time Telegram asks for, then goes back to per-second updates. The game and its deadlines never stop.
- The 1-second job never overlaps itself (`max_instances=1`, `coalesce`), and APScheduler's "skipped run" warnings are silenced.

**Tidier messages**
- One divider (`┈`) everywhere, instead of a mix of `─` and `┈`.
- Clues are grouped by place: "📍 place — today's detail" appears once, with the clues under it, instead of repeated under every clue.
- The city status lists three players per line, with an "alive/total" count, instead of one player per line.
- The case intro is more compact: victim and scene, then weapon and motive, share a line.
- The lobby shows "roles appear with 4+ players" instead of an empty roles line.
- The night clock hint is shorter.
- Tests: default durations, a clock that edits each second, flood backoff and resume, clue grouping, compact board. 411 tests pass; the quick QA suite is all green.

## Deploy: one SSH connection per job
- The third real run passed the key check, then timed out on login right after `ssh-keyscan`. keyscan opens a burst of connections (one per key type), which `ufw limit` or fail2ban treat as an attack.
- There is no keyscan any more: the host key is learned on the first login (`StrictHostKeyChecking accept-new`, or pinned with `VPS_KNOWN_HOSTS`). An SSH ControlMaster lets the upload reuse that login, so the whole job opens **one** connection (checked against a local sshd).
- If the login fails, it retries once after 30 s. The error then says which problem it is: unreachable (firewall or port), key refused, or host key mismatch.

## Deploy: clearer VPS_SSH_KEY check
- New `deploy/prepare_key.py` replaces the single vague "not a private key" error.
- It repairs copy/paste damage by itself: line breaks turned into spaces or lost, Windows line endings, indentation, a shell prompt around the key.
- It names each mistake it can't repair: the public `.pub` key, a key cut off before its END line, a damaged middle, a passphrase, a PuTTY `.ppk` key, empty or unrelated text.
- It also repairs a key where only the middle was copied (no BEGIN/END lines), and names the fingerprint or randomart that `ssh-keygen` prints, or a password pasted instead of the key.
- It undoes look-alike characters that phones and chat apps put in while copying: long or en dashes instead of `-----`, non-breaking or invisible spaces, a byte-order mark. When such characters break the key anyway, it lists their names, never the key's content.
- On success it prints the key's fingerprint.
- Public-repo logs: a successful deploy no longer prints the VPS hostname (it often contains the IP) or the bot's first log lines (group chat IDs). Only a failed start prints the bot log.
- `tests/test_deploy_key.py`: 30 cases against real `ssh-keygen` (ed25519, RSA, RSA PEM × 4 kinds of damage, middle-only, look-alike characters, and every error).

## Deploy from GitHub to a VPS
- New `.github/workflows/deploy.yml`: on every push to `main` (or "Run workflow") it runs the tests, logs in to the VPS with the `VPS_SSH_KEY` secret and uploads the commit plus a settings file built from the secrets (`BOT_TOKEN`, `BOT_USERNAME`, `DB_PATH`, `ADMIN_IDS`, `BOT_EXTRA_ENV`). The server needs no GitHub access. Until `VPS_HOST` is set, it only prints a warning.
- New `deploy/vps_deploy.sh` (runs on the server):
  - installs Python/venv if missing;
  - keeps the venv and the database between deploys;
  - checks `DB_PATH` (folder or trailing `/`, inside the code folder, relative name) and creates its folder;
  - writes and starts the systemd service `karagah`, which restarts after crashes and reboots;
  - waits 15 s and, if the bot didn't stay up, starts the previous version again and fails the job with the bot's log;
  - warns about a second copy (`Conflict`).
- Tested end to end over real SSH with a local sshd: first deploy, redeploy, rollback after a crashing build (database kept), root and non-root users with and without sudo, and every error message.
- `telegram_app.py`: `httpx` logs at WARNING. At INFO it logged every getUpdates call with the token in the URL, a line every few seconds on a 24/7 server.
- Step-by-step guide: `DEPLOY.md`.

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
