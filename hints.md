# Hint and evidence design audit — Claude implementation brief

Date: 2026-09-21. Scope: **research, source review, and original content design only**. No application code or test files were changed for this task. Proposed text below is not evidence that the current bot produces it.

**Latest revision:** section 13 records a subsequent source review of role archives, plate lookup, in-game menus and day tracking. It supersedes earlier statements that archives/vehicle records are entirely absent: partial implementations now exist. The current inspected registry has **77 endpoints**. Earlier source fingerprints and findings remain historical; the requested access, truth and privacy contracts remain the target.

## 1. Outcome and scope

The bot needs a **persistent, day-specific evidence dossier**, not another random sentence generator. Each dawn must explain what became publicly observable during the immediately preceding night, deliver authorized private findings, and advance the selected case through useful, verifiable discoveries. Reopening a report must return the same facts.

Reviewed: all 40 case definitions, all 16 evidence types, all 18 role definitions, the seven standard compositions, standard/Blitz timing, all nine phase enum values, the hint/evidence handlers and buttons, command/callback/text routing, night resolution, and the relevant report/persistence paths. The route registry had 74 endpoints at initial inspection and **75 at the closing check**, after a concurrent editor added `surrender`. Section 9 inventories all 75 and examines the relevant paths in detail.

**Meaning of “playlist”:** the source has 40 selectable cases and two timing modes (`Game.blitz`: standard or Blitz); it has no separate playlist model. This document covers every case in both modes. Eight optional thematic playlists in section 6 group the existing cases editorially; they are proposed navigation/content bundles, not existing endpoints. Tutorial, rematch, parallel tables, and anonymous voting are also covered as modifiers/journeys.

This document supplements [report.md](report.md), [rules.md](rules.md), and [evidence-and-roles.md](evidence-and-roles.md). The owner's requirement for player approval before day becomes night remains authoritative. Reading hints, exhausting the deck, a timeout, or receiving a lab result must never substitute for that approval.

### Evidence limits and reproducibility

The checkout contains concurrent application edits. This is a review of observed source, not a live Telegram playtest or certification of every possible game state. Existing tests were inspected; the previous audit counts are historical and are not a passing result for this checkout. No networked bot was started and no production database or `.env` was read.

Read-only checks during this task:

- Parsed the route registry: 74 endpoint names.
- Parsed the case catalog: 40 cases and 10 daily base templates.
- Reproduced the current template-selection formula for days 1–10: **all 40 cases repeat at least one base template**. Changing a random seed by day does not guarantee novelty.
- Checked the event dictionary's first-token lookup: blackout and anonymous-witness keys do not match; the single-word storm key does. This is separate from the engine's witness extra-card effect.

Source fingerprints captured during inspection; function names are the primary references because line numbers may move:

| Source | SHA-256 |
|---|---|
| `karagah/cases.py` | `dbb8395ad8f590e88073bd5bebf1ba083bf5c2d19931c0a6cda53d5f7927c2d8` |
| `karagah/engine.py` | `b0de93fbb0d2f530a78f5e5da5345dc92a9c77ebb29f16d168a71e6b61f5363d` |
| `karagah/dialogue.py` | `9719414c425c36f6da94ee76071b2f0f96e25edecc6e9f7f7f3c2a76c9feae6c` |
| `karagah/bot.py` | `4712e9e5b45fc1a990411901d714c45dd2bfd9bd5e15c439982abb6a832b7106` |
| `karagah/menus.py` | `cd2350d34d8739c57cdbffb40dcf87a51b9d3d9004a3633fb00faf48113c35a0` |
| `karagah/ui.py` | `13244377e0b888b2c128e35f83857836e10090f220e2af717fbb1124bbcf736b` |
| `karagah/telegram_app.py` | `9909a0d0c84aa87921ae5553db35aeae148e6d76f8a4fd4bc19c0262677b9bd5` |
| `karagah/models.py` | `312582f663f72506ddbcde17187e8df6b35bc8eb04e895e5fa413160b8fc97c6` |
| `karagah/roles.py` | `fc05a647aa34ecaf5269bd5b9733edf527b9bfac8181a60a4a0c20230cb6b79a` |

**Closing source-change note:** engine, bot, menus, UI and Telegram adapter changed after the fingerprints above. The 74 original routes remained, and `surrender` was added as route 75. Its handler/engine and the newly introduced live-board refresh path were inspected separately below. The main findings describe the initial source; they are implementation hypotheses to recheck against newer edits, not claims that every subsequent change was regression-tested. Cases, dialogue, models and roles still matched their initial fingerprints at the closing hash check.

The new surrender path marks the player no longer alive, removes their own actions/ballots, clears their suspect slot if applicable, and may set an interrogation phase to morning without resolving a night. **Hint implication:** this is a withdrawal event, not a new dawn or a forensic death. Preserve the last resolved-night report and do not generate evidence for an unresolved night. The new `board_of` / adapter board-refresh path currently targets lobby and voting screens; future dossier refresh must apply the same public/private restrictions and never turn a private finding into a group board.

## 2. Research translated into this game's requirements

These are design references, not proof that a particular Mafia balance or win rate will work.

