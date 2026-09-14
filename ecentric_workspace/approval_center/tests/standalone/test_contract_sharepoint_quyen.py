# Copyright (c) 2026, eCentric and contributors
"""Cap quyen tep hop dong tren SharePoint - do that 14/09 roi sua theo ket qua do.

Lan chay dau tren tenant that: tai len XANH, cap quyen DO voi `noResolvedUsers` va KHONG mot
ai trong 10 dia chi resolve duoc. Zero nguoi resolve la dau hieu loi nam o ngu canh app-only
chu khong phai o mot dia chi hong. Vi vay doi sang `createLink` scope=users - cung loai token,
nhung duong nay dang chay that moi tuan qua `weekly_report.create_org_link`.

Bo test giu bon dieu, deu la thu de mat tien neu sai:
  1. Than yeu cau gui di dung la createLink/scope=users/type=edit - KHONG phai /invite.
  2. KHONG BAO GIO tu dong lui ve scope="organization": cap nham ca cong ty quyen SUA hop dong
     con te hon bao loi.
  3. Mac dinh KHONG pha thua ke (khong thu hoi quyen cua nguoi dang co) tru khi noi ro.
  4. Tai khoan dich vu bi loai, va bi BAO RA chu khong bien mat im lang.
Cong them: chon tep de review phai uu tien tep Office, vi PDF khong sua duoc tren Office Online.
"""
import ast
import io
import os
import sys
import types
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
_SYNC = os.path.join(_ROOT, "approval_center", "features", "contract_review",
                     "infrastructure", "sharepoint_sync.py")
_API = os.path.join(_ROOT, "approval_center", "features", "contract_review",
                    "infrastructure", "sharepoint_probe.py")


def _doan(path, *ten):
    """Boc rieng vai ham/bien ra khoi module bang AST. Khong import ca module: no keo theo
    frappe va ca chuoi phu thuoc Graph."""
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    ra = []
    con_lai = set(ten)
    for node in tree.body:
        nn = getattr(node, "name", None)
        if nn is None and isinstance(node, ast.Assign):
            nn = getattr(node.targets[0], "id", None)
        if nn in con_lai:
            ra.append(ast.get_source_segment(src, node))
            con_lai.discard(nn)
    if con_lai:
        raise AssertionError("khong thay %s trong %s" % (", ".join(sorted(con_lai)), path))
    return "\n\n".join(ra)


class _Resp(object):
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


class _Requests(object):
    """Ghi lai moi lan goi de test khang dinh vao THAN yeu cau, khong phai vao viec 'co goi'."""

    def __init__(self, resp=None):
        self.calls = []
        self.resp = resp or _Resp(200, {"link": {"webUrl": "https://sp/link"}})

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "json": json or {}})
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "json": None})
        return self.resp


def _nap_sync(requests_gia):
    """Chay that phan than cua sharepoint_sync, voi Graph gia."""
    ns = {}
    ns["TIMEOUT"] = 30
    ns["_requests"] = lambda: requests_gia
    ns["_graph"] = lambda: "https://graph.microsoft.com/v1.0"
    ns["wr_sp"] = types.SimpleNamespace(SITE_ID="site-1", get_app_token=lambda: "TOKEN")

    class SharePointChuaSan(Exception):
        pass

    ns["SharePointChuaSan"] = SharePointChuaSan
    exec(compile(_doan(_SYNC, "TAI_KHOAN_DICH_VU", "loc_nguoi_that", "cap_quyen", "doc_quyen"),
                 "<sync>", "exec"), ns)
    return ns


NGUOI = ["tran.bui@ecentric.vn", "fabric.bot@ecentric.vn", "hoan.tran@ecentric.vn"]


class ThanYeuCau(unittest.TestCase):
    def setUp(self):
        self.req = _Requests()
        self.ns = _nap_sync(self.req)

    def test_goi_createlink_chu_khong_phai_invite(self):
        self.ns["cap_quyen"]("ITEM", NGUOI)
        url = self.req.calls[0]["url"]
        self.assertIn("/createLink", url)
        self.assertNotIn("/invite", url,
                         "/invite tra ve noResolvedUsers voi token app-only - khong quay lai")

    def test_scope_users_va_type_edit(self):
        self.ns["cap_quyen"]("ITEM", NGUOI, cho_sua=True)
        than = self.req.calls[0]["json"]
        self.assertEqual(than["scope"], "users")
        self.assertEqual(than["type"], "edit")
        self.assertEqual([r["email"] for r in than["recipients"]],
                         ["tran.bui@ecentric.vn", "hoan.tran@ecentric.vn"])

    def test_chi_xem_thi_type_view(self):
        self.ns["cap_quyen"]("ITEM", NGUOI, cho_sua=False)
        self.assertEqual(self.req.calls[0]["json"]["type"], "view")

    def test_khong_gui_email_moi(self):
        self.ns["cap_quyen"]("ITEM", NGUOI)
        self.assertIs(self.req.calls[0]["json"]["sendInvitation"], False)


