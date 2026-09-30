# Evidence and role usefulness audit

Date: 2026-09-20. Evaluated source: the stable snapshot identified in [audit-results.md](audit-results.md). This separates current behavior from the target design in [rules.md](rules.md).

## Overall finding

**Not every advertised role or clue is currently useful within an ordinary playable match.** Four roles are not assigned by any standard composition. Several other abilities work mechanically but provide redundant, predictable, or insufficiently contextual information. New event traces are an improvement over generic cards, but at least one trace makes a stronger claim than the underlying events justify.

The 40 cases have distinct narrative settings, but all use the same six-card generator, four generic interpretation templates, a common timeline pattern, and the same authenticity-position mask. All 280 case/player-count opening combinations passed structural gameplay checks. That establishes that they can start and progress through the opening, not that each is a distinct, fair, solvable mystery.

## 1. What makes information useful?

A useful clue should change an in-game decision without simply revealing a hidden role. Evaluate it along this chain:

**Actual game event → bounded observation → plausible alternatives → available verification → player decision → later resolution.**

Examples of decisions: question a specific alibi, watch a player tonight, protect a likely target, request a lab result, delay a verdict, or change a vote.

| Information class | Purpose | Example | Required safeguard |
|---|---|---|---|
| Actionable clue | Narrow a suspect/time/action set | A visitor was present during the relevant window | Must come from the actual event ledger; not every visitor is an attacker |
| Corroborating clue | Strengthen or weaken another observation | Independent transport timing agrees with an alibi | Independence is real; duplicated source evidence is not two confirmations |
| Exculpatory clue | Explain away suspicion | A fingerprint predates the incident | Available before the relevant irreversible verdict |
| Ambiguous clue | Create multiple testable theories | The cup has two contributors | Include contextual hypotheses rather than four interchangeable generic sentences |
| Deliberate frame | Enable adversarial deception | Accomplice plants a trace | Caused by an actual ability, with finite lifetime and a detection path |
| Unreliable rumor | Encourage social comparison | Witness may have confused two similar coats | Source reliability is explicit and uncertainty is fair; retain a truth ledger for the reveal |
| Red herring | Create a plausible detour that can be resolved | Old glove from a previous repair visit | Coherent innocent cause and a way to disprove relevance |
| Atmosphere | Give the case character | Rain, a damaged portrait, an argument unrelated to the killing | Brief and identifiable as background; do not consume scarce investigations on pure filler |

“Useless information” should mean optional atmosphere or a **resolvable** distraction, not arbitrary false facts. A red herring becomes useful once dismissing it teaches the player how the incident happened or removes a suspect.

## 2. Directions for writing fair cases

1. Write the hidden event timeline first: actors, actions, locations, time windows, causal links, and possible innocent explanations.
2. Generate observations from that ledger. Give each clue a source, time window, provenance, visibility, and concrete hypotheses it supports or contradicts.
3. Keep **authenticity**, **relevance**, and **reliability** separate. A genuine fingerprint may be irrelevant; a planted genuine hair may implicate the wrong person.
4. For an initial six-card set, start with roughly three actionable observations, one corroborating/exculpatory observation, one resolvable red herring, and one contextual clue. This is an editorial starting point, not a fixed positional pattern exposed to players.
5. Shuffle identities and positions per match. Never make a stable card number synonymous with “fake.”
6. Include at least two usable investigative routes for the selected role pool: for example, public timeline comparison and private forensics. No case should require an unavailable role.
7. Place decisive corroboration before the normal irreversible custody deadline, or provide a real appeal mechanism.
8. A failed hypothesis should still return an informative result: “sample predates the incident,” not merely “nothing useful.”
9. Preserve uncertainty honestly. Avoid statements such as “the killer is among these visitors” when poisoning, a hunter shot, or a linked death could explain the casualty.
10. At the final reveal, explain major clues and distractions. Do not invent the explanation after observing player guesses.
11. Bound clutter: a day should provide a small digest with links/buttons for details, not repeated six-card dumps. Do not increase the evidence counter when repeating a card.
12. Evaluate usefulness in playtests: which clue caused an action change, whether players could explain it, whether innocent players could refute a frame, and how often the mystery was solved by memorizing templates.

### Worked example: one useful clue and one fair distraction

Suppose the ledger says a doctor and an attacker both visited the eventual victim, and an old cleaner's fingerprint was already on the room's glass.

- Public useful clue: “Two visits occurred between 22:40 and 23:00; their purposes are unknown.”
- Private useful finding: the watcher reports the eligible visit count; a forensic test dates one fingerprint to an earlier window.
- Red herring: the cleaner's authentic fingerprint initially creates suspicion. A maintenance record or test can explain it before conviction.
- Player decision: compare alibis and question the visitors rather than treating physical presence as automatic guilt.
- Final resolution: explain the old fingerprint, the two actual visits, and the protection/attack outcome.

