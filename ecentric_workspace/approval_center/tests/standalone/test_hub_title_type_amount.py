# Copyright (c) 2026, eCentric and contributors
"""Bang "Tat ca yeu cau": tieu de that, loai doc duoc, va cot chi phi (09/09, Hoan).

Truoc do bang khong he lay tieu de phieu: cot "Tieu de" hien approval_title cua LOAI
("Payment Request") va cot "Loai" hien MA loai ("PAYMENT_REQUEST"). Ca trang 15 dong giong
het nhau nen khong phan biet duoc phieu nao voi phieu nao.

Bo test giu bon dieu:
  1. Cot Tieu de doc `r.title` (tieu de that), Cot Loai doc `r.type` (nhan nguoi doc duoc).
     KHONG con dong nao hien `r.approval_type` - do la MA, khong phai chu.
  2. Moi DocType trong AMOUNT_FIELDS phai co THAT truong do. Doi ten truong ma quen sua map
     thi cot Chi phi im lang trong rong, khong ai biet.
  3. Doc theo LO - mot truy van cho moi DocType, khong phai moi dong mot truy van.
  4. Mot form loi khong duoc lam trang ca bang.
"""
import ast
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "reporting")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_BSUM = os.path.join(_ROOT, "approval_center", "reporting", "business_summary.py")
_HUB = os.path.join(_ROOT, "approval_center", "ui", "all_requests", "main_section.html")
_DOCTYPE_DIR = os.path.join(_ROOT, "approval_center", "doctype")


def _read(p):
    return io.open(p, encoding="utf-8").read()


def _amount_fields():
    for node in ast.walk(ast.parse(_read(_BSUM))):
        if (isinstance(node, ast.Assign) and node.targets
                and getattr(node.targets[0], "id", None) == "AMOUNT_FIELDS"):
            return ast.literal_eval(node.value)
    raise AssertionError("khong doc duoc AMOUNT_FIELDS")


def _doctype_fields(doctype):
    slug = doctype.lower().replace(" ", "_")
    p = os.path.join(_DOCTYPE_DIR, slug, slug + ".json")
    if not os.path.isfile(p):
        return None
    doc = json.loads(_read(p))
    return {f.get("fieldname") for f in doc.get("fields", [])}


class TestMapSoTien(unittest.TestCase):
    def test_moi_truong_trong_map_deu_co_that(self):
        for dt, (amt, cur) in _amount_fields().items():
            fields = _doctype_fields(dt)
            self.assertIsNotNone(fields, "khong thay file DocType cua %s" % dt)
            self.assertIn(amt, fields, "%s: khong co truong '%s'" % (dt, amt))
            if cur:
                self.assertIn(cur, fields, "%s: khong co truong tien te '%s'" % (dt, cur))

    def test_moi_doctype_deu_co_request_title(self):
        for dt in _amount_fields():
            self.assertIn("request_title", _doctype_fields(dt), "%s thieu request_title" % dt)


def _load_bsum(rows_by_dt, raise_for=None):
    """Nap business_summary voi frappe gia; dem so lan truy van de chac la doc THEO LO."""
    calls = {"get_all": 0, "errors": []}
    frappe = types.ModuleType("frappe")

    class _Meta(object):
        def __init__(self, fields):
            self._f = fields

        def has_field(self, f):
            return f in self._f

    def get_meta(dt):
        return _Meta({"request_title", "payment_amount", "requested_amount", "currency",
                      "contract_value"})

    def get_all(dt, filters=None, fields=None, **kw):
        calls["get_all"] += 1
        if raise_for and dt in raise_for:
            raise RuntimeError("hong")
        return [dict(r) for r in rows_by_dt.get(dt, [])]

    frappe.get_meta = get_meta
    frappe.get_all = get_all
    frappe.log_error = lambda msg, title=None: calls["errors"].append(title)
    frappe.get_traceback = lambda: "TB"
    # KHONG go frappe gia ngay o day: `fetch()` chi `import frappe` LUC CHAY, nen phai de
    # module gia con trong sys.modules cho toi khi test goi xong (test tu don o tearDown).
    sys.modules["frappe"] = frappe
    ns = {"__name__": "bsum"}
    exec(compile(_read(_BSUM), _BSUM, "exec"), ns)
    return ns, calls


