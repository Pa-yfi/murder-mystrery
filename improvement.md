# Karagah: gameplay scenarios, quality requirements, and improvement plan

Date: 2026-09-20

## Status and scope

**Scenario documentation was completed first. The owner subsequently requested regression testing, edge-case/overflow checks, leak checks, evidence/role review, a rules document, and Persian role names. An offline test subset has now been implemented and executed.** The final recorded run has 184 existing tests passed, one existing skip, and 1,262 new checks passed / 63 failed cases. This document remains the wider scenario specification; it does not claim every listed scenario has been automated or passed.

Current deliverables: [rules.md](rules.md), [evidence-and-roles.md](evidence-and-roles.md), [role-names.md](role-names.md), and [audit-results.md](audit-results.md). The results document and hashed snapshot supersede preliminary source observations below wherever the implementation changed during this session.

The checkout was being edited during inspection. Changes were observed in `karagah/engine.py`, `models.py`, `bot.py`, `telegram_app.py`, and `ui.py`. Those edits were preserved. An initial existing-suite invocation encountered seven collection errors from a transient unterminated string in `bot.py`; that was superseded by a successful existing-suite run on the final snapshot. Tests now exist under `tests/quality/`. No live Telegram acceptance test has been performed and the production bot was not deployed or started by this audit.

Reviewed areas: role catalog and assignments, state transitions, night resolution, custody and juries, command handling, Telegram routing and delivery, UI, persistence, evidence generation, and existing test organization. Findings below are **source-review observations requiring rechecking against a stable revision**, unless explicitly described otherwise.

“All possible scenarios” cannot mean every unbounded sequence of messages, random outcome, concurrent update, and restart. The achievable commitment is: complete coverage of the finite authorization matrix, every supported phase transition, every advertised role, all 40 cases, all supported lobby sizes, identified interaction boundaries, and repeatable generated game sequences. Report remaining gaps instead of calling a sampled run exhaustive.

## 1. Required behavior and boundaries

| Requirement | Expected behavior |
|---|---|
| Role permissions | A player can perform only the capabilities granted to their role, current phase, custody, and life status. Server-side checks apply even if buttons are hidden. |
| Identity | The actor comes from the authenticated Telegram update; never from a callback's user ID or message text. |
| Private information | Roles, night choices, private notes, role findings, and interrogation messages are delivered only to authorized recipients. Failed DMs never become public content. |
| Human interrogation | The officer asks the actual suspect through the bot. The suspect writes their own answer through the bot. Scripted dialogue must not impersonate the human suspect. |
| Game isolation | Every action and private conversation is bound to a specific match, round, and phase/session. Switching tables cannot redirect an old action. |
| Invalid commands | Deny clearly and leave state unchanged. Do not return an internal error for ordinary invalid input. |
| Host authority | Host powers control the session; they do not grant another role's abilities or secret information. |
| Administrator authority | Admin powers moderate the service. They do not silently grant gameplay abilities or access to confidential conversations. |
| Persistence | Acknowledged actions survive restart; results and rewards are recorded exactly once. |
| Game completion | Completed matches have a retrievable result and bounded retention. No new gameplay mutation is accepted after completion. |
| Pause | Timers and gameplay mutations stop; resume restores the saved remaining duration. Read-only help and own notes remain available. |
| Evidence | Public and private evidence are distinguishable, results are meaningful, and revelation is consistent across manual and timed transitions. |

### Rules to settle before treating tests as authoritative

These are proposed defaults where the code or role descriptions leave ambiguity. They are not established product decisions.

| Decision | Proposed default / question to resolve |
|---|---|
| Night order | Validate committed actions, apply hiding/framing/protection, determine attacks and poison, resolve chained deaths, advance custody, compute findings, then evaluate victory once. Specify whether actors killed that night still complete actions. |
| Storm and poison | A storm cancels direct attacks; it should not silently erase already-mature poison. Decide whether poison still kills or is delayed. |
| Protection and poison | Specify whether protection cures existing poison before maturity, only on the due night, or also prevents new poisoning. Match the public rule text. |
| Framing and hiding | Define precedence if both affect a target and the exact lifetime of the frame. |
| Investigation | One information-bearing action per night; changing the committed target before resolution is allowed. Specify consecutive-night target restrictions. |
| Multiple killer-team members | Decide whether the team has one collective kill or individual attacks; the serial killer remains independent. |
| Hunter | Description promises a shot on death or life imprisonment. Apply once, using a previously committed valid target; define what protection can block. |
| Fate pair | Define death versus imprisonment propagation and interactions with hunter chains. |
| Officer unavailable | Define a replacement officer or a jury-led fallback when the officer dies/is imprisoned; the match must not require actions from an eliminated player. |
| Officer becomes suspect | No self-interrogation/self-acquittal. Use the jury or an explicitly designated replacement. |
| Serial killer alive | Do not declare city victory solely because the killer team is gone while an independent killer remains. Specify parity rules involving neutrals. |
| Smuggler victory | Decide whether survival is an additional individual victory alongside the winning faction. |
| Jury | Define eligible petitioners, minimum quorum, denominator for the 60% threshold, abstention, ties, timeout, and whether the suspect can petition. |
| No players survive | Choose and document a draw or another deterministic result. |
| Repeated questions | Human messages are preserved; automatic “contradiction” claims should not be inferred merely from a generated response changing. |
| Officer/suspect privacy | Closed two-person room by default. Public defense is a separate explicit action, not an automatic publication of the transcript. |
| Text and media | Initially support bounded plain-text interrogation. Reject unsupported media politely; add media only with explicit rules. |
| Seed selection | Reproducible seeds in tests; unpredictable per-match seeds in production. Avoid repeating assignments merely because a group ID is unchanged. |

