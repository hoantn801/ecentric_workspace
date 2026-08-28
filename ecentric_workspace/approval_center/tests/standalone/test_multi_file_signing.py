# Copyright (c) 2026, eCentric and contributors
"""Every signable file needs its OWN table of signature areas.

The first version called ConvertPdfFile once - for the first signable file - and applied that
table to every file in the package. With one file nothing shows. With two, every signature on
the second file carries a signatureId belonging to an area of the FIRST file: wrong, and
wrong silently. Recorded as QC finding #8 on 2026-08-28.

It also blocked the plan stated the same day: attach the Purchase Request to the Payment
Request so both are signed in one pass.

These tests drive the real adapter against a fake transport and read the request body, because
a source grep cannot show which file's areas ended up on which document.
"""
import json
import sys
import types
import unittest
from datetime import datetime

# Stub frappe dung chung voi test_scts_econtract_adapter.py.
#
# Hai file cung cai stub vao mot bien toan cuc, va `scts.py` giu tham chieu toi cai NAO
# NAP TRUOC. Ban dau stub o day dung gio thuc con ben kia dung moc co dinh, nen chay
# discover chung thi nam phep kiem cua ho gay - loi cua stub, khong phai cua code. Stub
# phai mo phong CUNG mot rang buoc, neu khong no chi la mot nguon su that thu hai.
from datetime import timedelta  # noqa: E402

if "frappe" not in sys.modules:
    fr = types.ModuleType("frappe")
    fr._ = lambda x: x
    fr.conf = {}
    fr.db = types.SimpleNamespace(set_value=lambda *a, **k: None,
                                  get_value=lambda *a, **k: None)
    fr.get_doc = lambda *a, **k: types.SimpleNamespace(save=lambda **kw: None)
    fr.session = types.SimpleNamespace(user="test@x")
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: datetime(2026, 8, 22, 12, 0, 0)
    utils.get_datetime = lambda v: (
        v if isinstance(v, datetime) else datetime.fromisoformat(str(v)))
    utils.add_to_date = lambda d, **kw: d + timedelta(minutes=kw.get("minutes", 0),
                                                      days=kw.get("days", 0))
    utils.cint = lambda v: int(v or 0)
    utils.flt = lambda v: float(v or 0)
    pw = types.ModuleType("frappe.utils.password")
    pw.get_decrypted_password = lambda *a, **k: "tok-cached"
    utils.password = pw
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    sys.modules["frappe.utils.password"] = pw

sys.path.insert(0, ".")
from ecentric_workspace.platform.esign.providers.scts import SctsAdapter  # noqa: E402
from ecentric_workspace.platform.esign.providers.scts_client import SctsClient  # noqa: E402
from ecentric_workspace.platform.esign.providers.base import ProviderError  # noqa: E402


class Resp(object):
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


def _areas(prefix, titles):
    return json.dumps([{"signatureId": "%s-%s" % (prefix, t), "title": t, "role": "thamgia",
                        "signatureType": "position", "keyword": "", "margin": 0.0,
                        "canBeSigned": True, "added": 0} for t in titles])


def _mk(transport):
    client = SctsClient(base_url="https://x", transport=transport, timeout=5)
    a = SctsAdapter.__new__(SctsAdapter)
    a._client = client
    a._with_auth = lambda fn: fn("TOKEN")
    return a


def _ctx(files, placements):
    return {"doc_code": "EC-PAYR-1", "title": "t", "amount": 1, "deadline": "",
            "workflow_definition_id": "WF", "document_type_id": "DT", "company_id": "EC",
            "department_id": "D", "document_template_id": "",
            "files": files, "placements": placements}


_F1 = {"order": 0, "file_dsf": "DSF1", "name": "payment.pdf", "content": b"%PDF-1",
       "can_be_signed": True, "is_supporting_document": False, "share_with_partner": False}
_F2 = {"order": 1, "file_dsf": "DSF2", "name": "purchase.pdf", "content": b"%PDF-2",
       "can_be_signed": True, "is_supporting_document": False, "share_with_partner": False}


def _pl(dsf, title):
    return {"signature_file": dsf, "page_index": 1, "x": 10, "y": 20, "width": 100,
            "height": 40, "level_no": 1, "page_height": 792.0, "scts_role_title": title}


class TestEachFileGetsItsOwnAreas(unittest.TestCase):
    def _run(self, files, placements, per_file_titles):
        calls = []

        def transport(method, url, headers=None, json_body=None, **kw):
            calls.append((url, json_body))
            if url.endswith("/api/AddDocument/ConvertPdfFile"):
                # Tra bang vung KHAC NHAU tuy noi dung tep - dung nhu eContract lam.
                which = "A" if (json_body or {}).get("fileBase64", "").startswith("JVBERi0x") else "A"
                n = len([c for c in calls if c[0].endswith("ConvertPdfFile")])
                prefix = "F%d" % n
                return Resp(200, {"success": True, "data": {
                    "originContentBase64": "", "contentBase64": "x",
                    "jsonData": _areas(prefix, per_file_titles[n - 1]), "total": 1}})
            return Resp(200, {"success": True, "data": "DOC-1", "errors": None})

        a = _mk(transport)
        a.create_document(_ctx(files, placements))
        body = [b for (u, b) in calls if u.endswith("/api/AddDocument")][0]
        return body, calls

    def test_two_files_trigger_two_area_lookups(self):
        body, calls = self._run([_F1, _F2],
                                [_pl("DSF1", "Nguoi trinh"), _pl("DSF2", "Nguoi trinh")],
                                [["Nguoi trinh"], ["Nguoi trinh"]])
        lookups = [c for c in calls if c[0].endswith("ConvertPdfFile")]
        self.assertEqual(len(lookups), 2,
                         "moi tep ky duoc phai hoi bang vung cua rieng no")

    def test_each_document_uses_its_own_area_id(self):
        body, _c = self._run([_F1, _F2],
                             [_pl("DSF1", "Nguoi trinh"), _pl("DSF2", "Nguoi trinh")],
                             [["Nguoi trinh"], ["Nguoi trinh"]])
        docs = body["Documents"]
        self.assertEqual(docs[0]["Signatures"][0]["signatureId"], "F1-Nguoi trinh")
        self.assertEqual(docs[1]["Signatures"][0]["signatureId"], "F2-Nguoi trinh",
                         "tep thu hai dang mang signatureId cua tep thu nhat")

    def test_one_file_still_works(self):
        body, calls = self._run([_F1], [_pl("DSF1", "Nguoi trinh")], [["Nguoi trinh"]])
        self.assertEqual(len([c for c in calls if c[0].endswith("ConvertPdfFile")]), 1)
        self.assertEqual(body["Documents"][0]["Signatures"][0]["signatureId"],
                         "F1-Nguoi trinh")

    def test_a_title_missing_on_THAT_file_is_refused_and_names_the_file(self):
        with self.assertRaises(ProviderError) as cm:
            self._run([_F1, _F2],
                      [_pl("DSF1", "Nguoi trinh"), _pl("DSF2", "CEO")],
                      [["Nguoi trinh"], ["Nguoi trinh"]])   # tep 2 KHONG co vung "CEO"
        msg = str(cm.exception)
        self.assertIn("DSF2", msg, "phai noi ro tep nao thieu vung, khong chi ten vai tro")


if __name__ == "__main__":
    unittest.main()
