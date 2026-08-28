# Copyright (c) 2026, eCentric and contributors
"""The signature was on the provider's PDF but never appeared on the ERP document.

Reported 2026-08-28: "ben ERP chua co chu ky, ben SCTS thi co roi".

Two different DocTypes name a level, and the code was comparing one to the other:

  * a signature BOX on the document identifies its level by `source_process_level` -
    the name of the EC Approval LEVEL, the shared process template;
  * a signature LEG points at EC Approval REQUEST Level, the per-request copy.

They never match, so no approval-level signature was ever drawn. The requester's signature
DID appear, because it is matched by `kind == "requester"` and needs no level at all - which
is precisely why the gap survived: the feature looked half-working rather than broken.

The overlay now translates request-level -> process-level before answering.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    root, tried = _HERE, []
    for _i in range(8):
        path = os.path.join(root, *parts)
        tried.append(path)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s" % parts[-1])


_API = _src("platform", "esign", "api.py")
_PLAN = _src("platform", "esign", "signer_plan.py")
_UI = _src("platform", "esign", "ui", "document_signing_section.html")


class TestBothSidesSpeakTheSameLevelIdentity(unittest.TestCase):
    def test_the_slot_side_uses_the_process_level(self):
        self.assertIn("lvl.source_process_level or None", _PLAN,
                      "o ky dinh danh cap bang EC Approval Level")

    def test_the_overlay_translates_before_answering(self):
        body = re.search(r"(?m)^def document_signature_overlay.*?(?=\n@|\ndef )",
                         _API, re.S).group(0)
        self.assertIn("_source_level_of(leg.get(\"request_level\"))", body,
                      "phai doi sang ten EC Approval Level truoc khi tra ve")
        self.assertNotIn('"level_ref": leg.get("request_level")', body,
                         "tra thang request_level = khong bao gio khop mot o ky nao")

    def test_the_translation_reads_the_right_field(self):
        body = re.search(r"(?m)^def _source_level_of.*?(?=\n@|\ndef )", _API, re.S).group(0)
        self.assertIn("EC Approval Request Level", body)
        self.assertIn("source_process_level", body)

    def test_a_missing_translation_is_none_not_a_wrong_id(self):
        body = re.search(r"(?m)^def _source_level_of.*?(?=\n@|\ndef )", _API, re.S).group(0)
        self.assertIn("return None", body,
                      "khong tra ra thi de trong, tuyet doi khong tra id sai - ve chu ky "
                      "vao o cua nguoi khac con te hon khong ve")


class TestTheUiMatchesOnThatSameKey(unittest.TestCase):
    def test_the_browser_compares_level_ref_to_level_ref(self):
        self.assertIn('String(r.level_ref) === String(sl.level_ref)', _UI)

    def test_the_requester_slot_does_not_need_a_level(self):
        m = re.search(r'kind === "requester"', _UI)
        self.assertIsNotNone(m, "chu ky nguoi de nghi khop theo kind, khong theo cap")


if __name__ == "__main__":
    unittest.main()