## 2. Complete role capability matrix

The current catalog contains 18 roles. Authorization must be tested against every other role, not just one representative wrong role.

| Role | Alignment | Intended ability/access | Required positive scenario | Required negative scenario |
|---|---|---|---|---|
| کارآگاه — Detective | City | Investigate a player; authenticate evidence as an alternative night action | Receive one private finding after the committed action resolves; framing/hiding affect the agreed result | Cannot use both alternatives that night; cannot kill, protect, or act in custody |
| بازجو — Officer | City | Private questioning, ambiguous hints, verdict, conditional release | Converse with the current human suspect; issue a verdict after the required night | Other roles cannot read hints or issue verdicts; dead/imprisoned officer cannot exercise authority |
| پزشک قانونی — Forensic specialist | City | Early laboratory information about evidence | Select an evidence item and receive its actual result privately | Cannot acquire unrelated investigative powers; player-target UI must not substitute for evidence selection |
| پزشک — Doctor | City | Protect and cure under the agreed poison rules | Protection prevents the defined attacks; valid cure clears poison once | Cannot protect self or bypass the consecutive-target rule by first selecting someone else |
| نگهبان — Watcher | City | Observe visits to a chosen player | Accurate count under the agreed visit definition; hiding handled consistently | Cannot see visitor roles/identities unless explicitly designed; no unrelated private findings |
| خبرنگار — Reporter | City | Reveal an extra public evidence item | Additional unique evidence is visible to the group | Cannot reveal secret roles or repeatedly expose the same item as new evidence |
| وکیل — Lawyer | City | Trigger a jury with one eligible petition | One lawyer petition forms a jury after the required custody time | Ordinary players still need the configured petition count; lawyer cannot issue the officer's verdict |
| شهروند — Citizen | City | Discussion, eligible voting, shared public features | Can participate in public decisions while eligible | Cannot submit a night power or read role findings belonging to others |
| کالبدشکاف — Coroner | City | Private death time and weapon/cause information | Receives meaningful findings for actual deaths, including multiple causes | No report when nobody dies; no access to unrelated roles; eliminated coroner has no new active power |
| شکارچی — Hunter | City | Preselect a final-shot target; trigger on death or life jail | Exactly one final shot for each permitted elimination trigger | Cannot retarget after elimination or fire repeatedly; cannot shoot self |
| قاتل — Killer | Killer team | Attack; know authorized teammates | Legal target dies unless a specified counter applies | Cannot self-kill or gain doctor/detective powers |
| همدست — Accomplice | Killer team | Frame a player; know authorized teammates | Frame affects the promised evidence/investigation for the documented duration | Cannot convert framing into a direct attack or permanently corrupt later findings |
| سم‌ساز — Poisoner | Killer team | Delayed poisoning; know authorized teammates | Target survives early nights, dies when due unless cured | No early death, duplicate death, or unintended deadline reset through repeated poisoning |
| خبرچین — Spy | Killer team | Learn whom the officer interrogated | Private target report; explicit no-interrogation result | Cannot read the entire transcript, hints, or suspect's notes |
| سپر بلا — Scapegoat | Neutral | Solo victory on life imprisonment | Life imprisonment triggers the documented victory once | Ordinary death or temporary jail does not grant this victory |
| جانی سریالی — Serial killer | Neutral | Independent attack; win as sole survivor | Continues contesting the game after killer-team elimination; receives correct victory/rewards | Cannot win merely through killer-team parity; other neutrals do not receive its power |
| بقال محله — Grocer | Neutral | Daily private rumor with advertised reliability | New eligible daily rumor; statistical reliability tested across controlled seeds | Cannot expose guaranteed truth or receive other roles' findings |
| قاچاقچی — Smuggler | Neutral | Hide a target from investigation/watch; survival objective | Both concealment effects apply and survival result is recorded correctly | Cannot acquire attack/protect powers; concealment expires as specified |

### Matrix dimensions

For each applicable role capability, cover:

- Every other role attempting that capability, plus an outsider, spectator, banned user, host, and administrator.
- Lobby, night, morning, discussion, voting, interrogation, jury, final court if supported, and completed match.
- Alive/free, under interrogation, temporary jail, life jail, and dead; paused as an additional independent condition.
- Valid target, self, teammate, opponent, neutral, dead target, jailed target, unknown ID, another game's ID, and missing target.
- Command, inline callback, private message, group message, stale button, edited argument, and duplicate update.
- Before the deadline, exactly at the deadline, after the deadline, after restart, and during concurrent timer processing.

Do not blindly multiply combinations without meaning. Generate all applicable authorization cases and explicit boundary/interaction cases; document exclusions. For denied actions assert **no mutation, no secret disclosure, no reward, and no delivery to another person**, not just `ok == False`.

## 3. Private officer–suspect conversation specification

### Proposed flow

