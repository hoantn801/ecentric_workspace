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
    fr.get_meta = lambda dt: types.SimpleNamespace(
        has_field=lambda f: f in ("payment_amount", "request_title"))

    def _get_all(dt, **k):
        flt = k.get("filters") or {}
        if "request_title" in flt:                     # tra ma phieu theo tieu de
            ghi["tim_tieu_de"].append((flt["request_title"], k.get("limit_page_length")))
            return [{"name": "R%d" % i} for i in range(ghi.get("_so_tieu_de", 2))]
        return [{"payment_amount": 100}, {"payment_amount": 50}]
    fr.get_all = _get_all

    class _Doc(dict):
        def insert(self, **k):
            ghi["vet"].append(dict(self))
            return self
    fr.get_doc = lambda d: _Doc(d)
    fr.db = types.SimpleNamespace(sql=lambda *a, **k: [])
    fr.utils = types.SimpleNamespace(
        now_datetime=lambda: types.SimpleNamespace(strftime=lambda f: "20260916_1200"))
    fr.whitelist = lambda *a, **k: (lambda f: f)
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = fr.utils
    xl = types.ModuleType("frappe.utils.xlsxutils")

    def _mk(bang, ten):
        ghi["tep"].append(("xlsx", len(bang)))
        ghi["_bang"] = bang
        return types.SimpleNamespace(getvalue=lambda: b"XLSXFAKE")
    xl.make_xlsx = _mk
    sys.modules["frappe.utils.xlsxutils"] = xl

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
    svc = types.ModuleType(base + "service")

    def _list(sc, f, start=0, page_length=50, search=None):
        ghi["service_calls"].append({"scope": sc, "filters": dict(f), "start": start,
                                     "page_length": page_length, "search": search})
        return {"rows": [{"name": "EC-1", "approvers": [], "requester_info": {"name": "A"},
                          "status": "Pending", "status_label": "Pending"}],
                "total": ghi.get("_count", 3), "start": start, "page_length": page_length}
    svc.list_requests = _list
    st = types.ModuleType(base + "status")
    st.NORMALIZED_STATUSES = ["Draft", "Pending", "Information Required",
                              "Completed", "Rejected", "Cancelled"]
    for m in (rapi, scope, q, svc, st):
        sys.modules[m.__name__] = m

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


class TestGhimPhamVi(unittest.TestCase):
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


class TestTongTien(unittest.TestCase):
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


class TestTiengViet(unittest.TestCase):
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


class TestTimTheoTieuDe(unittest.TestCase):
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


class TestExport(unittest.TestCase):
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
