# Copyright (c) 2026, eCentric and contributors
"""Tab "Tat ca" (16/10/2026): sap xep + loc theo truong nghiep vu o TANG TRUY VAN.

Ba dieu duoc giu o day, moi dieu la mot cach that de bien mot o loc thanh lo ho:
  1. ORDER BY chi sinh tu dac ta noi bo `_sort` ({"key" in SORT_KINDS, "dir" in SORT_DIRS,
     ...}). Dac ta la / thieu -> mac dinh cu (moi -> cu).
  2. Ten DocType / ten truong khong the di bang tham so SQL, nen phai qua regex truoc khi
     vao dau backtick; GIA TRI thi luon la %(tham_so)s.
  3. Dieu kien nghiep vu duoc AND cung `scope_predicate` - loc THU HEP, khong noi rong.
Kem: hop dong `all_tab_columns` / `all_tab_filters` tren ApprovalDefinition, va khai bao
that cua Contract Review / Payment Request tro dung truong co tren DocType.

Site-free: frappe va scope bi thay bang ban gia; queries.py duoc exec tu nguon.
"""
import ast
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.abspath(os.path.join(_HERE, "..", ".."))
_APP = os.path.abspath(os.path.join(_AC, ".."))
_DONG_SCOPE = "from ecentric_workspace.approval_center.reporting import scope as _scope"


def _doc(*p):
    with io.open(os.path.join(*p), encoding="utf-8") as fh:
        return fh.read()


def _nap_queries():
    """Exec queries.py voi frappe + scope gia. Tra ve (module, danh sach SQL da chay)."""
    ghi = []
    fr = types.ModuleType("frappe")
    fr.db = types.SimpleNamespace(
        sql=lambda q, p=None, **k: (ghi.append((q, dict(p or {}))), [{"c": 0}])[1])
    sc = types.SimpleNamespace(
        scope_predicate=lambda s: ("r.requested_by = %(u)s", {"u": "u@e.c"}))
    src = _doc(_AC, "reporting", "queries.py")
    assert _DONG_SCOPE in src, "dong import scope doi ten - sua bo nap cua test"
    m = types.ModuleType("_queries_under_test")
    m._scope = sc
    cu = sys.modules.get("frappe")
    sys.modules["frappe"] = fr
    try:
        exec(compile(src.replace(_DONG_SCOPE, ""), "queries.py", "exec"), m.__dict__)
    finally:
        if cu is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = cu
    return m, ghi


_BIZ = {"doctype": "EC Contract Review Request", "amount_field": "contract_value",
        "eq": (("brand", "ACME' OR 1=1 --"),), "amount_min": 1500000.0, "amount_max": None}
_MAC_DINH = "COALESCE(r.submitted_at, r.creation) DESC"


def _sx(key, huong, **k):
    return dict({"key": key, "dir": huong}, **k)


