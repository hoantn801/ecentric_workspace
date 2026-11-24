# Copyright (c) 2026, eCentric and contributors
"""Each Group: mot nguoi o HAI nhom cua cung cap phai them duoc (24/11/2026 - nguyen nhan 10 Offer
thang 10 khong sinh New Staff Preparation: "Duplicate approver ... for this request level").
Van chan trung that (cung cap, cung nguoi, cung nhom / cap khong chia nhom).
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_approver_mot_nguoi_hai_nhom.py
"""
import importlib
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))


class _Err(Exception):
    pass


def _load(rows):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    def throw(m, *a):
        raise _Err(m)
    fk.throw = throw
    def get_all(dt, filters=None, fields=None):
        out = []
        for r in rows:
            if r["request_level"] == filters["request_level"] and r["approver"] == filters["approver"] \
                    and r["name"] != filters["name"][1]:
                out.append(dict(r))
        return out
    fk.get_all = get_all
    fk.model = types.ModuleType("frappe.model")
    fk.model.document = types.ModuleType("frappe.model.document")
    class Document(object):
        def __init__(self, **kw):
            self.__dict__.update(kw)
        def get(self, k, d=None):
            return self.__dict__.get(k, d)
    fk.model.document.Document = Document
    sys.modules.update({"frappe": fk, "frappe.model": fk.model, "frappe.model.document": fk.model.document})
    m = "ecentric_workspace.approval_center.doctype.ec_approval_request_approver.ec_approval_request_approver"
    sys.modules.pop(m, None)
    return importlib.import_module(m).ECApprovalRequestApprover


class T(unittest.TestCase):
    def setUp(self):
        self.saved = dict(sys.modules)

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self.saved)

    def test_cung_nguoi_khac_nhom_duoc(self):
        A = _load([{"name": "R1", "request_level": "L1", "approver": "h@x", "participant_group": "HR"}])
        A(name=None, request_level="L1", approver="h@x", participant_group="HOF").validate()

    def test_cung_nguoi_cung_nhom_bi_chan(self):
        A = _load([{"name": "R1", "request_level": "L1", "approver": "h@x", "participant_group": "HR"}])
        with self.assertRaises(_Err):
            A(name=None, request_level="L1", approver="h@x", participant_group="HR").validate()

    def test_cap_khong_chia_nhom_van_chan_trung(self):
        A = _load([{"name": "R1", "request_level": "L1", "approver": "h@x", "participant_group": None}])
        with self.assertRaises(_Err):
            A(name=None, request_level="L1", approver="h@x", participant_group=None).validate()

    def test_khac_cap_duoc(self):
        A = _load([{"name": "R1", "request_level": "L1", "approver": "h@x", "participant_group": None}])
        A(name=None, request_level="L2", approver="h@x", participant_group=None).validate()


if __name__ == "__main__":
    unittest.main()
