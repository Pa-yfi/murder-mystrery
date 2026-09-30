# Claude handoff: repair the playable game loop and role abilities

Date: 2026-09-20. **Documentation only: no application or test implementation is changed by this report.**

## 1. Owner's latest requirements — highest priority

The owner played the bot and reported:

1. Players must vote to change from day to night instead of receiving an abrupt phase-change notification.
2. Each character must be able to activate its own intended abilities, privately where appropriate, and must not activate another role's abilities.
3. Play must continue through **Night 1, Night 2, Night 3, …** until a valid criminal/city outcome or an explicitly supported neutral outcome occurs.
4. Review all endpoints and provide consecutive problems, fixes, and acceptance criteria for Claude to implement.

**This latest player-voted day-to-night requirement supersedes any earlier recommendation in `rules.md` or `improvement.md` that would let a discussion/vote timer automatically move into night without player approval.** Update those documents together with implementation. Do not treat the previous automatic progression as the acceptance oracle.

This is a source review plus a handoff plan, not a new live test of the owner's session. The exact messages/logs from that session were not supplied, so the root causes below are supported by the code, not a reconstructed claim about which individual button they pressed.

## 2. Reviewed source and evidence limits

The review found **69 registered endpoint names** in `karagah/bot.py::_ROUTES`. All 69 are individually listed in section 8, in registration order. Also reviewed: the command/callback/text adapter, menus, role definitions, engine phases/night effects, and the existing persistence paths.

Read-only inspection also found newer menus and pending-text input that were not in the older audit snapshot. Source files have been changing independently during this session. Function names below are the stable references; recheck current implementation before editing.

Source fingerprints captured for this review:

| File | SHA-256 |
|---|---|
| `karagah/bot.py` | `cbe50d72571258414a3fa1ba1e22c153b963444e3d83fec2cefcf38f3db08af4` |
| `karagah/engine.py` | `d21b6fd54154ea6a2000b9d4c4fe52a92abd4aad04e9ae2b9865eb77ada9b5da` |
| `karagah/menus.py` | `dd90f314db684b6ffa8fbfad38eb90537b7b030dec431ee6065170288d34dcaf` |
| `karagah/telegram_app.py` | `33f789d5601e69384085f574d278b5ea5e4df5403f7e5151c708d92330472cc5` |

The earlier recorded audit had 184 existing passes, one skip, and 1,262 new passes / 63 failed contract cases. Those numbers belong to the hashed snapshot in [audit-results.md](audit-results.md), **not automatically to these newer menus/handlers**. Do not repeat them as proof this current version is passing or that a newer fix still fails.

## 3. Main problems and the repair order

### P01 — There is no consent vote to move from day to night

**Observed:** `Game.tick()` changes discussion to suspect voting, and closes the suspect vote when its deadline expires. `close_vote()` moves directly to `NIGHT`, or `send_to_interrogation()` moves to the next interrogation night. `/vote` and `/castvote` are accusation voting, not phase-consent voting. `/dawn`, `/discuss`, `/vote`, and `/closevote` call engine transitions directly.

**Impact:** A countdown or another player can move the game before participants are ready. Calling an accusation vote “a vote to change phase” would not meet the owner's requirement.

**Fix:** Add a distinct public **«آمادهٔ شب بعد هستم»** vote. Store it separately from suspect ballots, jury votes, interpretation votes, and emergency votes. Centralize transitions so neither a timer nor a legacy command can bypass this gate.

**Check:** With six eligible players, three approvals do not advance; four do. A timer cannot bypass that threshold. Repeated taps count once. A rejected or stale vote cannot change the round.

### P02 — Ability explanation, available button, authorization, and actual effect are separate and inconsistent

**Observed:** `menus.abilities_text()` describes phase/status restrictions, but `abilities_kb()` mostly checks whether the role has an ability. It can still offer buttons outside a usable phase/state. Officer and detective alternative actions are described without being fully represented in the own-abilities keyboard. `/hunter` still parses an integer immediately, while a naked “hunter” button can be offered. The forensic specialist is routed through a player-target action although its power concerns evidence.

**Impact:** A role may exist in the catalog and pass a basic engine test yet feel broken to a real player who cannot find a valid activation path or never receives the result.

**Fix:** Build one capability policy returning allowed actions, legal target type/set, remaining uses, disabled reason, and delivery visibility. Use that policy for both menus and execution. Each ability needs the whole chain: **discover → select → validate → commit → acknowledge → resolve → privately/publicly deliver the correct result**.

**Check:** A player can complete each advertised role's action using only buttons and necessary human text; no numeric-ID knowledge is required. Others cannot execute it by manually typing the command.

### P03 — Numbered nights exist internally but the complete loop is not guaranteed