class KhongTuMoRong(unittest.TestCase):
    """Dieu quan trong nhat trong file nay."""

    def test_khong_bao_gio_dung_scope_organization(self):
        req = _Requests()
        _nap_sync(req)["cap_quyen"]("ITEM", NGUOI)
        self.assertNotEqual(req.calls[0]["json"]["scope"], "organization")

    def test_that_bai_thi_nem_ra_chu_khong_lui_ve_pham_vi_rong(self):
        req = _Requests(_Resp(400, {}, "noResolvedUsers"))
        ns = _nap_sync(req)
        with self.assertRaises(ns["SharePointChuaSan"]):
            ns["cap_quyen"]("ITEM", NGUOI)
        self.assertEqual(len(req.calls), 1, "hong roi thi DUNG, khong thu lai bang duong rong hon")

    def test_mac_dinh_khong_pha_thua_ke(self):
        req = _Requests()
        _nap_sync(req)["cap_quyen"]("ITEM", NGUOI)
        self.assertNotIn("retainInheritedPermissions", req.calls[0]["json"],
                         "go quyen thua ke la thu hoi quyen cua nguoi dang co - phai noi ro moi lam")

    def test_pha_thua_ke_chi_khi_noi_ro(self):
        req = _Requests()
        _nap_sync(req)["cap_quyen"]("ITEM", NGUOI, pha_thua_ke=True)
        self.assertIs(req.calls[0]["json"]["retainInheritedPermissions"], False)


class LocTaiKhoan(unittest.TestCase):
    def setUp(self):
        self.ns = _nap_sync(_Requests())

    def test_bo_tai_khoan_dich_vu(self):
        giu, bo = self.ns["loc_nguoi_that"](NGUOI)
        self.assertEqual(bo, ["fabric.bot@ecentric.vn"])
        self.assertNotIn("fabric.bot@ecentric.vn", giu)

    def test_bo_qua_duoc_bao_ra_chu_khong_bien_mat(self):
        r = self.ns["cap_quyen"]("ITEM", NGUOI)
        self.assertEqual(r["bo_qua"], ["fabric.bot@ecentric.vn"])

    def test_bo_trung_lap_va_dia_chi_rac(self):
        giu, _bo = self.ns["loc_nguoi_that"](
            ["a@x.vn", "a@x.vn", "", None, "khong-phai-email"])
        self.assertEqual(giu, ["a@x.vn"])

    def test_danh_sach_rong_thi_khong_goi_graph(self):
        req = _Requests()
        r = _nap_sync(req)["cap_quyen"]("ITEM", ["fabric.bot@ecentric.vn"])
        self.assertEqual(req.calls, [])
        self.assertEqual(r["da_cap"], [])


class DocQuyen(unittest.TestCase):
    def test_phan_biet_quyen_thua_ke_voi_quyen_cap_rieng(self):
        req = _Requests(_Resp(200, {"value": [
            {"roles": ["read"], "inheritedFrom": {"path": "/sites/operation"},
             "grantedToV2": {"siteGroup": {"displayName": "Members"}}},
            {"roles": ["write"],
             "grantedToIdentitiesV2": [{"user": {"email": "hoan.tran@ecentric.vn"}}]},
        ]}))
        ra = _nap_sync(req)["doc_quyen"]("ITEM")
        self.assertTrue(ra[0]["thua_ke"])
        self.assertEqual(ra[0]["cho"], "Members")
        self.assertFalse(ra[1]["thua_ke"])
        self.assertEqual(ra[1]["vai_tro"], "write")
        self.assertEqual(ra[1]["cho"], "hoan.tran@ecentric.vn")


