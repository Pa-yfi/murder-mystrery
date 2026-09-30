# Karagah — what the game is, and where it dead-ends

Audit of branch `claude/playtest-agents` (engine v4). Part 1 is my understanding of the whole
game, written from the code. Part 2 says how every part was simulated. Part 3 lists every
dead end found, with evidence. Part 4 proposes fixes.

---

## Part 1 — What I understand of the game

### 1.1 What it is
**کارآگاه (Karagah)** is a Persian-language Telegram bot that runs a social-deduction game:
**Mafia/Werewolf + a murder-mystery wrapper**, for **4–10 players**, with no LLM. Everything
is rules-based and deterministic (seeded).

- A group of friends plays in a Telegram **group chat**. Secret things (your role, night
  actions, detective results, interrogation Q&A) happen in each player's **private chat
  (DM)** with the bot.
- Players are meant to **never type commands**. Everything is an inline button. The only
  typing is free text: note, will, officer's question, suspect's answer, defense.
- Stats live in **SQLite** (users, games, players, events, outcomes, snapshots, season XP,
  achievements, missions, vote accuracy). Unfinished games survive a bot restart via pickled
  snapshots.

### 1.2 How the code is built
```
run.py → karagah/telegram_app.py   (python-telegram-bot adapter: buttons → handle(), timer job every 15 s)
       → karagah/bot.py            (71 endpoints; one entry point handle(cmd, chat, uid, name, arg))
            ├── engine.py          (the rules / state machine)
            ├── roles.py           (18 roles, 3 scenarios × 4..10 players, balance validation)
            ├── cases.py           (40 murder cases, 6 evidence cards each)
            ├── dialogue.py        (rule-based "body language" hints for the officer)
            ├── ui.py / menus.py   (Persian screens + every keyboard)
            ├── cards.py           (PNG role card via Pillow)
            └── db.py              (SQLite)
```
`handle()` never throws. It returns `{ok, text, keyboard, private, announce, outbox}`, and the
adapter decides where each message goes:
- DM if `private`;
- the game's group if `announce`, even when the button was pressed in a DM;
- `outbox` entries go to other people (e.g. the question to the suspect).

### 1.3 Setting up a table
1. Someone taps **🎮 شروع بازی همین‌جا** (or **⚡ بلیتز**, which halves every timer). That
   person becomes the **host** and a lobby appears.
2. Others tap **🙋 منم بازی می‌کنم**. Each player taps **✅ آماده‌ام**, a deep link that opens
   the bot's DM, which proves the bot can message them privately.
3. The host picks a **🎭 سناریو** (scenario = the fixed role set, as in Iranian mafia) and
   taps **🎬 شروع بازی**. Only the host can do either.