**Observed:** `s.day` starts at 1 and increments in multiple branches of `close_vote()` and `send_to_interrogation()`. Interrogation is itself treated as a night. Morning can stall for a missing officer/decision, and there is no unified explicit “begin next night” operation shared by all branches. It would be incorrect to say that the code has no counter at all; the problem is consistency and liveness across branches.

**Fix:** Use a single monotonic round/night number and one entry point for starting a new night. Treat interrogation as a custody/session overlay on that night, not an additional uncounted night. All night effects, poison deadlines, evidence, custody counters, role findings, UI labels, and persisted state refer to that same number.

**Check:** Standard, no-vote, tie, acquittal, imprisonment, pause, and restart paths all show `شب ۱ → روز ۱ → شب ۲ → روز ۲ → شب ۳`. A jury never creates or skips a night. A duplicate callback cannot increment the counter twice.

### P04 — Interrogation still answers for the suspect

**Observed:** The newer `h_ask()` prompts for a question and returns a private response, which improves on the earlier public response. However `Game.ask()` still calls `dialogue.answer()` to fabricate a suspect response. Private output to the officer is not a real two-person conversation.

**Fix:** Officer sends a question; the actual suspect receives it inside the bot, writes a human answer, and the officer receives that answer. Scope the room to match/round/officer/suspect; deduplicate delivery and close it on lifecycle changes. Keep officer hints separate.

**Check:** An arbitrary human answer arrives unchanged at the officer, never at the group, and never at another table. Empty/failed answers do not become generated admissions.

### P05 — Prompt context can consume unrelated messages

**Observed:** `_PENDING` is keyed only by user ID and stores `(chat, command)`. `on_text()` pops it before checking whether the message has useful text; it does not verify the originating chat, prompt message, match version, role eligibility, or room/session. One prompt can overwrite another. A later ordinary group message can be consumed as an older private note/question/defense. Prompts are not durable.

**Fix:** Bind pending input to user, expected private chat, immutable match/session, originating prompt, command, expiry, and lifecycle version. Consume only after valid input; cancellation must work even with multiple active tables. Never intercept normal group conversation.

**Check:** A pending private note does not consume a group message. Switching tables, empty input, restart, suspect replacement, and cancellation leave no ambiguous context.

### P06 — Acknowledging an action does not prove the player received its effect

**Observed:** Night findings are appended to `p.notes`; `/notes` lets the player read them later. Start tells users to request `/myrole`; there is no complete guaranteed private fan-out for every new-night action panel and resolution. `_timer_job()` sends the tick text to the group rather than reusing the full manual dawn output/delivery workflow.

**Fix:** On each night start, privately deliver the assigned role's currently legal action panel. At resolution, queue relevant findings to the owner and a consistent public summary to the group. Mark explicit pending/failed delivery, with a private “view result” fallback. Do not expose outstanding role actors publicly.

**Check:** Both timer/manual resolution paths give the same effects and audiences. A detective does not need to guess that a silent note was created. Failed DM cannot become public role information.

### P07 — Terminal conditions and custody fallbacks can end too early or require impossible actions

**Observed:** `_check_win()` declares city victory whenever killer-team members are absent, even if a serial killer remains with city players. Officer special actions largely check identity without full life/custody checks. Suspect/office death and a verdict during jury lack a complete fallback. Rewards match translated string prefixes, which fails independent neutral victories.

**Fix:** Define explicit winner IDs/reasons and evaluate victory once after complete effect chains. Use a jury/procedural release fallback for an unavailable officer, close dead-suspect rooms, reject self-verdict, and prevent mutation after end. Follow the core/extended mode policy below.

**Check:** Night 2 and later continue while both hostile and non-hostile participants can still contest the game. End only for a valid terminal condition, never because a menu stopped offering actions.

## 4. Recommended player-controlled round specification

The following are concrete implementation defaults for Claude; the owner's requirement is phase voting, while the precise threshold/timeout policy is a proposed design choice documented here.

### 4.1 Separate phase readiness from accusations

