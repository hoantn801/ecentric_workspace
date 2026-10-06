# Copyright (c) 2026, eCentric and contributors
"""Nhap tai lieu cu tu SharePoint (legacy.import_one) + nhan "Ban cu" tren trang.

    python -m unittest ecentric_workspace.iso_docs.tests.test_legacy
"""
import copy
import datetime as dt
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from ecentric_workspace.iso_docs import constants as C  # noqa: E402
from ecentric_workspace.iso_docs import legacy as LG  # noqa: E402
from ecentric_workspace.iso_docs import library as L  # noqa: E402
from ecentric_workspace.iso_docs.errors import DocError, Forbidden  # noqa: E402
from ecentric_workspace.iso_docs.tests.test_iso_docs import Doc  # noqa: E402
from ecentric_workspace.iso_docs.tests import test_pages as TP  # noqa: E402


class Repo(TP.Repo):
    def __init__(self, docs=(), manager=True):
        super().__init__(list(docs), manager=manager)
        self.forced = []

    def update_draft(self, code, fields):
        f = dict(fields)
        revs = f.pop("ec_revisions", None)
        super().update_draft(code, f)
        if revs is not None:
            self.docs[code]["ec_revisions"] = [Doc(r, idx=i + 1) for i, r in enumerate(revs)]

    def force_published(self, code, note):
        self.forced.append((code, note))
        self.docs[code][C.STATE_FIELD] = C.S_PUBLISHED


BLOB = {"name": "QT.pdf", "content": b"%PDF-1"}
DATA = {
    "code": "QT-TCKT-02", "name": "Thanh toán", "type": "Quy trình", "dept": TP.FIN, "company_wide": 1,
    "purpose": "Quy định thống nhất trách nhiệm, trình tự thanh toán.",
    "signers": "lập: Trần Thị Mỹ Lệ; phê duyệt: Nguyễn Văn Lãm",
    "mermaid": TP.PKG["so_do_mermaid"], "steps_json": TP.STEPS,
    "revisions": [
        {"version": "1.0", "from": "2025-03-03", "to": "2025-08-24", "summary": "Tạo mới quy trình", "by": "Trần Thị Mỹ Lệ"},
        {"version": "2.0", "from": "2025-08-25", "summary": "Thêm bước kiểm tra", "changed_sections": "6.2",
         "pdf": BLOB, "docx": {"name": "QT.docx", "content": b"PK"}},
    ],
    "forms": [{"name": "Phiếu đề nghị thanh toán", "file": {"name": "bm.xlsx", "content": b"x"}}],
}


def run(repo, **kw):
    d = copy.deepcopy(DATA)
    d.update(kw)
    return LG.import_one(TP.ISO, d, repo=repo)


class TestLegacyImport(unittest.TestCase):
    def test_creates_published_doc_with_history(self):
        r = Repo()
        out = run(r)
        self.assertEqual(out, {"code": "QT-TCKT-02", "created": True, "skipped": False, "versions": ["1.0", "2.0"]})
        doc = r.docs["QT-TCKT-02"]
        self.assertEqual(doc[C.STATE_FIELD], C.S_PUBLISHED)
        self.assertEqual(r.forced[0][0], "QT-TCKT-02")
        self.assertEqual(doc.ec_current_version, "2.0")
        self.assertEqual(doc.ec_effective_from, dt.date(2025, 8, 25))
        self.assertEqual(doc.ec_next_review, dt.date(2026, 8, 25))
        self.assertEqual(doc.ec_source, LG.SOURCE)
        self.assertEqual(doc.ec_notify_home, 0)                     # khong thong bao trang chu
        old, cur = doc.ec_revisions
        self.assertEqual((old.status, old.effective_to, old.get("pdf")), (C.REV_EXPIRED, dt.date(2025, 8, 24), None))
        self.assertEqual((cur.status, cur.effective_to), (C.REV_EFFECTIVE, None))
        self.assertEqual((cur.pdf, cur.docx), ("/private/files/QT.pdf", "/private/files/QT.docx"))
        self.assertIn("Nguyễn Văn Lãm", cur.summary)
        self.assertIn("Biên soạn: Trần Thị Mỹ Lệ", old.summary)
        self.assertTrue(cur.mermaid.startswith("flowchart TD"))
        steps = json.loads(cur.steps_json)
        self.assertEqual(steps["tom_tat"]["muc_dich"], DATA["purpose"])
        self.assertEqual(steps["bieu_mau"][-1]["url"], "/private/files/bm.xlsx")
        self.assertEqual(all(x.source == LG.SOURCE for x in doc.ec_revisions), True)

    def test_rerun_is_skipped(self):
        r = Repo()
        run(r)
        out = run(r)
        self.assertTrue(out["skipped"])
        self.assertEqual(len(r.forced), 1)

    def test_never_overwrites(self):
        r = TP.seeded()
        r.forced = []
        r.force_published = lambda c, n: None
        with self.assertRaises(DocError):
            LG.import_one(TP.ISO, dict(copy.deepcopy(DATA), code="QT-TCKT-03"), repo=r)

    def test_partial_existing_refused(self):
        r = Repo()
        run(r)
        r.docs["QT-TCKT-02"]["ec_revisions"] = r.docs["QT-TCKT-02"]["ec_revisions"][:1]
        with self.assertRaises(DocError):
            run(r)

    def test_validation(self):
        bad = [
            {"code": "QT-03"}, {"type": "Sổ tay"}, {"dept": "Finance"}, {"name": " "}, {"revisions": []},
            {"revisions": [{"version": "2.0", "from": "2025-01-01"}, {"version": "1.0", "from": "2025-02-01"}]},
            {"revisions": [{"version": "1.0", "from": "01/02/2025"}]},
            {"revisions": [{"version": "1.0"}]},
        ]
        for kw in bad:
            with self.assertRaises(DocError, msg=str(kw)):
                run(Repo(), **kw)

    def test_manager_only(self):
        with self.assertRaises(Forbidden):
            run(Repo(manager=False))

    def test_library_marks_legacy(self):
        r = Repo()
        run(r)
        ctx = L.library_page(TP.EMP, repo=r)
        card = ctx["sections"][0]["cards"][0]
        self.assertTrue(card["legacy"])
        self.assertEqual(card["use"], TP.PKG["tom_tat"]["dung_khi"])   # "Dung khi" truoc, roi moi toi "Muc dich"
        d = L.doc_page(TP.EMP, "QT-TCKT-02", repo=r)
        self.assertTrue(d["legacy"])
        self.assertEqual(d["flow"]["facts"][0], ("Mục đích", DATA["purpose"]))
        out = TP.render("chi_tiet", {"d": d, "roles_json": "[]", "mermaid_js": "/m.js"})
        self.assertIn("Bản cũ chuyển từ SharePoint", out)
        out = TP.render("index", dict(ctx, can_manage=False))
        self.assertNotIn(">Bản cũ<", out)          # PO 06/10: the thu vien bo nhan (ca 61 deu la ban cu)


if __name__ == "__main__":
    unittest.main()
