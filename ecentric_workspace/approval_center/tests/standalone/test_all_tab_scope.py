# Copyright (c) 2026, eCentric and contributors
"""Tab "Tat ca": pham vi du lieu phai do SERVER quyet, khong do bo loc cua trinh duyet.

Bo test nay canh bon dieu, moi dieu la mot cach that de ro du lieu:

  1. `approval_type` do client gui phai bi GHI DE, khong phai "mac dinh khi thieu". Neu chi
     mac dinh thi mot request tu che doi duoc sang form khac va tab "Tat ca" cua Booking tra
     ve phieu thanh toan - kem theo ten nguoi thu huong va so tai khoan.
  2. `scope_predicate` phai di theo MOI luot doc. Bo loc o trinh duyet la tien nghi hien thi.
  3. Export co TRAN dong, va phai NEM LOI khi vuot chu khong am tham cat bot - nguoi dung
     tuong minh da co du lieu day du thi con te hon khong xuat duoc.
  4. Vet export phai duoc ghi TRUOC khi tep duoc dung. Ghi sau thi mot loi giua chung lam tep
     van di ra ma vet khong co.

Site-free: `frappe` va cac module reporting deu bi thay bang ban gia.
"""
import sys
import types
import unittest


_TEN_GIA = (
    "frappe", "frappe.utils", "frappe.utils.xlsxutils",
    "ecentric_workspace.approval_center.reporting.api",
    "ecentric_workspace.approval_center.reporting.scope",
    "ecentric_workspace.approval_center.reporting.queries",
    "ecentric_workspace.approval_center.reporting.service",
    "ecentric_workspace.approval_center.reporting.status",
)


def _dat(ten, mod):
    """Cam module gia vao CA sys.modules LAN thuoc tinh cua goi cha.

    `from goi import ten` doc THUOC TINH cua goi cha truoc, khong doc sys.modules. Chi cam
    vao sys.modules thi ban gia bi bo qua ngay khi mot bo test khac da nap ban that - va bo
    test thanh phu thuoc THU TU chay. Do dung 16/09: file nay xanh khi chay truoc
    test_todo_box_after_approve, 20 bai do khi chay sau.
    """
    sys.modules[ten] = mod
    cha, _, la = ten.rpartition(".")
    if cha and cha in sys.modules and sys.modules[cha] is not None:
        setattr(sys.modules[cha], la, mod)


def _luu():
    cu = {}
    for ten in _TEN_GIA:
        cu[ten] = sys.modules.get(ten, KeyError)
        cha, _, la = ten.rpartition(".")
        if cha:
            goi = sys.modules.get(cha)
            cu[(cha, la)] = getattr(goi, la, KeyError) if goi is not None else KeyError
    return cu


def _tra(cu):
    for khoa, gt in cu.items():
        if isinstance(khoa, tuple):
            cha, la = khoa
            goi = sys.modules.get(cha)
            if goi is None:
                continue
            if gt is KeyError:
                if hasattr(goi, la):
                    delattr(goi, la)
            else:
                setattr(goi, la, gt)
        elif gt is KeyError:
            sys.modules.pop(khoa, None)
        else:
            sys.modules[khoa] = gt


def _hang_that(ten):
    """Doc mot hang literal THAT cua queries.py (khong chep tay vao stub - stub tu bia ra
    danh sach rieng thi bai test kiem chinh no chu khong kiem code)."""
    import ast
    import io
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reporting",
                     "queries.py")
    for n in ast.parse(io.open(p, encoding="utf-8").read()).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == ten:
            return ast.literal_eval(n.value)
    raise AssertionError("queries.%s bien mat" % ten)


def _status_that(ten_mod):
    """reporting/status.py THAT (thuan Python, khong frappe) - nhan + anh xa trang thai."""
    import io
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reporting",
                     "status.py")
    m = types.ModuleType(ten_mod)
    exec(compile(io.open(p, encoding="utf-8").read(), p, "exec"), m.__dict__)
    return m


