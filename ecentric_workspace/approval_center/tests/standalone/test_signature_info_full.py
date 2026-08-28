# Copyright (c) 2026, eCentric and contributors
"""signatureInfo must carry everything the portal carries - eight fields, not three.

2026-08-28, 21:35. The user expanded the collapsed `signatureInfo` object in the portal's
own successful transition call. It holds EIGHT fields:

    id, name, image, signerId, hsmId, companyId, signType, signToken

Ours held three: id, name, image. Every transition we ever sent (five that day) was
answered 2xx and then silently ignored - no workflow row, no signature. A signing service
that is not told WHICH HSM certificate to sign with cannot produce a signature; whether
that is the exact mechanism or not, it was the last observable difference between the two
payloads after toUsers, transitionId, processAction, signType and the image had all been
made identical.

Every value comes from GetSignatures - the provider's own record of the signature - not
from anything we invent.

These tests RUN the real adapter and client against a fake transport and read the actual
request body. A source grep cannot prove a field reaches the wire; three of those certified
real holes earlier this week.
"""
import json
import sys
import types
import unittest
from datetime import datetime

# ---------------- frappe stub (adapter imports frappe + frappe.utils + .password) -----
# Dat "if not in sys.modules" de KHONG de len stub day du hon cua bo test khac khi chay
# discover chung; nhung khi chay mot minh thi phai du het cac module con.
if "frappe" not in sys.modules:
    fr = types.ModuleType("frappe")
    fr._ = lambda x: x
    fr.conf = {}
    fr.db = types.SimpleNamespace(set_value=lambda *a, **k: None,
                                  get_value=lambda *a, **k: None)
    fr.session = types.SimpleNamespace(user="test@x")
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: datetime.now()
    utils.get_datetime = lambda v: v
    utils.add_to_date = lambda d, **k: d
    utils.cint = lambda v: int(v or 0)
    utils.flt = lambda v: float(v or 0)
    pw = types.ModuleType("frappe.utils.password")
    pw.get_decrypted_password = lambda *a, **k: ""
    utils.password = pw
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    sys.modules["frappe.utils.password"] = pw

sys.path.insert(0, ".")
from ecentric_workspace.platform.esign.providers.scts import SctsAdapter  # noqa: E402
from ecentric_workspace.platform.esign.providers.scts_client import SctsClient  # noqa: E402


class Resp(object):
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


# The provider's own signature record, shape from the live GetSignatures contract.
_SIG = {"id": "638649a4-3920-4775-93bb-4575a08b0b7d", "signerId": "73f72e15-4f56",
        "code": "ky-tham-gia", "name": "Ký tham gia", "base64Image": "iVBORw0KGgo",
        "type": "HSM", "hsmCertId": "07524427-2dbb-4f73", "companyId": "ECENTRIC",
        "companyName": "eCentric"}

_CFG = {"transition_id": -2, "transition_name": "Trình ký",
        "process_action": "WfFunctionRunSignedOther", "sign_type": "ky-tham-gia"}


def _mk(transport):
    client = SctsClient(base_url="https://x", transport=transport, timeout=5)
    a = SctsAdapter.__new__(SctsAdapter)
    a._client = client
    a._with_auth = lambda fn: fn("TOKEN")
    return a


class TestSignatureInfoMatchesThePortal(unittest.TestCase):
    def _run(self, sig_record):
        calls = []

        def transport(method, url, headers=None, json_body=None, **kw):
            calls.append((method, url, json_body))
            if "/api/SignerSignature/GetSignatures/" in url:
                return Resp(200, [sig_record] if sig_record else [])
            return Resp(200, {"success": True, "data": "txn-1"})
        a = _mk(transport)
        a.transition_with_recipients("DOC-1", "73f72e15-4f56", ["3ef4b0e3"],
                                     _CFG, _SIG["id"])
        bodies = [b for (m, u, b) in calls if u.endswith("/api/Workflow/transition")]
        self.assertEqual(len(bodies), 1, "phai gui dung mot lenh transition")
        return bodies[0]

    def test_all_eight_captured_fields_are_on_the_wire(self):
        info = self._run(_SIG)["signatureInfo"]
        self.assertEqual(set(info.keys()),
                         {"id", "name", "image", "signerId", "hsmId", "companyId",
                          "signType", "signToken"},
                         "phai dung TAM truong nhu capture 21:35 - khong thieu, khong thua")

    def test_the_values_come_from_the_provider_record(self):
        info = self._run(_SIG)["signatureInfo"]
        self.assertEqual(info["id"], _SIG["id"])
        self.assertEqual(info["name"], "Ký tham gia")
        self.assertEqual(info["image"], "iVBORw0KGgo")
        self.assertEqual(info["signerId"], "73f72e15-4f56")
        self.assertEqual(info["hsmId"], "07524427-2dbb-4f73",
                         "hsmId phai la hsmCertId cua GetSignatures - thieu chung thu thi "
                         "khong ky duoc")
        self.assertEqual(info["companyId"], "ECENTRIC")
        self.assertEqual(info["signType"], "ky-tham-gia")
        self.assertEqual(info["signToken"], 0)

    def test_a_missing_record_still_sends_and_does_not_crash(self):
        """Doc hong thi van gui va de provider tu tu choi - khong tu ket luan thay no."""
        body = self._run(None)
        info = body["signatureInfo"]
        self.assertEqual(info["id"], _SIG["id"])
        self.assertEqual(info["image"], "")
        self.assertEqual(info["hsmId"], "")

    def test_the_rest_of_the_payload_still_matches_the_capture(self):
        body = self._run(_SIG)
        self.assertEqual(body["transitionId"], "-2")     # chuoi, khong phai so
        self.assertEqual(body["toUsers"], ["3ef4b0e3"])
        self.assertEqual(body["processAction"], "WfFunctionRunSignedOther")
        self.assertEqual(body["signType"], "ky-tham-gia")
        self.assertEqual(body["userId"], "73f72e15-4f56")


if __name__ == "__main__":
    unittest.main()