1. A valid vote identifies the suspect. Create an interrogation session tied to immutable `match_id`, round, officer ID, and suspect ID.
2. Send each participant a private room invitation. The group receives only the public custody announcement and timing.
3. The officer sends a question in the bot. The bot acknowledges receipt and relays the exact escaped text to the current suspect.
4. The suspect replies inside the bot. The bot relays that human-authored answer to the current officer and acknowledges receipt to the suspect.
5. Bind messages/replies to that session. Selecting another table does not reroute replies from the old room.
6. Keep role hints separate from the transcript. The suspect and group cannot request the officer's hints.
7. On verdict, release, death, session replacement, or game completion, close the room and reject later messages for it. Define pause and jury behavior explicitly.
8. A failed delivery leaves the message pending/failed with a safe sender notice. Never publish the text to the group. Deduplicate retry delivery.
9. Public defense uses a separate clearly labelled action and preview. Do not publish private answers automatically.
10. Persist enough state to restore room membership and pending deliveries after restart. Use a defined retention/deletion policy for transcripts.

### Conversation acceptance scenarios

| ID | Scenario | Required result |
|---|---|---|
| MSG-01 | Officer sends a question in an active room | Only the current suspect receives the exact question; officer receives an acknowledgement |
| MSG-02 | Suspect replies with arbitrary human text | Only the officer receives the reply; no generated substitute answer |
| MSG-03 | Officer asks the same question twice intentionally | Two distinct messages remain distinguishable; duplicate update delivery is still deduplicated |
| MSG-04 | Third player invokes room commands or guesses a session ID | Access denied; no transcript, participants' private metadata, or message content disclosed |
| MSG-05 | Host/admin who is not a participant attempts access | No implicit room access |
| MSG-06 | Officer/suspect belongs to two games | Session context selects the correct game without cross-delivery |
| MSG-07 | Player switches `/table`, then replies to an older room prompt | Reply stays bound to its original session or is explicitly rejected; never silently redirected |
| MSG-08 | Previous suspect replies after a new suspect is selected | Old room is closed; new suspect/officer room receives nothing |
| MSG-09 | Officer or suspect dies/is permanently removed | Session closes or transitions under the documented replacement rule |
| MSG-10 | Game pauses, enters jury, ends, or restarts | Allowed communication follows the documented lifecycle; no stale messages become new actions |
| MSG-11 | Recipient never started bot, blocked it, or delivery times out | Safe acknowledgement/error; content never reaches group; retry state is explicit |
| MSG-12 | Telegram delivers the same update twice | Exactly one transcript entry and one recipient delivery |
| MSG-13 | Process crashes after storing a question but before sending it | Pending delivery resumes without loss or duplication |
| MSG-14 | Markdown, Persian punctuation, RTL text, emoji, newline, or mention | Text remains readable and cannot alter routing or expose bot metadata |
| MSG-15 | Empty, over-limit, unsupported media, or forwarded input | Clear validation result; no partial mutation or accidental public forwarding |
| MSG-16 | Suspect chooses public defense | Only the explicitly selected defense is public; private transcript remains private |
| MSG-17 | Spectator checks status/log/reconstruction during play | Cannot retrieve room transcript or private hints |
| MSG-18 | Retention period ends or match is deleted | Transcript cleanup follows policy while preserving only required aggregate results |

Suggested implementation: a message envelope with `match_id`, `session_id`, `message_id`, authenticated sender, authorized recipient, visibility, and delivery state. Store pending delivery with the state change in one transaction. Do not use a global “last suspect” or the user's current selected table as the sole routing key.

## 4. Functional and gameplay scenario catalog

Each row below becomes one or more tests after the related implementation is stable. IDs are traceability labels, not passing-test counts.

### Lobby, readiness, and host controls

| ID | Scenario | Expected result |
|---|---|---|
| LOB-01 | Create and join a fresh lobby | Unique membership; creator is host; correct group/match identity |
| LOB-02 | Start with 3, 4, 10, and 11 players | Reject out-of-range counts; accept supported boundaries with ready players |
| LOB-03 | Join twice or join a full lobby | Clear rejection without duplicate state |
| LOB-04 | Join after start | Clear rejection; current roles and state unchanged |
| LOB-05 | Readiness from private onboarding | Mark ready only after the required private interaction/delivery verification |
| LOB-06 | Fake readiness from a group command or callback | Cannot claim private reachability without the documented verification |
| LOB-07 | One player not ready | Start is blocked with an actionable name list |
| LOB-08 | Force start | Only authorized host can override readiness; consequences explained |
| LOB-09 | Non-host starts/restarts via `/startgame`, `/new`, `/blitz`, `/rematch` | Session-control policy enforced consistently |
| LOB-10 | Start an already started match | Reject; do not reassign roles or reset day counters |
| LOB-11 | Host leaves lobby; last player leaves | Transfer host or close empty lobby; no abandoned ownership |
| LOB-12 | Host absent/dead and another player requests transfer | Explicit takeover rule; outsider cannot choose host |
| LOB-13 | Invalid case ID: negative, zero, 41, text, huge integer | Document default versus rejection; no accidental negative indexing |
| LOB-14 | Repeated games in the same group | New match identity, fresh randomness, clean state, preserved history |
| LOB-15 | Invite/deep-link join followed immediately by restart | Joined player survives in the correct saved lobby |
| LOB-16 | Blitz game | Displayed and actual phase/custody durations agree |

### Night resolution and role interactions

