# Copyright (c) 2026, eCentric and contributors
"""Thu vien tai lieu ISO - trang /tai-lieu, /tai-lieu/<ma>, /tai-lieu/quan-ly + nhap goi.
Chay THAT package / view / library / manage tren repo gia va render 3 template bang jinja2.

    python -m unittest ecentric_workspace.iso_docs.tests.test_pages
"""
import copy
import datetime as dt
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
APP = os.path.join(ROOT, "ecentric_workspace")
sys.path.insert(0, ROOT)

from ecentric_workspace.iso_docs import constants as C  # noqa: E402
from ecentric_workspace.iso_docs import library as L  # noqa: E402
from ecentric_workspace.iso_docs import manage as M  # noqa: E402
from ecentric_workspace.iso_docs import package as P  # noqa: E402
from ecentric_workspace.iso_docs import view as V  # noqa: E402
from ecentric_workspace.iso_docs.errors import DocError, Forbidden, NotFound  # noqa: E402
from ecentric_workspace.iso_docs.tests.test_iso_docs import Doc  # noqa: E402

TODAY = dt.date(2026, 10, 5)
ISO, HEAD, EMP = "iso@x", "phuong@x", "nv@x"
FIN, OPS = "Finance & Accounting - EC", "Operation & Data & System - EC"
DEPTS = [FIN, OPS, "Service - EC", "Human Resources - EC"]
with open(os.path.join(os.path.dirname(__file__), "fixtures", "goi_QT-TCKT-03.json"), encoding="utf-8") as fh:
    PKG = json.load(fh)
STEPS = P.steps_payload(PKG, {"BM-01": "/private/files/bm01.xlsx"})
EVIL = '<script>alert("x")</script>'


def rev(version, status, since, until=None, **kw):
    r = Doc(version=version, status=status, effective_from=since, effective_to=until, summary="",
            approver="tgd@x", pdf="/private/files/%s.pdf" % version, docx="", steps_json=STEPS,
            mermaid=PKG["so_do_mermaid"], idx=0)
    r.update(kw)
    return r


def qp(code, name, dept, state, current="", revs=None, **kw):
    d = Doc(name=code, ec_doc_code=code, quality_procedure_name=name, ec_doc_type="Quy trình",
            ec_department=dept, ec_doc_state=state, ec_current_version=current,
            ec_effective_from=dt.date(2025, 8, 25) if current else None,
            ec_next_review=dt.date(2026, 8, 25) if current else None, ec_draft_version="",
            ec_change_kind="", ec_change_summary="", ec_drafter="soan@x", ec_dept_head=HEAD,
            ec_company_wide=1, ec_parent_doc="", ec_revisions=revs or [], modified=None)
    for i, r in enumerate(d["ec_revisions"]):
        r["idx"] = i + 1
    d.update(kw)
    return d


class Repo:
    def __init__(self, docs, user=ISO, manager=True, trans=None):
        self.docs = {d.name: d for d in docs}
        self.user, self.manager = user, manager
        self.trans = trans or {}
        self.seen, self.applied, self.comments, self.files, self.inserted, self.updated = [], [], [], [], [], []

    # doc
    def today(self):
        return TODAY

    def is_manager(self, user):
        return self.manager

    def list_docs(self):
        return [Doc({k: v for k, v in d.items() if k != "ec_revisions"}) for d in self.docs.values()]

    def revisions(self, names, effective_only=False):
        out = []
        for n in names:
            for r in self.docs[n].ec_revisions:
                if not effective_only or r.status == C.REV_EFFECTIVE:
                    out.append(Doc(r, parent=n))
        return out

    def exists(self, code):
        return code in self.docs

    def get_doc(self, code):
        return self.docs.get(code)

    def transitions(self, doc):
        return [{"action": a, "next_state": n} for a, n in self.trans.get(doc.name, [])]

    def full_names(self, users):
        return {u: u.split("@")[0].title() for u in users if u}

    def mark_seen(self, code, user, version):
        self.seen.append((code, user, version))

    def departments(self):
        return DEPTS

    # ghi
    def apply_action(self, doc, action):
        self.applied.append((doc.name, action))
        to = dict(self.trans.get(doc.name, [])).get(action)
        if action == "Soạn phiên bản mới":
            to = C.S_DRAFT
        doc[C.STATE_FIELD] = to
        return doc

    def add_comment(self, name, text):
        self.comments.append((name, text))

    def save_file(self, name, fn, content):
        self.files.append((name, fn, len(content)))
        return "/private/files/" + fn

    def insert_doc(self, fields):
        self.inserted.append(dict(fields))
        f = dict(fields)
        f.pop("scope_departments", None)
        self.docs[fields["ec_doc_code"]] = qp(fields["ec_doc_code"], fields["quality_procedure_name"],
                                              fields["ec_department"], C.S_DRAFT, **{k: v for k, v in f.items()
                                              if k not in ("ec_doc_code", "quality_procedure_name", "ec_department")})

    def update_draft(self, code, fields):
        self.updated.append((code, dict(fields)))
        self.docs[code].update({k: v for k, v in fields.items() if k != "scope_departments"})


