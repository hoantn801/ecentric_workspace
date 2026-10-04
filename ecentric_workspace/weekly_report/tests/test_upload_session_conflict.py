# Copyright (c) 2026, eCentric and contributors
"""Va cham ten tep khi tao phien upload khong duoc chan nguoi nop.

04/10/2026: hai nguoi khong nop duoc bao cao W40. Man hinh hien nguyen van
`HTTP 409 {"error":{"code":"nameAlreadyExists"` -- 13 lan trong hai ngay. Code
DA gui `conflictBehavior: replace` va dong do dang chay tren production, nen
Graph van tu choi ghi de; nguyen nhan goc (tep bi check-out? phien upload do
dang con giu cho?) van chua xac dinh.

Bo test nay khong noi gi ve nguyen nhan do. No ghim mot dieu khac, dung bat ke
nguyen nhan: nguoi nop khong duoc chan vi mot va cham ten tep, va khong bao gio
phai doc ma loi cua Graph.

    bench run-tests --module ecentric_workspace.weekly_report.tests.test_upload_session_conflict
"""

import sys
import types
import unittest

if "frappe" not in sys.modules:
    _fr = types.ModuleType("frappe")
    _fr.whitelist = lambda *a, **k: (lambda f: f)
    _fr._ = lambda s: s
    _fr.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0] if a else "throw"))
    _fr.log_error = lambda **k: None
    _fr.get_doc = lambda *a, **k: None
    _fr.session = types.SimpleNamespace(user="tester")
    _fr.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
    sys.modules["frappe"] = _fr
    # `sharepoint.py` lam `from frappe.utils import ...` ngay khi nap module,
    # nen thieu cai nay la ca bo test khong chay duoc.
    _u = types.ModuleType("frappe.utils")
    _u.nowdate = lambda: "2026-10-04"
    _u.add_days = lambda d, n: "2026-10-04"
    _u.cint = lambda v: int(v or 0)
    _fr.utils = _u
    sys.modules["frappe.utils"] = _u

import frappe  # noqa: E402

from ecentric_workspace.weekly_report import sharepoint as SP  # noqa: E402

PATH = "Weekly Reports/E-commerce Operation/2026-W40_NV00083_Thu Nguyen_Weekly Report W40.2026.pdf"