def _nap():
    """Nap all_list voi frappe + reporting gia. Tra ve (module, so ghi nhan)."""
    ghi = {"service_calls": [], "count_calls": [], "vet": [], "tep": [], "throw": [],
           "tim_tieu_de": [], "_bang": []}

    fr = types.ModuleType("frappe")
    fr.session = types.SimpleNamespace(user="u@e.c")
    fr.response = {}
    fr._ = lambda s: s

    def _throw(msg):
        ghi["throw"].append(msg)
        raise RuntimeError(msg)
    fr.throw = _throw
    fr.log_error = lambda *a, **k: None
    fr.get_traceback = lambda: ""
    # `_truong`: truong DocType nghiep vu CO THAT (meta). Bai nao can thi ghi de.
    fr.get_meta = lambda dt: types.SimpleNamespace(
        has_field=lambda f: f in ghi.get("_truong", ("payment_amount", "request_title")),
        get_field=lambda f: types.SimpleNamespace(label="Nhan " + f))

    def _get_all(dt, **k):
        flt = k.get("filters") or {}
        if "request_title" in flt:                     # tra ma phieu theo tieu de
            ghi["tim_tieu_de"].append((flt["request_title"], k.get("limit_page_length")))
            return [{"name": "R%d" % i} for i in range(ghi.get("_so_tieu_de", 2))]
        if "_dong_nv" in ghi and "name" in (k.get("fields") or []):   # cot them theo lo
            ghi.setdefault("doc_cot", []).append((dt, list(k.get("fields")), flt))
            return [dict(x) for x in ghi["_dong_nv"]]
        return [{"payment_amount": 100}, {"payment_amount": 50}]
    fr.get_all = _get_all

    class _Doc(dict):
        def insert(self, **k):
            ghi["vet"].append(dict(self))
            return self
    fr.get_doc = lambda d: _Doc(d)
    def _sql(sql, params=None, **k):
        ghi.setdefault("sql", []).append((sql, dict(params or {})))
        return list(ghi.get("_sql_tra", []))
    fr.db = types.SimpleNamespace(sql=_sql)
    fr.utils = types.SimpleNamespace(
        now_datetime=lambda: types.SimpleNamespace(strftime=lambda f: "20260916_1200"))
    fr.whitelist = lambda *a, **k: (lambda f: f)
    _dat("frappe", fr)
    _dat("frappe.utils", fr.utils)
    xl = types.ModuleType("frappe.utils.xlsxutils")

    def _mk(bang, ten):
        ghi["tep"].append(("xlsx", len(bang)))
        ghi["_bang"] = bang
        return types.SimpleNamespace(getvalue=lambda: b"XLSXFAKE")
    xl.make_xlsx = _mk
    _dat("frappe.utils.xlsxutils", xl)

    base = "ecentric_workspace.approval_center.reporting."
    rapi = types.ModuleType(base + "api")
    rapi._parse_filters = lambda f, force_date=True: dict(f or {})
    scope = types.ModuleType(base + "scope")
    scope.resolve_scope = lambda u: {"mode": "requester", "user": u}
    scope.scope_predicate = lambda sc: ("r.requested_by = %(u)s", {"u": sc["user"]})
    q = types.ModuleType(base + "queries")

    def _count(sc, f, s=None):
        ghi["count_calls"].append((sc, dict(f), s))
        return ghi.get("_count", 3)
    q.count_requests = _count
    q.fetch_requests_page = lambda sc, f, a, b, s=None: [{"reference_name": "R1"}]
    # Chieu sap xep THAT cua queries (doc tu nguon, khong chep tay).
    q.SORT_DIRS = _hang_that("SORT_DIRS")
    svc = types.ModuleType(base + "service")

    def _list(sc, f, start=0, page_length=50, search=None):
        ghi["service_calls"].append({"scope": sc, "filters": dict(f), "start": start,
                                     "page_length": page_length, "search": search})
        mau = [{"name": "EC-1", "approvers": [], "requester_info": {"name": "A"},
                "status": "Pending", "status_label": "Pending"}]
        return {"rows": [dict(x) for x in ghi.get("_rows", mau)],
                "total": ghi.get("_count", 3), "start": start, "page_length": page_length}
    svc.list_requests = _list
    st = _status_that(base + "status")
    for m in (rapi, scope, q, svc, st):
        _dat(m.__name__, m)

    # PHAI reload, khong the chi xoa khoi sys.modules roi `from ... import`: khi goi cha da
    # nam trong sys.modules va DA co thuoc tinh `all_list`, Python tra ve thuoc tinh cu chu
    # khong nap lai. Bay nay lam bo test xanh khi chay le va do khi chay ca file - kieu do
    # con nguy hiem hon do han, vi no day nguoi ta di nghi ngo bai test.
    import importlib
    from ecentric_workspace.approval_center.shared.requests import all_list
    importlib.reload(all_list)
    return all_list, ghi


class _Def:
    code = "PAYMENT_REQUEST"
    business_doctype = "EC Payment Request"


class _Nen(unittest.TestCase):
    """Tra lai bang module CHUNG sau moi bai - neu khong, file nay lam do cac bo test chay
    sau no trong cung mot phien, va loi do khong he tro ve file gay ra no."""

    def setUp(self):
        self._cu = _luu()

    def tearDown(self):
        _tra(self._cu)


class TestGhimPhamVi(_Nen):
    def test_approval_type_cua_client_bi_ghi_de(self):
        al, ghi = _nap()
        al.list_all(_Def(), filters={"approval_type": "BOOKING_REQUEST"})
        self.assertEqual(ghi["service_calls"][0]["filters"]["approval_type"], "PAYMENT_REQUEST",
                         "approval_type do client gui phai bi GHI DE, khong duoc ton tai")

    def test_ghim_ca_khi_client_khong_gui_gi(self):
        al, ghi = _nap()
        al.list_all(_Def(), filters=None)
        self.assertEqual(ghi["service_calls"][0]["filters"]["approval_type"], "PAYMENT_REQUEST")

    def test_scope_duoc_giai_va_truyen_xuong(self):
        al, ghi = _nap()
        al.list_all(_Def())
        sc = ghi["service_calls"][0]["scope"]
        self.assertEqual(sc.get("mode"), "requester")
        self.assertEqual(sc.get("user"), "u@e.c")

    def test_page_length_bi_chan_tran(self):
        al, ghi = _nap()
        al.list_all(_Def(), page_length=100000)
        self.assertLessEqual(ghi["service_calls"][0]["page_length"], al.PAGE_MAX)

    def test_page_length_rac_khong_lam_vo_trang(self):
        al, ghi = _nap()
        al.list_all(_Def(), page_length="abc", start="xyz")
        self.assertEqual(ghi["service_calls"][0]["page_length"], 50)
        self.assertEqual(ghi["service_calls"][0]["start"], 0)


