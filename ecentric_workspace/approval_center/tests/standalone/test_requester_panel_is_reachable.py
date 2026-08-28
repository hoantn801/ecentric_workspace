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

    def test_submit_is_what_reaches_them_now(self):
        """28/08: cach bao dam da doi, dieu duoc bao dam thi khong.

        Truoc: panel phai VE RA nut "Trinh ky", vi do la duong duy nhat toi endpoint.
        Gio: "Gui yeu cau" goi thang sign_on_submit, nen nut do la thua - nhung phep bao
        dam van phai la "co mot duong tu dong toi endpoint", khong duoc bien mat cung voi
        cai nut. Hai lan (27 va 28/08) luong dung lai vi khong ai goi endpoint nay.
        """
        submitter = _src("approval_center", "shared", "finance_support.py")
        self.assertIn("sign_on_submit", submitter,
                      "khong con nut Trinh ky MA submit cung khong goi -> endpoint mo coi lai")
        requester = _src("platform", "esign", "requester.py")
        self.assertIn("return requester_submit_and_sign", requester,
                      "sign_on_submit phai thuc su di den endpoint gui ky")

    def test_no_button_asks_for_an_internal_step(self):
        m = re.search(r"var status, prepText, prepShow.*?\n(.*?)\n\s*elStatus\.textContent",
                      self.panel, re.S)
        self.assertIsNotNone(m)
        for banned in ("prepShow = true", "lockShow = true", "signShow = true"):
            self.assertNotIn(banned, m.group(1),
                             "buoc noi bo cua may khong duoc hoi nguoi dung: %s" % banned)

    def test_the_message_tells_them_what_is_happening(self):
        self.assertIn("Đã khoá gói ký và gửi chữ ký của bạn tới nhà cung cấp", self.panel,
                      "phai noi da xay ra gi, khong bao nguoi dung di bam them mot nut nua")


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
