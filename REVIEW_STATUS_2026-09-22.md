# Implementation status review — 2026-09-22

The latest feature branch contains substantial working additions, but the requirements in the Markdown documents are not all complete. Several older findings are fixed; several newer “implemented” statements describe only the main path and overstate lifecycle coverage.

## Revision and scope

- GitHub checked directly with `git ls-remote origin` on 2026-09-22.
- Repository: https://github.com/Pa-yfi/murder-mystrery
- GitHub default `main`: `f410ebd64903f894d4af5b9f1b62e66ae2b752f6`.
- GitHub `feat/role-access-and-live-boards`: `570fa571e97819d39004d9ed1215637d1ab8c7d9`, identical to local HEAD.
- The feature branch is **five commits ahead of GitHub main**. These changes are on GitHub but are not in its default branch. Local `main` is not the same revision as remote main; the comparison here uses the remotely verified SHA.
- Reviewed all 11 existing repository Markdown files, current implementation, relevant tests and commit differences. Application source was not changed. No live bot or production database was used.

| Commit after GitHub main | Delivered scope |
|---|---|
| `d9ef0c5` | Gameplay handoff, quality contracts and audit documentation |
| `dd1e6ad` | Role archives, vehicle records and live group boards |
| `9f32b6d` | Role-aware menus, navigation context and selected information-leak fixes |
| `ea6ba01` | Human interrogation, closing-hint gate, two-person jury and public release ballots |
| `570fa57` | Character appearances, witness descriptions, detective person lookup, shared plate lookup and non-fabricated closing hints |

## Fresh verification

Executed `.venv/Scripts/python.exe -B tools/run_quality_audit.py` against an isolated source snapshot with dummy credentials, temporary storage, mocked Telegram and blocked external connections.

| Suite | Passed | Failed | Skipped | Setup errors |
|---|---:|---:|---:|---:|
| Existing behavior | 333 | 0 | 5 | 0 |
| Quality contracts | 1,231 | 94 | 0 | 0 |
| Total | 1,564 | 94 | 5 | 0 |

Evidence: [summary.json](qa_results/20260922-140754/summary.json), [existing results](qa_results/20260922-140754/existing.txt), [quality results](qa_results/20260922-140754/quality.txt). Source hashes remained unchanged during the audit.

**94 failed cases do not mean 94 distinct bugs.** At least 52 cases need adaptation to custody v2: 42 city journeys issue a verdict without the new conversation/hint gate; one jury journey uses the old petition workflow; seven cases call the removed `request_jury` API; two permission cases request a hint before closing the room. The remaining 42 failed cases span multiple unresolved behavior contracts, some parameterized. Updating obsolete fixtures is necessary before comparing defect counts to the September 20 audit.

A passing old test can also be misleading: the transcript-limit test only calls `ask()` repeatedly, which now blocks on an unanswered question. It does not prove a quota on repeated completed human exchanges. Officer-state tests can be blocked by the new room gate without exercising actual officer eligibility.

The five skips cover one interrogation-night scenario, three citizen/recruitment scenarios, and daily grocer rumors. They are not completed coverage.

## Implemented and supported by current checks

- Core 4–10-player game, 40-case catalog, 18 role definitions, button navigation, SQLite storage, basic restart recovery and the runner already exist. All 280 case/size opening checks pass; this is not proof of full mystery quality.
- Questions reach the human suspect privately, and actual answers are relayed to the officer. The bot no longer generates the suspect's answer in this workflow.
- Conversation closure and acknowledged closing hints gate normal detention decisions. Hints use actual replies and voluntarily selected fictional stances; lawyer requests are reported only when actually made.
- Two selected city jurors and the jail/jail versus release outcome matrix work in focused tests. Public release voting replaces unilateral officer release. Blitz no longer halves the configured two-night sentence.
- Role-aware menu filtering, private Home/Back/Cancel context, host management, live readiness/voting boards and confirmed surrender are implemented in tested paths.
- Role archives and queued private vehicle-owner inquiries exist. Officer and detective have separate inquiry budgets. A one-use registration-forgery action exists.
- Character profiles, descriptions of actual movers, and a detective person-detail query with a daily quota exist.
- All 18 Persian display-name mappings exist, and role-card text tests verify old/new names together.
- Winner IDs are explicit for implemented winner branches; the serial killer's sole-survivor base reward test now passes.
- Selected older defects are fixed: outsider phase commands, outsider lab/interpretation access, public secret-action counts, and failed-DM public fallback checks pass.
- Pillow and `python-telegram-bot[job-queue]` are now declared in requirements. A fresh clean-environment install was not performed in this review.