1. After a ready lobby starts, announce **«شب ۱ آغاز شد»** and deliver private action panels. This first-night start is authorized by lobby readiness/start; it does not require a nonexistent preceding day.
2. Resolve Night N exactly once, then announce **«صبح روز N»**, public evidence/deaths, and private results. Complete any morning custody decision or its legal fallback.
3. Open public discussion. The day has **«آمادهٔ شب بعد هستم»** and **«هنوز گفتگو کنیم»** controls. The latter withdraws that player's readiness; it is not a veto against a achieved majority.
4. Eligible voters are current alive/free players (`can_vote` under the published rules); roles do not affect eligibility. The threshold is `floor(eligible / 2) + 1`. Re-evaluate safely if eligibility changes; never silently count a dead/removed voter. Display denominator and threshold.
5. Before the threshold, timers issue a visible reminder only; they do not force night, suspect voting, or a winner. Failure to reach agreement is a visible wait state, with host pause/cancel available—not fabricated progress.
6. Reaching the threshold closes discussion and opens the announced accusation ballot. Keep this a separate short stage, so players understand whether they are approving a phase or accusing a person.
7. The accusation ballot may nominate one suspect or end with no arrest under the documented tie/abstention rules. Its closure can start Night N+1 because a phase-consent vote for this day already passed. Record the link to that approved gate and consume it exactly once.
8. Start **one** Night N+1. If a suspect was nominated, attach the interrogation room/custody overlay to that same night. Do not increment again for an “interrogation night.”
9. At night, each role owner commits or passes their own action privately. A role without a night power receives a neutral “wait for morning” card; it does not receive someone else's ability.
10. Resolve at the pre-announced night deadline, or after all active participants use the same generic “ready for morning” interaction, if that early-close mode is enabled. Never let one player's naked `/dawn` cut off everyone else. Publish timing in advance; do not publish actual hidden-action completion counts.
11. Repeat until the terminal evaluator identifies a winner. Pause preserves both countdown and readiness/ballot state.

Only day-to-night consent is a strict owner requirement in this report. The proposed night-close deadline/generic-readiness choice should be visible in the lobby and consistent in rules/tests. Do not accidentally implement “everyone with a secret power has acted” as a public progress indicator.

### 4.2 Phase-vote edge cases

| Situation | Required response |
|---|---|
| 6 eligible, 3 yes | Remain in day |
| 6 eligible, 4 yes | Approve day end exactly once; open accusation ballot |
| 5 eligible, 3 yes | Approve day end |
| Same voter taps repeatedly | One approval, no extra weight |
| Player withdraws before approval | Remove approval; publish correct tally |
| Stale Day 1 button during Day 2 | Reject; no Day 2 mutation |
| Nonmember, dead player, prisoner, spectator | No phase vote unless specifically eligible under published rules |
| Timer expires with no majority | Reminder and visible wait; no forced transition |
| Majority and timeout arrive concurrently | One state change under the match lock/transaction |
| Voter eligibility changes | Recompute the live electorate/tally, show the changed threshold; don't silently inherit invalid votes |
| No eligible voters but no valid winner | Pause/recovery alert; never division-by-zero, silent night, or invented victory |
| Restart during day readiness | Restore approvals and gate identity, not a fresh hidden reset |
| No accusation votes or tied runoff | No arrest; begin the already-approved next night once |
| Unresolved morning suspect | Resolve verdict/jury/fallback before accepting a new discussion gate |

### 4.3 New conceptual interfaces Claude will need

These names are proposals, not current endpoints: `phasevote` (approve/withdraw), `phase_status` (public tally), `night_ready` (generic readiness), and a private `interrogation_reply` path. Do not claim they already exist.

Preserve compatibility carefully: `/vote` and `/castvote` remain suspect ballots; `/dawn` becomes a guarded request/status interface, not a bypass; `/tick` cannot grant phase approval. Keep explicit `match_id`, `round_id`, `phase_version`, gate approvals, and resolved-night identifiers in durable state.

## 5. Role-by-role activation plan

Use the display names in [role-names.md](role-names.md) without replacing canonical role IDs in stored state. Every row needs a legal menu, correct target type, server-side ownership check, action-budget check, real effect, and delivery acknowledgement.

