# Karagah quality audit — results and remaining work

Date: 2026-09-20

## Outcome

**The bot does not yet satisfy all target rules/scenarios.** The existing tests pass, but the expanded suite exposes gameplay, access-control, private-communication, persistence, evidence-usefulness, and resource-boundary gaps.

| Suite | Passed | Failed cases | Skipped | Collection/runtime setup errors |
|---|---:|---:|---:|---:|
| Existing tests | 184 | 0 | 1 | 0 |
| New quality contracts | 1,262 | 63 | 0 | 0 |
| Total | 1,446 | 63 | 1 | 0 |

These are parameterized **test-case counts**, not counts of distinct bugs. Some failures are new release-target design requirements, such as quotas, role availability, jury quorum, and human relay. They must not all be described as regressions of features that previously passed.

No application behavior was changed by this audit. Added files contain documentation, offline test contracts, and audit tools. Independent application edits observed during the session were preserved. No production deployment, bot startup, push, or message to real players was performed.

## Revision and reproducibility

- Final audited Git HEAD: `0e0dace680b484f3275a46352aa4859207df3094`.
- Final evidence directory: [qa_results/20260920-081824](qa_results/20260920-081824/).
- [summary.json](qa_results/20260920-081824/summary.json): exact SHA-256 of every copied source/test file, interpreter/dependency versions, failure names/messages, and unchanged-source check.
- [existing.xml](qa_results/20260920-081824/existing.xml), [quality.xml](qa_results/20260920-081824/quality.xml): machine-readable JUnit results.
- [existing.txt](qa_results/20260920-081824/existing.txt), [quality.txt](qa_results/20260920-081824/quality.txt): complete captured test output.
- [test-families.md](qa_results/20260920-081824/test-families.md): outcome counts for every test family.
- `source_snapshot/` in that directory contains the exact audited application/tests, without the live `.env` or database.
- Source hashes did not change during the final run. Earlier run directories are retained for traceability and are superseded by this one.

**Post-run worktree change:** during final documentation validation, independent edits changed `karagah/bot.py` and added an untracked `karagah/menus.py`. Those later edits were not part of the recorded snapshot and were not overwritten. Therefore the numbers above certify only the saved snapshot, not the subsequently changing working directory. Re-run the audit after those edits finish before accepting or releasing that newer version. [post-audit-worktree.json](qa_results/post-audit-worktree.json) records the observed divergence.

Command: `.venv/Scripts/python.exe -B tools/run_quality_audit.py`.

The runner copies source/tests into an isolated temporary directory, writes dummy credentials, points database writes at a temporary database, and separates the old suite from `tests/quality`. New tests reset their data in memory; one integration test deliberately closes/reopens a file-backed temporary database. Telegram delivery is mocked. External socket connections are blocked; Windows asyncio's internal loopback wake-up connection is permitted.

Windows sandbox permissions initially blocked creation of the temporary copy; the offline runner was rerun with approved access. The first network guard also blocked Windows asyncio's local wake-up socket; that harness defect was corrected before the final results. Those infrastructure failures are not counted as product defects.

Installed versions observed: pytest 9.1.1, python-telegram-bot 22.8, Pillow 12.3.0. APScheduler was **not installed**. The application declares basic Telegram/dotenv/pytest requirements but not Pillow or the scheduler extra: a clean-install/timer readiness gap, even though Pillow happens to be installed in this working environment.

## What was actually covered

