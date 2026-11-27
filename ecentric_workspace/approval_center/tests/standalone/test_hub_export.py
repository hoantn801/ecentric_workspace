# Copyright (c) 2026, eCentric and contributors
"""Nut "Excel" / "CSV" cua hub /approvals/all-requests (reporting.hub_export, 27/11/2026).

Bon dieu, moi dieu la mot cach that de ro du lieu:

  1. Tep phai di qua DUNG truy van cua bang hub. Kiem bang cach chay api.list_requests va
     hub_export.export voi CUNG tham so tren code THAT (api, scope, privacy, queries) va so
     SQL + tham so ma ca hai gui xuong DB: phai trung nhau tung ky tu (tru LIMIT).
  2. Tab + user do SERVER dat. Client gui `_me`, `box`, `_search_refs` long trong filters ->
     bi bo; `_me` luon la session user.
  3. Phieu rieng tu: dieu kien privacy.scope_sql (code THAT) co trong SQL cua tep, ca voi admin.
  4. Tep chi chua cot cua bang (khong truong nghiep vu nao khac), co tran dong (nem loi, khong
     cat bot), ghi vet TRUOC khi giao tep, chong cong thuc, ten tep dung mau.

Site-free: `frappe` gia; code reporting / privacy / all_list la code THAT.
"""
import ast
import datetime
import io
import json
import os
import re
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.abspath(os.path.join(_HERE, "..", ".."))
_ROOT = os.path.abspath(os.path.join(_AC, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_P = "ecentric_workspace.approval_center."


def _src(*p):
    with io.open(os.path.join(_AC, *p), encoding="utf-8") as fh:
        return fh.read()


def _dat(ten, mod):
    sys.modules[ten] = mod
    cha, _, la = ten.rpartition(".")
    if cha and sys.modules.get(cha) is not None:
        setattr(sys.modules[cha], la, mod)


class _Throw(Exception):
    pass


def _the_gioi(user="ketoan@e.c", roles=("Employee",), private=("OFFER_PRIVATE",),
              approver=False, rows=None, count=None):
    """Dung frappe gia + nap code THAT. Tra ve (modules, ghi)."""
    ghi = {"sql": [], "vet": [], "throw": [], "log": []}
    fr = types.ModuleType("frappe")
    fr.session = types.SimpleNamespace(user=user)
    fr.local = types.SimpleNamespace()
    fr.response = {}
    fr._ = lambda s: s
    fr.PermissionError = type("PermissionError", (Exception,), {})

    def _throw(msg, *a, **k):
        ghi["throw"].append(msg)
        raise _Throw(msg)
    fr.throw = _throw
    fr.log_error = lambda *a, **k: ghi["log"].append(a)
    fr.get_traceback = lambda: ""
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr.get_roles = lambda u=None: list(roles)
    fr.get_meta = lambda dt: types.SimpleNamespace(has_field=lambda f: f == "manager_email")

    def _get_all(dt, filters=None, fields=None, pluck=None, **k):
        if dt == "EC Approval Type" and (filters or {}).get("private") == 1:
            return list(private)
        return []
    fr.get_all = _get_all

    du_lieu = {"rows": rows, "count": count}

    def _sql(sql, params=None, as_dict=False, **k):
        ghi["sql"].append((sql, dict(params or {})))
        if "COUNT(*)" in sql:
            return [{"c": du_lieu["count"] if du_lieu["count"] is not None else len(du_lieu["rows"] or [])}]
        if "LIMIT %(_start)s" in sql:
            return [dict(r) for r in (du_lieu["rows"] or [])]
        return []
    fr.db = types.SimpleNamespace(
        sql=_sql, has_column=lambda dt, c: True,
        exists=lambda dt, f=None: bool(approver) if dt == "EC Approval Request Approver" else False,
        get_value=lambda *a, **k: "approvals-all-requests")

    class _Doc(dict):
        flags = types.SimpleNamespace()

        def insert(self, **k):
            ghi["vet"].append(dict(self, _ignore_links=getattr(self.flags, "ignore_links", None)))
            return self
    fr.get_doc = lambda d: _Doc(d)
    ut = types.ModuleType("frappe.utils")
    ut.get_first_day = lambda d: "2026-11-01"
    ut.get_last_day = lambda d: "2026-11-30"
    ut.nowdate = lambda: "2026-11-27"
    ut.add_to_date = lambda *a, **k: None
    ut.now_datetime = lambda: datetime.datetime(2026, 11, 27, 9, 30)
    ut.get_datetime = lambda s: s
    fr.utils = ut
    _dat("frappe", fr)
    _dat("frappe.utils", ut)

    # Phu thuoc nang cua queries (registry, quyen xu ly, cong ky) -> ban gia rong, fail-closed.
    reg = types.ModuleType(_P + "shared.registry")
    reg.APPROVAL_DEFINITIONS = {}
    reg.BUSINESS_DOCTYPE_DEFINITIONS = {}
    _dat(_P + "shared.registry", reg)
    perm = types.ModuleType(_P + "shared.workflow.permissions")
    perm.fulfilled_approval_types = lambda u: []
    perm.is_eligible_fulfiller_without_todo = lambda u, c: False
    _dat(_P + "shared.workflow.permissions", perm)
    ew = types.ModuleType(_P + "shared.requests.esign_wait")
    ew.waiting_requests = lambda me, m: set()
    _dat(_P + "shared.requests.esign_wait", ew)

    import importlib
    m = {}
    # service gia (cai TRUOC khi nap api - api import service o dau module): DUNG queries THAT
    # (cung SQL voi service that), tra dong tho.
    svc = types.ModuleType(_P + "reporting.service")

    def _list(scope, f, start=0, page_length=50, search=None):
        q = m["reporting.queries"]
        ghi.setdefault("svc", []).append({"f": dict(f), "start": start, "len": page_length,
                                          "search": search, "scope": scope})
        dong = q.fetch_requests_page(scope, f, start, page_length, search)
        tong = q.count_requests(scope, f, search)
        return {"rows": [dict(r) for r in dong], "total": tong, "start": start,
                "page_length": page_length}
    svc.list_requests = _list
    svc.my_drafts = lambda: []
    _dat(_P + "reporting.service", svc)
    m["reporting.service"] = svc
    for ten in ("reporting.status", "shared.workflow.privacy", "reporting.scope",
                "reporting.queries", "reporting.api", "reporting.business_summary",
                "shared.requests.all_list", "reporting.hub_export"):
        mod = importlib.import_module(_P + ten)
        m[ten] = importlib.reload(mod)
        _dat(_P + ten, m[ten])
    return m, ghi


class _Nen(unittest.TestCase):
    """Tra lai sys.modules nguyen trang sau moi bai (file nay nap lai code that voi frappe gia)."""

    def setUp(self):
        self._cu = dict(sys.modules)
        self._attrs = {}
        for ten, mod in list(sys.modules.items()):
            if ten.startswith("ecentric_workspace") and mod is not None:
                self._attrs[ten] = dict(vars(mod))

    def tearDown(self):
        for ten in list(sys.modules):
            # Chi go module CUA MINH vua nap (frappe gia, code app nap lai); thu vien ngoai
            # (openpyxl, numpy) giu nguyen - nap lai chung la canh bao + cham.
            if ten not in self._cu and (ten.startswith("ecentric_workspace") or ten.startswith("frappe")):
                sys.modules.pop(ten, None)
        sys.modules.update(self._cu)
        for ten, d in self._attrs.items():
            mod = sys.modules.get(ten)
            if mod is not None:
                vars(mod).clear()
                vars(mod).update(d)


def _bo_limit(sqls):
    out = []
    for sql, p in sqls:
        p = {k: v for k, v in p.items() if k not in ("_start", "_len")}
        out.append((re.sub(r"\s+", " ", sql), p))
    return out


def _chi_danh_sach(sqls):
    """Chi hai truy van cua danh sach (trang + dem) - bo truy van phu (cong ky...)."""
    return [x for x in sqls if "FROM `tabEC Approval Request` r" in x[0]
            and ("LIMIT %(_start)s" in x[0] or "COUNT(*)" in x[0])]


_LOC = {"department": "Finance - EC", "status": "Pending", "approval_type": "PAYMENT_REQUEST",
        "date_from": "2026-11-01", "date_to": "2026-11-30", "category": "Tài chính"}
_DONG = {"name": "EC-APR-1", "approval_type": "PAYMENT_REQUEST", "type_title": "Đề nghị thanh toán",
         "requested_by": "an@e.c", "requester_department": "Finance - EC",
         "submitted_at": "2026-11-20 09:15:00", "approval_status": "Pending", "current_level": 2,
         "current_level_name": "Kế toán duyệt", "reference_doctype": "EC Payment Request",
         "reference_name": "EC-PAYR-1"}


class TestCungTruyVanVoiBang(_Nen):
    def _ca_hai(self, box, filters, search, **kw):
        m, ghi = _the_gioi(rows=[_DONG], **kw)
        m["reporting.api"].list_requests(filters=json.dumps(filters), start=0, page_length=50,
                                         search=search, box=box)
        bang = _bo_limit(_chi_danh_sach(ghi["sql"]))
        ghi["sql"].clear()
        m["reporting.hub_export"].export(filters=json.dumps(filters), search=search, box=box)
        tep = _bo_limit(_chi_danh_sach(ghi["sql"]))
        return bang, tep, ghi, m

    def test_moi_tab_tep_trung_SQL_bang(self):
        for box in ("received", "sent", "fulfil", "watching", "all", None, "la-lung"):
            bang, tep, _g, _m = self._ca_hai(box, _LOC, "PAYR")
            self.assertTrue(bang, box)
            # Tep dem truoc (chan tran) roi moi doc -> co the them mot COUNT trung; so TAP truy van.
            def tap(xs):
                return {(sql, json.dumps(p, sort_keys=True, default=str)) for sql, p in xs}
            self.assertEqual(len(tap(bang)), 2, box)
            self.assertEqual(tap(bang), tap(tep),
                             "tab %s: tep KHONG di qua dung truy van cua bang" % box)

    def test_tab_dung_session_user_khong_tin_client(self):
        loc = dict(_LOC, _me="ceo@e.c", box="sent", _search_refs=["EC-PAYR-9"], _biz={"x": 1})
        _b, tep, _g, _m = self._ca_hai("received", loc, None)
        sql, p = tep[0]
        self.assertIn("va.approver = %(_me_recv)s", sql, "tab Da nhan phai ap dieu kien")
        self.assertEqual(p["_me_recv"], "ketoan@e.c", "_me phai la session user")
        self.assertNotIn("ceo@e.c", json.dumps(p), "_me client gui len KHONG duoc vao SQL")
        self.assertNotIn("_me_sent", p, "box client nhet trong filters khong duoc doi tab")
        self.assertFalse(any(k.startswith("sref_") for k in p), "_search_refs client bi bo")

    def test_bo_loc_ap_dung_dung(self):
        _b, tep, _g, _m = self._ca_hai("sent", _LOC, "PAYR")
        sql, p = tep[0]
        for khoa, gt in (("f_department", "Finance - EC"), ("f_status", "Pending"),
                         ("f_approval_type", "PAYMENT_REQUEST"), ("f_category", "Tài chính"),
                         ("_me_sent", "ketoan@e.c"), ("search", "%PAYR%")):
            self.assertEqual(p.get(khoa), gt, khoa)
        self.assertEqual(p["date_from"], "2026-11-01 00:00:00")
        self.assertEqual(p["date_to"], "2026-11-30 23:59:59")

    def test_pham_vi_nguoi_de_nghi(self):
        _b, tep, _g, _m = self._ca_hai("all", {}, None, private=())
        sql, p = tep[0]
        self.assertIn("r.requested_by = %(scope_user)s", sql)
        self.assertEqual(p["scope_user"], "ketoan@e.c")

    def test_phieu_rieng_tu_bi_loai_ca_voi_admin(self):
        for roles in (("Employee",), ("System Manager",)):
            _b, tep, _g, _m = self._ca_hai("all", {}, None, roles=roles)
            sql, p = tep[0]
            self.assertIn("r.approval_type NOT IN (%(priv_t_0)s)", sql, roles)
            self.assertEqual(p["priv_t_0"], "OFFER_PRIVATE")
            self.assertEqual(p["priv_user"], "ketoan@e.c")


def _dong_hub(**k):
    d = {"name": "EC-APR-7", "type": "Đề nghị thanh toán", "title": "Thanh toán CMC tháng 11",
         "amount": 1500000.0, "currency": "", "submitted_at": "2026-11-20 09:15:00.123456",
         "requester_info": {"name": "Nguyễn An", "user": "an@e.c"},
         "sent_to": [{"name": "Trần Bình", "user": "b@e.c"}, {"name": "", "user": "c@e.c"}],
         "department": "Finance - EC", "status": "Pending", "status_label": "Pending",
         "current_level": 2, "current_level_name": "Kế toán duyệt", "sla_breached": True,
         # truong KHONG duoc vao tep (khong co tren bang)
         "reference_name": "EC-PAYR-SECRET", "partner_signer_identity": "079912345678",
         "salary": 98765432, "extra": {"bank_account": "1903-555-777"},
         "detail_route": "/payment-request?id=EC-PAYR-SECRET"}
    d.update(k)
    return d


class TestTep(_Nen):
    def _xuat(self, hang, box="all", fmt="xlsx", count=None, **kw):
        m, ghi = _the_gioi(**kw)
        hx = m["reporting.hub_export"]
        goc = m["reporting.service"].list_requests

        def _list(scope, f, start=0, page_length=50, search=None):
            goc(scope, f, start, page_length, search)
            return {"rows": [dict(x) for x in hang], "total": count if count is not None else len(hang)}
        hx._service.list_requests = _list
        m["reporting.queries"].count_requests = lambda sc, f, s=None: count if count is not None else len(hang)
        import frappe
        frappe.response.clear()
        hx.export(filters="{}", box=box, fmt=fmt)
        return frappe.response, ghi, hx

    def test_vuot_tran_nem_loi_noi_ro_so(self):
        m, ghi = _the_gioi()
        hx = m["reporting.hub_export"]
        m["reporting.queries"].count_requests = lambda *a, **k: hx.EXPORT_MAX + 1
        with self.assertRaises(_Throw):
            hx.export(box="fulfil")
        self.assertIn(str(hx.EXPORT_MAX + 1), ghi["throw"][0])
        self.assertIn(str(hx.EXPORT_MAX), ghi["throw"][0])
        self.assertEqual(ghi["vet"], [], "vuot tran thi khong ghi vet, khong tep")
        self.assertNotIn("filecontent", __import__("frappe").response)

    def test_tran_bang_tab_Tat_ca_cua_form(self):
        m, _g = _the_gioi()
        self.assertEqual(m["reporting.hub_export"].EXPORT_MAX, m["shared.requests.all_list"].EXPORT_MAX)
        self.assertEqual(m["reporting.hub_export"].EXPORT_MAX, 5000)

    def test_dem_lai_luc_doc_van_vuot_thi_nem(self):
        m, ghi = _the_gioi()
        hx = m["reporting.hub_export"]
        m["reporting.queries"].count_requests = lambda *a, **k: 10
        hx._service.list_requests = lambda *a, **k: {"rows": [_dong_hub()], "total": hx.EXPORT_MAX + 3}
        with self.assertRaises(_Throw):
            hx.export()
        self.assertEqual(ghi["vet"], [], "co phieu moi giua luc dem va luc doc: van khong cat bot")

    def test_doc_toi_da_dung_tran(self):
        _r, ghi, hx = self._xuat([_dong_hub()])
        self.assertEqual(ghi["svc"][-1]["len"], hx.EXPORT_MAX)
        self.assertEqual(ghi["svc"][-1]["start"], 0)

    def test_khong_co_dong_thi_bao_chu_khong_tep_rong(self):
        with self.assertRaises(_Throw):
            self._xuat([], count=0)

    def test_ghi_vet_TRUOC_khi_dung_tep(self):
        m, ghi = _the_gioi()
        hx = m["reporting.hub_export"]
        m["reporting.queries"].count_requests = lambda *a, **k: 1
        hx._service.list_requests = lambda *a, **k: {"rows": [_dong_hub()], "total": 1}
        thu_tu = []
        hx._ghi_vet = lambda *a, **k: thu_tu.append("vet")
        hx._xlsx = lambda *a, **k: (thu_tu.append("tep"), b"X")[1]
        hx.export()
        self.assertEqual(thu_tu, ["vet", "tep"])

    def test_vet_du_ai_tab_loc_so_dong(self):
        _r, ghi, _hx = self._xuat([_dong_hub(), _dong_hub(name="EC-APR-8")], box="watching")
        self.assertEqual(len(ghi["vet"]), 1)
        v = ghi["vet"][0]
        self.assertEqual((v["doctype"], v["comment_type"], v["reference_doctype"]),
                         ("Comment", "Info", "Web Page"))
        self.assertTrue(v["_ignore_links"])
        for chu in ("2 dòng", "tab watching", "phạm vi requester", "xlsx", "ketoan@e.c"):
            self.assertIn(chu, v["content"])

    def test_ten_tep_theo_tab(self):
        for box, slug in (("received", "da-nhan"), ("sent", "da-gui"), ("fulfil", "cho-toi-xu-ly"),
                          ("watching", "toi-theo-doi"), ("all", "tat-ca"), (None, "tat-ca"),
                          ("../x", "tat-ca")):
            r, _g, _hx = self._xuat([_dong_hub()], box=box)
            self.assertEqual(r["filename"], "tat-ca-yeu-cau_%s_20261127-0930.xlsx" % slug)
            self.assertEqual(r["type"], "binary")
        r, _g, _hx = self._xuat([_dong_hub()], fmt="csv")
        self.assertTrue(r["filename"].endswith(".csv"))
        r, _g, _hx = self._xuat([_dong_hub()], fmt="exe")
        self.assertTrue(r["filename"].endswith(".xlsx"), "dinh dang la -> xlsx")

    def test_cot_giong_bang_hub(self):
        m, _g = _the_gioi()
        tieu_de = [c for c, _k in m["reporting.hub_export"].COLUMNS]
        html = _src("ui", "all_requests", "main_section.html")
        cols = re.findall(r'\["([^"]+)",\d+\]', html[html.index("var COLS="):][:400])
        self.assertEqual(len(cols), 10)
        vi_tri = [tieu_de.index(c) for c in cols]
        self.assertEqual(vi_tri, sorted(vi_tri), "cot tep phai theo dung thu tu bang hub")

    def test_xlsx_so_that_ngay_that_khong_cong_thuc(self):
        from openpyxl import load_workbook
        hang = [_dong_hub(title="=HYPERLINK(\"http://x\",\"bam\")"),
                _dong_hub(name="EC-APR-9", amount=None, title="", type="Nghỉ phép",
                          status="Completed", status_label="Completed", current_level=0,
                          current_level_name="", sla_breached=False),
                _dong_hub(name="EC-APR-10", amount=120.5, currency="usd",
                          fulfillment_status="Assigned"),
                _dong_hub(name="EC-APR-11", current_level_name="Level 3", current_level=3,
                          fulfillment_status="In Progress", fulfillment_owner="op@e.c")]
        r, _g, _hx = self._xuat(hang)
        ws = load_workbook(io.BytesIO(r["filecontent"])).active
        dau = [c.value for c in ws[1]]
        self.assertEqual(dau[:5], ["Ngày gửi", "Mã", "Tiêu đề", "Loại", "Chi phí"])
        a2 = ws["A2"]
        self.assertEqual(a2.value, datetime.datetime(2026, 11, 20, 9, 15))
        self.assertEqual(a2.number_format, "dd/mm/yyyy hh:mm")
        self.assertEqual(ws["E2"].value, 1500000)
        self.assertEqual(ws["E2"].number_format, "#,##0")
        self.assertEqual(ws["F2"].value, "VND")
        self.assertEqual(ws["C2"].data_type, "s", "tieu de '=' KHONG duoc thanh cong thuc")
        self.assertEqual(ws["G2"].value, "Nguyễn An")
        self.assertEqual(ws["H2"].value, "Trần Bình, c@e.c")
        self.assertEqual(ws["J2"].value, "Cấp 2 · Kế toán duyệt")
        self.assertEqual(ws["K2"].value, "Chờ duyệt")
        self.assertEqual(ws["L2"].value, "Có")
        # dong 3: khong tien -> o trong (KHONG phai 0), tieu de rong -> lay loai
        self.assertIsNone(ws["E3"].value)
        self.assertIsNone(ws["F3"].value)
        self.assertEqual(ws["C3"].value, "Nghỉ phép")
        self.assertEqual(ws["K3"].value, "Hoàn tất")
        self.assertIsNone(ws["J3"].value)
        # dong 4: tien te rieng, buoc xu ly ghi de cap + trang thai
        self.assertEqual((ws["E4"].value, ws["E4"].number_format, ws["F4"].value), (120.5, "#,##0.00", "USD"))
        self.assertEqual((ws["J4"].value, ws["K4"].value), ("Chờ nhận xử lý", "Chờ nhận xử lý"))
        self.assertEqual((ws["J5"].value, ws["K5"].value), ("Đang xử lý", "Đang xử lý (op@e.c)"))
        self.assertEqual(ws.freeze_panes, "A2")
        self.assertTrue(ws.auto_filter.ref)
        self.assertEqual(ws.max_row, 5)

    def test_csv_bom_iso_va_chong_cong_thuc(self):
        r, _g, _hx = self._xuat([_dong_hub(title="=1+1"), _dong_hub(title="-SUM(A1)", amount=0)], fmt="csv")
        b = r["filecontent"]
        self.assertTrue(b.startswith(b"\xef\xbb\xbf"))
        t = b.decode("utf-8-sig")
        self.assertIn("2026-11-20 09:15", t)
        self.assertIn("'=1+1", t)
        self.assertIn("'-SUM(A1)", t)
        self.assertIn(",1500000,", t)
        self.assertIn(",0,", t, "0 la mot so that, khong duoc thanh o trong")

    def test_khong_lo_truong_ngoai_bang(self):
        for fmt in ("csv", "xlsx"):
            r, _g, _hx = self._xuat([_dong_hub()], fmt=fmt)
            raw = r["filecontent"]
            if fmt == "xlsx":
                from openpyxl import load_workbook
                ws = load_workbook(io.BytesIO(raw)).active
                raw = json.dumps([[c.value for c in row] for row in ws.iter_rows()],
                                 default=str, ensure_ascii=False).encode("utf-8")
            for bi_mat in (b"079912345678", b"98765432", b"1903-555-777", b"EC-PAYR-SECRET"):
                self.assertNotIn(bi_mat, raw, "%s: lo %r" % (fmt, bi_mat))


class TestNguonCode(unittest.TestCase):
    def test_export_requests_la_POST(self):
        src = _src("reporting", "api.py")
        i = src.index("def export_requests(")
        self.assertIn('@frappe.whitelist(methods=["POST"])', src[max(0, i - 400):i])

    def test_khong_nhan_tham_so_user(self):
        t = ast.parse(_src("reporting", "api.py"))
        fn = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == "export_requests")
        self.assertEqual([a.arg for a in fn.args.args], ["filters", "search", "box", "fmt"])

    def test_list_requests_va_export_cung_mot_ham_loc(self):
        src = _src("reporting", "api.py")
        than = src[src.index("def list_requests("):src.index("def export_requests(")]
        self.assertIn("hub_filters(filters, box)", than)
        self.assertIn("_rapi.hub_filters(filters, box)", _src("reporting", "hub_export.py"))

    def test_luat_chan_export_giong_tab_Tat_ca(self):
        """Neu ai them luat chan export (has_permission/can_export...) vao tab "Tat ca" cua form
        thi hub phai co cung luat - va nguoc lai. Chi xet LOI GOI that (AST), khong xet docstring."""
        def goi(src):
            out = set()
            for n in ast.walk(ast.parse(src)):
                if isinstance(n, ast.Call):
                    f = n.func
                    ten = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                    if ten in ("has_permission", "can_export", "get_permissions", "has_perm"):
                        out.add(ten)
            return out
        self.assertEqual(goi(_src("shared", "requests", "all_list.py")),
                         goi(_src("reporting", "hub_export.py")))


if __name__ == "__main__":
    unittest.main()
