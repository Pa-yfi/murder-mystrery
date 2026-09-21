# Karagah game rules — release-target specification v2.1

Date: 2026-09-21

**Latest clue/access decision:** R09 now permits fictional appearance and vehicle-description clues, gives the detective one person-detail search per game day, and grants **both detective and officer** private access to observed plates and case-linked owner inquiries. This supersedes the officer-only plate restriction in earlier documents. Public clues may show supported appearance, vehicle color and model; full plates and registry results remain in the two authorized roles' private bot workflows.

**Latest custody decision:** R04, R05, R07 and R08 now define human interrogation → officer-only closing hint → direct temporary detention or a private two-person jury. Jurors are unconverted city-aligned players. Temporary detention lasts **two complete subsequent nights in every mode**, with a release-vote opportunity when a different suspect enters interrogation. These rules replace the earlier whole-town jury, 60% acquittal threshold, automatic officer appeal override and one-night Blitz detention. They are requirements for implementation, not a claim the current bot already follows them.

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
| Detective / کارآگاه | One alignment investigation OR evidence-authenticity check per night; additionally one person-detail search per game day; private vehicle/plate and owner inquiries under R09 | Day search reveals fictional descriptive records, not alignment; no consecutive-night alignment investigation of the same player; framing/hiding follow R06; no hospital charts or general police files |
| Officer / بازجو | Private human interrogation; closing hint; direct temporary detention, release, or two-person jury; private juror names; police files and vehicle/plate inquiries shared in scope with detective under R09 | Must be alive, free, current officer and not the suspect; decision requires closed conversation and acknowledged hint; cannot override active jury; no detective-only daily person search |
| Forensic specialist / پزشک قانونی | Select one evidence ID for a private early lab result each night | Evidence target, not arbitrary player target; authenticity is distinct from guilt |
| Doctor / پزشک | Protect one other player; clear/prevent poison on the protected player that night | Cannot self-protect or protect last night's target, including by editing an action |
| Watcher / نگهبان | Observe visits to one target; privately receive the defined visit count | No automatic visitor identity, alignment, or transcript access |
| Reporter / خبرنگار | Publish one additional unrevealed eligible evidence item | No secret roles, duplicate evidence, or private notes published |
| Lawyer / وکیل | Submit an attributed defense summary and one request for jury referral in an eligible supported mode | The request does not open a second jury, replace officer authorization, reveal jurors, or bypass the closing-hint gate |
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
3. **Morning:** resolve the night exactly once, publish deaths/public evidence, privately deliver findings. Finish a pending custody decision before opening a new discussion; apply the explicit timeout fallback if necessary.
4. **Discussion:** living eligible players debate public information. Private messages stay private.
5. **Approval and nomination:** a separate majority vote approves ending the day, then an accusation ballot chooses a suspect; latest valid ballots count. Approval and accusation are distinct votes. A timeout cannot supply missing player approval.
6. **Interrogation night:** when a suspect is nominated, the next night begins once and the suspect enters a private room with the officer. Other eligible players take their night actions. The room is an overlay on that night, not an extra night. A different new suspect also opens the R07 release opportunity for existing temporary prisoners.
7. **Custody decision:** after the real conversation closes and its private closing hint is acknowledged, the officer may decide immediately under R07 or refer to R05's jury. A full interrogation night is no longer a prerequisite. Decisions do not resolve the night, increment the day, or create an extra custody night; the ordinary cycle then continues.
8. **End:** terminal outcome, public role reveal, explanation, per-player results, and idempotent reward recording.

There is no separate functional “final court” phase in this ruleset; it is presentation of the final result, not an unimplemented transition players can enter.

Night, discussion, voting, conversation, jury and custody decisions have explicit deadlines. A timeout must not invent a human statement or silently convict someone. Target defaults: 60-second ordinary night, 180-second discussion, 90-second accusation vote, 120-second conversation, 90-second jury, 90-second release ballot and 60-second officer decision. Blitz halves these interaction durations, with a minimum of 30 seconds; it never halves the two-night temporary sentence. If a required room, jury or release ballot is still active at the night deadline, hold night resolution until that bounded proceeding ends. This preserves player time without creating another night. These are target defaults, not claims about existing timers.

