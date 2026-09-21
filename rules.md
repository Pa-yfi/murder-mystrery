# Karagah game rules — release-target specification v1

Date: 2026-09-20

**Status:** These are the intended rules for the next quality release, established for implementation and testing. They are not a claim that the current bot enforces every rule. Existing behavior differs in several places; see [improvement.md](improvement.md), [audit-results.md](audit-results.md), and [evidence-and-roles.md](evidence-and-roles.md). Proposed choices in the earlier scenario document are resolved here for this target ruleset; any future change must update both rules and tests.

## R01. Match setup and identity

- Standard games have 4–10 distinct players, exactly one officer, at least one killer-team player, and a published balanced role pool for that mode.
- Each match has a unique identity independent of its Telegram group. Parallel tables have distinct identities and share a real group destination only for intended public messages.
- Every player privately opens the bot and confirms readiness. The bot must verify private delivery before treating readiness as complete.
- Only the host starts, pauses, resumes, transfers, or explicitly cancels a match. A force-start override may bypass readiness but never grant a role extra access. The lobby must explain who is still unreachable.
- Starting an already-running match is rejected. Restarting requires explicit host cancellation, a public cancellation event, and a fresh match identity.
- Game mode, roles available, phase durations, custody durations, anonymity, and optional modifiers are fixed before roles are assigned. Do not change them mid-match.
- Gameplay takes place inside the bot/group. No external personal information or off-platform contact is needed to solve a case.
- The host has no additional role information. Moderation privileges do not confer gameplay or private-room privileges.

## R02. Roles and abilities

Players may use only their assigned abilities. All checks run on the server for both commands and buttons. Hiding a button is not authorization. A target ID never changes the identity of the actor.

The selected Persian display names are documented in [role-names.md](role-names.md): ردبین، رازپرس، اثرکاو، جان‌بان، شب‌پای، پرده‌گشا، دادخواه، هم‌محله، مرگ‌خوان، واپسین‌تیر، خاموشگر، ردساز، زهرریز، سایه‌شنو، بلاگردان، تنهاکُش، پچ‌پچ‌فروش، ردپوش. The table below retains canonical names for unambiguous rules and test references; a display name never changes permissions.

| Role | Ability and permitted information | Boundary |
|---|---|---|
| Detective / کارآگاه | One player alignment investigation OR one evidence-authenticity check per night; private result at resolution | No consecutive-night investigation of the same player; neutral reads suspicious; framing/hiding follow R06 |
| Officer / بازجو | Private human interrogation, ambiguous hints, post-night verdict, conditional release | Must be alive, free, current officer, and not the suspect; cannot act during a jury's decision |
| Forensic specialist / پزشک قانونی | Select one evidence ID for a private early lab result each night | Evidence target, not arbitrary player target; authenticity is distinct from guilt |
| Doctor / پزشک | Protect one other player; clear/prevent poison on the protected player that night | Cannot self-protect or protect last night's target, including by editing an action |
| Watcher / نگهبان | Observe visits to one target; privately receive the defined visit count | No automatic visitor identity, alignment, or transcript access |
| Reporter / خبرنگار | Publish one additional unrevealed eligible evidence item | No secret roles, duplicate evidence, or private notes published |
| Lawyer / وکیل | One eligible petition suffices to open a jury | Cannot issue officer verdicts or bypass the custody waiting period |
| Citizen / شهروند | Public discussion, permitted ballots, shared public evidence tools | No exclusive night power |
| Coroner / کالبدشکاف | Privately receive actual death-time window and cause category after deaths | No invented precision; distinguish direct attack, poison, linked death, and final shot |
| Hunter / شکارچی | Choose a final-shot target while alive/free; shot on death or life jail | One shot only; no self-target or retargeting after elimination |
| Killer / قاتل | Participate in killer-team attack and know teammates | No self-attack; team has one collective direct attack per night |
| Accomplice / همدست | Frame one player's trace; know killer teammates | Cannot turn framing into an attack or change actual alignment |
| Poisoner / سم‌ساز | Poison one target; know teammates | Poison matures two subsequent night resolutions later; R06 defines cure and repeats |
| Spy / خبرچین | Privately learn whether the officer actually questioned a suspect that night and whom | Not merely the already-public nomination; never read questions, answers, or officer hints |
| Scapegoat / سپر بلا | Solo victory upon life imprisonment | Temporary detention or death is not the trigger |
| Serial killer / جانی سریالی | Independent attack; sole-survivor objective | Not a killer-team member; no shared teammate information |
| Grocer / بقال محله | One private daily rumor from a defined source model | About 70% true over generation trials, not guaranteed per match; false rumors have explanations |
| Smuggler / قاچاقچی | Conceal one target from investigation and watching that night; survival objective | Concealment is not protection from attacks and does not erase actual events |

