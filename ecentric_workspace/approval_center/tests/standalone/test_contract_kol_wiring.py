# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC - noi day giua cac phan (doc ma, khong can bench).

  1. AI QC: che so dinh danh truoc khi gui AI; kiem so lieu + tep ky duoc bang MAY.
  2. DNTT: hop dong nam trong _SOURCES, tran chi la ham (khong phai mot truong), co giai thich.
  3. Form 27: truong KOL trong editable_fields deu ton tai tren DocType; truong may tinh
     (tien, so HD, tep, ky) KHONG nam trong editable_fields.
  4. Chu ky "doi noi dung" chi cong truong KOL vao phieu KOL (phieu cu khong bi duyet lai).
  5. Ham whitelist moi khong nhan user/actor; cac ham api goi duoc deu duoc re-export.
"""
import ast
import importlib.util
import json
import os
import pathlib
import sys
import types
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
AC = _HERE.parents[1]
APP = AC.parent
sys.path.insert(0, str(APP.parent))


def _load(path, name, inject=None):
    for k, v in (inject or {}).items():
        sys.modules[k] = v
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_frappe():
    fake = types.ModuleType("frappe")
    fake._ = lambda s: s
    fake.whitelist = lambda *a, **k: (lambda f: f)
    fake.utils = types.ModuleType("frappe.utils")
    fake.utils.now_datetime = lambda: None
    fake.utils.flt = lambda v: float(v or 0)
    fake.utils.nowdate = lambda: "2026-11-11"
    fake.utils.today = lambda: "2026-11-11"
    return {"frappe": fake, "frappe.utils": fake.utils}


class AiPureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inject = _fake_frappe()
        for mod in ("kol_lookup", "kol_files", "kol_service"):
            m = types.ModuleType("ecentric_workspace.approval_center.features.contract_review.application." + mod)
            m.file_bytes = m.can_manage = m.creator_row = lambda *a, **k: None
            inject[m.__name__] = m
        app = types.ModuleType("ecentric_workspace.approval_center.features.contract_review.application")
        for mod in ("kol_lookup", "kol_files", "kol_service"):
            setattr(app, mod, inject["ecentric_workspace.approval_center.features.contract_review.application." + mod])
        inject[app.__name__] = app
        cls.ai = _load(AC / "features/contract_review/application/kol_ai.py", "kol_ai_t", inject)
        for k in list(inject):
            if k.startswith("ecentric_workspace.approval_center.features.contract_review.application"):
                sys.modules.pop(k, None)
        sys.modules.pop("frappe", None)
        sys.modules.pop("frappe.utils", None)

    def test_che_cccd_stk_nhung_giu_so_tien_ngan(self):
        out = self.ai.redact("CCCD 079 123 456 789, STK 0011-2233-4455, phí 30.000.000 đồng, 3 buổi")
        self.assertNotIn("789", out)
        self.assertNotIn("4455", out)
        self.assertIn("3 buổi", out)

    def test_kiem_so_lieu_bang_may(self):
        text = "Bên B: Nguyễn Văn A, CCCD 079123456789. Tổng thanh toán 9.000.000 đồng."
        checks = {c["field"]: c["value_present"] for c in self.ai.data_checks(
            text, {"payable_amount": 9_000_000, "contract_no": None},
            {"supplier_name": "Nguyễn Văn A", "ec_cr_cccd": "079123456789",
             "ec_bank_account_no": "999888777"})}
        self.assertTrue(checks["Số tiền trả creator"])
        self.assertTrue(checks["CCCD"])
        self.assertTrue(checks["Tên creator"])
        self.assertFalse(checks["Số tài khoản"])

    def test_tep_ky_duoc(self):
        self.assertEqual(self.ai.signable_check("a.pdf", b"%PDF-1.7 Word"), "")
        self.assertIn("ReportLab", self.ai.signable_check("a.pdf", b"%PDF-1.4 ReportLab"))
        self.assertIn("ảnh", self.ai.signable_check("a.pdf", b"\x89PNG"))
        self.assertEqual(self.ai.signable_check("a.docx", b"PK\x03\x04"), "")
        self.assertTrue(self.ai.signable_check("a.png", b"x"))

    def test_trang_thai_qc(self):
        ok = [{"field": "x", "value_present": True}]
        self.assertEqual(self.ai.qc_status(ok, "", {"risky_clauses": [], "template_deviations": []}), "Đạt")
        self.assertEqual(self.ai.qc_status([{"field": "x", "value_present": False}], "", {}), "Lỗi")
        self.assertEqual(self.ai.qc_status(ok, "PDF ReportLab", {}), "Lỗi")
        self.assertEqual(self.ai.qc_status(ok, "", None), "Cần xem")
        self.assertEqual(self.ai.qc_status(ok, "", {"risky_clauses": [{"severity": "Cao"}],
                                                    "template_deviations": []}), "Cần xem")


class WiringTests(unittest.TestCase):
    def src(self, rel):
        return (AC / rel).read_text(encoding="utf-8")

    def test_dntt_nhan_hop_dong_lam_nguon_va_tran_la_ham(self):
        s = self.src("features/payment_request/application/funding.py")
        self.assertIn('"EC Contract Review Request": {', s)
        for fn in ("funding_total", "funding_approved", "funding_owner_filters", "funding_explain"):
            self.assertIn('_KOL + "%s"' % fn, s)
            self.assertIn("def %s(" % fn, self.src("features/contract_review/application/kol_funding.py"))
        self.assertIn("kol_funding.fill_payment", self.src("features/payment_request/application/service.py"))

    def test_editable_fields_ton_tai_va_khong_lo_truong_may_tinh(self):
        meta = json.loads(self.src("doctype/ec_contract_review_request/ec_contract_review_request.json"))
        names = {f["fieldname"] for f in meta["fields"]}
        tree = ast.parse(self.src("features/contract_review/domain/definition.py"))
        editable = None
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "editable_fields":
                editable = ast.literal_eval(node.value)
        self.assertTrue(editable)
        self.assertEqual(sorted(set(editable) - names), [])
        for computed in ("gross_amount", "pit_amount", "vat_amount", "payable_amount",
                         "advance_amount", "contract_no", "contract_file", "signing_status",
                         "signed_file", "ai_qc_status", "revenue_warning", "so_revenue"):
            self.assertIn(computed, names)
            self.assertNotIn(computed, editable)
        self.assertIn("EC Contract Acceptance", {f.get("options") for f in meta["fields"]})
        self.assertIn("KOL/KOC / Creator (EC)",
                      [f for f in meta["fields"] if f["fieldname"] == "contract_type"][0]["options"])

    def test_chu_ky_noi_dung_chi_cong_truong_kol_cho_phieu_kol(self):
        s = self.src("features/contract_review/application/service.py")
        self.assertIn("KOL_MATERIAL_FIELDS if kol.is_kol(doc) else []", s)
        self.assertNotIn('"sales_order"', s.split("KOL_MATERIAL_FIELDS")[0])

    def test_whitelist_kol_khong_nhan_user_va_duoc_re_export(self):
        tree = ast.parse(self.src("features/contract_review/controllers/kol_api.py"))
        exported = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and node.targets[0].id == "__all__":
                exported = set(ast.literal_eval(node.value))
        funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and any("whitelist" in ast.unparse(d) for d in n.decorator_list)}
        self.assertEqual(set(funcs), exported)
        for fn in funcs.values():
            self.assertFalse({"user", "actor"} & {a.arg for a in fn.args.args}, fn.name)
        self.assertIn("kol_api import *", self.src("features/contract_review/controllers/api.py"))

    def test_mau_hop_dong_co_doctype_va_quyen_finance(self):
        meta = json.loads(self.src("doctype/ec_contract_template/ec_contract_template.json"))
        self.assertEqual({p["role"] for p in meta["permissions"]}, {"System Manager", "EC Finance"})
        self.assertIn("inspect_template", self.src("doctype/ec_contract_template/ec_contract_template.py"))


if __name__ == "__main__":
    unittest.main()
