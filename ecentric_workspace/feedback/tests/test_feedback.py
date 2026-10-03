# Copyright (c) 2026, eCentric and contributors
"""Gop y cong ty - chay THAT domain / service / handler_service / notify / digest tren repo gia,
va render 4 trang www bang jinja2 tu context that cua service (khong can bench).

    python -m unittest ecentric_workspace.feedback.tests.test_feedback

Trong tam: AN DANH. Moi lop test "an danh" kiem ca context lan HTML ra trinh duyet cua NGUOI XU LY:
email / ho ten nguoi gui khong duoc xuat hien o bat cu dau.
"""
import ast
import copy
import datetime as dt
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
APP = os.path.join(ROOT, "ecentric_workspace")
sys.path.insert(0, ROOT)

from ecentric_workspace.approval_center.shared.workflow import business_hours as BH  # noqa: E402
from ecentric_workspace.feedback import constants as C  # noqa: E402
from ecentric_workspace.feedback import digest as DG  # noqa: E402
from ecentric_workspace.feedback import domain as D  # noqa: E402
from ecentric_workspace.feedback import handler_service as H  # noqa: E402
from ecentric_workspace.feedback import notify as N  # noqa: E402
from ecentric_workspace.feedback import service as S  # noqa: E402

LAN = "lan@ecentric.vn"         # nhan vien phong Van hanh - nguoi gui
TU = "tu@ecentric.vn"           # nhan vien khac
BOSS = "lam@ecentric.vn"        # phong Management - EC = nguoi xu ly
BOSS2 = "phuong@ecentric.vn"
ADMIN = "admin@ecentric.vn"     # System Manager, khong o Management
GUEST_ACC = "khach@x"           # co tai khoan, khong co ho so Employee
NAMES = {LAN: "Nguyễn Thị Lan", TU: "Phạm Tú", BOSS: "Lâm Nguyễn", BOSS2: "Phương Nguyễn", ADMIN: "Quản trị"}
FRI_4PM = dt.datetime(2026, 10, 2, 16, 0)        # thu Sau
PERIODS = BH.build_periods([{"weekday": w, "start_time": "09:00:00", "end_time": "18:00:00"}
                            for w in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")])


class Dup(Exception):
    pass


class FakeRepo:
    def __init__(self):
        self.clock = FRI_4PM
        self.emps = {LAN: "Van hanh - EC", TU: "Marketing - EC", BOSS: "Management - EC",
                     BOSS2: "Management - EC"}
        self.topics_ = [
            {"name": "van-phong", "topic_name": "Văn phòng & CSVC", "color": "teal", "icon": "building",
             "hint": "Chỗ ngồi", "enabled": 1},
            {"name": "cong-cu", "topic_name": "Công cụ / ERP", "color": "navy", "icon": "monitor", "hint": "",
             "enabled": 1},
            {"name": "cu", "topic_name": "Chủ đề cũ", "color": "gray", "icon": "dots", "hint": "", "enabled": 0},
        ]
        self.fbs = {}
        self.ident = {}            # name -> {user, sent_on, unread}
        self.msgs = []
        self.votes = []            # (name, user)
        self.files = {}            # (name, url) -> bytes
        self.enqueued = []
        self.notes = []            # thong bao da gui
        self.announced = []
        self.withdrawn = []
        self.digests = {}
        self.ai_calls = []
        self.ai_result = {"ok": True, "model": "kie-gemini", "data": {"topics": [
            {"name": "Chỗ gửi xe", "count": 2, "summary": "Hầm B2 hết chỗ sau 8h45."}]}}
        self.ai_runs = {}
        self.errors = []
        self.holidays = set()
        self.seq = 0
        self.dup_next = False

    # -- nguoi dung
    def handlers(self): return sorted(u for u, d in self.emps.items() if d == C.HANDLER_DEPARTMENT)
    def is_admin(self, user): return user == ADMIN
    def employee(self, user): return {"name": "EMP-" + user, "department": self.emps[user]} if user in self.emps else None
    def full_names(self, users): return {u: NAMES.get(u, u) for u in users or () if u}

    # -- chu de
    def topics(self, include_disabled=False):
        return [dict(t) for t in self.topics_ if include_disabled or t["enabled"]]

    # -- gop y
    def get(self, name):
        fb = self.fbs.get(name)
        return copy.deepcopy(fb) if fb else None

    def exists(self, name): return name in self.fbs

    def _match(self, fb, filters):
        for k, v in (filters or {}).items():
            cur = fb.get(k)
            if isinstance(v, list):
                op, arg = v
                if op == "in" and cur not in arg:
                    return False
                if op == "is" and (arg == "set") != bool(cur):
                    return False
                if op == "between" and not (arg[0] <= cur <= arg[1]):
                    return False
            elif (cur or 0) != v and cur != v:
                return False
        return True

    def list_rows(self, filters=None, order_by="creation desc", limit=0, fields=None):
        rows = [copy.deepcopy(f) for f in self.fbs.values() if self._match(f, filters)]
        rows.sort(key=lambda r: r["creation"], reverse="desc" in order_by)
        return rows[:limit] if limit else rows

    def board_rows(self):
        keep = ("name", "topic", "status", "public_title", "public_answer", "public_on", "vote_count", "creation")
        return [{k: f.get(k) for k in keep} for f in self.fbs.values() if f.get("is_public")]

    def rows_between(self, a, b):
        return self.list_rows({"creation": ["between", [a, b]], "is_spam": 0}, order_by="creation asc")

    def pending_notify(self): return self.list_rows({"notify_pending": 1})

    def clean_image(self, content, ext):
        if content == b"HONG":
            raise ValueError("anh hong")
        return content.replace(b"EXIF:Nguyen Thi Lan", b"")

    def open_unresponded(self):
        return [r for r in self.list_rows({"status": ["in", [C.ST_NEW, C.ST_VIEWING]]})
                if not r.get("responded_at") and r.get("due_at")]

    # -- danh tinh
    def my_names(self, user, limit=0):
        names = [n for n, i in sorted(self.ident.items(), key=lambda x: self.fbs[x[0]]["creation"], reverse=True)
                 if i["user"] == user]
        return names[:limit] if limit else names

    def my_unread(self, user): return {n: i["unread"] for n, i in self.ident.items() if i["user"] == user and i["unread"]}
    def sender_of(self, name): return (self.ident.get(name) or {}).get("user")
    def sent_today(self, user, day): return sum(1 for i in self.ident.values() if i["user"] == user and i["sent_on"] == day)
    def bump_unread(self, name): self.ident[name]["unread"] += 1
    def clear_unread(self, name): self.ident[name]["unread"] = 0

    # -- ghi
    def insert_feedback(self, values, user, day, files):
        self.seq += 1
        name = "GY-2026-%05d" % self.seq
        fb = dict(values, name=name, creation=self.clock, owner=C.SYSTEM_USER, attachments=[])
        for f in ("viewed_at", "viewed_by", "responded_at", "first_response_at", "closed_at", "reminded_soon_at",
                  "reminded_overdue_at", "duplicate_of", "public_title", "public_answer", "public_on",
                  "home_announcement", "submitter", "submitter_department", "pending_event"):
            fb.setdefault(f, None)
        fb.setdefault("is_public", 0)
        fb.setdefault("is_spam", 0)
        fb.setdefault("notify_pending", 0)
        for f in files:
            url = "/private/files/%s" % f["name"]
            self.files[(name, url)] = f["content"]
            fb["attachments"].append({"file_url": url, "file_name": f["name"], "file_size": f["size"]})
        self.fbs[name] = fb
        self.ident[name] = {"user": user, "sent_on": day, "unread": 0}
        return name

    def set_fields(self, name, values, by=None): self.fbs[name].update(values)

    def insert_message(self, values, by=None):
        m = dict({"from_status": None, "to_status": None, "from_topic": None, "to_topic": None, "body": None},
                 **values)
        m.update(name="MSG-%d" % len(self.msgs), creation=self.clock, owner=by or C.SYSTEM_USER)
        self.msgs.append(m)
        return m["name"]

    def messages(self, name): return [copy.deepcopy(m) for m in self.msgs if m["feedback"] == name]

    # -- +1
    def my_votes(self, user, names=None):
        return {n for n, u in self.votes if u == user and (names is None or n in names)}

    def find_vote(self, name, user): return "V" if (name, user) in self.votes else None

    def add_vote(self, name, user):
        if self.dup_next:
            self.dup_next = False
            raise Dup()
        self.votes.append((name, user))

    def remove_vote(self, vote): pass
    def set_vote_count(self, name, n): self.fbs[name]["vote_count"] = n
    def count_votes(self, name): return sum(1 for n, _ in self.votes if n == name)
    def is_duplicate(self, e): return isinstance(e, Dup)

    def file_content(self, name, url):
        c = self.files.get((name, url))
        return (url.rsplit("/", 1)[-1], c) if c is not None else None

    # -- lich
    def calendar(self): return (PERIODS, self.holidays, 9.0)
    def business_due(self, start, hours): return BH.calculate_business_due_at(start, hours, PERIODS, self.holidays)
    def business_seconds(self, a, b): return BH.business_seconds_between(a, b, PERIODS, self.holidays)

    # -- ban tin
    def digest(self, month): return copy.deepcopy(self.digests.get(month))

    def save_digest(self, month, values):
        self.digests.setdefault(month, {"name": month, "month": month, "sent_on": None}).update(values)

    def ai_runs_today(self, user, day): return self.ai_runs.get((user, day), 0)
    def bump_ai_runs(self, user, day): self.ai_runs[(user, day)] = self.ai_runs_today(user, day) + 1

    def generate_ai(self, prompt, schema):
        self.ai_calls.append(prompt)
        return self.ai_result

    # -- khac
    def today(self): return self.clock.date()
    def now(self): return self.clock
    def commit(self): pass
    def log_error(self, title): self.errors.append(title)
    def log_message(self, title, msg): self.errors.append(title)
    def announce(self, name, title, summary, link, start, end):
        self.announced.append((name, title, summary, link, start, end))
        return "ANN-" + name

    def withdraw(self, name): self.withdrawn.append(name)

    def notify(self, event, recipient, title, message, url, name, dedupe_key, actor=None):
        if any(n["key"] == dedupe_key for n in self.notes):
            return {"duplicate": True}
        self.notes.append({"event": event, "to": recipient, "title": title, "message": message, "url": url,
                           "key": dedupe_key, "actor": actor or C.SYSTEM_USER})

    def enqueue(self, method, **kw): self.enqueued.append((method, kw))

    def run_jobs(self):
        """Chay cac job da xep (nhu worker that) - notify chay DUOI SYSTEM_USER."""
        jobs, self.enqueued = self.enqueued, []
        for method, kw in jobs:
            fn = getattr(N, method.rsplit(".", 1)[-1])
            fn(repo=self, **kw)


def submit(r, user=LAN, anon=False, **kw):
    data = {"title": "Điều hoà phòng họp tầng 3 kêu to", "body": "Họp online phải tắt điều hoà.",
            "topic": "van-phong", "kind": "Phản ánh", "is_anonymous": 1 if anon else 0}
    data.update(kw)
    return S.submit(user, data, repo=r)["name"]


def blob(ctx):
    return json.dumps(ctx, default=str, ensure_ascii=False)


# ====================================================================== domain =====
class TestDomain(unittest.TestCase):
    def test_normalize_requires_fields(self):
        topics = {"van-phong": {}}
        with self.assertRaises(D.Invalid) as e:
            D.normalize_submission({"title": " ", "body": "", "topic": "x", "kind": "Khác"}, topics, 0)
        self.assertEqual(len(e.exception.errors), 4)
        ok = D.normalize_submission({"title": "  a   b ", "body": "x\r\n\n\n\ny", "topic": "van-phong",
                                     "is_anonymous": "true"}, topics, 4)
        self.assertEqual((ok["title"], ok["body"], ok["is_anonymous"], ok["kind"]), ("a b", "x\n\ny", 1, "Đề xuất"))

    def test_daily_limit_counts_every_submission(self):
        with self.assertRaises(D.Invalid) as e:
            D.normalize_submission({"title": "a", "body": "b", "topic": "t"}, {"t": {}}, C.DAILY_LIMIT)
        self.assertIn("đủ 5 góp ý", e.exception.errors[0])

    def test_files(self):
        self.assertEqual(D.check_files([{"name": "a.png", "size": 10}]), [])
        self.assertTrue(D.check_files([{"name": "a.exe", "size": 10}]))
        self.assertTrue(D.check_files([{"name": "a.pdf", "size": C.FILE_MAX_BYTES + 1}]))
        self.assertTrue(D.check_files([{"name": "a.pdf", "size": 0}]))
        self.assertTrue(D.check_files([{"name": "%d.pdf" % i, "size": 1} for i in range(C.MAX_FILES + 1)]))
        big = [{"name": "%d.pdf" % i, "size": 4 * 1024 * 1024} for i in range(4)]     # 16 MB > 12 MB
        self.assertIn("Tổng dung lượng", " ".join(D.check_files(big)))

    def test_handler_status_rules(self):
        self.assertEqual(D.check_handler_status(C.ST_NEW, C.ST_VIEWING, ""), [])
        self.assertTrue(D.check_handler_status(C.ST_VIEWING, C.ST_ANSWERED, " "))
        self.assertTrue(D.check_handler_status(C.ST_VIEWING, C.ST_DECLINED, ""))
        self.assertEqual(D.check_handler_status(C.ST_VIEWING, C.ST_DONE, ""), [])
        self.assertTrue(D.check_handler_status(C.ST_VIEWING, C.ST_NEW, "x"), "Moi chi he thong dat")
        self.assertNotIn("Sẽ làm", C.STATUSES, "PO bo trang thai Se lam 04/10")

    def test_clock_stops_only_on_response(self):
        self.assertFalse(D.stops_clock(C.ST_VIEWING, False), "Dang xem khong dung dong ho")
        self.assertTrue(D.stops_clock(None, True))
        self.assertTrue(D.stops_clock(C.ST_DONE, False))

    def test_reopen_once(self):
        self.assertTrue(D.can_reopen(C.ST_DONE, 0))
        self.assertFalse(D.can_reopen(C.ST_DONE, 1))
        self.assertFalse(D.can_reopen(C.ST_VIEWING, 0))

    def test_sla_state(self):
        fb = {"status": C.ST_NEW, "due_at": dt.datetime(2026, 10, 9, 16)}
        self.assertEqual(D.sla_state(fb, None, -2 * 9 * 3600 - 10, 9)["short"], "Quá 2 ngày")
        self.assertEqual(D.sla_state(fb, None, -3600 * 3, 9)["short"], "Quá 3 giờ")
        self.assertEqual(D.sla_state(fb, None, 6 * 3600, 9)["key"], "soon")
        self.assertEqual(D.sla_state(fb, None, 30 * 3600, 9)["short"], "Hạn 09/10")
        self.assertEqual(D.sla_state(dict(fb, responded_at=1), None, -99999, 9)["key"], "done")

    def test_anonymous_time_shows_date_only(self):
        t = dt.datetime(2026, 10, 2, 16, 37)
        self.assertEqual(D.fmt_time(t, anonymous=True), "02/10")
        self.assertEqual(D.fmt_time(t), "16:37 02/10")

    def test_board_card_has_only_public_fields(self):
        card = D.board_card({"name": "G1", "status": C.ST_DONE, "topic": "t", "public_title": "Công khai",
                             "public_answer": "Đã làm", "vote_count": 10, "body": "BÍ MẬT",
                             "submitter": LAN}, {}, set())
        self.assertNotIn("BÍ MẬT", blob(card))
        self.assertNotIn(LAN, blob(card))
        self.assertTrue(card["hot"])

    def test_month_helpers(self):
        self.assertEqual(D.month_range("2026-12"), (dt.date(2026, 12, 1), dt.date(2027, 1, 1)))
        self.assertIsNone(D.month_range("2026-13"))
        self.assertIsNone(D.month_range("x"))
        self.assertEqual(D.prev_month(dt.date(2026, 1, 15)), "2025-12")

    def test_clean_hot(self):
        out = D.clean_hot({"topics": [{"name": " Gửi   xe ", "count": "3", "summary": "a"}, {"name": ""}, "x",
                                      {"name": "b", "count": "?"}]})
        self.assertEqual(out, [{"name": "Gửi xe", "count": 3, "summary": "a"}, {"name": "b", "count": 0, "summary": ""}])


# ====================================================================== gui =========
class TestSubmit(unittest.TestCase):
    def test_named_submission(self):
        r = FakeRepo()
        name = submit(r)
        fb = r.fbs[name]
        self.assertEqual((fb["status"], fb["submitter"], fb["submitter_department"]), (C.ST_NEW, LAN, "Van hanh - EC"))
        self.assertEqual(r.sender_of(name), LAN)
        self.assertEqual(r.enqueued[0][0], "ecentric_workspace.feedback.notify.new_feedback")

    def test_anonymous_submission_stores_no_identity_on_feedback(self):
        r = FakeRepo()
        name = submit(r, anon=True)
        fb = r.fbs[name]
        self.assertEqual(fb["is_anonymous"], 1)
        self.assertIsNone(fb["submitter"])
        self.assertIsNone(fb["submitter_department"])
        self.assertNotIn(LAN, blob(fb))
        self.assertEqual(r.sender_of(name), LAN, "danh tinh nam o bang khoa rieng")

    def test_due_is_five_working_days(self):
        r = FakeRepo()
        name = submit(r)                              # thu Sau 16:00 -> thu Sau tuan sau 16:00
        self.assertEqual(r.fbs[name]["due_at"], dt.datetime(2026, 10, 9, 16, 0))
        r.holidays = {dt.date(2026, 10, 5)}           # nghi thu Hai -> lui mot ngay
        name = submit(r)
        self.assertEqual(r.fbs[name]["due_at"], dt.datetime(2026, 10, 12, 16, 0))

    def test_limits_and_access(self):
        r = FakeRepo()
        for _ in range(C.DAILY_LIMIT):
            submit(r, anon=True)
        with self.assertRaises(S.FeedbackError):
            submit(r)                                 # an danh van tinh vao 5 luot
        submit(r, TU)                                 # nguoi khac van gui duoc
        with self.assertRaises(S.Forbidden):
            submit(r, GUEST_ACC)
        with self.assertRaises(S.Forbidden):
            submit(r, "Guest")
        with self.assertRaises(S.FeedbackError):
            submit(r, TU, topic="cu")                 # chu de da tat

    def test_files_go_through(self):
        r = FakeRepo()
        out = S.submit(LAN, {"title": "a", "body": "b", "topic": "van-phong"},
                       [{"name": "anh.png", "content": b"x" * 10, "size": 10}], repo=r)
        fb = r.fbs[out["name"]]
        self.assertEqual(fb["attachments"][0]["file_name"], "anh.png")
        self.assertEqual(out["url"], "/gop-y/" + out["name"])
        with self.assertRaises(S.FeedbackError):
            S.submit(LAN, {"title": "a", "body": "b", "topic": "van-phong"},
                     [{"name": "x.exe", "content": b"x", "size": 1}], repo=r)


class TestAnonymousExtras(unittest.TestCase):
    def test_anonymous_due_rounded_to_end_of_day(self):
        r = FakeRepo()
        r.clock = dt.datetime(2026, 10, 2, 10, 37)
        self.assertEqual(r.fbs[submit(r, anon=True)]["due_at"], dt.datetime(2026, 10, 9, 18, 0))
        self.assertEqual(r.fbs[submit(r, TU)]["due_at"], dt.datetime(2026, 10, 9, 10, 37))

    def test_anonymous_files_only_images_renamed_and_cleaned(self):
        r = FakeRepo()
        base = {"title": "a", "body": "b", "topic": "van-phong", "is_anonymous": 1}
        with self.assertRaises(S.FeedbackError) as e:
            S.submit(LAN, base, [{"name": "bao-cao.docx", "content": b"x", "size": 1}], repo=r)
        self.assertIn("chỉ đính kèm được ảnh", str(e.exception))
        with self.assertRaises(S.FeedbackError):
            S.submit(LAN, base, [{"name": "a.png", "content": b"HONG", "size": 4}], repo=r)
        out = S.submit(LAN, base, [{"name": "Screenshot lan.nguyen.JPEG", "content": b"IMG EXIF:Nguyen Thi Lan",
                                    "size": 23}], repo=r)
        att = r.fbs[out["name"]]["attachments"][0]
        self.assertEqual(att["file_name"], "anh-1.jpg")
        self.assertNotIn(b"Nguyen", r.files[(out["name"], att["file_url"])])
        ctx = H.inbox(BOSS, repo=r, sel=out["name"])
        self.assertNotIn("lan.nguyen", blob(ctx))

    def test_pending_keeps_first_event(self):
        r = FakeRepo()
        name = submit(r, anon=True)
        S.send_message(LAN, name, "thêm", repo=r)
        self.assertEqual(r.fbs[name]["pending_event"], C.PENDING_NEW, "chua bao gop y moi -> giu 'new'")
        N.remind(repo=r)
        self.assertEqual(r.fbs[name]["notify_pending"], 0)
        S.send_message(LAN, name, "thêm nữa", repo=r)
        self.assertEqual(r.fbs[name]["pending_event"], C.PENDING_REPLY)
        self.assertEqual(r.enqueued, [])

    def test_summarize_failure_keeps_quota(self):
        r = FakeRepo()
        submit(r)

        def boom(prompt, schema):
            raise RuntimeError("kie")
        r.generate_ai = boom
        with self.assertRaises(RuntimeError):
            H.summarize_now(BOSS, "2026-10", repo=r)
        self.assertEqual(r.ai_runs_today(BOSS, r.today()), 0)


# ====================================================================== an danh =====
class TestAnonymity(unittest.TestCase):
    """Nguoi xu ly khong bao gio thay ai gui gop y an danh - context, thong bao, HTML."""

    def setUp(self):
        self.r = FakeRepo()
        self.name = submit(self.r, anon=True, title="Wifi tầng 4 rớt")
        self.assertEqual(self.r.enqueued, [], "an danh: khong bao ngay")
        self.r.clock += dt.timedelta(minutes=37)
        N.remind(repo=self.r)                         # dot bao moi gio

    def test_inbox_context_has_no_identity(self):
        ctx = H.inbox(BOSS, repo=self.r, sel=self.name)
        txt = blob(ctx)
        for leak in (LAN, NAMES[LAN], "Van hanh"):
            self.assertNotIn(leak, txt)
        self.assertEqual(ctx["selected"]["sender"], "Ẩn danh")
        self.assertEqual(ctx["items"][0]["who"], "Ẩn danh")

    def test_sender_messages_stay_anonymous(self):
        S.send_message(LAN, self.name, "Bổ sung: chiều nào cũng vậy", repo=self.r)
        msg = self.r.msgs[-1]
        self.assertIsNone(msg["author"])
        self.assertEqual(msg["owner"], C.SYSTEM_USER)
        ctx = H.inbox(BOSS, repo=self.r, sel=self.name)
        self.assertNotIn(LAN, blob(ctx))
        self.assertNotIn(NAMES[LAN], blob(ctx))
        self.assertNotIn(":", ctx["selected"]["thread"][-1]["when"], "an danh: khong hien gio phut")

    def test_new_feedback_notification_never_carries_sender(self):
        notes = [n for n in self.r.notes if n["key"].startswith("feedback_new|")]
        self.assertEqual(sorted(n["to"] for n in notes), [BOSS, BOSS2])
        for n in notes:
            self.assertEqual(n["actor"], C.SYSTEM_USER)
            self.assertNotIn(LAN, blob(n))
            self.assertNotIn(NAMES[LAN], blob(n))
            self.assertTrue(n["url"].startswith("/gop-y/xu-ly?gy="), "khong bao gio /app")

    def test_rendered_inbox_has_no_identity(self):
        out = _render("xu_ly", H.inbox(BOSS, repo=self.r, sel=self.name))
        self.assertNotIn(LAN, out)
        self.assertNotIn(NAMES[LAN], out)
        self.assertIn("Ẩn danh", out)

    def test_named_feedback_shows_name_to_handler(self):
        named = submit(self.r, TU)
        ctx = H.inbox(BOSS, repo=self.r, sel=named)
        self.assertEqual(ctx["selected"]["sender"], NAMES[TU])

    def test_overview_and_digest_have_no_identity(self):
        ctx = H.overview(BOSS, repo=self.r)
        self.assertNotIn(LAN, blob(ctx))
        DG.build(self.r, "2026-10")
        self.assertNotIn(LAN, self.r.ai_calls[-1])
        self.assertNotIn(NAMES[LAN], self.r.ai_calls[-1])


# ====================================================================== xu ly =======
class TestHandling(unittest.TestCase):
    def setUp(self):
        self.r = FakeRepo()
        self.name = submit(self.r, anon=True)
        N.remind(repo=self.r)

    def test_only_handlers(self):
        for fn in (lambda u: H.inbox(u, repo=self.r), lambda u: H.overview(u, repo=self.r),
                   lambda u: H.act(u, self.name, C.ST_DONE, repo=self.r)):
            with self.assertRaises(S.Forbidden):
                fn(TU)
        self.assertTrue(H.inbox(ADMIN, repo=self.r)["items"], "quan tri xem duoc hop xu ly")

    def test_viewing_does_not_stop_the_clock(self):
        H.mark_viewing(BOSS, self.name, repo=self.r)
        fb = self.r.fbs[self.name]
        self.assertEqual((fb["status"], fb["viewed_by"]), (C.ST_VIEWING, BOSS))
        self.assertIsNone(fb["responded_at"])
        self.assertEqual(self.r.ident[self.name]["unread"], 1)
        self.assertEqual(H.mark_viewing(BOSS2, self.name, repo=self.r)["changed"], False)

    def test_answer_requires_message_and_stops_clock(self):
        with self.assertRaises(S.FeedbackError):
            H.act(BOSS, self.name, C.ST_ANSWERED, "", repo=self.r)
        with self.assertRaises(S.FeedbackError):
            H.act(BOSS, self.name, C.ST_DECLINED, "  ", repo=self.r)
        self.r.clock += dt.timedelta(hours=2)
        H.act(BOSS, self.name, C.ST_ANSWERED, "Đã gọi bảo trì.", repo=self.r)
        fb = self.r.fbs[self.name]
        self.assertEqual(fb["status"], C.ST_ANSWERED)
        self.assertEqual(fb["responded_at"], self.r.clock)
        self.assertEqual(fb["first_response_at"], self.r.clock)
        self.assertEqual(fb["closed_at"], self.r.clock)
        self.r.run_jobs()
        upd = [n for n in self.r.notes if n["key"].startswith("feedback_upd|")]
        self.assertEqual(upd[-1]["to"], LAN)
        self.assertEqual(upd[-1]["event"], C.EV_SENDER)
        self.assertEqual(upd[-1]["title"], "Góp ý của bạn đã có trả lời")
        self.assertTrue(upd[-1]["url"].endswith("/gop-y/" + self.name))

    def test_reply_alone_stops_clock_and_notifies(self):
        H.act(BOSS, self.name, "", "Mình đang kiểm tra.", repo=self.r)
        fb = self.r.fbs[self.name]
        self.assertEqual(fb["status"], C.ST_VIEWING, "tra loi gop y Moi = da xem")
        self.assertIsNotNone(fb["responded_at"])
        self.r.run_jobs()
        self.assertEqual(self.r.notes[-1]["title"], "Có trả lời mới cho góp ý của bạn")

    def test_internal_note_hidden_from_sender(self):
        H.act(BOSS, self.name, C.ST_DONE, "GHI CHÚ NỘI BỘ: hỏi kế toán", internal=True, repo=self.r)
        fb = self.r.fbs[self.name]
        self.assertEqual(fb["status"], C.ST_NEW, "ghi chu khong doi trang thai")
        self.assertIsNone(fb["responded_at"], "ghi chu khong phai phan hoi")
        self.assertEqual(self.r.ident[self.name]["unread"], 0, "nguoi gui khong duoc bao")
        ctx = S.detail(LAN, self.name, repo=self.r)
        self.assertNotIn("GHI CHÚ NỘI BỘ", blob(ctx))
        self.assertNotIn("GHI CHÚ NỘI BỘ", _render("chi_tiet", ctx))
        self.assertIn("GHI CHÚ NỘI BỘ", blob(H.inbox(BOSS, repo=self.r, sel=self.name)))

    def test_detail_only_for_sender(self):
        with self.assertRaises(S.Forbidden):
            S.detail(TU, self.name, repo=self.r)
        with self.assertRaises(S.Forbidden):
            S.detail(BOSS, self.name, repo=self.r)    # trang chuyen nguoi xu ly sang hop xu ly
        with self.assertRaises(S.NotFound):
            S.detail(LAN, "GY-2026-99999", repo=self.r)

    def test_mark_read_clears_unread(self):
        H.mark_viewing(BOSS, self.name, repo=self.r)
        self.assertEqual(S.index_page(LAN, repo=self.r)["unread_total"], 1)
        S.mark_read(LAN, self.name, repo=self.r)
        self.assertEqual(self.r.ident[self.name]["unread"], 0)
        with self.assertRaises(S.Forbidden):
            S.mark_read(TU, self.name, repo=self.r)

    def test_reopen_once_with_new_due(self):
        H.act(BOSS, self.name, C.ST_DONE, "Đã sửa.", repo=self.r)
        with self.assertRaises(S.FeedbackError):
            S.send_message(LAN, self.name, "còn kêu", repo=self.r)
        with self.assertRaises(S.FeedbackError):
            S.reopen(LAN, self.name, "  ", repo=self.r)
        self.r.clock = dt.datetime(2026, 10, 12, 10, 0)
        S.reopen(LAN, self.name, "Vẫn còn kêu.", repo=self.r)
        fb = self.r.fbs[self.name]
        self.assertEqual((fb["status"], fb["reopen_count"], fb["responded_at"], fb["closed_at"]),
                         (C.ST_NEW, 1, None, None))
        self.assertEqual(fb["due_at"], dt.datetime(2026, 10, 19, 18, 0), "an danh: cuoi ngay")
        self.assertIsNotNone(fb["first_response_at"], "lan phan hoi dau tien giu nguyen cho thong ke")
        H.act(BOSS, self.name, C.ST_DONE, "Đã thay máy.", repo=self.r)
        with self.assertRaises(S.FeedbackError):
            S.reopen(LAN, self.name, "lần hai", repo=self.r)
        with self.assertRaises(S.Forbidden):
            S.reopen(TU, self.name, "x", repo=self.r)

    def test_topic_change(self):
        H.set_topic(BOSS, self.name, "cong-cu", repo=self.r)
        self.assertEqual(self.r.fbs[self.name]["topic"], "cong-cu")
        self.assertEqual(self.r.msgs[-1]["to_topic"], "Công cụ / ERP")
        with self.assertRaises(S.FeedbackError):
            H.set_topic(BOSS, self.name, "cu", repo=self.r)

    def test_duplicate_and_spam(self):
        orig = submit(self.r, TU)
        H.publish(BOSS, orig, True, "Điều hoà ồn", "", repo=self.r)
        H.mark_duplicate(BOSS, self.name, of=orig.lower(), repo=self.r)
        fb = self.r.fbs[self.name]
        self.assertEqual((fb["status"], fb["duplicate_of"]), (C.ST_DECLINED, orig))
        self.assertIn("bảng chung", self.r.msgs[-2]["body"])
        other = submit(self.r, TU)
        H.mark_duplicate(BOSS, other, spam=1, repo=self.r)
        self.assertEqual((self.r.fbs[other]["status"], self.r.fbs[other]["is_spam"]), (C.ST_DECLINED, 1))
        self.assertIn(other, [i["name"] for i in H.inbox(BOSS, "da-dong", repo=self.r)["items"]],
                      "spam van tim lai duoc")
        self.assertEqual(H.period(self.r, "2026-10", self.r.now())[0]["total"], 2, "spam khong tinh thong ke")
        with self.assertRaises(S.FeedbackError):
            H.mark_duplicate(BOSS, other, of=other, repo=self.r)
        with self.assertRaises(S.FeedbackError):
            H.mark_duplicate(BOSS, other, repo=self.r)

    def test_inbox_buckets(self):
        late = self.name
        soon = submit(self.r, TU)
        self.r.clock = dt.datetime(2026, 10, 9, 10, 0)          # name: han 09/10 16:00 -> con 6 gio
        fresh = submit(self.r, TU)
        self.r.clock = dt.datetime(2026, 10, 12, 10, 0)         # qua han 1 ngay
        H.act(BOSS, soon, C.ST_DONE, "", repo=self.r)
        ctx = H.inbox(BOSS, repo=self.r)
        self.assertEqual(ctx["counts"]["qua-han"], 1)
        self.assertEqual(ctx["counts"]["da-dong"], 1)
        self.assertEqual(ctx["counts"]["can-xu-ly"], 2)
        self.assertEqual({i["name"] for i in ctx["items"]}, {late, fresh})
        self.assertEqual([i["name"] for i in H.inbox(BOSS, "qua-han", repo=self.r)["items"]], [late])
        self.assertEqual([i["name"] for i in H.inbox(BOSS, "da-dong", repo=self.r)["items"]], [soon])
        self.assertEqual(H.inbox(BOSS, "tat-ca", q=fresh.lower(), repo=self.r)["items"][0]["name"], fresh)
        self.assertEqual(H.late_count(self.r), 1)


# ====================================================================== bang chung =
class TestBoard(unittest.TestCase):
    def setUp(self):
        self.r = FakeRepo()
        self.name = submit(self.r, anon=True, body="Chi tiết riêng: bàn số 12 cạnh cửa sổ")

    def test_only_published_and_only_public_fields(self):
        self.assertEqual(S.board(TU, repo=self.r)["cards"], [])
        with self.assertRaises(S.FeedbackError):
            H.publish(BOSS, self.name, True, "", repo=self.r)
        H.publish(BOSS, self.name, True, "Điều hoà phòng họp ồn", "Đã gọi bảo trì", repo=self.r)
        ctx = S.index_page(TU, tab="bang-chung", repo=self.r)
        self.assertEqual(len(ctx["cards"]), 1)
        out = _render("index", ctx)
        self.assertIn("Điều hoà phòng họp ồn", out)
        self.assertNotIn("bàn số 12", out)
        self.assertNotIn(LAN, out)
        H.publish(BOSS, self.name, False, repo=self.r)
        self.assertEqual(S.board(TU, repo=self.r)["cards"], [])

    def test_vote_toggle(self):
        with self.assertRaises(S.Forbidden):
            S.toggle_vote(TU, self.name, repo=self.r)
        H.publish(BOSS, self.name, True, "T", "", repo=self.r)
        d = S.toggle_vote(TU, self.name, repo=self.r)
        self.assertEqual((d["voted"], d["votes"]), (True, 1))
        self.assertEqual(self.r.fbs[self.name]["vote_count"], 1)
        self.r.votes.remove((self.name, TU))          # repo gia: remove_vote khong biet ten dong
        d = S.toggle_vote(TU, self.name, repo=self.r)
        self.assertEqual((d["voted"], d["votes"]), (True, 1))
        self.r.dup_next = True                        # bam hai tab cung luc: dong kia da co
        self.r.votes.remove((self.name, TU))
        d = S.toggle_vote(TU, self.name, repo=self.r)
        self.assertTrue(d["voted"])
        with self.assertRaises(S.Forbidden):
            S.toggle_vote(GUEST_ACC, self.name, repo=self.r)

    def test_hot_and_sort(self):
        other = submit(self.r, TU)
        H.publish(BOSS, self.name, True, "A", "", repo=self.r)
        H.publish(BOSS, other, True, "B", "", repo=self.r)
        self.r.votes = [(other, "u%d@x" % i) for i in range(C.HOT_VOTES)]
        self.r.fbs[other]["vote_count"] = C.HOT_VOTES
        cards = S.board(TU, repo=self.r)["cards"]
        self.assertEqual([c["title"] for c in cards], ["B", "A"])
        self.assertTrue(cards[0]["hot"])
        self.assertEqual(S.board(TU, "nhieu-nhat", "da-lam", repo=self.r)["cards"], [])


# ====================================================================== popup =======
class TestPopup(unittest.TestCase):
    def test_done_and_public_goes_to_homepage(self):
        r = FakeRepo()
        name = submit(r, anon=True)
        H.act(BOSS, name, C.ST_DONE, "Đã làm", repo=r)
        self.assertEqual(r.announced, [], "chua cong khai -> chua len popup")
        H.publish(BOSS, name, True, "Thêm chỗ gửi xe", "Thuê thêm 15 chỗ B3", repo=r)
        ann = r.announced[-1]
        self.assertEqual(ann[1], C.POPUP_PREFIX + "Thêm chỗ gửi xe")
        self.assertEqual(ann[3], "/gop-y?tab=bang-chung#gy-" + name)
        self.assertEqual((ann[5] - ann[4]).days, C.POPUP_DAYS - 1)
        self.assertEqual(r.fbs[name]["home_announcement"], "ANN-" + name)
        H.publish(BOSS, name, False, repo=r)
        self.assertEqual(r.withdrawn, [name])
        H.publish(BOSS, name, True, "Thêm chỗ gửi xe", "", repo=r)
        H.act(BOSS, name, C.ST_ANSWERED, "Đổi ý", repo=r)
        self.assertEqual(r.withdrawn, [name, name], "khong con Da lam -> rut popup")

    def test_reopen_withdraws_popup(self):
        r = FakeRepo()
        name = submit(r)
        H.act(BOSS, name, C.ST_DONE, "", repo=r)
        H.publish(BOSS, name, True, "T", "", repo=r)
        S.reopen(LAN, name, "Chưa ổn", repo=r)
        self.assertIn(name, r.withdrawn)


# ====================================================================== nhac + ban tin
class TestJobs(unittest.TestCase):
    def test_remind_once_per_kind(self):
        r = FakeRepo()
        name = submit(r, anon=True)
        self.assertEqual(N.remind(repo=r)["pending"], 1)
        r.clock = dt.datetime(2026, 10, 9, 10, 0)     # han an danh 09/10 18:00 -> con 8 gio
        out = N.remind(repo=r)
        self.assertEqual(out, {"soon": 1, "late": 0, "pending": 0})
        self.assertEqual(N.remind(repo=r), {"soon": 0, "late": 0, "pending": 0})
        r.clock = dt.datetime(2026, 10, 12, 9, 30)    # qua han
        self.assertEqual(N.remind(repo=r), {"soon": 0, "late": 1, "pending": 0})
        self.assertEqual(N.remind(repo=r), {"soon": 0, "late": 0, "pending": 0})
        late = [n for n in r.notes if n["event"] == C.EV_OVERDUE]
        self.assertEqual(sorted(n["to"] for n in late), [BOSS, BOSS2])
        self.assertNotIn(LAN, blob(r.notes))
        H.act(BOSS, name, "", "Đang xử lý", repo=r)
        self.assertEqual(N.remind(repo=r), {"soon": 0, "late": 0, "pending": 0}, "da phan hoi -> het nhac")

    def test_sender_wrote_goes_to_current_handler(self):
        r = FakeRepo()
        name = submit(r, anon=True)
        N.remind(repo=r)
        H.mark_viewing(BOSS2, name, repo=r)
        S.send_message(LAN, name, "Bổ sung", repo=r)
        r.run_jobs()
        self.assertFalse(any(n["key"].startswith("feedback_wrote") for n in r.notes), "an danh: cho dot")
        N.remind(repo=r)
        last = r.notes[-1]
        self.assertEqual((last["to"], last["event"]), (BOSS2, C.EV_HANDLER_UPDATE))

    def test_stats(self):
        r = FakeRepo()
        a = submit(r)
        b = submit(r, TU)
        submit(r, TU, anon=True)
        r.clock = dt.datetime(2026, 10, 5, 10, 0)
        H.act(BOSS, a, C.ST_DONE, "", repo=r)          # 2 gio lam viec -> dung han
        r.clock = dt.datetime(2026, 10, 14, 10, 0)
        H.act(BOSS, b, C.ST_ANSWERED, "Trễ", repo=r)   # qua 09/10 16:00 -> tre
        st, rows = H.period(r, "2026-10", r.now())
        self.assertEqual((st["total"], st["anonymous"], st["judged"], st["on_time_pct"]), (3, 1, 3, 33))
        self.assertEqual(st["overdue_count"], 1)
        self.assertEqual(st["topics"][0]["total"], 3)
        self.assertEqual(st["avg_label"], "3,8 ngày", "(3 gio + 66 gio lam viec) / 2 / 9 gio moi ngay")
        ov = H.overview(BOSS, "2026-10", repo=r)
        self.assertEqual(ov["delta"], 3)
        self.assertEqual(len(ov["late"]), 1)

    def test_digest_sent_once_and_ai_failure_is_not_fatal(self):
        r = FakeRepo()
        submit(r, anon=True)
        r.clock = dt.datetime(2026, 11, 1, 8, 45)
        hot = DG.monthly(repo=r)
        self.assertEqual(hot[0]["name"], "Chỗ gửi xe")
        dg = r.digests["2026-10"]
        self.assertEqual(json.loads(dg["stats"])["total"], 1)
        sent = [n for n in r.notes if n["event"] == C.EV_DIGEST]
        self.assertEqual(sorted(n["to"] for n in sent), [BOSS, BOSS2])
        self.assertTrue(sent[0]["url"].startswith("/gop-y/tong-quan?thang=2026-10"))
        DG.monthly(repo=r)
        self.assertEqual(len([n for n in r.notes if n["event"] == C.EV_DIGEST]), 2, "khong gui lai")
        r.ai_result = {"ok": False, "error": "kie down"}
        self.assertEqual(DG.build(r, "2026-10"), [])
        self.assertEqual(json.loads(r.digests["2026-10"]["hot_topics"]), [])

    def test_summarize_now_limit(self):
        r = FakeRepo()
        submit(r)
        for _ in range(C.AI_MANUAL_DAILY_LIMIT):
            H.summarize_now(BOSS, "2026-10", repo=r)
        with self.assertRaises(S.FeedbackError):
            H.summarize_now(BOSS, "2026-10", repo=r)


# ====================================================================== tai tep =====
class TestDownload(unittest.TestCase):
    def test_only_sender_or_handler_and_only_own_files(self):
        r = FakeRepo()
        out = S.submit(LAN, {"title": "a", "body": "b", "topic": "van-phong"},
                       [{"name": "a.pdf", "content": b"%PDF", "size": 4}], repo=r)
        self.assertEqual(S.download(LAN, out["name"], 0, repo=r)[1], b"%PDF")
        self.assertEqual(S.download(BOSS, out["name"], "0", repo=r)[1], b"%PDF")
        with self.assertRaises(S.Forbidden):
            S.download(TU, out["name"], 0, repo=r)
        for bad in (1, -1, "x", None):
            with self.assertRaises(S.NotFound):
                S.download(LAN, out["name"], bad, repo=r)
        self.assertNotIn("file_url", blob(S.detail(LAN, out["name"], repo=r)), "trang khong in duong dan tep")


# ====================================================================== khop schema ==
class TestSchema(unittest.TestCase):
    def _dt(self, name):
        folder = name.lower().replace(" ", "_")
        with open(os.path.join(APP, "feedback", "doctype", folder, folder + ".json"), encoding="utf-8") as fh:
            return json.load(fh)

    def _opts(self, dt_name, field):
        f = next(x for x in self._dt(dt_name)["fields"] if x["fieldname"] == field)
        return f["options"].split("\n")

    def test_selects_match_constants(self):
        self.assertEqual(tuple(self._opts(C.FEEDBACK_DT, "status")), C.STATUSES)
        self.assertEqual(tuple(self._opts(C.FEEDBACK_DT, "kind")), C.KINDS)
        self.assertEqual(tuple(self._opts(C.MESSAGE_DT, "kind")), C.MSG_KINDS)
        self.assertEqual(set(self._opts(C.TOPIC_DT, "color")), set(C.COLORS))
        self.assertEqual(tuple(self._opts(C.TOPIC_DT, "icon")), C.ICONS)

    def test_private_doctypes(self):
        for name in (C.FEEDBACK_DT, C.MESSAGE_DT, C.IDENTITY_DT, C.VOTE_DT, C.DIGEST_DT, C.TOPIC_DT):
            perms = self._dt(name)["permissions"]
            self.assertEqual({p["role"] for p in perms}, {"System Manager"}, name)
        for name in (C.FEEDBACK_DT, C.MESSAGE_DT, C.IDENTITY_DT):
            d = self._dt(name)
            self.assertEqual(d.get("read_only"), 1, "%s: read_only -> Frappe khong phat list_update" % name)
            self.assertEqual(d.get("track_changes"), 0, name)
        self.assertEqual(self._dt(C.IDENTITY_DT).get("track_views"), 1)

    def test_listed_fields_exist(self):
        from ecentric_workspace.feedback import constants  # noqa: F401
        with open(os.path.join(APP, "feedback", "repository.py"), encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        lists = {t.targets[0].id: ast.literal_eval(t.value) for t in tree.body
                 if isinstance(t, ast.Assign) and getattr(t.targets[0], "id", "").endswith("_FIELDS")}
        have = {f["fieldname"] for f in self._dt(C.FEEDBACK_DT)["fields"]} | {"name", "creation"}
        for key, fields in lists.items():
            self.assertEqual(set(fields) - have, set(), key)

    def test_feedback_update_event_registered_without_teams(self):
        with open(os.path.join(APP, "notification_center", "events.py"), encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        vals = {t.targets[0].id: t.value for t in tree.body if isinstance(t, ast.Assign)
                and isinstance(t.targets[0], ast.Name)}
        self.assertIn(C.EV_SENDER, ast.literal_eval(vals["EVENT_TYPES"]))
        self.assertIn(C.EV_SENDER, ast.literal_eval(vals["_DEFAULT_SEVERITY"]))
        self.assertIs(ast.literal_eval(vals["ROUTING_MATRIX"])[C.EV_SENDER]["teams"], False)
        events = ast.literal_eval(vals["EVENT_TYPES"])
        for ev in (C.EV_NEW, C.EV_DUE_SOON, C.EV_OVERDUE, C.EV_DIGEST, C.EV_HANDLER_UPDATE):
            self.assertIn(ev, events)

    def test_hooks_routes(self):
        with open(os.path.join(APP, "hooks.py"), encoding="utf-8") as fh:
            src = fh.read()
        i_static = src.index('"/gop-y/xu-ly"')
        i_code = src.index('"/gop-y/<code>"')
        self.assertLess(i_static, i_code, "route tinh phai dung truoc route <code>")
        self.assertIn('"ecentric_workspace.feedback.notify.remind"', src)
        self.assertIn('"ecentric_workspace.feedback.digest.monthly"', src)


# ====================================================================== trang www ====
class _NS(dict):
    __getattr__ = dict.get


def _env():
    try:
        import jinja2
    except ImportError:
        raise unittest.SkipTest("thieu jinja2")
    from jinja2.sandbox import SandboxedEnvironment
    base = ("<html><head><title>{% block title %}{% endblock %}</title>{% block style %}{% endblock %}</head>"
            "<body>{% block navbar %}NAVBAR{% endblock %}{% block content %}{% endblock %}"
            "{% block footer %}FOOTER{% endblock %}{% block script %}{% endblock %}</body></html>")
    loader = jinja2.ChoiceLoader([jinja2.DictLoader({"templates/base.html": base}), jinja2.FileSystemLoader(APP)])
    return SandboxedEnvironment(loader=loader, undefined=jinja2.StrictUndefined)


def _render(page, ctx):
    full = {"base_template_path": "templates/base.html", "gy_shell_mount": "<aside>MENU</aside>",
            "gy_topbar": "<div>TOPBAR</div>", "gy_css": "/a.css", "gy_js": "/a.js", "title": "T"}
    full.update(ctx)
    return _env().get_template("www/gop_y/%s.html" % page).render(**full)


EVIL = '<script>alert("x")</script>'


class TestPages(unittest.TestCase):
    def setUp(self):
        self.r = FakeRepo()
        self.name = submit(self.r, anon=True, title=EVIL, body=EVIL)

    def _clean(self, out):
        self.assertNotIn(EVIL, out)
        self.assertNotIn("NAVBAR", out)
        self.assertNotIn("FOOTER", out)
        self.assertIn("<aside>MENU</aside>", out)
        self.assertNotIn("/app/", out)

    def test_index_tabs(self):
        out = _render("index", S.index_page(LAN, repo=self.r))
        self._clean(out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn('name="topic" value="van-phong"', out)
        self.assertNotIn('value="cu"', out, "chu de da tat khong hien")
        self.assertIn("Nguyễn Thị Lan · Van hanh", out)
        self.assertIn("Còn <strong data-egy-left>4</strong>/5", out)
        self.assertNotIn("Hộp xử lý", out, "nhan vien khong thay nut hop xu ly")
        out = _render("index", S.index_page(BOSS, repo=self.r))
        self.assertIn('href="/gop-y/xu-ly"', out)
        out = _render("index", S.index_page(LAN, tab="cua-toi", repo=self.r))
        self._clean(out)
        self.assertIn('href="/gop-y/%s"' % self.name, out)
        out = _render("index", S.index_page(LAN, tab="bang-chung", repo=self.r))
        self.assertIn("Chưa có góp ý nào trên bảng chung", out)
        out = _render("index", S.index_page(GUEST_ACC, repo=self.r))
        self.assertIn("Chỉ nhân viên eCentric", out)

    def test_quota_exhausted_disables_submit(self):
        for _ in range(C.DAILY_LIMIT - 1):
            submit(self.r, anon=True)
        out = _render("index", S.index_page(LAN, repo=self.r))
        self.assertIn("data-egy-submit disabled", out)

    def test_detail(self):
        H.act(BOSS, self.name, C.ST_ANSWERED, "Trả lời " + EVIL, repo=self.r)
        out = _render("chi_tiet", S.detail(LAN, self.name, repo=self.r))
        self._clean(out)
        self.assertIn("Lâm Nguyễn", out)
        self.assertIn("Chưa ổn? Mở lại góp ý", out)
        self.assertIn("(ẩn danh với người xử lý)", out)
        named = submit(self.r, TU, body="NỘI DUNG GỐC của Tú")
        self.assertIn("NỘI DUNG GỐC của Tú", _render("chi_tiet", S.detail(TU, named, repo=self.r)))

    def test_disabled_topic_hidden_when_empty(self):
        ctx = H.inbox(BOSS, repo=self.r)
        self.assertNotIn("cu", [t["name"] for t in ctx["topics"]])
        self.r.fbs[self.name]["topic"] = "cu"
        self.assertIn("cu", [t["name"] for t in H.inbox(BOSS, repo=self.r)["topics"]])

    def test_inbox_and_overview(self):
        H.act(BOSS, self.name, "", "x", internal=True, repo=self.r)
        out = _render("xu_ly", H.inbox(BOSS, repo=self.r, sel=self.name))
        self._clean(out)
        self.assertIn('data-egy-handle="%s"' % self.name, out)
        self.assertIn('data-egy-opened="1"', out)
        self.assertNotIn('data-egy-opened', _render("xu_ly", H.inbox(BOSS, repo=self.r)),
                         "vao hop thu: dong dau tu chon khong bi danh dau Dang xem")
        self.assertIn("ghi chú nội bộ", out)
        out = _render("xu_ly", H.inbox(BOSS, "da-dong", repo=self.r))
        self.assertIn("Không có góp ý nào ở mục này", out)
        out = _render("tong_quan", H.overview(BOSS, repo=self.r))
        self._clean(out)
        self.assertIn("Tổng quan góp ý · Tháng 10/2026", out)
        DG.build(self.r, "2026-10")
        out = _render("tong_quan", H.overview(BOSS, "2026-10", repo=self.r))
        self.assertIn("Chỗ gửi xe", out)


if __name__ == "__main__":
    unittest.main()