Every advertised playable role must appear in a supported, tested mode. A mode may intentionally exclude some roles, but the menu must label that scope. Do not imply all catalog roles can appear in every player count.

## R03. Player state and action eligibility

| State | Ordinary night action | Public vote | Interrogation room | Existing own notes |
|---|---|---|---|---|
| Alive/free | If role and phase permit | If phase permits | Only if current officer/suspect | Read/write within quota |
| Under interrogation | No | No | Current suspect may answer and submit defense | Read; private notes allowed |
| Temporary jail | No | No | No active room unless explicitly summoned under a later rule | Read existing notes |
| Life jail | No | No | Closed | Read existing notes; spectator-safe public view |
| Dead | No | No | Closed | Read existing notes; spectator-safe public view |

- Dead/life-jailed players are eliminated. Temporary prisoners remain alive in the match, though ineligible for active powers.
- Officer powers, evidence authentication, hunter target selection, and other special commands obey the same actor-state restrictions. No alternate command bypasses custody.
- No ordinary actions are allowed in the lobby, completed match, or a paused match.
- An outsider, banned user, or spectator cannot mutate a match or access a player's secrets.

## R04. Phase flow

1. **Lobby:** join, leave, readiness, select mode, start.
2. **Night:** eligible players privately commit powers. Legal edits replace the choice until the deadline. Acknowledgements do not reveal results early.
3. **Morning:** resolve the night exactly once, publish deaths/public evidence, privately deliver findings. Resolve an outstanding custody decision before opening a new discussion.
4. **Discussion:** living eligible players debate public information. Private messages stay private.
5. **Vote:** eligible players choose a suspect; their latest valid ballot is the effective ballot.
6. **Interrogation night:** the suspect enters a private room with the officer. Other eligible players take their night actions. This counts as one actual night for poison and custody.
7. **Morning decision:** once the waiting period has elapsed, officer verdict or jury appeal resolves the suspect's case; then discussion resumes.
8. **End:** terminal outcome, public role reveal, explanation, per-player results, and idempotent reward recording.

There is no separate functional “final court” phase in this ruleset; it is presentation of the final result, not an unimplemented transition players can enter.

Night, discussion, voting, jury, and custody decisions have explicit deadlines. A timeout must not invent a human statement or silently convict someone. Proposed operational defaults: 60-second night, 180-second discussion, 90-second vote, 90-second jury, and 60-second morning custody decision; blitz halves phase durations. These are release-target defaults, not evidence that all corresponding timers exist today.

If neither officer nor jury can legally decide before the custody-decision deadline, release the suspect without declaring them factually innocent. Announce this procedural release.

## R05. Voting and juries

