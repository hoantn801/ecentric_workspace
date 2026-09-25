# Copyright (c) 2026, eCentric and contributors
"""Doc quyen tren tep SharePoint + doi moc thoi gian cua Graph ve gio he thong.

Phan CAP quyen da bi go 14/09: do tren tenant that thay nhom "Operation Members" DA co `write`
san tren thu vien, nen cap them cho tung nguoi chi la mot lop ACL thu hai tren mot lop da mo -
xem chu thich dai trong `shared/integrations/sharepoint_mirror.py`. Bo test cua phan do di
theo. Hai thu con lai o day van dat gia:

  * `doc_quyen` - cach tra loi cau hoi van se phai hoi: "nguoi nay mo khong duoc tep, quyen
    vuong o dau?".
  * `gio_he_thong` - Graph tra gio UTC con moc duyet la gio he thong (UTC+7). Lech 7 tieng o
    day lam moi phep so "tep bi sua sau khi duyet chua" sai THEO HUONG CO LOI CHO NGUOI SUA.
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
_MIRROR = os.path.join(_ROOT, "approval_center", "shared", "integrations", "sharepoint_mirror.py")


def _doan(path, *ten):
    """Boc rieng vai ham ra bang AST - khong import ca module (no keo theo frappe + Graph)."""
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    ra, con_lai = [], set(ten)
    for node in tree.body:
        if getattr(node, "name", None) in con_lai:
            ra.append(ast.get_source_segment(src, node))
            con_lai.discard(node.name)
    if con_lai:
        raise AssertionError("khong thay %s trong %s" % (", ".join(sorted(con_lai)), path))
    return "\n\n".join(ra)


class _Resp(object):
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class _Requests(object):
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        return self.resp


def _nap(requests_gia):
    ns = {"TIMEOUT": 30, "_requests": lambda: requests_gia,
          "_graph": lambda: "https://graph.microsoft.com/v1.0",
          "wr_sp": types.SimpleNamespace(SITE_ID="site-1", get_app_token=lambda: "TOKEN")}

    class SharePointChuaSan(Exception):
        pass

    ns["SharePointChuaSan"] = SharePointChuaSan
    exec(compile(_doan(_MIRROR, "doc_quyen"), "<m>", "exec"), ns)
    return ns


class DocQuyen(unittest.TestCase):
    def test_phan_biet_quyen_thua_ke_voi_quyen_cap_rieng(self):
        req = _Requests(_Resp(200, {"value": [
            {"roles": ["read"], "inheritedFrom": {"path": "/sites/operation"},
             "grantedToV2": {"siteGroup": {"displayName": "Members"}}},
            {"roles": ["write"],
             "grantedToIdentitiesV2": [{"user": {"email": "hoan.tran@ecentric.vn"}}]},
        ]}))
        ra = _nap(req)["doc_quyen"]("ITEM")
        self.assertTrue(ra[0]["thua_ke"])
        self.assertEqual(ra[0]["cho"], "Members")
        self.assertFalse(ra[1]["thua_ke"])
        self.assertEqual(ra[1]["vai_tro"], "write")
        self.assertEqual(ra[1]["cho"], "hoan.tran@ecentric.vn")

    def test_graph_tu_choi_thi_nem_ra_chu_khong_tra_danh_sach_rong(self):
        """Tra [] khi loi = man hinh bao "tep khong co quyen nao" - mot cau SAI, khong phai
        mot cau thieu."""
        ns = _nap(_Requests(_Resp(403, {})))
        with self.assertRaises(ns["SharePointChuaSan"]):
            ns["doc_quyen"]("ITEM")


class GioUTC(unittest.TestCase):
    def setUp(self):
        import datetime as _dt

        ns = {}
        exec(compile(_doan(_MIRROR, "gio_he_thong"), "<m>", "exec"), ns)

        def _get_datetime(txt):
            return _dt.datetime.strptime(txt, "%Y-%m-%d %H:%M:%S")

        def _convert(d):
            # Ham THAT cua Frappe tra ve datetime CO tzinfo. Ban gia luc dau tra ve gio tran
            # nen phep kiem "da bo tzinfo chua" khong do duoc gi - dot bien xoa
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
    unittest.main(verbosity=1)