| ID | Scenario | Expected result |
|---|---|---|
| NGT-01 | Valid action by each active role | Correct committed ability and target; no unrelated capability |
| NGT-02 | Change target before deadline | One final action; no repeated information or reward |
| NGT-03 | Invalid actor/target/status/phase | Deny and preserve state |
| NGT-04 | Two killers attack same target | One death, one death event, one will, one applicable cascade |
| NGT-05 | Doctor protects direct-attack target | Target survives under the agreed rules |
| NGT-06 | Doctor selects an allowed target then edits to last night's protected target | Consecutive-target restriction still applies |
| NGT-07 | Detective revisits previous night's target after actions were cleared/restarted | Cross-night restriction, if retained, survives both operations |
| NGT-08 | Detective investigates then exposes, and exposes then investigates | Cannot consume both powers that night |
| NGT-09 | Frame, hide, and investigate same target | Defined precedence; one private result |
| NGT-10 | Frame expires | Innocent target stops appearing framed at the documented boundary |
| NGT-11 | Hide plus watch | Hidden target's visits are treated according to the published rule |
| NGT-12 | Multiple visitors, watcher self-target, watcher visits another watcher | Count matches the explicitly documented visit definition |
| NGT-13 | Poison application, intermediate night, due night | Delay measured in actual nights, including interrogation nights |
| NGT-14 | Poison protected early, on due night, or repeatedly poisoned | Cure and rescheduling follow the settled rule |
| NGT-15 | Poison target dies or enters life jail before due night | Queue cleanup without duplicate death or effect on another target |
| NGT-16 | Storm with attack and mature poison | Storm behavior does not silently consume poison contrary to the rule |
| NGT-17 | Hunter killed directly, by poison, or through a fate pair | Last shot triggers once and resolves its chain correctly |
| NGT-18 | Hunter enters life jail | Promised last shot occurs once |
| NGT-19 | Hunter shoots a member of a fate pair | All required secondary deaths occur, without cycles/duplication |
| NGT-20 | Hunter target already dead or also attacked | No duplicate elimination or incorrect reward |
| NGT-21 | Reporter plus witness event on the same night | Distinct valid evidence; no duplicate reveal count |
| NGT-22 | Forensic specialist selects E1 versus E2 | Requested evidence determines the result; no irrelevant player selection |
| NGT-23 | Coroner with no death, one death, and mixed-cause deaths | Reports match actual events, not one hard-coded cause/time |
| NGT-24 | Spy with no suspect, active suspect, and replaced suspect | Sees only the permitted current target information |
| NGT-25 | Grocer across several days and many fixed seeds | Daily rumor freshness and specified reliability |
| NGT-26 | Actor eliminated during the same night | Committed action completes or cancels consistently with the chosen order |
| NGT-27 | No player submits an action | Night advances once; absence handling does not reveal hidden role membership |
| NGT-28 | Read same findings twice | No new result generation, XP, or duplicate notifications |

### Voting, custody, officer, and jury

| ID | Scenario | Expected result |
|---|---|---|
| VOT-01 | Eligible vote and replacement vote | One effective vote per voter |
| VOT-02 | Self-vote, outsider vote, dead/jailed vote | Enforce eligibility and preserve tally on rejection |
| VOT-03 | No votes, unique leader, first tie, second tie | Correct branch, phase, and next action |
| VOT-04 | Runoff begins by command or timer | Fresh deadline, correct runoff message, valid candidate restriction |
| VOT-05 | Vote after closing/deadline or stale callback | Rejected; no retroactive tally change |
| VOT-06 | Repeatedly vote for same killer | Final ballot counts once for accuracy/XP; no farming |
| VOT-07 | Anonymous vote | No voter-to-target mapping appears publicly or in spectator output |
| VOT-08 | Switch anonymity during an active vote | Explicit policy; prior anonymity promises are respected |
| CUS-01 | Vote leads to interrogation, then one real night passes | Correct suspect, custody counter, phase, and day |
| CUS-02 | Officer attempts an early verdict/jury requested too early | Denied until required night(s) elapsed |
| CUS-03 | Other eligible players act during interrogation night | Their ordinary powers work; suspect cannot use an ordinary night power |
| CUS-04 | Dead, jailed, or replaced officer invokes hints/ask/verdict/clear | Denied; role ID alone is insufficient |
| CUS-05 | Officer is the suspect | No self-acquittal; documented fallback works |
| CUS-06 | Suspect dies overnight | Stale custody/session state cleared; match remains playable |
| CUS-07 | Release versus temporary jail | Correct custody, counters, pending queue, and public announcement |
| CUS-08 | Two actual nights in temporary jail | Life imprisonment at exact threshold, without premature role reveal |
| CUS-09 | Officer clears previous prisoner without/with a new suspect | Conditional-release rule enforced |
| CUS-10 | Start new discussion/vote while verdict unresolved | Explicitly reject or resolve; never strand an old suspect |
| CUS-11 | Defense from current suspect versus unrelated player | Only authorized suspect submits; private/public destinations are explicit |
| JUR-01 | Two ordinary eligible petitions | Forms exactly one jury |
| JUR-02 | One eligible lawyer petition | Forms jury through lawyer privilege |
| JUR-03 | Duplicate, outsider, dead, jailed, or ineligible petition | No extra weight, invalid stored petition, or phase change |
| JUR-04 | 59%, exactly 60%, above 60%, no votes, and abstentions | Documented threshold and quorum followed |
| JUR-05 | Acquittal versus refusal | Return to correct daytime state; do not repeat the night |
| JUR-06 | Officer verdict while jury is active | Cannot corrupt the jury or clear its suspect unexpectedly |
| JUR-07 | Repeat jury request for same custody episode | Limit enforced; define whether a later new episode resets eligibility |
| JUR-08 | Jury deadline and restart during jury | Progress without permanent stall or loss of ballots |
| SOS-01 | Below/exact/above emergency-vote threshold | Single result at defined eligible-population denominator |
| SOS-02 | Supporter later dies, withdraws, or switches target | Stale support cannot be counted as a currently eligible vote |
| SOS-03 | Emergency vote in lobby, end, pause, or against invalid target | Rejected without disturbing ordinary custody |