def seeded(**kw):
    t03 = qp("QT-TCKT-03", "Thanh toán", FIN, "Ban hành", "2.0",
             [rev("1.0", C.REV_EXPIRED, dt.date(2025, 3, 3), dt.date(2025, 8, 24), summary="Tạo mới"),
              rev("2.0", C.REV_EFFECTIVE, dt.date(2025, 8, 25), summary="Thêm bước kiểm tra")])
    t01 = qp("QT-TCKT-01", "Mua hàng", FIN, "Cho Truong bo phan", "1.0",
             [rev("1.0", C.REV_EFFECTIVE, dt.date(2025, 1, 1))], ec_draft_version="1.1",
             ec_change_kind="Nhỏ", ec_change_summary="Sửa mục 6")
    iso3 = qp("QT-ISO-03", "Quản lý tài liệu", OPS, "Ban hành", "3.0",
              [rev("3.0", C.REV_EFFECTIVE, dt.date(2025, 5, 5))], ec_next_review=dt.date(2026, 9, 1))
    new = qp("QT-NS-02", "Ký hợp đồng lao động", "Human Resources - EC", "Nhap")
    old = qp("QT-DV-09", "Quy trình cũ", "Service - EC", "Hết hiệu lực", "1.0",
             [rev("1.0", C.REV_WITHDRAWN, dt.date(2024, 1, 1), dt.date(2026, 1, 1))])
    return Repo([t03, t01, iso3, new, old], **kw)


# =========================================================================== goi
class TestPackage(unittest.TestCase):
    def test_example_package_is_valid(self):
        self.assertEqual(P.errors(PKG, DEPTS), [])

    def mutate(self, fn):
        g = copy.deepcopy(PKG)
        fn(g)
        return P.errors(g, DEPTS)

    def test_rejects(self):
        cases = {
            "loai": lambda g: g.update(loai="Sổ tay"),
            "phong_ban": lambda g: g.update(phong_ban="Finance"),
            "kieu_sua": lambda g: g.update(kieu_sua="vua"),
            "tom_tat_thay_doi": lambda g: g.update(tom_tat_thay_doi=""),
            "vai_tro": lambda g: g["buoc"][0].update(A="XX"),
            "thieu nut": lambda g: g.update(so_do_mermaid=g["so_do_mermaid"].replace('S7[', 'S8[')),
            "click": lambda g: g.update(so_do_mermaid=g["so_do_mermaid"] + "\nclick S1 call x()"),
            "flowchart TD": lambda g: g.update(so_do_mermaid="graph LR\nS1-->S2"),
            "giu cho": lambda g: g["buoc"][0].update(dien_giai="Gửi Trưởng phòng ABC duyệt"),
            "pham vi": lambda g: g.update(pham_vi_doc={"ca_cong_ty": False, "phong_ban": []}),
            "thong bao": lambda g: g.update(pham_vi_doc={"ca_cong_ty": False, "phong_ban": [FIN]},
                                            thong_bao_trang_chu=True),
            "ma": lambda g: g.update(ma_tai_lieu="QT-03"),
            "form_erp": lambda g: g["buoc"][0].update(form_erp="https://x"),
            "bieu_mau": lambda g: g["buoc"][0].update(bieu_mau=["BM-99"]),
        }
        for k, fn in cases.items():
            self.assertTrue(self.mutate(fn), k)

    def test_new_package_needs_code(self):
        g = copy.deepcopy(PKG)
        g.update(loai_goi="moi", ma_tai_lieu="", ma_de_xuat="")
        self.assertTrue(any("mã" in e for e in P.errors(g, DEPTS)))
        self.assertEqual(P.errors(g, DEPTS, "QT-TCKT-09"), [])

    def test_to_fields(self):
        f = P.to_fields(PKG, "QT-TCKT-03", ISO)
        self.assertEqual(f["ec_change_kind"], C.KIND_MINOR)
        self.assertEqual(f["ec_source"], "Gói từ Claude")
        self.assertEqual(f["ec_company_wide"], 1)
        self.assertEqual(f["scope_departments"], [])
        self.assertTrue(f["ec_mermaid"].startswith("flowchart TD"))
        self.assertIn(f["ec_doc_type"], [n for _p, n in C.DOC_TYPES])
        g = dict(PKG, pham_vi_doc={"ca_cong_ty": False, "phong_ban": [FIN]}, thong_bao_trang_chu=True)
        f2 = P.to_fields(g, "QT-TCKT-03", ISO)
        self.assertEqual((f2["ec_company_wide"], f2["ec_notify_home"], f2["scope_departments"]), (0, 0, [FIN]))

    def test_steps_payload_keeps_form_urls(self):
        data = json.loads(STEPS)
        self.assertEqual(data["bieu_mau"][0]["url"], "/private/files/bm01.xlsx")
        self.assertEqual(len(data["buoc"]), len(PKG["buoc"]))


