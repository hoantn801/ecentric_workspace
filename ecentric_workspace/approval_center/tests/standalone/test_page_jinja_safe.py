# Copyright (c) 2026, eCentric and contributors
"""Moi nguon trang (main_section) phai render duoc tren Frappe that.

Su co 11/11/2026 22:00 (form 27 Contract Review): mot dong JS co hai dau ngoac nhon lien nhau
-> Frappe Web Page.render_dynamic coi ca trang la Jinja (kich hoat khi main_section co "{{"
hoac "<!-- jinja -->" hoac dynamic_template) -> render_template tu choi vi trang co ".__"
(vd `el.__ecw`) -> "417 Illegal template", ca trang trang. jsdom khong render Jinja nen test
trang khong bat duoc. Test nay doc dung luat cua frappe/utils/jinja.py + web_page.py v16.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]   # .../ecentric_workspace (app package)
JINJA_TRIGGERS = ("{{", "<!-- jinja -->")


def page_sources():
    for p in sorted(ROOT.rglob("*main_section*.html")):
        if "node_modules" in p.parts or "/tests/" in p.as_posix():
            continue
        yield p


class PageJinjaSafe(unittest.TestCase):
    def test_trang_khong_vo_tinh_thanh_jinja_roi_bi_tu_choi(self):
        bad = []
        for p in page_sources():
            text = p.read_text(encoding="utf-8", errors="replace")
            if any(t in text for t in JINJA_TRIGGERS) and ".__" in text:
                bad.append(str(p.relative_to(ROOT)))
        self.assertEqual(bad, [], "Trang vua co '{{' / '<!-- jinja -->' (Frappe render Jinja) vua co "
                         "'.__' (Jinja tu choi: 417 Illegal template). Bo '{{' khoi JS (vd '{'+'{').")

    def test_form_27_khong_co_hai_ngoac_nhon(self):
        p = ROOT / "approval_center/features/contract_review/ui/main_section.html"
        self.assertNotIn("{{", p.read_text(encoding="utf-8"))

    def test_quet_duoc_trang(self):
        self.assertGreater(len(list(page_sources())), 30)


if __name__ == "__main__":
    unittest.main()
