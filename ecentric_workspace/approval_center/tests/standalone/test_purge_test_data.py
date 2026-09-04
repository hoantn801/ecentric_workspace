# Copyright (c) 2026, eCentric and contributors
"""Cong cu xoa du lieu test Payment Request (TEMP, het han 30/09/2026) - cac chot phai giu.

Chay code THAT cua purge_test_data.py voi frappe gia. Chot: SM; het han; owner la -> tu choi
ca dot, khong xoa gi; dry_run khong xoa; sai cau xac nhan khong xoa; thu tu xoa con truoc cha
sau; bang append-only di qua frappe.db.delete, con lai qua delete_doc; co Error Log.
"""
import io
import os
import sys
import types
import unittest
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_SRC = os.path.join(_APP, "ecentric_workspace", "approval_center", "features", "payment_request",
                    "infrastructure", "purge_test_data.py")


def _mod(today="2026-09-10", pr_rows=None, sm=True):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.thrown = []
    fk.deleted_raw = []
    fk.deleted_doc = []
    fk.logs = []
    fk.session = types.SimpleNamespace(user="hoan.tran@ecentric.vn")

    def throw(msg, exc=None):
        fk.thrown.append(msg)
        raise Exception(msg)
    fk.throw = throw
    rows = pr_rows if pr_rows is not None else [
        {"name": "EC-PAYR-2026-00001", "owner": "hoan.tran@ecentric.vn"},
        {"name": "EC-PAYR-2026-00002", "owner": "hien.nguyen@ecentric.vn"}]
    tables = {
        "EC Payment Request": rows,
        "EC Approval Request": [{"name": "AR-1"}],
        "EC Digital Signature Package": [{"name": "PKG-1"}],
        "EC Digital Signature Request": [{"name": "DSR-1"}],
        "EC Digital Signature Event": [{"name": "EV-1"}, {"name": "EV-2"}],
        "EC Digital Signature Placement": [], "EC Digital Signature File": [{"name": "DSF-1"}],
        "EC Approval Action": [{"name": "ACT-1"}], "EC Approval Request Approver": [{"name": "APV-1"}],
        "EC Approval Request Level": [{"name": "LV-1"}], "File": [{"name": "F-1"}],
    }

    def get_all(dt, filters=None, fields=None, pluck=None, limit_page_length=None):
        data = tables.get(dt, [])
        if pluck:
            return [r[pluck] for r in data]
        return [types.SimpleNamespace(**r) for r in data]
    fk.get_all = get_all
    fk.db = types.SimpleNamespace(delete=lambda dt, flt: fk.deleted_raw.append((dt, flt)))
    fk.delete_doc = lambda dt, n, **kw: fk.deleted_doc.append((dt, n, kw))
    fk.log_error = lambda msg, title=None: fk.logs.append((title, msg))
    utils = types.ModuleType("frappe.utils")
    utils.getdate = lambda v: date.fromisoformat(str(v))
    utils.nowdate = lambda: today
    perms = types.ModuleType("ecentric_workspace.platform.esign.permissions")

    def assert_system_manager():
        if not sm:
            raise Exception("not sm")
    perms.assert_system_manager = assert_system_manager
    mods = {"frappe": fk, "frappe.utils": utils,
            "ecentric_workspace.platform.esign.permissions": perms}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_purge_under_test")
        with io.open(_SRC, encoding="utf-8") as fh:
            exec(compile(fh.read(), "purge_test_data.py", "exec"), m.__dict__)
        m._fk = fk
        m._mods = mods
        return m
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _run(m, fn):
    saved = {k: sys.modules.get(k) for k in m._mods}
    sys.modules.update(m._mods)
    try:
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class TestPurge(unittest.TestCase):
    def test_dry_run_dem_va_khong_xoa(self):
        m = _mod()
        r = _run(m, lambda: m.purge(None, dry_run=1))
        self.assertTrue(r["dry_run"])
        self.assertEqual(r["counts"]["EC Payment Request"], 2)
        self.assertEqual(m._fk.deleted_raw, []); self.assertEqual(m._fk.deleted_doc, [])

    def test_owner_la_thi_tu_choi_ca_dot_ke_ca_dry_run(self):
        m = _mod(pr_rows=[{"name": "EC-PAYR-2026-00009", "owner": "linh.ngo@ecentric.vn"},
                          {"name": "EC-PAYR-2026-00001", "owner": "hoan.tran@ecentric.vn"}])
        with self.assertRaises(Exception):
            _run(m, lambda: m.purge(m.CONFIRM_PHRASE, dry_run=0))
        self.assertIn("linh.ngo@ecentric.vn", m._fk.thrown[-1])
        self.assertEqual(m._fk.deleted_raw, []); self.assertEqual(m._fk.deleted_doc, [])

    def test_sai_cau_xac_nhan_khong_xoa(self):
        m = _mod()
        with self.assertRaises(Exception):
            _run(m, lambda: m.purge("xoa di", dry_run=0))
        self.assertEqual(m._fk.deleted_doc, [])

    def test_het_han_thi_tu_choi(self):
        m = _mod(today="2026-10-01")
        with self.assertRaises(Exception):
            _run(m, lambda: m.purge(m.CONFIRM_PHRASE, dry_run=0))
        self.assertIn("hết hạn", m._fk.thrown[-1])

    def test_khong_SM_thi_tu_choi(self):
        m = _mod(sm=False)
        with self.assertRaises(Exception):
            _run(m, lambda: m.purge(None, dry_run=1))

    def test_xoa_that_dung_thu_tu_con_truoc_cha_sau_va_co_log(self):
        m = _mod()
        r = _run(m, lambda: m.purge(m.CONFIRM_PHRASE, dry_run=0))
        self.assertFalse(r["dry_run"])
        raw = [d for d, _ in m._fk.deleted_raw]
        self.assertEqual(raw, ["EC Digital Signature Event", "EC Approval Action"],
                         "chi hai bang append-only di qua db.delete")
        order = [dt for dt, _, _ in m._fk.deleted_doc]
        self.assertLess(order.index("EC Digital Signature Request"), order.index("EC Digital Signature Package"))
        self.assertLess(order.index("EC Digital Signature Package"), order.index("EC Approval Request"))
        self.assertLess(order.index("EC Approval Request Level"), order.index("EC Approval Request"))
        self.assertLess(order.index("EC Approval Request"), order.index("EC Payment Request"))
        self.assertLess(order.index("File"), order.index("EC Payment Request"))
        self.assertEqual(order.count("EC Payment Request"), 2)
        self.assertTrue(all(kw.get("force") and kw.get("ignore_permissions") for _, _, kw in m._fk.deleted_doc))
        self.assertEqual(m._fk.logs[0][0], "PURGE payment request test data")


if __name__ == "__main__":
    unittest.main()
