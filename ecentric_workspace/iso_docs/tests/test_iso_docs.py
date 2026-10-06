# Copyright (c) 2026, eCentric and contributors
"""Thu vien tai lieu ISO - chay THAT domain / service / workflow_spec + announce_service dung
chung tren repo gia (khong can bench).

    python -m unittest ecentric_workspace.iso_docs.tests.test_iso_docs
"""
import datetime as dt
import json
import os
import re
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
APP = os.path.join(ROOT, "ecentric_workspace")
sys.path.insert(0, ROOT)

from ecentric_workspace.iso_docs import constants as C  # noqa: E402
from ecentric_workspace.iso_docs import domain as D  # noqa: E402
from ecentric_workspace.iso_docs import service as S  # noqa: E402
from ecentric_workspace.iso_docs import notify as N  # noqa: E402
from ecentric_workspace.iso_docs import workflow_spec as W  # noqa: E402
from ecentric_workspace.iso_docs.errors import DocError  # noqa: E402
from ecentric_workspace.home_today import announce_service as A  # noqa: E402

TODAY = dt.date(2026, 10, 5)
ISO = "iso@x"
CEO = "tgd@x"
HEAD = "phuong@x"     # truong phong Tai chinh
DRAFTER = "soan@x"


class Doc(dict):
    """Gia frappe Document: doc.get / doc.x / doc.x = / doc.append(child, row) / doc.flags."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.__dict__["flags"] = types.SimpleNamespace()

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v

    def append(self, field, row):
        self.setdefault(field, []).append(Doc(row))


class HomeRepo:
    """Gia home_today.repository cho announce_service."""

    def __init__(self, fail=False):
        self.rows, self.fail, self.errors, self.cleared = {}, fail, [], 0

    def savepoint(self, name):
        self.sp = dict((k, dict(v)) for k, v in self.rows.items())

    def rollback_to(self, name):
        self.rows = self.sp

    def log_error(self, title):
        self.errors.append(title)

    def nowdate(self):
        return TODAY

    def announcement_by_source(self, dt_, name, version):
        for k, r in self.rows.items():
            if (r["source_doctype"], r["source_name"], r["source_version"]) == (dt_, name, version):
                return k
        return None

    def announcement_published(self, name):
        return bool(self.rows[name]["published"])

    def update_announcement(self, name, values):
        self.rows[name].update(values)

    def cache_clear_today(self):
        self.cleared += 1

    def insert_announcement(self, values):
        name = "HA-%03d" % (len(self.rows) + 1)
        self.rows[name] = dict(values)       # ghi xong roi moi hong -> phai rollback dung phan nay
        if self.fail:
            raise RuntimeError("db down")
        return name

    def published_announcements_of(self, dt_, name):
        return [k for k, r in self.rows.items() if r["source_name"] == name and r["published"]]

    def set_announcement_published(self, name, on):
        self.rows[name]["published"] = 1 if on else 0


class Repo:
    """Gia iso_docs.repository - goi THAT announce_service voi HomeRepo."""

    def __init__(self, user=ISO, home=None, heads=None):
        self.user, self.home = user, home or HomeRepo()
        self.heads = heads if heads is not None else {"Finance & Accounting - EC": HEAD}
        self.links, self.enqueued, self.errors = [], [], []
        self.enqueue_fails = False

    def enqueue_notify(self, name, before, after, actor, stamp):
        if self.enqueue_fails:
            raise RuntimeError("redis down")
        self.enqueued.append((name, before, after, actor))

    def log_error(self, title):
        self.errors.append(title)

    def session_user(self):
        return self.user

    def today(self):
        return TODAY

    def dept_head(self, dept):
        return self.heads.get(dept)

    def state_before(self, doc):
        return getattr(doc.flags, "before", None)

    def publish_announcement(self, doc_name, version, payload):
        return A.publish_from_source(C.QP, doc_name, version, repo=self.home, **payload)

    def link_announcement(self, doc_name, version, name):
        self.links.append((doc_name, version, name))

    def withdraw_announcements(self, doc_name):
        return A.withdraw_source(C.QP, doc_name, repo=self.home)


def new_doc(**kw):
    d = Doc(name="QT-TCKT-03", quality_procedure_name="Quy trình thanh toán",
            ec_doc_code="QT-TCKT-03", ec_doc_type="Quy trình", ec_department="Finance & Accounting - EC",
            ec_company_wide=1, ec_notify_home=1, ec_notify_summary="Đề nghị thanh toán đi qua ERP.",
            ec_doc_state=C.S_DRAFT, ec_current_version="", ec_draft_version="", ec_change_kind="",
            ec_change_summary="Ban hành lần đầu trên ERP", ec_drafter=DRAFTER, ec_revisions=[],
            ec_scope_departments=[], ec_review_months=12)
    d.update(kw)
    return d


def move(doc, to, repo):
    """Mo phong apply_workflow: doi trang thai roi luu (validate -> on_update)."""
    doc.flags.before = doc.get(C.STATE_FIELD)
    doc[C.STATE_FIELD] = to
    kind = S.on_validate(doc, repo)
    S.on_update(doc, repo)
    return kind


def publish_major(doc, repo_iso, repo_ceo):
    move(doc, C.S_HEAD, repo_iso)
    move(doc, C.S_ISO, Repo(user=HEAD, home=repo_iso.home))
    move(doc, C.S_CEO, repo_iso)
    move(doc, C.S_PUBLISHED, repo_ceo)


# =========================================================================== domain
class TestVersion(unittest.TestCase):
    def test_next(self):
        self.assertEqual(D.next_version("", C.KIND_MAJOR), "1.0")
        self.assertEqual(D.next_version(None, C.KIND_MINOR), "1.0")
        self.assertEqual(D.next_version("3.0", C.KIND_MAJOR), "4.0")
        self.assertEqual(D.next_version("3.2", C.KIND_MAJOR), "4.0")
        self.assertEqual(D.next_version("3.2", C.KIND_MINOR), "3.3")
        self.assertEqual(D.next_version("1.9", C.KIND_MINOR), "1.10")

    def test_gt(self):
        self.assertTrue(D.version_gt("1.10", "1.9"))
        self.assertTrue(D.version_gt("2.0", ""))
        self.assertFalse(D.version_gt("2.0", "2.0"))
        self.assertFalse(D.version_gt("x", "1.0"))

    def test_add_months(self):
        self.assertEqual(D.add_months(dt.date(2026, 1, 31), 1), dt.date(2026, 2, 28))
        self.assertEqual(D.add_months(dt.date(2026, 10, 5), 12), dt.date(2027, 10, 5))
        self.assertEqual(D.add_months(dt.date(2027, 12, 31), 2), dt.date(2028, 2, 29))


class TestCode(unittest.TestCase):
    def test_ok(self):
        for c in ("QT-TCKT-03", "HD-ISO-01", "CS-NS-12", "BM-QT-TCKT-03-01", "TL-ISO-01"):
            self.assertIsNone(D.code_error(c), c)

    def test_bad(self):
        for c in ("", "QT-03", "XX-TCKT-03", "qt-tckt-03", "QT-TCKT-3", "QT-TOOLONG-03", "BM-QT-TCKT-03"):
            self.assertIsNotNone(D.code_error(c), c)

    def test_prefix_matches_type(self):
        self.assertIn("không khớp", D.code_error("HD-TCKT-03", "Quy trình"))
        self.assertIsNone(D.code_error("QT-TCKT-03", "Quy trình"))
        self.assertIsNone(D.code_error("BM-QT-TCKT-03-01", "Biểu mẫu"))


class TestValidate(unittest.TestCase):
    base = {"ec_doc_code": "QT-TCKT-03", "ec_doc_type": "Quy trình", "ec_company_wide": 1}

    def v(self, **kw):
        d = dict(self.base)
        d.update(kw)
        return D.validate(d)

    def test_ok(self):
        self.assertEqual(self.v(), [])

    def test_scope_needed(self):
        self.assertTrue(self.v(ec_company_wide=0))
        self.assertEqual(self.v(ec_company_wide=0, scope_departments=["Service - EC"]), [])

    def test_notify_only_company_wide(self):
        """Spec muc 5: chi tai lieu toan cong ty moi duoc tich thong bao."""
        errs = self.v(ec_company_wide=0, scope_departments=["Service - EC"], ec_notify_home=1)
        self.assertEqual(len(errs), 1)
        self.assertIn("toàn công ty", errs[0])
        self.assertEqual(self.v(ec_notify_home=1), [])

    def test_draft_version(self):
        self.assertTrue(self.v(ec_draft_version="2"))
        self.assertTrue(self.v(ec_draft_version="1.0", ec_current_version="1.0"))
        self.assertEqual(self.v(ec_draft_version="1.1", ec_current_version="1.0"), [])

    def test_kind_and_review(self):
        self.assertTrue(self.v(ec_change_kind="Vừa"))
        self.assertTrue(self.v(ec_review_months=0))
        self.assertEqual(self.v(ec_review_months=24), [])


class TestTransitionKind(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(D.transition_kind(C.S_CEO, C.S_PUBLISHED), "publish")
        self.assertEqual(D.transition_kind(C.S_ISO, C.S_PUBLISHED), "publish")
        self.assertEqual(D.transition_kind(C.S_WITHDRAW, C.S_PUBLISHED), "keep")
        self.assertEqual(D.transition_kind(C.S_WITHDRAW, C.S_EXPIRED), "withdraw")
        self.assertEqual(D.transition_kind(C.S_PUBLISHED, C.S_DRAFT), "new_draft")
        self.assertEqual(D.transition_kind(C.S_ISO, C.S_CEO), "iso_review")
        self.assertIsNone(D.transition_kind(C.S_PUBLISHED, C.S_PUBLISHED))


class TestPayload(unittest.TestCase):
    def test_spec(self):
        """Spec muc 2: tieu de, chuyen muc, ngay, link."""
        p = D.announcement_payload("QT-TCKT-03", "Quy trình thanh toán ", "2.0", TODAY, " Tóm tắt ")
        self.assertEqual(p["title"], "Ban hành: QT-TCKT-03 Quy trình thanh toán (v2.0)")
        self.assertEqual(p["category"], "Chính sách")
        self.assertEqual(p["start_date"], TODAY)
        self.assertEqual(p["end_date"], dt.date(2026, 10, 11))
        self.assertEqual(p["link"], "/tai-lieu/QT-TCKT-03")
        self.assertEqual(p["link_label"], "Xem tài liệu →")
        self.assertEqual(p["summary"], "Tóm tắt")
        self.assertIn(p["category"], A.CATEGORIES)
        self.assertEqual(A.DISPLAY_DEFAULT, "Ảnh + nội dung")


class TestPlan(unittest.TestCase):
    def test_already_published_version_adds_nothing(self):
        p = D.publish_plan([{"version": "2.0", "status": C.REV_EFFECTIVE}], "1.0", "2.0", C.KIND_MAJOR,
                           TODAY, ISO)
        self.assertTrue(p["already"])
        self.assertIsNone(p["row"])
        self.assertEqual((p["close"], p["doc"]), ([], {}))

    def test_should_announce(self):
        self.assertTrue(D.should_announce(1, 1))
        self.assertFalse(D.should_announce(1, 0))
        self.assertFalse(D.should_announce(0, 1))

    def test_on_update_guards_scope_even_if_flag_slipped(self):
        """Phong thu hai lop: du du lieu cu lot qua validate, khong toan cong ty -> khong thong bao."""
        iso = Repo()
        doc = new_doc(ec_company_wide=0, ec_effective_from=TODAY)
        doc.flags.ec_published_version = "1.0"
        self.assertIsNone(S.on_update(doc, iso))
        self.assertEqual(iso.home.rows, {})


class TestPermissionRules(unittest.TestCase):
    pub = {"ec_current_version": "1.0", "ec_doc_state": C.S_PUBLISHED, "ec_company_wide": 1,
           "ec_drafter": DRAFTER, "ec_dept_head": HEAD}
    emp = {"lft": 10}

    def test_manager_reads_all(self):
        self.assertTrue(D.can_read({"ec_doc_state": C.S_DRAFT}, ISO, True, None, []))

    def test_company_wide_needs_employee_profile(self):
        self.assertTrue(D.can_read(self.pub, "a@x", False, self.emp, []))
        self.assertFalse(D.can_read(self.pub, "khach@x", False, None, []))

    def test_scope_parent_includes_child(self):
        d = dict(self.pub, ec_company_wide=0)
        self.assertTrue(D.can_read(d, "a@x", False, {"lft": 12}, [(10, 20)]))
        self.assertFalse(D.can_read(d, "a@x", False, {"lft": 25}, [(10, 20)]))
        self.assertFalse(D.can_read(d, "a@x", False, {"lft": None}, [(10, 20)]))

    def test_draft_only_people_involved(self):
        d = dict(self.pub, ec_current_version="", ec_doc_state=C.S_DRAFT)
        self.assertFalse(D.can_read(d, "a@x", False, self.emp, []))
        self.assertTrue(D.can_read(d, DRAFTER, False, None, []))
        self.assertTrue(D.can_read(d, HEAD, False, None, []))

    def test_expired_hidden(self):
        d = dict(self.pub, ec_doc_state=C.S_EXPIRED)
        self.assertFalse(D.can_read(d, "a@x", False, self.emp, []))

    def test_new_draft_keeps_effective_readable(self):
        d = dict(self.pub, ec_doc_state=C.S_DRAFT)       # dang soan 2.0, 1.0 van hieu luc
        self.assertTrue(D.can_read(d, "a@x", False, self.emp, []))

    def test_write(self):
        self.assertTrue(D.can_write({"ec_doc_state": C.S_DRAFT, "ec_drafter": DRAFTER}, DRAFTER, False))
        self.assertFalse(D.can_write({"ec_doc_state": C.S_HEAD, "ec_drafter": DRAFTER}, DRAFTER, False))
        self.assertTrue(D.can_write({"ec_doc_state": C.S_HEAD, "ec_dept_head": HEAD}, HEAD, False))
        self.assertFalse(D.can_write({"ec_doc_state": C.S_PUBLISHED, "ec_dept_head": HEAD}, HEAD, False))
        self.assertTrue(D.can_write({"ec_doc_state": C.S_PUBLISHED}, ISO, True))


# =========================================================================== service
class TestSiteStateNames(unittest.TestCase):
    """Tren site doc luu "Nhap" / "Cho Truong bo phan" (Workflow State co san, collation bo dau)."""
    NHAP, CHO_TBP = "Nhap", "Cho Truong bo phan"

    def test_norm(self):
        self.assertTrue(D.is_state(self.NHAP, C.S_DRAFT))
        self.assertTrue(D.is_state(self.CHO_TBP, C.S_HEAD))
        self.assertTrue(D.is_state("HẾT  HIỆU LỰC", C.S_EXPIRED))
        self.assertTrue(D.is_state("Cho Tong giam doc", C.S_CEO))
        self.assertFalse(D.is_state(self.NHAP, C.S_HEAD))

    def test_write_with_site_names(self):
        self.assertTrue(D.can_write({"ec_doc_state": self.NHAP, "ec_drafter": DRAFTER}, DRAFTER, False))
        self.assertTrue(D.can_write({"ec_doc_state": self.CHO_TBP, "ec_dept_head": HEAD}, HEAD, False))
        self.assertFalse(D.can_write({"ec_doc_state": self.CHO_TBP, "ec_drafter": DRAFTER}, DRAFTER, False))

    def test_kinds_with_site_names(self):
        self.assertEqual(D.transition_kind("Ban hành", self.NHAP), "new_draft")
        self.assertEqual(D.transition_kind(self.NHAP, self.CHO_TBP), "move")
        self.assertIsNone(D.transition_kind(self.NHAP, C.S_DRAFT))
        self.assertEqual(D.transition_kind("Cho Ban ISO", "Ban hanh"), "publish")

    def test_read_hides_expired_any_spelling(self):
        d = {"ec_current_version": "1.0", "ec_doc_state": "Het hieu luc", "ec_company_wide": 1}
        self.assertFalse(D.can_read(d, "a@x", False, {"lft": 1}, []))

    def test_full_flow_with_site_names(self):
        iso = Repo()
        doc = new_doc(ec_doc_state=self.NHAP)
        move(doc, self.CHO_TBP, iso)
        move(doc, C.S_ISO, Repo(user=HEAD, home=iso.home))
        move(doc, C.S_CEO, iso)
        move(doc, C.S_PUBLISHED, Repo(user=CEO, home=iso.home))
        self.assertEqual(doc.ec_current_version, "1.0")
        self.assertEqual(len(iso.home.rows), 1)


class TestPublishFlow(unittest.TestCase):
    def test_validate_fills_head_and_rejects_bad(self):
        doc = new_doc(ec_doc_code=" qt-tckt-03 ")
        S.on_validate(doc, Repo())
        self.assertEqual(doc.ec_doc_code, "QT-TCKT-03")
        self.assertEqual(doc.ec_dept_head, HEAD)
        with self.assertRaises(DocError):
            S.on_validate(new_doc(ec_company_wide=0, ec_scope_departments=[Doc(department="Service - EC")]),
                          Repo())          # tich thong bao ma khong toan cong ty

    def test_first_publish_major(self):
        iso = Repo()
        doc = new_doc(ec_draft_pdf="/private/files/a.pdf", ec_mermaid="flowchart TD\nS1-->S2")
        publish_major(doc, iso, Repo(user=CEO, home=iso.home))
        self.assertEqual(doc.ec_current_version, "1.0")
        self.assertEqual(doc.ec_effective_from, TODAY)
        self.assertEqual(doc.ec_approver, CEO)
        self.assertEqual(doc.ec_next_review, dt.date(2027, 10, 5))
        self.assertEqual(len(doc.ec_revisions), 1)
        r = doc.ec_revisions[0]
        self.assertEqual((r.version, r.status, r.change_kind), ("1.0", C.REV_EFFECTIVE, C.KIND_MAJOR))
        self.assertEqual((r.reviewer, r.approver, r.drafter), (ISO, CEO, DRAFTER))
        self.assertEqual(r.pdf, "/private/files/a.pdf")
        self.assertEqual(r.mermaid, "flowchart TD\nS1-->S2")
        self.assertEqual(r.summary, "Ban hành lần đầu trên ERP")
        self.assertEqual(doc.ec_draft_pdf, "")              # ban nhap da chuyen vao lich su
        self.assertEqual(doc.ec_change_summary, "")
        self.assertEqual(doc.ec_iso_reviewer, "")

    def test_minor_revision_keeps_old_version(self):
        iso = Repo()
        doc = new_doc()
        publish_major(doc, iso, Repo(user=CEO, home=iso.home))
        move(doc, C.S_DRAFT, iso)                             # Soan phien ban moi
        doc.update(ec_change_kind=C.KIND_MINOR, ec_change_summary="Sửa bước 3")
        move(doc, C.S_HEAD, iso)
        move(doc, C.S_ISO, Repo(user=HEAD, home=iso.home))
        move(doc, C.S_PUBLISHED, iso)                         # nho: Ban ISO ban hanh, khong TGD
        self.assertEqual(doc.ec_current_version, "1.1")
        self.assertEqual([(r.version, r.status) for r in doc.ec_revisions],
                         [("1.0", C.REV_EXPIRED), ("1.1", C.REV_EFFECTIVE)])
        self.assertEqual(doc.ec_revisions[0].effective_to, dt.date(2026, 10, 4))
        self.assertEqual(doc.ec_revisions[1].approver, ISO)
        self.assertEqual(doc.ec_revisions[1].reviewer, ISO)

    def test_explicit_draft_version(self):
        iso = Repo()
        doc = new_doc(ec_draft_version="3.0")                # nhap file cu dang 3.0
        publish_major(doc, iso, Repo(user=CEO, home=iso.home))
        self.assertEqual(doc.ec_current_version, "3.0")

    def test_withdraw(self):
        iso = Repo()
        doc = new_doc()
        publish_major(doc, iso, Repo(user=CEO, home=iso.home))
        move(doc, C.S_WITHDRAW, iso)
        move(doc, C.S_EXPIRED, Repo(user=CEO, home=iso.home))
        self.assertEqual(doc.ec_revisions[0].status, C.REV_WITHDRAWN)
        self.assertEqual(doc.ec_revisions[0].effective_to, TODAY)
        self.assertEqual([r["published"] for r in iso.home.rows.values()], [0])   # rut thong bao


class TestHomeAnnouncement(unittest.TestCase):
    def test_created_on_publish_with_spec_fields(self):
        iso = Repo()
        ceo = Repo(user=CEO, home=iso.home)
        doc = new_doc()
        publish_major(doc, iso, ceo)
        rows = list(iso.home.rows.values())
        self.assertEqual(len(rows), 1)
        a = rows[0]
        self.assertEqual(a["title"], "Ban hành: QT-TCKT-03 Quy trình thanh toán (v1.0)")
        self.assertEqual(a["category"], "Chính sách")
        self.assertEqual(a["display"], "Ảnh + nội dung")
        self.assertEqual((a["start_date"], a["end_date"]), (TODAY, dt.date(2026, 10, 11)))
        self.assertEqual((a["link"], a["link_label"]), ("/tai-lieu/QT-TCKT-03", "Xem tài liệu →"))
        self.assertEqual(a["summary"], "Đề nghị thanh toán đi qua ERP.")
        self.assertEqual((a["source_doctype"], a["source_name"], a["source_version"]),
                         (C.QP, "QT-TCKT-03", "1.0"))
        self.assertEqual(ceo.links, [("QT-TCKT-03", "1.0", "HA-001")])

    def test_not_before_publish(self):
        iso = Repo()
        doc = new_doc()
        move(doc, C.S_HEAD, iso)
        move(doc, C.S_ISO, Repo(user=HEAD, home=iso.home))
        move(doc, C.S_CEO, iso)
        self.assertEqual(iso.home.rows, {})

    def test_idempotent_per_version(self):
        """Spec muc 3: luu lai / chay lai cung phien ban -> khong tao trung; phien ban moi -> moi."""
        iso = Repo()
        doc = new_doc()
        publish_major(doc, iso, Repo(user=CEO, home=iso.home))
        # job / workflow chay lai cung phien ban
        doc.flags.ec_published_version = "1.0"
        doc.flags.ec_published_summary = ""
        self.assertEqual(S.on_update(doc, iso), "HA-001")
        doc.flags.before = C.S_PUBLISHED           # luu lai khi da Ban hanh: khong doi gi
        S.on_validate(doc, iso)
        S.on_update(doc, iso)
        self.assertEqual(len(iso.home.rows), 1)
        self.assertEqual(len(doc.ec_revisions), 1)
        # phien ban moi -> thong bao moi, khong sua thong bao cu
        move(doc, C.S_DRAFT, iso)
        doc.update(ec_change_kind=C.KIND_MINOR)
        move(doc, C.S_HEAD, iso)
        move(doc, C.S_ISO, Repo(user=HEAD, home=iso.home))
        move(doc, C.S_PUBLISHED, iso)
        self.assertEqual(sorted(r["source_version"] for r in iso.home.rows.values()), ["1.0", "1.1"])
        self.assertEqual(iso.home.rows["HA-001"]["title"], "Ban hành: QT-TCKT-03 Quy trình thanh toán (v1.0)")

    def test_failure_does_not_block_publish(self):
        """Spec muc 4: loi tao thong bao -> van ban hanh, rollback phan thong bao, ghi Error Log."""
        iso = Repo(home=HomeRepo(fail=True))
        ceo = Repo(user=CEO, home=iso.home)
        doc = new_doc()
        publish_major(doc, iso, ceo)
        self.assertEqual(doc.ec_doc_state, C.S_PUBLISHED)
        self.assertEqual(doc.ec_current_version, "1.0")
        self.assertEqual(len(doc.ec_revisions), 1)
        self.assertEqual(iso.home.rows, {})                 # khong de lai thong bao do dang
        self.assertEqual(iso.home.errors, ["home_today.publish_from_source"])
        self.assertEqual(ceo.links, [])

    def test_unticked_or_department_scope_no_announcement(self):
        """Spec muc 5: khong tich / khong toan cong ty -> khong co thong bao."""
        iso = Repo()
        doc = new_doc(ec_notify_home=0)
        publish_major(doc, iso, Repo(user=CEO, home=iso.home))
        self.assertEqual(iso.home.rows, {})
        iso2 = Repo()
        doc2 = new_doc(ec_notify_home=0, ec_company_wide=0,
                       ec_scope_departments=[Doc(department="Finance & Accounting - EC")])
        publish_major(doc2, iso2, Repo(user=CEO, home=iso2.home))
        self.assertEqual(doc2.ec_current_version, "1.0")
        self.assertEqual(iso2.home.rows, {})
        # co gang tich sau khi da ban hanh pham vi phong ban -> bi chan
        doc2.ec_notify_home = 1
        with self.assertRaises(DocError):
            S.on_validate(doc2, iso2)

    def test_summary_falls_back_to_change_summary(self):
        iso = Repo()
        doc = new_doc(ec_notify_summary="")
        publish_major(doc, iso, Repo(user=CEO, home=iso.home))
        self.assertEqual(list(iso.home.rows.values())[0]["summary"], "Ban hành lần đầu trên ERP")


# =========================================================================== workflow + fixtures
class NotifyRepo:
    """Gia repository cho notify.state_changed."""

    def __init__(self, doc, iso=("iso@x", "dong@x"), ceo=("ceo@x",), note="", fail_for=(), disabled=False):
        self.doc, self.iso, self.ceo, self.note = doc, list(iso), list(ceo), note
        self.fail_for, self.disabled = set(fail_for), disabled
        self.sent, self.errors = [], []

    def conf_flag(self, key):
        return self.disabled

    def get_doc_any(self, name):
        return self.doc if self.doc and self.doc.name == name else None

    def role_users(self, role):
        return self.iso if role == C.ROLE_ISO else self.ceo

    def last_note(self, name, actor):
        return self.note

    def notify(self, event, to, title, message, url, name, actor, key):
        if to in self.fail_for:
            raise RuntimeError("smtp")
        self.sent.append({"event": event, "to": to, "title": title, "message": message, "url": url, "key": key})

    def log_error(self, title):
        self.errors.append(title)


class TestNotify(unittest.TestCase):
    def doc(self, **kw):
        return new_doc(ec_dept_head=HEAD, **kw)

    def plan(self, before, after, actor=DRAFTER, **kw):
        return D.notify_plan(before, after, self.doc(**kw), actor, ["iso@x", "dong@x"], ["ceo@x"])

    def test_each_waiting_state_goes_to_whoever_clicks_next(self):
        self.assertEqual([n["to"] for n in self.plan(C.S_DRAFT, C.S_HEAD)], [HEAD])
        self.assertEqual([n["to"] for n in self.plan(C.S_HEAD, C.S_ISO, actor=HEAD)], ["iso@x", "dong@x"])
        self.assertEqual([n["to"] for n in self.plan(C.S_ISO, C.S_CEO, actor="iso@x")], ["ceo@x"])
        self.assertEqual([n["to"] for n in self.plan(C.S_PUBLISHED, C.S_WITHDRAW, actor="iso@x")], ["ceo@x"])
        n = self.plan(C.S_DRAFT, C.S_HEAD)[0]
        self.assertEqual(n["event"], "approval_required")
        self.assertEqual(n["url"], "/tai-lieu/quan-ly?loc=cho-toi&ma=QT-TCKT-03")
        self.assertIn("QT-TCKT-03", n["title"])

    def test_no_head_falls_back_to_iso_and_skips_actor(self):
        d = new_doc(ec_dept_head="")
        self.assertEqual([n["to"] for n in D.notify_plan(C.S_DRAFT, C.S_HEAD, d, "iso@x", ["iso@x", "dong@x"], [])],
                         ["dong@x"])                       # nguoi bam la Ban ISO: khong tu bao minh

    def test_return_and_publish_go_to_drafter(self):
        r = D.notify_plan(C.S_CEO, C.S_DRAFT, self.doc(), "ceo@x", [], [], "Thiếu bước đối chiếu")
        self.assertEqual((r[0]["to"], r[0]["url"]), (DRAFTER, "/tai-lieu/soan?ma=QT-TCKT-03"))
        self.assertIn("Thiếu bước đối chiếu", r[0]["message"])
        p = D.notify_plan(C.S_CEO, C.S_PUBLISHED, self.doc(ec_current_version="1.0"), "ceo@x", [], [])
        self.assertEqual((p[0]["to"], p[0]["event"], p[0]["url"]), (DRAFTER, "mention", "/tai-lieu/QT-TCKT-03"))

    def test_quiet_cases(self):
        self.assertEqual(self.plan(None, C.S_DRAFT), [])               # tao moi
        self.assertEqual(self.plan("Nhap", C.S_DRAFT), [])             # cung trang thai (ten site)
        self.assertEqual(self.plan(C.S_HEAD, "Cho Truong bo phan"), [])  # luu lai khi dang cho TBP
        self.assertEqual(self.plan(C.S_PUBLISHED, C.S_DRAFT, actor="iso@x"), [])   # soan phien ban moi
        self.assertEqual(D.notify_plan(C.S_DRAFT, C.S_HEAD, self.doc(), HEAD, [], []), [])  # TBP tu gui

    def test_site_state_names(self):
        self.assertEqual([n["to"] for n in self.plan("Nhap", "Cho Truong bo phan")], [HEAD])

    def test_job_sends_and_survives_one_failure(self):
        d = self.doc(ec_doc_state=C.S_ISO)
        r = NotifyRepo(d, fail_for={"iso@x"})
        out = N.state_changed(d.name, C.S_HEAD, C.S_ISO, HEAD, "t1", repo=r)
        self.assertEqual(out, {"sent": 1, "failed": 1})
        self.assertEqual([x["to"] for x in r.sent], ["dong@x"])
        self.assertEqual(r.sent[0]["key"], "iso|QT-TCKT-03|%s|t1|dong@x" % D.norm_state(C.S_ISO))
        self.assertEqual(r.errors, ["iso_docs.notify"])

    def test_job_skips(self):
        d = self.doc(ec_doc_state=C.S_CEO)
        self.assertEqual(N.state_changed(d.name, C.S_HEAD, C.S_ISO, HEAD, repo=NotifyRepo(d)), {"skipped": "moved"})
        self.assertEqual(N.state_changed("QT-XX-01", C.S_HEAD, C.S_ISO, HEAD, repo=NotifyRepo(d)), {"skipped": "missing"})
        self.assertEqual(N.state_changed(d.name, C.S_ISO, C.S_CEO, HEAD, repo=NotifyRepo(d, disabled=True)),
                         {"skipped": "disabled"})

    def test_job_passes_note_on_return(self):
        d = self.doc(ec_doc_state="Nhap")
        r = NotifyRepo(d, note="Sửa bước 3")
        N.state_changed(d.name, C.S_HEAD, C.S_DRAFT, HEAD, repo=r)
        self.assertIn("Sửa bước 3", r.sent[0]["message"])

    def test_service_enqueues_on_transition_only(self):
        repo = Repo(user=DRAFTER)
        doc = new_doc()
        move(doc, C.S_HEAD, repo)
        self.assertEqual(repo.enqueued, [("QT-TCKT-03", C.S_DRAFT, C.S_HEAD, DRAFTER)])
        doc.flags.before = doc.get(C.STATE_FIELD)
        S.on_validate(doc, repo); S.on_update(doc, repo)          # luu lai, khong doi trang thai
        self.assertEqual(len(repo.enqueued), 1)

    def test_enqueue_failure_does_not_block(self):
        repo = Repo(user=DRAFTER)
        repo.enqueue_fails = True
        doc = new_doc()
        move(doc, C.S_HEAD, repo)
        self.assertEqual(doc.get(C.STATE_FIELD), C.S_HEAD)
        self.assertEqual(repo.errors, ["iso_docs.enqueue_notify"])

    def test_links_never_desk(self):
        for b, a in ((C.S_DRAFT, C.S_HEAD), (C.S_HEAD, C.S_ISO), (C.S_ISO, C.S_CEO), (C.S_CEO, C.S_DRAFT),
                     (C.S_CEO, C.S_PUBLISHED), (C.S_PUBLISHED, C.S_WITHDRAW)):
            for n in D.notify_plan(b, a, self.doc(), "x@x", ["iso@x"], ["ceo@x"]):
                self.assertTrue(n["url"].startswith("/tai-lieu"), n["url"])


class TestWorkflowSpec(unittest.TestCase):
    def test_states_complete(self):
        self.assertEqual(tuple(s for s, _ in W.STATES), C.STATES)
        self.assertEqual(W.STATES[0][0], C.S_DRAFT)              # trang thai dau = Nhap
        for s in C.STATES:
            self.assertIn(s, {x for x, _ in W.EDIT_ROLES}, s)

    def test_transitions_use_known_states(self):
        for frm, action, to, role, cond in W.TRANSITIONS:
            self.assertIn(frm, C.STATES)
            self.assertIn(to, C.STATES)
            self.assertIn(role, (C.ROLE_ISO, C.ROLE_CEO, C.ROLE_EMPLOYEE))
            if role == C.ROLE_EMPLOYEE:
                self.assertTrue(cond, "Employee phai co dieu kien tren doc: %s" % action)

    def test_flow_order(self):
        """Truong BP -> Ban ISO -> TGD -> ban hanh; sua nho bo TGD; chi TGD duyet ban lon."""
        to_pub = [(f, r, c) for f, _a, t, r, c in W.TRANSITIONS if t == C.S_PUBLISHED and f != C.S_WITHDRAW]
        self.assertEqual(sorted((f, r) for f, r, _ in to_pub), sorted([(C.S_CEO, C.ROLE_CEO), (C.S_ISO, C.ROLE_ISO)]))
        iso_pub = [c for f, r, c in to_pub if f == C.S_ISO][0]
        self.assertTrue(self._eval(iso_pub, ec_change_kind="Nhỏ", ec_current_version="1.0"))
        self.assertFalse(self._eval(iso_pub, ec_change_kind="Nhỏ", ec_current_version=""))
        self.assertFalse(self._eval(iso_pub, ec_change_kind="Lớn", ec_current_version="1.0"))
        to_ceo = [c for f, _a, t, _r, c in W.TRANSITIONS if t == C.S_CEO][0]
        self.assertTrue(self._eval(to_ceo, ec_change_kind="Nhỏ", ec_current_version=""))
        self.assertTrue(self._eval(to_ceo, ec_change_kind="Lớn", ec_current_version="1.0"))
        self.assertFalse(self._eval(to_ceo, ec_change_kind="Nhỏ", ec_current_version="1.0"))

    def test_head_conditions(self):
        self.assertTrue(self._eval(W.IS_HEAD, ec_dept_head=HEAD, user=HEAD))
        self.assertFalse(self._eval(W.IS_HEAD, ec_dept_head=HEAD, user=DRAFTER))
        self.assertTrue(self._eval(W.NO_HEAD, ec_dept_head=None))

    @staticmethod
    def _eval(cond, user="x", **doc):
        fr = types.SimpleNamespace(session=types.SimpleNamespace(user=user))
        return bool(eval(cond, {"__builtins__": {}}, {"doc": types.SimpleNamespace(**{
            "ec_change_kind": "", "ec_current_version": "", "ec_dept_head": None, **doc}), "frappe": fr}))


class TestFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(APP, "fixtures", "custom_field.json"), encoding="utf-8") as fh:
            cls.rows = [r for r in json.load(fh) if r["dt"] == C.QP]
        with open(os.path.join(APP, "hooks.py"), encoding="utf-8") as fh:
            cls.hooks = fh.read()

    def test_notify_fields(self):
        """Spec muc 1: ec_notify_home / ec_notify_summary / ec_home_announcement."""
        by = {r["fieldname"]: r for r in self.rows}
        self.assertEqual(by["ec_notify_home"]["fieldtype"], "Check")
        self.assertEqual(by["ec_notify_home"]["label"], "Thông báo lên trang chủ khi ban hành")
        self.assertIn("ec_company_wide", by["ec_notify_home"]["depends_on"])
        self.assertEqual(by["ec_notify_summary"]["fieldtype"], "Small Text")
        self.assertEqual(by["ec_home_announcement"]["options"], C.HOME_DT)
        self.assertEqual(by["ec_home_announcement"]["read_only"], 1)

    def test_every_field_in_hooks_filter_and_chain_valid(self):
        names = {r["fieldname"] for r in self.rows}
        native = {"quality_procedure_name", "process_owner", "process_owner_full_name"}
        for r in self.rows:
            self.assertIn('"%s"' % r["name"], self.hooks, r["name"])
            self.assertTrue(r["fieldname"].startswith("ec_"))
            self.assertIn(r["insert_after"], names | native, r["name"])
        self.assertEqual(len(names), len(self.rows))

    def test_select_options_match_constants(self):
        by = {r["fieldname"]: r for r in self.rows}
        self.assertEqual(by["ec_doc_type"]["options"].split("\n"), [n for _p, n in C.DOC_TYPES])
        self.assertEqual([x for x in by["ec_change_kind"]["options"].split("\n") if x], list(C.KINDS))
        self.assertEqual([x for x in by["ec_source"]["options"].split("\n") if x], list(C.SOURCES))
        self.assertEqual(by[C.STATE_FIELD]["options"], "Workflow State")

    def test_revision_doctype_matches_service(self):
        with open(os.path.join(APP, "iso_docs", "doctype", "ec_document_revision",
                               "ec_document_revision.json"), encoding="utf-8") as fh:
            dt_ = json.load(fh)
        cols = {f["fieldname"] for f in dt_["fields"]}
        for _f, col in S._DRAFT_TO_ROW:
            self.assertIn(col, cols)
        row = D.publish_plan([], "", "", "", TODAY, ISO)["row"]
        for k in row:
            self.assertIn(k, cols, k)
        status = [f for f in dt_["fields"] if f["fieldname"] == "status"][0]
        self.assertEqual(status["options"].split("\n"), list(C.REV_STATUSES))

    def test_hooks_registered(self):
        for s in ('permission_query_conditions["Quality Procedure"]', 'has_permission["Quality Procedure"]',
                  "ecentric_workspace.iso_docs.events.validate", "ecentric_workspace.iso_docs.events.on_update"):
            self.assertIn(s, self.hooks)
        with open(os.path.join(APP, "patches.txt"), encoding="utf-8") as fh:
            self.assertIn("ecentric_workspace.iso_docs.patches.p001_setup", fh.read())
        with open(os.path.join(APP, "modules.txt"), encoding="utf-8") as fh:
            self.assertIn("ISO Docs", fh.read().splitlines())

    def test_popup_untouched(self):
        """Spec muc 6: module khong goi toi popup / trang chu, chi qua announce_service."""
        src = ""
        for root, _d, files in os.walk(os.path.join(APP, "iso_docs")):
            for f in files:
                if f.endswith(".py") and "tests" not in root:
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        src += fh.read()
        self.assertNotIn("ec_home_popup", src)
        self.assertNotIn("home_today.service", src)
        self.assertNotIn("home_today import service", src)
        self.assertTrue(re.search(r"announce_service\.publish_from_source", src))


if __name__ == "__main__":
    unittest.main()
