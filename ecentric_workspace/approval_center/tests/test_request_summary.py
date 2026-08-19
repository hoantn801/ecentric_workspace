# Copyright (c) 2026, eCentric and contributors
"""request_summary(): notification body = sender + department + amount (best-effort),
meta-driven and never touching a missing field. Site-free: monkeypatch transitions.frappe."""
import sys
import types
import unittest


class _D(dict):
    __getattr__ = lambda self, k: self.get(k)


def _stub(fieldnames, values, full_names):
    fr = types.ModuleType("frappe")
    fr.get_meta = lambda dt: types.SimpleNamespace(
        fields=[types.SimpleNamespace(fieldname=f) for f in fieldnames])

    def get_value(dt, name, fields, as_dict=False):
        if dt == "User":
            return full_names.get(name)
        return _D({f: values.get(f) for f in fields})
    fr.db = types.SimpleNamespace(get_value=get_value)
    return fr


def _load_transitions():
    if "frappe" not in sys.modules:
        f = types.ModuleType("frappe"); f.__path__ = []
        f._ = lambda s: s
        f.get_meta = lambda dt: types.SimpleNamespace(fields=[])
        f.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
        u = types.ModuleType("frappe.utils")
        u.now_datetime = lambda *a, **k: None; u.add_to_date = lambda *a, **k: None; u.getdate = lambda *a, **k: None
        sys.modules["frappe"] = f; sys.modules["frappe.utils"] = u
    from ecentric_workspace.approval_center.shared.workflow import transitions as t
    return t


class TestRequestSummary(unittest.TestCase):
    def setUp(self):
        self.t = _load_transitions()
        self._orig = self.t.frappe

    def tearDown(self):
        self.t.frappe = self._orig

    def _run(self, fieldnames, values, full_names, dt="EC X", name="N1"):
        self.t.frappe = _stub(fieldnames, values, full_names)
        return self.t.request_summary(dt, name)

    def test_sender_dept_amount(self):
        out = self._run(["requested_by", "department", "payment_amount"],
                        {"requested_by": "a@e.c", "department": "Fin - EC", "payment_amount": 3800000},
                        {"a@e.c": "Hoan Tran"})
        self.assertIn("Người gửi: Hoan Tran", out)
        self.assertIn("Phòng ban: Fin - EC", out)
        self.assertIn("Số tiền: 3,800,000 VND", out)

    def test_no_amount_field(self):
        out = self._run(["requested_by", "requester_department"],
                        {"requested_by": "b@e.c", "requester_department": "Ops - EC"},
                        {"b@e.c": "B Nguyen"})
        self.assertIn("Người gửi: B Nguyen", out)
        self.assertIn("Phòng ban: Ops - EC", out)
        self.assertNotIn("Số tiền", out)

    def test_missing_fields_returns_empty(self):
        self.assertEqual(self._run([], {}, {}), "")


if __name__ == "__main__":
    unittest.main()