These are completed components, not certification of the broader features below.

## Partly implemented — cannot be marked fully done

| Area | Remaining work and evidence |
|---|---|
| Custody v2 and continuous nights | An immediate valid verdict changes INTERROGATION to MORNING before that night's resolution. This was reproduced on the isolated snapshot. The sentence counter has no admission-night identity to enforce the full subsequent-night contract. |
| Jury/room deadlines and fallback | An expired jury tick returns no transition, leaves phase JURY and removes the deadline; reproduced. Room, officer-decision and release proceedings lack the complete deadline/replacement/failure workflow required by R04–R08. |
| Officer/room permissions | `ask`, hints and the decision gate do not consistently check officer life/custody/pause status. Full match/session identity, retry acknowledgements and transcript retention remain missing. |
| Role archives | Revoked access adds a “frozen” label, but `archive()` still constructs fields from current players, deaths and records. Historical access needs actual stored snapshots. Doctor patient-review/history/quota workflows are not delivered merely by the archive label. |
| Person/plate queries | Reproduced: person lookup accepted at NIGHT; plate lookup accepted during DISCUSSION and after END; a fresh plate result delivered to a temporarily detained requester. These conflict with rules.md phase/delivery restrictions. |
| Vehicle provenance | Ownership is overwritten by forgery; there is no complete versioned ownership/use/observation ledger. Correction notifications do not recheck revoked recipient eligibility. |
| Appearance fairness | Narrow random pools encourage overlap but do not enforce the documented guarantee that each witness description leaves another compatible living person. Source review; a complete fairness campaign was not run. |
| Endings and rewards | Explicit winner IDs help payouts, but city can still win with a serial killer alive, the empty-survivor result is wrong, and repeated votes inflate rewards. Smuggler survival accounting remains absent. |
| Role activation and effects | Ordinary role isolation works broadly, but detective custody and hunter elimination restrictions fail; doctor/detective repeat-target restrictions fail; hunter life-jail shot is missing. Forensics still lacks the full selected-evidence workflow. |
| Role availability | Reporter, lawyer, grocer and smuggler are still absent from every standard composition. Grocer archive text exists, but the daily-delivery quality check fails and the new ordinary rumor test skips. Spy information still fails to distinguish real questioning from public nomination. |
| Delivery and reports | Private action/result delivery exists in selected paths, but no single durable, immutable daily report/inbox pipeline guarantees identical manual and timer output plus restart-safe retries. |
| Persistence | Active snapshots work in covered paths. Finalization still sets `finalized` before durable result storage, so retry fails; finished reveals disappear after restart. Versioned migrations and distinct durable match identities remain unfinished. |

## Still unfinished