4. A random case is dealt (#1–40). Roles are shuffled, with a cooldown so nobody repeats last
   game's role. Each player's **role card is pushed to their DM**.

### 1.4 Scenarios and roles
| Scenario | Flavour | Neutral roles used |
|---|---|---|
| **کلاسیک classic** | core mafia | scapegoat |
| **دادگاه court** | lawyer, reporter, forensic doctor; more evidence | scapegoat |
| **آشوب chaos** | every man for himself | serial killer, smuggler, grocer |

Exactly one officer and one detective in every table; killers are always a minority.

| Role | Team | Night action | What it learns / special |
|---|---|---|---|
| 🕵️ Detective | Town | investigate 1 player (result at dawn). Or instead: check if an evidence card is fake | not the same target 2 nights in a row |
| 🔦 Officer (بازجو) | Town | — | interrogates the suspect; gives the verdict |
| 💉 Doctor | Town | protect 1 player from kill and from poison that is due that night | not the same target twice in a row; self only once per game |
| 🛡️ Guard | Town | watch 1 player | count of visits to them |
| 🧪 Forensic doctor | Town | "autopsy" | whether today's evidence card is real or fake |
| 📰 Reporter | Town | interview 1 player | reveals one extra evidence card to everyone |
| ⚖️ Lawyer | Town | — | can call a jury alone |
| 🔬 Coroner | Town | — | time and weapon of each death |
| 🏹 Hunter | Town | pre-select a last-shot target | takes them along if killed or life-jailed |
| 👤 Citizen | Town | — | — |
| 🔪 Killer | Killers | kill 1 | knows the team; if removed, the knife passes to accomplice → poisoner → spy |
| 🧤 Accomplice | Killers | frame 1 | framed player reads "suspicious" to the detective; a fingerprint trace appears |
| ☠️ Poisoner | Killers | poison 1 | victim dies at dawn 2 nights later unless the doctor saves them that night |
| 📞 Spy | Killers | spy | learns whom the officer interrogated |
| 🎭 Scapegoat | Neutral | — | wins alone if life-jailed while alive |
| 🩸 Serial killer | Neutral | kill 1 | wins if last alive or 1-on-1 |
| 🏪 Grocer | Neutral | — | a daily rumour, 70% true; wins by surviving |
| 🚬 Smuggler | Neutral | hide 1 from detective/guard | wins by surviving |

Fate pair (7+ players): two town players whose deaths are linked.

### 1.5 One day, step by step
1. **🌙 Night** (60 s). Every role with an action opens **🌙 اکشن شبانه** in their DM and taps
   a name. Detained players are safe and cannot act.
   - **Night order:** hide → protect → frame/poison → kills → a storm cancels kills →
     poison that falls due → death chains (fate pair, hunter) → jail advances (temporary →
     life, hunter's shot) → private info → knife succession → win check.
   - **Ending the night:** only once everyone has acted or time is up.
2. **☀️ Morning** (90 s). The group sees:
   - deaths, the night event (storm / blackout / anonymous witness), today's evidence card;
   - traces: how many visited the victim, a fingerprint trace if someone was framed;
   - wills, and the status board.
   Private results arrive in each DM.
3. **💬 Discussion** (180 s). Talk; optional evidence votes and lab requests.
   **🚨 SOS**: once per game, 80% of voters send someone straight to temporary jail.
4. **🗳️ Vote** (90 s). The most-voted player goes to interrogation; abstaining is allowed.
   On a tie: one sudden-death revote between the tied players only; a second tie means
   nobody is arrested.
5. **🔦 Interrogation night.** The suspect spends the night detained (safe from kills).
   - The officer asks questions, which really reach the suspect's DM; the suspect answers.
   - The officer sees vague "body language" hints; a contradiction is flagged if an answer
     to the same question changes.
   - The suspect can post a **🛡️ last defense** to the group.
6. **Next morning — verdict.**
   - The officer rules **🔒 temporary jail** or **🔓 clear**.
   - Alternatively 2 players (or the lawyer alone) call a **⚖️ jury**: 60% acquit = freed.
   - If the officer is dead, jailed or is the suspect, a jury is formed automatically, and
     not acquitting means jail.
   - Temporary jail lasts 2 nights, then becomes **⛓️ life jail**: removal without revealing
     the role.
   - The officer can free an earlier prisoner only while a new suspect is in interrogation.

### 1.6 Winning and scoring
Checked in this order:
1. Scapegoat life-jailed while alive.
2. Nobody left → draw.
3. No killers and no serial killer left → **town**.
4. Serial killer with at most one other player left → **serial killer**.
5. Killers ≥ everyone else, with no serial killer → **killers**.
6. Past day 20 → draw.

Grocer and smuggler co-win if they survive.

Scoring:
- XP: 120 for a win, 40 for a loss; +10 per night result; +15 per final vote on a real killer.
- Coins: 60 / 20.
- MVP is the highest XP. Rank titles come from XP.

At 🏁 the end, everyone's role is revealed, along with who was wrongly life-jailed, correct
votes, MVP, and a log replay.

### 1.7 The murder-mystery layer
Each case has:
- a victim, a place, a weapon, a motive;
- a 4-line timeline and a "twist";
- **6 evidence cards**. Each has 3 possible interpretations, and 2 of the 6 are fake.

One card is revealed per morning; more come from the reporter and the anonymous-witness
event. Players can:
- vote on which interpretation they believe (**🧠 تفسیر**);
- send a card to the **🧪 lab** (result in 2 nights);
- have the detective **🔍 check** whether a card is fake.

### 1.8 Around the game
- **Progress:** 📊 profile/rank, 🏆 top players, 📅 monthly season, 🌍 group league,
  🎯 daily missions, 🏅 achievements.
- **Table tools:** 🎲 choose table / ➕ parallel table (up to 3 per group), 📺 spectate,
  🕶️ anonymous/open votes, 🔁 rematch, ⏰ reminder, ⏸️ pause / ▶️ resume,
  👑 hand over host, ⏳ timer check.
- **🛠️ Admin** (ADMIN_IDS only): active games, users, stats, role balance, ban.
- **Menus:** the main menu has 15 buttons. "🎛️ همه‌ی دکمه‌ها" shows every command in 7
  groups: play, interrogation & court, clues & notebook, progress, table & hosting, guide,
  admin.

---

## Part 2 — How every part was simulated
1. **Full games** (`python -m playtest`): agents read every Markdown file, fill every seat
   and play with buttons only.
   - 3 scenarios × 4–10 players × 30 seeds × 3 ways to advance (buttons in the group, the
     timer alone, buttons pressed from DMs) = **1,890 games, all finished**.
   - An independent referee checked about 89,000 ability timings. 31 edge-case probes also
     ran.
2. **Button crawl** (`python -m playtest.crawl`, new):
   - **43 game states**: empty group, lobby stages, night before/after actions, morning,
     discussion, vote, tie runoff, interrogation night, question pending, paused, verdict
     morning, jury, prisoner held, game over; across classic 9, court 10 and chaos 10.
   - **20 kinds of person** in each state: the host, every role, the suspect, the officer,
     dead and jailed players, an outsider, an admin who isn't playing.
   - Each opens their DM menu, the group messages and the dashboard, then presses
     **every button up to 3 screens deep** (text prompts get a sample text), each time from
     the same saved state.
   - **114,264 presses**. 67 of 71 endpoints succeed through some button. The other 4:
     - `back` and `night` are aliases that no button uses;
     - close-vote and close-jury only succeed once everyone has voted or time is up, which
       the full games cover.
   - Plus targeted checks: parallel tables, private-chat tables, the mid-game menu,
     rendering the PNG role card.

No crashes or internal errors, and no leaks of private information to the group.

---

## Part 3 — Dead ends

### A. Paths that lead nowhere or break the game (high)
| # | Dead end | Evidence |
|---|---|---|
| A1 | **A table created in a private chat can't be played by anyone but the host.** The DM main menu offers "🎮 شروع بازی همین‌جا" + "📨 دعوت دوست". Friends join through the link and the game starts, but every public message goes to the host's DM: the morning news, vote buttons, verdict, jury, ending. Friends only see "📣 در گروه اعلام شد" and never get a vote button. | crawl `private-table`; the game lives at chat = host id |
| A2 | **Parallel tables (➕ میز تازه) can't be joined or played with buttons.** The new table's "🙋 منم بازی می‌کنم" sends `join` from the group, which always routes to the group's main table. 4/4 joins landed in the main table. Start, dawn and vote of table #2 can't be pressed from the group either. | crawl `newtable` |
| A3 | **One tap destroys a live game.** "🏠 منوی اصلی" sits under every message, and in the group it shows "🎮 شروع بازی همین‌جا" and "⚡ بلیتز". A host tap wipes a running game, even a paused one, with no confirmation. The crawl saw this as the *only* single-tap phase change in several states. | crawl `one-tap-wipe` |
| A4 | **"📨 دعوت دوست" from DM invites to a lobby that doesn't exist.** The link is `join_<your user id>`; unless you built a DM table (see A1), friends get "این لابی دیگر فعال نیست". | crawl `dm-invite` |

### B. Mechanics that lead nowhere (the mystery is mostly decoration)
| # | Dead end | Why |
|---|---|---|
| B1 | **Evidence never points to a real player.** `Evidence.points_to` is never set; the 3 interpretations per card come from a generic list of 4 ("maybe the killer's", "maybe planted"…). Nothing in the case identifies who the killer players are. The "murder mystery" can't be *solved* from evidence; only the mafia-style signals are real (detective results, visit counts, frame fingerprint, co-location notes, hints). | `cases.py` `_evidence_deck` |
| B2 | **The fake cards are always E2 and E5** (`misleading: i in (1, 4)`) in all 40 cases. After one game a player knows which evidence is fake, so the detective's 🔍 check and the forensic doctor's action become worthless. | `cases.py` |
| B3 | **The lab returns nothing.** Two nights later it only posts "منشأ مدرک مشخص شد، تفسیرها را محدود کنید", with no actual result. | `engine.resolve_night` |
| B4 | **Evidence interpretation votes have no effect.** The majority interpretation is shown, then never used by anything. | `vote_interp` |
| B5 | **The "blackout 🕯️" night event does nothing**; only storm and witness have effects. | `resolve_night` |
| B6 | **Some roles' private info is already public.** The coroner always hears "23:15, with <case weapon>", and the weapon is printed in the case intro. The grocer's starting rumour is also the weapon. The forensic doctor's starting note is card E1's title, which is revealed on morning 1 anyway. | `engine.start`, `resolve_night` |
| B7 | **The case "secret" is never shown.** Every player gets the same `راز: <twist>` (not secret), and it was only ever used by the old auto-answer dialogue, which v4 replaced with real answers. `Player.trust` and `Player.suspicion` are never read. | grep |
| B8 | **Coins have nowhere to go.** They're earned every game; the shop was removed in v1.1. | `db`, PLAN |
| B9 | **The PNG role card is unreadable.** Pillow's default font has no Persian letters or emoji, so every character is an empty box. Sample: `playtest/rolecard_sample.png`. | crawl `rolecard-tofu` |
| B10 | **The officer's "story doesn't match the timeline" hint is random.** It fires on 20% of a hash, not on guilt. The stress level (which *is* higher for killers) is the only honest signal. | `dialogue.interrogation_hints` |

### C. Screens and buttons that don't lead anywhere (medium)
| # | Dead end | Evidence |
|---|---|---|
| C1 | **Screens with no buttons at all:** 🔐 my role, 🖼️ role card, 🕶️ anonymous/open, ⏳ timer check, 🔦 hints. The user must scroll up or type to continue. Roughly 2,400 presses landed on them. | crawl `nokb:*` |
| C2 | **Stale "🗣️ جواب بده" after a verdict.** An unanswered question stays attached to the former suspect. The button still opens the prompt, but the answer is refused ("فقط متهمِ داخل بازجویی جواب می‌دهد"). | crawl `textfail:answer` |
| C3 | **Buttons shown to everyone that only one person can ever use:** 🛠️ admin (main menu), the whole admin group, officer tools, the defense and hunter buttons in "همه‌ی دکمه‌ها". They fail with a clear message, but they are dead for 18 of 20 kinds of person. | crawl matrix |
| C4 | `back` and `night` endpoints exist but no button uses them (typed aliases). | coverage |
| C5 | **🌍 group league lists raw chat ids** (`گروه -100…`), not group names. | `h_league` |

### D. Waiting states (not stuck, but the timer is the only exit)
| # | State | Note |
|---|---|---|
| D1 | Night, vote and jury while someone hasn't acted or voted | By design since v4: nobody can close early, so a single AFK player makes everyone wait the full 60/90 s. There is no host override. |
| D2 | Morning with a suspect | Waits for the verdict or a jury; after 90 s the timer forms a jury automatically. |

---

## Part 4 — Suggested fixes (not applied yet)
- **A1/A4:** Remove "🎮 شروع بازی همین‌جا" from private chats (DM → only "add to group"), or refuse `new` in a DM with a message explaining that games live in groups.
- **A2:** Put the table id in its buttons (`join:<table>`, `startgame:<table>`…), or drop parallel tables.
- **A3:** Add a confirmation step for new/blitz while a game is running ("⚠️ بازیِ در جریان پاک شود؟ بله/خیر"), and hide them from the group menu during a game.
- **B1/B2:** Make evidence real. When the killer kills, generate a card whose true interpretation points at a real visitor (with the frame and smuggler able to corrupt it), and shuffle which cards are fake per game.
- **B3:** Lab = reveal which interpretation is correct. **B4:** the interpretation the town picks unlocks a hint.
- **B5:** Blackout = the guard sees nothing, or visit traces are hidden. **B6:** Give the coroner the *time* plus "which role type visited".
- **B7:** Remove dead fields, or feed the twist into the evidence.
- **B8:** Spend coins on cosmetic titles, or remove them.
- **B9:** Ship a Persian font (e.g. Vazirmatn) with arabic-reshaper + python-bidi, or drop the PNG.
- **C1:** Add "🔙 / 🌙 اکشن / 📋 داشبورد" buttons to those screens. **C2:** Clear pending questions when the verdict/jury closes.
- **C3:** Show role-specific and admin buttons only to the people who can use them.
- **D1:** Give the host a "⏭️ بستن با تایید" (force-close with confirmation) after a minimum wait.

Reproduce: `python -m playtest.crawl` (report: `playtest/dead_ends.json`) and `python -m playtest --seeds 30`.
