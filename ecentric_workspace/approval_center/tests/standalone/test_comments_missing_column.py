# Copyright (c) 2026, eCentric and contributors
"""Khung trao doi tren phieu khong duoc vo vi form khong co cot `fulfillment_owner`.

23/09: phan binh luan cua EC-APR-2026-00355 (HR Activity) tra HTTP 500 moi lan co nguoi mo
phieu. Do tren production: HR Activity, Contract Review, Purchase Request, Leave deu 500
(OperationalError), Payment + System thi 200. `_assert_can_view` doc CUNG hai cot
["requested_by", "fulfillment_owner"] - ma chi 8/28 DocType nghiep vu co cot thu hai. Song
tu 09/09 (p166).

Bo test giu ba dieu:
  1. Form KHONG co cot van qua duoc cong quyen - khong nem loi SQL.
  2. Form CO cot van doc va chuyen `fulfillment_owner` cho `can_view_request` - nguoi dang
     xu ly phieu phai con doc/gui duoc trao doi. Bo luon cot la siet qua tay.
  3. Doi chieu voi 28 DocType THAT trong repo: so form thieu cot phai khop, de lan sau ai them
     form thu 29 cung duoc bo test nay canh.

Cat ham bang AST, chay trong khong gian ten rieng - khong dung sys.modules.
"""
import ast
import glob
import io
import json
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.normpath(os.path.join(_HERE, "..", ".."))
_ACTIONS = os.path.join(_AC, "reporting", "actions.py")


def _ham(ten):
    src = io.open(_ACTIONS, encoding="utf-8").read()
    for node in ast.parse(src).body:
        if getattr(node, "name", None) == ten:
            return ast.get_source_segment(src, node)
    raise AssertionError("khong thay " + ten)


def _chay(cac_cot_co_that, ghi):
    """Dung `_assert_can_view` voi mot DocType chi co `cac_cot_co_that`."""
    class _Loi(Exception):
        pass

    def get_value(dt, name, fields, as_dict=False):
        thieu = [f for f in fields if f not in cac_cot_co_that]
        if thieu:
            # dung hanh vi that cua MariaDB: 1054 Unknown column
            raise _Loi("(1054, \"Unknown column '%s' in 'field list'\")" % thieu[0])
        return {f: "x@e.c" for f in fields}

    fr = types.SimpleNamespace(
        db=types.SimpleNamespace(get_value=get_value),
        get_meta=lambda dt: types.SimpleNamespace(has_field=lambda f: f in cac_cot_co_that),
        throw=lambda *a, **k: (_ for _ in ()).throw(PermissionError(a[0] if a else "")),
        PermissionError=PermissionError,
    )
    perm = types.ModuleType("perm")

    def can_view_request(request_name, **kw):
        ghi.append(kw)
        return True
    perm.can_view_request = can_view_request

    src = _ham("_assert_can_view").replace(
        "    from ecentric_workspace.approval_center.shared.workflow.permissions import can_view_request\n",
        "")
    ns = {"frappe": fr, "_": lambda s: s, "can_view_request": can_view_request}
    exec(src, ns)
    dn = types.SimpleNamespace(business_doctype="EC HR Activity Request", code="HR_ACTIVITY")
    return ns["_assert_can_view"](dn, "EC-HRAC-1", "EC-APR-2026-00355")


class TestCongQuyenTraoDoi(unittest.TestCase):
    def test_form_KHONG_co_cot_van_qua_cong(self):
        ghi = []
        row = _chay({"requested_by"}, ghi)
        self.assertEqual(row.get("requested_by"), "x@e.c")
        self.assertIsNone(ghi[0]["fulfillment_owner"])

    def test_form_CO_cot_van_chuyen_nguoi_xu_ly_cho_luat_quyen(self):
        ghi = []
        _chay({"requested_by", "fulfillment_owner"}, ghi)
        self.assertEqual(ghi[0]["fulfillment_owner"], "x@e.c",
                         "bo luon cot o form CO cot la siet qua tay - nguoi dang xu ly mat quyen doc")


class TestDoiChieu28Form(unittest.TestCase):
    def test_so_form_thieu_cot_khop_thuc_te(self):
        """Neu con so nay doi, hoac form moi ma khong co bo test nay canh, ta phai biet."""
        co, thieu = 0, 0
        for p in glob.glob(os.path.join(_AC, "features", "*", "domain", "definition.py")):
            src = io.open(p, encoding="utf-8").read()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and node.value.startswith("EC ") and node.value.endswith("Request"):
                    slug = node.value.lower().replace(" ", "_")
                    j = os.path.join(_AC, "doctype", slug, slug + ".json")
                    if os.path.exists(j):
                        names = {f["fieldname"] for f in json.load(open(j))["fields"]}
                        if "fulfillment_owner" in names:
                            co += 1
                        else:
                            thieu += 1
                    break
        self.assertGreater(thieu, 0, "khong con form nao thieu cot? kiem lai phep dem")
        self.assertGreater(co, 0)


if __name__ == "__main__":
    unittest.main()