| # | Display / canonical role | Private activation | Result and scope | Current issue / implementation instruction |
|---:|---|---|---|---|
| 1 | ردبین / کارآگاه | Choose player investigation OR evidence authentication | One private finding at resolution | Offer both options in own abilities; enforce shared budget and custody; persist prior-night target independently |
| 2 | رازپرس / بازجو | Open current suspect room; question; hints; post-night verdict/conditional release | Question to actual suspect; answer/hints to officer; only verdict public | Current generated reply is not human dialogue; add life/status/self/jury guards |
| 3 | اثرکاو / پزشک قانونی | Choose evidence ID, not player | Early concrete private lab result for that item | Current generic action target does not select the analyzed evidence; use evidence selector and preserve usefulness |
| 4 | جان‌بان / پزشک | Choose eligible other player | Protection/cure in resolver; safe private confirmation | Recheck previous-night restriction on every edit; specify poison cure window consistently |
| 5 | شب‌پای / نگهبان | Choose player to watch | Private observation/count with declared visit semantics | Current watcher observation excluded from visit count despite some text saying watchers visit; align ledger and wording |
| 6 | پرده‌گشا / خبرنگار | Select/confirm reveal action; no irrelevant player target | One new public clue plus owner acknowledgement | Not assigned in standard compositions; make selectable in a tested mode or label unavailable |
| 7 | دادخواه / وکیل | Request jury in eligible custody case | One petition forms jury under role privilege | Not assigned in standard compositions; don't equate generic `/jury` success with lawyer usability |
| 8 | هم‌محله / شهروند | No night power; public decisions, own notes/evidence | Clear “no night action” state; ordinary votes work | Avoid dead-looking action buttons and do not give a citizen another role's action |
| 9 | مرگ‌خوان / کالبدشکاف | Passive event subscription; “view findings” | Private actual cause/time window per death | Current fixed time/case weapon is inadequate for poison/hunter/linked deaths |
| 10 | واپسین‌تیر / شکارچی | Target selector before elimination | Stored final shot; trigger once on death or life jail | Naked `/hunter` button lacks selector; target cannot change after removal; life-jail trigger missing |
| 11 | خاموشگر / قاتل | Choose legal attack target | Attack at resolution, public death without premature role reveal | Preserve exclusive kill privilege; one agreed team attack if multiple killers are supported |
| 12 | ردساز / همدست | Choose frame target | Contestable trace/defined suspicious result | Label framing separately from killing; maintain finite duration and counter-evidence |
| 13 | زهرریز / سم‌ساز | Choose poison target | Delayed event tied to night number; cure rules visible | Keep deadline across restarts; recent source separates storm from poison, so re-test rather than reintroduce old fix |
| 14 | سایه‌شنو / خبرچین | Activate limited observation of actual officer activity | Private bounded metadata, never transcript | Current nominated suspect is already public; meaningful information must distinguish actual questioning |
| 15 | بلاگردان / سپر بلا | No night power | Solo objective triggered by life jail | Show objective privately; death/temporary jail is not its win |
| 16 | تنهاکُش / جانی سریالی | Independent target choice | Attack and explicit sole-survivor outcome/rewards | Prevent early city win while independent killer survives; don't infer reward from alignment-name prefix |
| 17 | پچ‌پچ‌فروش / بقال محله | Passive daily rumor; view latest | New private uncertainty-labelled rumor each day | Not assigned; no complete daily delivery mechanism; do not advertise reliability without generator/tests |
| 18 | ردپوش / قاچاقچی | Choose concealment target | Limited/inconclusive observation, not physical protection | Not assigned; define useful survival objective and result accounting |

### Core versus extended mode

The owner's central completion requirement is criminals versus the other group. Recommended implementation sequence: make the **core city-versus-criminal mode** complete and testable first, then explicitly enable neutral-objective roles in **extended mode**. Do not silently remove currently available neutrals or pretend their victory rules are ordinary city/criminal rules. Lobby descriptions and available compositions must show the chosen mode.

A neutral independent killer still alive prevents an ordinary city victory. A zero-survivor draw and simultaneous triggers need explicit precedence. Fix the complete effect pipeline before evaluating victory, not merely the displayed winner text.

## 6. Fix the entire ability lifecycle, not only buttons

For every action Claude should answer:

1. **Who sees it?** Only its owner, and only when available—or disabled with a precise reason.
2. **Who can invoke it?** Server revalidates owner, membership, role, phase, custody, life, pause, and match/version, even for hand-crafted callbacks.
3. **What is selected?** Player, evidence, suspect session, or no target. Do not route evidence/metadata powers through arbitrary player IDs.
4. **When is it spent?** One action per night where applicable. Editing a target is not a second action or a bypass for cooldown.
5. **What confirms commitment?** Private chosen-target acknowledgement, with legal edit/pass controls and the current night number.
6. **What actually resolves?** Structured event with actor, target, round, outcome/cause, and counters applied once.
7. **Who receives results?** Explicit private owner recipients and separately composed public events; read-only results are also reachable later.
8. **What if delivery fails?** Safe notice/retry; no group leak and no silent loss of acknowledged action.
9. **What if the player cannot act?** Clear reason; no stale clickable power. Passive roles still receive their rightful information.
10. **What if restart/phase change occurs?** Correct durable state; old buttons/pending prompts rejected or handled under their original valid session.

## 7. Shared endpoint defects to address centrally