| Layer | Executed coverage | Important limit |
|---|---|---|
| Unit | 810 ordinary night-action cases: 18 roles × 9 phases × 5 life/custody states; 90 exclusive-role checks; 12 special-ability state cases | This is not every possible role × target × callback × deadline combination |
| Functional | Actual command handlers and Telegram dispatch/reply adapter with fake transport; readiness, invitations, table routing, public/private destinations | Real Telegram delivery and client UI not exercised |
| Integration | SQLite persistence, file DB reconnect/restore, timer → handler → snapshot → broadcast, result-write failure/retry | A process-kill-at-every-SQL-commit campaign remains future work |
| Acceptance | 42 completed city-win journeys through public handlers, a real custody/jury path without manually setting custody counters, private role delivery; a failing human-room requirement | Other faction-win full-match journeys and complete room lifecycle not implemented in this new acceptance subset |
| Regression | Prior privacy, routing, timer and ending fixes plus newly discovered permission/custody/reward boundaries | Existing one skipped scenario is still skipped and must be made deterministic |
| Gameplay | All 40 cases × 7 sizes = 280 opening cycles; 7 sizes × 6 seeds = 42 completed city journeys | Harness uses known roles to select a legal winning strategy; does not measure human strategy or balance |
| Evidence/content | Generator/template review, all catalog roles/types, authenticity masks, clue uniqueness, lab/spy/grocer/trace contracts | No human assessment of all 40 mysteries' fairness/comprehension |
| Edge cases | Invalid targets/cases, IDs outside signed 64-bit range, repeated ballots/questions/notes, oversized rendered notes, SQL-like player names, threshold boundaries | No large-scale load/soak test, disk exhaustion, or memory profiler run |
| Leaks | Failed-DM recipients, private audit-content leak, interrogation audience, stale routing, aggregate activity side channel; redacted tracked-source/history scan | Signature scanning and selected privacy paths do not prove absence of all leaks |

The ordinary role-action matrix and all 90 exclusive-role checks pass: choosing a target cannot turn a citizen into a killer or a killer into a doctor. **Ten of twelve special-state checks fail**, showing that special commands do not consistently enforce custody/death restrictions.

The single inherited skip is the interrogation-night attack scenario whose chosen seed makes the killer the suspect. Replace its setup with a deterministic legal non-killer suspect; do not treat the skip as coverage.

## Confirmed failing contracts and recommended fixes

### Privacy, communication, and identity

| Finding | Reproduction / evidence | Required change |
|---|---|---|
| Human officer–suspect relay missing | `test_human_officer_question_reaches_suspect_via_bot`: officer's question never reaches the real suspect | Implement the match-bound two-person session from MSG-01–18; do not fabricate a suspect's answer |
| Interrogation response is public | `test_interrogation_content_not_public`: `h_ask` response is not private | Explicit authorized recipient(s) and visibility on message envelopes |
| Private note content in general audit history | `test_private_note_not_copied_to_general_audit_history` | Log event type, actor and IDs; keep raw private content in a separate scoped store or omit it |
| Old button acts on newly selected table | `test_old_callback_is_not_redirected_by_table_selection` | Put match/round/session version in callbacks; verify it before acting |
| Readiness can be asserted from group | `test_group_ready_does_not_claim_private_delivery` | Verify required private onboarding/delivery before changing readiness |
| Invite join not persisted in target lobby | `test_deep_link_join_is_persisted_in_target_game` | Save/lock the mutated target match, not just the incoming private chat |
| Remaining secret-activity side channel | `test_public_progress_does_not_disclose_secret_action_count` | Use generic public reminders; individual reminders only in private |

Named night-actor disclosure **is fixed in this later revision**: dashboard/reminder name checks pass. The remaining aggregate count changes when a hidden actor submits. That is a narrower inference channel, not the same claim as publishing role names. Failed-DM content/keyboard fallback tests also pass for role, hint, note, and conversation payloads.

### Role, phase, and custody enforcement

