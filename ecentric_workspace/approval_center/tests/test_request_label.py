# Copyright (c) 2026, eCentric and contributors
"""request_label(): notification label uses the reference doc's title (title_field),
falls back to '<Type> <id>' then the id. Site-free: monkeypatch the module's frappe."""
import sys
import types
import unittest


def _stub(meta, values, types_):
    fr = types.ModuleType("frappe")
    fr.get_meta = lambda dt: types.SimpleNamespace(title_field=meta.get(dt))

    def get_value(dt, name, field):
        if dt == "EC Approval Type":
            return types_.get(name)
        return values.get((dt, name, field))
    fr.db = types.SimpleNamespace(get_value=get_value)
    return fr


def _load_transitions():
    # Provide the frappe package transitions imports at module load, once.
    if "frappe" not in sys.modules:
        f = types.ModuleType("frappe"); f.__path__ = []
        f._ = lambda s: s
        f.get_meta = lambda dt: types.SimpleNamespace(title_field=None)
        f.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
        u = types.ModuleType("frappe.utils")
        u.now_datetime = lambda *a, **k: None
        u.add_to_date = lambda *a, **k: None
        u.getdate = lambda *a, **k: None
        sys.modules["frappe"] = f
        sys.modules["frappe.utils"] = u
    from ecentric_workspace.approval_center.shared.workflow import transitions as t
    return t


class TestRequestLabel(unittest.TestCase):
    def setUp(self):
        self.t = _load_transitions()
        self._orig = self.t.frappe

    def tearDown(self):
        self.t.frappe = self._orig

    def _rl(self, meta=None, values=None, types_=None):
        self.t.frappe = _stub(meta or {}, values or {}, types_ or {})
        return self.t.request_label

    def test_uses_title_field(self):
        rl = self._rl(meta={"EC AI Topup Request": "request_title"},
                      values={("EC AI Topup Request", "EC-AITOP-1", "request_title"): "De nghi top up AI - Higgsfield"})
        self.assertEqual(rl("EC AI Topup Request", "EC-AITOP-1", "AI_TOPUP"), "De nghi top up AI - Higgsfield")

    def test_fallback_type_label_plus_id(self):
        rl = self._rl(meta={"EC X": None}, types_={"AI_TOPUP": "AI Topup"})
        self.assertEqual(rl("EC X", "EC-APR-9", "AI_TOPUP"), "AI Topup EC-APR-9")

    def test_fallback_bare_id(self):
        rl = self._rl(meta={"EC X": None})
        self.assertEqual(rl("EC X", "EC-APR-9"), "EC-APR-9")

    def test_empty_title_falls_back(self):
        rl = self._rl(meta={"EC Y": "request_title"},
                      values={("EC Y", "N1", "request_title"): ""}, types_={"T": "Type Y"})
        self.assertEqual(rl("EC Y", "N1", "T"), "Type Y N1")

    def test_meta_error_never_raises(self):
        self.t.frappe = types.SimpleNamespace(
            get_meta=lambda dt: (_ for _ in ()).throw(RuntimeError("no meta")),
            db=types.SimpleNamespace(get_value=lambda *a, **k: None))
        self.assertEqual(self.t.request_label("EC Z", "N9"), "N9")


if __name__ == "__main__":
    unittest.main()