class TestSapXepTrang(unittest.TestCase):
    def setUp(self):
        self.q, _ = _nap_queries()

    def test_khong_khoa_thi_y_nhu_cu(self):
        self.assertEqual(self.q._order_by({}), _MAC_DINH)
        self.assertEqual(self.q._order_by(None), _MAC_DINH)
        self.assertEqual(self.q._order_by({"_sort": _sx("submitted", "desc")}), _MAC_DINH)

    def test_dac_ta_la_ve_mac_dinh(self):
        for xau in ("newest", "oldest", "amount_desc", "r.name; DROP TABLE x", 1, None,
                    ("oldest",), {}, _sx("SUBMITTED", "asc"), _sx("submitted", "ASC"),
                    _sx("submitted", "asc; DROP"), _sx("r.name", "asc"), _sx("biz", "up"),
                    {"key": "biz", "field": "contract_value"}):
            self.assertEqual(self.q._order_by({"_sort": xau, "_biz": _BIZ}, {}), _MAC_DINH,
                             repr(xau))

    def test_cu_den_moi(self):
        self.assertTrue(self.q._order_by({"_sort": _sx("submitted", "asc")}).startswith(
            "COALESCE(r.submitted_at, r.creation) ASC"))

    def test_theo_so_tien_can_dac_ta_nghiep_vu(self):
        s = _sx("biz", "desc", field="contract_value", text=False)
        self.assertEqual(self.q._order_by({"_sort": s}), _MAC_DINH,
                         "khong biet DocType nghiep vu thi khong duoc doan")
        o = self.q._order_by({"_sort": s, "_biz": _BIZ})
        sub = ("(SELECT b.`contract_value` FROM `tabEC Contract Review Request` b "
               "WHERE b.name = r.reference_name)")
        self.assertTrue(o.startswith(sub + " IS NULL, " + sub + " DESC"), o)
        self.assertNotIn("= ''", o, "truong so: 0 la so tien that, chi NULL xuong cuoi")
        self.assertIn(sub + " ASC", self.q._order_by(
            {"_sort": _sx("biz", "asc", field="contract_value"), "_biz": _BIZ}))

    def test_truong_chu_rong_cung_xuong_cuoi_ca_hai_chieu(self):
        sub = ("(SELECT b.`request_title` FROM `tabEC Contract Review Request` b "
               "WHERE b.name = r.reference_name)")
        for huong in ("asc", "desc"):
            o = self.q._order_by({"_sort": _sx("biz", huong, field="request_title", text=True),
                                  "_biz": _BIZ})
            self.assertTrue(o.startswith("(%s IS NULL OR %s = ''), %s %s" % (
                sub, sub, sub, huong.upper())), o)

    def test_trang_thai_theo_thu_tu_di_bang_tham_so(self):
        p = {}
        o = self.q._order_by({"_sort": _sx("status", "desc", order=[
            "Information Required", "Pending', 1) --", "Approved"])}, p)
        self.assertTrue(o.startswith(
            "FIELD(r.approval_status, %(so_st0)s, %(so_st1)s, %(so_st2)s) DESC"), o)
        self.assertNotIn("Pending", o, "gia tri trang thai KHONG duoc noi vao SQL")
        self.assertEqual(p["so_st1"], "Pending', 1) --")
        self.assertTrue(self.q._order_by({"_sort": _sx("status", "asc")}, {}).startswith(
            "r.approval_status ASC"))
        # Khong co params thi khong the tham so hoa -> roi ve cot tho, khong noi chuoi.
        self.assertTrue(self.q._order_by({"_sort": _sx("status", "asc", order=["X'"])})
                        .startswith("r.approval_status ASC"))

    def test_dinh_danh_ban_bi_tu_choi(self):
        for dt, f in (("X` b; DROP TABLE y; --", "contract_value"),
                      ("EC Contract Review Request", "contract_value` DESC, (SELECT 1)"),
                      ("EC Contract Review Request", "Contract_Value"),
                      ("EC Contract Review Request", "name; DROP")):
            with self.assertRaises(ValueError):
                self.q._order_by({"_sort": _sx("biz", "desc", field=f),
                                  "_biz": {"doctype": dt, "amount_field": "contract_value"}})


