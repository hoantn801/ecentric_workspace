# Copyright (c) 2026, eCentric and contributors
"""Tin noi bo - chay THAT domain / service / editor_service / cover_ai / permissions tren repo
gia, va render 4 trang www bang jinja2 tu context that cua service (khong can bench).

    python -m unittest ecentric_workspace.internal_posts.tests.test_internal_posts
"""
import copy
import datetime as dt
import io
import json
import os
import re
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
APP = os.path.join(ROOT, "ecentric_workspace")
sys.path.insert(0, ROOT)

from ecentric_workspace.internal_posts import constants as C  # noqa: E402
from ecentric_workspace.internal_posts import domain as D  # noqa: E402
from ecentric_workspace.internal_posts import service as S  # noqa: E402
from ecentric_workspace.internal_posts import editor_service as E  # noqa: E402
from ecentric_workspace.internal_posts import cover_ai as AI  # noqa: E402

TODAY = dt.date(2026, 10, 1)
HR = "hr@x"
LAN = "lan@x"          # phong Van hanh
MINH = "minh@x"        # phong Kho (con cua Van hanh)
TU = "tu@x"            # phong Marketing
NOEMP = "khach@x"      # co tai khoan nhung khong co ho so Employee


class Doc(dict):
    """Gia frappe Document: doc.get / doc.x / doc.x = / doc.set(child, rows)."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            return None

    def __setattr__(self, k, v):
        self[k] = v

    def set(self, k, v):
        self[k] = v

    def as_dict(self):
        return dict(self)


class Dup(Exception):
    pass


class FakeRepo:
    def __init__(self):
        # cay phong: Tat ca(1-12) > Van hanh(2-7) > Kho(3-4); Marketing(8-9); Phong tat(10-11)
        self.tree = {
            "All Departments": (1, 12, "All Departments", 1, 0),
            "Van hanh - EC": (2, 7, "Vận hành", 1, 0),
            "Kho - EC": (3, 4, "Kho", 0, 0),
            "Giao van - EC": (5, 6, "Giao vận", 0, 0),
            "Marketing - EC": (8, 9, "Marketing", 0, 0),
            "Phong cu - EC": (10, 11, "Phòng cũ", 0, 1),
        }
        self.emps = [{"user": HR, "lft": 8}, {"user": LAN, "lft": 2}, {"user": MINH, "lft": 3},
                     {"user": TU, "lft": 8}]
        self.names = {HR: "Trần Hoàn", LAN: "Nguyễn Thị Lan", MINH: "Lê Minh", TU: "Phạm Tú"}
        self.cats = [
            {"name": "thong-bao", "category_name": "Thông báo", "color": "navy", "icon": "megaphone",
             "home_category": "Thông báo", "enabled": 1},
            {"name": "huong-dan", "category_name": "Hướng dẫn", "color": "green", "icon": "book",
             "home_category": "Tính năng mới", "enabled": 1},
            {"name": "chinh-sach", "category_name": "Chính sách mới", "color": "yellow", "icon": "doc",
             "home_category": "Chính sách", "enabled": 1},
        ]
        self.posts = {}
        self.seen = {}               # name -> [user] theo thu tu
        self.rx = []
        self.files = {}              # url -> {post, is_private, file_name, file_size}
        self.jobs = {}
        self.enqueued = []
        self.saved = []
        self.deleted = []
        self.errors = []
        self.guides = [{"slug": "dnmh-dntt", "route": "/huong-dan/dnmh-dntt", "title": "ĐNMH → ĐNTT",
                        "summary": "Hai vòng", "updated": "2026-09-08", "audience": "Finance"}]
        self.dup_next = False

    # -- tien ich test
    def add(self, name, **kw):
        d = Doc(name=name, title=kw.pop("title", name), slug=kw.pop("slug", name), category="thong-bao",
                published=1, published_on=dt.datetime(2026, 9, 30, 9, 0), creation=dt.datetime(2026, 9, 30),
                pinned=0, expires_on=None, summary="", content="<p>x</p>", owner=HR, departments=[],
                attachments=[], cover_kind="color", cover_color="", cover_icon=1, cover_image="",
                cover_ai=0, notify_bell=1, push_to_home=1, notified_on=None, author_label="",
                home_announcement=None)
        d.update(kw)
        self.posts[name] = d
        return d

    # -- nguoi dung
    def is_editor(self, user): return user == HR
    def today(self): return TODAY
    def now(self): return dt.datetime(2026, 10, 1, 9, 0)
    def dept_tree(self): return self.tree
    def active_employees(self): return list(self.emps)
    def full_names(self, users): return {u: self.names.get(u, u) for u in users or () if u}

    def viewer_lft(self, user):
        return next((e["lft"] for e in self.emps if e["user"] == user), None)

    # -- chuyen muc
    def categories(self, include_disabled=False): return [dict(c) for c in self.cats]
    def category(self, name): return next((dict(c) for c in self.cats if c["name"] == name), None)

    # -- bai
    def _readable(self, d, user):
        if self.is_editor(user):
            return True
        lft = self.viewer_lft(user)
        if lft is None:
            return False
        sel = S.selected_ranges(self, [r["department"] for r in d.get("departments") or []])
        return D.readable(d, lft, sel, False)

    def list_posts(self, user, filters=None, or_filters=None, limit=0):
        out = []
        for d in self.posts.values():
            if not self._readable(d, user):
                continue
            if not self.is_editor(user) and D.expired(d, TODAY):
                continue
            f = filters or {}
            if "title" in f and f["title"][1].strip("%").lower() not in d["title"].lower():
                continue
            if "published" in f and not d["published"]:
                continue
            out.append(dict(d))
        out.sort(key=lambda r: (-int(r["pinned"]), -(r["published_on"] or r["creation"]).timestamp()))
        return out[:limit] if limit else out

    def post_departments(self, names):
        return {n: [r["department"] for r in self.posts[n].get("departments") or []] for n in names}

    def seen_by(self, user, names): return {n for n in names if user in self.seen.get(n, [])}
    def seen_users(self, name): return list(self.seen.get(name, []))
    def seen_users_many(self, names): return {n: set(self.seen.get(n, [])) for n in names}

    def mark_seen(self, name, user):
        lst = self.seen.setdefault(name, [])
        if user in lst:
            return False
        lst.append(user)
        return True

    def legacy_guides(self): return list(self.guides)
    def name_by_slug(self, slug): return next((n for n, d in self.posts.items() if d["slug"] == slug), None)
    def post_exists(self, name): return name in self.posts
    def get_post(self, name): return copy.deepcopy(self.posts[name])

    def can(self, doc, ptype, user):
        d = self.posts[doc] if isinstance(doc, str) else doc
        if ptype != "read":
            return self.is_editor(user)
        return self._readable(d, user)

    def safe_html(self, html):
        return re.sub(r"<script\b.*?</script>", "", str(html or ""), flags=re.S | re.I)

    def file_sizes(self, urls): return {u: 2048 for u in urls if u}
    def popup_published(self, name): return bool(name)

    # -- cam xuc
    def reactions(self, targets): return [dict(r) for r in self.rx if r["target"] in targets]

    def find_reaction(self, target, kind, user):
        return next(("RX-%d" % i for i, r in enumerate(self.rx) if (r["target"], r["kind"], r["user"]) == (target, kind, user)), None)

    def add_reaction(self, target, kind, user, today):
        if self.dup_next:
            self.dup_next = False
            raise Dup("Duplicate entry")
        self.rx.append({"target": target, "kind": kind, "user": user})

    def remove_reaction(self, name): self.rx.pop(int(name.split("-")[1]))
    def is_duplicate(self, exc): return isinstance(exc, Dup)

    # -- ghi
    def new_post(self): return Doc(name=None, published=0, departments=[], attachments=[])

    def save_post(self, doc):
        if not doc.get("name"):
            doc["name"] = "POST-%03d" % (len(self.posts) + 1)
        if not doc.get("slug"):
            doc["slug"] = D.unique_slug(doc.get("title"), lambda s: any(
                p["slug"] == s and n != doc["name"] for n, p in self.posts.items()))
        doc.setdefault("creation", dt.datetime(2026, 10, 1, 8, 0))
        doc.setdefault("owner", HR)
        if doc.get("published") and not doc.get("published_on"):      # lifecycle.validate that
            doc["published_on"] = dt.datetime(2026, 10, 1, 9, 30)
        doc.setdefault("published_on", None)
        self.saved.append(doc["name"])
        self.posts[doc["name"]] = Doc(doc)

    def delete_post(self, name):
        self.deleted.append(name)
        self.posts.pop(name)

    def file_info(self, url, post):
        f = self.files.get(url)
        return dict(f) if f and f["post"] == post else None

    # -- AI
    def cover_jobs_today(self, post, day):
        return sum(1 for j in self.jobs.values() if j["post"] == post and j["job_date"] == day)

    def insert_cover_job(self, post, user, day, source_text=""):
        name = "JOB-%02d" % (len(self.jobs) + 1)
        self.jobs[name] = {"name": name, "post": post, "requested_by": user, "job_date": day,
                           "status": "Queued", "images": "[]", "error": "", "source_text": source_text}
        return name

    def enqueue_cover_job(self, job): self.enqueued.append(job)
    def cover_job(self, job): return dict(self.jobs[job]) if job in self.jobs else None
    def set_cover_job(self, job, values): self.jobs[job].update(values)
    def old_cover_jobs(self, days): return [dict(j) for j in self.jobs.values()]
    def post_cover(self, post): return self.posts[post].get("cover_image") if post in self.posts else ""

    def save_remote_image(self, url, post, file_name, max_bytes):
        local = "/files/" + file_name
        self.files[local] = {"post": post, "is_private": 0, "file_name": file_name, "file_size": 10}
        return local

    def delete_post_file(self, url, post):
        return 1 if self.files.pop(url, None) else 0

    def log_error(self, title): self.errors.append(title)
    def log_message(self, title, msg): self.errors.append(title + ":" + msg)


def seeded():
    r = FakeRepo()
    r.add("P1", title="Kế hoạch team building", slug="team-building", pinned=1,
          published_on=dt.datetime(2026, 9, 28, 9, 0), summary="Đăng ký trước 10/10")
    r.add("P2", title="Quy chế công tác phí", slug="cong-tac-phi", category="chinh-sach",
          published_on=dt.datetime(2026, 9, 30, 9, 0), content="<h2>Điểm mới</h2><p>a</p><h2 id='x'>Áp dụng</h2>")
    r.add("P3", title="Lịch trực kho", slug="truc-kho", departments=[{"department": "Van hanh - EC"}],
          published_on=dt.datetime(2026, 9, 29, 9, 0))
    r.add("P4", title="Khám sức khoẻ", slug="kham", expires_on=dt.date(2026, 9, 25),
          published_on=dt.datetime(2026, 9, 15, 9, 0))
    r.add("P5", title="Bản nháp tháng 11", slug="nhap", published=0, published_on=None)
    return r


# ====================================================================== domain ===
class TestDomain(unittest.TestCase):
    def test_slugify_vietnamese(self):
        self.assertEqual(D.slugify("Kế hoạch team building Quý IV: đăng ký!"), "ke-hoach-team-building-quy-iv-dang-ky")
        self.assertEqual(D.slugify("ĐÀ NẴNG"), "da-nang")
        self.assertEqual(D.slugify("!!!"), "")

    def test_unique_slug_skips_reserved_and_taken(self):
        self.assertEqual(D.unique_slug("Viết bài", lambda s: False), "viet-bai-2")
        self.assertEqual(D.unique_slug("a", lambda s: s in ("a", "a-2")), "a-3")
        self.assertEqual(D.unique_slug("", lambda s: False), "bai-viet")

    def test_heading_ids_and_toc(self):
        html, toc = D.add_heading_ids('<h2 id="evil">Một</h2><p>x</p><h2></h2><h2 class="c">Hai <b>đậm</b></h2>')
        self.assertEqual(toc, [{"id": "muc-1", "text": "Một"}, {"id": "muc-2", "text": "Hai đậm"}])
        self.assertIn('<h2 id="muc-1">Một</h2>', html)
        self.assertNotIn("evil", html)
        self.assertIn('<h2 id="muc-2" class="c">', html)

    def test_scope_parent_includes_children(self):
        self.assertTrue(D.in_scope([], None))
        self.assertTrue(D.in_scope([(2, 7)], 3))
        self.assertFalse(D.in_scope([(3, 4)], 2), "phong con KHONG gom phong cha")
        self.assertFalse(D.in_scope([(None, None)], 3), "phong da xoa khoi cay: khong ai khop")
        self.assertFalse(D.in_scope([(2, 7)], None))

    def test_expired_still_readable_but_not_listed(self):
        p = {"published": 1, "expires_on": "2026-09-25"}
        self.assertTrue(D.readable(p, 3, [], False))
        self.assertFalse(D.listed(p, 3, [], False, TODAY))
        self.assertTrue(D.listed(p, 3, [], True, TODAY))
        self.assertFalse(D.readable({"published": 0}, 3, [], False))

    def test_validate_draft_vs_publish(self):
        ok = lambda n: n == "thong-bao"  # noqa: E731
        self.assertEqual(D.validate({"title": "A"}, TODAY, ok, 0), [], "nhap khong can chuyen muc")
        self.assertIn("Chọn một chuyên mục.", D.validate({"title": "A", "published": 1}, TODAY, ok, 0))
        self.assertIn("Bài cần có tiêu đề.", D.validate({"title": " "}, TODAY, ok, 0))
        self.assertIn("Chuyên mục không tồn tại.", D.validate({"title": "A", "category": "zz"}, TODAY, ok, 0))
        self.assertTrue(D.validate({"title": "A", "category": "thong-bao", "scope": "dept"}, TODAY, ok, 0))
        self.assertTrue(D.validate({"title": "A", "category": "thong-bao", "published": 1,
                                    "expires_on": "2026-09-01"}, TODAY, ok, 0))
        self.assertFalse(D.validate({"title": "A", "category": "thong-bao", "published": 1,
                                     "expires_on": "2026-09-01", "_was_published": 1}, TODAY, ok, 0),
                         "bai da dang roi het han: sua bai van luu duoc")
        self.assertTrue(D.validate({"title": "A", "cover_kind": "image"}, TODAY, ok, 0))

    def test_popup_window_and_rule(self):
        self.assertTrue(D.popup_allowed(0))
        self.assertFalse(D.popup_allowed(2))
        self.assertEqual(D.popup_window(TODAY, None), (TODAY, TODAY + dt.timedelta(days=6)))
        self.assertEqual(D.popup_window(TODAY, "2026-10-03")[1], dt.date(2026, 10, 3))

    def test_seen_summary_names_only_for_editor(self):
        names = {LAN: "Nguyễn Thị Lan", MINH: "Lê Minh", TU: "Phạm Tú"}
        s = D.seen_summary([LAN, MINH, TU], [LAN, "nguoi-ngoai@x"], names, MINH, False)
        self.assertEqual((s["total"], s["seen"], s["not_seen"], s["pct"]), (3, 1, 2, 33))
        self.assertEqual(s["not_seen_names"], [])
        e = D.seen_summary([LAN, MINH, TU], [LAN], names, HR, True)
        self.assertEqual(e["not_seen_names"], ["Lê Minh", "Phạm Tú"])

    def test_who_line(self):
        self.assertEqual(D.who_line([], 0, False), "")
        self.assertEqual(D.who_line(["Nguyễn Lan"], 1, False), "Lan")
        self.assertEqual(D.who_line(["Nguyễn Lan", "Lê Minh", "A B"], 3, True), "Bạn, Lan và 2 người khác")

    def test_home_cards_pin_first_and_live_only(self):
        r = seeded()
        cards = S._cards(r, HR, r.list_posts(HR), {c["name"]: c for c in r.cats}, TODAY)
        home = D.home_cards(cards)
        self.assertEqual([c["name"] for c in home], ["P1", "P2", "P3"], "ghim truoc, roi moi nhat; bo nhap / het han")


# ====================================================================== service ==
class TestListPage(unittest.TestCase):
    def test_all_mode_for_employee(self):
        r = seeded()
        ctx = S.list_page(LAN, repo=r)
        self.assertEqual(ctx["mode"], "all")
        self.assertEqual(ctx["pin"]["name"], "P1")
        self.assertEqual([c["name"] for c in ctx["side"]], ["P2", "P3"])
        names = {c["name"] for s in ctx["sections"] for c in s["cards"]}
        self.assertNotIn("P4", names, "het han rut khoi danh sach")
        self.assertNotIn("P5", names, "nhap: nhan vien khong thay")
        guides = [s for s in ctx["sections"] if s["category"]["slug"] == "huong-dan"][0]
        self.assertTrue(guides["cards"][0]["legacy"])
        self.assertEqual(ctx["counts"]["huong-dan"], 1)
        self.assertEqual(ctx["unseen_count"], 3)
        self.assertFalse(ctx["is_editor"])

    def test_scope_hides_post_from_other_department(self):
        r = seeded()
        self.assertIn("P3", {c["name"] for c in S.list_page(MINH, repo=r)["side"]}, "Kho thuoc Van hanh")
        tu = S.list_page(TU, repo=r)
        self.assertNotIn("P3", {c["name"] for s in tu["sections"] for c in s["cards"]})

    def test_editor_sees_drafts_and_expired(self):
        r = seeded()
        ctx = S.list_page(HR, repo=r)
        names = {c["name"] for c in S.list_page(HR, category="thong-bao", repo=r)["items"]}
        self.assertTrue({"P4", "P5"} <= names)
        self.assertEqual(ctx["counts"]["thong-bao"], 4)
        self.assertNotIn("P5", [c["name"] for c in ctx["side"]], "nhap khong len o noi bat")

    def test_category_unseen_search_and_paging(self):
        r = seeded()
        r.seen["P1"] = [LAN]
        ctx = S.list_page(LAN, category="chinh-sach", repo=r)
        self.assertEqual((ctx["mode"], [c["name"] for c in ctx["items"]]), ("list", ["P2"]))
        ctx = S.list_page(LAN, unseen=True, repo=r)
        self.assertEqual({c["name"] for c in ctx["items"]}, {"P2", "P3"})
        ctx = S.list_page(LAN, q="quy chế", repo=r)
        self.assertEqual([c["name"] for c in ctx["items"]], ["P2"])
        for i in range(30):
            r.add("X%02d" % i, slug="x%d" % i, published_on=dt.datetime(2026, 9, 1, 9, i))
        ctx = S.list_page(LAN, category="thong-bao", page="abc", repo=r)
        self.assertEqual((ctx["page_no"], ctx["page_count"], len(ctx["items"])), (1, 3, C.PAGE_SIZE))
        ctx = S.list_page(LAN, category="thong-bao", page="99", repo=r)
        self.assertEqual(ctx["page_no"], 3)

    def test_unknown_category_falls_back_to_all(self):
        self.assertEqual(S.list_page(LAN, category="khong-co", repo=seeded())["mode"], "all")


class TestPostPage(unittest.TestCase):
    def test_reader_view(self):
        r = seeded()
        r.posts["P2"]["content"] += "<script>alert(1)</script>"
        r.posts["P2"]["attachments"] = [{"file_url": "/private/files/qc.pdf", "file_name": "QC-03.pdf"}]
        r.seen["P2"] = [LAN, TU]
        p = S.post_page(MINH, "cong-tac-phi", repo=r)
        self.assertNotIn("<script", p["body"])
        self.assertEqual([t["text"] for t in p["toc"]], ["Điểm mới", "Áp dụng"])
        self.assertEqual(p["files"], [{"url": "/private/files/qc.pdf", "name": "QC-03.pdf", "ext": "PDF", "size": "2 KB"}])
        self.assertEqual((p["seen"]["seen"], p["seen"]["total"]), (2, 4))
        self.assertEqual(p["seen"]["not_seen_names"], [], "nhan vien khong thay ten nguoi chua xem")
        self.assertIsNone(p["editor_info"])
        self.assertEqual(p["category"]["name"], "Chính sách mới")
        self.assertEqual([i["kind"] for i in p["reactions"]["items"]], list(C.REACTION_KINDS))

    def test_editor_view(self):
        r = seeded()
        p = S.post_page(HR, "cong-tac-phi", repo=r)
        self.assertEqual(len(p["seen"]["not_seen_names"]), 4)
        self.assertEqual(p["editor_info"]["edit_url"], "/tin-noi-bo/viet-bai?bai=P2")

    def test_not_found_and_forbidden(self):
        r = seeded()
        with self.assertRaises(S.NotFound):
            S.post_page(LAN, "khong-co", repo=r)
        with self.assertRaises(S.Forbidden):
            S.post_page(TU, "truc-kho", repo=r)
        with self.assertRaises(S.Forbidden):
            S.post_page(LAN, "nhap", repo=r)
        with self.assertRaises(S.Forbidden):
            S.post_page(NOEMP, "team-building", repo=r)
        self.assertTrue(S.post_page(LAN, "kham", repo=r)["expired"], "het han van mo qua link")

    def test_scope_seen_counts_only_audience(self):
        r = seeded()
        r.seen["P3"] = [LAN, TU]          # TU ngoai pham vi (vd tung o phong, da chuyen)
        p = S.post_page(LAN, "truc-kho", repo=r)
        self.assertEqual((p["seen"]["seen"], p["seen"]["total"]), (1, 2))
        self.assertEqual(p["scope_label"], "Vận hành")


class TestSeenAndReactions(unittest.TestCase):
    def test_mark_seen(self):
        r = seeded()
        d = S.mark_seen(LAN, "P1", repo=r)
        self.assertEqual((d["first"], d["seen"], d["total"]), (True, 1, 4))
        self.assertFalse(S.mark_seen(LAN, "P1", repo=r)["first"])
        self.assertFalse(S.mark_seen(HR, "P5", repo=r)["first"], "nhap: HR mo xem khong tinh luot")
        for bad_user, post in (("Guest", "P1"), (TU, "P3"), (LAN, "NOPE")):
            with self.assertRaises(S.PostError):
                S.mark_seen(bad_user, post, repo=r)

    def test_toggle_reaction(self):
        r = seeded()
        v = S.toggle_reaction(LAN, "P1", "heart", repo=r)
        heart = [i for i in v["items"] if i["kind"] == "heart"][0]
        self.assertEqual((heart["n"], heart["mine"], v["who"]), (1, True, "Bạn"))
        S.toggle_reaction(MINH, "P1", "party", repo=r)
        self.assertEqual(S.reactions_view(r, "P1", LAN)["who"], "Bạn, Minh")
        v = S.toggle_reaction(LAN, "P1", "heart", repo=r)
        self.assertEqual([i for i in v["items"] if i["kind"] == "heart"][0]["n"], 0)
        r.dup_next = True
        S.toggle_reaction(TU, "P1", "cake", repo=r)            # trung (2 tab) -> khong loi
        with self.assertRaises(S.PostError):
            S.toggle_reaction(LAN, "P1", "angry", repo=r)
        with self.assertRaises(S.PostError):
            S.toggle_reaction(LAN, "P5", "heart", repo=r)
        with self.assertRaises(S.PostError):
            S.toggle_reaction(TU, "P3", "heart", repo=r)
        self.assertTrue(all(x["target"].startswith("post:") for x in r.rx))


# ====================================================================== editor ===
def payload(**kw):
    p = {"title": "Lịch nghỉ Tết 2027", "summary": "Tóm tắt", "content": "<p>Nội dung</p>",
         "category": "thong-bao", "scope": "all", "notify_bell": 1, "push_to_home": 1, "cover_kind": "color",
         "cover_color": "teal", "cover_icon": 1}
    p.update(kw)
    return p


class TestEditor(unittest.TestCase):
    def test_only_editors(self):
        r = seeded()
        for fn in (lambda: E.compose_context(LAN, repo=r), lambda: E.save(LAN, payload(), repo=r),
                   lambda: E.manage_context(LAN, repo=r), lambda: E.unpublish(LAN, "P1", repo=r),
                   lambda: E.delete_draft(LAN, "P5", repo=r)):
            with self.assertRaises(S.Forbidden):
                fn()

    def test_save_new_then_publish(self):
        r = seeded()
        res = E.save(HR, payload(), "save", repo=r)
        self.assertFalse(res["published"])
        self.assertEqual(res["slug"], "lich-nghi-tet-2027")
        res2 = E.save(HR, payload(name=res["name"], title="Lịch nghỉ Tết âm lịch 2027"), "publish", repo=r)
        self.assertTrue(res2["published"])
        self.assertEqual(res2["slug"], "lich-nghi-tet-am-lich-2027", "nhap: slug theo tieu de moi")
        res3 = E.save(HR, payload(name=res["name"], title="Đổi tên sau khi đăng"), "publish", repo=r)
        self.assertEqual(res3["slug"], "lich-nghi-tet-am-lich-2027", "da dang: giu link")
        self.assertEqual(r.posts[res["name"]]["cover_color"], "teal")

    def test_departments_validated(self):
        r = seeded()
        with self.assertRaises(S.PostError):
            E.save(HR, payload(scope="dept", departments=["Phong ma - EC"]), repo=r)
        with self.assertRaises(S.PostError):
            E.save(HR, payload(scope="dept", departments=[]), repo=r)
        res = E.save(HR, payload(scope="dept", departments=["Kho - EC"]), repo=r)
        self.assertEqual(r.posts[res["name"]]["departments"], [{"department": "Kho - EC"}])
        res = E.save(HR, payload(scope="all", departments=["Kho - EC"]), repo=r)
        self.assertEqual(r.posts[res["name"]]["departments"], [], "toan cong ty: bo phong ban gui kem")

    def test_files_must_belong_to_this_post(self):
        r = seeded()
        r.files["/files/bia.png"] = {"post": "P1", "is_private": 0, "file_name": "bia.png", "file_size": 1}
        r.files["/private/files/luong.xlsx"] = {"post": "HR-OTHER", "is_private": 1, "file_name": "luong.xlsx", "file_size": 1}
        r.files["/private/files/kh.pdf"] = {"post": "P1", "is_private": 1, "file_name": "kh.pdf", "file_size": 9}
        r.files["/files/cong-khai.pdf"] = {"post": "P1", "is_private": 0, "file_name": "c.pdf", "file_size": 9}
        ok = E.save(HR, payload(name="P1", cover_kind="image", cover_image="/files/bia.png",
                                attachments=[{"file_url": "/private/files/kh.pdf"}]), repo=r)
        self.assertEqual(r.posts[ok["name"]]["cover_image"], "/files/bia.png")
        self.assertEqual(r.posts["P1"]["attachments"][0]["file_name"], "kh.pdf")
        bad = [
            dict(name="P2", cover_kind="image", cover_image="/files/bia.png"),          # anh cua bai khac
            dict(cover_kind="image", cover_image="/files/bia.png"),                     # bai moi chua co ten
            dict(name="P1", attachments=[{"file_url": "/private/files/luong.xlsx"}]),   # tep private cua ho so khac
            dict(name="P1", attachments=[{"file_url": "/files/cong-khai.pdf"}]),        # tep cong khai
            dict(name="P1", cover_kind="image", cover_image="/private/files/kh.pdf"),   # anh bia private
        ]
        for b in bad:
            with self.assertRaises(S.PostError, msg=str(b)):
                E.save(HR, payload(**b), repo=r)

    def test_unknown_action_and_missing_post(self):
        r = seeded()
        with self.assertRaises(S.PostError):
            E.save(HR, payload(), "delete", repo=r)
        with self.assertRaises(S.NotFound):
            E.compose_context(HR, "NOPE", repo=r)

    def test_delete_only_never_published_drafts(self):
        r = seeded()
        with self.assertRaises(S.PostError):
            E.delete_draft(HR, "P1", repo=r)
        r.add("P6", published=0, notified_on=dt.datetime(2026, 9, 1))
        with self.assertRaises(S.PostError):
            E.delete_draft(HR, "P6", repo=r)
        r.add("P7", published=0)             # da tung dang roi go: dung Go, khong xoa
        with self.assertRaises(S.PostError):
            E.delete_draft(HR, "P7", repo=r)
        E.delete_draft(HR, "P5", repo=r)
        self.assertEqual(r.deleted, ["P5"])

    def test_unpublish(self):
        r = seeded()
        E.unpublish(HR, "P1", repo=r)
        self.assertEqual(r.posts["P1"]["published"], 0)

    def test_manage_groups(self):
        r = seeded()
        r.seen["P1"] = [LAN, MINH, "nguoi-da-nghi@x"]
        ctx = E.manage_context(HR, "live", repo=r)
        self.assertEqual({t["key"]: t["count"] for t in ctx["tabs"]}, {"live": 3, "draft": 1, "expired": 1})
        p1 = [i for i in ctx["items"] if i["name"] == "P1"][0]
        self.assertEqual((p1["seen"], p1["total"], p1["pct"]), (2, 4, 50))
        p3 = [i for i in ctx["items"] if i["name"] == "P3"][0]
        self.assertEqual((p3["total"], p3["scope_label"]), (2, "Vận hành"))
        self.assertEqual(E.manage_context(HR, "bogus", repo=r)["tab"], "live")

    def test_dept_options(self):
        opts = E.dept_options(FakeRepo())
        self.assertEqual([(o["label"], o["depth"]) for o in opts],
                         [("Vận hành", 0), ("Kho", 1), ("Giao vận", 1), ("Marketing", 0)])

    def test_compose_context(self):
        r = seeded()
        ctx = E.compose_context(HR, "P3", repo=r)
        self.assertEqual(ctx["post"]["scope"], "dept")
        self.assertEqual(ctx["post"]["departments"], ["Van hanh - EC"])
        self.assertEqual(ctx["company_size"], 4)
        self.assertEqual(len(ctx["colors"]), 8)
        self.assertEqual(ctx["ai_limit"], 5)
        self.assertIsNone(E.compose_context(HR, repo=r)["post"])


# ====================================================================== AI bia ===
class TestCoverAI(unittest.TestCase):
    def setUp(self):
        self._avail = AI.available
        AI.available = lambda: True

    def tearDown(self):
        AI.available = self._avail

    def test_limit_five_per_post_per_day(self):
        r = seeded()
        for i in range(C.AI_COVER_DAILY_LIMIT):
            d = AI.start(HR, "P1", "Tiêu đề đang gõ", "", "<p>Nội dung chưa lưu</p>", repo=r)
            self.assertEqual(d["used"], i + 1)
        with self.assertRaises(S.PostError) as cm:
            AI.start(HR, "P1", "t", repo=r)
        self.assertIn("5/5", str(cm.exception))
        AI.start(HR, "P2", "Bài khác", repo=r)          # moi bai mot quy rieng
        r.jobs["JOB-01"]["job_date"] = TODAY - dt.timedelta(days=1)
        AI.start(HR, "P1", "Hôm sau", repo=r)          # qua ngay: duoc lai
        self.assertIn("Nội dung chưa lưu", r.jobs["JOB-02"]["source_text"])
        self.assertEqual(len(r.enqueued), 7)

    def test_start_guards(self):
        r = seeded()
        with self.assertRaises(S.Forbidden):
            AI.start(LAN, "P1", "t", repo=r)
        with self.assertRaises(S.NotFound):
            AI.start(HR, "NOPE", "t", repo=r)
        AI.available = lambda: False
        with self.assertRaises(S.PostError):
            AI.start(HR, "P1", "t", repo=r)
        AI.available = lambda: True
        AI.start(HR, "P1", "", repo=r)
        self.assertIn("Kế hoạch team building", r.jobs["JOB-01"]["source_text"], "khong gui chu: doc bai da luu")

    def test_run_job_success(self):
        r = seeded()
        job = AI.start(HR, "P1", "Tiêu đề mới", "Tóm", "<p>Chi tiết</p>", repo=r)["job"]
        seen = {}

        def gen(prompt, **kw):
            seen["prompt"] = prompt
            return {"ok": True, "data": {"image_prompt": "A flat illustration of a team retreat, navy and yellow, no text"}}

        def imgs(prompt, n, **kw):
            seen["img"] = (prompt, n)
            return {"ok": True, "urls": ["https://kie/1.png", "https://kie/2.png", "https://kie/3.png"], "model": "m"}

        AI.run_job(job, repo=r, generate=gen, make_images=imgs)
        j = r.jobs[job]
        self.assertEqual(j["status"], "Done")
        self.assertEqual(len(json.loads(j["images"])), 3)
        self.assertIn("Tiêu đề mới", seen["prompt"])
        self.assertIn("Chi tiết", seen["prompt"])
        self.assertEqual(seen["img"][1], 3)
        st = AI.status(HR, job, repo=r)
        self.assertEqual((st["status"], len(st["images"]), st["error"]), ("Done", 3, ""))
        # anh AI la tep cong khai GAN VAO BAI -> luu lam bia duoc
        url = st["images"][1]
        E.save(HR, payload(name="P1", cover_kind="image", cover_image=url, cover_ai=1), repo=r)
        self.assertEqual(r.posts["P1"]["cover_ai"], 1)
        # don dep: giu anh dang lam bia, xoa 2 anh con lai
        self.assertEqual(AI.cleanup_unused(repo=r), 2)
        self.assertEqual(json.loads(r.jobs[job]["images"]), [url])

    def test_run_job_fallback_prompt_and_failures(self):
        r = seeded()
        job = AI.start(HR, "P1", "Tiêu đề", repo=r)["job"]
        got = {}

        def broken_gen(*a, **k):
            raise RuntimeError("model chu hong")

        def imgs(prompt, n, **kw):
            got["prompt"] = prompt
            return {"ok": False, "urls": [], "error": "Kie code=500"}

        AI.run_job(job, repo=r, generate=broken_gen, make_images=imgs)
        self.assertIn("Tiêu đề", got["prompt"], "model chu hong -> mo ta dung san tu tieu de")
        self.assertEqual(r.jobs[job]["status"], "Failed")
        self.assertEqual(AI.status(HR, job, repo=r)["error"], AI.FRIENDLY_ERROR)
        job2 = AI.start(HR, "P1", "Tiêu đề", repo=r)["job"]

        def boom(*a, **k):
            raise ValueError("x")
        AI.run_job(job2, repo=r, generate=broken_gen, make_images=boom)
        self.assertEqual(r.jobs[job2]["status"], "Failed")
        AI.run_job(job2, repo=r, generate=broken_gen, make_images=boom)      # chay lai: bo qua
        with self.assertRaises(S.Forbidden):
            AI.status(LAN, job2, repo=r)


# ====================================================================== quyen ====
class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.session = types.SimpleNamespace(user="Guest")
        self.db = types.SimpleNamespace(escape=lambda v: "'%s'" % str(v).replace("'", "\\'"))
        self.local = types.SimpleNamespace()


class TestPermissions(unittest.TestCase):
    def setUp(self):
        self._saved = sys.modules.get("frappe")
        sys.modules["frappe"] = FakeFrappe()
        for m in ("ecentric_workspace.internal_posts.permissions", "ecentric_workspace.internal_posts.repository"):
            sys.modules.pop(m, None)
        from ecentric_workspace.internal_posts import permissions as P
        from ecentric_workspace.internal_posts import repository as R
        self.P, self.R = P, R
        repo = FakeRepo()
        R.is_editor = repo.is_editor
        R.today = repo.today
        R.dept_tree = repo.dept_tree
        R.viewer = lambda u: ({"lft": repo.viewer_lft(u)} if repo.viewer_lft(u) is not None else None)

    def tearDown(self):
        for m in ("ecentric_workspace.internal_posts.permissions", "ecentric_workspace.internal_posts.repository"):
            sys.modules.pop(m, None)
        if self._saved is not None:
            sys.modules["frappe"] = self._saved
        else:
            sys.modules.pop("frappe", None)

    def test_query_conditions(self):
        self.assertEqual(self.P.query_conditions(HR), "")
        self.assertEqual(self.P.query_conditions(NOEMP), "1=0")
        q = self.P.query_conditions(MINH)
        self.assertIn("`tabEC Internal Post`.published = 1", q)
        self.assertIn("expires_on >= '2026-10-01'", q)
        self.assertIn("sel.lft <= 3 and sel.rgt >= 3", q)
        self.assertIn("not exists", q)

    def test_child_tables_follow_parent(self):
        P = self.P
        self.assertEqual(P.child_query_conditions(HR, "EC Internal Post File"), "")
        self.assertEqual(P.child_query_conditions(NOEMP, "EC Internal Post File"), "1=0")
        q = P.child_query_conditions(MINH, "EC Internal Post File")
        self.assertTrue(q.startswith("`tabEC Internal Post File`.parent in (select `tabEC Internal Post`.name"))
        self.assertIn("published = 1", q)

    def test_has_permission(self):
        P = self.P
        scoped = {"published": 1, "departments": [{"department": "Van hanh - EC"}]}
        self.assertTrue(P.has_permission(scoped, "read", MINH))
        self.assertFalse(P.has_permission(scoped, "read", TU))
        self.assertFalse(P.has_permission({"published": 0, "departments": []}, "read", LAN))
        self.assertTrue(P.has_permission({"published": 0, "departments": []}, "read", HR))
        self.assertFalse(P.has_permission({"published": 1, "departments": []}, "read", NOEMP))
        self.assertTrue(P.has_permission({"published": 1, "departments": []}, "write", TU),
                        "ptype ghi: de quyen role quyet (hook chi duoc tu choi)")
        gone = {"published": 1, "departments": [{"department": "Da xoa - EC"}]}
        self.assertFalse(P.has_permission(gone, "read", LAN))
        exp = {"published": 1, "expires_on": "2026-01-01", "departments": []}
        self.assertTrue(P.has_permission(exp, "read", LAN), "het han: van mo qua link")


# ====================================================================== popup chung
class FakeHomeRepo:
    def __init__(self):
        self.rows = {}
        self.fail = False
        self.log = []

    def savepoint(self, n): self.log.append("sp")
    def rollback_to(self, n): self.log.append("rb")
    def log_error(self, t): self.log.append("err")
    def nowdate(self): return TODAY
    def cache_clear_today(self): self.log.append("cache")

    def announcement_by_source(self, dt_, name, ver):
        return next((k for k, v in self.rows.items() if (v["source_doctype"], v["source_name"], v["source_version"]) == (dt_, name, ver)), None)

    def announcement_published(self, n): return bool(self.rows[n]["published"])
    def set_announcement_published(self, n, on): self.rows[n]["published"] = 1 if on else 0

    def published_announcements_of(self, dt_, name):
        return [k for k, v in self.rows.items() if v["source_doctype"] == dt_ and v["source_name"] == name and v["published"]]

    def update_announcement(self, n, fields): self.rows[n].update(fields)

    def insert_announcement(self, data):
        if self.fail:
            raise RuntimeError("db")
        n = "ANN-%d" % (len(self.rows) + 1)
        self.rows[n] = dict(data)
        return n


class TestAnnounceService(unittest.TestCase):
    def setUp(self):
        from ecentric_workspace.home_today import announce_service as A
        self.A = A

    def test_idempotent_versioned_and_withdraw(self):
        A, r = self.A, FakeHomeRepo()
        n1 = A.publish_from_source(C.POST_DT, "P1", "", "Tiêu đề", category="Chính sách", repo=r)
        self.assertEqual(A.publish_from_source(C.POST_DT, "P1", "", "Tiêu đề", repo=r), n1)
        self.assertEqual(len(r.rows), 1)
        self.assertEqual(r.rows[n1]["category"], "Chính sách")
        self.assertEqual(r.rows[n1]["start_date"], TODAY)
        n2 = A.publish_from_source("Quality Procedure", "QC-03", "2", "Ban hành", category="Lạ", repo=r)
        self.assertNotEqual(n1, n2)
        self.assertIn(r.rows[n2]["category"], A.CATEGORIES)
        self.assertEqual(A.withdraw_source(C.POST_DT, "P1", repo=r), 1)
        self.assertEqual(r.rows[n1]["published"], 0)
        self.assertEqual(A.publish_from_source(C.POST_DT, "P1", "", "Tiêu đề mới", link="/tin-noi-bo/a",
                                               start_date=dt.date(2026, 10, 5), repo=r), n1, "dang lai: bat lai cai cu")
        self.assertEqual((r.rows[n1]["published"], r.rows[n1]["title"], r.rows[n1]["start_date"]),
                         (1, "Tiêu đề mới", dt.date(2026, 10, 5)), "bat lai: noi dung + cua so ngay moi")
        A.publish_from_source(C.POST_DT, "P1", "", "Sửa tiêu đề", start_date=dt.date(2026, 10, 9), repo=r)
        self.assertEqual((r.rows[n1]["title"], r.rows[n1]["start_date"]), ("Sửa tiêu đề", dt.date(2026, 10, 5)),
                         "dang hien: doi chu, giu ngay")

    def test_error_rolls_back_and_returns_none(self):
        A, r = self.A, FakeHomeRepo()
        r.fail = True
        self.assertIsNone(A.publish_from_source(C.POST_DT, "P1", "", "T", repo=r))
        self.assertEqual(r.log[-2:], ["rb", "err"])


# ====================================================================== Kie anh ==
class TestImages(unittest.TestCase):
    def setUp(self):
        self._saved = sys.modules.get("frappe")
        fake = FakeFrappe()
        fake.conf = {}
        sys.modules["frappe"] = fake
        sys.modules.pop("ecentric_workspace.platform.ai.images", None)
        from ecentric_workspace.platform.ai import images
        self.I = images

    def tearDown(self):
        sys.modules.pop("ecentric_workspace.platform.ai.images", None)
        if self._saved is not None:
            sys.modules["frappe"] = self._saved
        else:
            sys.modules.pop("frappe", None)

    def test_parse(self):
        I = self.I
        self.assertEqual(I.parse_create(200, '{"code":200,"data":{"taskId":"t1"}}'), ("t1", ""))
        self.assertEqual(I.parse_create(200, '{"code":500,"msg":"Server exception"}')[0], "", "loi Kie = HTTP 200 + code")
        self.assertEqual(I.parse_create(502, "bad")[1], "HTTP 502")
        body = json.dumps({"code": 200, "data": {"state": "success", "resultJson": json.dumps({"resultUrls": ["https://a/1.png", "ftp://x"]})}})
        self.assertEqual(I.parse_record(200, body), ("success", ["https://a/1.png"], ""))
        self.assertEqual(I.parse_record(200, '{"data":{"state":"fail","failMsg":"nsfw"}}')[2], "nsfw")
        self.assertEqual(I.parse_record(200, '{"data":{"state":"generating"}}'), ("generating", [], ""))

    def test_generate_partial_success_and_scrub(self):
        I = self.I
        I.config = types.SimpleNamespace(disabled=lambda: False, api_key=lambda: "SECRETKEY")
        calls = {"n": 0}

        def create(key, body):
            calls["n"] += 1
            if calls["n"] == 2:
                raise IOError("timeout SECRETKEY")
            return "t%d" % calls["n"], ""

        def record(key, tid):
            return ("success", ["https://a/%s.png" % tid], "") if tid == "t1" else ("fail", [], "bad")

        I._create, I._record = create, record
        t = {"now": 0}
        out = I.generate("p", n=3, sleep=lambda s: t.__setitem__("now", t["now"] + s), clock=lambda: t["now"])
        self.assertTrue(out["ok"])
        self.assertEqual(out["urls"], ["https://a/t1.png"])
        self.assertNotIn("SECRETKEY", out["error"])
        I.config = types.SimpleNamespace(disabled=lambda: True, api_key=lambda: "k")
        self.assertEqual(I.generate("p")["error"], "ai_disabled")


# ====================================================================== trang www =
class _NS(dict):
    __getattr__ = dict.get


def _env(strict=True):
    try:
        import jinja2
    except ImportError:
        raise unittest.SkipTest("thieu jinja2")
    from jinja2.sandbox import SandboxedEnvironment
    base = ("<html><head><title>{% block title %}{% endblock %}</title>{% block style %}{% endblock %}</head>"
            "<body>{% block navbar %}NAVBAR{% endblock %}{% block content %}{% endblock %}"
            "{% block footer %}FOOTER{% endblock %}{% block script %}{% endblock %}</body></html>")
    loader = jinja2.ChoiceLoader([jinja2.DictLoader({"templates/base.html": base}), jinja2.FileSystemLoader(APP)])
    return SandboxedEnvironment(loader=loader, undefined=jinja2.StrictUndefined if strict else jinja2.Undefined)


def _render(page, ctx, strict=True):
    full = {"base_template_path": "templates/base.html", "ip_shell_mount": "<aside>MENU</aside>",
            "ip_topbar": "<div>TOPBAR</div>", "ip_css": "/a.css", "ip_js": "/a.js", "title": "T"}
    full.update(ctx)
    return _env(strict).get_template("www/tin_noi_bo/%s.html" % page).render(**full)


EVIL = '<script>alert("x")</script>'


class TestPages(unittest.TestCase):
    def test_index_all_mode(self):
        r = seeded()
        r.posts["P2"]["title"] = EVIL
        out = _render("index", S.list_page(LAN, repo=r))
        self.assertNotIn(EVIL, out)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("NAVBAR", out)
        self.assertNotIn("FOOTER", out)
        self.assertIn("<aside>MENU</aside>", out)
        self.assertIn('class="eip-big"', out)
        self.assertIn("Đã ghim", out)
        self.assertIn("Bài hướng dẫn có sẵn", out)
        self.assertIn('href="/tin-noi-bo?chuyen-muc=chinh-sach"', out)
        self.assertIn("Chưa xem <em>3</em>", out)
        self.assertNotIn("/tin-noi-bo/viet-bai", out, "nhan vien khong thay nut Viet bai")
        self.assertNotIn("/app/", out)

    def test_index_list_modes(self):
        r = seeded()
        out = _render("index", S.list_page(HR, category="huong-dan", repo=r))
        self.assertIn("Gộp cả bài hướng dẫn cũ", out)
        self.assertIn('href="/tin-noi-bo/viet-bai"', out)
        out = _render("index", S.list_page(LAN, q='"><img src=x>', repo=r))
        self.assertNotIn('"><img src=x>', out)
        self.assertIn("Không có bài nào khớp", out)
        for i in range(15):
            r.add("X%02d" % i, slug="x%d" % i)
        out = _render("index", S.list_page(LAN, category="thong-bao", page=2, repo=r))
        self.assertIn("Trang 2 / 2", out)
        self.assertIn('href="/tin-noi-bo?chuyen-muc=thong-bao&trang=1"', out)
        out = _render("index", S.list_page(LAN, unseen=True, repo=FakeRepo()))
        self.assertIn("Bạn đã xem hết các bài.", out)

    def test_post_page(self):
        r = seeded()
        r.posts["P2"].update(summary=EVIL, author_label=EVIL,
                             attachments=[{"file_url": "/private/files/a.pdf", "file_name": EVIL + ".pdf"}])
        out = _render("bai", {"post": S.post_page(LAN, "cong-tac-phi", repo=r)})
        self.assertNotIn(EVIL, out)
        self.assertIn('<a href="#muc-1" aria-current="true">Điểm mới</a>', out)
        self.assertIn('<h2 id="muc-2">Áp dụng</h2>', out)
        self.assertIn('data-eip-post="P2" data-eip-published="1"', out)
        self.assertIn('data-eip-rx="heart"', out)
        self.assertNotIn("Chỉ HR thấy", out)
        self.assertIn("Mở bài là được tính đã xem", out)
        hr = _render("bai", {"post": S.post_page(HR, "nhap", repo=r)})
        self.assertIn("Bản nháp. Chỉ HR xem được.", hr)
        self.assertIn("Chỉ HR thấy", hr)
        self.assertIn('href="/tin-noi-bo/viet-bai?bai=P5"', hr)
        self.assertNotIn("data-eip-rx-panel", hr, "nhap: khong tha cam xuc")
        exp = _render("bai", {"post": S.post_page(LAN, "kham", repo=r)})
        self.assertIn("Bài đã hết hạn ngày 25/09/2026", exp)
        sc = _render("bai", {"post": S.post_page(MINH, "truc-kho", repo=r)})
        self.assertIn("Bài chỉ dành cho Vận hành", sc)

    def test_compose_page(self):
        r = seeded()
        r.posts["P3"]["title"] = EVIL
        ctx = E.compose_context(HR, "P3", repo=r)
        ctx.update(ip_data_json=json.dumps({"post": ctx["post"]}).replace("</", "<\\/"), ip_editor_js="/e.js")
        out = _render("viet_bai", ctx)
        self.assertNotIn(EVIL, out.split('id="eip-data"')[0])
        self.assertNotIn("</script>\"", out)
        self.assertIn('data-eip-dept="Van hanh - EC" aria-pressed="true"', out)
        self.assertIn('value="dept" checked', out)
        self.assertIn('data-eip-act="unpublish"', out)
        self.assertIn('<script src="/e.js" defer></script>', out)
        self.assertEqual(out.count('class="eip-swatch'), 8)
        new = E.compose_context(HR, repo=r)
        new.update(ip_data_json="{}", ip_editor_js="/e.js")
        out = _render("viet_bai", new, strict=False)
        self.assertIn('data-eip-act="save"', out)
        self.assertIn("Chưa lưu", out)
        self.assertIn('value="all" checked', out)
        self.assertIn('<input type="checkbox" data-eip-chk="push_to_home" checked>', out)
        self.assertIn("Hiển thị trên popup trang chủ", out)

    def test_manage_page(self):
        r = seeded()
        r.posts["P1"]["title"] = EVIL
        out = _render("quan_ly", E.manage_context(HR, "live", repo=r))
        self.assertNotIn(EVIL, out)
        self.assertIn('data-eip-manage="unpublish" data-eip-name="P1"', out)
        self.assertIn('aria-current="page">Đang hiện<em>3</em>', out)
        r.add("P8", published=0)
        out = _render("quan_ly", E.manage_context(HR, "draft", repo=r))
        self.assertIn('data-eip-manage="delete" data-eip-name="P5"', out)
        self.assertNotIn('data-eip-name="P8"', out, "da tung dang: khong co nut Xoa nhap")
        out = _render("quan_ly", E.manage_context(HR, "expired", repo=FakeRepo()))
        self.assertIn("Chưa có bài nào hết hạn.", out)

    def test_page_controllers_are_uncached(self):
        for f in ("index", "bai", "viet_bai", "quan_ly"):
            src = io.open(os.path.join(APP, "www", "tin_noi_bo", f + ".py"), encoding="utf-8").read()
            self.assertIn("no_cache = 1", src, f)
            self.assertIn("require_login", src, f)

    def test_hooks_wiring(self):
        h = io.open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        for s in ('{"from_route": "/tin-noi-bo/<slug>", "to_route": "tin_noi_bo/bai"}',
                  'permission_query_conditions["EC Internal Post"]', 'has_permission["EC Internal Post"]',
                  '"ecentric_workspace.internal_posts.jinja.internal_posts_home"',
                  '{"source": "/huong-dan", "target": "/tin-noi-bo?chuyen-muc=huong-dan"'):
            self.assertIn(s, h)
        # route tinh dung truoc route slug
        self.assertLess(h.index('"/tin-noi-bo/viet-bai"'), h.index('"/tin-noi-bo/<slug>"'))
        self.assertIn("Internal Posts", io.open(os.path.join(APP, "modules.txt"), encoding="utf-8").read())


class TestAssets(unittest.TestCase):
    def test_js_has_no_jinja_and_uses_ecapi(self):
        for f in ("ec_internal_posts.js", "ec_internal_posts_editor.js"):
            src = io.open(os.path.join(APP, "public", "js", f), encoding="utf-8").read()
            self.assertNotIn("{{", src, f)
            self.assertNotIn("{%", src, f)
            self.assertNotIn("alert(", src, f)
            self.assertNotIn("window.fetch =", src, f)
        ed = io.open(os.path.join(APP, "public", "js", "ec_internal_posts_editor.js"), encoding="utf-8").read()
        self.assertIn("is_private", ed)
        self.assertIn("csrfToken", ed)

    def test_css_scoped(self):
        css = io.open(os.path.join(APP, "public", "css", "ec_internal_posts.css"), encoding="utf-8").read()
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        css = re.sub(r"@keyframes[^{]+\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
        for sel in re.findall(r"([^{}@]+)\{", css):
            for part in sel.split(","):
                part = part.strip()
                if not part or part.startswith(("from", "to", "media", "@")):
                    continue
                self.assertTrue(".eip-" in part, "luat CSS khong co tien to eip-: %r" % part)
        self.assertNotIn(".ec-sidebar", css)


if __name__ == "__main__":
    unittest.main()