class TestTongTien(_Nen):
    def test_co_tong_khi_it_phieu(self):
        al, ghi = _nap()
        out = al.list_all(_Def())
        self.assertEqual(out["total_amount"], 150)
        self.assertFalse(out["sum_capped"])

    def test_khong_tinh_tong_khi_vuot_nguong(self):
        al, ghi = _nap()
        ghi["_count"] = al.SUM_MAX + 1
        out = al.list_all(_Def())
        self.assertIsNone(out["total_amount"], "vuot nguong phai tra None, khong tra tong sai")
        self.assertTrue(out["sum_capped"])


class TestTiengViet(_Nen):
    """Nhan trang thai phai giong phan con lai cua Approval Center - va giong TRONG TEP XUAT."""

    def test_nhan_duoc_dich_sang_tieng_viet(self):
        al, ghi = _nap()
        out = al.list_all(_Def())
        self.assertEqual(out["rows"][0]["status_label"], "Chờ duyệt")

    def test_giu_nguyen_status_goc_de_bo_loc_van_khop(self):
        al, ghi = _nap()
        out = al.list_all(_Def())
        self.assertEqual(out["rows"][0]["status"], "Pending",
                         "dich ca gia tri goc thi bo loc im lang khong khop gi")

    def test_trang_thai_la_khong_lam_vo_man_hinh(self):
        al, _ = _nap()
        r = al._viet_hoa([{"status": "Thu La", "status_label": "Thu La"}])
        self.assertEqual(r[0]["status_label"], "Thu La")

    def test_bo_loc_tra_gia_tri_ANH_nhan_VIET(self):
        al, _ = _nap()
        st = al.filter_options(_Def())["statuses"]
        m = {x["value"]: x["label"] for x in st}
        self.assertEqual(m.get("Pending"), "Chờ duyệt")
        self.assertIn("Rejected", m, "gia tri gui len server phai giu tieng Anh")

    def test_tep_xuat_ra_cung_tieng_viet(self):
        al, ghi = _nap()
        al.export_all(_Def())
        self.assertTrue(any("Chờ duyệt" in str(x) for x in ghi["_bang"]),
                        "man hinh tieng Viet ma tep ke toan mo ra lai tieng Anh")


class TestTimTheoTieuDe(_Nen):
    """Tieu de that nam o DocType nghiep vu - menh de tim cua tang bao cao khong voi toi."""

    def test_co_tim_thi_tra_ma_theo_tieu_de(self):
        al, ghi = _nap()
        al.list_all(_Def(), search="CMC")
        self.assertEqual(len(ghi["tim_tieu_de"]), 1)
        self.assertEqual(ghi["tim_tieu_de"][0][0], ["like", "%CMC%"])
        self.assertIn("_search_refs", ghi["service_calls"][0]["filters"])

    def test_khong_tim_thi_khong_chay_truy_van_thua(self):
        al, ghi = _nap()
        al.list_all(_Def())
        self.assertEqual(ghi["tim_tieu_de"], [])
        self.assertNotIn("_search_refs", ghi["service_calls"][0]["filters"])

    def test_co_tran_so_ma_tra_ve(self):
        al, ghi = _nap()
        al.list_all(_Def(), search="a")
        self.assertEqual(ghi["tim_tieu_de"][0][1], al.SEARCH_REF_MAX,
                         "khong dat tran thi mot chu cai co the keo ve ca bang")

    def test_export_cung_tim_theo_tieu_de(self):
        al, ghi = _nap()
        al.export_all(_Def(), search="CMC")
        self.assertIn("_search_refs", ghi["service_calls"][-1]["filters"],
                      "tep xuat ra phai khop dung cai nguoi dung dang nhin")