| Finding | Failed contract | Required change |
|---|---|---|
| Detective can authenticate evidence while detained | `test_ineligible_roles_lose_special_powers` (2 detective cases) | Share actor-state guards with ordinary night actions |
| Hunter can retarget while detained/dead/life-jailed | Same family (4 hunter cases) | Freeze target when actor loses eligibility; shot event itself is separate |
| Officer hints remain available while detained/dead/life-jailed | Same family (4 officer cases) | Verify active, free officer and current session |
| Outsider can start/advance/close phases | Five `test_outsider_cannot_control_phases` variants | Central host/system-actor authorization policy |
| Active game can be started again | `test_start_twice_rejected` | Lobby-only transition guard |
| Dead players petition; outsider petition mutates state before failing | Jury petitioner regression tests | Validate first, mutate second; forbid ineligible petitioners |
| Verdict allowed during active jury | `test_verdict_cannot_corrupt_active_jury` | Exclusive jury/decision transition and current-suspect guard |
| Officer can acquit self | `test_officer_cannot_acquit_self` | Jury-led fallback for officer suspect |
| A killed suspect remains the active suspect | `test_suspect_death_closes_interrogation_state` | Close custody/session links after elimination |
| Single ballot can acquit without quorum | `test_one_vote_cannot_acquit_without_quorum` | R05 quorum before applying yes-percent threshold |
| Outsiders can submit lab work and interpretations | `test_lab_requires_membership`, `test_evidence_interpretation_requires_membership` | Eligible membership and evidence visibility checks |
| Banned player can join | `test_banned_user_cannot_join` | Enforce bans centrally for commands/callbacks |
| Emergency detention accepted after completion | `test_completed_game_rejects_emergency_detention` | Terminal-state guard across every mutation |

### Role effects, outcomes, and persistence

| Finding | Observed behavior | Required change |
|---|---|---|
| Doctor restriction bypass | Select a different target, then edit back to last night's target | Validate target against previous night on every edit |
| Detective restriction resets | Dawn clears previous-target bookkeeping | Persist prior-night target separately from current commitments |
| Hunter life-jail shot absent | Life imprisonment leaves selected target alive | Route life-jail elimination through the shared final-shot event path |
| Serial killer causes incorrect ending | City wins while serial killer and city players remain | Explicit independent-hostile victory logic |
| Solo serial killer gets loser base rewards | 40 XP/20 coins rather than winner base | Explicit winner IDs; stop deriving victory from translated alignment prefixes |
| No-survivor result is city win | Empty survivor set follows “no killers” branch | Apply draw precedence before faction victory |
| Repeat vote rewards inflate | Ten same-target ballots yield 270 XP instead of 135 in the fixture | Effective final ballots, not every history entry, feed rewards |
| Result retry fails | Simulated failed result write leaves finalized flag set; later retry records zero games | Transactional finalization, mark complete only after durable success |
| Ending lost after restart | Completed match dropped from snapshots and not reconstructed | Persist a compact final summary and match result |
| Pause at zero loses deadline | Resume restores `None`, disabling the timer | Distinguish zero from absent duration |
| Actions still work while paused | Killer can commit an action during pause | Guard all gameplay mutations while paused |

Ordinary 30-second pause/resume, timer transition persistence, file-backed snapshot reload, repeated ending reads without additional rewards, and the direct 60% jury threshold with full turnout pass their new checks. A quorum rule is a separate target requirement, not contradicted by the passing arithmetic tests.

### Evidence and role availability

- Reporter, lawyer, grocer, and smuggler fail the standard-composition reachability contract. They exist in the catalog but no supported player count assigns them.
- Every case uses the same real/fake card-position mask. This makes authenticity predictable without investigation.
- Revealed evidence repeats after the deck is exhausted.
- The lab message adds no concrete result that narrows hypotheses.
- The spy returns the same finding whether an actual question occurred or the suspect was merely nominated.
- The grocer does not produce a new daily rumor in the tested role fixture.
- An indirect-death trace incorrectly guarantees that a visitor is the killer.

See [evidence-and-roles.md](evidence-and-roles.md) for a usefulness assessment of every role and all 16 clue types, examples of fair red herrings, and the next design steps.

## Overflow, data growth, and leak review

| Boundary | Result | Interpretation |
|---|---|---|
| User ID `2**63` or `-2**63-1` | Uncaught SQLite integer conversion error | `touch_user` occurs outside the central exception guard. Real Telegram users cannot select their authenticated ID; this is an input-boundary/robustness gap, not a demonstrated remote identity-spoofing exploit |
| Invalid case `-1` | Accepted through Python negative indexing | Selects an unintended case; explicit 1–40 validation required |
| Case `41` or huge integer | Generic internal-error response | Should be a controlled user-input rejection |
| Action target with 5,000 digits | Controlled rejection | This input check passes; do not generalize to every numeric entry point |
| 101 private notes | All retained | No total quota; each note's truncation alone does not bound storage |
| 30 × 200-character notes | Single response is 6,217 characters | Needs pagination/bounded rendering; repeated send retries cannot fix oversized content |
| 101 unique questions | 101 retained answer entries | No session quota in current QA history |
| 100 identical votes | 100 history entries for one effective ballot | Memory/database growth and reward inflation |
| SQL-shaped name | Stored as plain data; schema intact | Parameterized write passed this test |
| Caches, transcripts, snapshots, image files | No soak/profiler proof | Add bounded retention, TTL cleanup, and measurements; do not claim absence of memory/resource leaks |

