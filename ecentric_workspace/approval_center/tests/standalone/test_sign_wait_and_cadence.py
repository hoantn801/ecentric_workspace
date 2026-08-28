# Copyright (c) 2026, eCentric and contributors
"""After "Duyệt & Ký" the screen must say it is waiting, and must not wait five minutes.

Hoan pressed the button and nothing on the page changed for one to two minutes. Measured from
his own data, most of that is SCTS itself: it signed at 17:59:24 and the ERP recorded the
approval at 18:00, thirty-six seconds later. The rest was the */5 poll.

Two problems, and the smaller one is the cadence. The bigger one is that a page which shows
no change is indistinguishable from a page where the click did nothing - so the natural
response is to press again. The stepper now says it is waiting and refreshes itself.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _find(*parts):
    tried = []
    root = _HERE
    for _i in range(8):
        path = os.path.join(root, *parts)
        tried.append(path)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s. Da thu:\n  %s" % (parts[-1], "\n  ".join(tried)))


class TestPollCadence(unittest.TestCase):
    def setUp(self):
        self.hooks = _find("hooks.py")

    def test_poll_pending_runs_every_minute(self):
        block = re.search(r'"\*/1 \* \* \* \*":\s*\[(.*?)\]', self.hooks, re.S)
        self.assertIsNotNone(block, "khong co khoi cron moi phut")
        self.assertIn("tasks.poll_pending", block.group(1))

    def test_it_is_declared_exactly_once(self):
        self.assertEqual(self.hooks.count("tasks.poll_pending"), 1,
                         "khai hai lan = chay hai lan moi chu ky, goi SCTS gap doi")

    def test_it_is_no_longer_on_the_five_minute_block(self):
        block = re.search(r'"\*/5 \* \* \* \*":\s*\[(.*?)\]', self.hooks, re.S)
        if block:
            self.assertNotIn("tasks.poll_pending", block.group(1))


class TestWaitingState(unittest.TestCase):
    def setUp(self):
        self.page = _find("approval_center", "features", "payment_request", "ui",
                          "main_section.html")

    def test_waiting_starts_after_a_successful_submit(self):
        self.assertIn("startSignWait(name,", self.page)

    def test_the_current_step_says_it_is_waiting(self):
        self.assertIn("Đang chờ nhà cung cấp xác nhận", self.page)
        # Phai bat vao cho GOI, khong phai cho DINH NGHIA: "markSignWait(steps, det)" cung
        # xuat hien o dong "function markSignWait(steps, det){", nen mot phep kiem ngay tho
        # van xanh khi ham da bi bo khong goi nua. Da vap dung loi nay khi nghiem thu.
        self.assertIn("renderStepsHTML(markSignWait(steps, det))", self.page,
                      "co ham nhung khong goi thi thanh tien trinh van cam nhu cu")
        tail = self.page[self.page.index("Hoàn tất"):][:400]
        self.assertNotIn("renderStepsHTML(steps)", tail,
                         "thanh tien trinh chi tiet dang goi ban KHONG co trang thai cho")

    def test_the_page_refreshes_itself(self):
        self.assertRegex(self.page, r"setInterval\([\s\S]{0,400}refreshDetail\(\)")

    def test_waiting_has_a_deadline(self):
        self.assertIn("SIGNWAIT.until", self.page)
        self.assertRegex(self.page, r"SIGNWAIT\.until\s*=\s*Date\.now\(\)\s*\+",
                         "phai co diem dung - khong duoc quay mai")

    def test_waiting_stops_when_the_level_moves_on(self):
        self.assertIn("current_level", self.page)
        self.assertIn("signWaitActive", self.page)

    def test_the_timer_is_cleared(self):
        self.assertIn("clearInterval(SIGNWAIT.timer)", self.page,
                      "khong don timer = nhieu vong lap chay chong len nhau")

    def test_it_stops_when_the_user_leaves_the_record(self):
        # Nhip do doi tu 10s -> 5s ngay 28/08 (chu ky that len sau 20-40 giay; 10 giay la
        # qua thua cho mot man hinh dang cho). Khong ghim con so vao phep kiem nay nua -
        # phep kiem thuoc ve "roi trang thi phai dung", khong phai ve nhip.
        block = re.search(r"SIGNWAIT\.timer = setInterval\(function\(\)\{(.*?)\}, \d+\)",
                          self.page, re.S)
        self.assertIsNotNone(block)
        self.assertIn("stopSignWait()", block.group(1),
                      "roi khoi ho so ma van hoi lai = goi API vo ich mai mai")


if __name__ == "__main__":
    unittest.main()