class TestExport(_Nen):
    def test_vuot_tran_thi_nem_loi_chu_khong_cat_bot(self):
        al, ghi = _nap()
        ghi["_count"] = al.EXPORT_MAX + 1
        with self.assertRaises(RuntimeError):
            al.export_all(_Def())
        self.assertEqual(ghi["tep"], [], "vuot tran ma van dung tep - nguoi dung se tuong day du")
        self.assertTrue(any(str(al.EXPORT_MAX) in str(m) for m in ghi["throw"]),
                        "cau bao loi phai noi ro tran la bao nhieu de nguoi dung sua duoc")

    def test_export_di_qua_dung_bo_loc_da_ghim(self):
        al, ghi = _nap()
        al.export_all(_Def(), filters={"approval_type": "LEAVE"}, search="abc")
        f = ghi["service_calls"][-1]["filters"]
        self.assertEqual(f["approval_type"], "PAYMENT_REQUEST")
        self.assertEqual(ghi["service_calls"][-1]["search"], "abc")

    def test_ghi_vet_TRUOC_khi_dung_tep(self):
        al, ghi = _nap()
        thu_tu = []
        goc_vet, goc_xlsx = al._ghi_vet, al._xlsx
        al._ghi_vet = lambda *a, **k: thu_tu.append("vet")
        al._xlsx = lambda *a, **k: (thu_tu.append("tep"), b"X")[1]
        try:
            al.export_all(_Def())
        finally:
            al._ghi_vet, al._xlsx = goc_vet, goc_xlsx
        self.assertEqual(thu_tu, ["vet", "tep"],
                         "ghi vet phai xay ra TRUOC khi tep duoc dung")

    def test_vet_ghi_du_ai_loc_gi_bao_nhieu_dong(self):
        al, ghi = _nap()
        al.export_all(_Def(), filters={"department": "Ops"})
        self.assertEqual(len(ghi["vet"]), 1)
        noi_dung = ghi["vet"][0]["content"]
        self.assertIn("PAYMENT_REQUEST", noi_dung)
        self.assertIn("Ops", noi_dung)
        self.assertIn("requester", noi_dung, "phai ghi lai pham vi cua nguoi xuat")

    def test_csv_co_BOM(self):
        al, _ = _nap()
        b = al._csv([["Mã", "Số tiền"], ["EC-1", 100]])
        self.assertTrue(b.startswith(b"\xef\xbb\xbf"),
                        "thieu BOM thi Excel tren Windows doc tieng Viet ra ky tu rac")

    def test_csv_dat_ten_tep_va_kieu_nhi_phan(self):
        al, _ = _nap()
        import frappe
        frappe.response.clear()
        al.export_all(_Def(), fmt="csv")
        self.assertTrue(frappe.response["filename"].endswith(".csv"))
        self.assertEqual(frappe.response["type"], "binary")


class _DefCR:
    """Dang khai cua Contract Review (definition that), tach khoi frappe."""
    code = "CONTRACT_REVIEW"
    business_doctype = "EC Contract Review Request"
    all_tab_columns = (("Legal entity / Brand", "brand", "text"),
                       ("Loại hợp đồng", "contract_type", "select"),
                       ("Giá trị", "contract_value", "money"))
    all_tab_filters = ("brand", "contract_type")


_TRUONG_CR = ("brand", "contract_type", "contract_value", "request_title")


def _nap_cr():
    al, ghi = _nap()
    ghi["_truong"] = _TRUONG_CR
    return al, ghi