The end-day approval threshold is more than half of currently eligible voters (`floor(eligible / 2) + 1`), with one editable approval per voter. With no majority, remain in discussion and show the tally; do not turn abstention or elapsed time into approval. Every new night consumes one approval except the initial Night 1. The bot always displays the match and current day/night; pause, jury, release ballots and room completion never increment the cycle themselves.

If neither officer nor jury can legally decide before the custody-decision deadline, release the suspect without declaring them factually innocent. Announce this procedural release.

## R05. Nomination and the private two-person jury

- Alive/free players vote once per round; changing a vote replaces it. Self-votes and votes for dead/life-jailed/temporary-jailed players are invalid. A player can explicitly abstain.
- A unique highest tally nominates a suspect. No votes means no arrest; the already-approved next night begins once. Never use an empty ballot to bypass day-end approval.
- A first tie opens a new timed runoff among tied leaders. A second tie yields no arrest. Announcements and buttons must match the actual phase.
- Anonymous mode hides voter-target mappings. It cannot be switched off mid-round.
- Vote rewards use effective final ballots only. Message count, duplicate taps, and edits never multiply XP or accuracy credit.

### R05.1 Selection and notification

After the conversation/hint gate, the officer can press **«⚖️ ارجاع به هیئت دو نفره»**. The bot chooses exactly two distinct eligible jurors, stores their identities for this custody episode, and sends each a private ballot. Eligibility means **currently city-aligned, never converted/recruited during this match, alive, free, able to receive the private ballot, and neither the suspect nor the officer**. “Citizen” here includes city-aligned specialist roles as well as the plain citizen; restricting it to the plain role would make most standard compositions impossible. Neutral roles are not eligible.

Choose without replacement using the match's stored random state; rotate away from recently used jurors where enough candidates exist. Reopening the panel must never redraw the jury. The officer cannot choose their names. Two devices/accounts cannot cast two votes for the same player.

- Juror message: «⚖️ برای پروندهٔ {episode} در روز/شب {N} عضو هیئت منصفه شدی. دربارهٔ حبس موقت {suspect} رأی بده. نقش افراد و گفتگوی خصوصی در اختیار هیئت قرار نمی‌گیرد.»
- Juror buttons: **«🔒 حبس موقت»**, **«🕊️ آزادی»**, and **«نمی‌توانم داوری کنم»**. Each sees their own receipt and may edit until both valid ballots finalize or the deadline expires.
- Officer sees the two jurors' display names and ballot-delivery status, **never their exact roles**. The public group receives only the fact that a jury is considering this case, not juror identities. Jurors are not shown one another's names or votes by the bot.
- The packet contains released public evidence, the suspect's deliberately shared defense and any permitted attributed summary. It excludes the officer's private closing hint, full plates, private medical charts and raw room transcript.

**Information tradeoff:** because selection is restricted to unconverted city members, naming jurors to the officer necessarily reveals their city eligibility at selection time. Exact roles remain hidden, but alignment is inferable. This follows the owner's requested rule; do not promise that juror alignment stays secret from the officer. This information advantage needs small-game balance testing.

### R05.2 Decision and failure handling

Both selected jurors must vote **temporary jail** to order temporary detention. Two freedom votes or a split vote release the suspect. A missing effective ballot at the deadline also causes **procedural release**, not a finding of innocence. Show the aggregate outcome to the officer and group; individual vote choices remain private.

Once referred, the officer cannot cancel the jury to obtain a different outcome, add detention during voting, or reverse its result in the same episode. A subsequent arrest needs a fresh valid nomination; it cannot be an immediate retry of the same closed jury. A genuinely new custody episode gets a new jury opportunity.

If a juror declines, dies, becomes detained, loses city eligibility or cannot receive the ballot before finalization, invalidate that juror's ballot and replace them once a new eligible candidate is available. Keep the other valid ballot confidential and keep the original deadline; replacements do not create unlimited waiting. Revalidate both jurors at finalization. Never fill an empty seat with a criminal, neutral, converted citizen, suspect or officer.