1. **Redundant investigative routes.** Justin Alexander recommends multiple independent clues for conclusions essential to a mystery. Adaptation here: every important case conclusion should have three authored observation opportunities, including at least one public route that survives the loss of an investigative role. Three repetitions of one witness are one source, not three confirmations. Do not translate this into three automatic alignment reveals. [The Three Clue Rule](https://www.thealexandrian.net/creations/misc/three-clue-rule.html).
2. **Separate a next step from an explanation.** Pelgrane distinguishes leads that point to another scene, clues that explain events, optional hints, and background details. Adaptation here: every significant card needs a legal next action, while atmosphere stays optional. Essential progress must not depend on a role absent from the selected composition. [A Taxonomy of Investigations](https://pelgranepress.com/2023/03/08/a-taxonomy-of-investigations/).
3. **Design for Telegram's actual transport.** `sendMessage` permits 1–4096 characters after entity parsing, and inline-button `callback_data` permits 1–64 bytes. Use a short dawn digest, paginated detail, and opaque callback tokens. Test Persian text and emoji in bytes as well as display length; do not put evidence prose or private role IDs in callbacks. [Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage), [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton).

The clue budgets, schedules, role contracts, example content, and acceptance thresholds below are this project's **proposals**. They are not borrowed rules or empirically validated balance claims.

## 3. Source findings, ordered by repair dependency

Priority: P0 = truth/privacy/game integrity; P1 = necessary usefulness/delivery; P2 = polish and tuning.

| ID | Priority | Observed problem and source | Required direction |
|---|---|---|---|
| H01 | P0 | `cases.day_clue` picks assertions from templates without a supporting event: moved body, withdrawal, torn page, altered clock. A scene name makes text specific-looking, not true. | Generate case discoveries from a stored prelude ledger and night observations from resolved night events. Every assertion has a source ID. |
| H02 | P0 | `dialogue.CASE_TELLS` and `FACT_TELLS` invent statements, clothing, flashlight state, and reactions for a human suspect. | Generate questions from evidence; quote only messages actually sent by that player. NPC narration must be explicitly labeled and limited to NPCs. |
| H03 | P0 | `_build_traces` says a killer is among a dead player's visitors, including indirect deaths where that is false. | Record death causes and visit outcomes separately. Report presence without asserting causation. |
| H04 | P0 | `menus.evidence_kb` lists all six cards. `h_interp` retrieves any case card; lab/expose also accept unrevealed codes. | Visibility checks before both rendering and mutation; hidden-card probing must not disclose existence/title. |
| H05 | P0 | `submit_lab` lacks actor authorization; `vote_interp` lacks membership/status/phase checks. Officer hints check officer ID/suspect but not complete live-state eligibility. | Shared server-side authorization for each read/write, including direct commands and old callbacks. |
| H06 | P0 | `_new_day_hint` counts action records as public visits near the scene, although actions have player targets, not scene coordinates. `_build_traces` uses a similar exclusion list, while its prose mentions watchers as visitors despite excluding watch. | Define successful physical visits, remote observations, and blocked attempts explicitly. Do not invent a location or count every submitted action as travel. |
| H07 | P0 | `_deliver_night_info` reports hidden targets as clean / zero visits. Public traces can still expose movement. | Pick and document a concealment contract: proposed result is “observation unavailable,” consistently across channels. Absence of evidence is not innocence. |
| H08 | P0 | `day_clue` says no death was a decision, although protection, storm, missed actions, or other causes may explain it. | Public output says no new death was confirmed. Reasons appear only where an authorized observation establishes them. |
| H09 | P0 | Fake clues are appended after the real clue with a distinctive candle prefix; `today_hint()` returns the last item, potentially only a fake. Unlimited submissions can flood the daily list. | Store testimony-like claims with hidden provenance, comparable styling/order, finite budget, and a verification route. Never let a forged claim replace a verified dawn header. |
| H10 | P0 | `officer_hints` infers events by matching rendered names/traces and note prefixes for day N or N−1. Stress is partly alignment-derived. | Query typed observations scoped to the relevant night/custody episode. Names are display text, not identity keys. Do not use body-language hints as an alignment oracle. |
| H11 | P1 | `h_dawn` renders evidence/hints/traces, while `Game.tick` discards the resolution payload and `h_tick` sends a short status. | One stored dawn report rendered identically after manual and scheduled resolution; separate actor-neutral private delivery. |
| H12 | P1 | Lab completion adds only “origin established; narrow interpretations” to a log. | Deliver an actual bounded finding, eliminated/surviving hypotheses, source and due day. Store/reopen the result. |
| H13 | P1 | Base cards always mark E2/E5 misleading. Six generic cards and four generic interpretation templates are reused across the catalog. | Case-specific hypotheses and context, per-match randomized opaque identities, no truth flag derived from position. |
| H14 | P1 | After six days the last card is appended repeatedly; reporter and witness reveal slots by day, which can collide with later normal reveals. | Select genuinely unrevealed eligible discoveries; count unique cards. Exhaustion produces a truthful delta report, not duplicate progress. |
| H15 | P1 | The daily seed repeats templates; blackout/witness event tails fail the first-token dictionary lookup. | Stored discovery schedule and typed event IDs; test novelty on source facts, not wording alone. |
| H16 | P1 | Forensic ability selects a player but examines the day's fixed card. Coroner gives the case weapon and 23:15 for later deaths. | Forensics selects evidence; coroner selects/receives a specific casualty's actual resolved cause and time window. |
| H17 | P1 | Reporter extra cards appear in state/log but the dawn response renders only the main card. New private findings accumulate in notes without a unified delivery receipt. | Report lists every newly released card; private inbox records unread findings and retries delivery safely. |
| H18 | P1 | Officer hints are the only `/hints` meaning; general “سرنخ‌ها” buttons mislead ordinary players seeking today's clues. | Public daily dossier and explicitly named private officer hints; preserve old command compatibility without leaking private output. |
| H19 | P1 | No standard composition includes reporter, lawyer, grocer, or smuggler. Spy repeats publicly nominated suspect; grocer has no daily delivery. | Do not require these roles for any standard case. Add separate tested rotations before advertising their pathways as playable. |
| H20 | P0 | Current callbacks carry command/card IDs without match/day binding; pending text is per user. `handle` logs the first 40 argument characters. | Bind interactions to match/actor/day; protect private note, question, answer, fake-clue, and action bodies from general audit logs. |
| H21 | P1 | Static case timeline/twist is not connected to player alibis or a typed event ledger; `Evidence.points_to` is not enough to make current dictionary cards causal. | Build a consistent prelude with access/observation sets before distributing clues. Distinguish that fictional crime from actual subsequent night events. |
| H22 | P1 | Laboratory delay is two days, while Blitz shortens custody to one night; reports can arrive after an irreversible decision. | Publish an absolute due dawn; ensure a public counter-evidence route before the verdict/appeal deadline. Blitz proposal: one-night lab latency. |
| H23 | P1 | Free-form will/shared note/defense is easily mistaken for a bot finding; final reconstruction is the last 12 log lines. | Label attributed claims. At end, resolve every material clue and planted claim from the ledger, without publishing unrelated private notes. |
| H24 | P2 | `abilities_text` says lab is always available; menus do not consistently reflect role/custody/phase. Interpretation tally counts all votes beside the winning text. | Context-aware controls and accurate “supporting votes / valid total,” with ties displayed explicitly. |

Do not reapply fixes solely because an older audit mentions them. For example, the inspected engine already separates mature poison from storm-cancelled direct attacks. The remaining report problem is that later narrative can still misdescribe those causes.

## 4. Hint contract: what every piece of information must mean

### 4.1 Two timelines, never silently merged

- **Case prelude:** the original named victim, scene, access records, and authored mystery before players' Night 1. All discoveries about it say “پروندهٔ اولیه”. Discovering a prelude record on Day 3 does not mean that event happened on Night 3.
- **Live match:** actual player actions/outcomes on Night N, custody events, genuine submitted testimony, and public observations. These say “شب N”.
- Do not attach a real player's name to a prelude act unless that fictional assignment was stored consistently at match creation and the player received the relevant role-play information. Do not tell a player they said something they never said.
- Prelude facts may narrow opportunity sets; they must not force every member of the criminal team to have personally committed the initial crime. Later recruitment changes alignment prospectively, not the historical ledger.

### 4.2 Minimum data contract for Claude

This is a schema specification, not implementation code. Each clue needs: immutable clue ID; match ID; case ID; case-version/seed; source event IDs; original incident/night number; discovery day; public/private visibility; allowed recipients; source type; observation text; uncertainty; relevant hypotheses; legal verification options; release conditions; expiry/relevance window; superseded-by link; and end-game explanation.

Keep secret provenance separate from public presentation. Authentication, relevance, source reliability, and guilt are separate facts. A real fingerprint can be old; a planted hair can genuinely belong to an innocent person; a witness can be honestly mistaken. A vote never alters the truth ledger.

Store one immutable `DawnReport` per resolved night with public facts, newly released clue IDs, due lab results, public custody changes, private result references, and delivery status. Resolve once; retry/reopen without regenerating facts or consuming additional actions. Persist the event/visibility state before dispatch. A failed DM stays private and available to its owner.

### 4.3 Clue quality checklist

Every **significant** clue must answer: what was observed; when; by which permitted source; what it supports; what it does not prove; which available action can test it; and what decision may change. An item without a decision or verification path is background, and must not consume a scarce power.

Proposed daily budget: one core case discovery, one live-night observation when available, one comparison/counter-evidence update, and at most one short rumor. These are maxima, not a requirement to fabricate four events. Due lab/private results are delivered even if the summary must paginate. Provide a public explanation route for any frame that could drive an irreversible verdict.

Planted claims use the same source class as ordinary unverified claims (“گزارش تأییدنشده”), not the same authority as verified system outcomes. Players may bluff in their own messages; the bot must not impersonate a verified lab result on their behalf. Proposed team budget: one editable planted claim per night, committed at resolution. Assignment to a particular criminal role is a balance decision to settle in `rules.md`; do not silently grant every team member every specialist power.

### 4.4 Progressive help, on request

Assistance reuses already visible facts. It does not disclose secret authorship or future cards.

| Level | Button | Allowed content | Example |
|---|---|---|---|
| 0 | «گزارش امروز» | Normal factual digest | «دو ثبت زمانی دربارهٔ ورود وجود دارد.» |
| 1 | «از کجا بررسی کنیم؟» | Point to two visible sources | «زمان دوربین را با رسید ورود مقایسه کنید.» |
| 2 | «چه چیزی جور نیست؟» | Explain the specific comparison | «این دو ثبت از ساعت‌های متفاوت‌اند؛ اختلاف ساعت را بررسی کنید.» |
| 3 | «روش بررسی» | Explain a legal procedure, not guilt | «از جدول اصلاح ساعت استفاده کنید؛ سپس زمان ورود را با بازهٔ حادثه بسنجید.» |

Repeated requests return the same level/result. These are proposed public help buttons, distinct from the officer's exclusive evidence access. Do not add a “reveal killer” shortcut.

## 5. Phase and mode specification — applies to every case below

### 5.1 All phase values

| Phase | Public content | Private content and controls | Must not happen |
|---|---|---|---|
| LOBBY | Case title/teaser if selected, mode, role-pool rules, explanation of evidence categories | DM readiness and tutorial | Show twist, future cards, assigned secret roles, or populated night report |
| NIGHT N | Frozen previous public dossier; “نتایج شب N پس از پایان شب منتشر می‌شود” | Own eligible ability, target/card selection, committed choice; previous personal findings | Live action counts, fresh observation before resolution, hints causing phase advance |
| MORNING / Day N | Full report of Night N, new prelude discovery, due results, public custody changes | New role findings and officer's refreshed dossier | Substitute case weapon for live death cause; omit timer-triggered reports |
| DISCUSSION | Visible dossier, factual comparison, unverified attributed claims, interpretation poll | Own notes and voluntary sharing preview | Poll consensus labeled as proof; forced night transition |
| VOTE | Stable public evidence cutoff and defense links | Eligible private ballot; own historical notes | New accusation-bearing random clue mid-ballot; hint click counted as vote |
| INTERROGATION / Night N | Custody status and last public dossier; no room transcript | Officer: questions linked to actual evidence; suspect: real reply controls; others: legal night actions | Synthetic statements attributed to the suspect; another night increment for entering the room |
| JURY | Frozen public case packet, attributed defense, counter-evidence and unresolved limitations | Private eligible jury ballot; officer evidence remains private unless explicitly shared under rules | Private role findings dumped automatically; late lab result silently ignored |
| COURT | Currently an enum value without a distinct hint handler; reuse the validated verdict packet if this phase becomes reachable | Only explicitly authorized verdict controls | Invent a new active phase in hints alone; dead-end menu |
| END | Winning reason, full causal reconstruction of material clues, resolved red herrings, permitted role reveal | Personal notes retained privately | Automatically publish every private message; keep actionable old buttons |

If genuinely material exculpatory evidence arrives during a ballot, proposed policy: pause the ballot, publish a visibly versioned amendment, allow review, and restart the ballot consistently. Do not silently change the dossier under existing votes. Apply the same policy to both teams.

### 5.2 Daily schedule without a fixed end day

| Dawn | Standard content stage | Blitz content stage | Ongoing action |
|---|---|---|---|
| Day 1 after Night 1 | Establish scene and first measurable discrepancy (case D1) | Same D1, short digest with optional details | Compare observations, select first verification |
| Day 2 after Night 2 | Independent cross-check (D2); due public/role findings | D2; one-night lab results | Challenge a concrete alibi/source, not demeanor |
| Day 3 after Night 3 | Test an innocent explanation or red herring (D3) | D3, plus D4 only if needed before an imminent irreversible decision | Reassess suspicion with counter-evidence |
| Day 4 after Night 4 | Context/twist payoff (D4), subject to prerequisites | Unreleased D4 or a new live-night delta | Explain the mechanism without auto-identifying a role |
| Day 5 | Oldest unresolved contradiction, scoped to that case's objects/timestamps | Same rule in compact form | Check one unresolved claim against a new permitted observation |
| Day 6 | Chain of custody / source independence review for a still-disputed item | Same rule | Resolve a planted/irrelevant lead if evidence supports it |
| Day 7 and every later day N | New live-night outcomes + due checks + versioned updates; no invented new prelude fact after exhaustion | Same rule | Continue Night N → Day N until a valid end condition |

Stages are opportunity order, not a demand that all matches last four days. If a match ends on Day 1, produce its ending report; do not delay victory to show the remaining content. If a release needs an unavailable prerequisite, deliver a public investigative lead and preserve that discovery for later. Do not offer a lab due after the only remaining appeal opportunity as the sole way to refute guilt.

For an exhausted quiet day: «صبح روز {N} — گزارش شب {N}: مرگ تازه‌ای تأیید نشد. یافتهٔ تازه‌ای از پروندهٔ اولیه در دست نیست. ادعای {C} هنوز بررسی نشده؛ مقایسهٔ {A} و {B} در دسترس است.» Omit the last clause if no such claim/comparison exists. Never promise endlessly unique facts from a finite case.

### 5.3 Seat-count and journey modifiers

| Context | Required adaptation |
|---|---|
| 4 players | Public timing/source comparison is essential: detective and officer cannot be the only surviving route. No doctor/watcher/forensics-dependent clue. |
| 5 players | Add protection ambiguity. No death does not confirm doctor success or expose their target. |
| 6 players | Scapegoat means suspicious alignment/fingerprint is not proof of criminal-team membership. Supply counter-evidence before life jail. |
| 7 players | Frame, coroner, and fate-pair possibilities: separate contact, original cause, and linked consequence. |
| 8 players | Forensics/watcher/coroner can corroborate different dimensions; no doctor exists in this composition. Never offer doctor as the required counterplay. |
| 9 players | Spy/hunter/scapegoat; do not require coroner or forensic specialist absent from this roster. Public cause uncertainty remains honest. |
| 10 players | Direct attack, poison, serial attack, hunter and linked consequences can coexist. Report each casualty separately; visits this night need not explain older poison. |
| Blitz | Source halves phase times and shortens custody. Proposed hint budget is unchanged; shorten presentation, not evidentiary fairness. One-night lab proposal needs implementation and tests. |
| Tutorial | Fixed illustrative facts, visible “نمونهٔ آموزشی”, no live-table actions or permanent clues. Explain claims vs findings. |
| Rematch | Fresh match ID and hidden assignments; same case may recur, but old tokens cannot operate it. Known narrative twist is not a current player's guilt. |
| Parallel tables / `/table` | Every dossier and action is table-bound. Switching the active table cannot retarget an old card button. |
| Anonymous voting | Evidence is unchanged. Do not reveal ballot authors through interpretation summaries, report metadata, or hint text. |
| Spectator / eliminated | Public dossier only during play; no private findings, votes, lab requests, or new interpretations. |
| Paused / resumed | Read existing evidence; do not resolve, release, reroll, or consume abilities while paused. |

## 6. Original case content: all 40 cases, grouped into proposed playlists

**Authoring status:** the following 160 D1–D4 clue texts are proposed fictional content, not observations of existing game events. Claude must first create the corresponding stored prelude facts and verification records, then release them on the specified dawn. Where the selected story variant does not contain that fact, use its authored alternative; never print an unsupported claim. None of these texts is a real-world forensic instruction.

Each row provides four distinct discovery stages plus a case-specific follow-up. That follow-up is the **continuing Day 5+ investigation** for the row, instantiated only from unresolved records. Phase delivery and standard/Blitz timing are defined in section 5, so the same case is not given conflicting truths across modes.

Required playable binding for every row: at least two plausible access/observation candidates at first release, a known innocent explanation, three independent observation opportunities for the key conclusion, and one public route. Candidate names come from match setup, never arbitrary names selected to make the current suspect look guilty. Authored mechanisms may be discoverable; secret team identities remain governed by game rules.

### Playlist A — «خانه‌های خاموش» / domestic scenes

| Case | D1: first observation | D2: independent check | D3: innocent explanation/correction | D4: contextual payoff | Day 5+ follow-up / verification |
|---|---|---|---|---|---|
| 01 — شب بارانی عمارت لواسان | «پروندهٔ اولیه: رد جابه‌جایی شمعدان از گردوغبار قدیمی روی میز جداست.» | «ثبت ورود کتابخانه با زمان تحویل پوشهٔ وصیت‌نامه یکسان نیست.» | «اثر روی جلد پوشه پیش از آخرین ملاقات ثبت شده؛ وجود آن به‌تنهایی حضور هنگام حادثه را ثابت نمی‌کند.» | «دو نسخهٔ وصیت‌نامه در بند وارث متفاوت‌اند؛ زمان تعویض نسخه هنوز باید روشن شود.» | Compare cover/version handover and library access; test who could reach the replacement window, not who inherits most. |
| 05 — سکوت ویلای شمال | «پروندهٔ اولیه: یک تکه از پاشنه کنار درِ تراس پیدا شد، نه کنار محل سقوط.» | «عکس پیش از مهمانی نشان می‌دهد کفش آن زمان سالم بوده است.» | «رد کفش دوم کنار گلدان مربوط به آبیاری پیش از مهمانی است.» | «شکستن پاشنه و سقوط دو رویداد جدا در تایم‌لاین‌اند؛ ترتیب آن‌ها را از شهادت‌ها بسنجید.» | Compare photo, access window and actual submitted account; do not infer a push from a broken shoe alone. |
| 16 — خانه‌ی بی‌برق | «پروندهٔ اولیه: زمان خاموشی راه‌پله با خاموشی ثبت‌شدهٔ ساختمان فرق دارد.» | «ثبت سرویس، وضعیت پله را پیش از خاموشی نشان می‌دهد.» | «رد تعمیرکار از نوبت سرویس قبلی است و حضور هنگام حادثه را ثابت نمی‌کند.» | «دستکاری فیوز و لغزندگی پله باید جدا بررسی شوند؛ یک نشانه به‌تنهایی علت مرگ نیست.» | Reconcile power record, service record and last safe passage; distinguish this prelude outage from a later random blackout. |
| 17 — پرونده‌ی اتاق قفل‌شده | «پروندهٔ اولیه: کلید در جیب مقتول پیدا شد؛ زمان قفل‌شدن هنوز معلوم نیست.» | «ثبت بازدید مجموعه نشان می‌دهد در پیش از کشف جسد یک بار باز بوده است.» | «رد روی جعبهٔ سکه با بازدید مجاز قبلی سازگار است.» | «وجود کلید داخل اتاق ثابت نمی‌کند هیچ‌کس پس از حادثه به در دسترسی نداشته است.» | Compare door state, access record and collection inventory; do not add an unrecorded secret passage. |
| 40 — راز خانه‌ی متروکه | «پروندهٔ اولیه: رد بازشدن پنجره در سمت بیرونی قاب دیده می‌شود.» | «گزارش بازدید ملک، وضعیت پنجره را پیش از آخرین ورود ثبت کرده است.» | «رد روی راه‌پله از بازدید قبلی مشتری است؛ زمانش با حادثه یکی نیست.» | «دو سند برای ملک وجود دارد؛ اختلاف سند، انگیزهٔ احتمالی است و هویت عامل را ثابت نمی‌کند.» | Reconcile window state, visits and document handover; test access to the outside without inventing travel. |

### Playlist B — «آخرین پذیرایی» / food and hospitality

| Case | D1 | D2 | D3 | D4 | Day 5+ follow-up / verification |
|---|---|---|---|---|---|
| 02 — پرونده‌ی چای تلخ | «پروندهٔ اولیه: دو فنجان از یک قوری پر شدند، اما افزودنی یکسانی نداشتند.» | «برگهٔ پذیرایی می‌گوید قندان میان دو نوبت روی میز دیگری بوده است.» | «نمونهٔ چای ساده، ادعای آلوده‌بودن همهٔ قوری را تأیید نمی‌کند.» | «یافتهٔ آزمایش به قندان مربوط است؛ داشتن فنجان به‌تنهایی دسترسی به منبع آلودگی را ثابت نمی‌کند.» | Compare serving order, sugar-bowl custody and sample IDs; keep prelude poisoning separate from a live poisoner action. |
| 06 — پرونده‌ی رستوران نیمه‌شب | «پروندهٔ اولیه: جای یک چاقو در فهرست ابزار آشپزخانه خالی نیست؛ ابزار کشف‌شده باید جدا شناسایی شود.» | «رسید تحویل وسایل مهمانی، ابزار دیگری را در همان روز ثبت کرده است.» | «اثر آشپز روی دستهٔ ابزارِ معمول، مربوط به آماده‌سازی غذاست.» | «چاقوی کشف‌شده از ست شخصی سرآشپز نیست؛ مسیر ورود آن از هویت صاحب آشپزخانه مهم‌تر است.» | Compare tool inventory, delivery and handling window; a borrowed tool does not prove its owner used it. |
| 11 — قتل در جشن نامزدی | «پروندهٔ اولیه: محل دو لیوان پس از یک نوبت پذیرایی عوض شده است.» | «تصویر میز، جای اولیهٔ لیوان‌ها را مستقل از گفتهٔ مهمانان نشان می‌دهد.» | «اثر روی لیوانِ سالم با جابه‌جایی هنگام پذیرایی سازگار است.» | «نام صاحب اولیهٔ لیوان با آخرین مصرف‌کننده یکسان نیست؛ ترتیب دست‌به‌دست‌شدن را دنبال کنید.» | Reconstruct glass custody using photo, tray record and actual claims; no guilt by old fingerprint. |
| 20 — پرونده‌ی هتل جنگلی | «پروندهٔ اولیه: کارت سوئیت ۲۰۲ دو ثبت ورود دارد؛ این دو ثبت لزوماً دو نفر نیستند.» | «زمان تحویل کیک بین دو ثبت کارت قرار می‌گیرد.» | «یکی از ثبت‌ها با بازشدن مجدد در برای تحویل وسایل سازگار است.» | «برای بررسی آلودگی کیک، زمان دسترسی به بسته را از زمان ورود به سوئیت جدا کنید.» | Compare card log, package seal and delivery account; a card identifies access, not necessarily its bearer. |
| 25 — مرگ صبح جمعه | «پروندهٔ اولیه: نام دریافت‌کنندهٔ چای با فردی که نخست برایش آماده شده بود فرق دارد.» | «ثبت پذیرایی، جابه‌جایی سینی را پیش از مصرف نشان می‌دهد.» | «اختلاف بر سر زمین، به‌تنهایی زمان یا امکان دسترسی به چای را مشخص نمی‌کند.» | «چای صبحگاهی را فرد دیگری نوشیده است؛ هدف اولیه و قربانی واقعی را یکی فرض نکنید.» | Compare recipient, serving route and documented exposure; never infer motive from religious identity. |
| 39 — قتل در کافه کتاب | «پروندهٔ اولیه: برای دو فنجان سفارش ثبت شده، اما فقط یک فنجان روی میز مانده است.» | «ثبت شست‌وشو نشان می‌دهد فنجان دوم پیش از رسیدن مأموران شسته شده است.» | «رسید اجاره اختلاف مالی را نشان می‌دهد، نه حضور هنگام آماده‌کردن قهوه.» | «شستن فنجان دوم یک مسیر بررسی است؛ بدون زمان‌بندی، پنهان‌کاری یا نظافت عادی هر دو ممکن‌اند.» | Compare order, washing sequence and access to service area; recover context rather than claim a clean cup proves guilt. |

### Playlist C — «رد در مسیر» / journeys and routes

| Case | D1 | D2 | D3 | D4 | Day 5+ follow-up / verification |
|---|---|---|---|---|---|
| 03 — قتل در آسانسور برج آرمیتا | «پروندهٔ اولیه: میان دو بخش تصویر آسانسور فاصله‌ای وجود دارد؛ مسیر بیرون از کابین ثبت جدا دارد.» | «ثبت طبقه با ساعت دوربین اختلاف دارد؛ زمان‌ها هنوز قابل مقایسهٔ مستقیم نیستند.» | «اثر روی دکمهٔ طبقهٔ ۱۴ می‌تواند از رفت‌وآمد عادی پیش از حادثه باشد.» | «پس از هم‌زمان‌سازی، وقفهٔ تصویر ۹۰ ثانیه است؛ فقط دسترسی در این بازه را بررسی کنید.» | Reconcile floor log, calibrated camera and maintenance access; absence from camera is not an alibi. |
| 07 — قطار ۲۳:۴۰ مشهد | «پروندهٔ اولیه: دو رسید معتبر برای یک جای کوپهٔ ۷ پیدا شده است.» | «زمان کنترل بلیت‌ها نشان می‌دهد هر دو رسید در یک نوبت بررسی نشده‌اند.» | «یکی از مسافران پیش از حرکت جایش را عوض کرده؛ شمارهٔ کوپهٔ روی بلیت، محل تمام شب او نیست.» | «فروش دوبارهٔ بلیت فرصت جابه‌جایی ایجاد کرده است؛ صاحب رسید را با شاهد ورود تطبیق دهید.» | Compare ticket issuance, conductor check and real alibi; keep transaction ownership distinct from physical presence. |
| 12 — سایه‌ای در پارکینگ | «پروندهٔ اولیه: شمارهٔ قرارداد خودرو با نام استفاده‌کنندهٔ آن شب یکسان نیست.» | «رسید تحویل خودرو، وضعیت آن را پیش از ورود به پارکینگ ثبت کرده است.» | «رد صاحب ثبت‌شدهٔ خودرو از تحویل قبلی باقی مانده است.» | «خودرو اجاره‌ای بوده؛ فرصت دسترسی بین تحویل و حرکت را بررسی کنید، نه فقط مالکیت را.» | Compare handover, inspection and parking access; a rental contract is not a crime admission. |
| 19 — قتل در ماهیگیری خزر | «پروندهٔ اولیه: بخش جداشدهٔ طناب با فرسودگی بقیهٔ طناب یکسان نیست.» | «عکس آماده‌سازی قایق، وضعیت طناب را پیش از حرکت ثبت کرده است.» | «گره قدیمی به سفر قبلی مربوط است؛ آن را با تغییر تازه یکی نگیرید.» | «طناب لنگر تازه تغییر کرده؛ اختلاف سهم صید فقط یک زمینه است و زمان دسترسی را ثابت نمی‌کند.» | Compare predeparture condition, storage access and recovered ends; keep mechanism description abstract. |
| 31 — مرگ در اتوبوس شبانه | «پروندهٔ اولیه: سه بلیت، نام خوانای مسافر ندارند؛ شمارهٔ صندلی آن‌ها مشخص است.» | «ثبت توقف‌ها نشان می‌دهد همهٔ دارندگان این بلیت‌ها هم‌زمان سوار نشده‌اند.» | «یک صندلی در طول مسیر عوض شده؛ شمارهٔ بلیت محل ثابت فرد را ثابت نمی‌کند.» | «مسیر قاچاق می‌تواند انگیزه باشد، اما مسیر حرکت داخل اتوبوس نیاز به شاهد جدا دارد.» | Compare boarding, seat changes and stop records; missing names alone must not mark criminals. |
| 37 — مرگ در برف | «پروندهٔ اولیه: دو قطعهٔ طناب از یک رشته‌اند؛ گزارش اولیه علت جدایی را مشخص نکرده است.» | «ثبت گروه صعود نشان می‌دهد طناب پیش از آخرین استراحت سالم بوده است.» | «اثر روی طناب می‌تواند از تقسیم تجهیزات هنگام شروع صعود باشد.» | «بررسی پرونده، بریدگی را از پارگی عادی جدا می‌کند؛ هنوز باید زمان دسترسی روشن شود.» | Compare equipment handover, condition record and route windows; do not equate insurance benefit with guilt. |

### Playlist D — «چرخ‌های خاموش» / workshops and machinery

| Case | D1 | D2 | D3 | D4 | Day 5+ follow-up / verification |
|---|---|---|---|---|---|
| 04 — مرگ در کارگاه سفال | «پروندهٔ اولیه: وضعیت قفل کوره با گزارش پایان کارگاه فرق دارد.» | «ثبت خروج شاگردان نشان می‌دهد کارگاه پس از پایان کلاس دوباره باز شده است.» | «اثر خاک روی لباس یکی از حاضران از جلسهٔ ساخت ظرف است.» | «قفل از بیرون بسته شده بود؛ دسترسی به قفل را از حضور معمول در کارگاه جدا کنید.» | Compare closure checklist, re-entry record and key custody; artistic rivalry is context only. |
| 18 — مرگ در سالن بدنسازی | «پروندهٔ اولیه: گیرهٔ ثبت‌شده در فهرست هالتر هنگام کشف صحنه در جای خود نیست.» | «تصویر آغاز تمرین، وجود گیره را نشان می‌دهد.» | «اثر روی میله با استفادهٔ عادی چند ورزشکار سازگار است.» | «تغییر وضعیت گیره در فاصلهٔ دو ثبت رخ داده؛ بررسی مکمل‌ها جای بررسی این بازه را نمی‌گیرد.» | Compare equipment condition and access between sets; distinguish a distracting commercial dispute. |
| 21 — راز چاپخانه | «پروندهٔ اولیه: بخشی از فاکتور سوخته با شمارگان ثبت‌شدهٔ چاپ تطبیق ندارد.» | «دفتر سفارش، یک تغییر پس از پایان شیفت را ثبت کرده است.» | «لکهٔ جوهر روی لباس از کار عادی چاپخانه قابل توضیح است.» | «فاکتور و سفارش دو نسخهٔ متفاوت از معامله‌اند؛ زمان تغییر سند را با دسترسی به دستگاه مقایسه کنید.» | Compare order versions, machine session and paper fragments; no guilt from occupation-related residue. |
| 23 — قتل در نمایشگاه خودرو | «پروندهٔ اولیه: زمان حرکت لیفت با حضور ثبت‌شده کنار پنل محلی هم‌پوشانی ندارد.» | «ثبت کنترل، یک فرمان را از مسیر دیگری نشان می‌دهد.» | «اثر روی پنل می‌تواند از آزمایش ایمنی پیش از بازشدن نمایشگاه باشد.» | «فرمان از راه دور ثبت شده؛ حضور نداشتن کنار پنل، به‌تنهایی دسترسی را رد نمی‌کند.» | Compare controller custody, command timestamp and access record; do not supply real sabotage instructions. |
| 24 — پرونده‌ی معدن متروکه | «پروندهٔ اولیه: موجودی مواد ثبت‌شده با موجودی تحویل‌گرفته‌شده یکسان نیست.» | «دفتر ورود تونل ۴، یک فاصلهٔ ثبت‌نشده دارد.» | «گردوغبار روی کفش میان چند مسیر مشترک است و فرد مشخصی را تعیین نمی‌کند.» | «کسری موجودی و ریزش باید با یک بازهٔ دسترسی مشترک پیوند بخورند؛ هم‌زمانیِ تقریبی کافی نیست.» | Compare inventory, independent shift record and tunnel access; keep hazardous mechanism non-operational. |
| 34 — مرگ در تعمیرگاه | «پروندهٔ اولیه: برگهٔ پایان شیفت، جک را سالم ثبت کرده است.» | «رسید ورود قطعهٔ جایگزین پس از آن برگه صادر شده است.» | «رد روغن روی لباس همهٔ تعمیرکاران دیده می‌شود؛ نشانهٔ اختصاصی نیست.» | «جک میان آخرین بررسی و شروع شیفت بعد تغییر کرده؛ اصالت قطعه و دسترسی دو پرسش جدا هستند.» | Compare inspection, part provenance and workshop entry; defect alone does not establish intentional killing. |

### Playlist E — «نسخهٔ پنهان» / records, art and media

| Case | D1 | D2 | D3 | D4 | Day 5+ follow-up / verification |
|---|---|---|---|---|---|
| 08 — خون روی بوم نقاشی | «پروندهٔ اولیه: شمارهٔ پشت تابلو با فهرست تحویل گالری سازگار نیست.» | «عکس نصب نمایشگاه جزئیاتی دارد که در تابلوی فعلی نیست.» | «رنگ روی آستین با کار مرمت قبلی سازگار است.» | «تابلوی موجود بدل است؛ زمان تعویض اثر را از زمان حادثه جدا بررسی کنید.» | Compare transport inventory, installation photo and access; recovering the forgery does not identify a murderer. |
| 13 — مرگ نویسنده‌ی گمنام | «پروندهٔ اولیه: شماره‌گذاری دست‌نویس، نبودن بخشی از فصل آخر را نشان می‌دهد.» | «نسخهٔ ارسالی به ناشر آن بخش را پیش‌تر داشته است.» | «پیام تند ناشر پیش از اختلاف تازه نوشته شده و به‌تنهایی تهدید قتل نیست.» | «حذف فصل پس از ارسال نسخه رخ داده؛ افراد دارای دسترسی به هر نسخه را جدا کنید.» | Compare version receipt, paper custody and edit window; do not fabricate a confession in missing text. |
| 15 — قتل در ایستگاه رادیو | «پروندهٔ اولیه: فایل استودیو پس از پایان برنامه هم ادامه دارد.» | «صدای علامت پخش، زمان فایل را با ثبت اتاق فرمان پیوند می‌دهد.» | «صدای شنیده‌شده در پس‌زمینه از برنامهٔ بازپخش هم می‌تواند آمده باشد.» | «میکروفن روشن مانده بود؛ فقط صدای دارای منشأ روشن را به حضور زنده نسبت دهید.» | Compare transcript segments, broadcast log and recording source; no voice-recognition expertise required. |
| 26 — قتل در استارتاپ | «پروندهٔ اولیه: ساعت لاگ سرور با ساعت ثبت ورود ساختمان یکسان نیست.» | «یک رویداد مشترک در هر دو ثبت، مقدار اختلاف ساعت را مشخص می‌کند.» | «ورود با حساب مشترک، به‌تنهایی هویت کاربر پشت دستگاه را ثابت نمی‌کند.» | «پس از اصلاح ساعت، ترتیب ورودها عوض می‌شود؛ اتهام بر پایهٔ زمان خام را دوباره بسنجید.» | Compare calibrated logs, account access and real statements; no technical hacking needed outside the game. |
| 30 — راز آتلیه‌ی عکاسی | «پروندهٔ اولیه: توالی نگاتیوها از ۱۲ به ۱۴ می‌رسد.» | «برگهٔ تحویل نشان می‌دهد نگاتیو ۱۳ پیش از بایگانی وجود داشته است.» | «لکهٔ مواد روی دستکش با کار عادی تاریک‌خانه سازگار است.» | «نبودن نگاتیو ۱۳ یک حذف انتخابی است؛ محتوای آن تا بازیابی یا شاهد معتبر، نامعلوم می‌ماند.» | Compare receipt, archive access and recoverable contact sheet; never invent the missing image's contents on demand. |
| 36 — قتل در سینما | «پروندهٔ اولیه: مدت حلقهٔ تحویل‌شده با نسخهٔ ثبت‌شده چهار دقیقه اختلاف دارد.» | «گزارش نمایش قبلی، محل اختلاف را در توالی صحنه‌ها محدود می‌کند.» | «اثر روی حلقه از تعویض عادی فیلم هم می‌تواند باشد.» | «چهار دقیقهٔ حذف‌شده را از خرابی دستگاه جدا کنید؛ زمان دسترسی به حلقه تعیین‌کننده است.» | Compare run log, version record and handover; censorship motive is not an identity proof. |

### Playlist F — «پرونده‌های بسته» / institutions and transactions

| Case | D1 | D2 | D3 | D4 | Day 5+ follow-up / verification |
|---|---|---|---|---|---|
| 10 — پرونده‌ی داروخانه شبانه‌روزی | «پروندهٔ اولیه: شمارهٔ صفحه‌های دفتر دارو یک فاصله دارد.» | «رسید انبار، تحویلی را ثبت کرده که صفحهٔ مربوط به آن در دفتر نیست.» | «اثر روی کشوی دارو با شیفت عادی چند نفر سازگار است.» | «صفحهٔ حذف‌شده مسیر تحویل را پنهان کرده، اما تحویل‌گیرنده لزوماً مصرف‌کننده نیست.» | Compare receipt, shift record and page custody; use fictional sample categories, not medical mechanisms. |
| 14 — پرونده‌ی مدرسه‌ی قدیمی | «پروندهٔ اولیه: دفتر کلید فقط دو نسخهٔ انباری را ثبت کرده است.» | «زمان تحویل یکی از کلیدها با زنگ تفریح هم‌پوشانی دارد.» | «اثر روی در از جابه‌جایی وسایل پیش از حادثه باقی مانده است.» | «دو نسخه بودن کلید، دو مظنون قطعی نمی‌سازد؛ گردش کلید میان افراد باید بررسی شود.» | Compare key handover, room access and school schedule; no unrecorded duplicate used as a late solution. |
| 22 — مرگ در بیمارستان خالی | «پروندهٔ اولیه: تصویر بخش ایزوله قطع است، اما ثبت ورود بخش ادامه دارد.» | «برگهٔ تحویل شیفت یک اختلاف زمانی با گزارش نخست دارد.» | «حضور ثبت‌شدهٔ پرستار در بخش می‌تواند وظیفهٔ معمول باشد.» | «خاموشی دوربین مسیر بررسی را عوض می‌کند؛ ثبت مستقل ورود و تحویل را کنار هم بگذارید.» | Compare independent logs and fictional treatment record; later night deaths need their own cause report. |
| 29 — قتل در جلسه‌ی هیئت‌مدیره | «پروندهٔ اولیه: شمارهٔ نسخهٔ صورت‌جلسه با نسخهٔ بایگانی فرق دارد.» | «رسید چاپ، نسخهٔ دوم را پس از پایان جلسه ثبت کرده است.» | «اثر روی خودکار مشترک، استفادهٔ عادی در امضای جلسه را هم توضیح می‌دهد.» | «صورت‌جلسه بازنویسی شده؛ اختلاف متن را با ترتیب امضا و دسترسی به وسایل مقایسه کنید.» | Compare version history, attendance and pen custody; political benefit alone is insufficient. |
| 38 — پرونده‌ی صرافی | «پروندهٔ اولیه: چند اسکناس شماره‌سریال پیوسته دارند و به یک بسته مربوط‌اند.» | «رسید تحویل بسته، زمانی متفاوت از معاملهٔ ادعاشده دارد.» | «داشتن یک اسکناس از بسته می‌تواند نتیجهٔ معاملهٔ عادی بعدی باشد.» | «پیوستگی شماره‌ها مسیر بسته را نشان می‌دهد، نه هویت عامل قتل را؛ آخرین تحویل تأییدشده را پیدا کنید.» | Compare simulated serial list, receipts and handover; no real bank or personal data needed. |

### Playlist G — «نشانه‌های محیط» / environment and access

| Case | D1 | D2 | D3 | D4 | Day 5+ follow-up / verification |
|---|---|---|---|---|---|
| 09 — مرگ خاموش استخر | «پروندهٔ اولیه: گزارش آبِ استخر با ثبت نوبت قبل تفاوت دارد.» | «دفتر سرویس، زمان آخرین بررسی آب را مستقل ثبت کرده است.» | «وجود مواد نگهداری در انبار، به‌تنهایی نشانهٔ دستکاری نیست.» | «مقدار غیرعادی کلر باید با زمان حضور مقتول و دسترسی به تجهیزات سنجیده شود؛ علت مرگ را از آن حدس نزنید.» | Compare fictional sample report, service and attendance; distinguish environmental anomaly from confirmed cause. |
| 28 — مرگ در باغ‌وحش | «پروندهٔ اولیه: قفل قفس هنگام بررسی آسیب ظاهری ندارد.» | «ثبت تحویل کلید، یک نوبت دسترسی پیش از حادثه را نشان می‌دهد.» | «رد نگهبان کنار قفس با بازدید معمول روزانه سازگار است.» | «قفل بی‌آسیب، مسیر دسترسی را محدود می‌کند اما فرد استفاده‌کننده از کلید را تعیین نمی‌کند.» | Compare key chain, inspection and enclosure access; do not infer criminality from routine proximity. |
| 32 — پرونده‌ی مسجدجامع | «پروندهٔ اولیه: وضعیت نردهٔ گلدسته با تصویر بازدید قبلی فرق دارد.» | «دفتر تعمیرات برای این تغییر، ثبت هم‌زمانی ندارد.» | «رد ابزار از تعمیر قدیمی هم ممکن است باقی مانده باشد.» | «بازشدن نرده را با بازهٔ دسترسی مقایسه کنید؛ شایعهٔ گنج هنوز یک ادعاست.» | Compare condition photo, maintenance and access; a rumor must not acquire system-certified truth. |
| 35 — پرونده‌ی گلخانه | «پروندهٔ اولیه: یک جفت دستکش از فهرست ابزار گلخانه کم شده است.» | «رسید تحویل وسایل نشان می‌دهد دستکش‌ها پیش از آخرین شیفت موجود بوده‌اند.» | «خاک روی کفش میان مسیر باغ و گلخانه مشترک است و به‌تنهایی مسیر را تعیین نمی‌کند.» | «نبودن دستکش و اختلاف نمونهٔ کود دو موضوع جدا هستند؛ پیوندشان نیاز به ثبت دسترسی دارد.» | Compare inventory, fictional sample and work assignment; never claim glove ownership proves exposure. |

### Playlist H — «تماس و ترکیب» / materials and laboratory puzzles

| Case | D1 | D2 | D3 | D4 | Day 5+ follow-up / verification |
|---|---|---|---|---|---|
| 27 — پرونده‌ی خیاطی پاساژ | «پروندهٔ اولیه: رنگ نخ روی لباس با سفارش در حال دوخت متفاوت است.» | «دفتر سفارش، پارچه‌ای با همان رنگ را در نوبت قبلی ثبت کرده است.» | «انتقال نخ از پردهٔ پرو می‌تواند تماس بی‌ارتباط با حادثه را توضیح دهد.» | «هم‌رنگی نخ به‌تنهایی مالک را تعیین نمی‌کند؛ زمان و محل انتقال باید بررسی شود.» | Compare order swatches, fitting-room access and sample context; no magical individual identification from color. |
| 33 — قتل در آزمایشگاه دانشگاه | «پروندهٔ اولیه: وضعیت هود با چک‌لیست آغاز نوبت کار تفاوت دارد.» | «ثبت مستقل تجهیزات، زمان تغییر وضعیت را در یک بازه محدود می‌کند.» | «دستکش مشترکِ آزمایشگاه می‌تواند چند اثر معمول داشته باشد.» | «خاموش‌بودن هود یک واقعیت محیطی است؛ برای نسبت‌دادن حادثه به فرد، دسترسی و زمان را جدا بررسی کنید.» | Compare equipment state, shift access and fictional exposure window; no operational toxicology details. |

### 6.1 Mapping a case row into every playable phase

For **each** row C01–C40, use this binding, with its own named object and sources:

1. Lobby: one-line teaser from its title/place; withhold its D4 payoff.
2. Night 1: private roles choose their own legal actions; no unreleased D1 contents on buttons.
3. Day 1: that row's D1 + Night 1 report + the row's first legal comparison.
4. Discussion/Vote 1: reference D1 by immutable ID; explanation/help may compare only released material.
5. Interrogation Night 2, if any: ask a question about the row's named object/time and the suspect's actual statement; otherwise ordinary Night 2.
6. Day 2: that row's D2 + actual Night 2 outcomes; do not overwrite D1.
7. Day 3/4: same process for D3/D4; preserve a visible correction trail and apply the deadline policy before a verdict.
8. Jury/Court: render the case's currently released evidence and unresolved hypotheses, not its future D4 text.
9. Day 5 onward: apply that row's follow-up to actual unresolved observations plus each new night. Do not select a different case's generic clock/weapon story.
10. End: explain the row's core discrepancy and innocent explanation, then the actual live-night chain and winning condition. If a prelude fact never became relevant, say so.

Examples of phase-specific questions for the private officer: C02 «در پیام {Q} گفتی فنجان از کدام سینی آمده؛ ثبت {E} دربارهٔ قندان چه چیزی را روشن نمی‌کند؟»; C03 «آیا زمانی که گفتی از ساعت دوربین است یا ساعت اصلاح‌شده؟»; C27 «چه ثبت یا شاهدی زمان تماس با پردهٔ پرو را تأیید می‌کند؟». Render a quoted premise only if that message exists; otherwise ask a neutral open question.

## 7. Dawn reports and event branches

### 7.1 Player-facing report layout

Proposed public template (placeholders are populated only from permitted records):

> ☀️ صبح روز {N} — گزارش شب {N}
>
> پرونده: {case_title} · میز: {table_label}
>
> **اتفاق‌های تأییدشده:** {public_casualties_or_no_confirmed_death}; {public_custody_changes}.
>
> **یافتهٔ تازه از پروندهٔ اولیه:** {case_discovery_id} — {observation}.
>
> **مشاهدهٔ مربوط به شب {N}:** {permitted_night_observation_or_no_new_observation}.
>
> **نتیجهٔ آماده:** {public_lab_finding_if_due}.
>
> **هنوز معلوم نیست:** {bounded_unresolved_question}.
>
> **مسیر بررسی:** {legal_comparison_or_available_action}.

Buttons: «مدارک امروز»، «گزارش روزهای قبل»، «مقایسهٔ مدارک»، «آزمایش‌های آماده»، «گفتگو». These are proposed labels; section 9 distinguishes current and new routes. Private report buttons must be sent separately to the owning player.

### 7.2 Concrete worked sequence — C02, standard mode

This is an illustrative fixture, not a recording of the user's match. Prelude has two cups, a moved sugar bowl, and stored serving records. Night 1 has one protected direct-attack target; Night 2 has no direct attack; a poison applied on Night 1 matures on Night 3 in a roster that actually contains a poisoner. Doctor protection on Night 3 is absent. The public channel does not learn those hidden causes from this template alone.

- **Day 1 public:** «صبح روز ۱ — مرگ تازه‌ای تأیید نشد. پروندهٔ اولیه، C02-P1: دو فنجان از یک قوری پر شدند، اما افزودنی یکسانی نداشتند. بررسی بعدی: ترتیب پذیرایی را با ثبت قندان مقایسه کنید. نبود مرگ، علت مشخصی را ثابت نمی‌کند.» Private doctor: own committed target and allowed result only; never identify an attacker.
- **Day 2 public:** «صبح روز ۲ — مرگ تازه‌ای تأیید نشد. C02-P2: قندان میان دو نوبت روی میز دیگری بوده است. P1 و P2 وجود یک مسیر تماس مشترک را نشان می‌دهند؛ هنوز معلوم نیست چه کسی در بازهٔ مربوط به قندان دسترسی داشته است.» Private detective: Night 2's single committed result, with frame/concealment limitations.
- **Day 3 public:** «صبح روز ۳ — مرگ {نام} تأیید شد. C02-P3: نمونهٔ چای ساده، آلودگی کل قوری را تأیید نمی‌کند. علت مرگ تازه را از یافتهٔ پروندهٔ اولیه نتیجه نگیرید.» If coroner exists and is eligible, private result: «گزارش شب ۳ برای {نام}: علت ثبت‌شده در بازی، اثر تأخیری سم است؛ تماس در شب ۳ شرط لازم این مرگ نیست.» No poisoner identity.
- **Day 4 public, only if game continues:** «صبح روز ۴ — {واقعیت‌های شب ۴}. C02-P4: نتیجهٔ نمونهٔ قندان مسیر آلودگی پروندهٔ اولیه را محدود می‌کند. دارندهٔ فنجان لزوماً به قندان دسترسی نداشته است.» Show a completed lab result only if its source/due conditions are met; otherwise label the authored prelude sample report as such.

The real roster must determine available private paths. This fixture's poison/coroner branch is unsuitable for four-player standard composition and must not be injected there.

### 7.3 Outcome-to-text matrix

| Actual branch | Safe public report | Private/verification detail | Forbidden inference |
|---|---|---|---|
| No action / explicit skip | «مرگ تازه‌ای تأیید نشد.» | Own actor sees own skip acknowledgement | “The killer chose mercy” or reveal AFK roles |
| Protected attack | Same public no-death wording unless an independent public observation exists | Doctor receives only the defined protection outcome; watcher gets permitted observation | Identity of doctor/attacker from the generic report |
| Direct death | Confirm casualty; observed route if available | Cause detail only to entitled channel | All visitors are killers |
| Two attacks same target | One casualty entry; observations may have multiple independent sources | Preserve both attempts and resolution in secret ledger | Count the victim twice or disclose number of killers |
| Poison pending | No public countdown by default | Poisoner sees own committed action; authorized later clue can suggest delayed exposure | Reveal poisoned target merely because queue exists |
| Mature poison | Confirm casualty, keep public cause uncertainty per rules | Coroner distinguishes older exposure from same-night contact | Killer must have visited this night |
| Poison cured on due night | No confirmed casualty | Authorized cure finding, if rule permits | Publicly identify doctor, poisoner, or saved target |
| Storm | Announce recorded weather; only affected physical traces have reduced availability | Mature poison still uses its own cause | “All testimony is weak” or all deaths impossible |
| Blackout | Limit observations from affected sensors/time windows | Independent nonvisual sources remain usable | Everyone moved unseen; complete alibi from missing footage |
| Anonymous witness | Release an eligible new witness observation with explicit limits | Source provenance stored privately | Reissue E6 or create an infallible killer identification |
| Frame / planted print | «یک اثر منتسب به {نام} ثبت شده؛ زمان و منشأ آن هنوز روشن نیست.» | Authentication/context can challenge the attribution | Same fixed card index always fake; publicly label actual planter |
| Planted text claim | Place under unverified reports with a stable claim ID | Private author receipt; public challenge path | Present it as verified bot narration; reveal fake status by emoji/order |
| Concealment | Report only unaffected public observations | Detective/watcher: unavailable/inconclusive per chosen contract | “Clean” or “zero visits” as certified innocence |
| Co-location | Name a target/location only if the observation's visibility allows it | Witnesses get observations they could actually make | Remote actions become physical meetings; dead actors receive new agency |
| Hunter / fate-linked consequence | Distinct casualty entries with causal relations retained secretly | Publish cause only according to role/reveal rules | Describe every death using original case weapon |
| Threat | Nothing public unless target shares an attributed claim | Target gets actual message; threat does not prove sender's knowledge | Infer guilt from stress level or forced dialogue |
| Recruitment | No automatic public alignment-update clue | Notify only authorized participants; historical results stay timestamped | Retrospectively change an earlier finding or expose acceptance through count |
| Suspect dies / is released | Update public custody; close associated room safely | Archive officer episode; cancel invalid new requests | Continue hint generation against a stale suspect |
| Reporter + witness + dawn unlock | Show each distinct eligible card once with its allowed source | Resolve duplicate discovery selections consistently | Inflate count or reveal next card early through a selector |
| Lab and verdict same dawn | Deliver material counter-evidence before verdict, or apply pause/review rule | Timestamp completion and exposure | Irreversible decision before the only exculpatory result |
| Restart / repeated timer / repeated click | Same stored report and same clue IDs | Retry pending delivery, not game resolution | Different hint, duplicated resource spend, or second casualty |
| Win during night | Final casualty summary followed by ending report | Authorized final reveal | Offer next-night controls or postpone winning for more hints |

## 8. Roles and all evidence types

### 8.1 Role-specific information plan

Names are canonical identifiers; themed Persian display names are in [role-names.md](role-names.md). Every private result states match, Night N, target/card, finding, and limitation. Ability access remains exclusive and follows current eligibility at commitment/resolution.

| Role | Useful hint/result | Boundaries |
|---|---|---|
| کارآگاه | One committed alignment observation OR evidence authentication per night | Timestamp; suspicious includes neutral/framed possibilities; no repeated-query oracle |
| بازجو | Evidence-linked question suggestions and actual testimony contradictions | Only active authorized officer/episode; no invented answers or guilt from demeanor |
| پزشک قانونی | Early contextual analysis of selected evidence: age/source compatibility and a narrowed hypothesis | Evidence selector, not player selector; distinct from detective's alignment check |
| پزشک | Own action receipt and explicitly permitted care result | No attacker identity; public no-death report does not reveal protection |
| نگهبان | One target's permitted visit observation for the resolved night | Define unique visitors vs visits; blocked/hidden/remote cases handled consistently |
| خبرنگار | One genuinely new eligible public discovery | Proposed rotation only until assigned in a mode; never skip prerequisites or expose secret role |
| وکیل | Organize public counter-evidence and jury packet | No special forensic truth; preserve existing jury privilege once playable |
| شهروند | Full public comparison, claims, interpretation and help ladder | Meaningful investigation without stolen night powers |
| کالبدشکاف | Actual casualty cause category and timing in the simulated game | Distinguish direct, delayed and linked causes; no generic case weapon for every death |
| شکارچی | Own target receipt; eventual shot belongs in causal reconstruction | No privileged guilt hint attached to target choice |
| قاتل | Own action/skip receipt and permitted planted-claim status | No access to city's private findings; deceit constrained by published budget |
| همدست | Own frame target/duration and verification risk | No universal exemption from action budget; frame remains falsifiable |
| سم‌ساز | Own committed poison target and due night | No public queue leak; follow defined cure/expiry rules |
| خبرچین | Proposed: whether a completed interrogation interaction occurred, within a bounded window | Must add information beyond public nomination; do not reveal officer identity or private transcript by default |
| سپر بلا | Public evidence and own status, like any eligible non-investigator | Suspicion is not guilt; no fake system-certified confession |
| جانی سریالی | Own independent attack receipt | No criminal-team knowledge or team-only fake-clue tools unless explicitly designed |
| بقال محله | Proposed: daily contextual rumor with stable source and later check | Not in standard pools; 70% requires a defined calibrated generator, not an unsupported badge |
| قاچاقچی | Own concealment receipt; observers receive limited/inconclusive data | Not in standard pools; privacy consistency across public traces and private reports |

### 8.2 All 16 evidence kinds: result and button semantics

These are in-game abstractions, not real forensic guarantees. Use only the rows suitable for the chosen case; do not randomly place CCTV in a scene without a camera or a scratch “on” electricity/poison.

| Kind | Meaningful result / hypothesis to test | Required detail action |
|---|---|---|
| اثر انگشت | Contact compatible with a stored interval; genuine does not mean recent | Compare contact time / source custody |
| DNA | Simulated contributor compatibility or exclusion, including mixed sample limitation | Compare authorized sample records |
| رد پا | Route/direction/time compatibility; shared footwear alternative | Compare route and observation window |
| تار مو | Contact/transfer context; not instant identity proof | Compare contact history |
| پیامک حذف‌شده | Recovered fragment + original timestamp + missing-context warning | Read linked recovered context |
| دوربین مداربسته | Observation window, blind interval, clock offset | Compare calibrated timeline |
| رسید تاکسی | Trip/receipt timing; receipt holder may differ from rider | Compare journey claim and receipt provenance |
| گزارش کالبدشکافی | Case-prelude or named live casualty's cause/time category | Open the correct incident report |
| لکه‌ی خون | Simulated sample/time/context compatibility, prior injury alternative | Compare incident relevance |
| دستکش | Handling/material/access clue, shared-tool alternative | Compare inventory and custody |
| فایل پاک‌شده | Version delta and bounded access record | Compare file versions |
| صدای ضبط‌شده | Provided transcript, source and relative sequence | Compare transcript markers; no outside audio tool |
| ساعت شکسته | Candidate time anchor with calibration/history | Compare independent clock |
| رسید کارت بانکی | Simulated transaction and possession history | Compare receipt/time/claim |
| خاک روی کفش | Route compatibility with nonunique material | Compare in-game route samples |
| لیوان | Serving order, handling chain, simulated exposure context | Compare serving sequence and samples |

Example lab result for C11: «آزمایش L2، مربوط به مدرک P2: نمونه با لیوان دومِ ثبت پذیرایی سازگار است. این نتیجه فرض “هر دو لیوان یکسان بوده‌اند” را تضعیف می‌کند؛ آخرین دارندهٔ لیوان هنوز معلوم نیست. مقایسهٔ بعدی: تصویر میز پیش از جابه‌جایی.» Store that result as a versioned observation; never turn “people voted for hypothesis 2” into a lab finding.

## 9. Endpoint and button audit

### 9.1 Current paths related to hints/evidence

The following endpoint names and callbacks exist now unless explicitly marked proposed. “Fix” describes required implementation, not a completed change.

| ID | Endpoint / button path | Current behavior or gap | Fix / acceptance outcome |
|---|---|---|---|
| EP01 | `hints` / «🔦 سرنخ‌ها» in command and officer menus | Calls private `officer_hints`; not a public clue archive | Rename officer-facing label «سرنخ‌های بازجویی»; add distinct public dossier route; deny other actors without revealing suspect-private data |
| EP02 | `dawn` / «پایان شب» | Manual full report, no stored reusable report object | Use shared resolution report; actor eligibility and phase-consent rules apply |
| EP03 | `tick` / `_timer_job` | Short status omits manual dawn's full content | Same public and private finding IDs as manual path; no repeated release |
| EP04 | `lab` → `lab:E1` | All cards selectable; no requesting-player contract in engine; generic delayed output | Only visible eligible cards; authorize request; show queue/due dawn/completed result |
| EP05 | `interp` → `interp:E1` → `interp:E1:0` | Hidden card detail accessible; unrestricted vote membership; ambiguous tally | Public released cards only; one editable eligible vote; explicit tie/support count; no factual verdict |
| EP06 | `expose` → `expose:E1` | Private immediate authenticity result; selected code stored only as a generic spent marker; custody/visibility gaps | Proposed dawn-delivered finding, selected clue persisted, exclusive nightly budget, private authorized card selector |
| EP07 | `act` / `night` alias → target | Same player selector for evidence-targeted forensics/reveal | Dispatch selector by ability target type, shared eligibility with engine; selected evidence produces matching result |
| EP08 | `abilities` | Text/button availability can diverge; blanket lab promise | Show only available actions plus precise unavailability reason; no access granted merely by visible catalog |
| EP09 | `myrole`, `rolecard` | Private role information surfaces | Include own recent unread-result link; no full clue deck or secret result embedded in public media |
| EP10 | `notes` | Dumps role notes and own notes without day pagination | Day/source filters; separate verified role findings from player-authored notes; strict ownership |
| EP11 | `note` | Free-form pending text, logged command prefix | Private note composer bound to actor/table; no general log body; no public truth status |
| EP12 | `share_note` | Stores text for deferred publication | Preview exact text and trigger; keep it an attributed player claim, never automatically publish entire notebook |
| EP13 | `will` | Stored death message enters game log | Deliver once at defined trigger; attributed claim; ensure dawn includes it without revealing unrelated notes |
| EP14 | `ask` | Synthetic response is presented as suspect answer and sent to suspect | Real question/reply relay and episode ID; question may cite visible clue ID; no fabricated testimony |
| EP15 | `defense` | Free-form player defense | Attribute exact submitted text, distinguish from findings, show on verdict packet under published visibility rules |
| EP16 | `killer:plant:{uid}` | Planted fingerprint creates frame state | Unique frame event, duration/cost, truthful public observation, valid counter-evidence route |
| EP17 | `killer:clue` / `fakeclue` | Free text appended with identifying prefix; no nightly cap | Proposed one editable team claim/night; no privileged source impersonation or author metadata leak |
| EP18 | `killer:threat:{uid}` | Adds stress and sends private message | Record real threat separately from inferred stress; no automatic public clue or invented reaction |
| EP19 | `killer:recruit:{uid}` / `recruit:0/1` | Private offer and team-change messaging; generic rumor goes to log | No involuntary public alignment hint; prior report remains historically true |
| EP20 | `killer:skip` | Removes attack and sets private skip marker | No-death report does not disclose this marker |
| EP21 | `hunter` | Selects last-shot target | Later cause-specific report; receipt private, no clue-derived target recommendation leaking alignment |
| EP22 | `status`, `dashboard` | Evidence count derived from list length; no full dossier | Unique discovered count and link to latest report; no public pending-role side channel |
| EP23 | `discuss`, `vote`, `closevote` | Advance phases; no evidence version/cutoff | Freeze/report version for ballot, no new hints from repeated phase controls, honor player-approved night transition |
| EP24 | `castvote` | Accusation ballot; separate from interpretation | Never mix evidence opinion votes with custody/phase votes |
| EP25 | `verdict`, `clear` | Officer decisions affecting custody | Require reviewable current packet, permitted actor, due counter-evidence policy |
| EP26 | `jury`, `juryvote`, `closejury`, `refer` | Jury formation and decisions | Public packet contains only authorized material; no private officer-hint broadcast by default |
| EP27 | `sos` | Emergency accusation path | Same evidence limitations/visibility; cannot bypass exculpatory-result handling |
| EP28 | `end` | Roles/reason and last-log reconstruction | Full material-clue explanation, each night distinct; no private notebook dump |
| EP29 | `commands`, `group`, `menu`, `back` | Broad command navigation | Public dossier discoverable; private officer label explicit; Back does not reveal a private screen to group |
| EP30 | `roles`, `roleinfo`, `help`, `tutorial` | Catalog/descriptions may imply unsupported abilities | Explain claims, evidence and role paths; separate examples from live reports |
| EP31 | `new`, `blitz`, `startgame` | Case/mode initialization; no authored dossier schedule | Create case/version/seed, prelude and report identity before first release |
| EP32 | `rematch`, `newtable`, `table` | New session/parallel routing | Dossier namespaces and stale-token rejection; no report crosses a table |
| EP33 | `spectate` | Public watching intent | Public archive only; no mutation or private identity inference |
| EP34 | `pause`, `resume`, `host` | Lifecycle controls | Paused evidence remains readable, not rerolled; host is not entitled to private results |
| EP35 | `cancel`, pending `on_text` | Pending state keyed by user, consumed before full contextual validation | Composer cancel/reset bound to table and purpose; ordinary group text cannot become a fake clue/question |
| EP36 | `handle`, `_dispatch`, `on_callback` | Common routing, locking, logging and persistence | Validate actor/table/match/phase/version/token before reading or mutating; redact sensitive arguments |
| EP37 | `_reply`, `_send_dms`, timer delivery | Existing private-failure fallback avoids dumping secret text; no durable inbox contract | Preserve privacy behavior; add bounded report delivery/retry and generic failures that do not identify roles |
| EP38 | `surrender` → `surrender:yes` / «🏳️ تسلیم می‌شوم» | Added during review; two-step withdrawal can alter custody/phase and winning state | Record withdrawal separately from night death; no invented autopsy/dawn, no role reveal; invalidate future private actions and retain immutable historical evidence |
| EP39 | `board_of` and adapter board refresh | Added during review for live lobby/vote boards | Any future evidence-board refresh renders only the public packet; ballot identity and private report contents remain governed by their own visibility rules |

### 9.2 Registry completeness — all 77 endpoint names after follow-up review

Numbers below follow the observed `_ROUTES` registration order. “Context” means reviewed for its connection to evidence; it does not claim a full security audit of unrelated statistics/admin functionality.

| # | Endpoint | Hint/evidence coverage |
|---|---|---|
| 1 | `start` | Context: DM/table readiness; no secret report before authorized routing |
| 2 | `menu` | EP29 |
| 3 | `back` | EP29 |
| 4 | `new` | EP31 |
| 5 | `join` | Context: membership gates dossier access |
| 6 | `leave` | Context: lobby departure must not retain private session rights |
| 7 | `startgame` | EP31 |
| 8 | `myrole` | EP09 |
| 9 | `night` | EP07 |
| 10 | `dawn` | EP02 |
| 11 | `discuss` | EP23 |
| 12 | `vote` | EP23 |
| 13 | `castvote` | EP24 |
| 14 | `closevote` | EP23 |
| 15 | `hints` | EP01 |
| 16 | `ask` | EP14 |
| 17 | `verdict` | EP25 |
| 18 | `clear` | EP25 |
| 19 | `jury` | EP26 |
| 20 | `juryvote` | EP26 |
| 21 | `closejury` | EP26 |
| 22 | `status` | EP22 |
| 23 | `end` | EP28 |
| 24 | `profile` | Context: historical stats must not reveal ongoing private findings |
| 25 | `help` | EP30 |
| 26 | `roles` | EP30 |
| 27 | `share` | Context: invitation preview must exclude hidden case/role details |
| 28 | `sharelink` | Context: invitation link is not dossier authorization |
| 29 | `admin` | Context: admin status does not grant gameplay private clues |
| 30 | `admin_games` | Context: operational metadata, not live truth ledger |
| 31 | `admin_users` | Context: logged private argument prefixes must be redacted |
| 32 | `admin_stats` | Context: aggregates must not expose current-night actions |
| 33 | `admin_ban` | Context: update access eligibility without changing historical facts |
| 34 | `tick` | EP03 |
| 35 | `dashboard` | EP22 |
| 36 | `defense` | EP15 |
| 37 | `will` | EP13 |
| 38 | `note` | EP11 |
| 39 | `notes` | EP10 |
| 40 | `sos` | EP27 |
| 41 | `lab` | EP04 |
| 42 | `interp` | EP05 |
| 43 | `expose` | EP06 |
| 44 | `top` | Context: historical aggregate, no active clue content |
| 45 | `league` | Context: historical aggregate, no active clue content |
| 46 | `season` | Context: historical aggregate, no active clue content |
| 47 | `missions` | Context: do not reward spam interpretation or reveal hidden actions |
| 48 | `achv` | Context: no mid-game badge exposing hidden role/action |
| 49 | `newtable` | EP32 |
| 50 | `spectate` | EP33 |
| 51 | `voteanon` | Context: no ballot identity leakage via dossier summaries |
| 52 | `rematch` | EP32 |
| 53 | `rolecard` | EP09 |
| 54 | `tutorial` | EP30 |
| 55 | `blitz` | EP31 |
| 56 | `hunter` | EP21 |
| 57 | `table` | EP32 |
| 58 | `act` | EP07 |
| 59 | `ready` | Context: opening DM proves access only, not clue entitlement |
| 60 | `remind` | Context: generic reminder; no public count/list of pending secret roles |
| 61 | `pause` | EP34 |
| 62 | `commands` | EP29 |
| 63 | `group` | EP29 |
| 64 | `roleinfo` | EP30 |
| 65 | `abilities` | EP08 |
| 66 | `cancel` | EP35 |
| 67 | `resume` | EP34 |
| 68 | `host` | EP34 |
| 69 | `balance` | Context: measure usefulness without exposing ongoing private findings |
| 70 | `killer` | EP16–EP20 |
| 71 | `fakeclue` | EP17 |
| 72 | `recruit` | EP19 |
| 73 | `share_note` | EP12 |
| 74 | `refer` | EP26 |
| 75 | `surrender` | EP38; added during closing inspection |
| 76 | `archive` | Section 13: new role-specific archive implementation and access gaps |
| 77 | `plate` | Section 13: new private lookup, lifecycle and provenance gaps |

### 9.3 Proposed new user routes — not currently implemented

| Proposed route | Persian label | Contract |
|---|---|---|
| `dossier` | «پرونده و مدارک» | Public released evidence; filters day/source; default current day |
| `report` | «گزارش روز» | Reopen immutable report for an authorized match/day |
| `evidence` | «جزئیات مدرک» | Visible clue by opaque ID with limits, sources and next steps |
| `compare` | «مقایسهٔ مدارک» | Compare two visible observations without revealing private truth |
| `hint_help` | «راهنمای بررسی» | Progressive help levels from already visible facts |
| `lab_status` | «نتایج آزمایشگاه» | Pending/due/completed checks; authorized result details |
| `reply` | «پاسخ به بازجو» | Human suspect reply tied to an active question/episode |

Keep `hints` as the private officer compatibility route, with precise label. Add the public dossier to main/dashboard/evidence menus. New routes need both command and callback registration; no prose-only promises of buttons that do not work.

### 9.4 Button safety and display contract

1. Render from the same permission predicate used by the endpoint. Check again at click time.
2. Use a short opaque token referencing match, phase/version, action, clue and audience server-side. The Telegram callback is not an authorization credential by itself.
3. A callback for another table, old match, stale phase or unreleased clue produces a generic explanation and fresh authorized menu; no action/resource charge.
4. Public card view is read-only and broadly available to authorized public viewers; submitting lab requests/interpretations has separate eligibility. Private findings remain owner-only after elimination unless a published rule says otherwise.
5. “Back” preserves private/public destination. A failed private message never falls back to its full text in a group.
6. Escape all player-authored text. Pagination must respect Telegram's documented limits and avoid breaking entities; the proposed digest target is under 2,500 characters, not a claim about the API maximum.
7. Report a changed selection, queued request, unavailable phase or completed result in Persian; never leave a loading spinner without an answer.
8. Lab/evidence selectors show title, short ID, release day and status. Do not expose secret authenticity or future count through disabled controls.

## 10. Scenario validation plan for Claude

These are test requirements, not tests run in this documentation task. Exhaustive enumeration of unbounded human messages and arbitrary match duration is impossible; use finite coverage plus invariants and generated state sequences. Do not label 40 successful openings as “all gameplay tested”.

### 10.1 Content coverage

- All **40 cases × 2 modes × 7 supported seat counts = 560 configurations** must pass structural content/role-access validation. This does not mean every possible action combination is covered.
- For each case, validate D1–D4 and its Day 5+ continuation: stored supporting fact, incident/night label, source independence, innocent explanation, public verification path, prerequisite order, and no required absent role.
- Test all nine phase values, marking COURT unreachable unless implemented. Test no-suspect and active-custody branches separately.
- Test all 16 evidence kinds with authentic-relevant, authentic-irrelevant and planted/unreliable variants where appropriate; avoid treating every kind as universally appropriate for every scene.
- Test all 18 role contracts in exclusive-access tests, then in full reachable compositions. Mark the four unassigned standard roles as proposed rotations, not passed standard gameplay.
- Human Persian review: sensible material/scene combinations, concise text, understandable time windows, no gender/occupation/religion guilt cues, and no outside knowledge needed.

### 10.2 Numbered acceptance scenarios

| ID | Setup / action | Required observation |
|---|---|---|
| HT01 | C01–C40, resolve Night 1 | Correct case D1, correctly labeled live Night 1 report, no future-card selector leak |
| HT02 | Continue legal no-vote cycles through Night 10 | Each dawn has correct number; repeated facts retain IDs; no duplicate evidence count or invented novelty |
| HT03 | Same saved state, manual dawn vs scheduled tick | Same report and private result identities/content/visibility |
| HT04 | Reopen today's report 100 times | Read-only, stable facts, no ability cost or progression |
| HT05 | Change one committed action before resolution | Findings follow final valid action, not superseded target |
| HT06 | No actions, skip, protection, storm compared | No-death public wording does not reveal hidden cause |
| HT07 | Poison due with only innocent visitors this night | No claim that a current visitor must be the killer |
| HT08 | Multiple attacks, hunter and linked consequences | One casualty record per player; accurate causal ledger; permitted public uncertainty |
| HT09 | Blackout / storm / anonymous witness | Correct typed event branch; independent evidence retained; witness unlock unique |
| HT10 | Frame an innocent player | Suspicious observation has bounded validity and a reachable refutation before irreversible punishment |
| HT11 | Submit repeated fake clues / edit chosen clue | Finite budget; one committed claim; no identifying prefix/order or truth-authority impersonation |
| HT12 | Fake clue body claims to be “official lab result” | Safely rendered as unverified authored claim, not upgraded authority |
| HT13 | Hidden target with detective, watcher and public traces | Consistent concealment policy; no clean/zero certainty from unavailable observation |
| HT14 | Outsider/dead/jailed player calls lab or interpretation directly | Denied mutation; no new evidence, vote, queue entry or secret metadata |
| HT15 | Non-officer requests hints, officer eliminated or no suspect | Authorized error, no private hint/role identification |
| HT16 | Human suspect never sent the alleged statement | No generated accusation or quote attributed to them |
| HT17 | Same display name on two players; rename between days | Evidence refers to stable identities; no cross-player fact attribution |
| HT18 | Forensic role chooses E3 instead of E1 | Result concerns selected authorized E3 and consumes correct budget |
| HT19 | Reporter + witness + natural reveal on same dawn | All newly eligible distinct cards shown once; prerequisites respected |
| HT20 | Detective authenticates old legitimate fingerprint | Authenticity does not imply relevance or guilt |
| HT21 | Interpretation ties and changed votes | Correct support counts and explicit tie; facts unchanged |
| HT22 | Lab completes during verdict/jury boundary | Exculpatory result visible before decision or ballot paused/versioned per policy |
| HT23 | Standard vs Blitz with shortened custody | Useful result/refutation path exists in time in both modes |
| HT24 | Missing specialist or specialist dies early | Case still has a public route; no mandatory unavailable ability |
| HT25 | DM unavailable at dawn, succeeds later | Same private finding retry, no group fallback or duplicate resource spend |
| HT26 | Restart before/after commit and before/after send | Stable report, durable pending delivery, no lost or duplicated outcome |
| HT27 | Old button after `/table`, rematch or replacement game | Cannot read/mutate another match; no hidden-card existence leak |
| HT28 | Pending fake-clue prompt then ordinary group chat | Group message not consumed as private submission; explicit composer context required |
| HT29 | Long Persian text, emoji, Markdown, many reports | Correct pagination, safe rendering, valid callback byte sizes |
| HT30 | Private note/question/fake clue enters command handler | General audit/event views contain metadata, not private text prefixes |
| HT31 | Public packet during anonymous ballot | No voter/role identity leak from summaries or counts |
| HT32 | Day 1 win or Night N final casualty | End promptly; no future clue required; material clue explanation remains available |
| HT33 | Same case in rematch with different hidden assignments | Known twist does not reveal a player's role; no fixed E2/E5 authenticity oracle |
| HT34 | Player requests progressive help | Compares only visible facts; does not reveal hidden author/role or future release |
| HT35 | Paused game with pending report/lab deadlines | Existing reports readable; no new release or action consumption until valid resume |
| HT36 | Review END dossier | Every material false lead has stored explanation; unrelated private notes/transcripts remain private |
| HT37 | Suspect/officer/other player surrenders before night resolution | Withdrawal is not a confirmed night death; no synthetic dawn/clue; episode/eligibility updates preserve the last resolved report and handle a resulting win |

### 10.3 Quality measures after correctness

Proposed release gates: zero unsupported factual assertions in fixtures; zero unauthorized private disclosures; every released core clue has a reachable verification route; all configured due results delivered or durably retrievable; no duplicate report/event IDs; no hidden-state-dependent styling/ordering oracle.

Human playtests should measure whether players can distinguish observation from claim, cite a clue when changing a decision, explain a dismissed red herring, find the relevant button without typing a code, and understand the latest night number. Track these by case/mode/seat count, together with time to first useful clue and abandoned investigations. Win rate alone does not measure clue quality. Establish baseline measurements before setting numerical comprehension or balance targets.

## 11. Implementation order and handoff

1. **Truth and privacy first:** typed event/prelude records, visibility guards, private logging policy, cause-safe observations. Remove unsupported narrative assertions.
2. **One report pipeline:** persistent report per night, equal manual/timer delivery, private inbox, unique releases and historical archive.
3. **Functional evidence tools:** visible-card selector, useful lab result, correct forensics target type, interpretation poll semantics, officer human conversation.
4. **Author one complete vertical slice:** C02 in standard and Blitz, including D1–D4, quiet Day 7, poison/non-poison rosters, fake claim and jury deadline. Use the worked sequence as a fixture, not runtime hard-coded history.
5. **Expand to all 40 cases:** implement the authored content and its supporting records; apply playlist/mode/role rules. Do not ship template text without its truth conditions and verification options.
6. **Bound adversarial interactions:** claim budgets, pending text context, table-bound callbacks, replay safety, report pagination and retention.
7. **Run HT01–HT62 plus existing regression suites**, publish actual results and unresolved limitations, then conduct Persian-language human playtests.
8. Update `rules.md`, `report.md`, role help and menu descriptions alongside implemented behavior. Do not claim the proposed playlist routes, new endpoints, or lab timing are already live.

Completion means a player can answer: **“What changed last night, what does this clue actually support, what can I check next, and which information belongs only to me?”** The bot should help players reason without fabricating their testimony or deciding guilt for them.

## 12. Owner's additional requirement: role-exclusive records and vehicle investigation

This section extends the plan following the owner's request for abilities/data to be granted and taken away correctly, doctor access to health/hospital reports, officer access to police files and plate ownership searches, and public clues about vehicle color/model. **Documentation only. At the initial review these services were absent; section 13 documents subsequently added partial implementations. The detailed services and proposed endpoint names below are still target contracts, not completed features.**

Terminology: “police” maps to the existing **بازجو** role, displayed as «رازپرس — مأمور پرونده» where helpful. Do not create a second police role or give the detective police permissions accidentally. The doctor is **پزشک / جان‌بان**; forensic specialist **پزشک قانونی / اثرکاو** and coroner **کالبدشکاف / مرگ‌خوان** remain distinct roles with distinct records.

All hospital, police, vehicle and plate records described here are **fictional match data**. The bot does not query real hospital systems, police databases, real plate registries or personal records. The full plate is a simulated identifier visible only through the authorized police workflow during active play.

### 12.1 Additional source findings

The source search found the hospital and vehicle terms in case scenery, but no health-record, hospital-record, vehicle-registry, plate-lookup or police-file subsystem. These features need explicit implementation; renaming an existing evidence button will not create them.

- `check_night_action` derives an ordinary action from the actor's role and blocks eliminated/jailed actors. This is a useful foundation, but special handlers must enforce the same lifecycle rules.
- `officer_hints` currently checks officer identity and the presence of a suspect; it does not provide police files or vehicle ownership and does not fully enforce current officer eligibility.
- `expose` has role/live/phase checks but lacks the full custody/visibility contract. A new specialist API must not inherit those gaps.
- Current `GameState`/case dictionaries have no vehicle ownership/use history or health observation ledger. A vehicle clue cannot truthfully identify an owner/driver until those fictional records exist.
- Current criminal toolkit checks team eligibility for several tools. Being on a team must not automatically grant every teammate's specialist power; specify this explicitly in the capability table below.

### 12.2 Complete role capability and data-access matrix

This is the **proposed authoritative capability map**, not a statement that all features already work. Base abilities are from the role catalog; added data services are labeled new. All actors may read released public evidence and their own previously delivered findings. None may access another role's private records merely by knowing a command or record ID.

| Role | Exclusive ability / service granted | Private data permitted | Explicitly withheld |
|---|---|---|---|
| کارآگاه — ردبین | Alignment investigation OR evidence authentication, one nightly choice | Own target finding or selected clue authenticity/context | Hospital charts, full plates, registry ownership, police case files, other's findings |
| بازجو — رازپرس | Human interrogation/verdict; **new police files and vehicle registry lookup** | Released police observations, full simulated plate, registered owner/use records within case scope | Hospital charts, detective alignment query, forensic-only samples, raw secret action ledger |
| پزشک قانونی — اثرکاو | Analyze a selected evidence item | Simulated sample provenance, compatibility and relevant time window | Live health dashboard, treatment power, police registry, full plates |
| پزشک — جان‌بان | Protect/treat under game rules; **new health/hospital record review** | Authorized patient record snapshot, observation time, clinical-status category and available care context | Hidden role/alignment, attacker/poisoner identity, full poison queue, police files and plate registry |
| نگهبان — شب‌پای | Observe a selected player's permitted visits | Own night's bounded observation; vehicle appearance only if actually observable | Owner lookup, full plates, medical records, all-player movements |
| خبرنگار — پرده‌گشا | Release one eligible new public clue in a supported rotation | Pending publishable discovery and released public dossier | Privileged medical/police records, secret role information, unreleased confidential plate image |
| وکیل — دادخواه | Special jury request; organize defense packet in a supported rotation | Public file and deliberately shared, permitted defense summaries | Full police archive or medical charts merely because they are a lawyer |
| شهروند — هم‌محله | Public comparison, interpretation, ordinary vote; no hidden specialist power | Own actual symptom/notification if the game explicitly delivered one; own submitted statements | Specialist dashboards or health/owner checks for others |
| کالبدشکاف — مرگ‌خوان | Examine resolved casualties | Cause category, timing and authorized postmortem findings for actual deaths | Live patient health, doctor protection, police registry; withdrawal is not an autopsy event |
| شکارچی — واپسین‌تیر | Set own last-shot target | Own committed target and permitted event receipt | Alignment/health/owner queries to optimize the shot |
| قاتل — خاموشگر | Direct attack or skip; only explicitly assigned deception tools | Own action history and authorized team information | Any civic specialist data, victim health status as a target selector, full plates |
| همدست — ردساز | Frame; proposed bounded planted-claim service belongs here when this role is present | Own frame history, target, expiry and claim receipt | Automatic kill/poison/investigation; registry edits; ability to rewrite official records |
| سم‌ساز — زهرریز | Delayed poison | Own submitted target/due-night receipt under game rules | Whole hospital record or all treatment outcomes; other poison actors' data unless explicitly shared |
| خبرچین — سایه‌شنو | Bounded observation of completed officer activity | Whether the permitted interaction occurred in the defined window | Question/answer transcript, full plate, owner response, police-file contents, officer identity from metadata |
| سپر بلا — بلاگردان | Own objective and public participation | Own status, public evidence and own delivered messages | Forged system truth, hidden guilt status of others, specialist records |
| جانی سریالی — تنهاکُش | Independent attack | Own action receipt | Criminal-team toolbox/team roster, doctor/police data |
| بقال محله — پچ‌پچ‌فروش | Daily bounded rumor in a supported rotation | Own rumor plus any later released corroboration | Full plates, registry owner truth, hospital findings disguised as rumor |
| قاچاقچی — ردپوش | Conceal a permitted target in a supported rotation | Own concealment result and limits | Alter official owner records, erase already published evidence, read police/medical files |

**Criminal-tool allocation proposal:** retain a single team claim budget; use accomplice when present and an explicitly documented killer fallback when absent. This is a proposed rules change from the current broad toolkit, not permission to remove an existing feature silently. Threat/recruitment permissions must likewise be declared as named capabilities, with their own costs, instead of inferred from team membership. Recruitment of an ordinary citizen must not grant medical, police, poison or investigation powers.

### 12.3 When access is given, suspended and taken away

Apply these rules to **buttons, commands, detail reads, searches, media, exports, background delivery and cached results**. Hiding a button is insufficient.

| State/event | New actions and fresh privileged data | Previously delivered information | Required response |
|---|---|---|---|
| Lobby / not yet assigned | No role capabilities | Tutorial/public preview only | «پس از شروع بازی و دریافت نقش فعال می‌شود.» |
| Role assignment | Grant only the assigned role's named capabilities for this match | Own role briefing and permitted initial files | Private menu lists exact available services |
| Alive/free in correct phase | Permit legal choice within quota and released-record scope | Reopen own findings without another charge | Receipt includes target, night/day and due time |
| Wrong phase | No new phase-specific action/search | Read eligible delivered records and public dossier | Explain next availability; do not spend quota |
| Interrogation custody | Suspend ordinary night powers and new specialist searches; suspect can answer actual questions/defend | Own existing archive remains readable privately | Do not offer medical/plate requests to a jailed specialist |
| Temporary jail | Suspend fresh specialist actions, searches and new privileged deliveries | Own old archive remains private and read-only | Public communication still follows custody rules |
| Released from custody | Restore original role's eligible services prospectively | Keep historical results with their original dates | Never “catch up” missed nights with free retrospective searches |
| Death / life jail / surrender | Revoke all future action and fresh privileged-data access immediately | Permit own old archive read-only; knowledge already seen cannot be erased | Cancel pending new searches under a documented resolution policy; no resource duplication |
| Officer unavailable | No other player, host or admin inherits police access automatically | Police archive stays protected | Public fallback clue route continues; any formal replacement needs explicit role grant and tests |
| Host transfer | No role/data privilege change | No transfer of private records | Hosting is operational authority, not police/doctor authority |
| Role/team change | Recompute capabilities from explicit role rules; revoke no-longer-held services | Old delivered findings stay historical, never rewritten | No implied specialist acquisition on criminal recruitment |
| Paused | Suspend new actions/releases | Read existing authorized material | Show paused status; preserve unspent quota |
| End | No new health/owner query; permitted final reconstruction only | Own private archive remains private | Even at end, do not dump full plates/charts automatically |
| Rematch / new table | Revoke old match tokens for new actions; create new grants and namespaces | Old archive remains separately labeled | No old police token can open new-match records |

The server authorizes before search/detail lookup and again before result delivery. Pending requests carry actor, match, role-capability version, record ID, source cutoff and deadline. The proposed default for a player eliminated before delivery is to withhold the undelivered privileged result; the public fallback must preserve case progress. If a role's game rule instead guarantees a dying result, document and test that exception explicitly.

### 12.4 Doctor workflow — health and hospital reports in the private bot

**New buttons:** «🏥 پرونده‌های درمانی من» → eligible patient/record → «📋 گزارش سلامت» or «🕒 سوابق مراجعه». Keep «💉 محافظت امشب» separate so reading a file never silently submits a protection action.

Proposed starting balance: one **new patient-record review per day**, available in morning/discussion to an alive, free doctor, with an immediate **stored snapshot** result. Reopening that result is free; it does not refresh live health. Existing protection remains one committed nightly action under its own restrictions. These quotas are tunable proposals, not measured balance outcomes.

Record eligibility: only patients linked to an actually released incident, hospital visit, or medically relevant clue—not an unrestricted list of every player's live health. When no record exists, state that no authorized record is available. A healthy character does not automatically have a hospital chart.

Permitted fields: fictional patient ID/name where already authorized, incident ID, visit/sample time, report completion time, observed symptom category, care already recorded, observation limitation, and permitted follow-up. Never return hidden role, guilt, attack intent, author of poison, unseen future death, or the entire poison queue. A stored “no abnormal finding at time T” is not immunity after T.

Example, supported fictional medical record:

> 🏥 گزارش سلامت — فقط برای جان‌بان
>
> بیمار: {نام مجاز} · مراجعه: شب ۲ · گزارش: روز ۳
>
> مشاهدهٔ ثبت‌شده: نشانهٔ تماس با یک عامل تأخیری در گزارش وجود دارد؛ هویت عامل یا زمان دقیق تماس مشخص نیست.
>
> محدودیت: این گزارش مربوط به زمان مراجعه است و سلامتِ همین لحظه را تضمین نمی‌کند.
>
> اقدام در دسترس: بررسی سوابق همین مراجعه؛ محافظت شبانه طبق قوانین نقش.

Only emit the exposure line if a medical observation exists. Do not derive it from a hidden queued poison alone. Before a game-ending delayed effect, fair counterplay requires a defined discoverable symptom/clinical observation route; the doctor cannot be expected to guess from an invisible countdown. If there is no doctor in the roster, avoid making a medical diagnosis the sole route to solving the case.

**Separation from other roles:** forensic specialist tests evidence material; coroner explains resolved death; doctor reviews living-patient care context and protects. A postmortem report is not a live-health chart, and a clinical record is not an alignment test.

### 12.5 Police workflow — private files, full plate and registered owner

**New buttons in officer DM:** «🚓 پرونده‌های انتظامی» → case-linked observation → «🚘 جزئیات خودرو» → «🔎 استعلام مالک ثبت‌شده». Every step remains inside the private bot. This workflow does not require a currently detained suspect; a living, free officer can investigate a released vehicle lead before making an accusation.

Proposed starting balance: one **new registry inquiry per night**, with the result delivered at dawn; reopening completed police files/results is free. The inquiry is separate from human interrogation but cannot be repeated against arbitrary plates. An eligible lead must contain an authorized full simulated plate. No arbitrary real plate entry, partial-plate brute-force query, or enumeration of all vehicle owners.

| Vehicle field | Public clue | Officer-only file | Rule |
|---|---|---|---|
| Color | Allowed if observation supports it | Same observation plus provenance | Night/poor lighting may allow only “dark,” not a precise color |
| Make/model | Allowed at observed precision | May include a better supported identification | “Sedan” does not become a specific model without new evidence |
| Location/time/direction | Allowed if the source is public | Detailed authorized timeline | Observation does not prove driver identity |
| Full plate | **Never in public report, image, button, callback or generic log** | Allowed only in officer's authorized DM record | Use a fictional internal plate ID such as `SIM-047`, not a real lookup |
| Partial plate | Omit from public by default under owner's plate-only-to-police requirement | May be stored privately with uncertainty | No fragments leaked through filenames, alternate text or errors |
| Registered owner | No automatic publication | Owner at the relevant record date, from fictional registry | Owner is not necessarily driver or killer |
| Loan/rental/use history | Attributed public summary only if legally released by game rules | Relevant stored record, where available | Missing record is uncertainty, not proof no loan occurred |
| Driver identity | Only if independently established and authorized for release | Separate evidentiary claim, not inferred from plate | Never equate registered ownership with guilt |

The officer may choose to share a **sanitized finding summary** under the game's disclosure rules, e.g. «ثبت مالکیت با ادعای استفاده‌کننده یکی نیست». The bot's sharing control never includes the full plate or unrelated file contents. Players can repeat knowledge outside the bot; software cannot retract what a human has read. The bot must still enforce its own output boundary consistently.

Example public lead:

> 🚘 مشاهدهٔ شب ۲: یک پژو ۲۰۶ خاکستری بین ۲۲:۴۰ و ۲۲:۵۰ نزدیک ورودی پارکینگ دیده شد. چهرهٔ راننده مشخص نیست. رنگ و مدل به‌تنهایی صاحب یا راننده را تعیین نمی‌کند.

Example private officer detail for the **same** stored observation:

> 🚓 پروندهٔ انتظامی V12 — محرمانه برای مأمور پرونده
>
> زمان مشاهده: شب ۲، ۲۲:۴۰ تا ۲۲:۵۰
>
> خودرو: پژو ۲۰۶ خاکستری · شناسهٔ پلاکِ ساختگی بازی: SIM-047
>
> منبع: ثبت مجاز دوربین ورودی؛ چهرهٔ راننده قابل تشخیص نیست.
>
> اقدام: «استعلام مالک ثبت‌شده» — نتیجه پس از پایان شب تعیین‌شده می‌رسد.

Example lookup result:

> 🔎 نتیجهٔ استعلام R8 برای V12: مالک ثبت‌شده در زمان واقعه، {نام درون‌بازی} است. یک سابقهٔ امانت مرتبط نیز ثبت شده است. مالکیت، رانندگی در شب ۲ را ثابت نمی‌کند. بررسی بعدی: زمان امانت را با مشاهدهٔ ورودی و ادعای استفاده‌کننده مقایسه کن.

If the ledger contains no loan, omit that claim and say use history is not established. If plates may be cloned or substituted in a game variant, author that event and a corroboration route up front; do not invent it retroactively to excuse an inconsistent solution.

### 12.6 Significant day-by-day vehicle and hospital clue sequence

Example fixture for C12 (rental vehicle) or a separately authored compatible variant of C03/C20/C31/C38. Attach it only when the scene has the relevant transport/hospital records. Do not add vehicles to every case indiscriminately.

| Day/phase | Public release | Doctor DM | Officer DM | Decision supported |
|---|---|---|---|---|
| Day 1 after Night 1 | «خودرویی تیره نزدیک ورودی دیده شد؛ مدل و راننده مشخص نیستند.» | Only an actually recorded, eligible clinical lead; otherwise no new record | Police lead V1, no full-plate query until legible record is released | Seek an independent observation; do not identify a person from color |
| Day 2 after Night 2 | A second stored source supports «پژو ۲۰۶ خاکستری»; explain why precision improved | Case-linked hospital record opens if a recorded visit exists | Legible plate record becomes available privately | Compare time/location; officer can commit one inquiry |
| Night 3 | Previous public report remains frozen | Doctor commits protection separately from record reading | Officer inquiry bound to V1 is committed | No live owner result or health polling |
| Day 3 after Night 3 | Publish only new permitted observation, not owner/plate | Stored visit/treatment time may support or challenge an alibi; no automatic public sharing | Registered owner and relevant rental/loan record | Owner, user and driver become separate hypotheses |
| Day 4 after Night 4 | An authorized second source resolves a relevant time discrepancy, if present | Authorized follow-up snapshot remains historical | Compare ownership/use time with vehicle observation | Corroborate or refute the suspect's actual claim |
| Day 5+ / jury | Only permitted released comparisons and attributed summaries | No fresh chart automatically added to public packet | No full plate in jury/group packet | Preserve fair defense without exposing restricted records |
| End | Explain whether the observed vehicle was relevant, borrowed, misidentified or unrelated | No raw chart dump | No automatic full-plate dump | Explain the clue's significance without confusing ownership and culpability |

Do not call a vehicle “the killer's car” in a public hint unless that relation is already established by permitted evidence. Internally the author may know it belongs to a killer or suspect; the public text should say **observed vehicle** until the players can support the stronger conclusion. Two players may have similar vehicles; model/color is a narrowing clue, not unique identification.

### 12.7 Additional proposed endpoints and UI acceptance

These endpoints are **new proposals**, not additions to the observed 75-route registry.

| Proposed route | Button | Actor / timing | Result boundary |
|---|---|---|---|
| `medical_files` | «🏥 پرونده‌های درمانی» | Doctor DM; alive/free for new records | Eligible case-linked records only |
| `health_report` | «📋 گزارش سلامت» | Doctor; one new review/day in morning/discussion | Stored time-bounded snapshot, no hidden-state poll |
| `hospital_history` | «🕒 سوابق مراجعه» | Doctor; same authorized patient review scope | Actual fictional visits, no all-player enumeration |
| `police_files` | «🚓 پرونده‌های انتظامی» | Officer DM; no suspect required | Released police files, not engine truth ledger |
| `vehicle_record` | «🚘 جزئیات خودرو» | Officer, authorized file | Full simulated plate confined to DM |
| `plate_lookup` | «🔎 استعلام مالک» | Officer; one new inquiry/night; valid full-plate lead | Queued case-specific registry result at dawn |
| `private_results` | «📥 نتیجه‌های من» | Owner only | Already delivered or currently authorized findings; separate days/services |
| `share_finding` | «📤 اشتراک خلاصهٔ یافته» | Authorized owner under communication/custody rules | Previewed sanitized summary; never plate/chart dump |

An ordinary player should see the public vehicle clue and their own menu, not a disabled “police plate” button that leaks the existence of a secret record. Requests by the wrong role receive a generic permission error before any record lookup. Endpoint permission uses authenticated actor identity, never a role or UID supplied in callback text.

### 12.8 Additional acceptance scenarios — HT38–HT50

| ID | Setup / action | Required observation |
|---|---|---|
| HT38 | Parameterize all 18 roles against medical/police/vehicle/plate endpoints | Only doctor gets new medical access and only officer gets new police/plate access; generic denial without record metadata for others |
| HT39 | Doctor opens a valid patient record twice; another player tries its ID | First review uses quota; reopen returns same snapshot free; other player denied |
| HT40 | Poison is queued but no clinical observation exists | Hospital endpoint does not expose hidden queue/author/countdown; observation-generation rule supplies fair counterplay where designed |
| HT41 | Doctor sees normal report at T; patient changes after T | Reopen still states T, not silently refreshed health; later record is separately authorized/versioned |
| HT42 | Public report/button/media/log created from vehicle observation | Color/model at supported precision may appear; full/partial plate and registry response do not leak |
| HT43 | Officer with no suspect opens police file and commits eligible plate query | Works privately; result at defined dawn; no dependency on invented interrogation |
| HT44 | Plate belongs to an innocent owner but another actor used vehicle | Result says registered owner/use uncertainty; no automatic guilt/driver assertion |
| HT45 | Query arbitrary plate, partial plate, future record, other table, old token | Denied before data lookup; no enumeration oracle or resource charge |
| HT46 | Doctor/officer jailed, killed, surrendered, released or transferred host status | Capabilities suspend/revoke/restore exactly as matrix; host transfer grants no specialist data |
| HT47 | Role changes after query but before delivery; DM retry after elimination | Recheck recipient capability/version; no fresh unauthorized record delivered through cache/retry |
| HT48 | Physician, forensic specialist and coroner request each other's data | Distinct grants maintained; autopsy reports reference actual deaths, never surrender |
| HT49 | Owner shares authorized finding to group/jury | Preview matches output; plate and raw clinical data absent; attribution and uncertainty retained |
| HT50 | Case/mode roster lacks doctor/officer access or specialist becomes unavailable | Public verification route keeps case playable without granting their powers to everyone; completed report remains immutable |

Before implementing, update the earlier role descriptions and quotas to this explicit contract. Do not market doctor health reports or private plate inquiries as functional until these paths, permissions, delivery behavior and failure cases are tested.

## 13. Follow-up structural review: active-game menus, capabilities and ongoing day

Reviewed again on 2026-09-21 after additional changes by another editor. This task still changes **only this document**. These findings update the current-status descriptions in sections 3 and 12; they do not replace the owner's requirements or claim a passing regression run.

### 13.1 What now exists, and what remains incomplete

| ID | Current source / structural observation | Consequence | Required correction |
|---|---|---|---|
| ST01 | `ui.main_menu(state)` now chooses `IN_GAME_MENU`; `h_menu` and `h_commands` display `g.s.day`. | Some pre-game clutter is already removed, and a day counter already exists. | Preserve this progress; make menu generation actor-, phase-, custody- and destination-aware. |
| ST02 | `menus.visible_groups(state)` filters only by live-game category and `PREGAME_ONLY`, without an actor argument. `interro`, `clues` and `dark` remain visible to everyone. | Citizens see police/plate, detective and criminal controls; irrelevant buttons remain even when actions fail. | Filter by capability and phase before grouping. Omit empty categories. Keep server authorization independent of visibility. |
| ST03 | `IN_GAME_MENU` includes `act` for every actor and phase. `dashboard_kb(state)` exposes phase controls without actor/host eligibility. | A role without a night action still sees it; ordinary users can be offered phase-closing controls. | Build menus from legal actions, not one fixed list for every active participant. |
| ST04 | `GLOBAL_CMDS` includes `menu` and `back`; `route_chat` returns the private chat for these instead of resolving the active group table. | Home/Back in DM may find no game state and show the pre-game menu even during a live match. | Resolve active game context for navigation. Global informational operations may remain separate, but cannot erase the live-session context. |
| ST05 | `h_cancel` and some completion paths, including `h_will`, call `commands_menu()` without state. | Cancel/Save can bring back unrelated categories and lobby controls. | Every response path carries the same authorized view context, including errors, empty inputs, Save, Cancel and Back. |
| ST06 | `visible_groups` hides the entire table/hosting category, which contains pause/resume/host controls. | Removing clutter also removes useful host operations. | Private host-only “مدیریت همین بازی” submenu; no new-game/replacement options within it. |
| ST07 | New `archive` and `plate` handlers return `private=True`; `roles.py` maps doctor to `hospital`, officer to `police_files`, and both forensic specialist/coroner to `forensic_files`. | Private routing and role-specific categories now exist, but category equality collapses distinct forensic duties. | Retain DM-only output; separate capabilities, source records and quotas rather than overloading `RoleDef.info`. |
| ST08 | `Game.archive` checks membership and case existence, but not alive/custody/phase before constructing current data. | Eliminated or detained actors can receive newly computed privileged information; this is not merely reopening old notes. | Apply the grant/revocation matrix; return immutable previously delivered results where permitted, not a freshly rebuilt live archive. |
| ST09 | Doctor archive selects three players by stress and calls `dialogue.stress_of`, whose band partly depends on alignment. It calls these “today's admissions” without admission records. | Medical reporting invents hospital attendance and can become an indirect alignment signal. | Use actual fictional clinical observations and visit timestamps; never role-derived stress as hospital evidence. |
| ST10 | Forensic archive directly includes case twist and misleading-card flags, labeled as lab findings, without a completed selected analysis. It uses case time/weapon for the report. | Free archive reads can bypass nightly powers and reveal unearned answers; unrelated later deaths get the wrong explanation. | Only released/completed analyses; coroner uses casualty events, forensic specialist uses selected samples. No new discovery from reopening the archive. |
| ST11 | `plate_lookup` checks police role/live state but not custody, phase, released lead, nightly quota or query cutoff. | Jailed police or repeated queries can obtain immediate fresh data. | Apply section 12's explicit scope/phase/quota contract, or document a deliberate tested alternative before implementation. |
| ST12 | `swap_plate` overwrites `plate_owner` and notifies previous lookup users without rechecking current eligibility. | Old ownership is lost; fake document, changed physical plate and real registry ownership are conflated; revoked users can receive new private messages. | Separate original registry, physical observed plate, use history and forged-document claim. Version corrections; recheck recipients. |
| ST13 | Case vehicle model/color/plate and `plate_owner` now exist; owner selection is partly alignment-conditioned, rather than drawn from a complete use/observation history. | Ownership may act as a statistical guilt shortcut while the actual driver/observation relationship is undefined. | Author a consistent fictional ownership/use ledger. Do not label the vehicle as the killer's merely from this selection. Public model/color requires an actual scene observation. |
| ST14 | Daily rumor selects some names from criminal alignment, then invents a location/argument statement; “70%” describes a branch, not verified statement truth. | A rumor is not demonstrably true just because it mentions a killer. | Evaluate truth against recorded events; preserve source uncertainty and a verification path. |
| ST15 | `start` initializes `day=1`; no-vote/tie paths and interrogation entry increment it separately. Surrender/other custody paths can set morning without resolving night. | UI can describe a morning without a completed night's report; independent increments risk skipped/doubled labels. | Centralize cycle transitions; keep current cycle and last resolved night explicit. A phase assignment alone cannot create a dawn report. |
| ST16 | Snapshot persistence pickles the Game and loads it if `outbox` exists; failed/old loads are silently skipped. | The whole day state can survive valid snapshots, but new field compatibility and a missing-game recovery message are not guaranteed. | Version snapshots, migrate supported versions, validate cycle/report invariants, and surface a recoverable failure instead of silently resetting to a lobby. |

### 13.2 Active-game menu contract — owner's requested behavior

Once a match starts, every player-facing navigation path opens **the current game's menu**. Visible buttons must help that actor play, understand, or safely manage that match. Do not display global progression, administration or lobby creation merely to make all registered commands discoverable.

**Shared group board:** case/table, current night/day and phase, public report, released evidence, public status, and an actor-neutral «منوی خصوصی من» entry. No role-specific button label, hospital/plate control, criminal menu or pending-role count appears on this shared board. Public board content must not change according to the role of the last person who clicked Refresh.

**Player DM:** own legal action, own authorized archive/results, own role/rules, notebook, current public dossier and eligible ballot. Show only currently applicable primary actions. Previously received findings remain reachable as read-only material even when a new action is unavailable. This is different from rendering another role's button and rejecting it after a click.

**Hide during active play:** New Game, Blitz creation, Join/Leave Lobby, Ready-to-start, Start Game again, Rematch, New Table creation, global leaderboards/season/missions/achievements/profile promotion, invitation marketing, admin tools, and full tutorial onboarding. Keep concise current-game rules/help, which are relevant. End-of-game results may offer Rematch once the match is actually over.

**Host DM:** add only relevant current-game controls: Pause or Resume as appropriate, Transfer Host, and a generic reminder. These do not grant role data or permit skipping the required player approval for the next night. A separate operational admin interface must not appear in ordinary player navigation.

**Multiple active tables:** if context is ambiguous, show a minimal private choice among the user's existing games, each labeled with its current phase/cycle. This is necessary game navigation, not a return to the global menu. Hide creation of another table; selecting an existing table must never retarget old buttons silently.

**Old messages and keyboards:** after starting/advancing, edit known current boards to remove obsolete controls where practical. Historical Telegram messages cannot always be removed; any old Join/New Game/Start/role-action callback must be revalidated and return to the live menu without replacing the match. The user's request to hide controls must not be interpreted as sufficient protection against typed commands or stale keyboards.

### 13.3 Concrete private menus by role and state

All examples include the common header and permitted notebook/public-report links. Buttons here describe target behavior, not newly implemented routes.

| Actor/state | Visible relevant controls | Hidden controls |
|---|---|---|
| Doctor, free, Night 3 | «💉 محافظت شب ۳»، «🏥 گزارش‌های دریافت‌شده»، «📓 یادداشت» | New daytime medical review, police files/plates, detective query, criminal tools |
| Doctor, free, Day 3 discussion | «🏥 بررسی گزارش سلامت» if quota/record eligible; «سوابق مراجعه»، public comparison | Night protection submission; stale queued results presented as live health |
| Officer, free, Night 3, valid vehicle lead | «🚓 پرونده‌های پلیس»، «🚗 استعلام پلاک» if quota available; active interrogation questions if there is a suspect | Hospital chart, detective ability; plate in any group keyboard |
| Officer, Day 3, no suspect | Received police/plate results and eligible case files | Verdict/Ask with no suspect; new night-only inquiry |
| Detective, free, Night 3 | Choose «استعلام یک نفر» OR «راستی‌آزمایی مدرک»; receipt shows consumed/available budget | Police owner lookup, clinical chart, both powers consumed in same night |
| Forensic specialist, free night | Eligible evidence selector and own completed sample results | Player-health selector; raw case twist or untested authenticity mask |
| Coroner, after a recorded death | Own casualty-specific report | Living-patient treatment/health dashboard; autopsy for surrender |
| Watcher, free night | Legal watch target and own prior visit reports | Registry query or unobserved full plate |
| Citizen / other no-night-action role | Public dossier, own notebook/role, relevant rules | Generic “night action” button with no legal action; specialist/criminal categories |
| Killer / accomplice / poisoner / spy | Only that role's explicitly granted current abilities and own/team-authorized data | Other criminal specialists' powers; hospital/police datasets |
| Suspect in interrogation | «پاسخ به سؤال»، own defense, existing private archive read-only | New ordinary night action, specialist search, another suspect's room |
| Temporary jail | Permitted read-only history and custody status | New powers, new confidential data or public submission controls |
| Eliminated / surrendered | Public spectator dossier and own previously delivered archive | New action/query/vote, live rebuilt role archive |
| Host who is also a player | Own role menu plus private host-management entry | Any extra specialist data; phase-vote override |
| Paused | Existing records and pause status; Resume only for authorized host | New action/query/release controls |

Reporter, lawyer, hunter, scapegoat, serial killer, grocer and smuggler follow the complete section 12.2 matrix; their menus use the same capability/phase filter. Do not invent an active power for a role whose objective is passive. The four roles absent from standard pools remain subject to supported-rotation validation.

### 13.4 Single structural flow for menus, actions and data

Proposed responsibility boundaries, preserving the existing engine/adapter separation:

1. **Resolve context:** authenticated actor, actual originating message, active match/table, group vs DM. Navigation such as Home, Back and Cancel also resolves this context.
2. **Build a read-only view context:** match ID/version, case, cycle, phase, paused state, actor's current role/custody, host flag, explicit capabilities, quotas and visible record IDs. Do not place the full secret state into a public view object.
3. **Authorize action/read:** one capability policy checks actor, operation, resource visibility and lifecycle. `RoleDef.info` is a display/data category, not the sole access decision.
4. **Build the keyboard:** select legal actions from that same policy and destination; group board remains actor-neutral. Never use an unfiltered “all commands” fallback inside a live match.
5. **Execute in engine under the match lock:** revalidate at click time, commit action/query, and emit typed events/results. Reads return stored observations, not fresh secret-derived deductions.
6. **Persist state and report delivery:** save cycle and event version before dispatch; private delivery checks current authorization. A view refresh cannot advance game state.
7. **Render one consistent response:** shared header, actor-safe body, contextual Back/Cancel, and only current relevant buttons. Adapter handles transport and retry, not new game facts.

Keep UI labels in `ui.py`/`menus.py`, policy and phase transitions in the engine or a dedicated policy module, routing in `bot.py`, persistence in `db.py`, and transport in `telegram_app.py`. These are implementation directions for Claude, not a request to refactor blindly. Add only the separation needed to make rules shared and testable.

### 13.5 Day/night tracking contract

Use one authoritative cycle number; `day` can remain its compatibility name. Also track the **last resolved night**, phase/version, and report ID explicitly. Do not infer the last completed night from the current phase or a formatted string.

| Transition | Counter/report rule | Example header |
|---|---|---|
| Lobby → initial night | Set cycle 1 once; no dawn report yet | «پروندهٔ چای تلخ · شب ۱ · انتخاب توانایی» |
| Night N → dawn | Resolve Night N once; save report N; cycle stays N | «روز ۳ · صبح · گزارش شب ۳» |
| Morning → discussion → vote | Cycle stays N; report N remains current | «روز ۳ · گفتگو · آخرین گزارش: شب ۳» |
| First tie → runoff | Same cycle N, new ballot version only | «روز ۳ · دور دوم رأی‌گیری» |
| Approved end of day → next night | Consume valid phase approval once; increment to N+1 once | «شب ۴ · انتخاب توانایی» |
| Suspect enters interrogation for next night | Use the same next-night transition, not an additional increment | «شب ۴ · بازجویی در جریان» |
| Jury/custody decision during day | Keep current cycle; no invented night report | «روز ۴ · هیئت منصفه · گزارش شب ۴» |
| Release/surrender during unresolved Night N | Record event without claiming dawn; preserve last resolved report N−1 | «شب ۴ · آخرین گزارش تکمیل‌شده: شب ۳» |
| Pause/resume | No cycle increment or new report | «شب ۴ · متوقف · آخرین گزارش: شب ۳» |
| Win during any phase | Final event/phase attached to current cycle; no N+1 transition | «پایان بازی · دور ۴» |
| Restart | Restore cycle, last resolved night, phase version, pending deliveries and quotas | Same header/report as before restart |

All menu, archive, status, role-result, hint, ballot and timer messages carry this shared context. Use Persian digits in display; internal IDs stay stable. A doctor's record separately states its observation time and release day. An officer lookup separately states the observed incident and lookup completion day. “Current Day 4” must not relabel a Day 2 medical observation as new data.

Persist a unique transition/report identity such as `(match_id, night_number)` and a state version; callbacks refer to their originating version. Repeated timer jobs, old buttons, reconnects and delivery retries cannot increment the cycle, consume approval twice or reroll hints. Different matches retain independent counters. On invalid/incompatible recovery, show a recovery status rather than silently presenting a fresh lobby as the previous game.

### 13.6 Follow-up acceptance checks — HT51–HT62

These are required tests for the implementation, not test results from this note-only review.

| ID | Scenario | Expected result |
|---|---|---|
| HT51 | Start each supported composition; enumerate menus for every actor in each reachable phase | Only game-relevant, actor-legal controls; no specialist/criminal category for the wrong role |
| HT52 | In live group game, use private Home/Back/Cancel, save a note/will, and trigger an error | Same active match and cycle retained; no pre-game/all-command fallback |
| HT53 | Open public board as doctor, officer, killer and citizen | Identical actor-neutral board; private role buttons/data appear only in respective DMs |
| HT54 | Host and ordinary player open current-game management | Host gets pause/resume/transfer as appropriate; no new-match replacement or role privilege |
| HT55 | Click old New/Join/Start/role button after game starts, changes phase or ends | Safe contextual response; no replacement, stale action, data leak or resource charge |
| HT56 | Doctor/officer dies or is jailed; reopen archive and receive pending correction | Historical authorized data only; no fresh rebuilt chart, plate or correction beyond current entitlement |
| HT57 | Open doctor/forensic archives repeatedly without clinical observations or completed analysis | No invented admissions, alignment-derived health signal, raw twist or unearned authenticity result |
| HT58 | Night 1 → Day 1 → vote/tie/runoff → approved Night 2; repeat through Night 10 | Exactly one increment per new night; all screens and report IDs agree |
| HT59 | Suspect surrendered/released during unresolved night; jury opens/closes | No synthetic dawn or skipped resolution; last completed-night report remains correct |
| HT60 | Restart before/after night commit and before/after report send; replay timer | Same cycle, clue facts and quotas; no duplicate transition or missing report |
| HT61 | Two concurrent tables at different cycles; navigate Home and select an existing table | Each header/action stays table-bound; old buttons never silently target the newly selected table |
| HT62 | Plate observation, ownership record, forgery and historical lookup differ | Distinct versioned records; no retroactive erasure of original result; color/model public, plate officer-only |

**Claude priority for this addition:** fix contextual navigation and capability checks before adding more buttons; replace invented archive data with stored observations; then centralize cycle/report transitions and validate every menu path. Do not claim that a role-specific label or a displayed day number alone satisfies access control or ongoing-game tracking.