- `handle()` touches the user before its exception guard: malformed/oversized IDs can raise outside normal error handling. Validate storage bounds before SQL.
- `handle()` does not consistently enforce bans/membership/phase/role itself; scattered handlers leave bypasses.
- `db.log_event(..., arg[:40])` stores the beginning of private notes/questions/answers. Metadata-only logging is needed for confidential input.
- Finalization flags precede durable result completion; retry/crash semantics need a transaction and immutable match result key.
- Callback data such as `act:4`, `verdict:1`, or `table:<id>` lacks immutable match/round context. A current selected table is not proof of an old button's intended game.
- Incoming private chat and actual match/group are not the same identity. Mutation lock/save target and message destination must be explicit, especially for links and parallel tables.
- New global menu commands are missing from the inspected `GLOBAL_CMDS`: `commands`, `group`, `roleinfo`, `cancel`. In multiple games, an ordinary navigation/cancel operation can be blocked by table ambiguity. Classify menu commands separately from gameplay commands.
- Timed result messages and direct command result messages diverge. Use common emitted events and recipient composition.
- Button “activation” cannot be fixed by removing guards. Correct menus must reflect rules, and rules must reject forged menu inputs.
- Name changes are presentation only. Use canonical IDs; string-prefix matching for win logic must be removed.

## 8. Consecutive review of every registered endpoint

Legend: **Change** = code observed conflicts with requirements or has a concrete gap. **Guard** = primary behavior exists but needs stronger context/permissions/lifecycle checks. **Keep/check** = no unique new defect established here; verify the listed contract. Shared defects in section 7 apply to every relevant row.

