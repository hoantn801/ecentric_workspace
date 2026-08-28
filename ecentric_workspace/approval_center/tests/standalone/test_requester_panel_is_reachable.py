# Copyright (c) 2026, eCentric and contributors
"""The requester must be able to prepare, lock and submit WITHOUT anyone calling an API by
hand.

Twice - 27 and 28 August - Hoan asked the same question: "there is no button". Both times the
answer was to call the endpoints from PowerShell, so the cause survived both rounds.

There were two holes, and each one alone was enough:

1. `_esign_requester_panel()` - the panel that owns "Chuẩn bị gói ký" and "Khoá gói ký" - was
   defined in page_sync and never called. A comment said the unified section had replaced it.
   The unified section contains no such controls, so nothing replaced anything.

2. `requester_submit_and_sign` had NO caller in any screen at all. The endpoint has worked
   since 23 August; there was simply never a "Trình ký" button. So even after preparing and
   locking, the flow dead-ended.

Between them the requester signing stage was unreachable through the UI from the day it was
built. It looked finished because every test drove the endpoints directly - which is exactly
what the tests below refuse to do.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
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


class TestPanelReachesThePage(unittest.TestCase):
    def setUp(self):
        self.sync = _src("approval_center", "features", "payment_request", "infrastructure",
                         "page_sync.py")

    def test_the_requester_panel_is_actually_injected(self):
        m = re.search(r"def _html\(\):(.*?)(?=\n# ---|\ndef )", self.sync, re.S)
        self.assertIsNotNone(m)
        self.assertIn("_esign_requester_panel()", m.group(1),
                      "dinh nghia ma khong goi thi panel khong bao gio len trang")

    def test_no_panel_builder_is_left_defined_but_unused(self):
        """Bat CA HO loi nay, khong chi cai vua sua."""
        orphans = []
        for name in re.findall(r"\ndef (_esign_\w+|_document_signing_section)\(\):", self.sync):
            uses = len(re.findall(r"\b%s\(\)" % name, self.sync))
            if uses < 2:                      # 1 = chi co dong dinh nghia
                orphans.append(name)
        self.assertEqual(orphans, [],
                         "ham dung HTML dinh nghia nhung khong duoc goi: %s" % orphans)


class TestTheRequesterCanFinishWithoutAnApiCall(unittest.TestCase):
    def setUp(self):
        self.panel = _src("platform", "esign", "ui", "requester_signing_panel.html")

    def test_prepare_lock_and_submit_all_have_buttons(self):
        for endpoint in ("prepare_requester_signing_package",
                         "requester_lock_signing_package",
                         "requester_submit_and_sign"):
            self.assertIn(endpoint, self.panel,
                          "khong man hinh nao goi %s -> phai goi API bang tay" % endpoint)

    def test_the_submit_button_exists_and_is_wired(self):
        self.assertIn('id="ecReqSign"', self.panel)
        self.assertIn("btnSign.onclick", self.panel,
                      "ve ra nut ma khong gan su kien thi bam khong an gi")

    def test_the_submit_button_shows_once_the_package_is_locked(self):
        m = re.search(r'\} else if \(locked\) \{(.*?)\} else if \(readyToLock\)',
                      self.panel, re.S)
        self.assertIsNotNone(m)
        self.assertIn("signShow = true", m.group(1),
                      "khoa goi xong ma khong hien nut Trinh ky thi luong dung o day")

    def test_the_message_tells_them_what_to_do_next(self):
        self.assertIn('Bấm \\"Trình ký\\"', self.panel,
                      "cau cu bao 'cho quan tri bat cong ky' - khong con dung va khong huong dan gi")


class TestEveryWhitelistedRequesterEndpointHasACaller(unittest.TestCase):
    """Phong loi CUNG HO: mot endpoint cua nguoi de nghi khong co giao dien nao goi."""

    _NO_UI_NEEDED = {"requester_signing_readiness"}   # readiness duoc goi ngam khi tai panel

    def test_no_orphan_requester_endpoint(self):
        api = _src("platform", "esign", "api.py")
        panel = _src("platform", "esign", "ui", "requester_signing_panel.html")
        section = _src("platform", "esign", "ui", "document_signing_section.html")
        main = _src("approval_center", "features", "payment_request", "ui", "main_section.html")
        screens = panel + section + main
        orphans = []
        for name in re.findall(r"\ndef (requester_\w+|prepare_requester_\w+)\(", api):
            if name in self._NO_UI_NEEDED:
                continue
            if name not in screens:
                orphans.append(name)
        self.assertEqual(orphans, [],
                         "endpoint cua nguoi de nghi khong man hinh nao goi: %s" % orphans)


if __name__ == "__main__":
    unittest.main()