1. **Player approval before day becomes night.** No separate phase-consent ballot/gate is implemented. `tick()` still automatically opens/closes accusation voting, and `close_vote()` enters the next night without the required majority approval. This is report.md P01 and rules.md R04's central unmet requirement.
2. **Evidence dossier and authored mystery pipeline.** The 40-case D1–D4 plans and eight playlists in hints.md remain design content. There is no corresponding complete prelude/event ledger, immutable dawn-report archive, comparison/help workflow or causal final explanation.
3. **Meaningful and fair evidence.** Fixed fake-card positions, duplicate reveals after deck exhaustion, generic laboratory output and unjustified killer-among-visitors statements still fail quality checks. Rumors are not grounded in a verified event truth model.
4. **Interaction isolation and private logging.** Old callbacks can operate on the newly selected table. Pending text remains keyed only by user and can consume a message from the wrong context. Raw private argument prefixes are still copied into general audit history.
5. **Readiness, bans and input boundaries.** Group readiness can claim private readiness; invite joins can be lost on restart; banned users can join; invalid case selection and signed-64-bit overflow checks fail.
6. **Consistent pause and terminal guards.** Night actions work while paused; resuming with zero time removes the deadline; emergency detention can mutate an ended game; engine start can run again.
7. **Storage/output limits.** Private notes and ballot history remain unbounded under tested contracts, and notes can render a 6,217-character response. Full transcript, cache and delivery retention policies remain unimplemented or unverified.
8. **Release validation.** Update old jury tests, replace seed-based skips with deterministic fixtures, exercise the complete CJV/HT/LOOP requirements, then perform Telegram staging, Persian UX, balance, concurrency and crash-recovery testing. These have not been completed by this offline audit.
9. **Later roadmap features.** PLAN.md phase 2's optional LLM integration, PostgreSQL migration, battle pass, full multi-account/AFK anti-cheat and visual replay are not delivered. Basic reminders/rate limits are not completion of the full anti-cheat proposal. Existing admin tools are already delivered.

## Status of every existing Markdown file

| File | Status against current code |
|---|---|
| [README.md](README.md) | Mostly describes delivered features, but overstates custody/access completeness. Counts are stale: code has 83 registered endpoint names, and this run has 333 existing passes rather than 235. |
| [PLAN.md](PLAN.md) | Original core/version milestones largely implemented; phase 2 pending. Open F-01/02 (synthetic/public interrogation) and F-24 (dependencies) are stale. F-11/12/13/15/16/17/22/23 remain open in whole or part. |
| [report.md](report.md) | Partial. P01 phase consent remains missing; P02 role UI improved; P04 human relay implemented; P03/P05/P06/P07 still have transition, context, delivery or outcome gaps. Old jury instructions are superseded by rules v2. |
| [hints.md](hints.md) | Partial. Sections 12–13 led to archives, plates and menu improvements. The broader evidence architecture, authored 40-case progression, playlists, comparison/help, medical workflow and full lifecycle contracts remain unfinished. Old officer-only plate statements are superseded. |
| [rules.md](rules.md) | Target specification, not a completion checklist. Main custody v2/R14 components exist, but the detailed R01–R12 lifecycle, timing, authorization, evidence and persistence requirements are not all enforced. R13's “full human room missing” statement is stale. |
| [improvement.md](improvement.md) | Scenario/design work and a substantial offline test subset are delivered; the full implementation roadmap and acceptance journeys are incomplete. Historical counts and old custody rules require reconciliation. |
| [evidence-and-roles.md](evidence-and-roles.md) | Completed historical audit; evidence usefulness and four-role availability findings remain relevant. Missing human relay, storm/poison and serial payout descriptions no longer all represent current code. |
| [role-names.md](role-names.md) | Display mapping and role-card text implemented. Stable language-independent IDs, full migration/RTL/image validation and unavailable-role labeling are not established as complete. Its statement that only documentation changed is historical. |
| [audit-results.md](audit-results.md) | Completed September 20 audit of a specific older snapshot. Preserve its historical results; they are not a current pass/fail certificate. Use the fresh evidence linked above for this revision. |
| [qa_results/README.md](qa_results/README.md) | Completed documentation of the committed historical evidence. New local audit runs are intentionally ignored by Git. |
| [qa_results/20260920-081824/test-families.md](qa_results/20260920-081824/test-families.md) | Completed per-family results for the old snapshot only; not the latest implementation status. |

## Recommended order

1. Repair phase approval, unresolved-night custody transitions and bounded jury/room fallbacks.
2. Fix private logging, match/session-bound interactions and role/phase/delivery authorization.
3. Correct victory, pause, finalization/restart and reward-history behavior.
4. Deliver the evidence ledger/report pipeline and genuinely playable role/content workflows.
5. Reconcile documents and outdated tests with rules v2, rerun the release checks, then consider merging the feature branch into main.

No meaningful overall completion percentage can be inferred from test counts: several critical requirements are absent while many passing cases are parameterized variants of the same authorization rule.
