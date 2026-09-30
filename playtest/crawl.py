"""خزنده‌ی دکمه‌ها: هر دکمه، در هر وضعیت بازی، برای هر نوع بازیکن — دنبال بن‌بست.

    python -m playtest.crawl          → playtest/DEAD_ENDS.md و dead_ends.json

وضعیت‌ها (لابی، شب، صبح، رای، تساوی، بازجویی، هیئت منصفه، زندان، پایان…) با
agentها و دکمه‌ی واقعی ساخته می‌شوند؛ بعد از هر وضعیت یک «عکس» گرفته می‌شود و
هر تپ روی همان عکس اجرا و دوباره برگردانده می‌شود، تا هر دکمه در همان لحظه سنجیده شود.

بن‌بست یعنی:
  • دکمه‌ای که به هیچ اندپوینتی نمی‌رسد یا «خطای داخلی» می‌دهد
  • صفحه‌ای بی هیچ دکمه‌ای برای ادامه (و بی آنکه متن بخواهد)
  • دکمه‌ای که به کسی نشان داده می‌شود ولی برای او در هیچ وضعیتی کار نمی‌کند
  • وضعیتی که هیچ‌کس با هیچ دکمه‌ای نمی‌تواند بازی را از آن جلو ببرد
  • اندپوینتی که با دکمه هرگز با موفقیت اجرا نمی‌شود
"""
from __future__ import annotations

import json
import logging
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from karagah import bot, db, menus
from karagah.bot import GAMES, handle, route_chat
from karagah.models import Custody, Phase
from karagah.roles import ROLES
from karagah.telegram_app import parse_callback

from .agent import cb_is
from .docs import read_all
from .probes import Scene
from .report import Report

OUTSIDER, ADMIN = 999_111, 777_000
HOME = {"menu", "commands", "back"}
SAMPLE_TEXT = "من آن شب خانه بودم."


