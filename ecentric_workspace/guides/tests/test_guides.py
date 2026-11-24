# Copyright (c) 2026, eCentric and contributors
"""Hop dong cua module huong dan.

Cai bo test nay canh, noi cho gon: MOT bai huong dan duoc khai o registry phai
that su den duoc tay nguoi dung - co trang, co route dung, co anh, co duong ve.
Moi muc duoi day tuong ung mot kieu hong DA hoac SAP xay ra:

  * registry khai mot bai nhung khong ai lam trang -> the o Approval Center bam
    vao ra 404. Khong test thi khong ai biet cho toi luc nguoi dung bam.
  * route o registry va ROUTE o page_sync lech nhau mot dau gach -> y het tren.
  * bai tham chieu mot anh khong co trong repo -> trang len song voi o anh vo.
  * bai khong co duong ve -> dung y Hoan 08/09: "gan len thi nho co nut back ve
    nhe, chu khong no bi bo vo do".

Chay doc lap (khong can frappe): page_sync.py co `import frappe` nen o day KHONG
import no - doc bang AST. Doi lai, test chay duoc o may nao cung duoc.
"""
import ast
import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GUIDES = os.path.dirname(HERE)                       # .../ecentric_workspace/guides
APP = os.path.dirname(GUIDES)                        # .../ecentric_workspace
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

from ecentric_workspace.guides import page_sync_util  # noqa: E402
from ecentric_workspace.guides import registry        # noqa: E402

PAGES_DIR = os.path.join(GUIDES, "pages")


def _page_dir_of(slug):
    """Thu muc trang cua mot slug: dau gach ngang -> gach duoi (quy uoc goi Python)."""
    return os.path.join(PAGES_DIR, slug.replace("-", "_"))


