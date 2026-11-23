# Copyright (c) 2026, eCentric and contributors
"""Quy trinh A-Z (24/11/2026, Hoan: "show full quy trinh tu A-Z"): moi loai phieu co viec SAU khi
duyet (engine _FULFILLMENT_HANDLERS) phai khai `journey_after`; khai sai thi gay luc nap registry;
get_bootstrap / get_detail tra `journey_after` + cac cap duyet that.
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_journey_after.py
"""
import glob
import importlib
import os
import re
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.dirname(_APP))


def _fake_frappe():
    fk = types.ModuleType("frappe")
    fk._ = lambda s, *a: s
    fk.whitelist = lambda *a, **k: (lambda f: f)
    fk.session = types.SimpleNamespace(user="a@x")
    mods = {"frappe": fk}
    for m in ("frappe.utils", "frappe.model", "frappe.model.document"):
        mods[m] = types.ModuleType(m)
    mods["frappe.utils"].get_datetime = lambda v=None: v
    return mods


class JourneyAfter(unittest.TestCase):
    def setUp(self):
        self.saved = dict(sys.modules)
        sys.modules.update(_fake_frappe())
        from ecentric_workspace.approval_center.shared.requests import contracts
        self.C = contracts
        self.defs = {}
        for f in sorted(glob.glob(os.path.join(_APP, "approval_center", "features", "*", "domain", "definition.py"))):
            mod = "ecentric_workspace." + os.path.relpath(f, _APP)[:-3].replace(os.sep, ".")
            m = importlib.import_module(mod)
            for v in vars(m).values():
                if isinstance(v, contracts.ApprovalDefinition):
                    self.defs[v.business_doctype] = v

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self.saved)

    def test_moi_loai_co_viec_sau_duyet_deu_khai_journey(self):
        src = open(os.path.join(_APP, "approval_center", "shared", "workflow", "transitions.py"),
                   encoding="utf-8").read()
        block = src[src.index("_FULFILLMENT_HANDLERS = {"):]
        block = block[:block.index("\n}\n")]
        doctypes = re.findall(r'^\s*"(EC [^"]+)":', block, re.M)
        self.assertGreater(len(doctypes), 15)
        missing = [dt for dt in doctypes if dt in self.defs and not self.defs[dt].journey_after]
        self.assertEqual([], missing, "co viec sau duyet nhung chua khai journey_after: %s" % missing)

    def test_khai_hop_le_va_validate(self):
        for d in self.defs.values():
            self.C.validate_definition(d)
            for label, meta, kind in d.journey_after:
                self.assertIn(kind, self.C.JOURNEY_KINDS)
        from dataclasses import replace
        bad = replace(next(iter(self.defs.values())), journey_after=(("X", "y", "khac"),))
        with self.assertRaises(ValueError):
            self.C.validate_definition(bad)

    def test_tuyen_dung_du_vong(self):
        hr = self.defs["EC Hiring Request"].journey_after
        self.assertEqual([j[0] for j in hr], ["HR tuyển dụng", "Offer từng ứng viên",
                                               "Chuẩn bị nhân sự mới", "Onboard"])
        self.assertEqual(self.defs["EC Payment Request"].journey_after[0][0], "Finance xử lý UNC")

    def test_bootstrap_tra_journey_va_cap_duyet(self):
        from ecentric_workspace.approval_center.shared.requests import query_service as Q
        d = self.defs["EC Hiring Request"]
        out = Q.journey_after(d)
        self.assertEqual(out[0], {"label": "HR tuyển dụng", "meta": d.journey_after[0][1], "kind": "fulfillment"})
        src = open(Q.__file__, encoding="utf-8").read()
        boot = src[src.index("def bootstrap("):src.index("def journey_after(")]
        self.assertIn('"journey_after": journey_after(definition)', boot)
        self.assertIn('"process_preview": _safe_preview(definition.code)', boot)
        self.assertIn('"journey_after": journey_after(definition),', src[src.index('"timeline": timeline'):])


if __name__ == "__main__":
    unittest.main()