class Crawl:
    def __init__(self):
        self.presses = 0
        self.results: List[dict] = []                    # هر تپ یک ردیف
        self.progress: Dict[str, set] = defaultdict(set)  # وضعیت → چه کسانی فاز را جلو بردند
        self.endpoint_ok: Dict[str, int] = defaultdict(int)
        self.endpoint_seen: Dict[str, int] = defaultdict(int)

    # ── عکس و برگرداندن ──
    def snap(self, sc: Scene):
        return pickle.dumps((dict(GAMES), dict(bot._PENDING), dict(bot._ACTIVE_TABLE),
                             dict(bot.LAST_ROSTER), sc.s.tg.clock.now))

    def restore(self, blob, sc: Scene):
        games, pend, act, roster, now = pickle.loads(blob)
        for d, v in ((GAMES, games), (bot._PENDING, pend), (bot._ACTIVE_TABLE, act),
                     (bot.LAST_ROSTER, roster)):
            d.clear()
            d.update(v)
        sc.s.tg.clock.now = now
        for u in [a.uid for a in sc.s.agents] + [OUTSIDER, ADMIN]:
            if db.is_banned(u):
                db.ban(u, False)

    # ── یک تپ ──
    def press(self, uid: int, chat: int, group: int, button: dict) -> Tuple[dict, Optional[str]]:
        self.presses += 1
        if "url" in button:
            url = button["url"]
            if "start=" not in url:
                return {"ok": True, "text": "(لینک بیرونی)", "keyboard": None, "external": True}, None
            arg = url.split("start=", 1)[1].split("&")[0]
            return handle("start", uid, uid, "", arg), "start"
        data = button.get("callback_data", "")
        cmd, arg = parse_callback(data)
        if cmd not in bot._ROUTES:
            return {"ok": False, "text": f"دکمه‌ی مرده: {data}", "keyboard": None, "dead": True}, cmd
        private = chat != group
        target = route_chat(cmd, chat, uid, private)
        if not target:
            return {"ok": False, "text": "مبهم: چند میز", "keyboard": None}, cmd
        res = handle(cmd, target, uid, f"U{uid}", arg)
        res["_target"] = target
        return res, cmd

    # ── یک وضعیت ──
    def crawl_state(self, sc: Scene, label: str, report: Report) -> None:
        group = sc.s.group
        g = GAMES.get(group)
        blob = self.snap(sc)
        people = [("میزبان", sc.host.uid)]
        for a in sc.s.agents[1:]:
            p = g.s.players.get(a.uid) if g else None
            tag = a.role or "بازیکن"
            if p and not p.alive:
                tag += " (مرده)"
            elif p and p.custody is not Custody.FREE:
                tag += f" ({p.custody.value})"
            if p and p.uid == g.s.suspect_uid:
                tag += " (متهم)"
            if g and a.uid == g.s.officer_uid and a.role != "بازجو":
                tag += " (بازجو)"
            people.append((tag, a.uid))
        people += [("غریبه", OUTSIDER), ("ادمینِ غیربازیکن", ADMIN)]
        start_phase = g.s.phase if g else None
        for who, uid in people:
            # ورودی‌ها: منوی پیوی، پیام‌های گروه، داشبورد گروه، پیام‌های پیویِ خودش
            entries: List[Tuple[int, dict, str]] = []
            self.restore(blob, sc)
            entries.append((uid, handle("start", uid, uid, f"U{uid}"), "/start پیوی"))
            for m in sc.s.tg.inbox(group)[-12:]:
                entries.append((group, {"ok": True, "text": m.text, "keyboard": m.keyboard}, "پیام گروه"))
            for m in sc.s.tg.inbox(uid)[-6:]:
                entries.append((uid, {"ok": True, "text": m.text, "keyboard": m.keyboard}, "پیام پیوی"))
            self.restore(blob, sc)
            entries.append((group, handle("dashboard", group, uid, f"U{uid}"), "/dashboard گروه"))
            seen = set()
            frontier = [(c, r, src, 0) for c, r, src in entries]
            while frontier:
                chat, res, src, depth = frontier.pop(0)
                for row in (res.get("keyboard") or {}).get("inline_keyboard", []):
                    for b in row:
                        key = (chat == group, b.get("callback_data") or b.get("url"))
                        if key in seen:
                            continue
                        seen.add(key)
                        self.restore(blob, sc)
                        out, cmd = self.press(uid, chat, group, b)
                        moved = bool(g) and GAMES.get(group) is not None and \
                            GAMES[group].s.phase is not start_phase
                        text_row = None
                        if bot._PENDING.get(uid):              # ربات متن خواست → یک متن نمونه بفرست
                            pchat, pcmd = bot.take_pending(uid)
                            t = handle(pcmd, pchat, uid, f"U{uid}", SAMPLE_TEXT)
                            text_row = {"ok": t["ok"], "text": t["text"][:140]}
                        self.record(label, who, uid, chat == group, src, depth, b, cmd, out, moved, text_row, report)
                        if moved:
                            self.progress[label].add(f"{who}: {b.get('text', '')}")
                        if depth < 3 and out.get("ok") and out.get("keyboard"):
                            where = uid if out.get("private") else chat
                            if out.get("announce") and out.get("_target"):
                                where = out["_target"]
                            frontier.append((where, out, f"{src} → {b.get('text', '')}", depth + 1))
        self.restore(blob, sc)

    def record(self, label, who, uid, in_group, src, depth, b, cmd, out, moved, text_row, report):
        text = out.get("text", "")
        kb = out.get("keyboard")
        cbs = [x.get("callback_data") for row in (kb or {}).get("inline_keyboard", []) for x in row
               if x.get("callback_data")]
        row = {"state": label, "who": who, "where": "گروه" if in_group else "پیوی", "via": src,
               "button": b.get("text", ""), "data": b.get("callback_data") or b.get("url", "")[:50],
               "cmd": cmd, "ok": bool(out.get("ok")), "reply": text[:160], "moved": moved,
               "buttons_after": cbs, "text_reply": text_row, "external": bool(out.get("external"))}
        self.results.append(row)
        if cmd:
            self.endpoint_seen[cmd] += 1
            if out.get("ok"):
                self.endpoint_ok[cmd] += 1
        if "خطای داخلی" in text or (text_row and "خطای داخلی" in text_row["text"]):
            report.find("بالا", "کد", f"خطای داخلی: «{b.get('text')}» ({cmd})",
                        f"{label} / {who} / {src}\n{text[:200]}", key=f"crash:{cmd}")
        if out.get("dead"):
            report.find("بالا", "دکمه‌ها", f"دکمه‌ی مرده: «{b.get('text')}»", row["data"], key=f"dead:{row['data']}")
        if out.get("ok") and not kb and not out.get("external") and not text_row:
            report.find("متوسط", "بن‌بست", f"صفحه‌ی بی‌دکمه بعد از «{b.get('text')}» ({cmd})",
                        f"{label} / {who}: «{text[:120]}» — کاربر برای ادامه باید دستور تایپ کند.",
                        key=f"nokb:{cmd}")
        if text_row and not text_row["ok"]:
            report.find("متوسط", "بن‌بست", f"متنِ خواسته‌شده رد شد بعد از «{b.get('text')}» ({cmd})",
                        f"{label} / {who}: {text_row['text']}", key=f"textfail:{cmd}")