def _module_const(path, name):
    """Doc mot hang so cap module bang AST - khong import (page_sync can frappe)."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return node.value.value
    return None


class TestRegistry(unittest.TestCase):
    def test_co_it_nhat_mot_bai(self):
        self.assertTrue(registry.GUIDES, "registry rong - phep kiem duoi dang mu")

    def test_moi_bai_khai_du_truong(self):
        for slug, g in registry.GUIDES.items():
            with self.subTest(slug=slug):
                for f in ("title", "short", "summary", "updated"):
                    self.assertTrue(g.get(f), "bai %s thieu truong %s" % (slug, f))
                # approval_types BAT BUOC khai (de khong ai quen), nhung duoc rong: bai
                # khong gan voi form nao (vd chot cong thang) thi khong co icon "?".
                self.assertIn("approval_types", g, "bai %s thieu truong approval_types" % slug)
                self.assertIsInstance(g["approval_types"], list)

    def test_route_suy_ra_tu_slug(self):
        self.assertEqual(registry.route_of("abc"), "/huong-dan/abc")

    def test_tra_bai_theo_loai_yeu_cau(self):
        for code in ("PURCHASE_REQUEST", "PAYMENT_REQUEST"):
            with self.subTest(code=code):
                g = registry.guide_for_approval_type(code)
                self.assertIsNotNone(g, "%s phai co bai huong dan" % code)
                self.assertEqual(g["route"], "/huong-dan/dnmh-dntt")

    def test_loai_khong_co_bai_tra_None(self):
        self.assertIsNone(registry.guide_for_approval_type("LEAVE"))
        self.assertIsNone(registry.guide_for_approval_type(None))
        self.assertIsNone(registry.guide_for_approval_type(""))

    def test_khong_hai_bai_cung_gianh_mot_loai_yeu_cau(self):
        """Hai bai cung khai PAYMENT_REQUEST thi icon "?" tro toi bai nao la do
        thu tu dict - tuc la do may rui. Chan tu day."""
        seen = {}
        for slug, g in registry.GUIDES.items():
            for code in g.get("approval_types", ()):
                self.assertNotIn(code, seen,
                                 "%s duoc ca %s va %s nhan" % (code, seen.get(code), slug))
                seen[code] = slug


class TestMoiBaiDeuCoTrangThAT(unittest.TestCase):
    def test_co_thu_muc_va_hai_tep(self):
        for slug in registry.GUIDES:
            with self.subTest(slug=slug):
                d = _page_dir_of(slug)
                self.assertTrue(os.path.isdir(d), "thieu thu muc trang cho bai %s: %s" % (slug, d))
                for f in ("page_sync.py", "main_section.html"):
                    self.assertTrue(os.path.isfile(os.path.join(d, f)),
                                    "bai %s thieu %s" % (slug, f))

    def test_route_cua_trang_khop_registry(self):
        for slug in registry.GUIDES:
            with self.subTest(slug=slug):
                route = _module_const(os.path.join(_page_dir_of(slug), "page_sync.py"), "ROUTE")
                self.assertEqual("/" + (route or ""), registry.route_of(slug),
                                 "ROUTE o page_sync lech voi registry -> the bam ra 404")

    def test_trang_muc_luc_dung_route_goc(self):
        route = _module_const(os.path.join(PAGES_DIR, "index", "page_sync.py"), "ROUTE")
        self.assertEqual("/" + (route or ""), registry.ROUTE_PREFIX)

    def test_page_sync_ghi_ro_ten_template(self):
        """Ban ke ma bam (test_html_change_needs_resync) doc AST cua page_sync de
        tim template. Khong co chuoi ".html" o do thi trang huong dan nam ngoai
        tam kiem - sua HTML ma khong ai doi hoi patch resync."""
        for d in [os.path.join(PAGES_DIR, "index")] + \
                 [_page_dir_of(s) for s in registry.GUIDES]:
            with self.subTest(page=os.path.basename(d)):
                src = io.open(os.path.join(d, "page_sync.py"), encoding="utf-8").read()
                self.assertIn('"main_section.html"', src)


class TestNoiDungTrang(unittest.TestCase):
    def _html(self, d):
        return io.open(os.path.join(d, "main_section.html"), encoding="utf-8").read()

    def test_moi_anh_tham_chieu_deu_co_tep(self):
        for slug in registry.GUIDES:
            d = _page_dir_of(slug)
            html = self._html(d)
            names = re.findall(r"\{\{img:([^}]+)\}\}", html)
            with self.subTest(slug=slug):
                # 23/11/2026: bai phai co HINH MINH HOA - anh chup man hinh HOAC so do luong
                # (mermaid, class ecg-flow). Bai quy trinh nhan su viet truoc khi form len nen
                # chua co anh chup; so do la thu thay the, khong phai trang chu chay.
                self.assertTrue(names or 'class="ecg-flow"' in html,
                                "bai %s khong co anh hay so do nao - co dung y khong?" % slug)
                for n in names:
                    self.assertTrue(os.path.isfile(os.path.join(d, "img", n.strip())),
                                    "bai %s thieu anh %s" % (slug, n))

    def test_thieu_anh_thi_NEM_LOI_chu_khong_de_o_vo(self):
        with self.assertRaises(ValueError):
            page_sync_util.embed_images("{{img:khong-co-that.jpg}}", os.path.join(GUIDES, "pages"))

    def test_duoi_anh_la_khong_ho_tro_cung_nem_loi(self):
        with self.assertRaises(ValueError):
            page_sync_util.embed_images("{{img:x.bmp}}", os.path.join(GUIDES, "pages"))

    def test_moi_bai_co_duong_ve(self):
        """Y Hoan 08/09: bai huong dan khong duoc "bo vo"."""
        for slug in registry.GUIDES:
            with self.subTest(slug=slug):
                html = self._html(_page_dir_of(slug))
                self.assertIn('href="%s"' % registry.ROUTE_PREFIX, html,
                              "bai %s khong co duong ve muc luc" % slug)

    def test_muc_luc_liet_ke_du_moi_bai(self):
        listed = page_sync_util.render_guides_list()
        for slug, g in registry.GUIDES.items():
            with self.subTest(slug=slug):
                self.assertIn('href="%s"' % registry.route_of(slug), listed)
                self.assertIn(g["title"], listed)

    def test_muc_luc_rong_thi_noi_that(self):
        real = registry.GUIDES
        try:
            registry.GUIDES = {}
            self.assertIn("Chưa có hướng dẫn nào", page_sync_util.render_guides_list())
        finally:
            registry.GUIDES = real

    def test_dung_duoc_ca_trang_muc_luc(self):
        """build() that su chay: thay {{guides_list}} va nhung anh (base64)."""
        html = page_sync_util.build(os.path.join(PAGES_DIR, "index"), "main_section.html")
        self.assertNotIn("{{guides_list}}", html)
        self.assertIn('class="gcards"', html)

    def test_dung_duoc_moi_bai_va_anh_thanh_data_uri(self):
        for slug in registry.GUIDES:
            with self.subTest(slug=slug):
                html = page_sync_util.build(_page_dir_of(slug), "main_section.html")
                self.assertNotIn("{{img:", html)
                if "{{img:" in self._html(_page_dir_of(slug)):
                    self.assertIn("data:image/", html)

    def test_muc_luc_chia_nhom_khi_co_nhieu_nhom(self):
        listed = page_sync_util.render_guides_list()
        self.assertIn('<h2 class="ggroup">%s</h2>' % registry.GROUP_DEFAULT, listed)
        self.assertIn('<h2 class="ggroup">%s</h2>' % registry.GROUP_HR, listed)
        # bai chung truoc, nhom nhan su sau; trong nhom theo "order" (tong quan dau tien)
        self.assertLess(listed.index("/huong-dan/dnmh-dntt"), listed.index(registry.GROUP_HR))
        self.assertLess(listed.index('href="/huong-dan/nhan-su"'), listed.index('href="/huong-dan/ky-luat"'))

    def test_mot_nhom_thi_khong_ve_tieu_de_nhom(self):
        real = registry.GUIDES
        try:
            registry.GUIDES = {k: v for k, v in real.items() if not v.get("group")}
            listed = page_sync_util.render_guides_list()
            self.assertNotIn("ggroup", listed)
            self.assertTrue(listed.startswith('<div class="gcards">'))
        finally:
            registry.GUIDES = real


class TestQuyTrinhNhanSu(unittest.TestCase):
    """8 bai quy trinh nhan su (23/11/2026): dung SLA brief, loi vao form, menu khu Nhan su."""

    SLUGS = ("nhan-su", "gan-phieu-duyet", "phe-duyet-dot-xuat", "offer-new-staff",
             "nghi-viec-clearance", "danh-gia-nhan-su", "khao-sat-nhan-su", "ky-luat")

    def _html(self, slug):
        return io.open(os.path.join(_page_dir_of(slug), "main_section.html"), encoding="utf-8").read()

    def test_du_8_bai_trong_nhom_nhan_su(self):
        for slug in self.SLUGS:
            with self.subTest(slug=slug):
                self.assertIn(slug, registry.GUIDES)
                self.assertEqual(registry.GUIDES[slug].get("group"), registry.GROUP_HR)

    def test_form_da_co_tro_ve_bai_dung(self):
        for code, slug in (("OFFER_REQUEST", "offer-new-staff"),
                           ("NEW_STAFF_PREPARATION", "offer-new-staff"),
                           ("RESIGNATION", "nghi-viec-clearance"),
                           ("CLEARANCE_REQUEST", "nghi-viec-clearance")):
            with self.subTest(code=code):
                self.assertEqual(registry.guide_for_approval_type(code)["route"], registry.route_of(slug))

    def test_sla_dung_brief(self):
        """SLA Hoan chot 22-23/11 - doi brief thi sua ca bai lan test, khong de lech im lang."""
        expect = {
            "phe-duyet-dot-xuat": ["Bình thường: 2 ngày làm việc", "Gấp: 4 giờ làm việc"],
            "offer-new-staff": ["1 ngày làm việc", "Trước ngày onboard 1 ngày làm việc",
                                "tối thiểu 2 ngày làm việc"],
            "nghi-viec-clearance": ["2 ngày làm việc", "Ngày làm việc cuối", "45 ngày", "30 ngày",
                                    "3 ngày làm việc", "Không cần báo trước"],
            "danh-gia-nhan-su": ["21 ngày trước", "37 ngày trước", "14 ngày trước", "30 ngày trước",
                                 "Thử việc, thực tập: 2 ngày làm việc", "Hợp đồng: 3 ngày làm việc",
                                 "Thử việc, thực tập: 3 ngày làm việc", "Hợp đồng: 5 ngày làm việc"],
            "khao-sat-nhan-su": ["Ngày 7 · ngày 30 · ngày 45", "Ngày 30 · ngày 60 · ngày 75",
                                 "3 ngày làm việc", "chỉ HR"],
            "ky-luat": ["Thẩm định trong 3 ngày làm việc", "Họp sớm nhất sau 5 ngày làm việc",
                        "2 ngày làm việc sau họp", "14 ngày", "Sau 3 tháng", "NĐ 145/2020"],
        }
        for slug, needles in expect.items():
            html = self._html(slug)
            for n in needles:
                with self.subTest(slug=slug, needle=n):
                    self.assertIn(n, html)

    def test_nghi_viec_khong_co_tu_choi(self):
        html = self._html("nghi-viec-clearance")
        self.assertIn("không có nút “Từ chối”", html)
        self.assertNotIn("Duyệt / Từ chối", html)

    def test_ky_luat_khong_co_tien_phat(self):
        self.assertIn("Không có ô tiền phạt", self._html("ky-luat"))

    def test_link_form_tro_dung_route_that(self):
        """Tich hop 23/11: link sang form la route THAT (khong con nhan "sắp mở")."""
        for slug, route in (("phe-duyet-dot-xuat", "/approvals/adhoc-approval"),
                            ("danh-gia-nhan-su", "/approvals/employee-review"),
                            ("danh-gia-nhan-su", "/ec-hr/danh-gia-nhan-su"),
                            ("khao-sat-nhan-su", "/khao-sat/ca-nhan"),
                            ("ky-luat", "/ky-luat")):
            with self.subTest(slug=slug, route=route):
                html = self._html(slug)
                self.assertIn('href="%s"' % route, html)
                self.assertNotIn("data-route-planned", html)
                self.assertNotIn("sắp mở", html)

    def test_menu_khu_nhan_su_tro_toi_tong_quan_KHONG_them_tung_bai(self):
        """24/11: 7 bai moi KHONG len menu (giong 8 bai 23/11) - loi vao la muc luc, trang tong quan
        va icon "?" o Approval Center. Menu khu Nhan su van chi co mot lien ket huong dan."""
        from ecentric_workspace.shell import nav as shell_nav
        links = [it for b in shell_nav.RAIL_LAYOUTS["hr"] for it in b.get("items") or []]
        guide_links = [it for it in links if str(it.get("route") or "").startswith(registry.ROUTE_PREFIX)]
        self.assertEqual([it["route"] for it in guide_links], [registry.route_of("nhan-su")])

    def test_menu_khu_nhan_su_tro_toi_tong_quan(self):
        from ecentric_workspace.shell import nav as shell_nav
        links = [it for b in shell_nav.RAIL_LAYOUTS["hr"] for it in b.get("items") or []]
        hit = [it for it in links if it.get("route") == registry.route_of("nhan-su")]
        self.assertEqual(len(hit), 1, "khu Nhan su phai co dung 1 loi vao huong dan quy trinh nhan su")


class TestBoHuongDanNhanSuDayDu(unittest.TestCase):
    """24/11/2026 (Hoan: "ok xu li di"): bai Tuyen dung A-Z + 6 bai ngan + cap nhat theo thay doi 24/11."""

    NEW = ("tuyen-dung", "thang-chuc-dieu-chinh-luong", "dieu-chuyen-noi-bo", "cap-nhat-thong-tin-nhan-su",
           "gioi-thieu-ung-vien", "hoat-dong-nhan-su", "phan-bo-ty-trong-brand")
    #: 13 loai phieu nhom "Nhan su" tren Approval Center: 11 loai p523 doi nhom + 2 loai seed san o HR.
    HR_CODES = ("HIRING_REQUEST", "OFFER_REQUEST", "NEW_STAFF_PREPARATION", "EMPLOYEE_INFO_UPDATE",
                "PROMOTION_REQUEST", "LATERAL_MOVE", "EMPLOYEE_REVIEW", "DISCIPLINE_DECISION", "RESIGNATION",
                "CLEARANCE_REQUEST", "EMPLOYEE_REFERRAL", "HR_ACTIVITY", "BRAND_WEIGHT")

    def _html(self, slug):
        return io.open(os.path.join(_page_dir_of(slug), "main_section.html"), encoding="utf-8").read()

    def test_danh_sach_13_loai_khop_nguon(self):
        """Doi chieu voi NGUON (p523 + seed), khong tin danh sach go tay o test."""
        import json
        p523 = io.open(os.path.join(APP, "approval_center", "patches", "p523_nhom_nhan_su_approval_center.py"),
                       encoding="utf-8").read()
        doi = set(re.findall(r'^    "([A-Z_]+)": "(?:ADMINISTRATION|OTHERS)",$', p523, re.M))
        seed = json.load(io.open(os.path.join(APP, "approval_center", "seed", "approval_types_seed.json"),
                                 encoding="utf-8"))
        hr_seed = {t["approval_code"] for t in seed if t.get("category") == "HR"}
        self.assertEqual(len(doi), 11)
        self.assertEqual(doi | hr_seed, set(self.HR_CODES))

    def test_moi_loai_nhom_nhan_su_deu_co_icon_huong_dan(self):
        for code in self.HR_CODES:
            with self.subTest(code=code):
                g = registry.guide_for_approval_type(code)
                self.assertIsNotNone(g, "%s khong co bai -> the Approval Center khong co icon ?" % code)
                self.assertEqual(g["group"], registry.GROUP_HR)

    def test_bai_moi_gan_dung_loai(self):
        for code, slug in (("HIRING_REQUEST", "tuyen-dung"), ("PROMOTION_REQUEST", "thang-chuc-dieu-chinh-luong"),
                           ("LATERAL_MOVE", "dieu-chuyen-noi-bo"), ("EMPLOYEE_INFO_UPDATE", "cap-nhat-thong-tin-nhan-su"),
                           ("EMPLOYEE_REFERRAL", "gioi-thieu-ung-vien"), ("HR_ACTIVITY", "hoat-dong-nhan-su"),
                           ("BRAND_WEIGHT", "phan-bo-ty-trong-brand")):
            with self.subTest(code=code):
                self.assertEqual(registry.guide_for_approval_type(code)["route"], registry.route_of(slug))

    def test_link_form_trong_bai_moi_la_route_cua_chinh_feature(self):
        """Route lay tu page_sync / activation cua feature - doi route o feature ma quen bai thi do."""
        def route(feature, fname="page_sync.py"):
            src = io.open(os.path.join(APP, "approval_center", "features", feature, "infrastructure", fname),
                          encoding="utf-8").read()
            return "/" + re.search(r'^ROUTE = "/?([^"]+)"', src, re.M).group(1)
        for slug, feature in (("tuyen-dung", "hiring_request"), ("tuyen-dung", "offer_request"),
                              ("tuyen-dung", "new_staff_preparation"), ("thang-chuc-dieu-chinh-luong", "promotion"),
                              ("dieu-chuyen-noi-bo", "lateral_move"),
                              ("cap-nhat-thong-tin-nhan-su", "employee_info_update"),
                              ("gioi-thieu-ung-vien", "employee_referral"), ("hoat-dong-nhan-su", "hr_activity"),
                              ("phan-bo-ty-trong-brand", "brand_weight")):
            with self.subTest(slug=slug, feature=feature):
                self.assertIn('class="ecg-link" href="%s"' % route(feature), self._html(slug))

    def test_moi_link_noi_bo_tro_route_co_that(self):
        """Moi href="/..." trong phan bai (khong tinh vo shell) phai la route khai trong code:
        ROUTE cua page_sync / activation, website_route_rules, hoac trang chu "/"."""
        routes = {"/"}
        for dirpath, dirs, files in os.walk(APP):
            dirs[:] = [d for d in dirs if d not in ("tests", "node_modules", "__pycache__", "public")]
            for f in files:
                if not f.endswith(".py"):
                    continue
                src = io.open(os.path.join(dirpath, f), encoding="utf-8", errors="ignore").read()
                routes.update("/" + m.strip("/") for m in re.findall(r'^\s*ROUTE(?:_[A-Z]+)? = "/?([^"?]+)"', src, re.M))
                routes.update(m.rstrip("/") for m in re.findall(r'"from_route": "([^"]+)"', src))
        for slug in registry.GUIDES:
            html = self._html(slug)
            body = html[html.find("<article"):]
            for href in re.findall(r'href="(/[^"]*)"', body):
                with self.subTest(slug=slug, href=href):
                    self.assertIn(re.split(r"[?#]", href)[0].rstrip("/") or "/", routes)

    def test_tuyen_dung_du_6_buoc_va_moc_gio(self):
        html = self._html("tuyen-dung")
        for n in ("Bước 1 — Đề xuất tuyển dụng", "Bước 2 — HR tuyển dụng nhận việc", "Bước 3 — Offer ứng viên",
                  "Bước 4 — Chuẩn bị nhân sự mới", "Bước 5 — Ngày onboard", "Bước 6 — Thử việc",
                  "Trước ngày onboard 1 ngày làm việc", "tối thiểu 2 ngày làm việc", "Từ 08:30 ngày onboard",
                  "10:00 ngày onboard", "eCentric Team", "Sửa lời giới thiệu / ngày onboard", "role EC Recruiter",
                  "60 ngày", "Điều 25", "Nhận tuyển dụng", "Tạo Offer", "Hoàn tất tuyển dụng"):
            with self.subTest(needle=n):
                self.assertIn(n, html)
        self.assertNotIn("luc.nguyen", html)

    def test_moc_gio_khop_code(self):
        """08:30 / 10:00 / 60 ngay / 00:30 / 00:45 la so trong code - doi code ma quen bai thi do."""
        welcome = io.open(os.path.join(APP, "approval_center", "features", "new_staff_preparation", "application",
                                       "welcome.py"), encoding="utf-8").read()
        self.assertIn("POPUP_FROM = datetime.time(8, 30)", welcome)
        hooks = io.open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        self.assertIn('setdefault("*/15 10 * * *", []).append(\n    "ecentric_workspace.approval_center.features.'
                      'new_staff_preparation.application.welcome.send_welcome_teams")', hooks)
        self.assertIn('setdefault("30 0 * * *", []).append(\n    "ecentric_workspace.hr.offboarding.'
                      'lock_left_employees_job.run")', hooks)
        self.assertIn('setdefault("45 0 * * *", []).append(\n    "ecentric_workspace.approval_center.shared.'
                      'workflow.approver_handover.sweep")', hooks)
        ec = io.open(os.path.join(APP, "approval_center", "features", "new_staff_preparation", "infrastructure",
                                  "employee_contract.py"), encoding="utf-8").read()
        self.assertIn("THU_VIEC_MAC_DINH_NGAY = 60", ec)

    def test_cap_nhat_24_11(self):
        expect = {
            "nhan-su": ["Mới từ 24/11", "Tiến trình A–Z", "Việc của bạn", "Yêu cầu bổ sung", "Còn thiếu N mục",
                        "00:45"],
            "offer-new-staff": ["/huong-dan/tuyen-dung", "Từ 08:30 ngày onboard", "10:00 ngày onboard",
                                "Sửa lời giới thiệu / ngày onboard", "role EC CnB hoặc HR"],
            "nghi-viec-clearance": ["00:30 sáng sau ngày cuối", "Left", "Dữ liệu giữ nguyên", "role) giữ nguyên",
                                    "00:45 sáng sau ngày cuối", "Microsoft 365", "IT khoá riêng"],
            "danh-gia-nhan-su": ["/huong-dan/tuyen-dung", "60 ngày", "Việc của bạn"],
            "ky-luat": ["Quyết định <b>sa thải</b>", "Clearance", "00:30", "00:45"],
        }
        for slug, needles in expect.items():
            html = self._html(slug)
            self.assertIn("Cập nhật 24/11/2026", html)
            for n in needles:
                with self.subTest(slug=slug, needle=n):
                    self.assertIn(n, html)

    def test_tong_quan_liet_ke_moi_bai_nhan_su(self):
        html = self._html("nhan-su")
        for slug, g in registry.GUIDES.items():
            if g.get("group") == registry.GROUP_HR and slug != "nhan-su":
                with self.subTest(slug=slug):
                    self.assertIn('class="gcard" href="%s"' % registry.route_of(slug), html)

    def test_brand_weight_khong_noi_bang_viec_cua_ban(self):
        """Trang /ec-hr/phan-bo-cong-viec khong dung ec_approval_ui -> bai khong duoc ha hen bang do."""
        self.assertNotIn("Việc của bạn", self._html("phan-bo-ty-trong-brand"))

    def test_khong_ten_nguoi_trong_bai_moi(self):
        for slug in self.NEW:
            with self.subTest(slug=slug):
                self.assertIsNone(re.search(r"[a-z]+\.[a-z]+[0-9]*@|ecentric\.vn", self._html(slug)))


if __name__ == "__main__":
    unittest.main()
