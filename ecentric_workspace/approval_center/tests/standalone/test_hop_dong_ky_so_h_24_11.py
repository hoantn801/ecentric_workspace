# Copyright (c) 2026, eCentric and contributors
"""PR-H (24/11/2026) - phia Hop dong theo PR-G cua chat Ky so:
  * hook doi chieu: hop dong thuong -> "not_applicable"; KOL khong lop chu (pages_text=[]) -> "no_text";
  * hook ec_esign_signing_files: KOL chi "Ban PDF de ky"; hop dong thuong rong;
  * "Can bo sung": KHONG go ban PDF cu (co the nam trong goi da khoa), van la tep PII;
  * trang: thay PDF khi goi da khoa -> hoi xac nhan -> reopen_signing_setup TRUOC khi tai len.
Chay: python -m unittest ecentric_workspace.approval_center.tests.standalone.test_hop_dong_ky_so_h_24_11
"""
import importlib
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_contract_kol_qc_15_11 import CR, STATE, Throw, _fresh  # noqa: E402
from test_hop_dong_ky_so_23_11 import P, _hooks, _kol_doc, _read  # noqa: E402


class HookDoiChieuPRG(unittest.TestCase):
    def setUp(self):
        _fresh("req@ec")
        STATE["values"][("User", "c@gmail.com")] = None

    def test_hop_dong_thuong_khong_ap_dung(self):
        _kol_doc(contract_type="Purchase / Mua vào (EC)")
        h = _hooks()
        self.assertEqual(h.verify_document(CR, "CR-1", "scan.pdf", [])["status"], "not_applicable")
        self.assertEqual(h.verify_document(CR, "CR-1", "x.pdf", ["bất kỳ"])["status"], "not_applicable")

    def test_kol_khong_lop_chu_van_chan(self):
        _kol_doc()
        self.assertEqual(_hooks().verify_document(CR, "CR-1", "x.pdf", [])["status"], "no_text")

    def test_kol_khop_van_match(self):
        _kol_doc()
        r = _hooks().verify_document(CR, "CR-1", "HD.pdf", ["Số: 23112026/HDDV/ECENTRIC-AB.X", "Thực nhận 9,000,000 đ"])
        self.assertEqual(r["status"], "match")


class TepKyDoNghiepVuKhai(unittest.TestCase):
    def setUp(self):
        _fresh("req@ec")

    def test_kol_chi_ban_pdf_de_ky(self):
        _kol_doc(sign_pdf="/private/files/HD.pdf", contract_file="/private/files/HDDV_1.docx",
                 signed_file="/private/files/da-ky.pdf")
        self.assertEqual(_hooks().signing_files("CR-1"), ["/private/files/HD.pdf"])

    def test_kol_chua_co_pdf_thi_rong(self):
        _kol_doc(sign_pdf=None)
        self.assertEqual(_hooks().signing_files("CR-1"), [])

    def test_hop_dong_thuong_rong(self):
        _kol_doc(contract_type="Purchase / Mua vào (EC)", sign_pdf="/private/files/HD.pdf")
        self.assertEqual(_hooks().signing_files("CR-1"), [])

    def test_hooks_khai_ham_ton_tai(self):
        hooks = _read("../hooks.py")
        self.assertIn("ec_esign_signing_files", hooks)
        self.assertIn("esign_hooks.signing_files", hooks)
        self.assertTrue(callable(getattr(_hooks(), "signing_files", None)))