# =========================================================================== view
class TestView(unittest.TestCase):
    def test_flow_roles_highlight_a_and_r(self):
        f = V.flow(STEPS)
        self.assertEqual([x for x, _ in f["facts"]], ["Dùng khi", "Bạn chuẩn bị", "Kết quả"])
        for r in f["roles"]:
            for sid in r["nodes"]:
                b = next(s for s in PKG["buoc"] if s["id"] == sid)
                self.assertTrue(b["A"] == r["ma"] or r["ma"] in b["R"])
        self.assertTrue(all("who" in s for s in f["steps"]))

    def test_flow_tolerates_garbage(self):
        self.assertEqual(V.flow("không phải json")["roles"], [])
        self.assertEqual(V.flow(None)["steps"], [])

    def test_labels(self):
        self.assertEqual(V.state_label("Nhap"), "Nháp")
        self.assertEqual(V.state_label("Cho Truong bo phan"), "Chờ trưởng bộ phận")
        self.assertTrue(V.is_pending("Cho Truong bo phan"))
        self.assertEqual(V.code_dept("QT-ISO-03"), "ISO")
        self.assertEqual(V.code_dept("BM-QT-TCKT-03-01"), "TCKT")
        self.assertEqual(V.fdate(dt.date(2026, 1, 2)), "02/01/2026")

    def test_review_due(self):
        d = {"ec_current_version": "1.0", "ec_doc_state": "Ban hành"}
        self.assertEqual(V.review_due(dict(d, ec_next_review=dt.date(2026, 10, 1)), TODAY), "qua-han")
        self.assertEqual(V.review_due(dict(d, ec_next_review=dt.date(2026, 10, 30)), TODAY), "sap-den-han")
        self.assertEqual(V.review_due(dict(d, ec_next_review=dt.date(2027, 1, 1)), TODAY), "")
        self.assertEqual(V.review_due(dict(d, ec_next_review=dt.date(2026, 1, 1), ec_doc_state="Het hieu luc"), TODAY), "")