class TestSapXep(_Nen):
    """Sap xep {"col","dir"} chi nhan khoa cot trong danh sach TRANG dung tu chinh cac cot
    dang hien (16/10/2026, sap xep tren header). Khong bao gio la ORDER BY cua client."""

    def _f(self, al, ghi, sort, d=None):
        al.list_all(d or _DefCR(), filters={"sort": sort})
        return ghi["service_calls"][-1]["filters"]

    # -- tuong thich nguoc: khoa chuoi cua ban <select> truoc -----------------------------
    def test_khoa_cu_oldest_van_nhan(self):
        al, ghi = _nap_cr()
        self.assertEqual(self._f(al, ghi, "oldest").get("_sort"),
                         {"key": "submitted", "dir": "asc"})

    def test_khoa_cu_so_tien_van_nhan(self):
        al, ghi = _nap_cr()
        for cu, huong in (("amount_desc", "desc"), ("amount_asc", "asc")):
            f = self._f(al, ghi, cu)
            self.assertEqual(f.get("_sort"), {"key": "biz", "dir": huong,
                                              "field": "contract_value", "text": False})
            self.assertEqual(f["_biz"]["doctype"], "EC Contract Review Request")
            self.assertEqual(f["_biz"]["amount_field"], "contract_value",
                             "phai sap theo DUNG truong cot 'So tien' dang hien (AMOUNT_FIELDS)")

    def test_moi_den_cu_la_mac_dinh_khong_dat_khoa(self):
        al, ghi = _nap_cr()
        for mac_dinh in ("newest", {"col": "submitted", "dir": "desc"}):
            f = self._f(al, ghi, mac_dinh)
            self.assertNotIn("_sort", f, "mac dinh phai di dung duong cu cua hub")
            self.assertNotIn("_biz", f)

    # -- dac ta moi -----------------------------------------------------------------------
    def test_cot_ngay_gui_cu_den_moi(self):
        al, ghi = _nap_cr()
        self.assertEqual(self._f(al, ghi, {"col": "submitted", "dir": "asc"}).get("_sort"),
                         {"key": "submitted", "dir": "asc"})

    def test_cot_tieu_de_sap_theo_request_title_la_chu(self):
        al, ghi = _nap_cr()
        f = self._f(al, ghi, {"col": "title", "dir": "asc"})
        self.assertEqual(f["_sort"], {"key": "biz", "dir": "asc", "field": "request_title",
                                      "text": True})
        self.assertEqual(f["_biz"]["doctype"], "EC Contract Review Request")

    def test_form_khong_co_request_title_thi_khong_sap_tieu_de(self):
        al, ghi = _nap()
        ghi["_truong"] = ("payment_amount",)
        f = self._f(al, ghi, {"col": "title", "dir": "asc"}, _Def())
        self.assertNotIn("_sort", f)
        self.assertNotIn("title", al.filter_options(_Def())["sort_cols"])

    def test_cot_trang_thai_theo_thu_tu_nhan_tieng_viet(self):
        al, ghi = _nap_cr()
        s = self._f(al, ghi, {"col": "status", "dir": "desc"})["_sort"]
        self.assertEqual((s["key"], s["dir"]), ("status", "desc"))
        nhan = [al.TRANG_THAI_VI[al._status.normalize(e)] for e in s["order"]]
        self.assertEqual(nhan, ["Cần bổ sung", "Chờ duyệt", "Đã hủy", "Hoàn tất", "Từ chối"],
                         "A -> Z phai theo nhan tieng Viet dang hien, khong theo gia tri tieng Anh")
        self.assertNotIn("_biz", self._f(al, ghi, {"col": "status", "dir": "asc"}),
                         "sap trang thai khong can dung DocType nghiep vu")

    def test_cot_them_khai_bao(self):
        al, ghi = _nap_cr()
        f = self._f(al, ghi, {"col": "x:brand", "dir": "desc"})
        self.assertEqual(f["_sort"], {"key": "biz", "dir": "desc", "field": "brand", "text": True})
        f = self._f(al, ghi, {"col": "x:contract_type", "dir": "asc"})
        self.assertTrue(f["_sort"]["text"], "kieu select la chu - chuoi rong xuong cuoi")

    def test_tiem_va_khoa_la_ve_mac_dinh(self):
        al, ghi = _nap_cr()
        for xau in ("submitted_at; DROP TABLE `tabUser`", "r.name DESC", "OLDEST", ["oldest"],
                    {"k": 1}, 1, None, True,
                    {"col": "x:name; DROP", "dir": "asc"},
                    {"col": "x:brand` DESC, (SELECT 1)", "dir": "asc"},
                    {"col": "x:request_title", "dir": "asc"},        # khong khai la cot
                    {"col": "x:contract_value", "dir": "asc"},       # trung cot so tien
                    {"col": "x:", "dir": "asc"},
                    {"col": "brand", "dir": "asc"},                  # thieu tien to x:
                    {"col": "r.approval_status", "dir": "asc"},
                    {"col": "amount", "dir": "ASC"},
                    {"col": "amount", "dir": "asc; DROP"},
                    {"col": "amount"},
                    {"col": ["amount"], "dir": "asc"},
                    {"dir": "asc"}):
            f = self._f(al, ghi, xau)
            self.assertNotIn("_sort", f, "khoa sap xep la lot qua: %r" % (xau,))
            self.assertNotIn("_biz", f, "khoa la van dung dac ta nghiep vu: %r" % (xau,))

    def test_cot_khai_ma_meta_khong_co_thi_khong_sap(self):
        al, ghi = _nap()
        ghi["_truong"] = ("contract_type", "contract_value", "request_title")   # khong co brand
        f = self._f(al, ghi, {"col": "x:brand", "dir": "asc"})
        self.assertNotIn("_sort", f)
        self.assertNotIn("x:brand", al.filter_options(_DefCR())["sort_cols"])

    def test_form_khong_co_so_tien_thi_bo_sap_xep_theo_so_tien(self):
        al, ghi = _nap()
        ghi["_truong"] = ("request_title",)
        for sx in ("amount_asc", {"col": "amount", "dir": "desc"}):
            f = self._f(al, ghi, sx)
            self.assertNotIn("_sort", f)
            self.assertNotIn("_biz", f)

    def test_sort_cols_khop_dung_cot_dang_hien(self):
        al, ghi = _nap_cr()
        o = al.filter_options(_DefCR())
        self.assertEqual(o["sort_cols"], ["submitted", "status", "title", "amount",
                                          "x:brand", "x:contract_type"])
        self.assertEqual([(c["sort"], c["filter"]) for c in o["columns"]],
                         [("x:brand", True), ("x:contract_type", True)])
        # Moi khoa server khai la sap duoc - khong khoa nao ma bam roi ve mac dinh.
        for k in o["sort_cols"]:
            if k == "submitted":
                continue
            self.assertIn("_sort", self._f(al, ghi, {"col": k, "dir": "asc"}), k)

    def test_export_theo_cung_thu_tu(self):
        al, ghi = _nap_cr()
        al.export_all(_DefCR(), filters='{"sort": {"col": "x:brand", "dir": "asc"}}')
        self.assertEqual(ghi["service_calls"][-1]["filters"].get("_sort", {}).get("field"),
                         "brand", "tep xuat ra phai cung thu tu voi bang dang nhin")
        al.export_all(_DefCR(), filters='{"sort": "oldest"}')
        self.assertEqual(ghi["service_calls"][-1]["filters"].get("_sort"),
                         {"key": "submitted", "dir": "asc"})