| # | Endpoint | Current behavior / problem | Claude's fix direction and acceptance check |
|---:|---|---|---|
| 01 | `/start` | **Guard:** menus plus join/readiness links mutate another match; incoming chat save/lock may miss target | Authenticate link context, persist/lock target match; join/ready must survive immediate restart |
| 02 | `/menu` | **Keep/check:** public main menu | No gameplay mutation or role disclosure; active match navigation should remain obvious |
| 03 | `/back` | **Guard:** same handler as menu, not necessarily prompt cancellation | Decide whether Back cancels the current prompt; no invisible pending input after navigation |
| 04 | `/new` | **Guard:** host can replace running game; lobby can be replaced by another user | Require explicit cancellation/restart action and fresh match identity; don't let a stray button discard a populated lobby |
| 05 | `/join` | **Guard:** `_ensure` may create a game and join current chat/table | Validate intended lobby, ban, capacity; duplicate joins cannot mutate; button must bind correct table |
| 06 | `/leave` | **Guard:** lobby-only leave and host transfer | Remove stale DB/prompt/readiness records; last departure closes lobby cleanly |
| 07 | `/startgame` | **Change:** no explicit host gate in handler; engine start can be repeated | Host-only and lobby-only; verified readiness, bounded case ID, private initial role/action delivery |
| 08 | `/myrole` | **Keep/check:** private role info for member | Correct match when in several; blocked DM never public; refresh must not reassign a role |
| 09 | `/night` | **Guard:** alias for action panel/submission, not phase transition | Retain compatibility; clearly label own action; never use as a day-to-night command |
| 10 | `/dawn` | **Change:** resolves immediately for caller | Replace bypass with guarded night-close readiness/status; only resolver closes a permitted night once |
| 11 | `/discuss` | **Change:** directly opens discussion | Enter only after valid morning decisions; no unauthorized caller, unresolved suspect, or double phase advance |
| 12 | `/vote` | **Change:** immediately opens suspect ballot | Keep accusation meaning; require approved day-end consent; do not confuse with new phase vote |
| 13 | `/castvote` | **Guard:** accepts target, replaces tally but appends history | One effective ballot, legal voter/target and round; duplicate votes don't farm rewards; stale callback rejected |
| 14 | `/closevote` | **Change:** closes immediately; `None` means both runoff and night but UI announces night | Authorized closure after ballot conditions; distinguish runoff/no-arrest/nomination; consume approved day gate once |
| 15 | `/hints` | **Guard:** officer ID check, private response | Require current living/free non-suspect officer and active room; hints never go to suspect/group |
| 16 | `/ask` | **Change:** prompts, then generates answer via engine; newer response is private | Relay question to actual suspect, preserve human answers, officer-only room entry before creating prompt |
| 17 | `/verdict` | **Guard:** selection UI precedes full officer validation; result after suspect cleared logs ID zero | Check authority/state first; forbid active-jury/self verdict; capture actual suspect ID before mutation; group gets public verdict |
| 18 | `/clear` | **Guard:** offers prisoners, then conditional release | Current eligible officer only; valid distinct new suspect; avoid exposing unavailable controls to outsiders |
| 19 | `/jury` | **Change:** petition before full eligibility validation | Validate member/life/custody, petition once, lawyer privilege, actual elapsed night; no outsider entry left behind |
| 20 | `/juryvote` | **Guard:** non-`1` input becomes false | Explicit yes/no/abstain parsing, eligible electorate, current jury version, one effective ballot |
| 21 | `/closejury` | **Change:** caller can close; percentage without turnout quorum | Enforce closure condition/quorum, correct phase return, no timer/phase approval bypass |
| 22 | `/status` | **Keep/check:** public board | Accurate day/night/custody, no private actions/roles; no hidden phase mutation |
| 23 | `/end` | **Guard:** ending report only while game object exists | Persist retrievable final result; explicit winner; repeated reads don't payout; complete group announcement at natural end |
| 24 | `/profile` | **Change:** reads current-game player XP rather than durable lifetime profile | Separate lifetime and match stats; work after end/restart; avoid silently showing reset totals |
| 25 | `/help` | **Change:** old progression instructions can contradict voted day-end | Rewrite around phase consent, own abilities, human room, numbered rounds and mode-specific wins |
| 26 | `/roles` | **Guard:** catalog includes unassignable roles | Show availability by mode/size, display/canonical names, precise ability limits; don't reveal assignments |
| 27 | `/share` | **Guard:** read-like command calls `_ensure` and can create/replace a game | Sharing should reference chosen lobby; explicit creation separately; avoid losing a finished result |
| 28 | `/sharelink` | **Guard:** uses incoming chat ID for invite | Generate actual match-bound link, not unrelated private chat; expired/wrong-table links fail safely |
| 29 | `/admin` | **Keep/check:** default-deny admin check | Retain deny for empty list; no implicit gameplay powers |
| 30 | `/admin_games` | **Guard:** recent game query can include finished rows | Distinguish active/finished/abandoned and immutable matches; keep admin destination private |
| 31 | `/admin_users` | **Guard:** administrative user details and events | No raw private text in ordinary history; limit output/paginate; prevent public group delivery of user details |
| 32 | `/admin_stats` | **Guard:** aggregates depend on current DB model | Count distinct matches, not group IDs; consistent result states and private moderation audience |
| 33 | `/admin_ban` | **Change:** stores a flag, central gameplay enforcement missing | Validate target and enforce ban on every mutating entry point; never show success with continued unrestricted play |
| 34 | `/tick` | **Change:** scheduled logic advances without day consent | Timer may remind/open approved stages, never synthesize phase votes; idempotent trusted-system transition path |
| 35 | `/dashboard` | **Change:** phase controls include direct advance commands | Show phase-vote tally, round, legal next step; no bypass buttons or private activity inference |
| 36 | `/defense` | **Guard:** prompts then public text; current suspect check only | Validate before prompt; deliberate public preview/confirm, bounded text, no private-room transcript auto-publication |
| 37 | `/will` | **Guard:** pending text and mutation for any member status | Private match-scoped prompt, alive/free edit policy; publish only actual will after actual permitted death event |
| 38 | `/note` | **Guard:** pending text and unbounded note count | Own private input only; quotas, safe escaping, no raw audit logging, no accidental group message consumption |
| 39 | `/notes` | **Change:** one unbounded joined response | Paginate findings/notes; show night/event result delivery status; no permission to read another player's notes |
| 40 | `/sos` | **Guard:** distinct emergency detention vote, weak phase/lifecycle rules | Keep separate from phase consent; one use, current eligibility/threshold, no post-game or paused mutations |
| 41 | `/lab` | **Change:** no member gate; selector includes all evidence and result is generic | Shared eligible-player revealed-evidence queue; concrete result, role-specific early access separately; correct due night |
| 42 | `/interp` | **Change:** outsider can inspect/vote; all-card menu exposes unrevealed items | Enforce visible evidence and eligible membership; tally replacement and target-bound callbacks |
| 43 | `/expose` | **Guard:** no-argument selector appears before role check; engine custody gap | Only detective's eligible alternative action, same budget as investigation, proper result timing, restricted evidence access |
| 44 | `/top` | **Keep/check:** public leaderboard | Durable, correct winner/XP accounting; bounded names/output and pagination |
| 45 | `/league` | **Guard:** grouping by chat/player snapshots can misrepresent history | Aggregate immutable completed match records; parallel tables correctly attributed to parent group |
| 46 | `/season` | **Keep/check:** monthly XP | Exactly-once credit, documented season boundary, no manual score inflation via repeated actions |
| 47 | `/missions` | **Keep/check:** private progress | Correct eligibility and once-per-period reward; no private action details exposed |
| 48 | `/achv` | **Guard:** achievements and accuracy rely on defective reward history | Final ballots only, explicit neutral wins, same totals after restart |
| 49 | `/newtable` | **Change:** synthetic IDs double as game/chat IDs; actual target match may not be saved | Separate logical table ID from Telegram destination; bind join/buttons/timers/persistence to correct table |
| 50 | `/spectate` | **Guard:** copies recent log lines | Public-event projection only; exclude room, private notes, hidden action actors and speculative sensitive metadata |
| 51 | `/voteanon` | **Guard:** owner toggles at any time | Lobby-only setting or next-round effect; never revoke anonymity halfway through a ballot |
| 52 | `/rematch` | **Guard:** in-memory roster and reusable deterministic seed | Fresh match/seed, verify participants/readiness, persist previous roster if supported, no silent overwriting |
| 53 | `/rolecard` | **Guard:** private image depends on Pillow/font rendering | Correct own role and Persian display name; graceful dependency/font failure, safe temp-file lifecycle |
| 54 | `/tutorial` | **Change:** static text/buttons are not an interactive practice match | Teach new phase vote and activation cycle; optional isolated practice with no live state mutation |
| 55 | `/blitz` | **Guard:** creates shorter game, still direct replacement path | Same permissions/consent and role rules; halve published timings consistently without skipping night numbers |
| 56 | `/hunter` | **Change:** `int(arg)` on naked button; no target selector; actor status gap | No-arg opens legal own target selection; commit only while eligible; freeze after elimination, fire once |
| 57 | `/table` | **Guard:** pins current match in memory; ended selection may persist | Validate membership/lifecycle; explicit selection UI; never reinterpret an old callback using new selection |
| 58 | `/act` | **Guard:** own role panel partly correct but targets don't fit every ability | Use unified capability policy and target types; show round/commit status, passive-role explanation, no unrelated ability |
| 59 | `/ready` | **Guard:** membership-based ready flag does not prove private delivery | Verified private flow; persist target lobby; prevent group/forged ready from granting reachability |
| 60 | `/remind` | **Keep/check:** newer night reminder is generic, improving secrecy | Retain no hidden actor names/counts; daytime reminders distinguish phase-consent voters from accusation voters |
| 61 | `/pause` | **Guard:** host-only, but mutation endpoints may keep working | Freeze votes/actions/room entry; retain time/phase gate; do not clear committed choices |
| 62 | `/commands` | **Guard:** global button directory not classified global in routing | Available without forced table selection; show catalog vs currently usable commands distinctly |
| 63 | `/group` | **Guard:** menu category browsing can be blocked by multi-game routing | Global navigation; category does not confer its role/admin powers |
| 64 | `/roleinfo` | **Guard:** integer index allows negative indexing and catalog scope unclear | Validate nonnegative range/stable role ID; global read-only; label unplayable modes |
| 65 | `/abilities` | **Change:** descriptions and keyboard differ; absent officer/detective alternatives | Own role + actual phase/status policy drives both; every intended action reachable, disabled reasons accurate |
| 66 | `/cancel` | **Change:** keyed to one user's pending tuple; can be blocked by ambiguous table routing | Global cancellation of explicit selected prompt/session; no accidental match cancellation |
| 67 | `/resume` | **Guard:** zero remaining time treated as absent | Restore exact remainder and readiness votes; due-zero resolves only through permitted gate, not permanent clock loss |
| 68 | `/host` | **Guard:** takeover/selector can be requested by outsider when old owner unavailable | Require current eligible member; explicit transfer/takeover event; no added role knowledge |
| 69 | `/balance` | **Keep/check:** admin aggregate outcomes | Use enough samples and correct outcome IDs; report uncertainty/abandonment; do not claim balance from test count alone |

