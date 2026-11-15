# Copyright (c) 2026, eCentric and contributors
"""Ten deck khong bao gio trung + loi tao phien upload de lai dau vet (15/11/2026).

Hai su co that:
  * 15/11: "Weekly_Report_VitaDairy_MTD_14-11 (2).pptx" -> createUploadSession
    409 nameAlreadyExists du da gui conflictBehavior=replace (tep cung ten dang bi
    giu tren SharePoint). Doi ten tay (viet lien, khong dau) thi nop duoc.
  * 08/11: secret Microsoft het han, ~4 gio moi lan nop deu hong, nhung Error Log
    khong cho biet AI bi: GraphError lam rollback ca request, ke ca dong log.

Chay khong can bench: PYTHONPATH=.:tools/ci/stubs python3 -m pytest <file>
"""

import types
import unittest
from unittest import mock

from ecentric_workspace.weekly_report import api, sharepoint


class DeckFilenameTest(unittest.TestCase):
    def test_vietnamese_spaces_and_parentheses_become_plain_ascii(self):
        got = sharepoint.deck_filename("Báo cáo Tuần Đặc biệt (2).PPTX", "11151630ab12")
        self.assertEqual(got, "Bao_cao_Tuan_Dac_biet_2_11151630ab12.pptx")

    def test_the_15_11_file_gets_a_new_unique_name(self):
        got = sharepoint.deck_filename("Weekly_Report_VitaDairy_MTD_14-11 (2).pptx", "11151626x9y8")
        self.assertEqual(got, "Weekly_Report_VitaDairy_MTD_14-11_2_11151626x9y8.pptx")

    def test_same_name_twice_never_collides(self):
        a = sharepoint.deck_filename("report.pdf", "11151630aaaa")
        b = sharepoint.deck_filename("report.pdf", "11151630bbbb")
        self.assertNotEqual(a, b)

    def test_output_only_has_safe_characters(self):
        nasty = 'a"*:<>?/\\|#%&+= ~`!@$^{}[];,\'b.pdf'
        got = sharepoint.deck_filename(nasty, "s1")
        self.assertRegex(got, r"^[A-Za-z0-9._-]+$")
        self.assertTrue(got.endswith("_s1.pdf"))
        # build_deck_path cung khong con gi de cat
        self.assertEqual(sharepoint.safe_filename(got), got)

    def test_no_extension_and_empty_name(self):
        self.assertEqual(sharepoint.deck_filename("bao cao", "s1"), "bao_cao_s1")
        self.assertEqual(sharepoint.deck_filename("", "s1"), "deck_s1")
        self.assertEqual(sharepoint.deck_filename("(((.pdf", "s1"), "deck_s1.pdf")

    def test_dots_inside_name_kept_only_as_separators(self):
        got = sharepoint.deck_filename("Weekly Report W40.2026.pdf", "s1")
        self.assertEqual(got, "Weekly_Report_W40.2026_s1.pdf")

    def test_long_title_is_capped(self):
        got = sharepoint.deck_filename("x" * 500 + ".pdf", "s1")
        self.assertLessEqual(len(got), sharepoint.DECK_BASE_MAX + len("_s1.pdf"))

    def test_stamp_is_sanitised_too(self):
        self.assertEqual(sharepoint.deck_filename("a.pdf", "11/15 16:30"), "a_11151630.pdf")


class _Thrown(Exception):
    pass