- Alive/free players vote once per round; changing a vote replaces it. Self-votes and votes for dead/life-jailed/temporary-jailed players are invalid. A player can explicitly abstain.
- A unique highest tally nominates a suspect. No votes means no arrest and the next night begins.
- A first tie opens a new timed runoff among tied leaders. A second tie yields no arrest. Announcements and buttons must match the actual phase.
- Anonymous mode hides voter-target mappings. It cannot be switched off mid-round.
- Once a suspect has spent the required interrogation night, two distinct eligible free players may petition for a jury; one eligible lawyer suffices. The suspect is not an eligible petitioner/voter in their own proceeding.
- Jury eligible electorate is snapshotted when the jury opens. An eliminated juror's ballot does not count; recompute the eligible denominator when required by elimination.
- A valid jury requires participation by a majority of the current eligible electorate. Acquittal requires at least 60% yes among non-abstaining ballots; exactly 60% qualifies. Zero effective votes never acquits by arithmetic accident.
- No quorum or insufficient yes votes returns authority to the officer/decision fallback; it does not itself create a life sentence.
- The officer cannot change the suspect's custody while a jury is active. The same custody episode gets one jury; a genuinely new later episode resets that limit.
- Vote rewards use effective final ballots only. Message count, duplicate taps, and edits never multiply XP or accuracy credit.

## R06. Night resolution order and interactions

Treat one night's actions as a batch. Submission order must not change the outcome.

1. Validate the actor, target, phase/session version, deadline, and action budget at commitment; reject invalid edits without removing the prior legal choice.
2. Freeze committed actions at resolution. Free/eligible actors at the freeze complete simultaneous actions even if killed by another action in that batch.
3. Apply concealment, framing, and protection. Doctor protection prevents a new poisoning and removes existing poison on that target that night.
4. Create new poison due two later actual nights. Repeated poisoning does not accelerate or extend an already-pending dose.
5. Determine direct attacks and mature poison. Protection blocks direct attacks. A storm cancels direct attacks only; it does not erase mature poison. Neutralize or postpone any effect only under an explicit rule.
6. Resolve deaths, hunter shots, and fate-pair links to a fixed point. Maintain a processed-event set so each player dies and each hunter fires at most once.
7. Advance custody once for the completed night. A hunter entering life jail also triggers the defined final shot. Reprocess resulting death links before evaluating victory.
8. Deliver scoped role findings and unique evidence based on the actual event ledger, then evaluate victory once.

Specific rules:

- Doctor protection does not block a fate-linked death or a hunter's final shot. A hunter's target must still be active when the shot triggers; otherwise it fizzles, without retargeting after elimination.
- Fate links trigger on death, not imprisonment. A hunter killing a linked player propagates to the partner. Chains cannot loop.
- Concealment lasts for the current night. A concealed investigation returns “inconclusive/hidden,” not a guaranteed clean alignment. A hidden watcher result is also inconclusive rather than false proof of no visits.
- A frame survives through the next night and makes an otherwise readable target suspicious; concealment takes precedence. The trace is contestable, not conclusive guilt.
- Direct target visits include attack, protection, poisoning, framing, and concealment. Watching/investigating are remote; evidence laboratory actions and room spying do not create fictional visits to an arbitrary player.
- Findings distinguish observed facts from interpretations. A poison/linked/shot victim does not prove that a visitor was the killer that night.

## R07. Custody and officer fallback

- Interrogation lasts one complete actual night before verdict eligibility. Blitz does not reduce it below one night.
- Confirmed detention becomes temporary jail for two further nights in standard mode, one in blitz. At the threshold, convert to life jail unless validly released.
- Conditional early release from temporary jail requires an eligible officer and a different current suspect. A released suspect is procedurally cleared, not mechanically revealed as city.
- No role is revealed merely because a player dies or enters life jail. Roles are revealed at match end.
- A dead suspect's case/room closes immediately. Do not allow a verdict against a stale suspect or leave their custody blocking the next phase.
- If the officer dies or is detained, use a jury-led process. Do not give the host officer secrets or ask an eliminated officer to continue acting.
- If the officer becomes the suspect, they cannot judge themselves. The jury process and procedural-release timeout apply.
- Emergency detention is available once per match during discussion. It needs at least 80% of current eligible other players, rounded up; excluding the target avoids impossible small-population thresholds. Support is one target per supporter and stale support is removed when eligibility changes. It cannot bypass terminal or paused state.