class ThayPdfKhiCanBoSung(unittest.TestCase):
    def _mod(self, enabled=True):
        _fresh("req@ec")
        gate = types.ModuleType(P + "esign_gate")
        gate.enabled = lambda name: enabled
        sys.modules[P + "esign_gate"] = gate
        files = types.ModuleType(P + "kol_files")
        files.claim_upload = lambda doc, url, user: url
        sys.modules[P + "kol_files"] = files
        sys.modules.pop(P + "kol_sign_pdf", None)
        m = importlib.import_module(P + "kol_sign_pdf")
        self.dropped = []
        m._drop_old = lambda doc, url: self.dropped.append(url)
        return m

    def _doc(self, **kw):
        d = _kol_doc(sign_pdf="/private/files/cu.pdf", **kw)
        d["db_set"] = lambda k, v: d.__setitem__(k, v)
        return d

    def test_can_bo_sung_khong_go_ban_cu(self):
        m = self._mod()
        d = self._doc(approval_request="AR-1")
        STATE["values"][("EC Approval Request", "AR-1")] = "Information Required"
        r = m.attach("CR-1", "/private/files/moi.pdf", "req@ec")
        self.assertEqual(r["sign_pdf"], "/private/files/moi.pdf")
        self.assertEqual(d["sign_pdf"], "/private/files/moi.pdf")
        self.assertEqual(self.dropped, [])

    def test_chua_gui_van_go_ban_cu(self):
        m = self._mod()
        self._doc()
        m.attach("CR-1", "/private/files/moi.pdf", "req@ec")
        self.assertEqual(self.dropped, ["/private/files/cu.pdf"])

    def test_ban_cu_chu_administrator_van_an(self):
        _fresh("req@ec")
        acc = importlib.import_module(P + "kol_access")
        biz = {"sign_pdf": "/private/files/moi.pdf", "contract_file": None, "acceptances": []}
        old = {"file_url": "/private/files/cu.pdf", "file_name": "cu.pdf", "owner": "Administrator"}
        self.assertTrue(acc._is_pii_attachment(biz, old))

    def test_cau_bao_ma_moi(self):
        m = self._mod()
        self.assertIn("bằng tay", m.summarize({"ok": False, "reason": "manual_placement"})["message"])
        self.assertIn("trùng bản đã khoá", m.summarize({"ok": False, "reason": "unchanged_in_locked_package"})["message"])
        self.assertIn("không phải bản PDF để ký", m.summarize({"ok": False, "reason": "not_signing_file"})["message"])

    def test_view_bao_goi_da_khoa(self):
        m = self._mod()
        m.is_stale = lambda doc: False
        d = self._doc(approval_request="AR-1")
        STATE["values"][("EC Approval Request", "AR-1")] = "Information Required"
        lc = types.ModuleType("ecentric_workspace.platform.esign.lifecycle")
        lc.locked_signable_shas = lambda dt, name: {"abc"}
        es = types.ModuleType("ecentric_workspace.platform.esign")
        es.lifecycle = lc
        saved = {k: sys.modules.get(k) for k in ("ecentric_workspace.platform.esign",
                                                   "ecentric_workspace.platform.esign.lifecycle")}
        sys.modules.update({"ecentric_workspace.platform.esign": es,
                            "ecentric_workspace.platform.esign.lifecycle": lc})
        try:
            self.assertTrue(m.view(d, "req@ec")["locked"])
            lc.locked_signable_shas = lambda dt, name: None
            self.assertFalse(m.view(d, "req@ec")["locked"])
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        STATE["values"][("EC Approval Request", "AR-1")] = "Pending"
        self.assertFalse(m.view(d, "req@ec")["locked"])


