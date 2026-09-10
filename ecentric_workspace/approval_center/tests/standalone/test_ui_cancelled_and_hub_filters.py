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


_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)


def _khoi_style(s):
    """Chi lay phan trong <style>. Luat CSS nam o day; moi thu khac la markup hoac JS."""
    return _STYLE.findall(s)


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
        """`ec-dp-*` va `ec-cb` la asset dung chung TOAN SITE. Mot LUAT CSS khong gioi han
        pham vi se doi giao dien cua nhung trang khac ma khong ai ngo - bai hoc
        'asset toan site: TRANG tu khai quyen so huu'.

        CHI quet trong <style>. Ban dau quet ca file, nen mot dong JAVASCRIPT hop le -
        `t.closest(".ec-cb-display")` - cung bi doi hoi mang selector CSS. Chon nhieu cham
        thu hai trong mot ngay: phep do phai cat dung loai dong minh muon kiem.
        """
        for khoi in _khoi_style(self.h):
            for dong in _bo_chu_thich(khoi).splitlines():
                if ".ec-dp-" in dong or ".ec-cb" in dong:
                    self.assertIn("#ec-apl-root .fgrid", dong,
                                  "luat CSS cham vao asset dung chung phai gioi han trong "
                                  ".fgrid: " + dong.strip())

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

    def test_mo_mot_o_loc_thi_dong_cac_o_kia(self):
        """DO TREN PRODUCTION 10/09: bam lan luot 4 o loc -> CA BON panel cung mo, chong len
        bang ben duoi. Goc o `ec_formkit.bundle.js`: nut goi `e.stopPropagation()` nen cu bam
        khong toi duoc bo dong-khi-bam-ra-ngoai o tang document cua ba o kia."""
        self.assertIn("function dongOLocKhac", self.h)
        i = self.h.index("function dongOLocKhac")
        than = self.h[i:i + 900]
        self.assertIn(".ec-cb-panel", than)
        self.assertIn("hidden=true", than.replace(" ", ""))

    def test_nghe_o_PHA_BAT_va_trong_pham_vi_fgrid(self):
        """Hai dieu kien SONG HANH, thieu mot la vo dung:
          * pha BAT (capture=true) - pha noi bot bi stopPropagation cua nut chan mat;
          * gioi han trong `#ec-apl-root .fgrid` - `ec-cb` la asset dung chung toan site,
            nghe o tang document la doi hanh vi cua nhung trang khac ma khong ai ngo."""
        i = self.h.index("function dongOLocKhac")
        than = self.h[i:i + 900]
        self.assertIn("#ec-apl-root .fgrid", than)
        self.assertIn("}, true)", than.replace(" ", "").replace("\n", "")
                      .replace("},true)", "}, true)"))

    def test_boot_CO_goi_dongOLocKhac(self):
        """Viet ham ma khong noi vao boot thi la code chet."""
        i = self.h.index("function boot()")
        self.assertIn("dongOLocKhac();", self.h[i:i + 1200])

    def test_KHONG_sua_bundle_dung_chung(self):
        """Ban va phai nam TRONG trang nay. Neu ai do chuyen sang sua `ec_formkit.bundle.js`
        thi 27 form + cac trang legacy dung chung deu doi hanh vi.

        Kiem CHINH FILE bundle, khong kiem chuoi trong trang hub. Ban dau viet
        `assertNotIn("ec_formkit.bundle", self.h)` - va no do vi chinh CAU CHU THICH trong
        trang giai thich goc loi da nhac ten file do. Lan thu ba trong ngay mot phep do bi
        chinh chu thich cua minh lam do; nen quet vao THU CAN KIEM, dung quet quanh no.
        """
        p = os.path.join(_APP, "public", "js", "ec_formkit.bundle.js")
        if not os.path.exists(p):
            self.skipTest("khong thay ec_formkit.bundle.js")
        src = _read("public", "js", "ec_formkit.bundle.js")
        self.assertNotIn("dongOLocKhac", src,
                         "ban va phai nam trong trang hub, KHONG duoc do vao bundle dung chung")
        self.assertNotIn("ec-apl-root", src,
                         "bundle dung chung khong duoc biet gi ve trang hub")

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
        """Ba buoc sua HTML: ma bam khop FILE, patch duoc tro toi CO THAT, va da khai trong
        patches.txt.

        KHONG bat cung TEN patch. Ban dau chot "p173_resync_cancelled_badge_and_hub_filters",
        nen dot sau (p174) lam test do trong khi khong co gi sai - buoc moi dot sua trang nay
        deu phai sua test. Dieu can giu la ba buoc DAY DU, khong phai mot cai ten.
        """
        import hashlib
        import json
        man = json.loads(_read("approval_center", "patches", "resync_manifest.json"))
        khai = _read("patches.txt")
        for khoa, duong in (("approval_center/features/payment_request/ui/main_section.html", _PR_UI),
                            ("approval_center/ui/all_requests/main_section.html", _HUB_UI)):
            raw = io.open(os.path.join(_APP, *duong), "rb").read().replace(b"\r\n", b"\n")
            self.assertEqual(man[khoa]["sha256"], hashlib.sha256(raw).hexdigest(),
                             khoa + ": ma bam khong khop FILE")
            patch = man[khoa].get("last_resync_patch") or ""
            self.assertTrue(patch, khoa + ": thieu last_resync_patch")
            self.assertTrue(
                os.path.exists(os.path.join(_APP, "approval_center", "patches", patch + ".py")),
                khoa + ": ban ke tro toi patch KHONG TON TAI: " + patch)
            self.assertIn(patch, khai, khoa + ": patch chua khai trong patches.txt: " + patch)


if __name__ == "__main__":
    unittest.main()