class TestDieuKienNghiepVu(unittest.TestCase):
    def setUp(self):
        self.q, self.ghi = _nap_queries()

    def test_gia_tri_di_bang_tham_so(self):
        p = {}
        c = self.q._biz_clause({"_biz": _BIZ}, p)
        self.assertNotIn("ACME", c, "gia tri client KHONG duoc noi vao SQL")
        self.assertNotIn("1500000", c)
        self.assertIn("b.`brand` = %(bz_eq0)s", c)
        self.assertIn("b.`contract_value` >= %(bz_amount_min)s", c)
        self.assertNotIn("<=", c, "dau con lai bo trong thi khong them dieu kien")
        self.assertEqual(p["bz_eq0"], "ACME' OR 1=1 --")
        self.assertEqual(p["bz_amount_min"], 1500000.0)
        self.assertIn("r.reference_doctype = %(bz_dt)s", c)
        self.assertTrue(c.startswith("EXISTS (") and c.endswith(")"))

    def test_nhieu_gia_tri_IN_moi_gia_tri_mot_tham_so(self):
        p = {}
        c = self.q._biz_clause({"_biz": dict(_BIZ, eq=(), amount_min=None, **{"in": (
            ("brand", ("ACME", "B') OR 1=1 --")), ("contract_type", ("Sales",)),
            ("brand", ()))})}, p)
        self.assertIn("b.`brand` IN (%(bz_in0_0)s, %(bz_in0_1)s)", c)
        self.assertIn("b.`contract_type` IN (%(bz_in1_0)s)", c)
        self.assertNotIn("ACME", c)
        self.assertNotIn("OR 1=1", c)
        self.assertEqual(p["bz_in0_1"], "B') OR 1=1 --")
        self.assertEqual(c.count(" IN ("), 2, "danh sach rong khong duoc sinh 'IN ()'")

    def test_IN_co_tran(self):
        p = {}
        self.q._biz_clause({"_biz": dict(_BIZ, eq=(), **{"in": (
            ("brand", tuple("v%d" % i for i in range(self.q.IN_MAX + 30))),)})}, p)
        self.assertEqual(len([k for k in p if k.startswith("bz_in")]), self.q.IN_MAX)

    def test_dinh_danh_ban_trong_IN_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            self.q._biz_clause({"_biz": dict(_BIZ, **{"in": (("brand`) OR (1", ("x",)),)})}, {})

    def test_loc_co_ban_nhieu_gia_tri_thanh_IN(self):
        p = {}
        fr = self.q._non_date_filters({"department": ["Ops", "x') OR 1=1 --"],
                                       "status": "Pending", "requester": [],
                                       "approval_type": "CONTRACT_REVIEW"}, p)
        self.assertIn("r.requester_department IN (%(f_department_0)s, %(f_department_1)s)", fr)
        self.assertIn("r.approval_status = %(f_status)s", fr, "mot gia tri giu dang cu")
        self.assertFalse(any("requested_by" in x for x in fr), "danh sach rong = khong loc")
        self.assertEqual(p["f_department_1"], "x') OR 1=1 --")
        self.assertFalse(any("OR 1=1" in x for x in fr))

    def test_khong_dieu_kien_thi_khong_them_gi(self):
        self.assertIsNone(self.q._biz_clause({}, {}))
        self.assertIsNone(self.q._biz_clause({"_biz": dict(_BIZ, eq=(), amount_min=None)}, {}))

    def test_dinh_danh_ban_trong_dieu_kien_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            self.q._biz_clause({"_biz": dict(_BIZ, eq=(("brand` = 1 OR 1", "x"),))}, {})

    def test_moi_truy_van_trang_va_dem_deu_AND_pham_vi(self):
        f = {"approval_type": "CONTRACT_REVIEW", "_biz": _BIZ,
             "_sort": _sx("biz", "asc", field="contract_value")}
        self.q.fetch_requests_page({"mode": "requester"}, f, 0, 50)
        self.q.count_requests({"mode": "requester"}, f)
        self.assertEqual(len(self.ghi), 2)
        for sql, p in self.ghi:
            w = sql.split(" WHERE ", 1)[1]
            self.assertIn("r.requested_by = %(u)s AND", w, "thieu scope_predicate")
            self.assertIn(" AND EXISTS (SELECT 1 FROM `tabEC Contract Review Request` b", w)
            self.assertEqual(p["bz_eq0"], "ACME' OR 1=1 --")
        self.assertIn("ORDER BY (SELECT b.`contract_value`", self.ghi[0][0])

    def test_sap_trang_thai_tham_so_nam_trong_cung_truy_van(self):
        f = {"approval_type": "CONTRACT_REVIEW",
             "_sort": _sx("status", "asc", order=["Pending", "Approved"])}
        self.q.fetch_requests_page({"mode": "requester"}, f, 0, 50)
        sql, p = self.ghi[-1]
        self.assertIn("ORDER BY FIELD(r.approval_status, %(so_st0)s, %(so_st1)s) ASC", sql)
        self.assertEqual((p["so_st0"], p["so_st1"]), ("Pending", "Approved"))
        self.assertIn("r.requested_by = %(u)s AND", sql.split(" WHERE ", 1)[1])

    def test_hub_khong_dat_biz_thi_sql_y_nhu_cu(self):
        self.q.fetch_requests_page({"mode": "admin"}, {}, 0, 10)
        sql = self.ghi[-1][0]
        self.assertNotIn("EXISTS", sql)
        self.assertIn("ORDER BY " + _MAC_DINH + " LIMIT", sql)