# =========================================================================== thu vien
class TestLibrary(unittest.TestCase):
    def test_only_effective_docs(self):
        ctx = L.library_page(EMP, repo=seeded())
        self.assertEqual(ctx["total"], 3)          # bo ban nhap moi + tai lieu het hieu luc
        self.assertEqual([d["label"] for d in ctx["depts"]], ["Finance & Accounting", "Operation & Data & System"])
        self.assertEqual(ctx["dept"], FIN)
        codes = [c["code"] for _l, rows in ctx["groups"] for c in rows]
        self.assertEqual(codes, ["QT-TCKT-01", "QT-TCKT-03"])

    def test_drafting_flag(self):
        ctx = L.library_page(EMP, repo=seeded())
        flags = {c["code"]: c["drafting"] for _l, rows in ctx["groups"] for c in rows}
        self.assertEqual(flags, {"QT-TCKT-01": True, "QT-TCKT-03": False})

    def test_views(self):
        r = seeded()
        self.assertEqual([c["code"] for c in L.library_page(EMP, view="he-thong", repo=r)["system"]], ["QT-ISO-03"])
        tasks = L.library_page(EMP, view="viec", repo=r)["tasks"]
        self.assertTrue(tasks and all(t["use"] for t in tasks))
        self.assertEqual(L.library_page(EMP, view="la", repo=r)["view"], "phong-ban")

    def test_search_accent_insensitive(self):
        res = L.library_page(EMP, q="mua hang", repo=seeded())["results"]
        self.assertEqual([c["code"] for c in res], ["QT-TCKT-01"])
        res = L.library_page(EMP, q="QUAN LY TAI LIEU", repo=seeded())["results"]
        self.assertEqual([c["code"] for c in res], ["QT-ISO-03"])
        self.assertEqual(L.library_page(EMP, q="khong co gi", repo=seeded())["results"], [])

    def test_doc_page(self):
        r = seeded()
        d = L.doc_page(EMP, "QT-TCKT-03", repo=r)
        self.assertEqual((d["version"], d["is_old"], d["drafting"]), ("2.0", False, False))
        self.assertEqual([h["version"] for h in d["history"]], ["2.0", "1.0"])
        self.assertTrue(d["mermaid"].startswith("flowchart TD"))
        self.assertEqual(r.seen, [("QT-TCKT-03", EMP, "2.0")])

    def test_doc_page_old_version_and_drafting(self):
        r = seeded()
        d = L.doc_page(EMP, "QT-TCKT-03", version="1.0", repo=r)
        self.assertTrue(d["is_old"])
        self.assertEqual(d["current_version"], "2.0")
        self.assertTrue(L.doc_page(EMP, "QT-TCKT-01", repo=r)["drafting"])

    def test_doc_page_not_found(self):
        r = seeded()
        for code, ver in (("QT-XX-01", ""), ("QT-NS-02", ""), ("QT-TCKT-03", "9.9")):
            with self.assertRaises(NotFound):
                L.doc_page(EMP, code, version=ver, repo=r)


# =========================================================================== quan ly
class TestManage(unittest.TestCase):
    def test_waiting_for_me(self):
        r = seeded(user=HEAD, manager=False, trans={"QT-TCKT-01": [("Đồng ý", "Chờ Ban ISO"),
                                                                  ("Trả lại", "Nhap")]})
        ctx = M.manage_page(HEAD, repo=r)
        self.assertEqual(ctx["filter"], "cho-toi")
        self.assertEqual(ctx["counts"]["cho-toi"], 1)
        it = ctx["items"][0]
        self.assertEqual((it["code"], it["open"]), ("QT-TCKT-01", True))
        self.assertEqual(it["tag"], ("wait", "Bản 1.1 chờ bạn duyệt"))
        self.assertEqual([a["action"] for a in it["actions"]], ["Đồng ý", "Trả lại"])
        self.assertTrue(it["actions"][1]["danger"])
        self.assertEqual(it["desk"], "")                      # khong phai Ban ISO: khong link desk
        self.assertEqual(it["versions"][0]["version"], "1.1")

    def test_counts_and_filters(self):
        r = seeded()
        ctx = M.manage_page(ISO, repo=r)
        self.assertEqual(ctx["filter"], "tat-ca")             # khong co gi cho toi
        self.assertEqual(ctx["counts"], {"cho-toi": 0, "ra-soat": 3, "dang-soan": 2, "het-hieu-luc": 1,
                                         "tat-ca": 4})
        self.assertEqual({i["code"] for i in M.manage_page(ISO, flt="ra-soat", repo=r)["items"]},
                         {"QT-ISO-03", "QT-TCKT-03", "QT-TCKT-01"})
        self.assertEqual([i["code"] for i in M.manage_page(ISO, flt="phong", dept=OPS, repo=r)["items"]],
                         ["QT-ISO-03"])
        self.assertEqual(M.manage_page(ISO, flt="phong", dept="Không có", repo=r)["filter"], "tat-ca")
        tags = {i["code"]: i["tag"] for i in ctx["items"]}
        self.assertEqual(tags["QT-ISO-03"], ("old", "Quá hạn rà soát"))
        self.assertEqual(tags["QT-NS-02"], ("off", "Đang soạn bản 1.0"))
        self.assertEqual(tags["QT-TCKT-01"], ("off", "Bản 1.1 · Chờ trưởng bộ phận"))
        self.assertTrue(all(i["desk"] for i in ctx["items"]))

    def test_search(self):
        items = M.manage_page(ISO, q="mua hang", repo=seeded())["items"]
        self.assertEqual([i["code"] for i in items], ["QT-TCKT-01"])

    def test_action_rules(self):
        r = seeded(trans={"QT-TCKT-01": [("Đồng ý", "Chờ Ban ISO"), ("Trả lại", "Nhap")]})
        with self.assertRaises(Forbidden):
            M.do_action(ISO, "QT-TCKT-01", "Ban hành", repo=r)
        with self.assertRaises(DocError):
            M.do_action(ISO, "QT-TCKT-01", "Trả lại", "  ", repo=r)
        with self.assertRaises(NotFound):
            M.do_action(ISO, "QT-XX-01", "Đồng ý", repo=r)
        out = M.do_action(ISO, "QT-TCKT-01", "Trả lại", "Thiếu bước đối chiếu", repo=r)
        self.assertEqual(out["state"], "Nháp")
        self.assertEqual(r.comments, [("QT-TCKT-01", "Trả lại: Thiếu bước đối chiếu")])
        self.assertEqual(r.applied, [("QT-TCKT-01", "Trả lại")])