Coverage note: these are registered application commands, not HTTP routes. Check both direct commands and their callback aliases. The same handler reached by a menu must enforce the same rule.

## 9. Adapter and background paths that are not ordinary endpoints

| Path | Finding / fix direction |
|---|---|
| `_dispatch` | Resolve immutable callback/session context before selected table; classify new global menu/cancel commands correctly |
| `make_cmd` | A private administrative phase request may need a separate group announcement; don't use incoming chat as every output destination |
| `on_callback` | Verify callback version, membership and original match; handle missing/deleted messages; answer spinner safely; dedup actual updates rather than blocking valid target edits |
| `on_text` | Do not consume a private prompt with unrelated group text; validate context before popping; no silent prompt loss on blank/expired/invalid input |
| `_reply` | Preserve failed-DM no-content fallback; add explicit recipients/pagination; protect log output from private text and token-bearing exception strings |
| `_send_photo_or_voice` | Correct intended destination per event; image dependencies/fonts; clean temporary files; do not voice-announce a phase that didn't validly change |
| `_timer_job` | Never bypass phase-consent vote; emit complete shared resolution events with consistent public/private delivery, not only a short tick message |
| `_post_init` | Restore games, gates, pending safe deliveries and room state; one ready announcement per restored match where needed |
| `main` | Requires real readiness policy and scheduler capability; newer warning when JobQueue missing is useful, but declared dependencies still must support the selected mode |
| `handle` | Shared authorization/validation/transaction/event output; no private raw argument logging; verify every mutation only after permission |
| `_guard_replace` | Guard the populated lobby as well as active match; record abandonment only after an explicit accepted cancellation |
| `_ensure` | A read/share action must not silently create a match or replace an ending; make creation explicit |
| `_PENDING`/`_ACTIVE_TABLE`/dedup caches | Bound and expire; game/session-aware cancellation and restore policy; no cross-match prompt overwrite |

