# Copyright (c) 2026, eCentric and contributors
"""Tắt cổng ký số thì chữ ký biến mất khỏi quy trình — giờ nó thành một món nợ hiện ra.

Hai đường xử lý khác nhau, và sự khác nhau đó chưa từng được ghi ở đâu:

  * người đề nghị — `requester_signature_required` dùng `get_enabled_profile`, KHÔNG phụ
    thuộc cổng. Cổng tắt vẫn bắt ký;
  * cấp duyệt — `level_requires_signature` dùng `get_active_profile`, PHỤ THUỘC cổng. Cổng
    tắt thì `assert_level_completable` thoát sớm, và nút "Duyệt" thường hoàn tất một cấp lẽ
    ra bắt buộc ký số. Không chữ ký, không cảnh báo, không một dòng nào trong lịch sử.

Nhìn lại sau vài tháng, phiếu đó trông y hệt một phiếu đã ký đầy đủ.

Đã chốt 31/08: phiếu vẫn đi tiếp và hoàn tất được — đó là quyết định vận hành. Đổi lại,
món nợ phải HIỆN RA. Một món nợ không ai nhìn thấy là một món nợ không bao giờ được trả.

Và không có "tự đẩy qua SCTS khi cổng mở lại": chữ ký số là hành động của con người ký bằng
chứng thư của họ, không phải dữ liệu để hoãn rồi đẩy sau. Chỉ chính người duyệt đó ký được.
"""
import ast
import io
import json
import os
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


def _read(*parts):
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


_GUARD = _read("platform", "esign", "guard.py")
_OPS = _read("platform", "esign", "ops.py")
_UI = _read("platform", "esign", "ui", "ops_page.html")


def _fn(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError("khong tim thay ham %s" % name)


class TestOneBodyForOneQuestion(unittest.TestCase):
    """Ban dau viet mot ham song song `_policy_wants_level` - va do dung la cach hai luat
    bat dau lech nhau. Gio ca hai cau hoi di qua CUNG MOT than."""

    def test_khong_con_ham_song_song(self):
        names = [n.name for n in ast.parse(_GUARD).body
                 if isinstance(n, ast.FunctionDef)]
        self.assertNotIn("_policy_wants_level", names,
                         "hai ban sao cua cung mot luat se troi khoi nhau")

    def test_co_tham_so_bo_qua_cong(self):
        fn = [n for n in ast.parse(_GUARD).body
              if isinstance(n, ast.FunctionDef) and n.name == "level_requires_signature"][0]
        args = [a.arg for a in fn.args.args]
        self.assertIn("ignore_gates", args)

    def test_bo_qua_cong_thi_dung_duong_tra_cuu_doc_lap(self):
        body = _fn(_GUARD, "level_requires_signature")
        self.assertIn("get_enabled_profile", body,
                      "duong khong phu thuoc cong")
        self.assertIn("get_active_profile", body,
                      "duong phu thuoc cong - van phai giu cho hanh vi cu")


class TestTheGateNoLongerFailsSilently(unittest.TestCase):
    def test_cong_dong_thi_GHI_NO_chu_khong_thoat_im(self):
        body = _fn(_GUARD, "assert_level_completable")
        self.assertIn("_record_signature_debt", body,
                      "truoc day nhanh nay `return` khong lam gi ca")

    def test_van_KHONG_chan_duyet(self):
        # Quyet dinh van hanh 31/08: phieu di tiep. Ham ghi no khong duoc nem loi.
        body = _fn(_GUARD, "_record_signature_debt")
        self.assertNotIn("frappe.throw", body,
                         "ghi no khong duoc chan duyet - do la quyet dinh da chot")

    def test_ghi_no_hong_khong_lam_gay_viec_duyet(self):
        body = _fn(_GUARD, "_record_signature_debt")
        self.assertIn("except Exception", body)
        self.assertIn("log_error", body, "khong nuot im lang - Error Log giu lai")

    def test_chi_ghi_khi_CHINH_SACH_that_su_doi_ky(self):
        body = _fn(_GUARD, "_record_signature_debt")
        self.assertIn("ignore_gates=True", body,
                      "loai yeu cau khong dung ky so thi khong co gi de no")

    def test_co_ghi_vao_lich_su_phieu(self):
        body = _fn(_GUARD, "_record_signature_debt")
        self.assertIn("log_action", body)
        self.assertIn("cổng ký số đang tắt", body,
                      "dong lich su phai noi ro VI SAO cap nay khong co chu ky")

    def test_co_phat_su_kien(self):
        body = _fn(_GUARD, "_record_signature_debt")
        self.assertIn("SignatureDeferred", body)

    def test_loai_su_kien_da_khai_bao(self):
        j = _read("approval_center", "doctype", "ec_digital_signature_event",
                  "ec_digital_signature_event.json")
        self.assertIn("SignatureDeferred", j,
                      "emit mot loai chua khai bao thi Frappe luu sai - loi chi lo khi chay")


class TestTheDebtIsStoredWhereItBelongs(unittest.TestCase):
    def test_cap_duyet_co_truong_ghi_no(self):
        j = json.loads(_read("approval_center", "doctype", "ec_approval_request_level",
                             "ec_approval_request_level.json"))
        names = [f["fieldname"] for f in j["fields"]]
        for f in ("signature_deferred", "signature_deferred_at", "signature_deferred_by",
                  "signature_settled_at"):
            self.assertIn(f, names)

    def test_cac_truong_do_chi_doc(self):
        j = json.loads(_read("approval_center", "doctype", "ec_approval_request_level",
                             "ec_approval_request_level.json"))
        for f in j["fields"]:
            if f["fieldname"].startswith("signature_"):
                self.assertEqual(f.get("read_only"), 1,
                                 "%s phai chi doc - khong ai go tay xoa mot mon no" % f["fieldname"])


class TestTheDebtIsVisible(unittest.TestCase):
    """Mot mon no khong ai nhin thay la mot mon no khong bao gio duoc tra."""

    def test_ops_liet_ke_no_chu_ky(self):
        names = [n.name for n in ast.parse(_OPS).body if isinstance(n, ast.FunctionDef)]
        self.assertIn("signature_debts", names)

    def test_chi_liet_ke_no_CHUA_TRA(self):
        body = _fn(_OPS, "signature_debts")
        self.assertIn("signature_settled_at", body,
                      "da tra roi ma van hien thi thi danh sach nhanh chong vo nghia")

    def test_dem_vao_the_dau_trang(self):
        self.assertIn('"signature_debts": len(signature_debts', _OPS)

    def test_giao_dien_co_bang_rieng(self):
        self.assertIn("signature_debts", _UI)
        self.assertIn("debtRow", _UI)

    def test_danh_dau_no_tren_phieu_DA_DUYET_XONG(self):
        # Phieu da hoan tat thi mon no de bi bo quen nhat - phai noi thang ra.
        self.assertIn("Phiếu đã duyệt xong", _UI)

    def test_noi_ro_khong_ai_ky_thay_duoc(self):
        self.assertIn("Không ai ký thay được", _UI,
                      "chu ky so la hanh dong cua nguoi giu chung thu - khong hoan lai duoc")


if __name__ == "__main__":
    unittest.main()