# ───────────────────────── ساختن وضعیت‌ها ─────────────────────────
def build_states(sc: Scene, crawl: Crawl, report: Report, name: str) -> None:
    """وضعیت‌ها را با دکمه‌ی واقعی یکی‌یکی می‌سازد و در هر کدام خزش می‌کند."""
    step = lambda lbl: crawl.crawl_state(sc, f"{name} · {lbl}", report)  # noqa: E731
    step("۱ شب اول")
    killer = sc.role("قاتل")
    victim = sc.citizen(killer)
    for a in sc.s.agents:                                   # همه اکشن می‌دهند؛ قاتل یک نفر را می‌کشد
        if a is killer:
            sc.act(killer, victim)
        elif sc.g.ability_of(sc.g.s.players[a.uid]) not in ("", "hunter") and sc.g.legal_targets(a.uid):
            t = next(u for u in sc.g.legal_targets(a.uid) if u != victim.uid or True)
            a.tap(cb_is("act"), ("dm",), depth=3, nav="act")
            hit = a.find(cb_is(f"act:{t}"), ("dm",), 1)
            if hit:
                a.press(*hit)
    step("۲ شب اول، همه اکشن دادند")
    sc.dawn()
    step("۳ صبح (با کشته)")
    sc.host.tap(cb_is("discuss"), ("group",), depth=20)
    step("۴ گفتگو")
    sc.host.tap(cb_is("vote"), ("group",), depth=6)
    step("۵ رای‌گیری")
    voters = [a for a in sc.s.agents if sc.g.s.players[a.uid].can_vote]
    a, b = voters[0], voters[1]
    voters[2].tap(cb_is(f"vote:{a.uid}"), ("group",), depth=60)
    voters[3].tap(cb_is(f"vote:{b.uid}"), ("group",), depth=60)
    for v in voters[4:] + voters[:2]:
        v.tap(cb_is("vote:0"), ("group",), depth=60)
    sc.close_vote()
    x = sc.citizen(killer)
    if sc.g.s.phase is Phase.VOTE and sc.g.s.tie_leaders:
        step("۶ دور دوم تساوی")
        pick = x.uid if x.uid in sc.g.s.tie_leaders else sc.g.s.tie_leaders[0]
        for v in voters:
            if sc.g.s.players[v.uid].can_vote and v.uid != pick:
                v.tap(cb_is(f"vote:{pick}"), ("group",), depth=60)
        sc.close_vote()
    if sc.g.s.suspect_uid is None:                     # تساوی نشد → یک روزِ دیگر و بازجوییِ x
        sc.interrogate(x)
    step("۷ شب بازجویی")
    off = sc.s.agent(sc.g.s.officer_uid)
    if sc.g.officer_can_judge():
        off.navigate("ask")
        off.say("ساعت یازده کجا بودی؟")
        step("۷ب بازجو پرسید، متهم هنوز جواب نداده")
    sc.host.navigate("pause")
    step("۷ج بازی متوقف")
    sc.host.navigate("resume")
    sc.dawn()
    step("۸ صبح با متهمِ منتظر حکم")
    if sc.g.s.phase is Phase.MORNING and sc.g.awaiting_verdict():
        sus = sc.g.s.suspect_uid
        askers = [v for v in sc.s.agents if sc.g.s.players[v.uid].can_vote and v.uid != sus][:2]
        for v in askers:
            if sc.g.s.phase is Phase.MORNING:
                sc.s.tg.command(v.uid, "/dashboard", sc.s.group)
                v.tap(cb_is("jury"), ("group",), depth=2)
        step("۹ هیئت منصفه")
        for v in sc.s.agents:
            hit = v.find(cb_is("jury:0"), ("group",), 10)
            if hit and sc.g.s.players[v.uid].can_vote:
                v.press(*hit)
        sc.host.tap(cb_is("closejury"), ("group",), depth=10)
        if sc.g.s.phase is Phase.MORNING and sc.g.awaiting_verdict() and sc.g.officer_can_judge():
            sc.verdict(1)
        step("۱۰ صبح با زندانیِ حبس موقت")
    for _ in range(60):                                     # تا پایان با دکمه
        if sc.g.s.phase is Phase.END:
            break
        if sc.g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            sc.dawn()
        elif sc.g.s.phase is Phase.JURY:
            sc.s.tg.clock.advance((sc.g.remaining() or 0) + 1)
            sc.host.tap(cb_is("closejury"), ("group",), depth=10)
        elif sc.g.awaiting_verdict():
            sc.s.tg.clock.advance((sc.g.remaining() or 0) + 1)
            sc.s.tg.timer_job()
        else:
            free = [a for a in sc.s.agents if sc.g.s.players[a.uid].free]
            bad = [a for a in free if ROLES[a.role].align.value != "شهر"]
            sc.interrogate((bad or free)[0])
    if sc.g.s.phase is Phase.END:
        sc.host.tap(cb_is("end"), ("group",), depth=20)
        step("۱۱ پایان بازی")


