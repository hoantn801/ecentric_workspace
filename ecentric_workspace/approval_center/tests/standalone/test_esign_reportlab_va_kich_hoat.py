# Copyright (c) 2026, eCentric and contributors
"""Hai cho chan (12/11/2026, Hoan chot):

1. PDF sinh bang ReportLab bi chan NGAY LUC dua vao goi ky / danh dau can ky.
   30/09: 00316-00321 - 0/6 tep ReportLab ky duoc, 135/135 tep khac ky duoc. Cong nhan lenh
   (2xx) roi im; phieu ket "Cho gui di", lo ra sau 20 phut. Tep tham khao (khong can ky) KHONG
   bi chan.
2. Phieu DA DONG (Approved / Rejected / Cancelled) khong duoc mo cap duyet 1 khi chu ky nguoi de
   nghi den muon (QC Opus 12/11: chan dang chay luc phieu bi huy ky xong -> mo cap 1 -> nguoi
   duyet nhan ToDo + SLA tren phieu da huy).
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ESIGN = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "platform", "esign"))


def _src(name):
    with io.open(os.path.join(_ESIGN, name), encoding="utf-8") as fh:
        return fh.read()


_PKG = _src("package.py")
_REQ = _src("requester.py")


class _Throw(Exception):
    pass


def _fns(src, names, g):
    tree = ast.parse(src)
    code = ""
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in names:
            code += ast.get_source_segment(src, n) + "\n\n"
        elif isinstance(n, ast.Assign) and any(getattr(t, "id", "") in names for t in n.targets):
            code = ast.get_source_segment(src, n) + "\n" + code
    exec(compile(code, "x", "exec"), g)
    return g


def _pkg_env(**extra):
    import re
    g = {"re": re, "os": os, "_": lambda s: s, "PDF_MAGIC": b"%PDF-", "EXT_DENYLIST": (),
         "frappe": types.SimpleNamespace(
             throw=lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m)),
             db=types.SimpleNamespace(count=lambda *a, **k: 0, get_value=lambda *a, **k: 1,
                                      set_value=lambda *a, **k: None))}
    g.update(extra)
    g.setdefault("UnsignableProducer", _Throw)
    return _fns(_PKG, {"unsignable_producer", "assert_signable_producer", "_validate_content",
                       "set_file_flags", "_UNSIGNABLE_PRODUCERS", "_PRODUCER_RE",
                       "_unsignable_cached", "preflight_for_lock"}, g)


def _pdf(producer=b"Microsoft\xae Word 2021", creator=None):
    info = b"/Producer (" + producer + b")"
    if creator:
        info += b" /Creator (" + creator + b")"
    return b"%PDF-1.4\n1 0 obj << " + info + b" >> endobj\ntrailer\n%%EOF\n"


RL = _pdf(b"ReportLab PDF Library - www.reportlab.com", b"\\(unspecified\\)")
#: Dau ra mac dinh ReportLab 4/5 - DUNG chuoi tren tep that cua 00316 (prod, 12/11).
RL_OPEN = _pdf(b"ReportLab PDF Library - \\(opensource\\)", b"anonymous")


class TestNhanDien(unittest.TestCase):
    def test_reportlab(self):
        self.assertEqual(_pkg_env()["unsignable_producer"](RL), "reportlab")

    def test_dau_ra_that_cua_00316(self):
        self.assertEqual(_pkg_env()["unsignable_producer"](RL_OPEN), "reportlab")

    def test_ngoac_thoat_truoc_chu_reportlab(self):
        self.assertEqual(_pkg_env()["unsignable_producer"](_pdf(b"Foo \\(x\\) ReportLab")),
                         "reportlab")

    def test_word_khong_chan(self):
        self.assertIsNone(_pkg_env()["unsignable_producer"](_pdf()))

    def test_excel_ios_khong_chan(self):
        g = _pkg_env()
        for p in (b"Microsoft\xae Excel\xae 2021", b"iOS Version 18.7.8 \\(Build 22H352\\)",
                  b"Microsoft: Print To PDF"):
            self.assertIsNone(g["unsignable_producer"](_pdf(p)), p)

    def test_creator_reportlab_cung_chan(self):
        self.assertEqual(_pkg_env()["unsignable_producer"](_pdf(b"x", b"reportlab")), "reportlab")

    def test_khong_doan_tu_noi_dung_khac(self):
        """Chu 'ReportLab' trong NOI DUNG trang (vd hop dong voi cong ty ten do) khong phai
        nha san xuat - chi doc /Producer va /Creator."""
        body = b"%PDF-1.4\nBT (Hop dong ReportLab Ltd) Tj ET\n/Producer (Microsoft Word)\n%%EOF\n"
        self.assertIsNone(_pkg_env()["unsignable_producer"](body))


class TestChanLucDuaVaoGoi(unittest.TestCase):
    PROFILE = {"max_file_mb": 25, "max_files": 20, "require_signable_pdf": 1}
    PKG = types.SimpleNamespace(name="PKG-1")

    def test_tep_can_ky_bi_chan(self):
        g = _pkg_env()
        with self.assertRaises(_Throw) as c:
            g["_validate_content"](self.PKG, self.PROFILE, "hd.pdf", RL, 1)
        self.assertIn("ReportLab", str(c.exception))
        self.assertIn("Word", str(c.exception), "phai noi cach sua, khong chi noi loi")
        self.assertIn("hd.pdf", str(c.exception), "phai noi TEP NAO")
        self.assertIn("Bộ chứng từ", str(c.exception), "tep khong can ky: chi duong ra")

    def test_tep_tham_khao_khong_bi_chan(self):
        g = _pkg_env()
        self.assertTrue(g["_validate_content"](self.PKG, self.PROFILE, "bang_tinh.pdf", RL, 0))

    def test_tep_word_van_qua(self):
        g = _pkg_env()
        self.assertTrue(g["_validate_content"](self.PKG, self.PROFILE, "hd.pdf", _pdf(), 1))

    def test_danh_dau_can_ky_sau_cung_bi_chan(self):
        row = types.SimpleNamespace(package="PKG-1", is_pdf=1, file_name="hd.pdf")
        writes = []
        g = _pkg_env(get_package=lambda n: types.SimpleNamespace(profile="P"),
                     perms=types.SimpleNamespace(assert_requester_draft_package=lambda p: None),
                     file_bytes=lambda n: RL)
        g["frappe"].get_doc = lambda dt, n: row
        g["frappe"].db.set_value = lambda *a, **k: writes.append(a)
        with self.assertRaises(_Throw):
            g["set_file_flags"]("DSF-1", requires_signature=1)
        self.assertEqual(writes, [], "chan TRUOC khi ghi")
        g["set_file_flags"]("DSF-1", requires_signature=0)
        self.assertTrue(writes, "bo danh dau can ky thi khong can kiem")


class TestChotTruocKhiToiCong(unittest.TestCase):
    """create_revision chep dong DSF khong qua _validate_content; goi Draft co tu truoc ban nay
    cung vay. preflight_for_lock la cho MOI duong deu di qua truoc cong (QC 12/11)."""

    def _env(self, content, cache):
        reads = []
        rows = [types.SimpleNamespace(name="DSF-1", file_name="hd.pdf", requires_signature=1,
                                      is_pdf=1, sha256="abc", size_bytes=10)]

        class C(object):
            def hget(self, h, k):
                return cache.get(k)

            def hset(self, h, k, v):
                cache[k] = v

        def fb(n):
            reads.append(n)
            return content
        lim = types.SimpleNamespace(fits=lambda *a: True, mb=lambda x: x)
        g = _pkg_env(package_files=lambda n: rows, package_placements=lambda n: [],
                     file_bytes=fb, _payload_copies_for_profile=lambda p: 1)
        g["frappe"].db.get_value = lambda *a, **k: types.SimpleNamespace(profile="P", status="Draft")
        g["frappe"].get_all = lambda *a, **k: []
        g["frappe"].cache = lambda: C()
        import sys
        pkg = types.ModuleType("ecentric_workspace.platform.esign")
        pkg.limits = lim
        saved = {k: sys.modules.get(k) for k in ("ecentric_workspace.platform.esign",
                                                 "ecentric_workspace.platform.esign.limits")}
        sys.modules["ecentric_workspace.platform.esign"] = pkg
        sys.modules["ecentric_workspace.platform.esign.limits"] = lim
        try:
            out1 = g["preflight_for_lock"]("PKG-1")
            out2 = g["preflight_for_lock"]("PKG-1")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        return out1, out2, reads

    def test_bat_reportlab_o_preflight(self):
        out1, out2, reads = self._env(RL_OPEN, {})
        self.assertIn("unsignable_producer:hd.pdf", out1)
        self.assertEqual(out1, out2)
        self.assertEqual(len(reads), 1, "lan sau doc tu cache theo sha, khong doc lai bytes")

    def test_word_qua_preflight(self):
        out1, _o, _r = self._env(_pdf(), {})
        self.assertFalse([e for e in out1 if e.startswith("unsignable_producer")])

    def test_cau_bao_tieng_viet_cho_nguoi_dung(self):
        g = _fns(_REQ, {"_preflight_vi", "_PREFLIGHT_VI"}, {})
        msg = g["_preflight_vi"]("unsignable_producer:hd.pdf")
        self.assertIn("hd.pdf", msg)
        self.assertIn("Word", msg)

    def test_document_setup_khong_nuot_thanh_dinh_dang_chua_ho_tro(self):
        src = io.open(os.path.join(_ESIGN, "document_setup.py"), encoding="utf-8").read()
        i, j = src.index("except pkgsvc.UnsignableProducer"), src.index('"unsupported_signable_format"')
        self.assertLess(i, j, "phai bat loi rieng TRUOC nhanh 'PDF' chung")


class _AR(dict):
    __getattr__ = dict.get


class TestPhieuDaDongKhongMoCap1(unittest.TestCase):
    def _run(self, approval_status):
        calls = {"activated": 0}
        ar = _AR(approval_type="PAYMENT_REQUEST", reference_doctype="EC Payment Request",
                 current_level=0, requester_signature_status="Processing",
                 requested_by="thu@x", approval_status=approval_status)
        dsr = _AR(actor_type="Requester", actor_user="thu@x", status="Approval Completed")

        committed = _AR(ar)
        snapshot = _AR(ar, approval_status="Pending")    # lenh THUONG thay snapshot cu
        writes = []

        def get_value(dt, name, fields=None, as_dict=False, for_update=False):
            if dt != "EC Approval Request":
                return dsr
            if fields == "name":
                return name
            return committed if for_update else snapshot
        engine = types.SimpleNamespace(
            _request_levels=lambda n: [types.SimpleNamespace(level_no=1)],
            _activate_level=lambda doc, lv: calls.__setitem__("activated", calls["activated"] + 1))
        import sys
        pkg = types.ModuleType("ecentric_workspace.approval_center.shared.workflow")
        pkg.transitions = engine
        saved = {k: sys.modules.get(k) for k in (
            "ecentric_workspace.approval_center.shared.workflow",
            "ecentric_workspace.approval_center.shared.workflow.transitions")}
        sys.modules["ecentric_workspace.approval_center.shared.workflow"] = pkg
        sys.modules["ecentric_workspace.approval_center.shared.workflow.transitions"] = engine
        try:
            g = {"AR": "EC Approval Request", "DSR": "EC Digital Signature Request",
                 "now_datetime": lambda: "now",
                 "guard": types.SimpleNamespace(requester_signature_required=lambda *a: True),
                 "events": types.SimpleNamespace(emit=lambda *a, **k: None),
                 "frappe": types.SimpleNamespace(
                     db=types.SimpleNamespace(get_value=get_value,
                                              set_value=lambda *a, **k: writes.append(a)),
                     get_doc=lambda *a: object())}
            _fns(_REQ, {"activate_level_one_after_requester_signature", "_NOT_ACTIVATABLE"}, g)
            out = g["activate_level_one_after_requester_signature"]("AR-1", "DSR-1")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        self._writes = writes
        return out, calls["activated"]

    def test_phieu_huy_tu_choi_da_duyet_khong_mo(self):
        for st in ("Cancelled", "Rejected", "Approved"):
            out, n = self._run(st)
            self.assertFalse(out["activated"], st)
            self.assertEqual(n, 0, st)
            self.assertIn("request_closed", out["reason"])

    def test_van_ghi_nguoi_de_nghi_da_ky(self):
        """Nguoi de nghi DA ky that tren cong - phieu da huy van phai ghi dung su that."""
        self._run("Cancelled")
        self.assertTrue(any(isinstance(w[-1], dict) and w[-1].get("requester_signature_status")
                            == "Signed" for w in self._writes))

    def test_phieu_dang_cho_van_mo_nhu_cu(self):
        out, n = self._run("Pending")
        self.assertTrue(out["activated"])
        self.assertEqual(n, 1)

    def test_doc_co_khoa_khong_doc_snapshot(self):
        """Gia lap REPEATABLE READ: lenh thuong thay 'Pending' (snapshot), lenh co khoa thay
        'Cancelled' (vua commit). Phai theo lenh co khoa (QC 12/11 tai hien duoc loi nay)."""
        out, n = self._run("Cancelled")
        self.assertEqual(n, 0)
        self.assertEqual(out["reason"], "request_closed:Cancelled")


if __name__ == "__main__":
    unittest.main()