If the death actually came from mature poison with no attacker visit that night, the clue must not guarantee that one of that night's visitors killed the victim. A change to the event cause must change the inference.

## 3. All 16 evidence types

Current baseline: each type is principally a title/kind in a generic static card with shared interpretation templates. The table describes how each can become useful **inside the game**, without external tools, real personal data, or professional knowledge. These are content directions, not implemented forensic claims.

| Type in catalog | Useful bounded information | Fair red herring / limitation | In-game verification and payoff |
|---|---|---|---|
| Fingerprint / اثر انگشت | Links a player to a touched surface during a stated interval | Old legitimate visit; planted trace | Compare visit timeline and forensic age/placement; challenge a frame |
| DNA | Establishes a simulated contributor set or excludes a candidate | Mixed sample, transfer, contamination | Lab narrows contributor hypotheses; never automatically equals guilt |
| Footprint / رد پا | Direction, route, and approximate time/location compatibility | Shared footwear or earlier passage | Compare alibis and another route observation; choose a watcher target |
| Hair / تار مو | Contact with an object/location | Innocent transfer or old contact | Date/context evidence can exclude incident relevance |
| Deleted message / پیامک حذف‌شده | A bounded communication time and partial content | Old argument unrelated to the killing; missing context | Recover a second fragment and compare sender's claim |
| CCTV / دوربین مداربسته | Entry/exit window, number of people, partial appearance | Clock offset, occlusion, similar clothing | Cross-check clock calibration and independent timestamp |
| Taxi receipt / رسید تاکسی | Claimed departure/arrival window or route | Receipt held by someone else | Compare receipt ownership, witness window, and stated alibi |
| Autopsy report / گزارش کالبدشکافی | Actual death window/cause category | Delay between poisoning and death can mislead a same-night inference | Coroner/lab distinguishes event cause and timing; prevents false visitor accusations |
| Blood / لکه‌ی خون | Links injury/contact to a place or object | Innocent earlier injury | Compare simulated sample age and injury account |
| Glove / دستکش | Tool handling or concealment opportunity | Shared work equipment | Compare material/residue/time context; avoid role stereotypes |
| Deleted file / فایل پاک‌شده | Time of an edit/access and a recoverable fragment | Routine deletion or copied account | Compare logs and independent event chronology |
| Recording / صدای ضبط‌شده | Sequence and relative timing of audible events | Misheard sound, incomplete clip, background voice | Supply bounded transcript/segments and compare timestamps; no external audio expertise required |
| Broken watch / ساعت شکسته | Candidate event time | Previously broken or altered watch | Another time anchor can confirm or refute its relevance |
| Bank receipt / رسید کارت بانکی | In-game transaction window/location/relationship | Borrowed card or unrelated debt | Compare transaction with alibi; avoid real financial/personal information |
| Soil / خاک روی کفش | Route/location compatibility | Common soil or old contamination | Compare two in-game sample descriptions and travel accounts |
| Glass/cup / لیوان | Who handled which vessel and possible exposure order | Switched cups, old prints, innocent handling | Combine serving sequence, sample evidence, and poison timing |

Every evidence item should carry structured fields such as `evidence_id`, `source_event_ids`, `observed_at`, `time_window`, `visibility`, `authenticity`, `relevance`, `reliability`, `hypotheses`, `verification_options`, and `resolution`. The bot must expose only the fields allowed to the requesting player.

## 4. What the current evidence checks found

| Check | Snapshot result | Why it matters |
|---|---|---|
| All 40 cases start at all 7 supported sizes | 280 opening cycles passed | Structural compatibility, not content-solvability proof |
| Authenticity differs by case/position | Failed: every mask is `(real, fake, real, real, fake, real)` | Players can learn E2/E5 without spending a legitimate investigative action |
| Evidence stays unique after deck exhaustion | Failed: repeated reveals exceeded six while unique IDs stayed six | Inflated progress and duplicate clue presentation |
| Lab result adds actionable information | Failed | The generic “origin established; narrow interpretations” message gives no actual narrowing |
| Spy's information adds something unavailable publicly | Failed usefulness contract | Repeats the publicly nominated suspect; distinguish actual private questioning or redesign the role |
| Grocer produces a new daily rumor | Failed | A catalog promise is missing a daily delivery path |
| Trace truth matches cause of death | Failed unit contract | A non-attack visitor is still described as belonging to a set guaranteed to include the killer |