def lobby_states(crawl: Crawl, report: Report, rb) -> None:
    """پیش از بازی: گروهِ بی‌بازی، لابی ناقص، لابی پر ولی ناآماده، میز موازی."""
    sc = Scene(report, rb, 6, 1, "لابی", lobby=False)
    try:
        s = sc.s
        bot.RATE_LIMIT_ENABLED = False
        for a in s.agents:
            a.read_docs(rb)
        crawl.crawl_state(sc, "لابی · ۰ گروهِ بی‌بازی", report)
        s.tg.command(s.host.uid, "/new", s.group)
        s.agents[1].tap(cb_is("join"), ("group",))
        crawl.crawl_state(sc, "لابی · ۱ لابیِ دو نفره", report)
        for a in s.agents[2:]:
            a.tap(cb_is("join"), ("group",))
        crawl.crawl_state(sc, "لابی · ۲ لابی پر، کسی آماده نیست", report)
        for a in s.agents:
            a.tap(lambda b: "start=ready_" in b.get("url", ""), ("group",), depth=10)
        crawl.crawl_state(sc, "لابی · ۳ همه آماده", report)
    finally:
        sc.s.tg.close()


def check_parallel_tables(report: Report, rb) -> None:
    """«➕ میز تازه»: آیا کسی می‌تواند با دکمه وارد میز دوم شود و آن را بازی کند؟"""
    sc = Scene(report, rb, 5, 1, "میز موازی", lobby=False)
    try:
        s = sc.s
        s.tg.command(s.host.uid, "/new", s.group)
        s.tg.command(s.host.uid, "/newtable", s.group)
        vid = next((c for c in GAMES if c != s.group), None)
        m = s.tg.last(s.group)
        joined = []
        for a in s.agents[1:]:
            hit = a.find(cb_is("join"), ("group",), 1)
            if hit:
                a.press(*hit)
                joined.append(a.uid)
        in_new = [u for u in joined if vid and u in GAMES[vid].s.players]
        if vid and not in_new:
            report.find("بالا", "بن‌بست", "«➕ میز تازه» میزی می‌سازد که هیچ‌کس با دکمه واردش نمی‌شود",
                        f"میز {vid} ساخته شد؛ ولی دکمه‌ی «🙋 منم بازی می‌کنم» زیر پیامِ همان میز callback «join» "
                        "دارد و در گروه به میزِ اصلیِ گروه می‌رسد (route_chat در گروه همیشه chat خود گروه است). "
                        f"{len(joined)} نفر زدند و همه به میز اصلی رفتند. تنها راه ورود، لینک دعوت join_{vid} در پیوی است؛ "
                        "شروع/شب/رای آن میز هم از گروه قابل زدن نیست.", key="newtable")
    finally:
        sc.s.tg.close()