class UploadSessionTest(unittest.TestCase):
    """create_deck_upload_session: ten duy nhat, va loi thi ghi log KEM nguoi bam."""

    def setUp(self):
        self.calls = {"log": [], "commit": 0, "throw": [], "session_path": None}
        fake_db = types.SimpleNamespace(
            get_value=lambda *a, **k: "NV00003",
            commit=lambda: self.calls.__setitem__("commit", self.calls["commit"] + 1),
        )
        self.frappe = types.SimpleNamespace(
            db=fake_db,
            session=types.SimpleNamespace(user="huyen.nguyen@ecentric.vn"),
            generate_hash=lambda length=10: "ab12"[:length],
            log_error=lambda title=None, message=None: self.calls["log"].append((title, message)),
            throw=self._throw,
            get_roles=lambda *a: [],
        )
        self.patches = [
            mock.patch.object(api, "frappe", self.frappe),
            mock.patch.object(api, "_assert_can_submit_for", lambda e: None),
            mock.patch.object(api, "now_datetime",
                              lambda: __import__("datetime").datetime(2026, 11, 15, 16, 30)),
            mock.patch.object(api, "_", lambda s: s),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _throw(self, msg, exc=None):
        self.calls["throw"].append(msg)
        raise _Thrown(msg)

    def _session_ok(self, rel_path, token):
        self.calls["session_path"] = rel_path
        return "https://upload/xyz"

    def test_happy_path_uses_unique_ascii_name(self):
        with mock.patch.object(sharepoint, "get_app_token", lambda: "tok"), \
             mock.patch.object(sharepoint, "create_deck_upload_session", self._session_ok):
            out = api.create_deck_upload_session(
                filename="Weekly_Report_VitaDairy_MTD_14-11 (2).pptx", week_label="2026-W46",
                employee="HR-EMP-00023", department="E-commerce Operation - EC")
        self.assertEqual(out, {"success": True, "upload_url": "https://upload/xyz"})
        self.assertEqual(
            self.calls["session_path"],
            "Weekly Reports/E-commerce Operation/"
            "2026-W46_NV00003_Weekly_Report_VitaDairy_MTD_14-11_2_11151630ab12.pptx")
        self.assertEqual(self.calls["log"], [])

    def _fail_with(self, text):
        def boom(*a, **k):
            raise sharepoint.GraphError(text)
        with mock.patch.object(sharepoint, "get_app_token", lambda: "tok"), \
             mock.patch.object(sharepoint, "create_deck_upload_session", boom):
            with self.assertRaises(_Thrown):
                api.create_deck_upload_session(
                    filename="a.pdf", week_label="2026-W46",
                    employee="HR-EMP-00023", department="Media - EC")

    def test_failure_is_logged_with_the_person_and_committed(self):
        self._fail_with('createUploadSession x failed: HTTP 409 {"error":{"code":"nameAlreadyExists"}}')
        self.assertEqual(len(self.calls["log"]), 1)
        title, msg = self.calls["log"][0]
        self.assertEqual(title, api.UPLOAD_FAIL_LOG)
        self.assertIn("user=huyen.nguyen@ecentric.vn", msg)
        self.assertIn("employee=HR-EMP-00023", msg)
        self.assertIn("week=2026-W46", msg)
        # Khong commit thi frappe.throw rollback mat luon dong log (su co 08/11).
        self.assertEqual(self.calls["commit"], 1)

    def test_user_sees_plain_vietnamese_not_graph_json(self):
        self._fail_with('createUploadSession x failed: HTTP 409 {"error":{"code":"nameAlreadyExists"}}')
        shown = self.calls["throw"][0]
        self.assertIn("khoá trên SharePoint", shown)
        self.assertIn("Nháp của bạn vẫn được giữ", shown)
        self.assertNotIn("{", shown)

    def test_expired_secret_gets_its_own_message(self):
        def bad_token():
            raise sharepoint.GraphError('token failed: HTTP 401 {"error":"invalid_client"}')
        with mock.patch.object(sharepoint, "get_app_token", bad_token):
            with self.assertRaises(_Thrown):
                api.create_deck_upload_session(
                    filename="a.pdf", week_label="2026-W46",
                    employee="HR-EMP-00023", department="Media - EC")
        self.assertIn("Microsoft", self.calls["throw"][0])
        self.assertEqual(self.calls["commit"], 1)

    def test_non_graph_errors_are_not_swallowed(self):
        def other(*a, **k):
            raise ValueError("bug")
        with mock.patch.object(sharepoint, "get_app_token", other):
            with self.assertRaises(ValueError):
                api.create_deck_upload_session(
                    filename="a.pdf", week_label="2026-W46",
                    employee="HR-EMP-00023", department="Media - EC")
        self.assertEqual(self.calls["log"], [])


if __name__ == "__main__":
    unittest.main()