class TestLocNhieuGiaTri(_Nen):
    """O tick tren header: trang thai / phong ban / nguoi de nghi nhan DANH SACH (-> IN).
    Dang mot gia tri cu van chay nhu truoc."""

    def _f(self, al, ghi, **flt):
        al.list_all(_Def(), filters=flt)
        return ghi["service_calls"][-1]["filters"]

    def test_mot_gia_tri_dang_cu_giu_nguyen(self):
        al, ghi = _nap()
        f = self._f(al, ghi, department="Ops", requester="a@e.c", status="Pending")
        self.assertEqual((f["department"], f["requester"], f["status"]),
                         ("Ops", "a@e.c", "Pending"))

    def test_danh_sach_thanh_list(self):
        al, ghi = _nap()
        f = self._f(al, ghi, department=["Ops", " Finance ", "Ops", ""],
                    requester=["a@e.c", "b@e.c"])
        self.assertEqual(f["department"], ["Ops", "Finance"], "phai cat khoang trang + bo trung")
        self.assertEqual(f["requester"], ["a@e.c", "b@e.c"])

    def test_danh_sach_mot_phan_tu_thanh_gia_tri_don(self):
        al, ghi = _nap()
        self.assertEqual(self._f(al, ghi, department=["Ops"])["department"], "Ops")

    def test_trang_thai_nhan_chuan_hoa_doi_sang_engine(self):
        al, ghi = _nap()
        f = self._f(al, ghi, status=["Completed", "Pending", "Draft", "Hacked'--"])
        self.assertEqual(f["status"], ["Approved", "Pending"],
                         "Completed -> Approved; Draft va gia tri la bi bo")
        self.assertNotIn("status", self._f(al, ghi, status=["Draft"]))
        self.assertNotIn("status", self._f(al, ghi, status="Draft"))

    def test_gia_tri_rac_bi_bo_khong_nem_loi(self):
        al, ghi = _nap()
        f = self._f(al, ghi, department={"x": 1}, requester=[{"a": 1}, ["b"], True, None],
                    status={"$ne": 1})
        for k in ("department", "requester", "status"):
            self.assertNotIn(k, f, "gia tri rac lot vao bo loc %s" % k)

    def test_danh_sach_co_tran(self):
        al, ghi = _nap()
        f = self._f(al, ghi, department=["d%d" % i for i in range(al.DISTINCT_MAX + 50)])
        self.assertEqual(len(f["department"]), al.DISTINCT_MAX)

    def test_gia_tri_qua_dai_bi_cat(self):
        al, ghi = _nap()
        self.assertEqual(len(self._f(al, ghi, department=["x" * 999, "y"])["department"][0]),
                         al.GIA_TRI_MAX)

    def test_approval_type_van_bi_ghi_de_khi_co_danh_sach(self):
        al, ghi = _nap()
        f = self._f(al, ghi, approval_type=["BOOKING_REQUEST"], department=["Ops", "HR"])
        self.assertEqual(f["approval_type"], "PAYMENT_REQUEST")

    def test_export_cung_bo_loc_danh_sach(self):
        al, ghi = _nap()
        al.export_all(_Def(), filters={"department": ["Ops", "HR"], "status": ["Rejected"]})
        f = ghi["service_calls"][-1]["filters"]
        self.assertEqual((f["department"], f["status"]), (["Ops", "HR"], "Rejected"))
        self.assertEqual(f["approval_type"], "PAYMENT_REQUEST")


class TestKhoangTien(_Nen):
    def _biz(self, al, ghi, **f):
        al.list_all(_DefCR(), filters=f)
        return ghi["service_calls"][-1]["filters"].get("_biz")

    def test_chuoi_kieu_viet_nam_hieu_dung(self):
        al, ghi = _nap_cr()
        b = self._biz(al, ghi, amount_min="1.500.000", amount_max=20000000)
        self.assertEqual(b["amount_min"], 1500000)
        self.assertEqual(b["amount_max"], 20000000)
        self.assertEqual(b["amount_field"], "contract_value")

    def test_go_nguoc_hai_dau_thi_dao_lai(self):
        al, ghi = _nap_cr()
        b = self._biz(al, ghi, amount_min=500, amount_max=100)
        self.assertEqual((b["amount_min"], b["amount_max"]), (100, 500))

    def test_gia_tri_rac_bi_bo_qua_khong_nem_loi(self):
        al, ghi = _nap_cr()
        for rac in ("abc", "-5", -5, "1e400", float("nan"), True, "", None, "1 OR 1=1"):
            self.assertIsNone(self._biz(al, ghi, amount_min=rac), "lot gia tri rac: %r" % (rac,))

    def test_form_khong_co_so_tien_thi_khong_loc_so_tien(self):
        al, ghi = _nap()
        ghi["_truong"] = ("request_title",)
        self.assertIsNone(self._biz(al, ghi, amount_min=1, amount_max=2))

    def test_tong_tien_cong_dung_truong_dang_hien(self):
        al, ghi = _nap_cr()
        ghi["_truong"] = _TRUONG_CR + ("amount",)        # co ca truong du phong cu
        tong = []
        import frappe
        goc = frappe.get_all
        frappe.get_all = lambda dt, **k: (tong.append(k.get("fields")), [{"contract_value": 7}])[1]
        try:
            out = al.list_all(_DefCR())
        finally:
            frappe.get_all = goc
        self.assertIn(["contract_value"], tong)
        self.assertEqual(out["total_amount"], 7)


    def test_form_nhieu_tien_te_khong_cong_tong(self):
        al, ghi = _nap()
        ghi["_truong"] = ("requested_amount", "currency")

        class _Ai:
            code = "AI_TOPUP"
            business_doctype = "EC AI Topup Request"
        out = al.list_all(_Ai())
        self.assertIsNone(out["total_amount"], "cong USD voi VND ra mot tong sai")
        al.list_all(_Ai(), filters={"amount_min": 5})
        self.assertEqual(ghi["service_calls"][-1]["filters"]["_biz"]["amount_min"], 5,
                         "loc khoang so tien van dung duoc tren cot dang hien")