## R08. Private two-person communication

- An interrogation room belongs to one match, round, officer, and suspect. Authenticate both senders from Telegram updates.
- Officer questions are relayed to the human suspect; human answers are relayed to the officer. No rule-based or AI answer may be presented as something the human said.
- Both participants see delivery acknowledgements. Group messages reveal only public custody events, not the transcript or question contents.
- Private hints remain officer-only. The spy receives only the specific R02 metadata, never room contents.
- Switching selected tables does not change a message's room. Old buttons/messages cannot act on a new round or suspect.
- Release, death, life jail, match completion, or replacement closes the room. Pause suspends new gameplay messages; a jury may read only an explicitly published defense, not the transcript.
- Failed DM delivery never falls back to public content, keyboards, identifiers, or a forwarded original message. Give a neutral notice and a retry path.
- Store pending deliveries and session state durably; retry without duplicate delivery. General admin audit logs store event metadata, not raw private text.

## R09. Evidence, rumors, and fair misdirection

- A clue must have provenance, a time window, an observation, at least two plausible interpretations when ambiguous, and an in-game verification/refutation path.
- Authentic means the artifact is real; relevant means it bears on this incident; reliable means the observation is trustworthy. These are different properties.
- Useful clues change a reasonable decision: who to question, whom to protect/watch, which account to test, or whether to vote. Clues do not need to identify the killer outright.
- A red herring is explainable: a real old fingerprint, innocent visit, mistaken timestamp, or a frame created by an actual ability. It must be resolvable with available information before the relevant decision becomes irreversible.
- Pure atmosphere is explicitly non-evidentiary and short. Do not charge a scarce action to discover that arbitrary filler had no meaning.
- Do not hard-code fake evidence to fixed card positions or labels across cases. Players should investigate rather than memorize that “E2 and E5 are always fake.”
- Do not manufacture a trace inconsistent with the event ledger. Where information is incomplete, say so; never state an unearned guarantee.
- Do not repeat an already-revealed card as a new clue. Reporter/witness overlap is deduplicated. Once the deck is exhausted, report that fact or produce a supported new event-based clue.
- Shared laboratory requests return a concrete result, not an instruction to “narrow interpretations” without new information. Requests require eligible membership and revealed evidence; privileged early analysis is role-specific.
- Every case must have at least one useful evidence path accessible through the roles present in that mode. Absence of the forensic specialist must not make the mystery impossible.
- A single ambiguous clue, stress indicator, or suspicious alignment is not proof of guilt. Genuine player deception is allowed within the game; false bot assertions are not a substitute for fair uncertainty.

See [evidence-and-roles.md](evidence-and-roles.md) for all 16 evidence types, current usefulness findings, and writing directions.

## R10. Victory and reward precedence

Evaluate once after the complete resolution batch, not halfway through chained deaths.

1. If no active players remain, declare a draw. No faction victory rewards.
2. If the scapegoat newly receives life imprisonment while alive, declare its solo victory.
3. If the serial killer is the sole active survivor, declare its solo victory.
4. City wins when no active killer-team member or serial killer remains.
5. Killer team wins at parity or majority against all other active players **only when no active serial killer remains**.
6. Otherwise play continues. An active smuggler surviving to a non-draw ending receives an additional individual survival win; this does not override the main outcome.

For this ruleset “active” means alive and not life-jailed; temporary prisoners still count until their final elimination. This is a deliberate balance rule and must be shown to players.

- Winner IDs and reasons are explicit data, not inferred from translated string prefixes.
- Base rewards are 120 XP/60 coins for winners, 40 XP/20 coins for other participants, and 40 XP/20 coins for a draw. Correct final effective ballots earn the published bonus once per round. Define additional bonuses separately.
- Completion, rewards, missions, achievements, and season statistics are recorded once per immutable match ID. Retry and restart cannot duplicate or omit them.
- The final report explains deaths/custody, role reveals, winning trigger, and important clue resolution. It does not automatically publish private conversation transcripts.