If **fewer than two eligible candidates exist before referral**, do not open a one-person jury. Tell the officer only «هیئت دو نفره در این دور قابل تشکیل نیست»; do not expose the rejected candidates or their eligibility reasons. The officer may still use the direct-decision options if they satisfy the conversation/hint gate. If the jury has already opened and cannot finish with two eligible ballots, the deadline produces procedural release. Officer unavailable/self-accused cases use R07's fallback and cannot be self-judged.

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

### R07.1 Interrogation → closing hint → decision

Each arrest creates a new custody episode tied to match, suspect, current officer and cycle. Its decision sequence is:

**Human conversation open → conversation closed → officer-only closing hint delivered and acknowledged → officer decision or two-person jury → release or temporary jail.**

At least one actual officer question and one actual suspect answer constitute a completed exchange. After that exchange either participant may request closure with «پایان گفتگو»; the other gets a short final-response window within the existing room deadline. Closing stores the final sequence and prevents later messages from being inserted before the hint. A pre-existing explicit final reply can close the room immediately when both agree. Conversation length must not depend on secret guilt.

No answer, failed delivery or timeout produces an **incomplete-conversation closure**, explicitly labeled as such. It never produces a synthetic reply or an adverse demeanor finding. To prevent an absent player being convicted through invented evidence, an incomplete episode ends in procedural release; the officer can use a fresh later nomination if warranted. A player cannot keep the night open indefinitely by repeatedly requesting more time.

For a completed exchange, send one stable private closing hint to the officer **regardless of the suspect's true alignment**. Decision controls appear only after the officer opens/acknowledges that hint. Acknowledging a hint is not a verdict. Failed hint delivery leaves the decision gated until retry or the decision deadline; at expiry release procedurally.

The officer's controls are:

1. **«🔒 حبس موقت برای دو شب»** — direct order after the gate, with a confirmation identifying the correct suspect/episode and expiry rule.
2. **«⚖️ ارجاع به هیئت دو نفره»** — R05's private jury chooses detention or release.
3. **«🕊️ آزادی؛ شواهد کافی نیست»** — an explicit non-punitive option; release does not expose alignment.

No direct permanent-jail button exists. The bot never chooses detention because it knows a player's role. Arrest ends powers while the suspect is questioned; discussion of evidence and actual human replies remains possible in the authorized room.

### R07.2 Closing-hint content, role context, time and sequence

Hints are **ambiguous role-play cues and evidence-linked observations**, not diagnosis, lie detection or a hidden alignment score. Each stored hint records episode, suspect, source message/event IDs, observation sequence, relevant night/day, role-play context, visibility and limitations. Identical repeated reads return the same hint; a new episode may produce a different cue only from that episode's context.

- Use actual message sequence: hesitation is a measured delay only when delivery times are reliable; connection delay remains an alternative. A contradiction quotes two actual claims with their sequence/timestamps and the permitted evidence it conflicts with.
- “Demanded a lawyer” appears only if the player actually requested legal help in text or through a button. That request is neutral and cannot count as proof of guilt or as a negative vote modifier.
- A Telegram bot cannot see sweating or shaking hands. Such cues are allowed only as clearly labeled **fictional scene narration**, drawn from an independently assigned scene/emotional state, or as attributed self-description submitted by the player. They cannot be presented as observed real behavior.
- Role-specific context concerns the character's fictional task and knowledge, not a direct role reveal. A doctor may discuss care timing, a watcher observations, a citizen routine access. Do not tell the officer the secret role through exclusive wording or a role-specific cue dictionary. Use multiple role-plausible variants and information the suspect has actually disclosed or that the officer is entitled to know.
- Innocent and criminal suspects can both be calm, nervous, demanding or inconsistent. Do not select intensity from `align`, score stress from role guilt, or force every criminal to display a tell. A valid alibi or coherent answer is also a useful closing observation.

Examples; render only when the stated trigger exists:

| Trigger and sequence | Officer-only closing hint | Limit |
|---|---|---|
| Suspect chose a fictional nervous stance after question 2 | «روایت صحنه: پس از سؤال دوم، دست‌های شخصیت می‌لرزید. این توصیف نمایشی است؛ ترس از اتهام هم می‌تواند آن را توضیح دهد.» | Not real visual observation or an alignment hint |
| Stored hot-room scene; suspect's declared discomfort precedes the accusation | «روایت صحنه: پیش از طرح اتهام هم از گرما شکایت داشت و عرق می‌کرد؛ این نشانه را به اتهام نسبت نده.» | Context and ordering can explain away suspicion |
| Real “I want a lawyer” message after question 3 | «در پاسخ سوم درخواست وکیل کرد. این درخواست، حق دفاع است و دلالتی بر گناه ندارد.» | Does not summon/reveal a hidden lawyer automatically |
| Actual care-related account changes between answers 1 and 4 | «در پاسخ اول زمان مراجعه را پیش از خاموشی گفت؛ در پاسخ چهارم پس از خاموشی. منبع ساعت هنوز روشن نیست.» | Quote only real claims; do not announce “the doctor lied” |
| Actual account matches two authorized independent sources | «ترتیب گفته‌های او با دو ثبتِ قابل‌دسترسی سازگار است؛ سازگاری، هویت تیمی را ثابت نمی‌کند.» | Include exculpatory cues as well as suspicious ones |
| No reliable demeanor/contradiction source | «نشانهٔ رفتاری قابل اتکایی ثبت نشد. تصمیم را بر مدارک منتشرشده و پاسخ‌های واقعی بنا کن.» | Valid hint; never fabricate a tell to fill the screen |

### R07.3 Temporary jail: two complete subsequent nights

Detention begins immediately after the confirmed officer order or finalized jury order. The prisoner cannot act at night, vote, submit public game messages, receive new privileged role data or join a jury. They may privately read already delivered notes/results and see their custody clock. They remain alive for R10's victory count until permanent imprisonment or death.

The sentence is **two complete subsequent resolved nights**, including in Blitz. Admission during Day N counts Night N+1 and Night N+2. Admission during Night N does **not** count that partially spent night; it also counts Nights N+1 and N+2. Save admission cycle, first eligible night and distinct completed-night IDs. Never increment custody for a timer poll, hint read, jury ballot, pause, phase rename or repeated dawn.

Example: detained on Day 2 → «۰ از ۲ شب»; after Night 3 resolves → «۱ از ۲ شب»; after Night 4 resolves → permanent jail unless already released. Detained during Night 2 has the same two future full nights. The bot shows the exact eligible nights and current count, not an ambiguous wall-clock countdown.

### R07.4 Release vote when a different suspect enters interrogation

Each valid entry of a **different** new suspect creates one release-vote opportunity for each existing temporary prisoner. This is a public-electorate release process, **not** the new suspect's secret two-person jury. The officer has a “request release review” control, but cannot bypass the ballot to release a prisoner unilaterally.

- Electorate: currently alive/free eligible players, excluding the temporary prisoner and anyone currently under interrogation. It includes all alignments; criminal players may bluff and vote here. Do not reuse the private jury's city-only filter for a public vote, since that would expose eligibility through exclusion.
- For each prisoner, buttons are **«🕊️ آزادی {name}»**, **«🔒 ادامهٔ حبس»**, **«ممتنع»**. One editable ballot per eligible player. No new accusation or sentence extension occurs in this vote.
- Release needs more than half of the current eligible electorate, not merely half of those who answered. With four eligible voters, three release votes are required. Abstention, tie, zero electorate and timeout leave the existing sentence unchanged; they never add an extra night.
- Opening an appeal does not reset the prisoner's night count. If multiple prisoners exist, use separate labeled ballots under one bounded release window. Each `(new-suspect episode, prisoner episode)` pair can be opened only once.
- Keep ballots open for the announced release window and finalize them before the current night's resolution. If a prisoner's second eligible night is due, a successful release takes precedence over that night's custody escalation. Do not extend the window indefinitely or hold already completed escalation retroactively.
- This opportunity is triggered by the new suspect's arrival; it remains valid until its original deadline even if that suspect is promptly released. Repeated screen opens or repeated nomination events for the same episode cannot manufacture additional appeals.
- When released, restore the prisoner's original role permissions prospectively, clear the current detention episode, cancel its scheduled escalation and announce **procedural release**, not innocence. If the action deadline for the current night already passed, do not grant a retrospective night action. Any later fresh arrest starts a new episode/count.