class TestCotVaLocThem(_Nen):
    def test_chi_truong_KHAI_LOC_moi_vao_dieu_kien(self):
        al, ghi = _nap_cr()
        al.list_all(_DefCR(), filters={"extra": {
            "brand": " ACME ", "contract_type": "Sales / Bán ra (EC)",
            "request_title": "khong khai loc", "brand`; DROP": "x", "contract_value": 1,
            "name; DROP TABLE x": ["a"]}})
        b = ghi["service_calls"][-1]["filters"]["_biz"]
        self.assertEqual(dict(b["in"]), {"brand": ("ACME",),
                                         "contract_type": ("Sales / Bán ra (EC)",)})
        self.assertNotIn("eq", b, "tu 16/10 moi loc truong nghiep vu di qua `in`")

    def test_danh_sach_gia_tri_thanh_IN(self):
        al, ghi = _nap_cr()
        al.list_all(_DefCR(), filters={"extra": {"brand": ["ACME", "Beta", "ACME", " "],
                                                 "contract_type": []}})
        b = ghi["service_calls"][-1]["filters"]["_biz"]
        self.assertEqual(dict(b["in"]), {"brand": ("ACME", "Beta")},
                         "bo trung + bo rong; danh sach rong = khong loc")

    def test_gia_tri_khong_phai_chuoi_bi_bo(self):
        al, ghi = _nap_cr()
        al.list_all(_DefCR(), filters={"extra": {"brand": [{"a": 1}, ["b"], True],
                                                 "contract_type": {"x": 1}}})
        self.assertNotIn("_biz", ghi["service_calls"][-1]["filters"])
        al.list_all(_DefCR(), filters={"extra": ["brand", "ACME"]})
        self.assertNotIn("_biz", ghi["service_calls"][-1]["filters"])

    def test_truong_khai_ma_meta_khong_co_thi_bi_loai(self):
        al, ghi = _nap()
        ghi["_truong"] = ("contract_type", "contract_value")     # khong co `brand`
        al.list_all(_DefCR(), filters={"extra": {"brand": "ACME"}})
        self.assertNotIn("_biz", ghi["service_calls"][-1]["filters"])
        o = al.filter_options(_DefCR())
        self.assertNotIn("brand", [c["fieldname"] for c in o["columns"]])
        self.assertNotIn("brand", [c["fieldname"] for c in o["extra_filters"]])

    def test_cot_them_gan_vao_tung_dong_theo_lo(self):
        al, ghi = _nap_cr()
        ghi["_rows"] = [{"name": "EC-1", "reference_name": "R1", "status": "Pending"},
                        {"name": "EC-2", "reference_name": "R2", "status": "Pending"}]
        ghi["_dong_nv"] = [{"name": "R1", "brand": "ACME", "contract_type": "Sales"}]
        out = al.list_all(_DefCR())
        self.assertEqual(out["rows"][0]["extra"], {"brand": "ACME", "contract_type": "Sales"})
        self.assertEqual(out["rows"][1]["extra"], {"brand": None, "contract_type": None})
        self.assertEqual(len(ghi["doc_cot"]), 1, "phai doc theo LO, mot truy van cho ca trang")
        dt, fields, flt = ghi["doc_cot"][0]
        self.assertEqual(fields, ["name", "brand", "contract_type"],
                         "cot trung truong so tien khong duoc doc/ve lan thu hai")
        self.assertEqual(flt, {"name": ["in", ["R1", "R2"]]})

    def test_form_khong_khai_gi_giu_nguyen_nhu_cu(self):
        al, ghi = _nap()
        o = al.filter_options(_Def())
        self.assertEqual(o["columns"], [])
        self.assertEqual(o["extra_filters"], [])
        self.assertEqual(o["amount"], {"field": "payment_amount", "label": "Số tiền"})

    def test_nhan_so_tien_lay_tu_cot_khai(self):
        al, ghi = _nap_cr()
        o = al.filter_options(_DefCR())
        self.assertEqual(o["amount"], {"field": "contract_value", "label": "Giá trị"})
        self.assertEqual([c["fieldname"] for c in o["columns"]], ["brand", "contract_type"])
        self.assertEqual([(c["fieldname"], c["label"]) for c in o["extra_filters"]],
                         [("brand", "Legal entity / Brand"), ("contract_type", "Loại hợp đồng")])