class TestHopDongDinhNghia(unittest.TestCase):
    """`all_tab_columns` / `all_tab_filters` sai thi gay LUC NAP REGISTRY."""

    def setUp(self):
        fk = types.ModuleType("frappe")
        cu = sys.modules.get("frappe")
        sys.modules["frappe"] = fk
        try:
            self.m = types.ModuleType("_contracts_all_tab")
            exec(compile(_doc(_AC, "shared", "requests", "contracts.py"), "contracts.py", "exec"),
                 self.m.__dict__)
        finally:
            if cu is None:
                sys.modules.pop("frappe", None)
            else:
                sys.modules["frappe"] = cu

    def _d(self, **kw):
        import dataclasses
        a = {f.name: () for f in dataclasses.fields(self.m.ApprovalDefinition)
             if f.default is dataclasses.MISSING}
        a.update(code="X", business_doctype="EC X", options_provider=lambda: {},
                 submitter=lambda n: n, resubmitter=lambda n, c: {}, title_builder=None)
        a.update(kw)
        return self.m.ApprovalDefinition(**a)

    def test_mac_dinh_rong_hop_le(self):
        d = self._d()
        self.assertEqual((d.all_tab_columns, d.all_tab_filters), ((), ()))
        self.m.validate_definition(d)

    def test_khai_dung_thi_qua(self):
        self.m.validate_definition(self._d(
            all_tab_columns=(("Brand", "brand", "text"), ("Giá trị", "contract_value", "money")),
            all_tab_filters=("brand",)))

    def test_khai_sai_bi_tu_choi(self):
        for kw in ({"all_tab_columns": (("Brand", "brand", "html"),)},
                   {"all_tab_columns": (("Brand", "brand` OR 1", "text"),)},
                   {"all_tab_columns": (("", "brand", "text"),)},
                   {"all_tab_columns": (("Brand", "brand"),)},
                   {"all_tab_columns": [("Brand", "brand", "text")]},
                   {"all_tab_filters": ("Brand",)},
                   {"all_tab_filters": ["brand"]}):
            with self.assertRaises(ValueError, msg=repr(kw)):
                self.m.validate_definition(self._d(**kw))


def _khai_bao(rel, ten):
    """Doc gia tri literal cua keyword `ten` trong file definition (khong can frappe)."""
    tree = ast.parse(_doc(_AC, "features", *rel.split("/")))
    for n in ast.walk(tree):
        if isinstance(n, ast.keyword) and n.arg == ten:
            return ast.literal_eval(n.value)
    return None


def _truong_doctype(json_rel, dt):
    d = json.loads(_doc(_AC, "doctype", *json_rel.split("/")))
    out = {f["fieldname"]: f["fieldtype"] for f in d["fields"]}
    for f in json.loads(_doc(_APP, "fixtures", "custom_field.json")):
        if f.get("dt") == dt:
            out[f["fieldname"]] = f["fieldtype"]
    return out


class TestKhaiBaoThat(unittest.TestCase):
    def test_contract_review(self):
        rel = "contract_review/domain/definition.py"
        cot = _khai_bao(rel, "all_tab_columns")
        loc = _khai_bao(rel, "all_tab_filters")
        self.assertEqual([c[1] for c in cot], ["brand", "contract_type", "contract_value"])
        self.assertEqual(cot[0][0], "Legal entity / Brand")
        self.assertEqual(set(loc), {"brand", "contract_type"})
        co = _truong_doctype("ec_contract_review_request/ec_contract_review_request.json",
                             "EC Contract Review Request")
        for _n, fn, kieu in cot:
            self.assertIn(fn, co, "khai truong khong co tren DocType: " + fn)
        self.assertEqual(co["contract_value"], "Currency")
        for fn in loc:
            self.assertIn(fn, co)

    def test_payment_request(self):
        rel = "payment_request/domain/definition.py"
        cot = _khai_bao(rel, "all_tab_columns") or ()
        loc = _khai_bao(rel, "all_tab_filters") or ()
        co = _truong_doctype("ec_payment_request/ec_payment_request.json", "EC Payment Request")
        for fn in [c[1] for c in cot] + list(loc):
            self.assertIn(fn, co, "khai truong khong co tren DocType: " + fn)
        # So tai khoan / ngan hang KHONG duoc thanh cot hay o loc cua tab "Tat ca".
        for nhay_cam in ("bank_account_number", "account_bank"):
            self.assertNotIn(nhay_cam, [c[1] for c in cot] + list(loc))


if __name__ == "__main__":
    unittest.main()