## R11. Timers, absence, and recovery

- Scheduled and manual transitions follow the same authorization/state/persistence path. Timers are system actors, not anonymous players with unrestricted general powers.
- Pause freezes the clock and gameplay changes. Save remaining time before changing pause state; zero remaining means due immediately after resume, not no timer.
- Missed actions default to no action. Private reminders may identify a player's missing action. Public progress must not reveal hidden-role holders or allow exact hidden action counts to be inferred from polling.
- Missing players never speak through generated answers. Officer absence uses R07.
- After restart, restore a consistent committed state. Process each expired transition once; do not fast-forward multiple lethal phases without the intervening player interaction window.
- An acknowledged action must be durable. Database failure produces a recoverable error, not a false success.
- Completed matches retain a retrievable summary; large in-memory objects, temporary role-card files, rate-limit caches, and expired room data are cleaned up under bounded retention.

## R12. Input, data limits, and confidentiality

These are new release-target quotas; current tests intentionally expose missing enforcement.

| Data | Target boundary |
|---|---|
| User/player IDs | Valid Telegram identity from authenticated update and supported signed 64-bit storage range; reject arbitrary overflow before SQL |
| Case selection | Explicit supported ID 1–40; omission selects random; negative indexing is never accepted |
| Player display name | Up to 120 visible characters, escaped safely |
| Private note | Up to 200 characters; at most 100 retained per player per match |
| Will | Up to 200 characters; editable only while eligible |
| Public defense | Up to 300 characters; current suspect only, deliberate publication |
| Interrogation message | Up to 1,000 characters; at most 100 per session, with clear quota feedback |
| Rendered text page | At most 3,500 characters, allowing headroom; paginate rather than silently dropping content |
| Ballots | One effective ballot per voter per round; bound any audit history independently |
| Dedup/rate entries | Expire after their configured window; bound cache size and prune on a scheduled cleanup |
| Session retention | Proposed: private transcripts/pending delivery content removed after 7 days; final summaries retained 30 days; aggregate statistics contain no private text |

Never log or commit bot tokens, live environment files, private transcripts, or production databases. Keep private-message content out of ordinary administrator histories and error messages. Storage snapshots require a trusted, versioned format and explicit migration/error handling.

## R13. Applicability and test status

These rules cover normal flow, role/state permissions, simultaneous effects, custody/jury fallback, communication, terminal states, and invalid inputs. They do **not** yet pass all implementation checks.

| Rule | Scenario groups in improvement.md | Evidence/checks |
|---|---|---|
| R01 | LOB, RTE | Opening-cycle matrix; lifecycle and invalid-case contracts |
| R02–03 | Role matrix, NGT, SEC-05 | 810 ordinary role/phase/status cases, 90 exclusive-role cases, 12 special-state cases |
| R04–05 | VOT, CUS, JUR | 42 complete city journeys; real custody jury journey; runoff/reward contracts |
| R06 | NGT | Existing night-ability tests plus doctor/detective/hunter/trace contracts; remaining combinations planned |
| R07 | CUS, JUR, SOS | Jury petition and active-jury verdict contracts; fallback journeys still need implementation |
| R08 | MSG | Delivery privacy and relay acceptance contracts; full human room missing |
| R09 | NGT-21–25, evidence direction | Six evidence/usefulness contracts; content review of all case generators/types |
| R10 | END, DB | Serial winner, payout retry, ending restart, repeated-result contracts |
| R11 | TIM, DB, OPS | Timer persistence, pause boundaries, file DB restart integration |
| R12 | SEC, OPS, edge cases | Integer bounds, oversize note output, quotas, repeated input, SQL parameter handling, redacted repository signature scan |

The latest recorded results and untested boundaries are in [audit-results.md](audit-results.md). Any rule change must update this applicability mapping, acceptance expectations, and regression contracts before release.