### Endings, rewards, persistence, and routing

| ID | Scenario | Expected result |
|---|---|---|
| END-01 | Last killer-team member eliminated, no hostile neutral | City wins with full reveal and correct rewards |
| END-02 | Killer parity | Correct faction result under the settled neutral rules |
| END-03 | Serial killer alone | Serial killer recorded as winner in game, profile, season, and achievements |
| END-04 | Killer team eliminated while serial killer and city survive | Match continues unless explicitly different rules are adopted |
| END-05 | Scapegoat life jail versus ordinary death | Solo victory only for the documented trigger |
| END-06 | Smuggler survives to another faction's ending | Individual survival objective and rewards handled explicitly |
| END-07 | Everyone dies or multiple win triggers occur together | Deterministic precedence/draw rule; one payout |
| END-08 | `/end` repeatedly; timer tick after end | Reveal remains available; no duplicate XP/coins or gameplay mutation |
| END-09 | Restart after completion | Result/reveal remains accessible without replaying rewards |
| END-10 | Rematch | New match ID and clean per-match state; historical totals preserved |
| DB-01 | Save/reload in every phase | Phase, roles, actions, timers, custody, queues, votes, and messages preserved |
| DB-02 | Crash immediately before/after reward commit or snapshot removal | One durable finalization, never duplicate or missing payout |
| DB-03 | Result storage fails once then succeeds | Retry works; in-memory finalized flag does not suppress recovery |
| DB-04 | Database locked/full/unavailable | Safe failure; no false success acknowledgement or partial state corruption |
| DB-05 | Old/corrupt snapshot | Diagnosable error and recovery policy; unaffected games still load |
| DB-06 | Two matches in same group | Distinct history and players; no overwrite of previous match records |
| DB-07 | Player leaves lobby, match ends, retention expires | No stale active-player rows or unbounded state/cache growth |
| RTE-01 | One active game, private command | Correct game selected; output goes to intended recipient |
| RTE-02 | Multiple active games, no selected table | Request selection; do not guess |
| RTE-03 | Selected table ends while another remains active | Old selection does not trap unrelated future commands |
| RTE-04 | Two parallel tables in one group | Callbacks, invitations, persistence, and broadcasts use correct logical table and real Telegram chat |
| RTE-05 | Stale callback from another round/match | Reject rather than act on the new game |
| RTE-06 | Private host advances phase | Required public announcement still reaches group exactly once |

### Timers, privacy, input, and operations

| ID | Scenario | Expected result |
|---|---|---|
| TIM-01 | Just before/exactly at/after each timed deadline | One legal transition with complete public/private outputs |
| TIM-02 | Manual close and scheduled tick overlap | One transition, one resolution, one reward |
| TIM-03 | Pause with 30 seconds, zero seconds, or no deadline | Preserve semantics and remaining duration |
| TIM-04 | Attempt action/vote/verdict while paused | Denied; read-only operations still available |
| TIM-05 | Resume after wait or restart | Remaining duration restored; no permanent timer loss |
| TIM-06 | Offline while several deadlines pass | Documented catch-up policy; no uncontrolled repeated elimination |
| TIM-07 | Scheduler dependency missing | Startup reports that automatic timers are unavailable; no silent feature loss |
| SEC-01 | Failed DM for role, hints, findings, or transcript | No content or sensitive keyboard sent to group |
| SEC-02 | Empty/nonempty admin list | Default deny; only listed IDs perform admin operations |
| SEC-03 | Banned player joins or sends action/callback | Ban is enforced across entry points |
| SEC-04 | Public dashboard/reminder lists pending night actors | Does not identify hidden active-role holders or action choices |
| SEC-05 | Every role invokes every exclusive capability | Only the authorized role/status succeeds |
| SEC-06 | Spectator accesses notes/role/action/session | Cannot access private player data or mutate gameplay |
| SEC-07 | Malformed callbacks, missing/deleted message, huge IDs, Unicode input | Clear response; no crash or cross-game access |
| SEC-08 | Rate limit and duplicate callback | Legitimate edits remain possible; duplicate delivery has no extra effect |
| SEC-09 | Private content reaches audit logs/admin user history | Content access/retention follows explicit policy; no accidental transcript exposure |
| OPS-01 | Clean environment installation | All imports, image generation, scheduler, and entry point work using declared dependencies |
| OPS-02 | Persian names, emoji, long names, RTL role cards | Readable text and images; safe message/caption limits |
| OPS-03 | Restart, temporary network failure, Telegram send retry | No lost acknowledged action or private-to-public fallback |
| OPS-04 | Many simultaneous games and long-running process | Measured latency, bounded caches, graceful shutdown, reliable save/restore |
| OPS-05 | All menu buttons in every phase | Point to supported, correctly authorized actions with helpful feedback |

## 5. Full-match acceptance journeys

