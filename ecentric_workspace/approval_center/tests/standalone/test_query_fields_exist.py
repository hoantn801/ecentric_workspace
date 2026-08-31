# Copyright (c) 2026, eCentric and contributors
"""Moi truong duoc truy van phai CO THAT trong DocType.

31/08/2026: `ops.stuck_legs` hoi `EC Digital Signature Request` hai truong `business_doctype`
va `business_name`. Hai truong do nam tren GOI, khong nam tren chan ky. MySQL nem
`1054 Unknown column`, ca `inbox()` tra 500, va trang quan tri hien dung mot dong:
"Can quyen System Manager" - sai hoan toan.

Ca bo test khong thay gi ca. Ly do don gian: chung gia lap `frappe.get_all`, ma ban gia lap
thi tra ve bat cu truong nao minh hoi. Mot phep kiem chi hoi chinh no thi luon dong y voi
chinh no. Phai doi chieu voi DocType THAT - tuc la file .json trong repo.

Phep kiem nay doc AST cac module esign, tim moi loi goi `frappe.get_all` / `get_all` /
`frappe.db.get_value`, lay ten DocType (giai duoc ca hang so module nhu PKG/DSR) va danh sach
truong, roi doi chieu voi fieldname trong .json. Khong chay Frappe, khong can CSDL.
"""
import ast
import glob
import io
import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "patches")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()

#: Module duoc soi. Them file vao day khi mo rong pham vi.
_MODULES = [
    "platform/esign/ops.py",
    "platform/esign/guard.py",
    "platform/esign/lifecycle.py",
]

#: Truong Frappe tu sinh cho MOI DocType - khong nam trong .json nhung van truy van duoc.
_STANDARD = {
    "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
    "parent", "parentfield", "parenttype", "_user_tags", "_comments", "_assign",
    "_liked_by", "_seen",
}


def _doctype_fields():
    """fieldname cua tung DocType, doc tu .json trong repo."""
    out = {}
    pattern = os.path.join(_ROOT, "*", "doctype", "*", "*.json")
    for path in glob.glob(pattern):
        try:
            doc = json.loads(io.open(path, encoding="utf-8").read())
        except ValueError:
            continue
        if doc.get("doctype") != "DocType" or not doc.get("name"):
            continue
        names = {f.get("fieldname") for f in doc.get("fields", []) if f.get("fieldname")}
        out[doc["name"]] = names | _STANDARD
    return out


_FIELDS = _doctype_fields()


def _const_strings(tree):
    """Hang so module dang `PKG = "EC Digital Signature Package"`."""
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt, val = node.targets[0], node.value
        if isinstance(tgt, ast.Name) and isinstance(val, ast.Constant) \
                and isinstance(val.value, str):
            out[tgt.id] = val.value
    return out


def _resolve(node, consts):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    return None


def _field_names(node):
    """Ten truong trong mot danh sach chu. Bo qua bieu thuc (`count(name) as n`, ham SQL...)."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    out = []
    for el in node.elts:
        if not (isinstance(el, ast.Constant) and isinstance(el.value, str)):
            return None
        raw = el.value.strip()
        if any(c in raw for c in "( )*,`"):
            continue
        out.append(raw.split(".")[-1].strip("`"))
    return out


def _queries(rel):
    """(doctype, [truong], dong) cho moi loi goi doc du lieu giai duoc trong mot module."""
    src = io.open(os.path.join(_ROOT, rel), encoding="utf-8").read()
    tree = ast.parse(src)
    consts = _const_strings(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "attr", None)
        if name not in ("get_all", "get_list", "get_value"):
            continue
        if not node.args:
            continue
        doctype = _resolve(node.args[0], consts)
        if not doctype:
            continue
        fields = None
        for kw in node.keywords:
            if kw.arg in ("fields", "fieldname"):
                fields = _field_names(kw.value)
        if fields is None and name == "get_value" and len(node.args) >= 3:
            fields = _field_names(node.args[2])
            if fields is None:
                one = _resolve(node.args[2], consts)
                fields = [one] if one else None
        if fields:
            found.append((doctype, fields, node.lineno))
    return found


class TestQueriedFieldsExist(unittest.TestCase):
    def test_doc_duoc_dinh_nghia_doctype(self):
        self.assertGreater(len(_FIELDS), 10,
                           "khong doc duoc DocType nao tu repo - phep kiem nay dang mu")

    def test_moi_truong_truy_van_deu_co_that(self):
        checked = 0
        for rel in _MODULES:
            for doctype, fields, lineno in _queries(rel):
                if doctype not in _FIELDS:
                    continue          # DocType cua Frappe/ERPNext, khong co .json trong repo
                for f in fields:
                    checked += 1
                    with self.subTest(module=rel, line=lineno, doctype=doctype, field=f):
                        self.assertIn(
                            f, _FIELDS[doctype],
                            "%s dong %d hoi '%s' tren '%s' nhung DocType do khong co truong "
                            "nay -> MySQL nem 1054 luc chay that. Truong co the nam tren mot "
                            "DocType lien ket - lay qua link, dung hoi thang."
                            % (rel, lineno, f, doctype))
        self.assertGreater(checked, 20,
                           "chi doi chieu duoc %d truong - AST khong con doc duoc cac loi goi, "
                           "phep kiem da mu sau mot lan tai cau truc" % checked)

    def test_khong_module_nao_bi_doc_thanh_rong(self):
        """Nguong tong khong du.

        Go SACH loi goi trong ops.py ma bo test van xanh, vi hai module con lai da qua nguong
        20 truong. Mot module bi doc thanh rong - do doi ten ham, doi cach goi, hay chuyen
        sang lop bao boc - se im lang tuot khoi tam kiem. Nguong phai dat tren TUNG module.
        """
        for rel in _MODULES:
            with self.subTest(module=rel):
                self.assertTrue(
                    _queries(rel),
                    "%s khong con loi goi doc du lieu nao doc duoc. Neu that su khong con "
                    "thi bo no khoi _MODULES mot cach co y; con khong thi cach doc AST da "
                    "khong theo kip code." % rel)


if __name__ == "__main__":
    unittest.main()
