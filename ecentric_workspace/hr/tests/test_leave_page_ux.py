# Copyright (c) 2026, eCentric and contributors
"""UX trang /ec-hr/leave (03/11/2026) - giu cac moc tren nguon fixture (CA main_section lan
main_section_html). Hanh vi da chay thu bang Chromium voi API gia, chup truoc/sau o 390px va 1366px.

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_leave_page_ux
"""
import io
import json
import os
import re
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIELDS = ("main_section", "main_section_html")


def _page():
    with io.open(os.path.join(APP, "fixtures", "web_page.json"), encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r.get("route") == "ec-hr/leave"][0]


class LeaveOverlayVars(unittest.TestCase):
    """Form xin nghi, toast va popup chi tiet nam NGOAI #ec-hr-lv-root (markup dong root som) ->
    var(--green-b) ... khong xac dinh: toast trong suot, o Ly do mat vien, nut Duyet trong popup
    trong suot. Bien mau phai duoc khai bao cho chinh ba khoi do."""

    def test_bien_mau_cho_khoi_ngoai_root(self):
        for f in FIELDS:
            h = _page()[f]
            m = re.search(r"\.lv-modal-bg,#lv-toast,#ec-lvd-back\{([^}]*)\}", h)
            self.assertTrue(m, f)
            for v in ("--green-b", "--red-b", "--border", "--navy", "--gray-b", "--amber-b"):
                self.assertIn(v + ":", m.group(1), (f, v))
            self.assertIn(".lv-modal-bg *,#ec-lvd-back *{box-sizing:border-box}", h, f)


if __name__ == "__main__":
    unittest.main()
