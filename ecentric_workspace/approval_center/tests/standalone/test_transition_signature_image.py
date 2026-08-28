# Copyright (c) 2026, eCentric and contributors
"""The handover call must carry the signature image, and must never log it.

Three nights of guessing ended with one line, read off the wire on 2026-08-27:

    errors: SignatureInfo.Image=The Image field is required.

Two things worth recording. First, the fix is small: eContract wants the image inside
`signatureInfo`, not just the id and name. Second - and this is the part I got wrong - my
standing hypothesis was that `instanceId` had to be a workflow/task id rather than the
document id. ASP.NET reports EVERY invalid field in one response, and it named exactly one.
So the document id was right all along, and the diagnosis only became possible once
`error_digest` stopped truncating the message before its useful half.

The image is signature material, so these checks also pin down that it never reaches an
event, a log, or an error string.
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


def _fn(src, name):
    m = re.search(r"\n    def %s\(.*?\n(.*?)(?=\n    def |\Z)" % name, src, re.S)
    assert m, "khong tim thay %s" % name
    return m.group(1)


class TestImageIsSent(unittest.TestCase):
    def setUp(self):
        self.client = _src("platform", "esign", "providers", "scts_client.py")
        self.adapter = _src("platform", "esign", "providers", "scts.py")

    def test_signature_info_carries_the_image(self):
        body = _fn(self.client, "transition")
        self.assertIn('"image": signature_image or ""', body,
                      "thieu truong image -> eContract tra 400 SignatureInfo.Image")

    def test_the_parameter_exists_and_defaults_to_none(self):
        self.assertIn("signature_image=None", self.client)

    def test_the_adapter_actually_fetches_it(self):
        body = _fn(self.adapter, "transition_with_recipients")
        self.assertIn("self.signature_record(provider_user_id, signature_id)", body)
        self.assertIn("signature_image=image", body,
                      "lay anh ve roi khong truyen di thi van 400 nhu cu")

    def test_a_failed_fetch_does_not_invent_a_verdict(self):
        body = _fn(self.adapter, "transition_with_recipients")
        self.assertIn("except Exception:", body)
        self.assertIn("rec = None", body)
        self.assertNotIn("return", body.split("except Exception:")[1][:120],
                         "hong lay anh thi van gui va de provider tu choi, khong tu ket luan thay no")


class TestImageNeverLeaks(unittest.TestCase):
    """Anh chu ky la vat lieu chu ky - khong duoc roi vao su kien, log hay chuoi loi."""

    def test_the_error_sanitizer_withholds_bodies_mentioning_base64(self):
        client = _src("platform", "esign", "providers", "scts_client.py")
        body = _fn(client, "_safe_body")
        self.assertIn('"base64"', body)
        self.assertIn("body withheld", body)

    def test_safe_error_withholds_messages_mentioning_base64(self):
        sanitize = _src("platform", "esign", "sanitize.py")
        self.assertIn('"base64"', sanitize)
        self.assertIn("message withheld", sanitize)

    def test_the_request_body_is_not_echoed_into_the_error(self):
        client = _src("platform", "esign", "providers", "scts_client.py")
        body = _fn(client, "transition")
        self.assertNotIn("body)", body.split("raise ProviderError")[-1] if "raise ProviderError" in body else "",
                         "khong duoc dua nguyen body (co chua anh) vao thong diep loi")


class TestTheDisplayNameComesFromTheProvider(unittest.TestCase):
    """28/08: portal gui signatureInfo.name = "Ky tham gia"; minh gui ma "ky-tham-gia".

    Ten hien thi KHONG suy ra duoc tu ma. Truoc day khong co ten nao khac de gui nen code
    lay tam `sign_type`. GetSignatures tra ve ca `name` trong cung mot lan goi da dung de
    lay anh - doc thang tu do thay vi doan.

    Khong chung minh duoc day la nguyen nhan chung tu bi ket; chi la mot bien so bi loai.
    """

    def setUp(self):
        self.src = _src("platform", "esign", "providers", "scts.py")

    def test_the_name_is_read_from_the_provider_record(self):
        body = re.search(r"(?m)^    def signature_record.*?(?=\n    def )", self.src, re.S)
        self.assertIsNotNone(body, "thieu ham doc nguyen ban ghi chu ky")
        self.assertEqual(body.group(0).count("get_signatures"), 1,
                         "mot lan goi lay du moi truong, khong goi nhieu lan")

    def test_the_provider_name_outranks_the_code(self):
        body = re.search(r"(?m)^    def transition_with_recipients.*?(?=\n    @|\n    def )",
                         self.src, re.S).group(0)
        m = re.search(r"signature_name or ([a-z_]+) or config\.get\(\"sign_type\"\)", body)
        self.assertIsNotNone(m, "thu tu uu tien ten chu ky da bi doi")
        self.assertEqual(m.group(1), "provider_name",
                         "ten nha cung cap phai duoc uu tien truoc ma sign_type")

    def test_a_failure_to_read_it_does_not_stop_the_send(self):
        body = re.search(r"(?m)^    def transition_with_recipients.*?(?=\n    @|\n    def )",
                         self.src, re.S).group(0)
        self.assertIn("except Exception:", body)
        self.assertIn("rec = rec or {}", body,
                      "doc hong thi van gui di va de provider tu tu choi")


if __name__ == "__main__":
    unittest.main()