class ChonTep(unittest.TestCase):
    def setUp(self):
        ns = {}
        exec(compile(_doan(_API, "DUOI_OFFICE", "chon_tep_office"), "<api>", "exec"), ns)
        self.chon = ns["chon_tep_office"]

    def _t(self, ten):
        return types.SimpleNamespace(file_name=ten, file_url="/private/files/" + ten)

    def test_uu_tien_docx_hon_pdf_du_pdf_cu_hon(self):
        tep = [self._t("HD.pdf"), self._t("HD.docx")]
        self.assertEqual(self.chon(tep).file_name, "HD.docx")

    def test_khong_co_tep_office_thi_lay_tep_dau(self):
        tep = [self._t("HD.pdf"), self._t("phu luc.png")]
        self.assertEqual(self.chon(tep).file_name, "HD.pdf")

    def test_khong_phan_biet_hoa_thuong(self):
        self.assertEqual(self.chon([self._t("a.pdf"), self._t("B.DOCX")]).file_name, "B.DOCX")


class GioUTC(unittest.TestCase):
    """Graph tra ve gio UTC; ERP so voi moc duyet la gio he thong (UTC+7).

    Do that 14/09 nem (1292, "Incorrect datetime value: '2026-09-14T08:58:18Z'") - MariaDB
    khong nhan chu T/Z. Nhung loi de thay do chi la be noi: cai dat tien la neu luu nguyen
    gio UTC thi moi phep so "tep bi sua sau khi duyet chua" lech BAY TIENG, va lech theo
    huong co loi cho ke sua. Bo test nay canh CA HAI.
    """

    def setUp(self):
        ns = {}
        exec(compile(_doan(_SYNC, "gio_he_thong"), "<sync>", "exec"), ns)
        # frappe.utils gia: doi UTC -> UTC+7, dung nhu convert_utc_to_system_timezone that.
        import datetime as _dt

        def _get_datetime(txt):
            return _dt.datetime.strptime(txt, "%Y-%m-%d %H:%M:%S")

        def _convert(d):
            # Ham THAT cua Frappe tra ve datetime CO tzinfo. Ban gia luc dau tra ve gio tran
            # nen phep kiem "da bo tzinfo chua" khong the do duoc gi - dot bien xoa
            # .replace(tzinfo=None) song sot. Ban gia phai giong that o dung diem ma bai test
            # dang khang dinh, neu khong thi bai test chi dang tu trang tri.
            return (d + _dt.timedelta(hours=7)).replace(
                tzinfo=_dt.timezone(_dt.timedelta(hours=7)))

        mod = types.ModuleType("frappe.utils")
        mod.get_datetime = _get_datetime
        mod.convert_utc_to_system_timezone = _convert
        frappe_mod = types.ModuleType("frappe")
        frappe_mod.utils = mod
        self._cu = (sys.modules.get("frappe"), sys.modules.get("frappe.utils"))
        sys.modules["frappe"] = frappe_mod
        sys.modules["frappe.utils"] = mod
        self.gio = ns["gio_he_thong"]

    def tearDown(self):
        for ten, cu in zip(("frappe", "frappe.utils"), self._cu):
            if cu is None:
                sys.modules.pop(ten, None)
            else:
                sys.modules[ten] = cu

    def test_doi_sang_gio_he_thong_chu_khong_giu_utc(self):
        d = self.gio("2026-09-14T08:58:18Z")
        self.assertEqual(d.hour, 15, "08:58 UTC phai thanh 15:58 gio Viet Nam")
        self.assertEqual(d.day, 14)

    def test_bo_chu_T_va_Z(self):
        d = self.gio("2026-09-14T08:58:18Z")
        self.assertNotIn("T", str(d))
        self.assertNotIn("Z", str(d))

    def test_khong_con_tzinfo(self):
        self.assertIsNone(self.gio("2026-09-14T08:58:18Z").tzinfo,
                          "Frappe luu gio tran theo mui he thong")

    def test_nhan_ca_dang_offset_00_00(self):
        self.assertEqual(self.gio("2026-09-14T08:58:18+00:00"),
                         self.gio("2026-09-14T08:58:18Z"))

    def test_bo_phan_le_giay(self):
        self.assertEqual(self.gio("2026-09-14T08:58:18.1234567Z"),
                         self.gio("2026-09-14T08:58:18Z"))

    def test_rong_thi_tra_None(self):
        self.assertIsNone(self.gio(None))
        self.assertIsNone(self.gio(""))

    def test_qua_nua_dem_thi_sang_ngay_hom_sau(self):
        d = self.gio("2026-09-14T18:30:00Z")
        self.assertEqual((d.day, d.hour), (15, 1), "18:30 UTC ngay 14 = 01:30 ngay 15 gio VN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
