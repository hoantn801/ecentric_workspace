# Copyright (c) 2026, eCentric and contributors
"""p523 doi loai phieu nhan su sang nhom HR: dung danh sach, chi doi khi dang o nhom cu, idempotent."""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATCH = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "patches",
                      "p523_nhom_nhan_su_approval_center.py")


def _nap(rows):
    f = types.ModuleType("frappe")
    db = {"EC Approval Type": rows, "EC Approval Category": {"HR": {}, "ADMINISTRATION": {}},
          "DocType": {"EC Approval Type": {}}}
    f.db = types.SimpleNamespace(
        exists=lambda dt, n=None: n in db.get(dt, {}),
        get_value=lambda dt, n, fld: db[dt][n].get(fld),
        set_value=lambda dt, n, fld, v: db[dt][n].__setitem__(fld, v),
        commit=lambda: None)
    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = f
    try:
        m = types.ModuleType("p523")
        exec(compile(io.open(_PATCH, encoding="utf-8").read(), _PATCH, "exec"), m.__dict__)
        return m
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved


class T(unittest.TestCase):
    def test_doi_dung(self):
        rows = {"HIRING_REQUEST": {"category": "ADMINISTRATION"},
                "OFFER_REQUEST": {"category": "ADMINISTRATION"},
                "EMPLOYEE_REFERRAL": {"category": "OTHERS"},
                "DOCUMENT_REQUEST": {"category": "ADMINISTRATION"},
                "ASSET_DAMAGE_LOSS": {"category": "ADMINISTRATION"},
                "PROMOTION_REQUEST": {"category": "FINANCE_BUDGET"},   # da doi tay
                "PAYMENT_REQUEST": {"category": "FINANCE_BUDGET"}}
        m = _nap(rows)
        m.execute()
        m.execute()
        self.assertEqual(rows["HIRING_REQUEST"]["category"], "HR")
        self.assertEqual(rows["OFFER_REQUEST"]["category"], "HR")
        self.assertEqual(rows["EMPLOYEE_REFERRAL"]["category"], "HR")
        self.assertEqual(rows["DOCUMENT_REQUEST"]["category"], "ADMINISTRATION")
        self.assertEqual(rows["ASSET_DAMAGE_LOSS"]["category"], "ADMINISTRATION")
        self.assertEqual(rows["PROMOTION_REQUEST"]["category"], "FINANCE_BUDGET")
        self.assertEqual(rows["PAYMENT_REQUEST"]["category"], "FINANCE_BUDGET")

    def test_danh_sach(self):
        m = _nap({})
        self.assertNotIn("DOCUMENT_REQUEST", m.DOI)
        self.assertNotIn("ASSET_DAMAGE_LOSS", m.DOI)
        self.assertEqual(len(m.DOI), 11)


if __name__ == "__main__":
    unittest.main()
