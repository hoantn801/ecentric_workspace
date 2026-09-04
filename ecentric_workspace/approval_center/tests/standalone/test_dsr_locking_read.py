# Copyright (c) 2026, eCentric and contributors
"""process_signing_request phai doc DSR bang MOT lenh co khoa tra ve du lieu.

Hai lan gui doi tren cung mot chan ky, cach nhau 1 giay, khong ai bam gi:

    EC-DSR-2026-00035  03/09 02:23:58 HT | 02:24:00 PA | 02:24:01 BV | 02:24:08 HT | 02:24:10 PA
    EC-DSR-2026-00041  04/09 03:28:03 HT | 03:28:05 PA | 03:28:05 BV | 03:28:11 HT | 03:28:13 PA

Co che: worker A dang gui; cron poll_pending (*/1) get_all thay DSR Queued -> goi
process_signing_request -> `get_value(name, for_update=True)` DOI khoa; A commit Provider
Accepted; B thuc day, nhung lenh doc `*` sau do la lenh THUONG - duoi REPEATABLE READ no
doc snapshot lap tu luc get_all, van la Queued -> may_have_sent=False -> gui lan hai.

Sua: doc `*` ngay trong lenh co khoa. Kiem bang AST: lenh doc dau tien cua ham phai la
get_value(DSR, dsr_name, "*", as_dict=True, for_update=True), va KHONG con lenh doc `*`
nao khong khoa truoc khi `dsr` duoc dung.
"""
import ast
import io
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TASKS = os.path.join(_HERE, "..", "..", "..", "platform", "esign", "tasks.py")


def _fn(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError("khong thay ham %s" % name)


def _kw(call, name):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


class TestDocCoKhoa(unittest.TestCase):
    def setUp(self):
        with io.open(_TASKS, encoding="utf-8") as fh:
            self.tree = ast.parse(fh.read())
        self.fn = _fn(self.tree, "process_signing_request")

    def _dsr_assign(self):
        for st in self.fn.body:
            if isinstance(st, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "dsr" for t in st.targets):
                return st
        raise AssertionError("khong thay `dsr = ...` o cap ngoai cua ham")

    def test_dsr_doc_bang_lenh_co_khoa_tra_du_lieu(self):
        st = self._dsr_assign()
        call = st.value
        self.assertIsInstance(call, ast.Call)
        self.assertEqual(ast.unparse(call.func), "frappe.db.get_value")
        args = [ast.unparse(a) for a in call.args]
        self.assertEqual(args[2], "'*'", "phai doc DU LIEU, khong chi `name`")
        fu = _kw(call, "for_update")
        self.assertIsNotNone(fu, "thieu for_update=True: lenh doc `*` la lenh thuong -> snapshot cu")
        self.assertTrue(isinstance(fu, ast.Constant) and fu.value is True)
        ad = _kw(call, "as_dict")
        self.assertTrue(isinstance(ad, ast.Constant) and ad.value is True)

    def test_khong_con_lenh_doc_name_khoa_roi_doc_thuong(self):
        """Mau cu: get_value(DSR, dsr_name, 'name', for_update=True) roi get_value(..., '*').
        Neu con ca hai thi lenh thu hai van la lenh thuong - loi chua sua."""
        st = self._dsr_assign()
        idx = self.fn.body.index(st)
        before = self.fn.body[:idx]
        for s in before:
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
                src = ast.unparse(s.value)
                self.assertNotIn("for_update", src,
                                 "khoa rieng truoc roi doc thuong sau = van doc snapshot cu")

    def test_dsr_la_lenh_dau_tien_cua_ham(self):
        """Khong duoc co lenh doc nao khac truoc no trong ham (moi lenh doc thuong lap snapshot)."""
        st = self._dsr_assign()
        idx = self.fn.body.index(st)
        for s in self.fn.body[:idx]:
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
                continue        # docstring
            self.assertNotIsInstance(s, (ast.Assign, ast.Expr),
                                     "co lenh truoc lenh doc co khoa: %s" % ast.unparse(s)[:80])


if __name__ == "__main__":
    unittest.main()
