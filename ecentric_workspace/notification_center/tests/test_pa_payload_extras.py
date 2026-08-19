# Copyright (c) 2026, eCentric and contributors
"""power_automate.build_payload exposes structured card extras (requester_name /
department / amount) derived meta-driven from the reference doc, so the Teams flow can
lay them out as separate lines. Site-free: stub frappe, load the module in isolation."""
import importlib.util
import os
import sys
import types
import unittest

_PA = os.path.join(os.path.dirname(__file__), "..", "providers", "power_automate.py")


class _D(dict):
    __getattr__ = lambda self, k: self.get(k)


def _load(fieldnames, row, full_name):
    fr = types.ModuleType("frappe"); fr.__path__ = []
    fr.get_meta = lambda dt: types.SimpleNamespace(
        fields=[types.SimpleNamespace(fieldname=f) for f in fieldnames])

    def gv(dt, name, fields, as_dict=False):
        if dt == "User":
            return full_name
        return _D({f: row.get(f) for f in fields})
    fr.db = types.SimpleNamespace(get_value=gv)
    sys.modules["frappe"] = fr
    spec = importlib.util.spec_from_file_location("pa_mod", os.path.abspath(_PA))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


class TestPayloadExtras(unittest.TestCase):
    def test_amount_dept_sender(self):
        pa = _load(["requested_by", "department", "payment_amount"],
                   {"requested_by": "a@e.c", "department": "Production - EC", "payment_amount": 3800000},
                   "Hoàn Trần")
        out = pa.build_payload({"reference_doctype": "EC Payment Request", "reference_name": "EC-PAY-1"})
        self.assertEqual(out["requester_name"], "Hoàn Trần")
        self.assertEqual(out["department"], "Production - EC")
        self.assertEqual(out["amount"], "3,800,000 VND")

    def test_no_amount_field_blank(self):
        pa = _load(["requested_by", "requester_department"],
                   {"requested_by": "b@e.c", "requester_department": "Ops - EC"}, "B Nguyen")
        out = pa.build_payload({"reference_doctype": "EC Leave Request", "reference_name": "L1"})
        self.assertEqual(out["requester_name"], "B Nguyen")
        self.assertEqual(out["amount"], "")

    def test_non_business_ref_all_blank(self):
        pa = _load([], {}, None)
        out = pa.build_payload({"reference_doctype": "Task", "reference_name": "T1"})
        self.assertEqual(out["requester_name"], "")
        self.assertEqual(out["amount"], "")
        self.assertEqual(out["department"], "")


if __name__ == "__main__":
    unittest.main()
