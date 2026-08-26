# Copyright (c) 2026, eCentric and contributors
"""Ba lỗi giao diện phát hiện khi pilot UAT VOID 5/6 (26–27/08/2026).

Đây là các lỗi CHỈ nhìn thấy trên trình duyệt thật, nên khoá lại bằng cách đối chiếu chính
mã nguồn đã ship — kiểu test này mù nếu chỉ grep chuỗi, vì vậy mỗi khẳng định đều đi kèm một
khẳng định ngược (thứ PHẢI biến mất) để việc sửa mã buộc phải sửa cả test.

  python -m unittest ecentric_workspace.approval_center.tests.standalone.test_ui_regressions_uat5
"""
import os
import unittest

_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_DRAWER = os.path.join(_APP, "ecentric_workspace", "platform", "esign", "ui",
                       "document_signing_section.html")
_FORMKIT = os.path.join(_APP, "ecentric_workspace", "public", "js", "ec_formkit.bundle.js")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestTrySignRendersSomething(unittest.TestCase):
    """Nút "Ký thử" đổi màu nhưng không vẽ gì: vòng lặp chạy trên `layer._kids`, một thuộc
    tính KHÔNG BAO GIỜ được gán ở bất kỳ đâu trong file."""

    def test_no_longer_reads_the_phantom_kids_property(self):
        src = _read(_DRAWER)
        self.assertNotIn("layer._kids", src,
                         "_kids khong bao gio duoc gan -> vong lap luon rong")

    def test_reads_the_boxes_actually_in_the_dom(self):
        src = _read(_DRAWER)
        self.assertIn('layer.querySelectorAll(".ecd-box")', src)

    def test_refuses_when_there_is_no_box_instead_of_going_silent(self):
        src = _read(_DRAWER)
        self.assertIn("Chưa có ô chữ ký nào", src,
                      "khong co o thi phai noi ra, khong duoc doi mau nut roi im lang")

    def test_surfaces_the_backend_reason(self):
        """Backend trả `reason` khi không lấy được mẫu — phải hiện ra, không nuốt."""
        src = _read(_DRAWER)
        self.assertIn("o.reason", src)


class TestSignerPanelDoesNotClipLastCard(unittest.TestCase):
    """Thẻ người ký cuối (CEO) bị thanh chân trang che, bấm không được."""

    def test_grid_children_can_shrink(self):
        src = _read(_DRAWER)
        self.assertIn(".ecd-drawer .ecd-body > *{min-height:0}", src,
                      "con cua grid mac dinh min-height:auto -> cot tran ra ngoai")

    def test_signer_column_has_bottom_breathing_room(self):
        src = _read(_DRAWER)
        self.assertIn(".ecd-signers{overflow:auto;padding:16px 16px 32px}", src)
        self.assertNotIn(".ecd-signers{overflow:auto;padding:16px}", src,
                         "padding cu khong chua duoc the cuoi cung")


class TestFormkitDoesNotDoubleUpUploaders(unittest.TestCase):
    """Trang Payment Request có bộ tải tệp riêng nhưng formkit bọc thêm một lớp nữa,
    thành hai vùng kéo-thả chồng nhau. Lọc theo đường dẫn không đủ vì nhiều trang cùng
    nằm dưới /approvals."""

    def test_skips_inputs_owned_by_the_page(self):
        src = _read(_FORMKIT)
        self.assertIn('inp.hasAttribute("data-upload")', src)

    def test_offers_an_explicit_opt_out_for_future_pages(self):
        src = _read(_FORMKIT)
        self.assertIn('inp.closest("[data-ec-no-formkit]")', src,
                      "trang moi phai tu choi duoc ma khong can sua lai formkit")

    def test_the_payment_request_uploader_is_marked(self):
        """Ô tải tệp của Payment Request phải mang dấu `data-upload` để guard nhận ra."""
        page = os.path.join(_APP, "ecentric_workspace", "approval_center", "features",
                            "payment_request", "ui", "main_section.html")
        self.assertIn('data-upload="request_attachment"', _read(page))

    def test_the_esign_upload_area_claims_ownership(self):
        """Vùng dropzone thừa trong ảnh chụp thực ra bọc `#ecdUpload` của khu ký số — ô đó
        KHÔNG có `data-upload`, nên guard đầu tiên không chạm tới. Khu này phải tự khai."""
        src = _read(_DRAWER)
        self.assertIn('<div class="ecd-up" data-ec-no-formkit>', src)
        self.assertIn('id="ecdUpload" multiple style="display:none" data-ec-no-formkit', src)

    def test_hidden_inputs_are_left_alone(self):
        """Ô tải tệp bị ẩn = trang tự điều khiển bằng nút riêng; bọc vào là sinh vùng thừa."""
        src = _read(_FORMKIT)
        self.assertIn('inp.style.display === "none"', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