These must use public command/callback flows wherever possible. Do not fake `custody_nights = 1`, manually set the winner, or skip a required branch because a random seed assigned the wrong role. Deterministic fixtures can assign roles for unit tests; full-match tests must demonstrate actual assignment/startup.

| ID | Journey | Acceptance criterion |
|---|---|---|
| ACC-01 | 4-player ready lobby → role delivery → investigation → voting → human interrogation → jail progression → city victory | Entire match completes, secrets remain private, results recorded once |
| ACC-02 | Killer victory through valid night actions and votes | Winning condition and reveal match actual survivors |
| ACC-03 | 10-player match with poison, doctor, hunter, and serial killer | Interactions follow the resolution specification; no early city win |
| ACC-04 | Innocent suspect → private conversation → jury acquittal | Human messages reach correct participants; normal play resumes |
| ACC-05 | Previous prisoner cleared after new suspect arrives | Conditional release works through actual commands |
| ACC-06 | Scapegoat deliberately reaches life jail | Correct independent winner and rewards |
| ACC-07 | Host absent, officer killed, suspect killed, or player blocks bot | Defined recovery path; match does not stall indefinitely |
| ACC-08 | Two groups/tables with shared participants | No action, private message, or timer announcement crosses game boundaries |
| ACC-09 | Restart at night, interrogation, jury, and finalization boundaries | Correct state and pending deliveries restored; no double payout |
| ACC-10 | Timer-driven match and equivalent manually advanced match | Equivalent game results and information delivery, allowing documented timing differences |
| ACC-11 | Pause/resume and blitz | Correct remaining durations and custody rules throughout a complete match |
| ACC-12 | Real Telegram staging match with consenting test participants | DM permissions, callbacks, actual two-person relay, retries, RTL rendering, and group delivery verified |

Staging is a separate execution step, not part of this documentation task. Do not message real players or start the production bot as an incidental test.

## 6. Findings to recheck after ongoing changes

These observations refer to code inspected during this session. File names and function names are given because line numbers are moving. None should be labelled “fixed” or “still failing on the final build” without a later test.

| Finding | Priority | Observation / impact | Relevant scenario IDs |
|---|---|---|---|
| F-01 | P0 | `Game.ask()` calls `dialogue.answer()` and `h_ask()` returns that generated answer; no human two-person relay was present in the inspected path. | MSG-01–18, ACC-04 |
| F-02 | P0 | `h_ask()` was not marked private; when invoked in a group, generated interrogation content can be public. A private-room feature needs explicit recipients, not just a private boolean. | MSG-01, MSG-04, SEC-01 |
| F-03 | P0 | Public `h_dashboard()`/`h_remind()` use `pending_actors()`, which selects players by hidden night ability. Publishing those names exposes role information by inference. | SEC-04, NGT-27 |
| F-04 | P1 | `expose()` checks role and `in_game`, but not interrogation/temporary custody; `set_hunter()` checks role but not actor life/custody. Officer methods rely mainly on officer ID. | SEC-05, CUS-04, NGT-03 |
| F-05 | P1 | `request_jury()` adds a petitioner before fully validating membership and does not check life/vote eligibility in the inspected implementation. | JUR-03 |
| F-06 | P1 | `h_startgame`, `h_dawn`, `h_discuss`, `h_vote`, `h_closevote`, and `h_closejury` need a consistent session-control policy. Several lacked host/member checks. | LOB-09, TIM-02, SEC-06 |
| F-07 | P1 | `Game.start()` lacked an explicit lobby-only guard; invoking start again risks reshuffling an active game. | LOB-10 |
| F-08 | P1 | `pause()` set `paused=True` before asking `remaining()`, which then read `paused_left` rather than the active deadline. `resume()` treats zero as no deadline. Action methods need pause guards too. | TIM-03–05 |
| F-09 | P1 | New readiness requirements were being added while many existing test helpers called `start()` without readiness. Startup test failures must be distinguished from deeper gameplay failures. | LOB-05–08 |
| F-10 | P1 | `/ready` needs proof of the required private interaction. A group command returning a private response does not by itself prove delivery succeeded before state was changed. | LOB-05–06 |
| F-11 | P1 | `handle()` set `finalized=True` before `record_results()`. A failed write can suppress retry; separate commits/snapshot deletion also need crash-safe finalization. | DB-02–03 |
| F-12 | P1 | Finished games remained in memory but their snapshots were dropped. Restart-safe final reveal and bounded retention need a deliberate design. | END-08–09, DB-07 |
| F-13 | P1 | `_check_win()` declared city victory whenever no killer-team players remained, even with a surviving serial killer and other players. | END-04 |
| F-14 | P1 | Winner/reward matching uses alignment-name prefixes. A neutral serial-killer winner and the smuggler's survival objective require explicit individual win handling. | END-03, END-06 |
| F-15 | P1 | Hunter final-shot logic was in the night-death path, not the life-imprisonment transition promised in the role description. Cascade order also needs review. | NGT-17–20 |
| F-16 | P1 | Doctor repeat-target restriction can be bypassed by first committing another target; detective previous-target bookkeeping was stored in the dictionary cleared at dawn. | NGT-06–07 |
| F-17 | P1 | The inspected compositions never assign lawyer, reporter, grocer, or smuggler. Listing a role and manually injecting it in tests does not make it available to real players. | Role matrix, JUR-02, NGT-21/25 |
| F-18 | P1 | Forensic action accepts a player target but selects evidence from the current day; coroner results use a fixed time and the case weapon. These do not fully match the advertised investigative choices. | NGT-22–23 |
| F-19 | P1 | Parallel tables use synthetic IDs as `Game.chat_id`; callbacks/timer broadcasts need a separate real Telegram chat ID and immutable table identity. | RTE-04 |
| F-20 | P1 | A verdict during an active jury can clear the suspect without a corresponding jury-state transition. Unresolved or dead suspects also need cleanup. | JUR-06, CUS-06/10 |
| F-21 | P2 | `h_closevote()` treats a `None` result as night even when the engine kept voting open for a runoff. | VOT-04 |
| F-22 | P2 | Every vote edit appends to `vote_history`, and payout rewards hits in that history; repeated votes can inflate XP/accuracy. | VOT-06 |
| F-23 | P1 | `is_banned()` exists in storage; enforcement was not present in the inspected central handler. | SEC-03 |
| F-24 | P1 | `requirements.txt` listed basic Telegram, dotenv, and pytest dependencies, while cards import Pillow and automatic timers require the scheduler dependency. Verify in a clean environment rather than relying on the developer's venv. | OPS-01, TIM-07 |
| F-25 | P2 | Evidence authenticity is always tied to the same deck positions; evidence and laboratory text are only loosely connected to actual players/actions. | NGT-22, improvement roadmap |
| F-26 | P1 | Private-room commands, group control, and old callbacks need explicit match/session versions; current selected table alone cannot safely identify an old button's intended match. | MSG-06–08, RTE-05 |
| F-27 | P2 | Night events and default game seeds derive from chat/day; repeated group matches can repeat assignments/events. | LOB-14 |
| F-28 | P1 | Mature poison entries are removed before storm cancellation; a storm may erase a due poisoning entirely. Requires a settled rule and regression scenario. | NGT-16 |
| F-29 | P2 | `games` uses chat ID as its primary key; player rows also use chat ID. Multiple matches in one group can overwrite history and leave stale participants. | DB-06–07 |
| F-30 | P1 | Private arguments are written into audit-event details, and admin user history can expose those details. Define which confidential content is excluded or protected. | SEC-09 |

