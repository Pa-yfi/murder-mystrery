# v9 design: animations, transitions and the live card

## What current Telegram bots can do (research, Sep 2026)
| Feature | Bot API | Limits | Used here |
|---|---|---|---|
| Coloured buttons: `style` = `primary` (blue), `success` (green) or `danger` (red) | 9.4 (Feb 2026) | none | ✅ Every button gets a colour from its meaning (`ui.style_for`). |
| Animated custom emoji on buttons (`icon_custom_emoji_id`) | 9.4 | Only if the bot owner has Telegram Premium (or bought a Fragment username). | ✅ Optional: set `BUTTON_EMOJI` in `.env` as `{"act": "<custom emoji id>", …}`. If Telegram rejects it, the adapter resends without icons and stops trying. |
| Message effects (`message_effect_id`: 🔥 🎉 👍 …) | 7.4 | Private chats only. The IDs are undocumented and rotate, so a stale one fails with `EFFECT_ID_INVALID`. | ✅ The private role card gets 🔥 and a winner's private result gets 🎉. The IDs can be overridden with `MESSAGE_EFFECTS`, and a rejection resends without the effect. |
| Single-emoji messages are shown big and animated | client behaviour | Only messages that contain emoji and nothing else. | ✅ Phase transitions are single-emoji frames (🌇→🌆→🌃→🌙, 🌌→🌄→🌅→☀️, 🗳️→📊, 🔒→⛓️, 🏁→🎉), edited in place, then deleted. |
| Editing messages | always | Rate limits (~20 edits/min per chat). | ✅ One live card per phase, edited every 5 s. Idle lobbies stop animating after 10 min. |
| Streaming drafts (`sendMessageDraft`), rich messages, ephemeral group messages | 9.3 / 10.1 / 10.2 | Newer than python-telegram-bot 22.8. | ⏭️ Not used. Ephemeral messages (group messages only one user sees) would be a good fit for private game info later. |

Sources: [Bot API changelog](https://core.telegram.org/bots/api-changelog), [Bot API](https://core.telegram.org/bots/api), [python-telegram-bot InlineKeyboardButton](https://docs.python-telegram-bot.org/en/stable/telegram.inlinekeyboardbutton.html), [message_effect_id values](https://gist.github.com/wiz0u/2a6d40c8f635687be363d72251a264da), [stale effect id breaking /start](https://github.com/harshi79/Advaced-Posting-Bot-In-Tg/pull/5), [coloured buttons and premium emoji guide](https://github.com/whitedestrierfaith/telegram-colored-inlinebuttons-premium-emoji).

## The visual system (`karagah/theme.py`)
- **Ribbon headers:** `🌙 ┈┈ *شبِ ۲* ┈┈ 🌙` on the live card, morning, discussion, vote, interrogation, jury, verdict, ending, case, role card, action panel and dashboard.
- **Hourglass:** `⏳` and `⌛` alternate on every 5-second edit of the live card.
- **Shiny bar:** 10 cells in the phase colour, with a ✨ that moves one cell each edit. The phase colours are night 🟪, morning 🟨, discussion 🟩, vote 🟧, jury 🟫 and lobby 🟦. In the last 20% of the time the bar turns 🟥.
- **Readiness meter:** 🟢🟢⚪⚪ in the lobby card and in the private "you're ready" reply.
- **Path:** `📅 🌙۱ ☀️۱ 🌙۲▶️` under the live card.

## Live card
- **Lobby:** the "new game" message *is* the live lobby card. It lists every player with ✅ or the turning hourglass, a ready meter and the next step, and it updates by itself:
  - after every tap in the group;
  - after a "✅ آماده‌ام" tapped in private chat (`res["refresh"]`);
  - every 5 s while the lobby is active.
- **During play:** one card per phase: the ribbon, the time left with its bar, the vote count, and the path so far. When the phase changes, the old card is marked "✔️ تمام شد" and a new one is posted.

## Duplicates removed
- **Back and menu:** "🔙 بازگشت" and "🏠 منوی اصلی" both went to `menu` and sat side by side under more than 1,100 messages. They are now one "🏠 منو", and `ui.kb()` drops any repeated callback in a keyboard.
- **Live card:** it no longer shows "🔄 بروزرسانی" (it refreshes itself) or "🏠 منو" next to "🏠 منوی کامل".
- **Lobby:** the host panel and the lobby were two different cards with the same buttons. There is now one lobby card, and the false "only you see this" text is gone.
- **Game start:** the start message no longer carries a second "🌙 پایان شب". The live card has it.
- **Main menu:** it only appears outside a game, so its in-game buttons (night action, abilities, dashboard, and board/role in private chat) were dead ends and were removed.

## The bot only talks about the game
- **Help page:** no longer cites "RULES.md", and describes the current night rule (pass, grace period).
- **Tutorial:** no longer teaches the old "E1 evidence with three interpretations"; it uses the real clue, frame and lab system.
- **Ability texts:** updated for frame, scene examination and the reporter's interview.
- **Channel:** the "add to channel" button is removed; the game can't be played in a channel.
- **Bad input:** "enter a number/ID" is replaced with "this button is no longer valid".
- **Admin pages:** they list user IDs, and now reply only in private.
- **Private-chat doors:** "join" and "share" pressed in private chat no longer create an invisible private table.

## Gameplay bugs found this round
| Bug | Found by | Fix |
|---|---|---|
| The detective could check a clue, press "not tonight", then investigate: two actions in one night. | Targeted probe of the new pass button | Pass is refused once the clue result has been seen. |
| A night that starts with every night role dead or in custody (and no officer on duty) waited 60 s for nothing. | Night fuzzer: 350 random nights of act/pass/change/clue-check sequences | Morning comes at once ("🌅 امشب هیچ نقشی کاری برای انجام دادن نداشت"). |
| "Ready" before "join" answered "join first". | Ready-phase review | One tap does both. |
| Ready in private chat didn't update the lobby card in the group. | Ready-phase review | Refreshed at once. |
