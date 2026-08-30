# Copyright (c) 2026, eCentric and contributors
"""Bị trả lại để bổ sung chứng từ: phải có chỗ tải lên, và tệp đó KHÔNG phải để ký.

30/08. Màn hình "Chỉnh sửa & gửi lại" không có một bề mặt tải lên nào, đúng lúc người đề
nghị cần bổ sung chứng từ nhất. Hai luật gặp nhau: ô `request_attachment` cũ bị CSS ẩn theo
nguyên tắc "một bề mặt tải lên duy nhất", còn bề mặt duy nhất đó - "+ Tải tài liệu" - lại
đóng theo `_setup_editable`, vốn trả "already_submitted" ngay khi có Approval Request.

Gốc rễ là gộp hai câu hỏi khác nhau vào MỘT cổng:

  * "được sửa THIẾT LẬP KÝ không?"  - phân loại tài liệu, đặt ô ký. Đã khoá gói thì không.
  * "được đính kèm thêm BẰNG CHỨNG không?" - một tờ hoá đơn. Câu này độc lập hoàn toàn.

Quy ước đã chốt: tệp thêm ở giai đoạn bị trả lại LUÔN là bộ chứng từ - không ký, không vào
gói, không đẩy sang SCTS. Muốn đổi tài liệu cần ký thì cấp duyệt Từ chối, làm phiếu mới.

Lý do rất cứng và không thương lượng được: SCTS chỉ nhận danh sách tệp LÚC TẠO tài liệu.
Không có endpoint thêm trang vào tài liệu đã tạo (`providers/scts.py` chỉ gửi `documents` một
lần trong AddDocument). Nên "vừa giữ chữ ký cũ vừa thêm tệp vào hồ sơ bên SCTS" là thứ không
dựng được, chứ không phải chưa dựng.
"""
import io
import os
import re
import types
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


def _src(*parts):
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


_DS = _src("platform", "esign", "document_setup.py")
_UI = _src("platform", "esign", "ui", "document_signing_section.html")


def _load_can_add_supporting(ar, status, raises=False):
    """Chay dung ham that, khong grep."""
    body = re.search(r"(?m)^def _can_add_supporting\(.*?(?=\ndef )", _DS, re.S).group(0)

    def _get_value(dt, name, field):
        if raises:
            raise Exception("db down")
        return status

    env = {"perms": types.SimpleNamespace(business_approval_request=lambda b, n: ar),
           "frappe": types.SimpleNamespace(db=types.SimpleNamespace(get_value=_get_value)),
           "AR": "EC Approval Request"}
    exec(compile(body, "document_setup.py", "exec"), env)
    return env["_can_add_supporting"]


class TestTheDoorOpensExactlyWhenSentBack(unittest.TestCase):
    def test_dang_bi_tra_lai_thi_dinh_kem_duoc(self):
        fn = _load_can_add_supporting("AR-1", "Information Required")
        self.assertTrue(fn("EC Payment Request", "PR-1", True))

    def test_dang_cho_duyet_binh_thuong_thi_khong(self):
        fn = _load_can_add_supporting("AR-1", "Pending")
        self.assertFalse(fn("EC Payment Request", "PR-1", True),
                         "ho so dang chay khong duoc dong them gi")

    def test_da_duyet_xong_thi_khong(self):
        fn = _load_can_add_supporting("AR-1", "Approved")
        self.assertFalse(fn("EC Payment Request", "PR-1", True))

    def test_da_tu_choi_thi_khong(self):
        fn = _load_can_add_supporting("AR-1", "Rejected")
        self.assertFalse(fn("EC Payment Request", "PR-1", True))

    def test_khong_phai_nguoi_de_nghi_thi_khong(self):
        fn = _load_can_add_supporting("AR-1", "Information Required")
        self.assertFalse(fn("EC Payment Request", "PR-1", False),
                         "cap duyet khong duoc tu them chung tu vao ho so nguoi khac")

    def test_chua_gui_thi_khong_di_duong_nay(self):
        fn = _load_can_add_supporting(None, None)
        self.assertFalse(fn("EC Payment Request", "PR-1", True),
                         "chua gui thi da co duong tai len binh thuong")

    def test_doc_hong_thi_dong_cua(self):
        fn = _load_can_add_supporting("AR-1", "Information Required", raises=True)
        self.assertFalse(fn("EC Payment Request", "PR-1", True))


