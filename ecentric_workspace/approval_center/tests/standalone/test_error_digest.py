# Copyright (c) 2026, eCentric and contributors
"""An audit field must not delete the part of an error that names the cause.

Real case, 2026-08-27. `/api/Workflow/transition` was rejected with HTTP 400. The provider
returns an RFC 9110 problem document, which puts boilerplate first and the offending FIELD
last. `error_summary` is a Data column cut at 140 characters, so what got stored was:

    ProviderError: SCTS rejected transition (HTTP 400): {"type":"https://tools.ietf.org/
    html/rfc9110#section-15.5.1","title":"One or more valida

Every character that would have identified the problem was thrown away - and the diagnosis
cost another deploy cycle. Twice over those two nights the same shape of mistake: the tool
was mute exactly where it needed to speak.
"""
import unittest

from ecentric_workspace.platform.esign.sanitize import AUDIT_SUMMARY_LIMIT, error_digest

REAL_400 = ('ProviderError: SCTS rejected transition (HTTP 400): '
            '{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.1",'
            '"title":"One or more validation errors occurred.","status":400,'
            '"errors":{"instanceId":["The instanceId field is required."]}}')


class TestErrorDigest(unittest.TestCase):
    def test_short_messages_are_untouched(self):
        self.assertEqual(error_digest("boom"), "boom")

    def test_result_fits_the_data_column(self):
        self.assertLessEqual(len(error_digest(REAL_400)), AUDIT_SUMMARY_LIMIT)

    def test_keeps_the_field_name_at_the_tail(self):
        out = error_digest(REAL_400)
        self.assertIn("instanceId", out,
                      "ten field bi cat mat thi ca ban sua nay vo nghia")

    def test_keeps_the_head_that_says_what_failed(self):
        out = error_digest(REAL_400)
        self.assertIn("ProviderError", out)
        self.assertIn("400", out)

    def test_marks_the_cut(self):
        self.assertIn("...", error_digest(REAL_400))

    def test_empty_and_none_are_safe(self):
        self.assertEqual(error_digest(None), "")
        self.assertEqual(error_digest(""), "")

    def test_head_slice_alone_would_have_failed_this(self):
        """Nghiem thu nguoc: cach cu (cat dau) KHONG the qua duoc phep kiem nay."""
        self.assertNotIn("instanceId", REAL_400[:AUDIT_SUMMARY_LIMIT])


if __name__ == "__main__":
    unittest.main()
