# Copyright (c) 2026, eCentric and contributors
"""Breadcrumb cua mot route CO THAT nhung KHONG ve dong menu.

`sidebar_hidden` tra loi cau hoi "co ve dong nay vao thanh ben khong". No KHONG
tra loi "route nay co ton tai khong" - chinh chu thich o shell/nav.py compose()
noi vay. Nhung `_crumb_target` truoc 08/09 hoi registry bang compose() mac dinh,
tuc la bo qua muc an: hai trang co route hop le (/viec-cua-toi va muc luc huong
dan /huong-dan) rot ra khoi ban do va o breadcrumb thanh TRONG - dung cai cam
giac "bo vo" ma breadcrumb sinh ra de tranh.

Bo test nay giu dung mot dieu: trang nao co trong ban do route thi cung phai co
breadcrumb, ke ca khi muc cua no bi an khoi thanh ben.
"""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))          # .../ecentric_workspace
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

from ecentric_workspace.shell import fallback as fb   # noqa: E402
from ecentric_workspace.shell import nav as shell_nav  # noqa: E402


def _hidden_routes():
    """Route cua MOI muc sidebar_hidden trong moi ngu canh (khong liet ke tay)."""
    out = set()
    for ctx in shell_nav.CONTEXTS:
        for it in shell_nav.compose(ctx, include_hidden=True):
            for c in [it] + list(it.get("children") or []):
                if c.get("sidebar_hidden"):
                    out.add(c["route"])
    return sorted(out)


class TestMucAnVanCoBreadcrumb(unittest.TestCase):
    def test_co_it_nhat_mot_muc_an(self):
        self.assertTrue(_hidden_routes(), "khong con muc sidebar_hidden nao - test dang mu")

    def test_moi_route_an_deu_ra_breadcrumb(self):
        for route in _hidden_routes():
            with self.subTest(route=route):
                self.assertNotEqual(fb.crumbs_inner(route).strip(), "",
                                    "route %s khong ra breadcrumb -> trang bo vo" % route)

    def test_khong_ve_dong_menu_cho_muc_an(self):
        """Nua con lai cua hop dong: an VAN LA an - breadcrumb khong keo no ve lai
        thanh ben. Neu mat khang dinh nay thi ban sua o tren da di qua xa."""
        for route in _hidden_routes():
            with self.subTest(route=route):
                side = fb.render_mount_inner(route)
                self.assertNotIn('class="ec-shell-item" href="%s"' % route, side)


class TestBaiHuongDanQuyVeMucLuc(unittest.TestCase):
    """Bai huong dan khong co dong menu rieng; breadcrumb cua no phai co mot LINK
    ve muc luc - do la duong ve duy nhat o phan vo trang."""

    ROUTE = "/huong-dan/dnmh-dntt"

    def test_crumb_cua_bai_co_link_ve_muc_luc(self):
        html = fb.crumbs_inner(self.ROUTE, detail_html="<strong>x</strong>")
        self.assertIn('href="/huong-dan"', html)

    def test_muc_luc_la_muc_HIEN_TAI_khi_dang_o_muc_luc(self):
        html = fb.crumbs_inner("/huong-dan")
        self.assertIn("ec-shell-crumb-current", html)
        self.assertNotIn('<a class="ec-shell-crumblink" href="/huong-dan"', html)

    def test_trang_bai_that_su_mang_crumb_do(self):
        path = os.path.join(APP, "guides", "pages", "dnmh_dntt", "main_section.html")
        html = io.open(path, encoding="utf-8").read()
        m = fb.CRUMBS_RE.search(html)
        self.assertIsNotNone(m, "trang bai huong dan khong co vung breadcrumb")
        self.assertIn('href="/huong-dan"', m.group(2))


if __name__ == "__main__":
    unittest.main()