class _Resp(object):
    def __init__(self, status, text="", payload=None):
        self.status_code = status
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeRequests(object):
    """Ghi lai moi lan goi va tra ve ket qua da dat san, theo thu tu."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.urls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.urls.append(url)
        return self._responses.pop(0) if self._responses else _Resp(500, "het ket qua")


CONFLICT = _Resp(409, '{"error":{"code":"nameAlreadyExists","message":"..."}}')


def _ok(url="https://upload.example/session"):
    return _Resp(200, "", {"uploadUrl": url})


class RenameOnConflictTest(unittest.TestCase):
    def setUp(self):
        self._orig = SP.requests
        self.logged = []
        frappe.log_error = lambda **k: self.logged.append(k)

    def tearDown(self):
        SP.requests = self._orig

    def test_no_conflict_uses_the_original_path_and_calls_once(self):
        """Canh doi: ban va KHONG duoc lam doi duong di binh thuong."""
        SP.requests = _FakeRequests([_ok()])
        url = SP.create_deck_upload_session(PATH, "TOKEN")
        self.assertEqual(url, "https://upload.example/session")
        self.assertEqual(len(SP.requests.urls), 1, "khong trung thi chi goi MOT lan")
        self.assertNotIn("(2)", SP.requests.urls[0])
        self.assertEqual(self.logged, [], "khong doi ten thi khong ghi log")

    def _duong_dan(self, url):
        """Lay lai duong dan tep tu URL Graph, da giai ma.

        Kiem tren URL tho thi de viet nham: `quote()` ma hoa ca `(` `)` thanh
        `%28 %29`, va URL ket thuc bang `:/createUploadSession` chu khong phai
        `.pdf`. Hai phep kiem dau tien cua bo test nay do sai vi the.
        """
        try:
            from urllib.parse import unquote
        except ImportError:                      # py2
            from urllib import unquote           # noqa
        tail = url.split("/drive/root:/", 1)[1]
        return unquote(tail.rsplit(":/", 1)[0])

    def test_conflict_retries_with_a_suffixed_name(self):
        SP.requests = _FakeRequests([CONFLICT, _ok()])
        url = SP.create_deck_upload_session(PATH, "TOKEN")
        self.assertEqual(url, "https://upload.example/session")
        self.assertEqual(len(SP.requests.urls), 2)
        self.assertEqual(self._duong_dan(SP.requests.urls[0]), PATH,
                         "lan dau phai dung duong dan goc")
        self.assertIn(" (2)", self._duong_dan(SP.requests.urls[1]),
                      "lan hai phai doi ten")

    def test_suffix_goes_before_the_extension(self):
        """`bao cao.pdf (2)` thi SharePoint lan trinh duyet deu khong nhan ra PDF."""
        SP.requests = _FakeRequests([CONFLICT, _ok()])
        SP.create_deck_upload_session(PATH, "TOKEN")
        self.assertTrue(self._duong_dan(SP.requests.urls[1]).endswith(".pdf"),
                        "duoi tep phai van la .pdf")

    def test_renaming_is_recorded(self):
        """Doi ten lang le thi vai tuan nua thu muc day ban sao ma khong ai biet
        vi sao. Phai de lai dau vet de con truy nguyen nhan goc."""
        SP.requests = _FakeRequests([CONFLICT, _ok()])
        SP.create_deck_upload_session(PATH, "TOKEN")
        self.assertEqual(len(self.logged), 1)
        self.assertIn("(2)", self.logged[0]["message"])

    def test_gives_up_after_a_bounded_number_of_tries(self):
        """Khong thu vo han: qua vai lan thi khong con la va cham ten nua,
        va nguoi dung dang ngoi doi."""
        SP.requests = _FakeRequests([CONFLICT] * 10)
        with self.assertRaises(SP.GraphError):
            SP.create_deck_upload_session(PATH, "TOKEN")
        self.assertLessEqual(len(SP.requests.urls), SP.RENAME_ATTEMPTS + 1)

    def test_other_errors_are_not_retried(self):
        """403/404/500 thi doi ten khong cuu duoc. Thu them chi lam nguoi dung
        doi lau hon, va che mat loi that."""
        for status, body in ((403, "accessDenied"), (404, "itemNotFound"),
                             (500, "generalException")):
            SP.requests = _FakeRequests([_Resp(status, body)])
            with self.assertRaises(SP.GraphError):
                SP.create_deck_upload_session(PATH, "TOKEN")
            self.assertEqual(len(SP.requests.urls), 1,
                             "loi %d khong duoc thu lai" % status)

    def test_409_that_is_not_a_name_clash_is_not_retried(self):
        """409 con duoc dung cho chuyen khac (vi du xung dot phien ban). Chi
        doi ten khi Graph noi DUNG la trung ten."""
        SP.requests = _FakeRequests([_Resp(409, '{"error":{"code":"resourceModified"}}')])
        with self.assertRaises(SP.GraphError):
            SP.create_deck_upload_session(PATH, "TOKEN")
        self.assertEqual(len(SP.requests.urls), 1)

    def test_error_message_still_carries_graphs_own_reason(self):
        """Nguoi dung khong doc ma loi, nhung nguoi SUA thi can. Giu nguyen van
        ly do cua Graph trong ngoai le."""
        SP.requests = _FakeRequests([CONFLICT] * 10)
        try:
            SP.create_deck_upload_session(PATH, "TOKEN")
        except SP.GraphError as exc:
            self.assertIn("nameAlreadyExists", str(exc))
        else:
            self.fail("phai nem GraphError")

    def test_return_type_is_still_a_plain_string(self):
        """`approval_center...sharepoint_mirror` dung gia tri nay THANG lam URL
        de PUT. Doi sang tuple la lam hong module cua chat khac."""
        SP.requests = _FakeRequests([_ok()])
        self.assertIsInstance(SP.create_deck_upload_session(PATH, "TOKEN"), str)


class SuffixTest(unittest.TestCase):
    def test_keeps_folder_and_extension(self):
        out = SP._with_suffix("Weekly Reports/X/2026-W40_NV1_bao cao.pdf", 2)
        self.assertEqual(out, "Weekly Reports/X/2026-W40_NV1_bao cao (2).pdf")

    def test_handles_a_name_without_extension(self):
        out = SP._with_suffix("Weekly Reports/X/khong_co_duoi", 3)
        self.assertEqual(out, "Weekly Reports/X/khong_co_duoi (3)")

    def test_only_the_last_dot_counts(self):
        """`Weekly Report W40.2026.pdf` -- ten that cua ca hai nguoi bi chan
        04/10 deu co dau cham giua ten."""
        out = SP._with_suffix("Weekly Reports/X/W40.2026.pdf", 2)
        self.assertEqual(out, "Weekly Reports/X/W40.2026 (2).pdf")


if __name__ == "__main__":
    unittest.main()