class NguoiDuyetXemBanPdfDeKy(unittest.TestCase):
    """PO 24/11 (cau 4): nguoi trong luong duyet xem / mo duoc sign_pdf o khoi Ky so; PII khac van an."""
    SIGN = "/private/files/HD-ky.pdf"

    def _run(self, user, approver=True, esign=True, roles=()):
        _fresh(user)
        STATE["roles"][user] = list(roles)
        gate = types.ModuleType(P + "esign_gate")
        gate.enabled = lambda name: esign
        sys.modules[P + "esign_gate"] = gate
        STATE["values"][(CR, "CR-1")] = lambda field, as_dict: (
            {"sign_pdf": self.SIGN, "approval_request": "AR-1"} if isinstance(field, (list, tuple)) else None)
        if approver:
            STATE["exists"].add(("EC Approval Request Approver",
                                 tuple(sorted({"approval_request": "AR-1", "approver": user}.items()))))
        acc = importlib.import_module(P + "kol_access")
        biz = {"name": "CR-1", "contract_type": "KOL/KOC / Creator (EC)", "approval_request": "AR-1",
               "requested_by": "req@ec", "owner": "req@ec", "creator": None,
               "sign_pdf": None,                 # da qua redact_business
               "contract_file": "/private/files/HDDV_1.docx", "acceptances": []}
        files = [{"name": "F1", "file_url": self.SIGN, "file_name": "HD-ky.pdf", "owner": "Administrator"},
                 {"name": "F2", "file_url": "/private/files/HDDV_1.docx", "file_name": "HDDV_1.docx",
                  "owner": "Administrator"},
                 {"name": "F3", "file_url": "/private/files/cu.pdf", "file_name": "cu.pdf", "owner": "Administrator"},
                 {"name": "F4", "file_url": "/private/files/brief.pdf", "file_name": "brief.pdf", "owner": "acc@ec"}]
        return [f["name"] for f in acc.redact_attachments(files, biz)]

    def test_nguoi_duyet_thay_ban_pdf_de_ky_khong_thay_pii_khac(self):
        self.assertEqual(self._run("ceo@ec"), ["F1", "F4"])

    def test_ke_toan_trong_luong_duyet_cung_thay(self):
        self.assertIn("F1", self._run("ktt@ec", roles=("EC Finance",)))

    def test_nguoi_ngoai_luong_duyet_khong_thay(self):
        self.assertEqual(self._run("khac@ec", approver=False), ["F4"])

    def test_chua_ky_qua_nen_tang_thi_van_an(self):
        self.assertEqual(self._run("ceo@ec", esign=False), ["F4"])


class TrangHoiXacNhanKhongMoLaiTruoc(unittest.TestCase):
    """Sau review chat Ky so 24/11: KHONG goi reopen_signing_setup truoc khi tai - auto_place tu mo lai
    chi khi tep moi qua het phep kiem (tep trung / sai / loi thi tai lieu cu tren cong con nguyen)."""

    def test_trang_hoi_xac_nhan_roi_tai_thang(self):
        page = _read("features/contract_review/ui/main_section.html")
        self.assertNotIn("reopen_signing_setup", page)
        i = page.index('if(a==="signpdf"&&spv.locked)')
        seg = page[i:i + 1400]
        self.assertIn("modal(", seg)
        self.assertIn("runSignPdf", seg)
        self.assertIn("sp.locked", page)
        run = page[page.index("var runSignPdf=function()"):i]
        self.assertLess(run.index('"kol_attach_sign_pdf"'), run.index('"kol_auto_place_sign"'))

    def test_bao_da_mo_lai_goi(self):
        _fresh("req@ec")
        gate = types.ModuleType(P + "esign_gate")
        gate.enabled = lambda name: True
        sys.modules[P + "esign_gate"] = gate
        sys.modules.pop(P + "kol_sign_pdf", None)
        m = importlib.import_module(P + "kol_sign_pdf")
        r = m.summarize({"ok": True, "placed": [{}, {}], "reopened": "PKG-2"})
        self.assertTrue(r["message"].startswith("Đã mở lại gói ký; tài liệu cũ trên cổng sẽ được huỷ."))
        self.assertIn("2 ô ký", r["message"])
        self.assertEqual(r["reopened"], "PKG-2")
        r = m.summarize({"ok": False, "reason": "unchanged_in_locked_package", "reopened": None})
        self.assertNotIn("Đã mở lại", r["message"])

    def test_patch_moc_khong_con_reopen(self):
        for f in ("p512_resync_hop_dong_thay_pdf", "p513_resync_hop_dong_thay_pdf_khong_mo_truoc"):
            src = _read("patches/%s.py" % f)
            self.assertNotIn('"reopen_signing_setup"', src[src.index("_MARKS"):src.index("_MARKS") + 120])


if __name__ == "__main__":
    unittest.main()
