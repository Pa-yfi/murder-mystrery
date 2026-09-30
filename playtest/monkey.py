"""python -m playtest.monkey — بازیِ کامل با بازیکن‌های «شلوغ‌کار».

agentها وسط بازی هر دکمه‌ی قابل‌دیدنی را در هر لحظه‌ای می‌زنند (حتی دکمه‌ی کهنه‌ی دیروز)،
/start و /menu می‌زنند، متن می‌فرستند، ساعت را جلو می‌برند و در کنارش بازیِ درست هم جلو می‌رود.
بعد از هر قدم می‌سنجیم:
  • ترتیبِ فاز و روز: لابی → شب ۱ → صبح ۱ → گفتگو ۱ → رای ۱ → شب/بازجویی ۲ → صبح ۲ …
  • هیچ «خطای داخلی» (استثنای گرفته‌نشده) در هیچ پاسخی نیست
  • بازی گیر نمی‌کند (با گذشتِ زمان همیشه جلو می‌رود)
  • فراخوانیِ ربات وسط بازی (/start، /menu، 🏠، متن در پیوی) بازیِ جاری را نشان می‌دهد نه منوی ربات
  • شب تا وقتی همه‌ی نقش‌ها تصمیم نگرفته‌اند (یا مهلت + فرصتِ اضافه تمام نشده) بسته نمی‌شود
  • پیامِ ساعتِ هر فاز خودش را ویرایش می‌کند (یک پیام، متنِ تازه)
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

from karagah import bot
from karagah.models import Phase

from .docs import read_all
from .game import Session
from .report import Report

# انتقال‌های مجاز: (فاز قبل، فاز بعد) → اختلافِ روز
ALLOWED = {
    (Phase.NIGHT, Phase.MORNING): 0, (Phase.INTERROGATION, Phase.MORNING): 0,
    # بازجو نمی‌تواند حکم بدهد → هیئت منصفه همان سحر تشکیل می‌شود (صبح در همان پیام)
    (Phase.NIGHT, Phase.JURY): 0, (Phase.INTERROGATION, Phase.JURY): 0,
    (Phase.MORNING, Phase.DISCUSSION): 0, (Phase.MORNING, Phase.JURY): 0,
    (Phase.JURY, Phase.MORNING): 0,
    (Phase.DISCUSSION, Phase.VOTE): 0,
    (Phase.VOTE, Phase.NIGHT): 1, (Phase.VOTE, Phase.INTERROGATION): 1,
    # نسخه ۹: شبی که هیچ نقشی کاری ندارد همان لحظه به صبح (یا هیئت منصفه‌ی خودکار) می‌رسد
    (Phase.VOTE, Phase.MORNING): 1, (Phase.VOTE, Phase.JURY): 1,
}
LIVE = (Phase.NIGHT, Phase.INTERROGATION, Phase.MORNING, Phase.DISCUSSION, Phase.VOTE, Phase.JURY)
MENU_MARK = "🏠 *منوی اصلی*"
LIVE_MARK = "🎮 *بازیِ جاری*"


class Monkey:
    def __init__(self, n, seed, scen, report: Report, rb):
        self.sess = Session(n, seed, report, rb, "group", scen, talk=False)
        self.r = report
        self.rng = random.Random(seed * 7919 + n)
        self.trail = []                 # [(phase, day)]
        self.jailed_on = {}             # uid → روزی که حبس موقت شروع شد
        self.last_actor = None
        self.steady_jumps = 0           # گذشتِ زمان بدون عوض شدنِ فاز (ساعت باید ویرایش شود)
        self.steps = 0

    @property
    def g(self):
        return self.sess.g

    # ── ثبتِ ترتیب ──
    def watch(self, why: str) -> None:
        g = self.g
        cur = (g.s.phase, g.s.day)
        if not self.trail:
            self.trail.append(cur)
            if cur != (Phase.NIGHT, 1):
                self.r.find("بالا", "ترتیب", "بازی با «شب ۱» شروع نشد", str(cur))
            return
        prev = self.trail[-1]
        if cur == prev:
            return
        self.trail.append(cur)
        if cur[0] is Phase.END:
            return
        want = ALLOWED.get((prev[0], cur[0]))
        if want is None or cur[1] - prev[1] != want:
            self.r.find("بالا", "ترتیب", "ترتیبِ روز/شب به هم ریخت",
                        f"{prev[0].value} {prev[1]} → {cur[0].value} {cur[1]} (پس از {why})",
                        key=f"seq:{prev[0].value}>{cur[0].value}")

    def watch_custody(self) -> None:
        """حبس موقت دقیقاً بعد از ۲ شب (سحرِ دوم) حبس ابد می‌شود — نه زودتر، نه دیرتر."""
        from karagah.models import Custody
        g = self.g
        for p in g.s.players.values():
            if p.custody is Custody.TEMP_JAIL:
                self.jailed_on.setdefault(p.uid, g.s.day)
            elif p.uid in self.jailed_on:
                d0 = self.jailed_on.pop(p.uid)
                if p.custody is Custody.LIFE_JAIL and p.alive and g.s.day - d0 != g.temp_jail_nights:
                    self.r.find("بالا", "بازداشت", "حبس موقت زودتر/دیرتر از ۲ شب حبس ابد شد",
                                f"{p.name}: حبس موقت روز {d0} → حبس ابد روز {g.s.day}", key="temp-life-timing")

    # ── کارهای شلوغ‌کار ──
    def random_press(self) -> str:
        a = self.rng.choice(self.sess.agents)
        msgs = a._recent(("dm", "group"), 8)
        btns = [(m, b) for m in msgs for b in m.buttons()
                if "callback_data" in b or "start=" in b.get("url", "")]
        if not btns:
            return "no-buttons"
        m, b = self.rng.choice(btns)
        self.last_actor = a.uid
        a.press(m, b)
        return f"{a.name}:{b.get('callback_data') or b.get('url')}"

    def call_bot(self) -> str:
        a = self.rng.choice(self.sess.agents)
        g, tg = self.g, self.sess.tg
        where = self.rng.choice(("group", "dm"))
        cmd = self.rng.choice(("/start", "/menu"))
        chat = self.sess.group if where == "group" else a.uid
        m = tg.command(a.uid, cmd, chat)
        if g.s.phase in LIVE and a.uid in g.s.players and LIVE_MARK not in m.text:
            self.r.find("بالا", "منو", "فراخوانیِ ربات وسط بازی منوی ربات را نشان داد نه بازی را",
                        f"{cmd} در {where}، فاز {g.s.phase.value}", key=f"menu-in-game:{where}:{cmd}")
        return f"{a.name}:{cmd}@{where}"

    def type_dm(self) -> str:
        a = self.rng.choice(self.sess.agents)
        m = a.say(self.rng.choice(("سلام", "من بی‌گناهم", "کی شب تموم میشه؟")))
        g = self.g
        if g.s.phase in LIVE and m.cause == "text" and m.text.lstrip("\u200f").startswith(MENU_MARK):
            self.r.find("متوسط", "منو", "متن در پیوی وسط بازی منوی ربات را نشان داد", key="menu-in-game:text")
        return f"{a.name}:text"

    def time_jump(self) -> str:
        tg = self.sess.tg
        for _ in range(self.rng.choice((1, 2, 4))):      # هر ۵ ثانیه، مثل CLOCK_INTERVAL
            tg.clock.advance(5)
            before = (tg.clock_msg.mid if tg.clock_msg else None, tg.clock_msg.text if tg.clock_msg else "")
            key0 = tg.clock_key
            tg.timer_job()
            if key0 is not None and key0 == tg.clock_key and not self.g.s.paused:
                self.steady_jumps += 1
            cm = tg.clock_msg
            g = self.g
            if cm is None:
                if g.s.phase in LIVE:
                    self.r.find("بالا", "ساعت", "فاز در جریان است ولی پیامِ ساعت ندارد", key="clock-missing")
                continue
            if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
                leaked = [p.name for p in g.s.players.values() if p.name in cm.text]
                if leaked:
                    self.r.find("بالا", "امنیت", "ساعتِ شب نامِ بازیکن‌ها را نشان می‌دهد", str(leaked),
                                key="clock-night-names")
            if before[0] == cm.mid and not g.s.paused and g.remaining() and before[1] == cm.text:
                self.r.find("متوسط", "ساعت", "ساعت با گذشتِ زمان ویرایش نشد", cm.text[:60], key="clock-frozen")
        return "timer"

    def progress(self) -> str:
        s = self.sess
        if self.g.s.paused:                       # کسی «⏸️ توقف» زده؛ میزبان ادامه می‌دهد
            s.host.tap(lambda b: b.get("callback_data") == "resume", ("group", "dm"), depth=12, nav="resume")
            return "resume"
        h = {Phase.NIGHT: s.night, Phase.INTERROGATION: s.night, Phase.MORNING: s.morning,
             Phase.DISCUSSION: s.discussion, Phase.VOTE: s.vote, Phase.JURY: s.jury}
        h[self.g.s.phase]()
        return "progress"

    # ── اجرا ──
    def run(self, max_steps=900) -> dict:
        s = self.sess
        try:
            if not s.lobby():
                return {"ok": False, "why": "lobby"}
            self.watch("start")
            s.ref.track_custody = False
            s.ref.track_intents = False
            last_change, last_key = 0, None
            for i in range(max_steps):
                if self.g.s.phase is Phase.END:
                    break
                roll = self.rng.random()
                pick = (self.random_press if roll < 0.45 else self.call_bot if roll < 0.55
                        else self.type_dm if roll < 0.62 else self.time_jump if roll < 0.80
                        else self.progress)
                g = self.g
                night = g.s.phase in (Phase.NIGHT, Phase.INTERROGATION)
                pending = list(g.pending_actors()) if night else []
                self.last_actor = None
                deadline = g.s.deadline
                try:
                    why = pick()
                except AssertionError:
                    continue
                others = set(pending) - {self.last_actor}      # آخرین تصمیم خودش شب را می‌بندد (درست)
                if night and self.g.s.phase not in (Phase.NIGHT, Phase.INTERROGATION) and others \
                        and deadline and s.tg.clock.now < deadline and why != "progress":
                    self.r.find("بالا", "شب", "شب پیش از تصمیمِ همه‌ی نقش‌ها و پیش از پایان مهلت بسته شد",
                                f"{len(pending)} نقش هنوز تصمیم نگرفته بود؛ با «{why}»", key="night-early")
                self.steps += 1
                self.watch(why)
                self.watch_custody()
                key = (self.g.s.phase, self.g.s.day, len(self.g.s.votes), self.g.s.suspect_uid)
                if key != last_key:
                    last_key, last_change = key, i
                elif i - last_change > 150:
                    self.r.find("بحرانی", "جریان بازی", "بازی با دکمه و تایمر جلو نرفت (گیر)",
                                f"{self.g.s.phase.value} روز {self.g.s.day}",
                                key=f"monkey-stuck:{self.g.s.phase.value}")
                    break
            if self.steady_jumps and not s.tg.clock_edits:
                self.r.find("بالا", "ساعت", "پیامِ ساعت هیچ‌وقت خودش را ویرایش نکرد", key="clock-no-edit")
            else:
                self.r.ok("ساعت: یک پیام برای هر فاز که خودش را ویرایش می‌کند")
            return {"ok": self.g.s.phase is Phase.END, "steps": self.steps,
                    "trail": [(p.value, d) for p, d in self.trail]}
        finally:
            s.tg.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="playtest.monkey")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--min", type=int, default=4)
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "monkey"))
    args = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    rb = read_all()
    rep = Report()
    done = total = 0
    for scen in ("classic", "court", "chaos"):
        for n in range(args.min, args.max + 1):
            for seed in range(1, args.seeds + 1):
                rep.context = f"{scen}، {n} نفره، بذر {seed} (شلوغ‌کار)"
                res = Monkey(n, seed, scen, rep, rb).run()
                total += 1
                done += int(bool(res.get("ok")))
    path = rep.write(Path(args.out))
    print(f"🐒 {done}/{total} بازیِ شلوغ‌کار تمام شد · {len(rep.findings)} یافته → {path}")
    for f in rep.sorted():
        print(f"  [{f['sev']}] {f['title']} ×{f['count']} — {f['detail'][:140]} | {'؛ '.join(f['where'][:2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