The numerical note/message quotas in R12 are new product targets. Failing those quota contracts is explicitly a design gap; the observed unbounded accumulation and oversized single response are concrete behaviors. Python integers themselves do not wrap like fixed-width C integers; the observed failure is conversion into SQLite's integer range.

### Repository credential scan

Command: `.venv/Scripts/python.exe -B tools/audit_repository_leaks.py`.

[repository_leak_scan.json](qa_results/repository_leak_scan.json) records a redacted scan at `0e0dace680b484f3275a46352aa4859207df3094`:

- 35 tracked paths inspected for sensitive file tracking.
- 82 reachable historical text blobs scanned with signatures for Telegram tokens, private-key headers, GitHub tokens, and OpenAI-style keys.
- Zero matching signatures; no tracked `.env`, database, or private-key file path found at HEAD.
- No matched secret values are printed or stored in reports; a future match would report location/type/fingerprint only.

Limits: the untracked live `.env` and production database were intentionally not read; remote-only history, binaries, blobs over 2 MB, credentials outside the selected signatures, and off-repository stores were not scanned. **Zero signature matches is not proof that no secret exists anywhere.** Application privacy leaks above are distinct and were found despite this clean signature scan.

## Rules applicability: answer to “do the rules apply to all scenarios?”

**The written rules specify defaults and exceptions for the catalogued scenarios; the implementation does not enforce all of them yet.** Passing 1,446 cases does not prove every interaction or possible message sequence correct.

Covered boundaries include phase/life/custody eligibility, private versus public delivery, quorum/threshold distinction, replayed inputs, selected-table changes, terminal states, poison/custody time concepts, and restart persistence. Remaining high-value work:

1. Full bidirectional human-room lifecycle, retries, participant replacement, closing, and transcript retention.
2. All simultaneous-effect combinations, particularly poison + storm + cure and hunter + linked death + protection.
3. All faction/neutral win endings through complete legal commands, including draws and smuggler survival.
4. Real Telegram DM readiness, callbacks, message limits, images, and RTL display.
5. Concurrent timer/action races under a real workload and fault injection at each durable transaction boundary.
6. Versioned snapshot migration and old-message behavior across application upgrades.
7. Human playtests for useful evidence, fair red herrings, role balance, and downtime.

No hidden `xfail`, blanket skips, or rewrites to make defective behavior pass were added. The new suite deliberately remains red for unmet contracts. Standard `pytest` collection includes these tests, so it should now fail until the gaps are implemented or a documented rule is deliberately revised.

## Prioritized implementation handoff

1. **Before public play:** implement human private rooms; prevent public interrogation/audit-content disclosure and stale cross-table actions; unify role/status/member checks.
2. **Before release:** fix custody/jury/terminal transitions, independent winner logic, transactional finalization, readiness persistence, pause guards, and boundary validation.
3. **Before advertising the full catalog:** make unavailable roles explicitly selectable in balanced modes or label them unavailable; implement meaningful spy/grocer/forensic/coroner behavior.
4. **Quality milestone:** meaningful case-linked evidence, fair counter-evidence/red herrings, bounded storage/rendering, complete dependency declarations, and private-safe progress UI.
5. Re-run `.venv/Scripts/python.exe -B tools/run_quality_audit.py`; compare failure families, not just total count. Preserve the recorded seed/input and add a regression for each corrected defect.

The selected Persian role display titles are in [role-names.md](role-names.md). Only documentation naming changed; canonical code identifiers and gameplay powers were left intact.
