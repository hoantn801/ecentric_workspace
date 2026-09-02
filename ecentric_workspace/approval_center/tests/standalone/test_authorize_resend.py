# Copyright (c) 2026, eCentric and contributors
"""Gui lai co kiem: chi khi nha cung cap xac nhan nguoi ky CHUA co chu ky, chi do ops, mot lan.

"Thu lai" khong gui lai - dung y, lenh ky khong idempotent. Nhung 00042/DSR-00027: lenh
pool 02/09 03:25 tra 2xx roi khong lam gi; SCTS xac nhan `expected_signer_absent`; Thu lai
chi quay ve Manual Review mai mai. Chan do can mot duong ra CO KIEM, khong phai sua tay DB.

Ba bat bien:
  1. Chot mot chieu cu VAN LA cau lenh dau tien cua nhanh Queued (test_e2e3_no_second_submit
     giu). Chi khi `resend_authorized` moi qua duoc no.
  2. Worker XOA co TRUOC khi gui - gui hong thi ve Manual Review, ops phai xac nhan lai.
     Khong bao gio mot co cu cho phep gui lan ba.
  3. authorize_resend hoi nha cung cap NGAY LUC DO va chi nhan `expected_signer_absent` /
     `not_enough_signatures`. Da ky -> tu choi (dung Thu lai). Khong hoi duoc -> tu choi.
"""
import ast
import io
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()


def _src(rel):
    return io.open(os.path.join(_ROOT, "platform", "esign", rel), encoding="utf-8").read()


def _fn(src, name):
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError("khong thay ham " + name)


def _calls(node):
    return [getattr(c.func, "attr", None) or getattr(c.func, "id", None)
            for c in ast.walk(node) if isinstance(c, ast.Call)]


class TestWorkerXoaCoTruocKhiGui(unittest.TestCase):
    def setUp(self):
        self.src = _src("tasks.py")
        self.fn = _fn(self.src, "process_signing_request")

    def _resend_branch(self):
        """`if may_have_sent:` (KHONG co `and not resend_authorized`) - nhanh gui lai."""
        for n in ast.walk(self.fn):
            if isinstance(n, ast.If):
                seg = ast.get_source_segment(self.src, n.test) or ""
                if seg.strip() == "may_have_sent":
                    return n
        raise AssertionError("khong thay nhanh gui lai `if may_have_sent:`")

    def test_chot_cu_van_dung_truoc_va_xet_co(self):
        than = ast.get_source_segment(self.src, self.fn) or ""
        i_chot = than.find('if may_have_sent and not int(dsr.get("resend_authorized")')
        i_resend = than.find("if may_have_sent:\n")
        self.assertNotEqual(i_chot, -1, "chot mot chieu mat dieu kien resend_authorized")
        self.assertNotEqual(i_resend, -1)
        self.assertLess(i_chot, i_resend, "chot phai dung TRUOC nhanh gui lai")

    def test_xoa_co_TRUOC_moi_lenh_gui(self):
        br = self._resend_branch()
        body_src = "\n".join(ast.get_source_segment(self.src, s) or "" for s in br.body)
        self.assertIn('"resend_authorized", 0', body_src, "khong xoa co = co cu cho gui lan ba")
        for cam in ("transition_with_recipients", "approve_and_sign", "bulk_process"):
            self.assertNotIn(cam, _calls(br), "nhanh xoa co KHONG duoc tu gui - gui o duoi, "
                                              "sau khi co da xoa: %s" % cam)
        # ...va viec xoa co nam TRUOC lenh gui trong than ham
        than = ast.get_source_segment(self.src, self.fn) or ""
        self.assertLess(than.find('"resend_authorized", 0'), than.find("transition_with_recipients("))

    def test_ghi_su_kien_ResendExecuted(self):
        self.assertIn('"ResendExecuted"', ast.get_source_segment(self.src, self._resend_branch()) or "")


class TestAuthorizeResendHoiNhaCungCapTruoc(unittest.TestCase):
    def setUp(self):
        self.src = _src("api.py")
        self.fn = _fn(self.src, "authorize_resend")
        self.than = ast.get_source_segment(self.src, self.fn) or ""

    def test_chi_System_Manager_va_POST(self):
        self.assertIn("assert_system_manager", _calls(self.fn))
        decos = [ast.get_source_segment(self.src, d) or "" for d in self.fn.decorator_list]
        self.assertTrue(any('methods=["POST"]' in d for d in decos), "lenh GHI phai la POST")

    def test_bat_buoc_ly_do(self):
        self.assertIn("Bắt buộc nhập lý do", self.than)

    def test_chi_tu_Manual_Review(self):
        self.assertIn('dsr.status != "Manual Review"', self.than)

    def test_HOI_nha_cung_cap_va_dung_CHUNG_verify(self):
        c = _calls(self.fn)
        self.assertIn("poll_status", c, "khong hoi nha cung cap = doan")
        self.assertIn("verify_signed_result", c, "phai dung CHUNG phep verify voi worker")
        self.assertIn("_expected_for", c, "cung expected voi worker (thu tu, cua so)")

    def test_da_ky_thi_tu_choi(self):
        self.assertIn("if vr.ok:", self.than)
        i = self.than.find("if vr.ok:")
        self.assertIn("frappe.throw", self.than[i:i + 200], "da co chu ky ma cho gui lai = ky dup")

    def test_chi_nhan_hai_ly_do_chua_ky(self):
        self.assertIn('startswith("expected_signer_absent")', self.than)
        self.assertIn('startswith("not_enough_signatures")', self.than)
        i = self.than.find('startswith("not_enough_signatures")')
        self.assertIn("frappe.throw", self.than[i:i + 300],
                      "ly do khac (khong doc duoc gio, lech tai lieu...) phai TU CHOI")

    def test_khong_hoi_duoc_thi_tu_choi(self):
        i = self.than.find("adapter.poll_status")
        self.assertIn("except Exception", self.than[i:i + 200])
        self.assertIn("frappe.throw", self.than[i:i + 400], "khong hoi duoc ma van cho = doan")

    def test_dat_co_ghi_su_kien_roi_moi_retry(self):
        i_co = self.than.find('"resend_authorized", 1')
        i_ev = self.than.find('"ResendAuthorized"')
        i_retry = self.than.find("retry_signature_request(")
        self.assertTrue(-1 < i_co < i_ev < i_retry,
                        "thu tu phai la: dat co -> ghi su kien -> xep hang lai")
        seg = self.than[i_ev:i_ev + 400]
        for k in ('"boi"', '"ly_do"', '"nha_cung_cap_noi"'):
            self.assertIn(k, seg, "su kien phai ghi ai / vi sao / nha cung cap noi gi")


if __name__ == "__main__":
    unittest.main()