The authenticity, spy-value, lab-content, and quota tests are **quality/design contracts**, not claims that an earlier test once passed and then regressed. They intentionally identify gaps against the target rules.

## 5. Usefulness of all 18 roles within the current boundary

Distinctive Persian display titles and their canonical-role mapping are in [role-names.md](role-names.md). This audit uses the canonical names so its findings continue to match the code.

Standard seat counts are from `COMPOSITIONS`; “unit-access passes” refers to the all-role authorization tests and does not imply full usability or balanced gameplay.

| Role | Assigned at player counts | Current contribution | Limitation / direction |
|---|---|---|---|
| Detective | 4–10 | Alignment findings and evidence authenticity can guide votes | Consecutive-target restriction resets; custody bypass for expose; fixed fake-card positions reduce authentication value |
| Officer | 4–10 | Central custody decision-maker | Human room missing; status checks and unavailable-officer fallback need work; synthetic replies are not human interrogation |
| Forensic specialist | 8 | Private authenticity finding | Ignores chosen player target and picks day's card; needs evidence-selection UI and meaningful additional context |
| Doctor | 5, 6, 7, 9, 10 | Directly changes survival and poison outcome | Consecutive-target edit bypass; settle poison cure timing; no doctor in 8-player composition is a balance choice to measure |
| Watcher | 8, 9, 10 | Visit counts can corroborate claims | Publish a consistent visit definition; avoid conflict with public traces and hiding |
| Reporter | None | Would improve public evidence tempo | Not available in standard games; effect must produce a genuinely new visible clue |
| Lawyer | None | Would provide a distinct jury path | Not available in standard games; ordinary jury path cannot substitute for testing lawyer privilege |
| Citizen | 4, 5, 6, 7 | Essential voting/social role; useful without a night power | Preserve private-role uncertainty; an ordinary citizen must still have meaningful public evidence work |
| Coroner | 7, 8, 10 | Intended to distinguish death timing/cause | Fixed time and case weapon do not explain actual poison/hunter/linked deaths |
| Hunter | 9, 10 | Credible elimination consequence | Life-jail shot missing; eliminated player can still retarget; chain ordering needs verification |
| Killer | 4–10 | Core opposition, survival pressure, deception | Core attack path works; protect private action context and fresh seeds |
| Accomplice | 7–10 | Creates alternate explanations and suspicion | Must remain falsifiable; frame lifetime and hiding precedence need consistency |
| Poisoner | 10 | Delayed threat, timing puzzle, counterplay for doctor | Storm can erase mature poison; treatment timing needs a consistent rule |
| Spy | 9 | Intended informational support for killers | Target information is already public; useful value needs a hidden but limited observation |
| Scapegoat | 6, 8, 9 | Makes “suspicious” non-equivalent to killer; creates voting risk | Distinguish imprisonment from death and define simultaneous-win precedence |
| Serial killer | 10 | Independent hostile objective | Premature city victory with serial killer alive; solo winner receives loser base reward |
| Grocer | None | Intended social uncertainty and rumor source | Not assigned; no daily rumor mechanism; don't advertise 70% reliability without a defined generator |
| Smuggler | None | Intended investigation/watch counterplay and survival goal | Not assigned; survival reward absent; hiding should be inconclusive rather than false certainty |

Conclusion: **all roles have a potential design purpose, but not all are operationally useful in the current standard game.** Do not solve this by giving everyone access to every power. Introduce explicit tested modes/rotations, preserve exclusive abilities, and remove or label unsupported catalog entries until playable.

## 6. Additional usefulness acceptance criteria

- For each role, at least one full-match scenario must show its ability changing a legitimate player's decision or the outcome, plus an adversarial test proving others cannot access it.
- For each evidence type, include one relevant instance, one innocent explanation, and one invalid inference the bot explicitly avoids.
- For every case/mode, verify at least one path to useful conclusions using its actual assigned roles; role injection in a unit test is not enough.
- Compare play with and without a clue/role in controlled scenarios. If no reachable decision differs, redesign its information or state that it is atmosphere.
- Avoid game facts that require real-world forensics, internet research, cultural stereotypes, or private personal knowledge. Everything needed must be available in the game boundary.
- Measure action usage, comprehension, incorrect-certainty rates, appeal opportunities, and whether players resolve red herrings. Win rate alone cannot establish usefulness.

## 7. What remains unproven

No human playtest was performed; no measured cognitive difficulty, strategic balance, or clue comprehension is claimed. The automated checks cover selected necessary conditions and specific failure modes. Full human-room communication, all resolution-order combinations, mode-specific role rotations, and every acceptance journey remain implementation/test work. See the scenario catalog and release gate in [improvement.md](improvement.md).