P0 means resolve before a public gameplay trial. P1 means resolve before release acceptance. P2 means address in the quality milestone unless it blocks a core rule.

## 7. Test implementation plan and executed subset

The implemented subset uses `tests/quality/test_unit_permissions.py`, `test_regression_contracts.py`, `test_functional_privacy.py`, `test_edge_cases.py`, `test_gameplay_acceptance.py`, `test_evidence_contracts.py`, and `test_rule_boundaries.py`. The layer directories below remain an organizational proposal. See [audit-results.md](audit-results.md) for actual executed coverage, deliberate failing contracts, and untested scenarios.

Do not rewrite a failing assertion simply to match the implementation. Resolve the intended rule first, then change the implementation or documented requirement with traceability.

| Test layer | What it must establish | Proposed location |
|---|---|---|
| Unit | Role capabilities; input/target validity; individual effects; thresholds; timer arithmetic; reward predicates | `tests/unit/` |
| Functional | Commands and callbacks produce correct state changes, responses, keyboard options, and audiences | `tests/functional/` |
| Integration | Dispatcher + engine + temporary SQLite + fake Telegram transport; snapshots; private relay; crash/retry boundaries | `tests/integration/` |
| Acceptance | ACC journeys and MSG requirements through public entry points; separate real Telegram staging checklist | `tests/acceptance/` |
| Regression | Original ten findings plus F-01–30 once reproduced; each fix has a stable failing-before/passing-after test | `tests/regression/` |
| Gameplay | Supported sizes/cases/seeds, legal and adversarial action sequences, full terminal journeys, multi-role interactions | `tests/gameplay/` |

### Deterministic coverage strategy

1. Capture a stable source revision/hash manifest, dependency versions, and clean/dirty status. Preserve unrelated work.
2. Run existing tests without hiding failures. Report setup/collection failures separately from behavior failures.
3. Add the explicit role-permission matrix. Use named deterministic fixtures for positive and negative role tests; cover all 18 roles.
4. Run 4–10 player starts against all 40 cases: **280 distinct size/case configurations** before seed variations. Verify legal role counts, one officer, unique users/evidence IDs, no early reveal, and initial timers.
5. Exercise every phase edge through public commands, including forbidden edges. Court must either have a supported reachable purpose or be explicitly excluded as unused.
6. Add explicit pairwise interactions: kill/protect, frame/investigate, hide/investigate, hide/watch, poison/protect, hunter/fate, reporter/witness, custody/night action, jury/verdict, pause/timer, end/reward.
7. Add the higher-order cases that pairwise testing misses: poison + storm + protection; hunter + fate pair + simultaneous attack; verdict + timer + restart; private delivery + crash + retry; two games + table switch + stale callback.
8. Generate bounded, reproducible action sequences across all sizes with varied seeds. Check invariants after **every** action. Save the seed and minimal event sequence on failure.
9. Use deliberate winning strategies/scenarios for terminal-path tests. A random game reaching a turn cap is an inconclusive run, not a successful completed match.
10. Repeat selected simulations with a restart at each significant boundary and compare their state/results with uninterrupted execution.

### Invariants for generated gameplay