def check_rolecard(report: Report, rb, out: Path) -> Optional[str]:
    """کارت نقش PNG را واقعاً بساز. فونت پیش‌فرض Pillow حروف فارسی و ایموجی ندارد؛
    اگر همه‌ی پیکسل‌های متن یک شکلِ «جعبه» باشند، کارت عملاً خالی است."""
    import shutil
    from karagah import cards
    from PIL import ImageFont
    try:
        path = cards.render_role_card("کارآگاه", "آرش")
    except Exception as e:
        report.find("متوسط", "کد", "کارت نقش PNG ساخته نمی‌شود", str(e))
        return None
    dst = out / "rolecard_sample.png"
    shutil.copy(path, dst)
    font = ImageFont.load_default(size=48)
    if bytes(font.getmask("ک")) == bytes(font.getmask("ه")):   # دو حرف متفاوت، یک شکل = جعبه
        report.find("بالا", "بن‌بست", "کارت نقش تصویری (🖼️) فارسی و ایموجی را جعبه‌ی خالی نشان می‌دهد",
                    "cards.py با فونت پیش‌فرض Pillow می‌نویسد که حروف فارسی و ایموجی ندارد؛ هر حرف یک مستطیلِ "
                    f"ضربدری می‌شود (نمونه: playtest/{dst.name}). حروف هم بدون اتصال و راست‌به‌چپ چیده می‌شوند.",
                    key="rolecard-tofu")
    return dst.name


def check_private_table(report: Report) -> None:
    """«🎮 شروع بازی همین‌جا» + «📨 دعوت دوست» در پیوی: آیا بقیه بازی را می‌بینند؟"""
    from karagah.bot import GAMES
    db.reset(":memory:")
    GAMES.clear()
    host, friends = 61, (62, 63, 64)
    handle("new", host, host, "Host")                     # میزِ ساخته‌شده در پیوی
    for u in friends:
        handle("start", u, u, f"P{u}", f"join_{host}")    # لینک دعوت
    handle("startgame", host, host)
    g = GAMES.get(host)
    if not g or g.s.phase is not Phase.NIGHT:
        return
    for u in list(g.pending_actors()):
        handle("act", host, u, arg=str(g.legal_targets(u)[0]))
    res = handle("dawn", route_chat("dawn", friends[0], friends[0], True), friends[0])
    if res.get("ok") and res.get("announce"):
        report.find("بالا", "بن‌بست", "میزِ ساخته‌شده در پیوی فقط برای میزبان قابل بازی است",
                    "منوی اصلی در پیوی «🎮 شروع بازی همین‌جا» و «📨 دعوت دوست» دارد. دوستان با لینک وارد میزِ "
                    "chat=پیویِ میزبان می‌شوند و بازی شروع می‌شود، ولی هر اعلام عمومی (صبح، کیبورد رای، حکم، "
                    "هیئت منصفه، پایان) به «گروهِ بازی» یعنی پیویِ میزبان می‌رود؛ دوستان فقط «📣 در گروه اعلام شد» "
                    "می‌بینند و هرگز دکمه‌ی رای را نمی‌بینند.", key="private-table")
    GAMES.clear()
    res = handle("start", 70, 70, "X", "join_71")          # دعوت از پیویِ کسی که میز ندارد
    if not res.get("ok"):
        report.find("متوسط", "بن‌بست", "«📨 دعوت دوست» در پیوی به لابیِ ناموجود لینک می‌دهد",
                    f"لینک join_<آیدی پیوی> است؛ اگر فرستنده در پیوی میز نساخته باشد، گیرنده «{res['text'][:60]}» می‌بیند.",
                    key="dm-invite")