### R07.5 Permanent jail, unavailable players and victory

After the second eligible night finishes, apply any valid completed release first, then convert surviving unreleased temporary prisoners to permanent jail exactly once. Permanent jail means elimination: no abilities, voting, jury membership, fresh private findings or public game communication. Previously delivered private records remain read-only; public spectator-safe viewing is allowed. No further release ballot applies to permanent jail in this ruleset.

- No role is revealed merely because a player dies or enters life jail. Roles are revealed at match end.
- A dead suspect's case/room closes immediately. Do not allow a verdict against a stale suspect or leave their custody blocking the next phase.
- If the officer becomes unavailable before referral, use a procedural fallback: an eligible two-person jury may consider the public packet after the human conversation opportunity closes, with an explicit “officer unavailable” reason and no invented private hint. Without two eligible jurors, release procedurally. The host receives no officer files or juror identities. If the officer is the suspect, they cannot see this episode's juror names or judge themselves.
- If the officer disappears after a jury opens, the already valid jury completes independently. If the suspect dies/surrenders, close their proceeding without a detention/release verdict against a nonexistent active suspect.
- A temporary prisoner can still be affected by attacks/poison under R06. If dead before escalation, close the sentence as death; do not also life-jail them or trigger the scapegoat's imprisonment win.
- Permanent imprisonment triggers the hunter/scapegoat rules where applicable. Evaluate R10 after the full simultaneous event batch. A killer's **temporary** detention is not victory; permanent elimination of the last hostile actor may be. Finding a suspicious plate, receiving a hint or a jury's accusation never itself declares a winner.
- Emergency `/sos` becomes an **expedited nomination into this same interrogation process**, not an immediate detention bypass. It remains once per match and needs 80% of current eligible other players, rounded up. A successful nomination proceeds with the next player-approved night; it does not itself approve that transition. Only one suspect episode can be active at a time.

### R07.6 Small-game and fairness boundaries

A four-player composition may have fewer than two eligible city jurors after excluding the officer and suspect. That is a real limitation of the requested city-only jury rule, not a reason to secretly recruit an ineligible juror. Display the unavailability generically and use the direct-decision or procedural-release fallback above. Do not promise every accusation gets a jury at every seat count.

Every suspect receives the same conversation deadline, closing-hint procedure and defense access regardless of actual role. Neither nervousness, a request for legal help, an officer accusation nor a jury result reveals alignment. Public and private reports retain episode/day IDs so repeated arrests and several temporary prisoners cannot mix identities or sentences.

## R08. Private two-person communication

- An interrogation room belongs to one match, round, officer, and suspect. Authenticate both senders from Telegram updates.
- Officer questions are relayed to the human suspect; human answers are relayed to the officer. No rule-based or AI answer may be presented as something the human said.
- Both participants see delivery acknowledgements. Group messages reveal only public custody events, not the transcript or question contents.
- Private hints remain officer-only. The spy receives only the specific R02 metadata, never room contents.
- The R07 closing hint appears only after the real conversation closes. The decision keyboard is bound to that closed episode and acknowledged hint. It cannot be invoked early through a typed command or stale callback.
- A request for a lawyer is relayed as the suspect's own request, not interpreted as guilt. A lawyer-role player may provide a permitted attributed defense summary voluntarily; the bot never reveals that role or adds a third person to the private room automatically.
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

### R09.1 Fictional appearance and vehicle clues

Clues may describe a **tall or short character, a woman or man as described by the witness, approximate build, hairstyle, beard, glasses, a facial scar, clothing, an accessory, gait, or a vehicle's color/model**. Use only details supported by the fictional observation. A distant silhouette may establish height/build but not a facial scar; poor lighting may support “dark vehicle” rather than a precise color. Witness descriptions are attributed observations, not infallible identity facts.