class TestDocTheoLo(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("frappe", None)

    VIEWS = [
        {"name": "APR-1", "reference_doctype": "EC Payment Request", "reference_name": "P1"},
        {"name": "APR-2", "reference_doctype": "EC Payment Request", "reference_name": "P2"},
        {"name": "APR-3", "reference_doctype": "EC AI Topup Request", "reference_name": "A1"},
        {"name": "APR-4", "reference_doctype": "EC Leave Request", "reference_name": "L1"},
    ]

    def test_mot_truy_van_moi_doctype(self):
        ns, calls = _load_bsum({
            "EC Payment Request": [{"name": "P1", "request_title": "Tra tien A", "payment_amount": 1000},
                                   {"name": "P2", "request_title": "Tra tien B", "payment_amount": 2000}],
            "EC AI Topup Request": [{"name": "A1", "request_title": "Nap AI", "requested_amount": 250,
                                     "currency": "USD"}],
            "EC Leave Request": [{"name": "L1", "request_title": "Nghi phep"}]})
        views = [dict(v) for v in self.VIEWS]
        ns["apply"](views)
        self.assertEqual(calls["get_all"], 3, "phai doc theo LO: 1 truy van moi DocType (3 loai)")
        self.assertEqual(views[0]["title"], "Tra tien A")
        self.assertEqual(views[0]["amount"], 1000)
        self.assertEqual(views[2]["currency"], "USD")

    def test_form_khong_co_tien_thi_de_TRONG_khong_phai_0(self):
        ns, _c = _load_bsum({"EC Leave Request": [{"name": "L1", "request_title": "Nghi phep"}]})
        views = [{"name": "APR-4", "reference_doctype": "EC Leave Request", "reference_name": "L1"}]
        ns["apply"](views)
        self.assertEqual(views[0]["title"], "Nghi phep")
        self.assertIsNone(views[0]["amount"], "trong va 0 la hai chuyen khac nhau")

    def test_mot_form_loi_khong_lam_trang_ca_bang(self):
        ns, calls = _load_bsum(
            {"EC Payment Request": [{"name": "P1", "request_title": "Tra tien A", "payment_amount": 1}]},
            raise_for={"EC AI Topup Request"})
        views = [dict(v) for v in self.VIEWS[:3]]
        ns["apply"](views)
        self.assertEqual(views[0]["title"], "Tra tien A", "form con lai van phai co du lieu")
        self.assertTrue(calls["errors"], "phai log loi thay vi nem ra ngoai")


class TestGiaoDien(unittest.TestCase):
    def test_cot_tieu_de_doc_title_cot_loai_doc_nhan(self):
        src = _read(_HUB)
        self.assertIn("cell(r.title||r.type)", src, "cot Tieu de phai doc r.title")
        self.assertNotIn("cell(r.approval_type)", src,
                         "khong duoc hien MA loai (PAYMENT_REQUEST) cho nguoi dung doc")

    def test_co_cot_chi_phi_va_dung_so_cot(self):
        src = _read(_HUB)
        self.assertIn('["Chi phí",', src)
        i = src.index("var COLS=[")
        cols_src = src[i: src.index("];", i)]
        n_cols = cols_src.count('["')
        body = src[src.index("var body=rows.map"):]
        body = body[:body.index("</tr>")]
        n_cells = body.count("+cell(")
        self.assertEqual(n_cols, n_cells,
                         "so cot tieu de (%d) phai bang so o trong mot dong (%d)" % (n_cols, n_cells))

    def test_doi_khoa_be_rong_cot_khi_them_cot(self):
        """Be rong luu theo VI TRI cot; giu khoa cu thi cot moi lam lech het."""
        self.assertIn('COLW_KEY="ec_apl_colw_v2"', _read(_HUB))

    def test_tien_te_khac_VND_thi_hien_ma(self):
        src = _read(_HUB)
        self.assertIn("function fmtMoney(", src)
        blk = src[src.index("function fmtMoney("):]
        blk = blk[:blk.index("function render(")]
        self.assertIn('"VND"', blk, "phai bo qua VND va hien ma cho ngoai te")


if __name__ == "__main__":
    unittest.main(verbosity=2)