class TestGiaTriRiengTrongPhamVi(_Nen):
    """O chon brand/loai hop dong KHONG duoc liet ke gia tri tu phieu nguoi xem khong thay."""

    def test_moi_truy_van_distinct_deu_mang_pham_vi_va_ghim_form(self):
        al, ghi = _nap_cr()
        ghi["_sql_tra"] = [{"v": "ACME"}]
        o = al.filter_options(_DefCR())
        rieng = [(q, p) for q, p in ghi["sql"] if "b.`" in q]
        self.assertEqual(len(rieng), 2, "brand + contract_type")
        for q, p in rieng:
            self.assertIn("r.requested_by = %(u)s", q, "thieu scope_predicate")
            self.assertIn("r.approval_type = %(ft_type)s", q, "thieu ghim form")
            self.assertIn("r.reference_doctype = %(ft_dt)s", q)
            self.assertIn("LIMIT %(ft_max)s", q)
            self.assertEqual(p["u"], "u@e.c")
            self.assertEqual(p["ft_type"], "CONTRACT_REVIEW")
            self.assertEqual(p["ft_max"], al.DISTINCT_MAX)
        self.assertEqual(o["extra_filters"][0]["options"], ["ACME"])

    def test_phong_ban_va_nguoi_de_nghi_cung_trong_pham_vi_va_co_tran(self):
        al, ghi = _nap_cr()
        ghi["_sql_tra"] = [{"v": "Ops", "label": "An"}]
        o = al.filter_options(_DefCR())
        co_ban = [(q, p) for q, p in ghi["sql"] if "b.`" not in q]
        self.assertEqual(len(co_ban), 2, "phong ban + nguoi de nghi")
        for q, p in co_ban:
            self.assertIn("r.requested_by = %(u)s AND r.approval_type = %(ft_type)s", q)
            self.assertIn("LIMIT %(ft_max)s", q, "o tick khong gioi han la tai vo ich len DB")
            self.assertEqual(p["ft_max"], al.DISTINCT_MAX)
        self.assertEqual(o["departments"], ["Ops"])
        self.assertEqual(o["requesters"], [{"value": "Ops", "label": "An"}])

    def test_trang_thai_khong_co_nhap(self):
        al, _ = _nap()
        st = al.filter_options(_Def())["statuses"]
        self.assertNotIn("Draft", [x["value"] for x in st],
                         "Nhap khong bao gio co tren EC Approval Request - tick vao la loc gia")
        self.assertEqual([x["label"] for x in st],
                         ["Chờ duyệt", "Cần bổ sung", "Hoàn tất", "Từ chối", "Đã hủy"])

    def test_ten_truong_la_khong_bao_gio_vao_SQL(self):
        al, ghi = _nap_cr()
        n = len(ghi.get("sql", []))
        self.assertEqual(al._gia_tri_rieng(_DefCR(), "brand` FROM x; --", "1=1", {}), [])
        self.assertEqual(len(ghi.get("sql", [])), n)


class TestExportCotThem(_Nen):
    def test_tep_co_cot_them_noi_sau_cot_co_dinh(self):
        al, ghi = _nap_cr()
        ghi["_rows"] = [{"name": "EC-1", "reference_name": "R1", "status": "Pending",
                         "approvers": []}]
        ghi["_dong_nv"] = [{"name": "R1", "brand": "ACME", "contract_type": "Sales"}]
        al.export_all(_DefCR(), filters={"extra": {"brand": "ACME"}})
        dau, dong = ghi["_bang"][0], ghi["_bang"][1]
        co_dinh = [lab for _k, lab in al._COT]
        self.assertEqual(dau[:len(co_dinh)], co_dinh, "vi tri cot cu phai giu nguyen")
        self.assertEqual(dau[len(co_dinh):], ["Legal entity / Brand", "Loại hợp đồng"])
        self.assertEqual(dong[len(co_dinh):], ["ACME", "Sales"])
        self.assertEqual(dict(ghi["service_calls"][-1]["filters"]["_biz"]["in"]),
                         {"brand": ("ACME",)}, "tep xuat ra phai cung bo loc voi bang")

    def test_form_khong_khai_thi_tep_y_nhu_cu(self):
        al, ghi = _nap()
        al.export_all(_Def())
        self.assertEqual(ghi["_bang"][0], [lab for _k, lab in al._COT])


class TestNguonMa(unittest.TestCase):
    def test_export_all_la_POST_trong_api_adapter(self):
        """Frappe hoan tac moi ghi trong request GET -> tep di ra ma vet bi cuon lai."""
        import io
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(here, "..", "..", "shared", "api_adapter.py")
        src = io.open(p, encoding="utf-8").read()
        i = src.index("def export_all(")
        self.assertIn('methods=["POST"]', src[max(0, i - 400):i])


if __name__ == "__main__":
    unittest.main()