## 10. Night-number and end-condition acceptance scenarios for Claude

These are instructions for later tests; no new tests are added or run in this report-only step.

| ID | Journey | Required observation |
|---|---|---|
| LOOP-01 | 4-player start → Night 1 → Day 1 → phase majority → no arrest → Night 2 → Day 2 → Night 3 | Exactly increasing round labels; real private action panels each night |
| LOOP-02 | Day-consent vote remains below threshold while timers expire | Day stays open; reminders only |
| LOOP-03 | Majority → suspect ballot → interrogation overlay | One increment into next night; no separate duplicate night |
| LOOP-04 | Tied suspect vote → runoff → second tie | Fresh runoff UI/time; next night only under the existing approved gate |
| LOOP-05 | Suspect acquitted after interrogation night | Continue that day's morning/discussion; do not repeat prior night |
| LOOP-06 | Temporary jail for required subsequent nights | Count real resolved nights once; life jail at correct threshold |
| LOOP-07 | Poison on Night 1, Night 2 survival, due Night 3 | Correct effect/cure and night labels even if Night 2 is interrogation |
| LOOP-08 | Officer killed or becomes suspect | Legal fallback; no dead officer action or self-verdict required to progress |
| LOOP-09 | Pause day readiness or night after choices committed; restart; resume | Saved votes/choices/time survive; no forced or duplicate phase |
| LOOP-10 | Same update delivered twice during phase-majority crossing | One approval, one night increment, one public announcement |
| LOOP-11 | Player has two active tables and presses an old ability button | Original table/session or safe rejection; never another table's action |
| LOOP-12 | Criminal win after multiple nights | Explicit valid terminal condition, public reason/roles, one durable payout |
| LOOP-13 | City win after multiple nights | No active criminal or independent hostile remains under chosen mode |
| LOOP-14 | Serial killer survives after criminal team removed | Continue extended mode; do not prematurely award city |
| LOOP-15 | Everyone dies / independent triggers overlap | Published precedence/draw; deterministic one-time result |
| LOOP-16 | Blocked DM during role/action/result delivery | Clear safe recovery; no role leak; no false claim recipient received it |
| LOOP-17 | Full officer question and human answer in bot | Both correct private recipients; group sees only deliberate public defense/verdict |
| LOOP-18 | All roles at least once in a supported mode | Ability reachable without typing IDs, correct target/effect/result, other roles denied |

Also retain the broader permission, overflow, evidence and regression matrix from [improvement.md](improvement.md). Modify older tests whose expected auto-progression conflicts with the new phase-consent requirement; explain that requirement change instead of silently deleting coverage.

## 11. Implementation sequence and completion criteria

1. **Agree data/state boundaries first:** match/round/phase identity, phase-consent ballot versus accusation ballot, interrogation overlay, explicit winner IDs.
2. **Repair central progression:** approved day gate, guarded night resolution, single counter increment, no timer bypass, legal missing-officer/suspect fallback.
3. **Repair authorization and menus together:** shared capability policy, target types, own-only private action panels, guards on both commands and callbacks.
4. **Repair delivery and human rooms:** explicit recipients, actual two-person messages, scoped pending input, durable safe results/retries.
5. **Complete role effects and information value:** every selectable role meaningful, no fixed fake-card positions, useful forensics and accurate traces.
6. **Repair persistence and ending:** transactional completion, saved summaries, safe restart, correct repeated-match state.
7. **Run existing and updated contracts, then full playtest:** test every endpoint through direct command and button, and run LOOP-01–18. Report failed, skipped, and untested scenarios separately.

Do not mark a role fixed merely because its handler returns `ok=True`, or mark the game loop fixed because a counter changed in one branch. Completion means real players can see what to do, commit only their legal action, receive its result, approve the next night, and finish a multi-night match without administrative rescue or secret leakage.

## 12. GitHub handoff notes

- Treat this as a review/remediation task, not a release-ready “all bugs fixed” change.
- Preserve unrelated work already present in the checkout. Use an audit/documentation commit separately from Claude's gameplay fixes.
- Recommended review work items: (1) voted phase progression, (2) own-role capability UI/policy, (3) human interrogation room, (4) round/winner/persistence correctness, (5) evidence usefulness and full endpoint acceptance.
- Claude should cite endpoint numbers and LOOP IDs in its PR description, show old/new behavior, and attach test results from its actual final revision.
- Do not upload `.env`, live databases, private transcripts, or token-bearing logs.
- Do not merge/deploy simply because the older test suite passes: its automatic-progression assumptions must be updated for the owner's latest playtest requirements.
