# Copyright (c) 2026, eCentric and contributors
"""Tep da ky KHONG BAO GIO duoc xoa (Hoan 08/09). Hook File.on_trash -> file_guard.

Kiem tren code that (exec, frappe gia): DSF.signed_file tro vao -> chan; ten SIGNED- -> chan;
tep thuong -> cho qua; co override -> cho qua + log; hooks.py co dang ky; purge tool bat co.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


class _Perm(Exception):
    pass


def _guard(signed_names=(), flag=False):
    logs = []
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.PermissionError = _Perm
    fk.session = types.SimpleNamespace(user="u@ec.vn")
    fk.flags = types.SimpleNamespace(ec_allow_signed_file_delete=flag)
    fk.log_error = lambda msg, title=None: logs.append(title)
    fk.db = types.SimpleNamespace(
        exists=lambda dt, f: f.get("signed_file") in signed_names,
        has_column=lambda dt, c: False)

    def throw(msg, exc=Exception):
        raise exc(msg)
    fk.throw = throw
    saved = sys.modules.get("frappe"); sys.modules["frappe"] = fk
    try:
        m = types.ModuleType("_fg")
        exec(compile(_read("platform", "esign", "file_guard.py"), "file_guard.py", "exec"), m.__dict__)
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved
    m._logs = logs
    return m


class _Doc(types.SimpleNamespace):
    def get(self, k, d=None):
        return getattr(self, k, d)


class TestGuard(unittest.TestCase):
    def test_dsf_tro_vao_thi_chan(self):
        m = _guard(signed_names=("F-SIGNED",))
        with self.assertRaises(_Perm):
            m.forbid_signed_file_delete(_Doc(name="F-SIGNED", file_name="x.pdf"))

    def test_ten_SIGNED_thi_chan(self):
        m = _guard()
        with self.assertRaises(_Perm):
            m.forbid_signed_file_delete(_Doc(name="F2", file_name="SIGNED-abc.pdf"))

    def test_tep_thuong_cho_qua(self):
        m = _guard(signed_names=("F-SIGNED",))
        m.forbid_signed_file_delete(_Doc(name="F3", file_name="hop dong.pdf"))   # khong nem

    def test_override_cho_qua_va_log(self):
        m = _guard(signed_names=("F-SIGNED",), flag=True)
        m.forbid_signed_file_delete(_Doc(name="F-SIGNED", file_name="SIGNED-a.pdf"))
        self.assertEqual(m._logs, ["esign signed file delete OVERRIDE"])

    def test_dang_ky_hook_va_purge_bat_co(self):
        h = _read("hooks.py")
        i = h.index('"File": {')
        self.assertIn('"on_trash": "ecentric_workspace.platform.esign.file_guard.forbid_signed_file_delete"', h[i:i + 400])
        p = _read("approval_center", "features", "payment_request", "infrastructure", "purge_test_data.py")
        self.assertIn("frappe.flags.ec_allow_signed_file_delete = True", p)
        self.assertLess(p.index("ec_allow_signed_file_delete"), p.index("for dt, names in plan.items()"))


if __name__ == "__main__":
    unittest.main()