class TestImport(unittest.TestCase):
    form = {"name": "phieu-de-nghi-thanh-toan.xlsx", "content": b"x" * 10}

    def files(self):
        return [{"name": os.path.basename(f["file"]), "content": b"x"} for f in PKG["bieu_mau"]]

    def test_revision_of_published_doc_goes_back_to_draft(self):
        r = seeded()
        out = M.import_package(ISO, json.dumps(PKG), pdf={"name": "noi_dung.pdf", "content": b"%PDF"},
                               forms=self.files(), repo=r)
        self.assertEqual((out["code"], out["created"]), ("QT-TCKT-03", False))
        self.assertEqual(r.applied, [("QT-TCKT-03", "Soạn phiên bản mới")])
        code, f = r.updated[-1]
        self.assertEqual(f["ec_change_kind"], C.KIND_MINOR)
        self.assertEqual(f["ec_draft_pdf"], "/private/files/noi_dung.pdf")
        self.assertNotIn("ec_doc_code", f)
        self.assertEqual(json.loads(f["ec_steps_json"])["bieu_mau"][0]["url"],
                         "/private/files/" + os.path.basename(PKG["bieu_mau"][0]["file"]))
        self.assertTrue(D_is_draft(r.docs["QT-TCKT-03"]))

    def test_new_doc_created_as_draft(self):
        g = dict(copy.deepcopy(PKG), loai_goi="moi", ma_tai_lieu="", ma_de_xuat="QT-TCKT-09",
                 ten="Quy trình mới")
        r = seeded()
        out = M.import_package(ISO, json.dumps(g), forms=self.files(), repo=r)
        self.assertEqual((out["code"], out["created"]), ("QT-TCKT-09", True))
        self.assertEqual(r.inserted[0]["ec_doc_code"], "QT-TCKT-09")
        self.assertEqual(r.applied, [])                       # khong ban hanh, khong bam buoc nao

    def test_rejections(self):
        r = seeded()
        with self.assertRaises(Forbidden):
            M.import_package(EMP, json.dumps(PKG), repo=seeded(manager=False))
        with self.assertRaises(DocError):
            M.import_package(ISO, "{khong phai json", repo=r)
        with self.assertRaises(DocError):                     # thieu tep bieu mau goi khai
            M.import_package(ISO, json.dumps(PKG), repo=r)
        with self.assertRaises(DocError):                     # tai lieu dang trong luong duyet
            M.import_package(ISO, json.dumps(dict(PKG, ma_tai_lieu="QT-TCKT-01")), forms=self.files(), repo=r)
        with self.assertRaises(DocError):                     # goi moi trung ma
            M.import_package(ISO, json.dumps(dict(PKG, loai_goi="moi")), code="QT-TCKT-03",
                             forms=self.files(), repo=r)
        with self.assertRaises(DocError):                     # pdf sai duoi
            M.import_package(ISO, json.dumps(PKG), pdf={"name": "a.exe", "content": b"x"},
                             forms=self.files(), repo=r)
        with self.assertRaises(DocError):                     # qua 24 MB
            M.import_package(ISO, json.dumps(PKG), pdf={"name": "a.pdf", "content": b"x" * (19 << 20)},
                             docx={"name": "a.docx", "content": b"x" * (6 << 20)}, forms=self.files(), repo=r)
        self.assertEqual(r.applied, [])
        self.assertEqual(r.updated, [])