- An unauthorized action never changes state or reveals private information.
- A player has at most one effective ballot per voting round and one allowed committed night action.
- Eliminations, poison maturity, custody transitions, and final shots occur at most once per triggering event.
- Every suspect/pending prisoner references an existing valid player and consistent custody state.
- Public evidence is unique and belongs to the current case; secret role data is absent from public output.
- Phase, day, deadlines, and pause state agree; replayed updates do not advance time twice.
- Results are terminal; rewards, achievements, and missions are idempotent across retries/restarts.
- Every private delivery has an authorized recipient in the correct match/session.
- Match state is recoverable; one game's state cannot contaminate another.
- A supported journey either progresses legally or reports a specific missing human action/recovery path; it does not silently deadlock.

### Fixtures and isolation

- Use temporary databases or in-memory SQLite; never the existing `karagah.db`.
- Use synthetic environment values, not the real `.env` token. Block outbound network calls in offline tests.
- Mock the Telegram transport and clock, not the engine behavior being tested.
- Reset games, selected tables, callback deduplication, rate limits, rosters, locks as appropriate, and DB connections between tests.
- Assert responses and recipients as well as internal state. A correct engine result with no player-visible delivery is not feature completion.
- Test duplicate updates separately from two intentional identical commands.
- For persistence integration, use a file-backed temporary database and actually close/reopen it. An in-memory object round-trip alone does not demonstrate crash recovery.
- Do not skip a role scenario because of an unlucky seed. Use a known valid composition/seed or an explicit unit fixture and label which was used.
- Keep compatibility changes to legacy test setup separate from new behavior tests. Never globally auto-mark everyone ready and claim the readiness flow was tested.

### Regression ledger for the original ten findings

| Original issue | Regression contract |
|---|---|
| 1. DM leak | Failed DM for each confidential payload produces only a content-free notice; no sensitive keyboard |
| 2. Empty admin list | Denies every nonlisted actor, including empty-list configuration |
| 3. Active game replacement | Consistent policy for new/blitz/rematch/startgame and direct callback attempts |
| 4. Missing ending | Reveal available after command-driven/timer-driven finish and after restart; one payout |
| 5. Multi-investigation | Repeated target changes yield only one permitted result and respect alternate-action exclusivity |
| 6. Missing role effects | Each advertised ability has an observable correct effect and usable UI, not just an accepted action key |
| 7. Unreachable jury | Complete vote → interrogation night → petition → jury → decision without manually editing custody counters |
| 8. Expired runoff | Fresh deadline plus accurate runoff UI and candidate policy |
| 9. Timer persistence | Same durable transition/output as manual progression; results finalized once |
| 10. Private routing | Single/multiple games, explicit selection, stale context, parallel tables, and completed-game lookup |

### Later execution order and release gate

1. Confirm application changes are finished and select the revision being evaluated.
2. Compile/import/collect tests; validate dependencies in a clean environment.
3. Run unit and authorization suites, then functional, integration, regression, and gameplay suites.
4. Produce JUnit results plus a readable summary mapping failures to the IDs in this document. Record pass/fail/skip/error counts separately, duration, seeds, and source hashes.
5. Measure branch coverage for authorization, state transitions, night resolution, and finalization. Coverage is supporting evidence, not proof of gameplay correctness.
6. Run scripted staging acceptance separately with explicit test participants. Record actual delivery/visibility outcomes.
7. Release only when P0/P1 behavior and all agreed acceptance journeys pass, no critical scenario is skipped, crash-safe payout is verified, and outstanding lower-priority limitations are documented.

The reproducible command for the implemented suites is `.venv/Scripts/python.exe -B tools/run_quality_audit.py`. It separately runs existing and new tests in a credential-free source snapshot, uses a temporary database and fake Telegram transport, blocks external network connections, and records hashes, versions, JUnit XML, logs, and a JSON summary. Failing contracts return a nonzero exit code. The planned layer directories should not be used in commands until they exist.

## 8. Improvement roadmap

| Order | Improvement | Definition of done |
|---|---|---|
| 1 | Central authorization policy | Every command and callback checks actor, role, phase, custody, membership, pause, and target; SEC-05 passes across the matrix |
| 2 | Real private interrogation | MSG-01–18 implemented; human questions/answers delivered to the two authorized participants; no scripted impersonation |
| 3 | Unified state transition service | Manual commands and timers share one transition/persistence/event path; equivalent outputs and no duplicate execution |
| 4 | Durable match IDs and finalization | Separate match/table/chat identity, transactional result ledger, reliable crash recovery, retained final summaries |
| 5 | Complete role delivery | All supported roles appear in a selectable documented mode, have appropriate target UI, real effects, readable findings, and correct victory logic |
| 6 | Private-safe UX | Group dashboard never enumerates secret active-role actors; private action panel shows legal targets, action status, and findings |
| 7 | Robust absence and pause behavior | Proper clock handling, readiness verification, host/office fallback, no forced dependence on eliminated players |
| 8 | Evidence with gameplay meaning | Player-specific alibis/timelines, meaningful forensic selection, actual death causes, and laboratory results that narrow hypotheses |
| 9 | Fair progression and balance | Reward final effective actions, measure faction/role win rates and match duration by size, prevent repeat-vote farming and predictable assignments |
| 10 | Operational polish | Declared runtime dependencies, bounded caches/retention, migration-aware snapshots, structured errors, Persian typography, and tested clean installation |

Success should be measured through completed matches, absence of unauthorized deliveries, recovery after failure, correctness of role abilities, and clear player feedback—not solely the number of passing test functions.