def check_one_tap_wipe(report: Report) -> None:
    """میزبان وسط بازی (حتی در توقف) «🎮 شروع بازی همین‌جا» را از منوی گروه می‌زند."""
    from karagah.bot import GAMES
    db.reset(":memory:")
    GAMES.clear()
    G = -777
    handle("new", G, 1, "Host")
    for u in range(2, 6):
        handle("join", G, u, f"P{u}")
    handle("startgame", G, 1)
    handle("pause", G, 1)
    menu = handle("menu", G, 1)
    has_new = any(b.get("callback_data") == "new" for row in menu["keyboard"]["inline_keyboard"] for b in row)
    handle("new", G, 1, "Host")
    if has_new and GAMES[G].s.phase is Phase.LOBBY:
        report.find("بالا", "بن‌بست", "یک تپِ میزبان روی «🎮 شروع بازی همین‌جا»/«⚡ بلیتز» بازیِ در جریان را پاک می‌کند",
                    "منوی اصلیِ گروه (دکمه‌ی «🏠 منوی اصلی» زیر همه‌ی پیام‌ها) این دو دکمه را دارد؛ میزبان با یک تپ، بدون "
                    "تایید و حتی وقتی بازی متوقف است، بازی ۵ نفره را دور می‌ریزد و لابیِ خالی می‌سازد.", key="one-tap-wipe")


def main(argv=None) -> int:
    logging.disable(logging.CRITICAL)
    out = Path(__file__).resolve().parent
    rb = read_all()
    report = Report()
    crawl = Crawl()
    bot.ADMIN_IDS.append(ADMIN)
    try:
        lobby_states(crawl, report, rb)
        for scen, n in (("classic", 9), ("court", 10), ("chaos", 10)):
            sc = Scene(report, rb, n, 2, f"خزش {scen}", scenario=scen)
            try:
                bot.RATE_LIMIT_ENABLED = False       # خزنده سریع‌تر از آدم می‌زند
                build_states(sc, crawl, report, f"{scen}{n}")
            finally:
                sc.s.tg.close()
        check_parallel_tables(report, rb)
        check_private_table(report)
        check_one_tap_wipe(report)
        card = check_rolecard(report, rb, out)
    finally:
        bot.ADMIN_IDS.remove(ADMIN)
    # ماتریسِ خلاصه: هر اندپوینت × هر نوع بازیکن → چند بار کار کرد / چند بار زده شد
    matrix: Dict[str, Dict[str, list]] = defaultdict(dict)
    for r in crawl.results:
        if not r["cmd"] or r["external"]:
            continue
        who = r["who"].split(" (")[0]
        cell = matrix[r["cmd"]].setdefault(who, [0, 0, ""])
        cell[1] += 1
        if r["ok"]:
            cell[0] += 1
        elif not cell[2]:
            cell[2] = r["reply"][:90]
    data = {"presses": crawl.presses, "states": sorted({r["state"] for r in crawl.results}),
            "endpoint_ok": crawl.endpoint_ok, "endpoint_seen": crawl.endpoint_seen,
            "matrix": matrix, "findings": report.sorted(), "rolecard": card}
    (out / "dead_ends.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{crawl.presses} تپ در {len(data['states'])} وضعیت، {len(report.findings)} یافته → playtest/dead_ends.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