def D_is_draft(doc):
    from ecentric_workspace.iso_docs import domain
    return domain.is_state(doc.get(C.STATE_FIELD), C.S_DRAFT)


# =========================================================================== template
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


def render(page, ctx):
    full = {"base_template_path": "templates/base.html", "iso_shell_mount": "<aside>MENU</aside>",
            "iso_topbar": "<div>TOPBAR</div>", "iso_css": "/a.css", "iso_js": "/a.js", "title": "T"}
    full.update(ctx)
    return _env().get_template("www/tai_lieu/%s.html" % page).render(**full)


class TestTemplates(unittest.TestCase):
    def evil_repo(self):
        r = seeded(user=HEAD, manager=True, trans={"QT-TCKT-01": [("Đồng ý", "Chờ Ban ISO"), ("Trả lại", "Nhap")]})
        r.docs["QT-TCKT-03"]["quality_procedure_name"] = EVIL
        r.docs["QT-TCKT-01"]["quality_procedure_name"] = EVIL
        r.docs["QT-TCKT-03"].ec_revisions[1]["mermaid"] = PKG["so_do_mermaid"] + "\n%% " + EVIL
        return r

    def check(self, out):
        self.assertNotIn(EVIL, out)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("NAVBAR", out)
        self.assertIn("<aside>MENU</aside>", out)

    def test_index_every_view(self):
        r = self.evil_repo()
        for view in ("phong-ban", "viec", "he-thong"):
            out = render("index", dict(L.library_page(EMP, view=view, repo=r), can_manage=True))
            self.assertIn('aria-current="page"', out)
        self.check(render("index", dict(L.library_page(EMP, repo=r), can_manage=False)))
        out = render("index", dict(L.library_page(EMP, q="thanh", repo=r), can_manage=False))
        self.assertIn("kết quả cho", out)

    def test_index_empty(self):
        out = render("index", dict(L.library_page(EMP, repo=Repo([])), can_manage=False))
        self.assertIn("Chưa có tài liệu nào được ban hành", out)

    def test_doc_page(self):
        r = self.evil_repo()
        d = L.doc_page(EMP, "QT-TCKT-03", repo=r)
        out = render("chi_tiet", {"d": d, "roles_json": json.dumps(d["flow"]["roles"], ensure_ascii=False),
                                  "mermaid_js": "/m.js"})
        self.check(out)
        self.assertIn('id="eti-src" hidden>flowchart TD', out)
        self.assertIn('data-eti-flow', out)
        self.assertIn('<script src="/m.js" defer></script>', out)
        self.assertIn("/private/files/bm01.xlsx", out)
        self.assertIn("?ban=1.0", out)
        out_old = render("chi_tiet", {"d": L.doc_page(EMP, "QT-TCKT-03", version="1.0", repo=r),
                                      "roles_json": "[]", "mermaid_js": "/m.js"})
        self.assertIn("đã hết hiệu lực", out_old)

    def test_doc_page_without_diagram(self):
        r = seeded()
        r.docs["QT-TCKT-03"].ec_revisions[1]["mermaid"] = ""
        out = render("chi_tiet", {"d": L.doc_page(EMP, "QT-TCKT-03", repo=r), "roles_json": "[]",
                                  "mermaid_js": "/m.js"})
        self.assertNotIn("data-eti-flow", out)
        self.assertNotIn("/m.js", out)
        self.assertIn('<details class="eti-steps" open>', out)

    def test_manage(self):
        r = self.evil_repo()
        out = render("quan_ly", M.manage_page(HEAD, repo=r))
        self.check(out)
        self.assertIn('data-eti-act="QT-TCKT-01"', out)
        self.assertIn('value="Trả lại"', out)
        self.assertIn('id="eti-import"', out)
        out2 = render("quan_ly", M.manage_page(HEAD, repo=seeded(manager=False)))
        self.assertNotIn('id="eti-import"', out2)
        self.assertNotIn("/desk/", out2)


if __name__ == "__main__":
    unittest.main()
