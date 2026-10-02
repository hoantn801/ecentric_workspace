# Copyright (c) 2026, eCentric and contributors
"""Popup "Hom nay o eCentric" - ec_home_popup.js chay THAT trong jsdom tren trang chu da render.
Thieu jinja2 / node / jsdom -> SKIP kem ly do (skip khong phai xanh).
    NODE_PATH=<thu muc co jsdom> python -m pytest ecentric_workspace/home_today/tests/test_popup_js.py
Khoa: khong co noi dung -> khong goi API; popup noi (fixed, z 1040 < eC Mate 1045), bo cuc trang
khong doi; thu tu o; reaction; "Khong hien lai hom nay" + muc moi hien lai; escape; loi im lang.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(APP))
from ecentric_workspace.shell.tests import test_home_source as H  # noqa: E402

JS = os.path.join(APP, "public", "js", "ec_home_popup.js")
HARNESS = os.path.join(HERE, "popup_harness.js")
PAYLOAD = os.path.join(HERE, "sample_payload.json")
DRAW = os.path.join(APP, "public", "surveys", "ec_survey_draw.js")


class TestPopupInJsdom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import jinja2  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("thieu jinja2")
        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("khong co node")
        if subprocess.run([node, "-e", "require('jsdom')"], capture_output=True, cwd=HERE).returncode:
            raise unittest.SkipTest("khong nap duoc jsdom (NODE_PATH?)")
        files = []
        for has in (True, False):
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as fh:
                fh.write(H.render(H._src(), cel={"level": 1, "badge": "x", "has_content": has}))
                files.append(fh.name)
        try:
            p = subprocess.run([node, HARNESS, files[0], files[1], JS, PAYLOAD, DRAW], capture_output=True,
                               text=True, cwd=HERE, timeout=120)
        finally:
            for f in files:
                os.unlink(f)
        if p.returncode:
            raise AssertionError(p.stdout[-2000:] + p.stderr[-3000:])
        cls.r = json.loads(p.stdout)

    def test_no_content_no_api_call(self):
        self.assertEqual(self.r["off"], {"calls": 0, "pop": False})

    def test_floating_overlay_does_not_touch_layout(self):
        m = self.r["main"]
        self.assertTrue(m["pop"])
        self.assertEqual(m["calls"][0], {"get": "ecentric_workspace.home_today.api.get_today"})
        self.assertTrue(m["parentIsBody"])
        self.assertEqual(m["bodyKidsAdded"], 1)
        self.assertTrue(m["fixed"])
        self.assertEqual(m["z"], "1040", "phai nam DUOI eC Mate (1045)")
        self.assertTrue(m["skeletonSame"])
        self.assertTrue(m["skeletonSameAtEnd"])
        self.assertEqual(m["role"], "dialog/true")
        self.assertTrue(m["focusInDialog"])

    def test_tiles_in_po_order(self):
        m = self.r["main"]
        self.assertEqual(m["tiles"], ["Đêm hội Trung thu eCentric 2026", "Thông báo", "Sinh nhật", "Bạn mới",
                                      "Sự kiện công ty", "Nghỉ lễ sắp tới", "Kỷ niệm gắn bó"])
        self.assertEqual(m["badges"], [None, "3", "2", "1", "Mới", None, "1"])
        self.assertEqual(m["sub"][0], "Sự kiện · 29/09/2026")
        self.assertEqual(m["sub"][2], "2 hôm nay · 3 tuần này")
        self.assertEqual(m["sub"][5], "Tết Dương lịch · còn 94 ngày")
        self.assertEqual(m["textHero"], "Chấm công và xin nghỉ ngay trên điện thoại")
        self.assertEqual(m["date"], "Thứ Ba, 29/09/2026")
        self.assertEqual(m["bdHero"], "Chúc mừng sinh nhật Hà và Khoa!")
        self.assertEqual(m["soon"][0], "01/10QHPhạm Quốc Huy · Operation · Thứ Năm")

    def test_poster_full_picture(self):
        p = self.r["main"]["poster"]
        self.assertEqual(p["img"], "/files/poster-trung-thu.jpg")
        self.assertEqual(p["thumb"], "/files/poster-trung-thu.jpg")
        self.assertTrue(p["heroless"], "poster: anh phu kin, khong co khung chu hero")
        self.assertEqual(p["open"], "_blank", "poster khong co duong dan: bam anh mo anh goc o tab moi")
        self.assertEqual(p["bar"], "Sự kiệnĐêm hội Trung thu eCentric 2026")

    def test_poster_with_link_click_goes_to_link(self):
        """PO 01/10: poster co duong dan thi bam vao hinh di toi cho do, khong mo anh goc."""
        self.assertEqual(self.r["posterLink"], {"href": "/huong-dan/chot-cong-thang", "target": None,
                                                "btn": "Xem hướng dẫn →"})

    def test_news_detail_and_links(self):
        m = self.r["main"]
        self.assertTrue(m["expanded"].startswith("Từ hôm nay mọi người có thể chấm công"))
        self.assertEqual(m["links"], [["/ec-hr/attendance", "Dùng thử ngay", None],
                                      ["/files/cong-tac-phi-2026.pdf", "Xem văn bản", None]])

    def test_reaction_toggle(self):
        m = self.r["main"]
        self.assertEqual(m["heartBefore"], ["false", "5"])
        self.assertEqual(m["heartAfter"][:2], ["true", "6"])
        self.assertTrue(m["heartAfter"][2].startswith("Bạn, Minh Anh"))
        self.assertEqual(m["post"][0], {"post": "ecentric_workspace.home_today.api.toggle_reaction",
                                         "d": {"target": "bd:E1:2026", "kind": "heart"}})

    def test_teams_style_reactions(self):
        """PO 29/09 16:27: chua ai tha thi KHONG hien o; nut mat cuoi o goc mo bang chon 4 icon."""
        m = self.r["main"]
        self.assertEqual(m["chipsBefore"], [["heart:5", "flower:2", "cake:7", "party:1"],
                                            ["heart:3", "cake:4", "party:2"]])
        self.assertEqual(m["pickers"], [4, 4])
        self.assertTrue(m["pickOpen"])
        self.assertEqual(m["afterPick"], ["heart:3", "flower:1", "cake:4", "party:2"])
        self.assertTrue(m["pickClosed"])

    def test_keyboard_and_close(self):
        m = self.r["main"]
        self.assertEqual(m["afterArrow"], "Bạn mới")
        self.assertTrue(m["closedByEsc"])
        self.assertEqual(m["stored"]["d"], "2026-09-29")
        self.assertEqual(len(m["stored"]["k"]), 8)

    def test_auto_rotate_pauses_on_hover(self):
        a = self.r["auto"]
        self.assertEqual(a["now"], "Thông báo")
        self.assertEqual(a["pausedStays"], "Thông báo")
        self.assertTrue(a["closedByBackdrop"])
        self.assertTrue(a["escInMateKeepsOpen"], "Esc khi dang go trong eC Mate khong duoc dong popup")

    def test_keyboard_user_stops_auto_rotate(self):
        self.assertEqual(self.r["focusPause"], {"stays": "Đêm hội Trung thu eCentric 2026", "focusKept": True})

    def test_hide_today_and_new_items(self):
        self.assertEqual(self.r["hidden"], {"same": False, "newItem": True, "otherDay": True, "junk": True})

    def test_reopen_keeps_hide_tick(self):
        """PO 29/09 17:31: da tich "Khong hien lai hom nay" roi bam mo lai -> o tich phai con tich."""
        self.assertEqual(self.r["reopen"], {"checked": True, "clearedAfterUntick": True, "freshUnchecked": True})

    def test_escaping_and_empty_tiles_hidden(self):
        x = self.r["xss"]
        self.assertFalse(x["pwn"])
        self.assertEqual(x["imgs"], 0)
        self.assertTrue(x["escaped"])
        self.assertEqual(x["tiles"], ["Sinh nhật", "Sự kiện công ty"])

    def test_draw_tile_first_with_countdown_and_upcoming(self):
        d = self.r["draw"]
        self.assertTrue(d["pop"], "luot quay dang dem nguoc la muc moi -> mo lai du da tich an hom nay")
        self.assertEqual((d["firstTile"], d["badge"]), ("Quay số may mắn", "● Hôm nay"))
        self.assertEqual((d["chip"], d["mine"]), ("Sắp quay · 10:00", "027"))
        self.assertRegex(d["clock"] or "", r"^\d\d:\d\d$")
        self.assertEqual(d["upcoming"], [["Pantry tháng 10", "✓ Bạn đã có xe", "Còn 2 ngày"],
                                         ["Đào tạo Q3", "Chưa nộp phiếu", "Còn 8 ngày"]])
        self.assertEqual(d["cta"], [["Nộp phiếu", "/khao-sat/lam?s=KS-3"]])
        self.assertEqual(d["stillDraw"], "Quay số may mắn")

    def test_upcoming_gift_box_lists_prizes(self):
        g = self.r["draw"]["gift"]
        self.assertEqual(g["n"], 2)
        self.assertEqual(g["cnt"], "4")
        self.assertTrue(g["noCnt"], "luot quay chua nhap qua thi khong co so dem")
        self.assertEqual(g["items"], ["1Voucher <b>500K</b>×1", "2Trà sữa×3"])
        self.assertFalse(g["raw"], "ten qua phai escape")
        self.assertEqual(g["note"], "Nhận quà ở lễ tân")
        self.assertTrue(g["on1"])
        self.assertEqual(g["swap"], [False, True], "mo hop nay thi dong hop kia")

    def test_draw_results_static_with_empty_number(self):
        x = self.r["draw"]["done"]
        self.assertEqual(x["chip"], "Đã quay xong")
        self.assertEqual(x["nums"], ["012", "083"])
        self.assertEqual(x["res"], ["MATrần Minh Anh", "Không ai giữ số này · quà để lại"])
        self.assertTrue(x["replay"])

    def test_popup_opens_itself_at_t_minus_5(self):
        self.assertEqual(self.r["timer"], {"before": False, "after": True, "slide": "Quay số may mắn", "cta": "Chọn số"})

    def test_api_failure_is_silent(self):
        self.assertEqual(self.r["fail"]["pop"], False)
        self.assertEqual(self.r["fail"]["warns"], 1)


if __name__ == "__main__":
    unittest.main()
