# Copyright (c) 2026, eCentric and contributors
"""Ba viec giao dien Hoan feedback 10/09.

  1. Phieu DA HUY phai danh dau do trong form chi tiet. EC-PAYR-2026-00047 da huy nhung
     badge van xam va cap 2 van hien "Dang xu ly" mau navy - nhin y het mot phieu dang
     chay. Goc: `buildStepper` chua bao gio doc `approval_status`; no chi nhin
     `level_status` / `current_level`, ma huy phieu KHONG doi hai thu do.

  2. Hub /approvals/all-requests "to qua" - giam 1-2 co chu o tab, tieu de, o nhap filter.

  3. Hang filter hub trong "lon xon nhu vo hai dong". DA DO TREN PROD: grid KHONG xuong
     dong - 8 cot mot hang (8 x 132.75px trong container 1118px). Cai lech la NHAN, chenh
     10px: item cao 48px (label 16 + input 30 + margin 2) so voi 58px (`span.ec-dp-wrap`
     cao 40 - o lich) va 57px (`div.ec-cb` cao 39 - o Trang thai). `.fgrid` dat
     `align-items:end` nen o nao cao hon se day NHAN cua no len tren.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_CHU_THICH = re.compile(r"<!--.*?-->|/\*.*?\*/", re.S)


def _bo_chu_thich(s):
    """Boc chu thich TRUOC khi quet nguon.

    Da tra gia cho bai hoc nay 08/09: chinh CAU CHU THICH vua viet cung khop mau dang quet,
    nen test do vi mot ly do thuoc ve PHEP DO chu khong phai thuoc ve code. O day dau file
    hub co doan giai thich vi sao `.ec-dp-wrap` / `.ec-cb` cao hon o nhap thuong - nhung
    dong do khong phai luat CSS, khong the doi hoi chung mang selector gioi han pham vi.
    """
    return _CHU_THICH.sub("", s)
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_PR_UI = ("approval_center", "features", "payment_request", "ui", "main_section.html")
_HUB_UI = ("approval_center", "ui", "all_requests", "main_section.html")


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


class TestPhieuDaHuyDanhDauDo(unittest.TestCase):
    def setUp(self):
        self.h = _read(*_PR_UI)

    def test_badge_huy_chuyen_sang_DO(self):
        self.assertIn('"Cancelled":["b-red","Đã hủy"]', self.h)
        self.assertNotIn('"Cancelled":["b-gray"', self.h, "xam la cai dang sua")

    def test_tien_trinh_doc_TRANG_THAI_PHIEU_chu_khong_chi_tung_cap(self):
        """Day la goc cua loi: cap 2 ra "Dang xu ly" vi khong ai hoi phieu con song khong."""
        self.assertIn("function markCancelled", self.h)
        i = self.h.index("function markCancelled")
        than = self.h[i:i + 900]
        self.assertIn('approval_status!=="Cancelled"', than)
        self.assertIn('state:"cancelled"', than)

    def test_buildStepper_CO_goi_markCancelled(self):
        """Viet ham ma khong noi vao duong render thi no la code chet - dung cai bay da lam
        `mark_verified` bi bo quen tu 28/08 den 09/09."""
        self.assertIn("renderStepsHTML(markCancelled(markSignWait(steps, det), det), det)", self.h)

    def test_cac_buoc_sau_khi_huy_KHONG_con_goi_la_Cho(self):
        """Huy roi thi cac cap sau khong bao gio toi luot - de "Cho" la noi sai su that."""
        i = self.h.index("function markCancelled")
        self.assertIn('statusLabel:"Không thực hiện"', self.h[i:i + 900])

    def test_co_mau_va_nhan_cho_trang_thai_cancelled(self):
        self.assertIn('cancelled:"Đã hủy"', self.h)
        self.assertIn('cancelled:"var(--red)"', self.h)
        self.assertIn(".step.cancelled .step-dot", self.h)
        self.assertIn(".stepline.is-cancelled::after", self.h)

    def test_dau_X_dung_cho_ca_cancelled(self):
        self.assertIn('s.state==="rejected"||s.state==="cancelled"', self.h)

    def test_KHONG_dung_toi_duong_ky_so(self):
        """Dot nay chi doi cach HIEN THI. Cham vao khoi ky so la viec khac hoan toan."""
        for cam in ("approve_and_sign", "authorize_resend", "sync_signatures_from_provider"):
            i = self.h.index("function markCancelled")
            self.assertNotIn(cam, self.h[i:i + 900], cam)


class TestHubFilterThangHang(unittest.TestCase):
    def setUp(self):
        self.h = _read(*_HUB_UI)

    def test_ep_chieu_cao_HAI_thanh_phan_dung_chung(self):
        """`.ec-dp-wrap` (40px) va `.ec-cb` (39px) cao hon o nhap thuong (30px) - do la ly do
        NHAN bi lech, khong phai vi grid xuong dong."""
        self.assertIn("#ec-apl-root .fgrid .ec-dp-wrap", self.h)
        self.assertIn("#ec-apl-root .fgrid .ec-cb", self.h)

    def test_ghi_de_CO_GIOI_HAN_trong_fgrid(self):
        """`ec-dp-*` va `ec-cb` la asset dung chung TOAN SITE. Mot luat khong gioi han pham vi
        se doi giao dien cua nhung trang khac ma khong ai ngo - dung bai hoc
        'asset toan site: TRANG tu khai quyen so huu'."""
        for dong in _bo_chu_thich(self.h).splitlines():
            if ".ec-dp-" in dong or ".ec-cb" in dong:
                self.assertIn("#ec-apl-root .fgrid", dong,
                              "luat cham vao asset dung chung phai gioi han trong .fgrid: " + dong.strip())

    def test_khong_con_can_day(self):
        i = self.h.index("#ec-apl-root .fgrid{")
        dong = self.h[i:self.h.index("\n", i)]
        self.assertIn("align-items:start", dong)
        self.assertNotIn("align-items:end", dong)

    def test_nut_Xoa_loc_tu_chua_khoang_bang_chieu_cao_nhan(self):
        """Nut khong co nhan phia tren; khong chua khoang do thi day nut lech len."""
        i = self.h.index("#ec-apl-root .fend .btn{")
        self.assertIn("margin-top:16px", self.h[i:self.h.index("\n", i)])

    def test_giam_co_chu_tab_va_tieu_de(self):
        for i, cu in ((self.h.index("#ec-apl-root .tab{"), "font-size:14px"),
                      (self.h.index("#ec-apl-root .apl-title{"), "font-size:17px")):
            self.assertNotIn(cu, self.h[i:self.h.index("\n", i)], cu + " la co cu")
        self.assertIn("font-size:12.5px", self.h[self.h.index("#ec-apl-root .tab{"):][:200])

    def test_KHONG_dung_zoom_cho_ca_trang(self):
        """`zoom` lam lech moi phep do toa do (screenshot, getBoundingClientRect) va keo theo
        ca vo shell dung chung - giam co chu tung cho thi kiem soat duoc."""
        self.assertNotIn("zoom:", self.h)


class TestPatchVaBanKe(unittest.TestCase):
    def test_patch_khai_va_kiem_ket_qua_CHO_CA_HAI_trang(self):
        self.assertIn("p173_resync_cancelled_badge_and_hub_filters", _read("patches.txt"))
        src = _read("approval_center", "patches",
                    "p173_resync_cancelled_badge_and_hub_filters.py")
        self.assertIn('action == "refused"', src, "phai bao khi bi tu choi ghi")
        self.assertIn("approvals/payment-request", src)
        self.assertIn("approvals/all-requests", src)

    def test_mot_trang_hong_khong_keo_theo_trang_kia(self):
        src = _read("approval_center", "patches",
                    "p173_resync_cancelled_badge_and_hub_filters.py")
        i = src.index("def execute()")
        self.assertIn("try:", src[i:], "moi trang phai co try rieng")
        self.assertIn("frappe.log_error(frappe.get_traceback()", src[i:])

    def test_ban_ke_ma_bam_cap_nhat_cho_CA_HAI_trang(self):
        import hashlib
        import json
        man = json.loads(_read("approval_center", "patches", "resync_manifest.json"))
        for khoa, duong in (("approval_center/features/payment_request/ui/main_section.html", _PR_UI),
                            ("approval_center/ui/all_requests/main_section.html", _HUB_UI)):
            raw = io.open(os.path.join(_APP, *duong), "rb").read().replace(b"\r\n", b"\n")
            self.assertEqual(man[khoa]["sha256"], hashlib.sha256(raw).hexdigest(), khoa)
            self.assertEqual(man[khoa]["last_resync_patch"],
                             "p173_resync_cancelled_badge_and_hub_filters", khoa)


if __name__ == "__main__":
    unittest.main()
