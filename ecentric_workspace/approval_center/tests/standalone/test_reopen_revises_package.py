# Copyright (c) 2026, eCentric and contributors
"""Đổi TÀI LIỆU CẦN KÝ thì đường "Gửi lại" phải dừng hẳn — và nói rõ phải làm gì thay thế.

Lịch sử của chỗ này, vì nó giải thích vì sao bộ test đổi hai lần trong bốn ngày:

**27/08** — `resubmit()` reset cấp duyệt và không đụng gì tới gói ký. Danh sách tệp bị đóng
băng từ lúc khoá, nên tài liệu đính kèm sau đó không vào gói, và mọi cấp sau ký lên bộ CŨ
trong khi ai cũng tưởng đang nhìn bộ đã bổ sung. Im lặng, chỉ lộ ra khi kiểm toán.

**28–30/08** — nối `create_revision` vào `on_request_reopened`: nội dung ký đổi thì tạo gói
phiên bản mới, ai đã ký thì ký lại.

**31/08 — bỏ hướng đó.** Chuỗi ấy KHÔNG BAO GIỜ kết thúc được:

  1. `create_revision` chép tệp + ô ký của gói cũ;
  2. `sign_on_submit` → `prepare` thêm tờ trình MỚI với `requires_signature=1`, không ô ký;
  3. `preflight_for_lock` từ chối → `frappe.throw`;
  4. Frappe rollback cả giao dịch → gói Draft vừa tạo BIẾN MẤT.

Nên cửa sổ đặt ô ký (`_setup_editable`, mở khi gói là Draft và đang chờ người đề nghị ký)
không bao giờ tồn tại ngoài giao dịch vừa bị huỷ. Người dùng bấm "Gửi lại" và chỉ nhận một
thông báo thiếu vị trí ký, lần nào cũng vậy.

Quy ước đã chốt: đổi tài liệu cần ký thì cấp duyệt **Từ chối**, người đề nghị bấm **"Tạo
phiếu mới từ phiếu này"**. Lý do cứng: SCTS chỉ nhận danh sách tệp lúc tạo tài liệu.

Bộ test này giữ ba điều: chỉ thêm bằng chứng thì đi tiếp; đổi tài liệu ký thì dừng và nói rõ
đường thay thế; và "không đọc được" phải nói đúng là không đọc được, không nói dối là đã đổi.
"""
import ast
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    root = _HERE
    for _i in range(8):
        path = os.path.join(root, *parts)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s" % (parts[-1],))


