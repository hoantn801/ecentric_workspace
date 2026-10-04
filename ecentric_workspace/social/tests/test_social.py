# Copyright (c) 2026, eCentric and contributors
"""Bang tin + Cau lac bo - service chay THAT tren repo gia (khong can bench).
    python -m unittest ecentric_workspace.social.tests.test_social
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from ecentric_workspace.internal_posts import comments as engine  # noqa: E402
from ecentric_workspace.social import clubs as CL  # noqa: E402
from ecentric_workspace.social import comments_subject as CS  # noqa: E402
from ecentric_workspace.social import constants as C  # noqa: E402
from ecentric_workspace.social import domain as D  # noqa: E402
from ecentric_workspace.social import feed as F  # noqa: E402
from ecentric_workspace.social import moderation as M  # noqa: E402
from ecentric_workspace.social import service as S  # noqa: E402
from ecentric_workspace.social import sources as SRC  # noqa: E402

NOW = dt.datetime(2026, 10, 5, 9, 0)
LAN, KHANG, ANH, TUNG, HR, OUT = "lan@x", "khang@x", "anh@x", "tung@x", "hr@x", "out@x"


class Dup(Exception):
    pass


class FakeRepo:
    """Cung giao dien voi social/repository.py (+ phan binh luan cua internal_posts/repository.py)."""

    def __init__(self):
        self.clock = NOW
        # cay phong ban: Van hanh (1-6) > Kho (2-3); Marketing (7-8)
        self.tree = {"Van hanh": (1, 6, "Vận hành", 1, 0), "Kho": (2, 3, "Kho", 0, 0), "Marketing": (7, 8, "Marketing", 0, 0)}
        self.emp = {LAN: ("Van hanh", 1), KHANG: ("Kho", 2), ANH: ("Marketing", 7), TUNG: ("Kho", 2)}
        self.names = {LAN: "Nguyễn Thị Lan", KHANG: "Đỗ Minh Khang", ANH: "Vũ Ngọc Anh", TUNG: "Bùi Thanh Tùng",
                      HR: "Phòng Nhân sự"}
        self.mods = {HR}
        self.posts, self.images, self.mentions = {}, {}, {}
        self.rx, self.comments, self.bells, self.logged = [], {}, [], []
        self.clubs_, self.members_, self.rsvps_, self.reports = {}, [], [], []
        self.files = {}
        self.n = 0

    # nguoi
    def now(self): return self.clock
    def today(self): return self.clock.date()
    def is_moderator(self, u): return u in self.mods
    def viewer(self, u):
        e = self.emp.get(u)
        return {"employee": "EMP-" + u, "department": e[0], "lft": e[1]} if e else None
    def dept_tree(self): return self.tree
    def full_names(self, users): return {u: self.names.get(u, u) for u in users if u}
    def user_departments(self, users): return {u: self.tree[self.emp[u][0]][2] for u in users if u in self.emp}
    def hr_managers(self): return [HR]
    def people(self): return [{"user": u, "name": self.names[u], "dept": self.tree[e[0]][2]} for u, e in self.emp.items()]
    def employee_user(self, emp): return {"E-LAN": LAN, "E-TUNG": TUNG}.get(emp)
    def log_error(self, t): self.logged.append(t)

    # bai
    def _name(self, p):
        self.n += 1
        return "%s%03d" % (p, self.n)

    def insert_post(self, values, mentions=()):
        if values.get("moment_key") and any(p.get("moment_key") == values["moment_key"] for p in self.posts.values()):
            raise Dup()
        name = self._name("SP")
        row = {k: None for k in ("club", "dept_only", "department", "body", "kudos_to", "kudos_value", "event_title",
                                 "event_start", "event_place", "moment_key", "hidden", "hidden_by", "hidden_on",
                                 "hidden_reason", "report_count", "edited_on", "author")}
        row.update(values, name=name, creation=self.clock, owner=values.get("author"))
        self.posts[name] = row
        self.mentions[name] = list(mentions or [])
        self.clock += dt.timedelta(minutes=1)
        return name

    def attach_images(self, name, imgs):
        self.images[name] = [{"file_url": "/private/files/%s-%d" % (name, i), "file_name": im["name"],
                              "width": im["width"], "height": im["height"]} for i, im in enumerate(imgs)]
        for i, im in enumerate(imgs):
            self.files["/private/files/%s-%d" % (name, i)] = (name, im["content"])

    def clean_image(self, content, ext, side):
        if content == b"broken":
            raise ValueError("x")
        return b"CLEAN:" + content, "jpg" if ext in ("jpg", "jpeg") else "png", 800, 600

    def image_content(self, name, url):
        got = self.files.get(url)
        return ("anh.jpg", got[1]) if got and got[0] == name else None

    def post(self, name): return dict(self.posts[name]) if name in self.posts else None
    def post_exists(self, name): return name in self.posts
    def update_post(self, name, values): self.posts[name].update(values)
    def images_of(self, names): return {n: list(self.images.get(n) or []) for n in names}
    def mentions_of(self, names): return {n: list(self.mentions.get(n) or []) for n in names}
    def posts_since(self, user, since):
        return sum(1 for p in self.posts.values() if p["author"] == user and p["kind"] != "moment" and p["creation"] >= since)

    def delete_post(self, name):
        self.posts.pop(name)
        self.comments = {k: c for k, c in self.comments.items() if c["post"] != name}

    def feed_rows(self, before=None, limit=60, kinds=None, author=None, mine=None, clubs=None, department=None,
                  upcoming_after=None):
        out = []
        for p in sorted(self.posts.values(), key=lambda p: p["creation"], reverse=True):
            if p["kind"] == "moment" or (before and p["creation"] >= before) or (kinds and p["kind"] not in kinds):
                continue
            if author and p["author"] != author or clubs is not None and p.get("club") not in clubs:
                continue
            if department and p.get("department") != department:
                continue
            if mine and mine not in (p["author"], p.get("kudos_to")):
                continue
            if upcoming_after and (not p.get("event_start") or p["event_start"] < upcoming_after):
                continue
            out.append(dict(p))
        return out[:limit]

    def events_between(self, start, end, limit=50):
        return sorted([dict(p) for p in self.posts.values() if p["kind"] == "event" and not p.get("hidden")
                       and start <= p["event_start"] < end], key=lambda p: p["event_start"])

    def club_events(self, club, start, limit=20):
        return sorted([dict(p) for p in self.posts.values() if p["kind"] == "event" and p.get("club") == club
                       and p["event_start"] >= start], key=lambda p: p["event_start"])[:limit]

    def hidden_posts(self, limit=100): return [dict(p) for p in self.posts.values() if p.get("hidden")]

    # khoanh khac
    def moment_post(self, key):
        return next((dict(p) for p in self.posts.values() if p.get("moment_key") == key), None)

    def moment_posts(self, keys): return {p["moment_key"]: dict(p) for p in self.posts.values() if p.get("moment_key") in keys}

    def insert_moment(self, key, owner):
        try:
            self.insert_post({"kind": "moment", "moment_key": key, "author": owner})
        except Dup:
            pass
        return self.moment_post(key)

    # cam xuc
    def reactions(self, targets): return [dict(r) for r in self.rx if r["target"] in targets]
    def find_reaction(self, t, k, u):
        for i, r in enumerate(self.rx):
            if (r["target"], r["kind"], r["user"]) == (t, k, u):
                return "RX%d" % i
        return None
    def add_reaction(self, t, k, u, d): self.rx.append({"target": t, "kind": k, "user": u})
    def remove_reaction(self, name): self.rx.pop(int(name[2:]))
    def is_duplicate(self, exc): return isinstance(exc, Dup)

    # binh luan (giao dien internal_posts/repository)
    def comments_of(self, post, ref_doctype=None):
        return [dict(c) for c in sorted(self.comments.values(), key=lambda c: c["creation"])
                if c["post"] == post and c["ref_doctype"] == (ref_doctype or "EC Internal Post")]
    def comment(self, name): return dict(self.comments[name]) if name in self.comments else None
    def insert_comment(self, post, user, content, parent=None, ref_doctype=None):
        name = self._name("CM")
        self.comments[name] = {"name": name, "ref_doctype": ref_doctype or "EC Internal Post", "post": post, "user": user,
                               "content": content, "parent_comment": parent, "hidden": 0, "hidden_by": None,
                               "hidden_on": None, "deleted": 0, "edited_on": None, "creation": self.clock}
        self.clock += dt.timedelta(seconds=1)
        return name
    def update_comment(self, name, values): self.comments[name].update(values)
    def comment_count_since(self, post, user, since, ref_doctype=None):
        return sum(1 for c in self.comments.values() if c["post"] == post and c["user"] == user and c["creation"] >= since)
    def comment_counts(self, names, ref_doctype=C.POST_DT):
        return {n: sum(1 for c in self.comments.values() if c["post"] == n and c["ref_doctype"] == ref_doctype
                       and not c["hidden"] and not c["deleted"]) for n in names}

    def send_bell(self, *a, **kw):
        if len(a) == 7:                       # internal_posts.comments: (event, user, title, message, url, ref, dedupe)
            a = a[1:]
        user, title, message, url, ref, dedupe = a
        if any(b[5] == dedupe for b in self.bells):
            return
        self.bells.append((user, title, message, url, ref, dedupe, kw.get("actor")))

    # CLB
    def clubs(self, statuses=None):
        return sorted([dict(c) for c in self.clubs_.values() if not statuses or c["status"] in statuses],
                      key=lambda c: c["club_name"])
    def club(self, name): return dict(self.clubs_[name]) if name in self.clubs_ else None
    def club_by_slug(self, slug): return next((dict(c) for c in self.clubs_.values() if c["slug"] == slug), None)
    def slug_taken(self, slug): return any(c["slug"] == slug for c in self.clubs_.values())
    def insert_club(self, values):
        name = self._name("CLB")
        row = {"lead": None, "proposed_by": None, "decided_by": None, "decided_on": None, "decision_note": "",
               "emoji": "", "color": "green", "category": "Thể thao", "description": ""}
        row.update(values, name=name, creation=self.clock)
        self.clubs_[name] = row
        return name
    def update_club(self, name, values): self.clubs_[name].update(values)
    def open_proposals_of(self, u): return sum(1 for c in self.clubs_.values() if c["proposed_by"] == u and c["status"] == C.CLUB_PENDING)
    def members(self, club): return [m["user"] for m in self.members_ if m["club"] == club]
    def member_counts(self, names): return {n: len(self.members(n)) for n in names}
    def member_samples(self, names, per=3): return {n: self.members(n)[:per] for n in names}
    def clubs_of(self, u): return [m["club"] for m in self.members_ if m["user"] == u]
    def find_member(self, club, u):
        return next(("M%d" % i for i, m in enumerate(self.members_) if m["club"] == club and m["user"] == u), None)
    def add_member(self, club, u):
        if self.find_member(club, u):
            raise Dup()
        self.members_.append({"club": club, "user": u})
    def remove_member(self, name): self.members_.pop(int(name[1:]))

    # tham gia
    def rsvps(self, posts): return [dict(r) for r in self.rsvps_ if r["post"] in posts]
    def find_rsvp(self, post, u): return next((dict(r) for r in self.rsvps_ if r["post"] == post and r["user"] == u), None)
    def add_rsvp(self, post, u, a): self.rsvps_.append({"name": "R%d" % len(self.rsvps_), "post": post, "user": u, "answer": a})
    def set_rsvp(self, name, a): next(r for r in self.rsvps_ if r["name"] == name)["answer"] = a
    def remove_rsvp(self, name): self.rsvps_ = [r for r in self.rsvps_ if r["name"] != name]

    # bao cao
    def find_report(self, post, u): return next((r["name"] for r in self.reports if r["post"] == post and r["user"] == u), None)
    def add_report(self, post, u, reason):
        self.reports.append({"name": "RP%d" % len(self.reports), "post": post, "user": u, "reason": reason,
                             "status": C.REPORT_NEW, "creation": self.clock})
    def count_reports(self, post, status=None): return sum(1 for r in self.reports if r["post"] == post and (not status or r["status"] == status))
    def open_reports(self): return [dict(r) for r in self.reports if r["status"] == C.REPORT_NEW]
    def close_reports(self, post, by, action, at):
        for r in self.reports:
            if r["post"] == post and r["status"] == C.REPORT_NEW:
                r.update(status=C.REPORT_DONE, handled_by=by, action=action)


def club(repo, title="Chạy bộ", lead=KHANG, status=C.CLUB_ACTIVE, members=(KHANG, LAN)):
    name = repo.insert_club({"club_name": title, "slug": D.slugify(title), "emoji": "🏃", "status": status, "lead": lead})
    for m in members:
        repo.add_member(name, m)
    return name


HR_CARDS = []
PEOPLE = {"birthdays": [], "onboard": [], "anniversaries": []}


def setUpModule():
    global _orig
    _orig = (SRC.hr_cards, SRC.people_today, SRC.open_surveys, SRC.feedback_done, SRC.toggle_moment)
    SRC.hr_cards = lambda user, repo=None: [dict(c) for c in HR_CARDS]
    SRC.people_today = lambda repo=None: PEOPLE
    SRC.open_surveys = lambda user, repo=None: [{"name": "SV1", "title": "Khảo sát văn phòng mới", "url": "/khao-sat/lam?s=SV1",
                                                 "close_at": "2026-10-07 17:00:00"}]
    SRC.feedback_done = lambda user, limit=3, repo=None: []


def tearDownModule():
    SRC.hr_cards, SRC.people_today, SRC.open_surveys, SRC.feedback_done, SRC.toggle_moment = _orig


def hr_card(name, ts, pinned=False, need_ack=False):
    return {"name": name, "url": "/tin-noi-bo/" + name.lower(), "title": "Tin " + name, "summary": "", "pinned": pinned,
            "need_ack": need_ack, "ack_deadline_label": "", "date_label": ts.strftime("%d/%m/%Y"), "ts": ts,
            "category": {"name": "Chính sách"}, "cover": {"kind": "color", "color": "navy", "image": ""},
            "author": "", "scope_label": "", "rx_total": 0, "rx_kinds": [], "rx_mine": False, "comments": 0,
            "comment_url": "/tin-noi-bo/x#binh-luan"}


# ====================================================================== tests ====
class TestAccess(unittest.TestCase):
    def test_guest_and_non_employee_are_refused(self):
        r = FakeRepo()
        for u in ("Guest", "", OUT):
            with self.assertRaises(S.Forbidden):
                S.context(r, u)
        self.assertTrue(S.context(r, HR)["moderator"])          # HR khong co ho so van kiem duyet duoc

    def test_dept_only_post_follows_the_department_subtree(self):
        r = FakeRepo()
        name = S.create(LAN, {"body": "Họp phòng 3h", "dept_only": "1"}, repo=r)["name"]
        self.assertEqual(r.posts[name]["department"], "Van hanh")
        self.assertTrue(S.post_view(KHANG, name, repo=r))       # Kho la phong con cua Van hanh
        with self.assertRaises(S.Forbidden):
            S.post_view(ANH, name, repo=r)                      # Marketing khong thay
        self.assertTrue(S.post_view(HR, name, repo=r))

    def test_image_follows_the_post_visibility(self):
        r = FakeRepo()
        name = S.create(LAN, {"body": "x", "dept_only": "1"}, [{"name": "a.JPG", "content": b"img"}], repo=r)["name"]
        orig = S._repo
        S._repo = lambda repo: r
        try:
            self.assertEqual(S.image(KHANG, name, 0), ("anh.jpg", b"CLEAN:img"))
            with self.assertRaises(S.Forbidden):
                S.image(ANH, name, 0)
            with self.assertRaises(S.NotFound):
                S.image(KHANG, name, 5)
        finally:
            S._repo = orig


class TestCreate(unittest.TestCase):
    def test_plain_post_with_images_and_mentions(self):
        r = FakeRepo()
        card = S.create(LAN, {"body": "  Ca đêm xong sớm 🎉  ", "mentions": [KHANG, LAN, OUT, KHANG]},
                        [{"name": "IMG_1.jpeg", "content": b"a"}, {"name": "b.png", "content": b"b"}], repo=r)
        p = r.posts[card["name"]]
        self.assertEqual(p["body"], "Ca đêm xong sớm 🎉")
        self.assertEqual(r.mentions[card["name"]], [KHANG])     # bo trung, bo chinh minh, bo nguoi ngoai
        self.assertEqual([i["file_name"] for i in r.images[card["name"]]], ["anh-1.jpg", "anh-2.png"])
        self.assertEqual(card["n_images"], 2)
        self.assertIn("/api/method/ecentric_workspace.social.api.image?post=", card["images"][0]["src"])
        self.assertEqual([(b[0], b[5]) for b in r.bells], [(KHANG, "social_tag|%s|%s" % (card["name"], KHANG))])

    def test_empty_bad_image_and_rate_limit(self):
        r = FakeRepo()
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "   "}, repo=r)
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "x"}, [{"name": "virus.exe", "content": b"x"}], repo=r)
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "x"}, [{"name": "a.jpg", "content": b"broken"}], repo=r)
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "x"}, [{"name": "a.jpg", "content": b"x"}] * 7, repo=r)
        for i in range(C.POST_RATE_MAX):
            S.create(LAN, {"body": "bài %d" % i}, repo=r)
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "thêm"}, repo=r)
        self.assertEqual(len(r.posts), C.POST_RATE_MAX)

    def test_kudos(self):
        r = FakeRepo()
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "tự khen", "kudos_to": LAN}, repo=r)
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "", "kudos_to": KHANG}, repo=r)
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "x", "kudos_to": KHANG, "kudos_value": "khong-co"}, repo=r)
        card = S.create(LAN, {"body": "Cảm ơn anh đã ở lại gỡ đơn", "kudos_to": KHANG, "kudos_value": "tan-tam",
                              "mentions": [KHANG, ANH]}, repo=r)
        self.assertEqual(card["kind"], "kudos")
        self.assertEqual(card["kudos"]["value"], "Tận tâm")
        self.assertEqual(r.mentions[card["name"]], [ANH])       # nguoi duoc khen khong bi gan ten lan nua
        self.assertEqual([b[0] for b in r.bells], [KHANG, ANH])
        self.assertIn("khen bạn · Tận tâm", r.bells[0][1])

    def test_club_post_and_event_rules(self):
        r = FakeRepo()
        c = club(r)
        with self.assertRaises(S.Forbidden):
            S.create(ANH, {"body": "xin vào", "club": c}, repo=r)              # chua tham gia
        S.create(LAN, {"body": "Sáng nay 8km", "club": c}, repo=r)
        ev = {"club": c, "event_title": "Chạy 5km", "event_start": "2026-10-11T06:00", "event_place": "Q7"}
        with self.assertRaises(S.Forbidden):
            S.create(LAN, dict(ev), repo=r)                                   # khong phai nguoi phu trach
        with self.assertRaises(S.SocialError):
            S.create(KHANG, dict(ev, event_start="2026-10-01T06:00"), repo=r)  # da qua
        with self.assertRaises(S.SocialError):
            S.create(KHANG, {"event_title": "x", "event_start": "2026-10-11T06:00"}, repo=r)  # ngoai CLB
        r.bells = []
        card = S.create(KHANG, ev, repo=r)
        self.assertEqual(card["kind"], "event")
        self.assertEqual(card["event"]["when"], "06:00 Chủ Nhật 11/10")
        self.assertEqual(card["event"]["date"], {"mon": "TH10", "day": "11"})
        self.assertEqual([b[0] for b in r.bells], [LAN])                       # chuong chi thanh vien, tru nguoi tao
        r.update_club(c, {"status": C.CLUB_ARCHIVED})
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "x", "club": c}, repo=r)


class TestReviewFixes(unittest.TestCase):
    def test_dept_only_cannot_reach_people_outside(self):
        r = FakeRepo()
        with self.assertRaises(S.SocialError) as cx:
            S.create(LAN, {"body": "cảm ơn", "kudos_to": ANH, "dept_only": "1"}, repo=r)
        self.assertIn("Vũ Ngọc Anh", str(cx.exception))
        with self.assertRaises(S.SocialError):
            S.create(LAN, {"body": "x", "mentions": [ANH], "dept_only": "1"}, repo=r)
        S.create(LAN, {"body": "cảm ơn", "kudos_to": KHANG, "dept_only": "1"}, repo=r)   # Kho thuoc Van hanh

    def test_reported_post_cannot_be_deleted_and_hr_hears_new_round(self):
        r = FakeRepo()
        p = S.create(LAN, {"body": "x"}, repo=r)["name"]
        S.report(KHANG, p, "", repo=r)
        with self.assertRaises(S.SocialError):
            S.delete(LAN, p, repo=r)
        S.dismiss_reports(HR, p, repo=r)
        S.report(ANH, p, "lại", repo=r)
        self.assertEqual(len([b for b in r.bells if b[5].startswith("social_report")]), 2)
        self.assertEqual(r.posts[p]["report_count"], 1)
        S.dismiss_reports(HR, p, repo=r)
        S.delete(LAN, p, repo=r)

    def test_hidden_moment_and_archived_club(self):
        global PEOPLE
        r = FakeRepo()
        PEOPLE = {"birthdays": [{"key": "bd:E-LAN:2026", "emp": "E-LAN", "name": "Lan", "role": "", "initials": "L"}],
                  "onboard": [], "anniversaries": []}
        try:
            name = CS.ensure_moment(KHANG, "bd:E-LAN:2026", repo=r)
            r.posts[name]["hidden"] = 1
            self.assertEqual(F.moments(r, S.context(r, KHANG)), [])
        finally:
            PEOPLE = {"birthdays": [], "onboard": [], "anniversaries": []}
        c = club(r)
        S.create(KHANG, {"club": c, "event_title": "Chạy", "event_start": "2026-10-11T06:00"}, repo=r)
        CL.set_status(HR, c, False, repo=r)
        self.assertEqual(SRC.popup_events(LAN, dt.date(2026, 10, 5), repo=r), [])
        self.assertEqual(CL.leave(LAN, c, repo=r)["joined"], False)


class TestActions(unittest.TestCase):
    def setUp(self):
        self.r = FakeRepo()
        self.p = S.create(LAN, {"body": "Bánh mì hôm nay mình bao!"}, repo=self.r)["name"]

    def test_react_toggles_one_heart(self):
        self.assertEqual(S.react(KHANG, self.p, repo=self.r), {"total": 1, "emojis": "❤️", "mine": True, "who": "Bạn"})
        S.react(ANH, self.p, repo=self.r)
        self.assertEqual(S.post_view(KHANG, self.p, repo=self.r)["rx"]["who"], "Bạn, Vũ Ngọc Anh")    # re chuot: ai da tha
        self.assertEqual(S.post_view(LAN, self.p, repo=self.r)["rx"]["who"], "Đỗ Minh Khang, Vũ Ngọc Anh")
        S.react(ANH, self.p, repo=self.r)
        self.assertEqual(S.react(KHANG, self.p, repo=self.r)["total"], 0)

    def test_edit_and_delete_rights(self):
        with self.assertRaises(S.Forbidden):
            S.edit(KHANG, self.p, "sửa trộm", repo=self.r)
        card = S.edit(LAN, self.p, "Bánh mì + cà phê", repo=self.r)
        self.assertTrue(card["edited"])
        with self.assertRaises(S.Forbidden):
            S.delete(KHANG, self.p, repo=self.r)
        S.delete(HR, self.p, repo=self.r)
        self.assertNotIn(self.p, self.r.posts)

    def test_report_then_hr_hides(self):
        with self.assertRaises(S.SocialError):
            S.report(LAN, self.p, "", repo=self.r)                  # bai cua minh
        self.assertEqual(S.report(KHANG, self.p, "Quảng cáo", repo=self.r), {"reported": True, "again": False})
        self.assertEqual(S.report(KHANG, self.p, "lần 2", repo=self.r)["again"], True)
        S.report(ANH, self.p, "", repo=self.r)
        self.assertEqual(self.r.posts[self.p]["report_count"], 2)
        self.assertEqual([b[0] for b in self.r.bells if b[5].startswith("social_report")], [HR])   # chi lan dau
        with self.assertRaises(S.Forbidden):
            S.hide(KHANG, self.p, repo=self.r)
        S.hide(HR, self.p, True, "Spam", repo=self.r)
        self.assertEqual(self.r.open_reports(), [])
        with self.assertRaises(S.Forbidden):
            S.post_view(KHANG, self.p, repo=self.r)                 # nguoi khac khong thay nua
        own = S.post_view(LAN, self.p, repo=self.r)
        self.assertTrue(own["hidden"])
        self.assertEqual(own["hidden_reason"], "Spam")
        self.assertFalse(own["can_edit"])
        with self.assertRaises(S.SocialError):
            S.react(LAN, self.p, repo=self.r)
        S.hide(HR, self.p, False, repo=self.r)
        self.assertTrue(S.post_view(KHANG, self.p, repo=self.r))

    def test_rsvp_toggle_switch_and_past(self):
        c = club(self.r)
        ev = S.create(KHANG, {"club": c, "event_title": "Chạy", "event_start": "2026-10-11T06:00"}, repo=self.r)["name"]
        card = S.rsvp(LAN, ev, "going", repo=self.r)
        self.assertEqual((card["event"]["going"], card["event"]["mine"]), (1, "going"))
        self.assertEqual(card["event"]["line"], "Bạn")
        S.rsvp(ANH, ev, "going", repo=self.r)
        card = S.rsvp(TUNG, ev, "going", repo=self.r)
        self.assertEqual(card["event"]["line"], "Bạn, Lan và 1 người khác")
        card = S.rsvp(LAN, ev, "maybe", repo=self.r)
        self.assertEqual((card["event"]["going"], card["event"]["maybe"]), (2, 1))
        card = S.rsvp(LAN, ev, "maybe", repo=self.r)                # bam lai = bo
        self.assertEqual((card["event"]["maybe"], card["event"]["mine"]), (0, ""))
        with self.assertRaises(S.SocialError):
            S.rsvp(LAN, ev, "no", repo=self.r)
        with self.assertRaises(S.SocialError):
            S.rsvp(LAN, self.p, "going", repo=self.r)
        self.r.clock = dt.datetime(2026, 10, 12, 10, 0)
        with self.assertRaises(S.SocialError):
            S.rsvp(LAN, ev, "going", repo=self.r)


class TestFeed(unittest.TestCase):
    def setUp(self):
        global HR_CARDS, PEOPLE
        self.r = r = FakeRepo()
        r.clock = dt.datetime(2026, 10, 4, 8, 0)
        self.c = club(r)
        self.a = S.create(LAN, {"body": "bài 1"}, repo=r)["name"]
        self.k = S.create(ANH, {"body": "cảm ơn", "kudos_to": LAN}, repo=r)["name"]
        self.cp = S.create(KHANG, {"body": "Tối nay chạy", "club": self.c}, repo=r)["name"]
        self.ev = S.create(KHANG, {"club": self.c, "event_title": "Chạy 5km", "event_start": "2026-10-11T06:00"}, repo=r)["name"]
        self.h = S.create(TUNG, {"body": "spam"}, repo=r)["name"]
        S.hide(HR, self.h, True, repo=r)
        r.clock = NOW
        HR_CARDS = [hr_card("OLD", dt.datetime(2026, 9, 1, 8, 0), pinned=True),
                    hr_card("PIN", dt.datetime(2026, 10, 3, 8, 0), pinned=True, need_ack=True),
                    hr_card("NEW", dt.datetime(2026, 10, 4, 8, 2, 30))]
        PEOPLE = {"birthdays": [{"key": "bd:E-LAN:2026", "emp": "E-LAN", "name": "Nguyễn Thị Lan", "given": "Lan",
                                 "role": "AE · Vận hành", "initials": "NL"}], "onboard": [], "anniversaries": []}

    def tearDown(self):
        global HR_CARDS, PEOPLE
        HR_CARDS, PEOPLE = [], {"birthdays": [], "onboard": [], "anniversaries": []}

    def kinds(self, ctx):
        return [(it["type"], it["key"] if it["type"] == "moment" else it.get("name")) for it in ctx["items"]]

    def test_all_merges_hr_and_moments_by_time(self):
        ctx = F.page(KHANG, repo=self.r)
        self.assertEqual(self.kinds(ctx), [("hr", "PIN"), ("moment", "bd:E-LAN:2026"), ("post", self.ev), ("hr", "NEW"),
                                           ("post", self.cp), ("post", self.k), ("post", self.a), ("hr", "OLD")])
        self.assertNotIn(self.h, [x[1] for x in self.kinds(ctx)])          # bai bi an
        self.assertEqual([t["text"] for t in ctx["todo"]][0], "Xác nhận đã đọc: Tin PIN")
        self.assertIn("Khảo sát: Khảo sát văn phòng mới · còn 2 ngày", [t["text"] for t in ctx["todo"]])
        self.assertEqual([c["title"] for c in ctx["my_clubs"]], ["Chạy bộ"])
        self.assertEqual(ctx["my_clubs"][0]["next"], "Sự kiện CN 11/10 · Chạy 5km")
        self.assertEqual(ctx["today"][0]["short"], "Sinh nhật · Vận hành")
        self.assertEqual(ctx["next"], "")
        tung = F.page(TUNG, repo=self.r)                                  # nguoi dang thay bai bi an cua minh
        self.assertIn(self.h, [x[1] for x in self.kinds(tung)])

    def test_filters(self):
        get = lambda loc, u=KHANG: [x[1] for x in self.kinds(F.page(u, loc, repo=self.r))]  # noqa: E731
        self.assertEqual(get("tin-hr"), ["NEW", "PIN", "OLD"])         # chi trang "Tat ca" day tin ghim len dau
        self.assertEqual(get("loi-khen"), [self.k])
        self.assertEqual(get("cua-toi", LAN), [self.k, self.a])          # bai minh dang + loi khen minh nhan
        self.assertEqual(get("clb-cua-toi"), [self.ev, self.cp])
        self.assertEqual(get("clb-cua-toi", ANH), [])
        self.assertEqual(get("phong-toi", LAN), [self.a])
        self.assertEqual(get("su-kien"), ["SV1", self.ev])
        self.assertEqual(F.page(KHANG, "khong-co", repo=self.r)["loc"], "")

    def test_pagination_cursor(self):
        for i in range(C.FEED_PAGE + 3):
            S.create(KHANG if i % 2 else TUNG, {"body": "b%d" % i}, repo=self.r)
            self.r.clock += dt.timedelta(minutes=10)
        p1 = F.page(LAN, "cua-toi", repo=self.r)
        self.assertEqual(p1["next"], "")
        p1 = F.page(LAN, repo=self.r)
        self.assertEqual(len([i for i in p1["items"] if i["type"] != "moment"]), C.FEED_PAGE + 1)  # + 1 tin ghim
        self.assertTrue(p1["next"])
        p2 = F.page(LAN, "", p1["next"], repo=self.r)
        seen = {i.get("name") for i in p1["items"]}
        self.assertFalse(seen & {i.get("name") for i in p2["items"]})
        self.assertEqual(p2["todo"], [])
        self.assertFalse(p2["first_page"])

    def test_moment_wish_and_reaction_share_popup_keys(self):
        ctx = F.page(KHANG, repo=self.r)
        m = ctx["items"][1]
        self.assertEqual((m["rx_kind"], m["post"], m["wishes"], m["anchor"]), ("cake", "", 0, "m-bd-E-LAN-2026"))
        with self.assertRaises(D.SocialError):
            CS.ensure_moment(KHANG, "bd:E-OTHER:2026", repo=self.r)
        name = CS.ensure_moment(KHANG, "bd:E-LAN:2026", repo=self.r)
        self.assertEqual(CS.ensure_moment(ANH, "bd:E-LAN:2026", repo=self.r), name)
        self.assertEqual(self.r.posts[name]["author"], LAN)                 # nguoi duoc chuc la "chu bai"
        subj = CS.SocialSubject(self.r)
        view = engine.add(KHANG, name, "Chúc mừng sinh nhật Lan!", repo=self.r, subject=subj)
        self.assertEqual(view["count"], 1)
        self.assertEqual(self.r.bells[-1][0], LAN)
        self.assertEqual(self.r.bells[-1][1], "Đỗ Minh Khang chúc mừng sinh nhật bạn")
        self.assertEqual(self.r.bells[-1][3], "/bang-tin/bai/%s#binh-luan" % name)
        ctx = F.page(ANH, repo=self.r)
        self.assertEqual((ctx["items"][1]["post"], ctx["items"][1]["wishes"]), (name, 1))
        self.assertEqual(SRC.wish_counts(["bd:E-LAN:2026", "bd:X"], repo=self.r), {"bd:E-LAN:2026": 1})
        self.assertNotIn(name, [x[1] for x in self.kinds(F.page(LAN, "cua-toi", repo=self.r))])

    def test_popup_events(self):
        S.create(LAN, {"body": "x", "dept_only": "1"}, repo=self.r)
        out = SRC.popup_events(ANH, dt.date(2026, 10, 5), repo=self.r)
        self.assertEqual([(e["title"], e["days_left"], e["club"], e["month"]) for e in out], [("Chạy 5km", 6, "Chạy bộ", "Th10")])
        self.assertEqual(SRC.popup_events(ANH, dt.date(2026, 9, 20), repo=self.r), [])  # ngoai 14 ngay


class TestComments(unittest.TestCase):
    def test_social_comments_use_the_shared_engine(self):
        r = FakeRepo()
        p = S.create(LAN, {"body": "Ai đi ăn trưa?", "dept_only": "1"}, repo=r)["name"]
        subj = CS.SocialSubject(r)
        view = engine.add(KHANG, p, "Mình!", repo=r, subject=subj)
        self.assertEqual((view["count"], view["items"][0]["is_post_author"]), (1, False))
        self.assertEqual(r.comments[view["items"][0]["name"]]["ref_doctype"], C.POST_DT)
        self.assertEqual(r.bells[-1][:2], (LAN, "Đỗ Minh Khang bình luận bài của bạn trên Bảng tin"))
        with self.assertRaises(S.Forbidden):
            engine.add(ANH, p, "Cho mình với", repo=r, subject=subj)     # khong thay bai Chi phong toi
        cm = view["items"][0]["name"]
        engine.like(LAN, cm, repo=r, subject=subj)
        with self.assertRaises(Exception):
            engine.hide(KHANG, cm, repo=r, subject=subj)                 # chi HR
        engine.hide(HR, cm, repo=r, subject=subj)
        self.assertEqual(S.post_view(LAN, p, repo=r)["comments"], 0)
        # ma binh luan cua Tin noi bo khong dung duoc qua cua Bang tin (va nguoc lai)
        icm = r.insert_comment("IP1", LAN, "tin noi bo")
        with self.assertRaises(Exception) as cx:
            engine.like(LAN, icm, repo=r, subject=subj)
        self.assertIn("Không tìm thấy bình luận", str(cx.exception))
        S.hide(HR, p, True, repo=r)
        with self.assertRaises(Exception):
            engine.add(LAN, p, "còn bình luận được không?", repo=r, subject=subj)


class TestClubs(unittest.TestCase):
    def test_propose_decide_join_leave(self):
        r = FakeRepo()
        club(r, "Chạy bộ")
        with self.assertRaises(D.SocialError):
            CL.propose(ANH, {"club_name": "Chạy bộ", "description": ""}, repo=r)
        out = CL.propose(ANH, {"club_name": "Chạy bộ", "description": "Chạy tối", "emoji": "🏃", "color": "hack"}, repo=r)
        self.assertEqual((out["slug"], out["status"]), ("chay-bo-2", C.CLUB_PENDING))
        name = out["name"]
        self.assertEqual(r.clubs_[name]["color"], "green")
        self.assertEqual(r.members(name), [ANH])
        self.assertEqual(r.bells[-1][0], HR)
        CL.join(LAN, name, repo=r)                                        # "toi cung muon tham gia"
        lst = CL.list_page(TUNG, repo=r)
        self.assertEqual([(c["title"], c["members"]) for c in lst["pending"]], [("Chạy bộ", 2)])
        with self.assertRaises(D.Forbidden):
            CL.decide(LAN, name, True, repo=r)
        with self.assertRaises(D.SocialError):
            CL.decide(HR, name, False, "", repo=r)                        # tu choi phai co ly do
        CL.decide(HR, name, True, "", repo=r)
        self.assertEqual(r.clubs_[name]["status"], C.CLUB_ACTIVE)
        self.assertEqual(r.bells[-1][:2], (ANH, "HR đã duyệt CLB Chạy bộ"))
        with self.assertRaises(D.SocialError):
            CL.decide(HR, name, True, repo=r)
        with self.assertRaises(D.SocialError):
            CL.leave(ANH, name, repo=r)                                   # dang phu trach
        self.assertEqual(CL.leave(LAN, name, repo=r), {"joined": False, "members": 1})
        CL.set_lead(HR, name, KHANG, repo=r)
        self.assertEqual((r.clubs_[name]["lead"], KHANG in r.members(name)), (KHANG, True))

    def test_proposal_limits_and_hr_opens_directly(self):
        r = FakeRepo()
        for i in range(C.CLUB_PROPOSE_MAX_OPEN):
            CL.propose(LAN, {"club_name": "CLB %d" % i, "description": "x"}, repo=r)
        with self.assertRaises(D.SocialError):
            CL.propose(LAN, {"club_name": "CLB thêm", "description": "x"}, repo=r)
        out = CL.propose(HR, {"club_name": "Board game", "description": "Ma sói thứ 6"}, repo=r)
        self.assertEqual(out["status"], C.CLUB_ACTIVE)
        self.assertEqual(r.members(out["name"]), [])                      # HR khong co ho so: khong thanh vien

    def test_club_page_and_archive(self):
        r = FakeRepo()
        c = club(r)
        S.create(LAN, {"body": "ảnh chạy", "club": c}, [{"name": "a.jpg", "content": b"x"}], repo=r)
        S.create(KHANG, {"club": c, "event_title": "Chạy 5km", "event_start": "2026-10-11T06:00"}, repo=r)
        ctx = CL.club_page(ANH, "chay-bo", repo=r)
        self.assertEqual((len(ctx["items"]), ctx["can_post"], ctx["can_event"]), (2, False, False))
        self.assertEqual(len(ctx["upcoming"]), 1)
        self.assertTrue(CL.club_page(KHANG, "chay-bo", repo=r)["can_event"])
        self.assertEqual(len(CL.club_page(ANH, "chay-bo", "anh", repo=r)["photos"]), 1)
        self.assertEqual(len(CL.club_page(ANH, "chay-bo", "thanh-vien", repo=r)["members"]), 2)
        CL.set_status(HR, c, False, repo=r)
        with self.assertRaises(D.NotFound):
            CL.club_page(ANH, "chay-bo", repo=r)
        with self.assertRaises(D.NotFound):
            CL.club_page(ANH, "khong-co", repo=r)


class TestModeration(unittest.TestCase):
    def test_page_groups_reports_and_lists_clubs(self):
        r = FakeRepo()
        p = S.create(LAN, {"body": "x"}, repo=r)["name"]
        S.report(KHANG, p, "Sai", repo=r)
        S.report(ANH, p, "", repo=r)
        with self.assertRaises(D.Forbidden):
            M.page(LAN, repo=r)
        ctx = M.page(HR, repo=r)
        self.assertEqual((ctx["n_reports"], len(ctx["groups"][0]["reports"])), (1, 2))
        S.dismiss_reports(HR, p, repo=r)
        self.assertEqual(M.page(HR, repo=r)["groups"], [])
        CL.propose(LAN, {"club_name": "Cầu lông", "description": "x"}, repo=r)
        club(r, "Bóng đá")
        ctx = M.page(HR, "clb", repo=r)
        self.assertEqual(([c["title"] for c in ctx["pending"]], [c["title"] for c in ctx["active"]]),
                         (["Cầu lông"], ["Bóng đá"]))
        self.assertEqual(ctx["pending"][0]["proposer"], "Nguyễn Thị Lan")


class TestDomain(unittest.TestCase):
    def test_who_tip_caps_the_list(self):
        users = ["u%d" % i for i in range(13)] + ["u1", LAN]
        tip = D.who_tip(users, LAN, {"u0": "An"})
        self.assertTrue(tip.startswith("Bạn, An, u1"))
        self.assertTrue(tip.endswith("và 4 người khác"))

    def test_helpers(self):
        self.assertEqual(D.slugify("Game & Board game Đà Nẵng"), "game-board-game-da-nang")
        self.assertEqual(D.clean_text("  a  \n\n\n\n b ", 100), "a\n\nb")
        self.assertEqual(D.event_short(dt.datetime(2026, 10, 9, 19, 0)), "T6 09/10")
        self.assertEqual(D.event_state(dt.datetime(2026, 10, 5, 7, 0), NOW), "live")
        self.assertEqual(D.event_state(dt.datetime(2026, 10, 5, 5, 0), NOW), "past")
        with self.assertRaises(D.SocialError):
            D.parse_event({"event_title": "x", "event_start": "2027-12-01 06:00"}, NOW)


class TestTemplates(unittest.TestCase):
    """The bai ve that bang Jinja (escape noi dung nguoi dung nhap)."""

    def test_user_text_is_escaped(self):
        try:
            import jinja2
        except ImportError:
            self.skipTest("jinja2")
        app = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(app))   # nhu Frappe: KHONG autoescape
        r = FakeRepo()
        r.names[LAN] = "<b>Lan</b>"
        c = club(r, "<i>CLB</i>")
        card = S.create(LAN, {"body": "<script>alert(1)</script>", "club": c, "mentions": [KHANG]}, repo=r)
        html = env.get_template("templates/includes/social/items.html").render(items=[dict(card, type="post")])
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<b>Lan</b>", html)
        self.assertNotIn("<i>CLB</i>", html)
        view = engine.add(KHANG, card["name"], "<img src=x onerror=alert(1)>", repo=r, subject=CS.SocialSubject(r))
        view["moment"] = False
        html = env.get_template("templates/includes/social/comments.html").render(cm=view)
        self.assertNotIn("<img src=x", html)


if __name__ == "__main__":
    unittest.main()
