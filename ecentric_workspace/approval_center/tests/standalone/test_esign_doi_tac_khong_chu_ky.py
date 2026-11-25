# Copyright (c) 2026, eCentric and contributors
"""Canh sang buoc DOI TAC gui KHONG chu ky - giong cong CMC (25/11/2026).

Su co EC-CTR-2026-00135 (WF09): CEO bam Duyet & Ky -> ERP gui `-5` (CEO -> Doi tac) kem
signatureInfo "ky-chinh". Log xu ly quy trinh cua CMC: "Loi xu ly", nguoi nhan trong; tai lieu
sang nut doi tac nhung Ky chinh trong va doi tac "Cho gui di".
Cong CMC (tasks.js) KHONG gui chu ky khi buoc dich la PARTNER:
    requiresSignature = transition.isSigned && toState.stateType !== 'PARTNER'
Chot o day:
  1. Duong ky lay-buoc-tu-cong: ke hoach partner_handover -> gui signature_id None; con lai giu
     nguyen chu ky cua nguoi ky (DNTT, cap ky noi bo khong doi).
  2. Su kien HandoverTargeted ghi `signature_sent` de truy vet.
  3. Adapter: signature_id None -> payload khong chu ky (signatureInfo / signType null).
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")


def _read(*p):
    with io.open(os.path.join(_ESIGN, *p), encoding="utf-8") as fh:
        return fh.read()


class TestPartnerHandoverNoSignature(unittest.TestCase):
    def setUp(self):
        self.src = _read("tasks.py")

    def test_partner_handover_sends_no_signature(self):
        self.assertRegex(self.src, r"sig_for_send = \(None if plan\.get\(\"partner_handover\"\)"
                                   r"\s+else dsr\.effective_signature_id\)")

    def test_send_uses_the_chosen_signature(self):
        i = self.src.index("sig_for_send = (None")
        block = self.src[i:i + 600]
        self.assertIn("adapter.transition_with_recipients(", block)
        call = block[block.index("adapter.transition_with_recipients("):]
        call = call[:call.index(")") + 1]
        self.assertIn("sig_for_send", call)
        self.assertNotIn("effective_signature_id", call)

    def test_no_other_signed_send_bypasses_the_rule(self):
        """Moi lenh transition_with_recipients chi co hai dang: sig_for_send (duong ky) hoac
        None (buoc duyet khong ky)."""
        calls = re.findall(r"adapter\.transition_with_recipients\((.*?)\)\s*\n", self.src,
                           flags=re.S)
        self.assertTrue(calls)
        for c in calls:
            self.assertNotIn("effective_signature_id", c, c)

    def test_event_records_whether_signature_was_sent(self):
        self.assertIn('"signature_sent": not plan.get("partner_handover")', self.src)

    def test_adapter_unsigned_payload_branch_exists(self):
        scts = _read("providers", "scts.py")
        i = scts.index("def transition_with_recipients")
        body = scts[i:i + 4000]
        self.assertIn("if signature_id is None:", body)
        seg = body[body.index("if signature_id is None:"):]
        seg = seg[:seg.index("return")]
        self.assertIn("None, None, None, comment", seg)


if __name__ == "__main__":
    unittest.main()