At match creation, assign fictional character descriptions independently of role/alignment and make each player's own description privately available. These are characters, not claims about the real Telegram users. Do not inspect profile photos, infer players' real gender/appearance, or require real identity, medical or vehicle data. Description and appearance never make someone more criminal by themselves.

Store an appearance profile and, where relevant, a time-indexed clothing/accessory or vehicle-use record. A later change requires a recorded in-game event; do not silently change a character's height, scar, vehicle or ownership to fit the currently accused player. Profiles may overlap. Keep enough plausible alternatives early in the case that one broad descriptor is not an automatic role reveal.

Every descriptive clue includes source, incident/night, observation window, visible detail, uncertainty and a verification path. It must distinguish **observed person**, **registered vehicle owner**, **vehicle user/driver**, **suspect** and **confirmed actor**. Do not call a car “the killer's car” merely because its owner is a suspect. A plate can identify a registry record without identifying the driver.

Examples, conditional on stored supporting observations:

| Clue | Permitted text | Useful next step |
|---|---|---|
| Public witness description | «شاهد شب ۲ فردی قدبلند با بارانی تیره دیده و او را زن توصیف کرده است؛ صورت از این فاصله مشخص نبوده.» | Compare height/clothing and timing; do not invent facial detail |
| Public closer observation | «دوربین ورودی در شب ۳ مردی کوتاه‌قد با عینک گرد نشان می‌دهد؛ سمت چپ صورت پوشیده است.» | Test compatibility with a fictional profile; covered features remain unknown |
| Public facial detail | «در تصویر روشن ورودی، خطی شبیه جای زخم کنار ابرو دیده می‌شود؛ کیفیت تصویر برای شناسایی قطعی کافی نیست.» | Request a supported person-detail comparison and independent observation |
| Public vehicle detail | «یک پژو ۲۰۶ خاکستری در بازهٔ ۲۲:۴۰ تا ۲۲:۵۰ کنار درِ پشتی دیده شد؛ چهرهٔ راننده روشن نیست.» | Compare route/time; authorized investigator checks plate privately |
| Private plate clue, detective or officer | «خودروی ثبت‌شده در مشاهدهٔ V12: پژو ۲۰۶ خاکستری؛ پلاک ساختگی بازی SIM-047. این مشاهده هویت راننده را ثابت نمی‌کند.» | Case-linked private registered-owner inquiry |

The examples are authored fiction, not facts to print in every match. Attribute misidentification to an explicit unreliable source and provide a way to check it. Do not generate arbitrary false descriptions as verified system observations.

### R09.2 Detective's daily person-detail search

The detective gets **one new person-detail search per game day**, separate from the existing nightly alignment/evidence choice. Day means the game's numbered day, not calendar midnight. The allowance becomes available after each completed dawn and does not accumulate if unused. It is available during morning/discussion while the detective is alive, free and the game is unpaused.

Private workflow: **«🕵️ بررسی مشخصات یک نفر» → choose one player in the current match → confirm target → receive a stored private descriptive report**. Living players, current suspects and temporarily jailed players may be subjects; dead/permanently jailed subjects use already released historical evidence instead of a fresh daily search. Actor eligibility and subject eligibility are separate.

The report returns the selected character's relevant fictional identifying details, record time and a bounded comparison to released observations: e.g. height category, recorded appearance/accessory, and whether a visible feature is compatible, incompatible or unknown. It does **not** reveal role, alignment, guilt, hospital chart, hidden action, current secret location, other players' profiles or unreleased clues. Matching a description is not proof the person was present.

Example:

> 🕵️ بررسی مشخصات — روز ۳، فقط برای کارآگاه
>
> شخصیت: {نام انتخاب‌شده}
>
> مشخصات ثبت‌شده: قدبلند؛ عینک گرد؛ موهای کوتاه.
>
> مقایسه با مشاهدهٔ W7: قد و عینک سازگارند؛ تصویر دربارهٔ مو اطلاعات کافی ندارد. این تطبیق، حضور در محل یا گناه را ثابت نمی‌کند.
>
> سهمیهٔ امروز: استفاده شد. نتیجهٔ همین بررسی در دفترچه باقی می‌ماند.