def _fn(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError("khong tim thay ham %s" % name)


def _joined(src):
    """Noi cac chuoi lien ke lai truoc khi so.

    Mot thong bao dai duoc chia thanh nhieu literal ("...phieu " / "nay..."), nen tim ca cum
    bang assertIn se truot du chuoi HIEN RA cho nguoi dung dung y het. Phep kiem truot theo
    kieu do la phep kiem noi doi theo chieu nguoc lai: no bao do tren ma nguon dung.
    """
    import re as _re
    return _re.sub(r'"\s*\n\s*"', "", src)


def _code_only(src):
    """Bỏ chú thích và docstring. Bốn lần trong hai ngày một phép kiểm bắt trúng chữ nằm
    trong lời văn giải thích của chính bản sửa; ở file này chú thích nhắc đủ mọi tên hàm."""
    code = re.sub(r"(?m)^\s*#.*$", "", src)
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    return code


class TestOnlyEvidenceGoesThrough(unittest.TestCase):
    """Trường hợp thường gặp nhất: Kế toán đòi thêm hoá đơn."""

    def setUp(self):
        self.src = _src("platform", "esign", "lifecycle.py")

    def test_khong_doi_noi_dung_ky_thi_di_tiep(self):
        body = _code_only(_fn(self.src, "on_request_reopened"))
        self.assertIn('verdict == "unchanged"', body)
        self.assertIn('out["unchanged"] = True', body)

    def test_goi_Draft_khong_can_lam_gi(self):
        # Gói Draft tự nhặt tệp mới, không có gì đóng băng để phải xử lý.
        self.assertRegex(self.src, r'_FROZEN = \([^)]*"Locked"')
        self.assertNotIn('"Draft"', re.search(r"_FROZEN = \([^)]*\)", self.src).group(0))


class TestChangingSignableContentStopsHere(unittest.TestCase):
    def setUp(self):
        self.src = _src("platform", "esign", "lifecycle.py")
        self.body = _code_only(_fn(self.src, "on_request_reopened"))

    def test_KHONG_con_tao_goi_phien_ban_moi(self):
        self.assertNotIn("create_revision", self.body,
                         "chuoi tao-ban-moi roi ky khong bao gio ket thuc duoc - xem docstring")

    def test_tu_choi_ngay_thay_vi_ghi_roi_rollback(self):
        self.assertIn("frappe.throw", self.body)

    def test_nhanh_da_doi_KHONG_co_duong_ra_nao_khac(self):
        # Chi kiem "co frappe.throw" thi mot dot bien chen `return out` NGAY TRUOC no van
        # xanh - nhanh throw thanh code chet ma test khong biet. Doc cay cu phap: sau cho
        # xu ly `unchanged`, moi duong di deu phai ket thuc bang mot loi goi throw.
        import ast as _ast
        fn = [n for n in _ast.parse(self.src).body
              if isinstance(n, _ast.FunctionDef) and n.name == "on_request_reopened"][0]
        after_unchanged = []
        seen_unchanged = False
        for stmt in fn.body:
            if not seen_unchanged:
                # `ast.dump` in chuoi bang NHAY DON: Constant(value='unchanged'). Tim
                # '"unchanged"' se khong bao gio khop, va vong lap ket thuc voi danh sach
                # rong - phep kiem do vi ly do sai.
                dumped = _ast.dump(stmt)
                if "unchanged" in dumped:
                    seen_unchanged = True
                continue
            after_unchanged.append(stmt)
        self.assertTrue(after_unchanged, "khong co gi sau nhanh unchanged")
        returns = [n for st in after_unchanged for n in _ast.walk(st)
                   if isinstance(n, _ast.Return)]
        self.assertEqual(returns, [],
                         "nhanh 'da doi' khong duoc tra ve binh thuong - phai dung han")
        throws = [n for st in after_unchanged for n in _ast.walk(st)
                  if isinstance(n, _ast.Call) and getattr(n.func, "attr", "") == "throw"]
        self.assertEqual(len(throws), 2, "mot throw cho 'da doi', mot cho 'khong doc duoc'")

    def test_khong_ghi_gi_truoc_khi_tu_choi(self):
        head = self.body.split("frappe.throw")[0]
        for write in ("set_value", "emit(", "insert("):
            self.assertNotIn(write, head,
                             "ghi roi moi tu choi = de lai rac neu giao dich khong rollback")

    def test_noi_ro_duong_THAY_THE(self):
        fn = _joined(_fn(self.src, "on_request_reopened"))
        self.assertIn("Từ chối", fn)
        self.assertIn("Tạo phiếu mới từ phiếu này", fn,
                      "chan mot duong ma khong chi duong khac = nguoi dung ket o day")

    def test_noi_ro_LY_DO(self):
        fn = _fn(self.src, "on_request_reopened")
        self.assertIn("nhà cung", fn,
                      "phai noi rang gioi han la cua nha cung cap, khong phai y minh")


class TestUnreadableIsNotTheSameAsChanged(unittest.TestCase):
    """Gộp hai thứ này vào một khi 'đã đổi' nghĩa là CHẶN HẲN thì một tệp không đọc được
    trên đĩa sẽ khoá vĩnh viễn mọi lần gửi lại — và thông báo còn nói sai sự thật."""

    def setUp(self):
        self.src = _src("platform", "esign", "lifecycle.py")

    def test_ham_tra_BA_ket_qua(self):
        body = _code_only(_fn(self.src, "_signable_content_verdict"))
        for verdict in ('"unchanged"', '"changed"', '"unreadable"'):
            self.assertIn(verdict, body)

    def test_moi_duong_doc_hong_deu_ra_unreadable(self):
        body = _code_only(_fn(self.src, "_signable_content_verdict"))
        # ba nhanh: package_files nem loi / thieu ma bam / _attached_signable_shas tra None
        self.assertEqual(body.count('return "unreadable"'), 3)

    def test_thong_bao_cua_hai_truong_hop_KHAC_nhau(self):
        fn = _fn(self.src, "on_request_reopened")
        self.assertIn("Không đọc được", fn)
        self.assertIn("Tài liệu cần ký đã thay đổi", fn)

    def test_tep_khong_doc_duoc_tra_None_chu_khong_tra_tap_rong(self):
        body = _code_only(_fn(self.src, "_attached_signable_shas"))
        self.assertIn("return None", body,
                      "tra tap rong = moi tep coi nhu bien mat = bao 'da doi' sai")


class TestTheEngineStillAsksFirst(unittest.TestCase):
    """Phần vẫn đúng từ bản 28/08: engine hỏi lớp ký số TRƯỚC khi reset cấp duyệt."""

    def setUp(self):
        self.tr = _src("approval_center", "shared", "workflow", "transitions.py")

    def test_resubmit_hoi_esign_truoc_khi_dung_toi_cap_duyet(self):
        body = _fn(self.tr, "resubmit")
        self.assertLess(body.index("_esign_on_reopen"), body.index("_request_levels"),
                        "hoi sau khi da reset = neu tu choi thi cap duyet da bi dung roi")

    def test_chi_dung_module_thieu_moi_duoc_bo_qua(self):
        body = _fn(self.tr, "_esign_on_reopen")
        self.assertIn("except ImportError", body)
        self.assertNotIn("except Exception", body,
                         "nuot loi that = gui lai im lang tren mot goi ky da cu")

    def test_tu_choi_lan_len_toi_nguoi_dung(self):
        # `frappe.throw` trong on_request_reopened phai di xuyen qua resubmit, khong bi bat.
        body = _fn(self.tr, "resubmit")
        self.assertNotIn("try:", body.split("_esign_on_reopen")[1][:200])


class TestNothingClaimsARevisionHappened(unittest.TestCase):
    """`reopen_notice` giờ luôn trả chuỗi rỗng - phải nói rõ, không để nó trông như còn dùng."""

    def test_ham_giu_lai_co_giai_thich(self):
        src = _src("platform", "esign", "lifecycle.py")
        fn = _fn(src, "reopen_notice")
        self.assertIn("khong bao gio con True", fn,
                      "code chet ma trong nhu con song la thu da lam panel bi bo quen 28/08")


if __name__ == "__main__":
    unittest.main()