class TestItIsSeparateFromTheSetupGate(unittest.TestCase):
    """Neu ai do gop lai lam mot, be tac 30/08 quay lai nguyen ven."""

    def test_khong_goi_setup_editable(self):
        # Doc CAY CU PHAP, khong grep chuoi: docstring cua chinh ham nay co nhac ten
        # `_setup_editable` de giai thich vi sao hai cong phai tach roi, nen phep grep se
        # khop voi loi van giai thich va bao do trong khi ma nguon hoan toan dung. Cung ho
        # voi cai bay da vap sang nay o test CSS.
        import ast
        fn = next(n for n in ast.walk(ast.parse(_DS))
                  if isinstance(n, ast.FunctionDef) and n.name == "_can_add_supporting")
        called = {getattr(c.func, "id", None) or getattr(c.func, "attr", None)
                  for c in ast.walk(fn) if isinstance(c, ast.Call)}
        self.assertNotIn("_setup_editable", called,
                         "hai cong phai doc lap - gop lai la tai dien be tac")

    def test_trang_thai_duoc_tra_ra_cho_giao_dien(self):
        self.assertIn('"can_add_supporting": can_add_supporting', _DS)


class TestAFileOutsideALockedPackageIsSupporting(unittest.TestCase):
    """Khong the vao goi da khoa -> khong duoc bao la 'can ky'."""

    def _req_sig(self, cur_name, is_draft):
        m = re.search(r"req_sig = bool\(is_draft\) if cur_name else True", _DS)
        self.assertIsNotNone(m, "khong tim thay luat mac dinh - phep kiem da mu")
        return eval(m.group(0).split("= ", 1)[1],
                    {}, {"is_draft": is_draft, "cur_name": cur_name})

    def test_chua_co_goi_thi_mac_dinh_can_ky(self):
        self.assertTrue(self._req_sig(None, False), "giai doan lap ho so: mac dinh la to trinh")

    def test_goi_con_nhap_thi_van_can_ky(self):
        self.assertTrue(self._req_sig("PKG-1", True))

    def test_goi_da_khoa_thi_la_bo_chung_tu(self):
        self.assertFalse(self._req_sig("PKG-1", False),
                         "doi chu ky tren mot tep khong the vao goi = hua dieu khong lam duoc")


class TestTheButtonOpensOnThatFlag(unittest.TestCase):
    def test_giao_dien_doc_can_add_supporting(self):
        self.assertIn("STATE.can_add_supporting", _UI)

    def test_nut_mo_khi_chi_duoc_them_bang_chung(self):
        m = re.search(r"upBtn\.disabled = ([^;]+);", _UI)
        self.assertIsNotNone(m, "khong tim thay cho bat/tat nut")
        self.assertIn("supportOnly", m.group(1),
                      "nut phai mo o ca truong hop chi-them-bang-chung")

    def test_noi_ro_tep_do_khong_can_ky(self):
        self.assertIn("bộ chứng từ", _UI,
                      "phai noi ro tep them o buoc nay khong can ky")


class TestTheLegacyFieldStaysHidden(unittest.TestCase):
    """Ban va 30/08 mo lai o cu da bi go - mot be mat tai len duy nhat."""

    def test_khong_con_luat_mo_lai_o_cu(self):
        css = re.sub(r"/\*[\s\S]*?\*/", " ", _UI)
        self.assertNotIn("payr-formwrap:has(#payr-resubmit)", css,
                         "ban va cu dung lai be mat tai len thu hai - da chot go")

    def test_van_con_luat_an_o_cu(self):
        css = re.sub(r"/\*[\s\S]*?\*/", " ", _UI)
        self.assertIn('.fld:has([data-upload="request_attachment"])', css)


if __name__ == "__main__":
    unittest.main()
