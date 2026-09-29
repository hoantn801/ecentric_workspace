"""Ba trang /ec-hr/attendance, /ec-hr/leave, /ec-hr/salary khong duoc "nhieu lop" tro lai.

NHIEU_LOP/brief_hr.md (28/09): trang ve HTML server roi JS moi an / di chuyen / ve de len
(the cham cong lech 968px, dai so du nghi phep lech 903px), 13 khoi <script|style id> chen
dan vao trang cham cong, va trang nghi phep goi ec_hr_today_state 3 lan moi lan mo.
Nguon cua ba trang la fixtures/web_page.json (migrate dong bo tu file nay).

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_hr_pages_layers
"""
import hashlib
import json
import os
import re
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROUTES = ("ec-hr/attendance", "ec-hr/leave", "ec-hr/salary")
JS = os.path.join(APP, "public", "js", "ec_hr_pages.js")
CSS = os.path.join(APP, "public", "css", "ec_hr_pages.css")


def _pages():
    with open(os.path.join(APP, "fixtures", "web_page.json"), encoding="utf-8") as fh:
        rows = json.load(fh)
    return {r["route"]: r["main_section_html"] for r in rows if r["route"] in ROUTES}


def _v(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:10]


class TestKhongNhieuLop(unittest.TestCase):
    def setUp(self):
        self.pages = _pages()
        self.assertEqual(sorted(self.pages), sorted(ROUTES))

    def test_khong_con_khoi_chen_co_ten(self):
        # Moi trang: MOT <style> + MOT <script> cua chinh no. Ngoai le duy nhat la chot bao ve
        # phieu luong (khong cho trinh duyet prerender /ec-hr/salary).
        for route, h in self.pages.items():
            ids = re.findall(r'<(?:script|style)[^>]*\bid="([^"]+)"', h)
            allowed = ["ec-salary-noprerender"] if route == "ec-hr/salary" else []
            self.assertEqual(ids, allowed, route)

    def test_asset_chung_dung_phien_ban(self):
        # ?v= phai la ma bam that cua file: sua asset ma quen doi thi trinh duyet giu ban cu.
        for route, h in self.pages.items():
            self.assertIn('/assets/ecentric_workspace/js/ec_hr_pages.js?v=%s"' % _v(JS), h, route)
            self.assertIn('/assets/ecentric_workspace/css/ec_hr_pages.css?v=%s"' % _v(CSS), h, route)

    def test_bo_cuc_nam_san_trong_markup(self):
        for route in ("ec-hr/attendance", "ec-hr/leave"):
            h = self.pages[route]
            self.assertNotIn("ec-hr-desk-v1", h, route)
            self.assertNotIn("insertBefore(colMain", h, route)
            self.assertIn('<div class="ec-col ec-col-side">', h, route)
            self.assertIn('<div class="ec-col ec-col-main">', h, route)
        att = self.pages["ec-hr/attendance"]
        # cot phai (the cham cong) dung TRUOC cot trai -> dien thoai giu dung thu tu cu
        self.assertLess(att.index('<div class="ec-col ec-col-side">'), att.index('<div class="ec-col ec-col-main">'))
        self.assertIn('id="ha-ci-btn" style="display:none"', att)
        self.assertIn('id="ec-att-teambar-slot"', att)

    def test_cham_cong_giu_cho_theo_du_lieu(self):
        # Do live 28/09 luc CHUA check-in: nut Cham cong hien -> the hero cao them 52px, day dong
        # thoi gian xuong; JS an 2 dong r2/r3 -> mat chu "Ra ca". Ca hai trang thai phai cung khung.
        att = self.pages["ec-hr/attendance"]
        self.assertIn("#ha-ci-card .ha-hero-main{min-height:", att)
        self.assertNotRegex(att, r"ha-tl-r[23]'\)\.style\.display")
        self.assertNotIn("tlLn.style.display", att)
        # "—" cho (skeleton) va chu that phai cao bang nhau, neu khong dong "Ra ca" lech 13px
        self.assertIn("#ha-tl .ha-tl-t{line-height:20px}", att)
        self.assertIn("#ha-tl .ha-tl-s:empty{min-height:17px}", att)

    def test_today_state_chi_goi_mot_lan(self):
        for route, h in self.pages.items():
            self.assertNotIn("ec_hr_today_state", h, route)
        with open(JS, encoding="utf-8") as fh:
            js = fh.read()
        self.assertEqual(js.count("/api/method/ec_hr_today_state"), 1)
        self.assertIn("if (asked ||", js)

    def test_khong_boc_fetch(self):
        with open(JS, encoding="utf-8") as fh:
            js = fh.read()
        for src in list(self.pages.values()) + [js]:
            self.assertNotRegex(src, r"window\.fetch\s*=")


class TestAttendanceDatabaseNghi(unittest.TestCase):
    def test_chuyen_huong_sang_trang_moi(self):
        # 29/09: /attendance-database (ban cu, khong menu, boc window.fetch) cho nghi.
        import ast
        with open(os.path.join(APP, "hooks.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        rules = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "website_redirects" for t in node.targets):
                for d in ast.walk(node.value):
                    if isinstance(d, ast.Dict):
                        rules.append(ast.literal_eval(d))
        self.assertIn({"source": "/attendance-database", "target": "/ec-hr/attendance",
                       "redirect_http_status": 302}, rules)

if __name__ == "__main__":
    unittest.main()