Reject invalid targets without consuming the allowance. Once a valid search is committed and its result durably stored, the allowance is spent even if delivery needs retry. Reopening/retrying returns the same result free; changing targets is not permitted after commitment. A later game day may examine the same person again, but unchanged records must be labeled unchanged, not fabricated as new discoveries. The no-consecutive-target restriction remains specific to the nightly alignment investigation.

No search during voting, an active jury, night, custody, elimination or pause. Release restores remaining current-day eligibility, not missed-day credits. Restart, table switching, duplicate requests and a new interrogation episode cannot reset the allowance. A new match has its own independent quota and fictional profiles.

### R09.3 Plates: detective and officer share private investigation access

Both **کارآگاه** and **بازجو** can see full fictional plates in authorized case-linked vehicle records and investigate the registered owner directly inside the bot. This does not give the detective all police files, juror names, private interrogation hints or officer verdict powers. It does not give the officer the detective's daily person-detail or alignment search.

Use the same private workflow and factual source for both roles: **«🚘 مشاهدهٔ خودرو» → «پلاک ثبت‌شده» → «🔎 استعلام مالک» → stored result**. An inquiry requires an actually available vehicle lead with a sufficiently legible plate. No arbitrary real plate search, all-owner enumeration or hidden-lead probing is permitted.

Target rule: each role holder can commit **one new plate inquiry per night**, with its result delivered at dawn, separately from their other ability budgets. Reopening an already delivered vehicle record/result costs nothing. The two investigators have independent quotas and inboxes; one person's request does not disclose that person's role or consume the other's allowance. Both must receive consistent facts for the same record version.

Result fields: fictional plate ID, observed vehicle color/model at supported precision, registered owner at the relevant record date, any authorized recorded loan/rental/use history, and unresolved driver identity. An inconclusive/partial plate remains inconclusive; no automatic guess. Ownership changes, substituted plates and forged documents remain distinct versioned events and cannot erase old findings.

Only alive/free eligible holders receive new inquiries or fresh privileged results. Recheck eligibility at delivery, including corrections. Existing results stay privately readable under R03. Public reports, group buttons, media, logs and jury packets omit full plates and raw registry results. An investigator may deliberately publish an allowed attributed summary, but the bot's sharing action must preview and redact restricted fields. Color/model can be public where supported.

### R09.4 Appearance/plate access acceptance checks

These are implementation requirements, not tests executed for this document update.

| ID | Scenario | Required outcome |
|---|---|---|
| IDV01 | Generate characters/clues for different roles, cases and seeds | Fictional profiles exist independently of alignment; observation detail matches source visibility |
| IDV02 | Detective searches A, then B on the same game day | A yields one durable private report; B denied without second disclosure; reopen A free |
| IDV03 | Next dawn, wall-clock midnight, restart or repeated callback | Only a genuinely new game day renews the person-search allowance |
| IDV04 | Description matches several players or visible features conflict | State compatibility/uncertainty accurately; never return automatic guilt |
| IDV05 | Officer/citizen/other role requests detective's person-detail endpoint | Denied without profile leakage; plate permission does not imply person-search permission |
| IDV06 | Detective and officer independently query the same valid plate/version | Both authorized privately, same factual record, separate quotas; other roles denied |
| IDV07 | Borrowed/cloned/substituted plate or changed ownership | Preserve source/version/use history; registered owner is not automatically driver or killer |
| IDV08 | Investigator detained/eliminated before delivery or after earlier result | No fresh unauthorized result; previously delivered report stays historical/read-only |
| IDV09 | Public hint, media, logs, jury packet and share preview | Supported color/model/appearance only; full plate and raw registry result remain restricted |
| IDV10 | Reused case in a new match or two parallel tables | Independent profiles/quotas and bound callbacks; no prior-match identity or data leak |

