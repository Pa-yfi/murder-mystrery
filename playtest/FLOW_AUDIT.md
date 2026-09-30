# Flow audit (v7): buttons, sequence, live timer, night waiting

How this was checked:
- `python -m playtest.monkey`: agents press any visible button at any moment (including stale ones), type `/start` and `/menu` in the group and in DMs, send DM text, and jump the clock in 5-second timer ticks, while normal play keeps the game moving. After every step it checks:
  - the night/day order;
  - internal errors;
  - stalls;
  - the jail timing;
  - whether a night ended before everyone decided;
  - whether the clock edits itself;
  - whether the night clock names anyone.
- `python -m playtest --seeds 4`: 252 full games (3 scenarios × 4–10 players × 4 seeds × 3 ways of advancing phases) plus rule probes.
- `python -m playtest.crawl`: every button in 40 game states.
- `tests/test_live_flow_v7.py`: 16 unit tests for the rules below.

## Bugs found (all fixed)

| # | Severity | Bug | How it was found | Fix |
|---|---|---|---|---|
| 1 | high | `/start`, `/menu`, 🏠 and 🔙 during a game showed the generic bot menu, in the group and in DMs. DM text showed the "all buttons" board. | monkey baseline: 155 hits in 42 games | `h_start`, `h_menu` and `back` show the **current game**. In the group: clock + dashboard + this phase's buttons. In a DM: your role, status, tonight's decision and your buttons. "🏠 full menu" (`fullmenu`) sits under the panel. |
| 2 | high | The night never ended when everyone had acted. The table waited the full 60 s or for someone to press "end night". | code reading + timeline | The last decision triggers dawn at once, and the morning is posted to the group (`_dawn_if_all_decided`). |
| 3 | high | There was no way to "choose not to play" at night. A doctor who wanted to skip looked the same as an absent player. | code reading | New "🙅 امشب کاری نمی‌کنم" button (`pass`). It counts as a decision, cancels any chosen target, and can be undone until dawn. |
| 4 | high | The host could close the night after half the time even with roles undecided. | code reading (`_gate` host override) | Removed for the night. Only "everyone decided" or "deadline + grace" ends it. |
| 5 | medium | At the deadline, the night ended immediately and undecided roles were silently dropped. | code reading | One grace period (`NIGHT_GRACE_SECONDS=30`, half in blitz). Each undecided player gets a DM reminder with their buttons. The group sees an announcement with no names. After the grace period, undecided players count as "did nothing". |
| 6 | medium | There was no live countdown. The timer job ran every 15 s and only posted when the phase changed. | code reading | One clock message per phase, **edited every 5 s** (`CLOCK_INTERVAL`). It shows the phase, the day/night number, the time left with a 🟩⬜ bar, vote counts, and the path (`📅 🌙۱ ☀️۱ 🌙۲▶️`). When the phase changes, the old clock is marked "✔️ تمام شد" and a new one is posted. At night it never shows names or counts. |
| 7 | high (prevented) | With auto-dawn, an interrogation night would have closed before the officer asked anything. | harness while building #2 | In interrogation nights the officer must press "✅ بازجویی تمام شد". The night waits for it, and the deadline + grace still apply. |
| 8 | medium | The detective's "check a clue" did not count as a decision, so the night would wait for the timer. | code reading | `h_expose` also triggers the auto-dawn check. |
| 9 | low | The night-action panel opened during the day still said "the night is waiting for your decision". | monkey (6-player classic, seed 5) | Outside the night, the panel says "it's not night; act on night N+1". |
| 10 | low | README endpoint count was stale (71; the code has 73). | sweep doc check | Updated. |

## Checked and correct (no change needed)
- **Order:** night N → morning N → discussion N → vote N → night or interrogation night N+1. This held in every monkey game (147 total across all runs) and every sweep game. The only same-dawn jump is night → jury, when the officer can't judge (the morning message then carries the jury).
- **Crashes:** no internal error ("خطای داخلی") in any response, whatever was pressed and whenever.
- **Stalls:** no stalls, as long as someone resumes a paused game (pause is host-only by design).
- **Jail timing:** temporary jail becomes life jail after exactly 2 nights.
- **Old saves:** snapshots from older versions restore with the new fields filled in (`_upgrade`).

## Harness-only issues fixed (not game bugs)
- The referee counted jail nights only for nights it drove itself, so timer-ended nights looked like "life jail after 1 night". The monkey now tracks custody itself.
- The referee compared the pressed actions after the engine had already resolved the night (the last decision now resolves it). A `NIGHT_OBSERVERS` hook in the engine lets it compare at the moment of resolution.
- The harness's "clue check worked" test looked for the old wording, so the detective's clue check was never exercised.

## Deliberate choice to review
"The night must not end until everyone decides" is enforced. The one exception is a player who ignores both the deadline and the grace reminder: after the grace period they count as "did nothing", so one absent player can't freeze the table forever. The grace length is `NIGHT_GRACE_SECONDS` in `.env`. Setting it very high makes the night effectively wait for everyone; the host can still ⏸️ pause.
