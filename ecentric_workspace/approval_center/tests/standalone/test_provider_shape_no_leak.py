# Copyright (c) 2026, eCentric and contributors
"""A diagnostic must never become a data dump.

`provider_document_shape` exists to answer one question - is eContract's `instanceId` the
same thing as the document id? - without firing candidate values at a NON-IDEMPOTENT write.
The temptation with any such tool is to "just return the raw response". These checks make
that impossible to do by accident: the shape carries types, never values, and identifiers
are limited to GUID-ish tokens under identifier-looking keys.

The payload below is modelled on a real eContract document detail: it carries an amount, a
signer email, a signing time, a private comment and a filename. None of them may appear in
the output.
"""
import unittest

from ecentric_workspace.platform.esign import shapes

RAW = {
    "id": "31f17256-aaaa-4bbb-8ccc-ddddddddddd0",
    "name": "UAT VOID 6 - hoa don noi bo",
    "amount": 12345,
    "isValid": True,
    "workflowInstanceId": "9f8e7d6c-1111-4222-8333-444444444444",
    "signers": [{"email": "hoan.tran@ecentric.vn", "signedAt": "11:54",
                 "userId": "73f72e15-4f56-4bde-84e9-68edd9918d7c",
                 "comment": "y kien rieng tu"}],
    "files": [{"fileId": "aaaa1111-2222-4333-8444-555555555555", "fileName": "secret.pdf"}],
}

SECRETS = ("UAT VOID 6", "12345", "y kien rieng tu", "secret.pdf",
           "hoan.tran@ecentric.vn", "11:54")


class TestNoLeak(unittest.TestCase):
    def _blob(self):
        import json
        return json.dumps(shapes.shape_of(RAW)) + json.dumps(shapes.identifiers_of(RAW))

    def test_nothing_sensitive_appears_anywhere(self):
        blob = self._blob()
        for secret in SECRETS:
            self.assertNotIn(secret, blob, "lo du lieu: %s" % secret)

    def test_shape_reports_types_not_values(self):
        shape = shapes.shape_of(RAW)
        self.assertEqual(shape["name"], "str")
        self.assertEqual(shape["amount"], "int")
        self.assertEqual(shape["isValid"], "bool")
        self.assertEqual(shape["signers"][0]["comment"], "str")

    def test_depth_is_capped(self):
        deep = {"a": {"b": {"c": {"d": {"e": {"f": "x"}}}}}}
        flat = repr(shapes.shape_of(deep))
        self.assertIn("...", flat, "phai cat bot khi qua sau")

    def test_identifier_count_is_capped(self):
        wide = {("k%03did" % i): "aaaa1111-2222-4333-8444-5555555555%02d" % (i % 100)
                for i in range(200)}
        self.assertLessEqual(len(shapes.identifiers_of(wide)), shapes.MAX_IDENTIFIERS)


class TestAnswersTheQuestion(unittest.TestCase):
    """Neu no khong lo ra duoc instanceId thi cong cu nay vo dung."""

    def test_camel_case_id_keys_are_found(self):
        ids = shapes.identifiers_of(RAW)
        self.assertIn("workflowInstanceId", ids,
                      "camelCase la quy uoc cua eContract - bo qua no la tuot mat dung field can tim")
        self.assertIn("signers[0].userId", ids)
        self.assertIn("files[0].fileId", ids)

    def test_instance_id_can_be_compared_with_document_id(self):
        ids = shapes.identifiers_of(RAW)
        self.assertNotEqual(ids["workflowInstanceId"], ids["id"],
                            "day chinh la cau tra loi dang can: hai thu KHAC nhau")

    def test_non_guid_identifier_values_are_ignored(self):
        self.assertEqual(shapes.identifiers_of({"someId": "admin"}), {},
                         "id dang chuoi thuong (vd tai khoan 'admin') khong phai GUID")

    def test_non_identifier_keys_are_ignored_even_when_guidish(self):
        self.assertEqual(shapes.identifiers_of({"token": "aaaa1111-2222-4333-8444-555555555555"}), {})


if __name__ == "__main__":
    unittest.main()