**Synchronization:** officer-only plate statements in `hints.md` and earlier handoffs are superseded by this section. Claude must update role cards, archive access, plate endpoints, private menus and tests together. The new daily descriptive search is distinct from the nightly alignment power; do not implement it by calling that power for free.

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
| R04–05 | VOT, CUS, JUR | Historical city/jury journeys are not validation of v2's private two-person jury; new checks below are required |
| R06 | NGT | Existing night-ability tests plus doctor/detective/hunter/trace contracts; remaining combinations planned |
| R07 | CUS, JUR, SOS | v2 replaces old petition/whole-town jury and Blitz custody expectations; conversation, release and permanent-jail journeys require new tests |
| R08 | MSG | Delivery privacy and relay acceptance contracts; full human room missing |
| R09 | NGT-21–25, evidence direction | Six evidence/usefulness contracts; content review of all case generators/types |
| R10 | END, DB | Serial winner, payout retry, ending restart, repeated-result contracts |
| R11 | TIM, DB, OPS | Timer persistence, pause boundaries, file DB restart integration |
| R12 | SEC, OPS, edge cases | Integer bounds, oversize note output, quotas, repeated input, SQL parameter handling, redacted repository signature scan |

The latest recorded results and untested boundaries are in [audit-results.md](audit-results.md). Any rule change must update this applicability mapping, acceptance expectations, and regression contracts before release.

### Custody v2 acceptance cases — required, not yet executed

| ID | Scenario | Required result |
|---|---|---|
| CJV01 | Officer tries verdict before actual answer, room closure or hint acknowledgement | Rejected without custody mutation |
| CJV02 | Innocent and criminal complete identical exchanges | Same gate and deadline; no alignment-dependent demeanor cue |
| CJV03 | No reply / blocked DM / room timeout | No synthetic testimony; procedural release and bounded phase hold |
| CJV04 | Player requests lawyer / selects role-play stance / gives no cue | Actual request attributed neutrally; fictional cue labeled; valid no-cue fallback |
| CJV05 | Officer refers with two eligible unconverted city jurors | Exactly two private notifications; officer sees names, not exact roles; group sees neither |
| CJV06 | Jury votes jail/jail, free/free, jail/free or one missing | Respectively temporary jail, release, release, procedural release |
| CJV07 | Juror recruited, eliminated, jailed, declines or cannot receive DM | Remove invalid ballot; eligible replacement under original deadline or release; no ineligible seat |
| CJV08 | Fewer than two eligible jurors in 4-player/late game | No one-person jury; correct direct-decision or officer-unavailable release fallback |
| CJV09 | Officer attempts detention while jury is active or after release | Denied for same episode; reopening cannot reroll members/results |
| CJV10 | Admission on Day 2 or during Night 2, standard and Blitz | Count only completed Nights 3 and 4; no partial-night credit |
| CJV11 | Different suspect enters while one/multiple prisoners are temporary | One separately labeled release ballot per eligible prisoner episode; count not reset |
| CJV12 | Release vote at second-night boundary, or tied/timed-out ballot | Successful release cancels escalation; otherwise original sentence proceeds once |
| CJV13 | Death/poison/surrender before escalation; hunter/scapegoat at escalation | Correct causal elimination and R10 precedence; no duplicate or false imprisonment trigger |
| CJV14 | Officer dies, is detained or becomes suspect | No self-judgment/secret transfer; bounded jury/public-packet fallback or release |
| CJV15 | Restart/retry/old callback during hint, jury or release vote | Same episode, chosen jurors, ballots, deadlines and night count; no reroll/double escalation |
| CJV16 | Last killer detained then permanently jailed, another hostile still active, or no players remain | Temporary jail alone does not win; apply R10 after full batch |

**Documentation synchronization:** the previous jury electorate/threshold and jail-duration wording in `report.md`, `hints.md`, `improvement.md` and existing tests is historical wherever it conflicts with this v2. Claude must update implementation, help/buttons and tests to this explicit flow. The two-person jury and the public release ballot are distinct proceedings with distinct eligibility; never reuse one electorate for the other.
