# Copyright (c) 2026, eCentric and contributors
"""20/11/2026 EC-CTR-2026-00122: createLink(scope=users) tra 400 noResolvedUsers neu MOT dia chi khong co
tai khoan Microsoft 365 -> ca lo hong, .docx mat "Mo online" (moi phieu cua anh.luu tu 09/10). cap_quyen
phai cap TUNG NGUOI khi gap loi do: nguoi resolve duoc van co quyen, nguoi hong vao bo_qua + log.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_sp_cap_quyen_bo_nguoi_khong_resolve.py
"""
import types
import unittest

from test_sharepoint_mirror import _MIRROR, _doan

NO_RES = '{"error":{"code":"noResolvedUsers","message":"x"}}'


class _Resp(object):
    def __init__(self, code, text="", link=None):
        self.status_code, self.text, self._link = code, text, link

    def json(self):
        return {"link": {"webUrl": self._link}} if self._link else {}


class _Req(object):
    def __init__(self, hong=(), loi_khac=None):
        self.hong, self.loi_khac, self.goi = set(hong), loi_khac, []

    def post(self, url, headers=None, json=None, timeout=None):
        ai = [r["email"] for r in json["recipients"]]
        self.goi.append(ai)
        if self.loi_khac and self.loi_khac in ai:
            return _Resp(500, "boom")
        if any(a in self.hong for a in ai):
            return _Resp(400, NO_RES)
        return _Resp(200, "", link="https://sp/link")


def _nap(req):
    log = []

    class SharePointChuaSan(Exception):
        pass
    ns = {"_requests": lambda: req, "_graph": lambda: "https://g", "TIMEOUT": 5,
          "wr_sp": types.SimpleNamespace(SITE_ID="S", get_app_token=lambda: "T"),
          "TAI_KHOAN_DICH_VU": ("fabric.bot",), "SharePointChuaSan": SharePointChuaSan,
          "frappe": types.SimpleNamespace(log_error=lambda *a, **k: log.append(a))}
    exec(compile(_doan(_MIRROR, "loc_nguoi_that", "cap_quyen", "_khong_resolve"), "<m>", "exec"), ns)
    return ns, log


class CapTungNguoiKhiCoNguoiKhongResolve(unittest.TestCase):
    def test_ca_lo_ok_thi_mot_lan_goi(self):
        req = _Req()
        ns, log = _nap(req)
        r = ns["cap_quyen"]("I", ["a@x.vn", "b@x.vn"], token="T")
        self.assertEqual(r["da_cap"], ["a@x.vn", "b@x.vn"])
        self.assertEqual(len(req.goi), 1)
        self.assertEqual(log, [])

    def test_mot_nguoi_hong_thi_van_cap_cho_nguoi_con_lai(self):
        req = _Req(hong={"anh.luu@x.vn"})
        ns, log = _nap(req)
        r = ns["cap_quyen"]("I", ["anh.luu@x.vn", "kieu@x.vn", "lien@x.vn", "fabric.bot@x.vn"], token="T")
        self.assertEqual(r["da_cap"], ["kieu@x.vn", "lien@x.vn"])
        self.assertIn("anh.luu@x.vn", r["bo_qua"])
        self.assertIn("fabric.bot@x.vn", r["bo_qua"])
        self.assertEqual(r["link"], "https://sp/link")
        self.assertTrue(log and "anh.luu@x.vn" in log[0][0])

    def test_khong_ai_resolve_thi_nem_nhu_cu(self):
        req = _Req(hong={"a@x.vn", "b@x.vn"})
        ns, _ = _nap(req)
        with self.assertRaises(ns["SharePointChuaSan"]):
            ns["cap_quyen"]("I", ["a@x.vn", "b@x.vn"], token="T")

    def test_loi_khac_khong_phai_noResolvedUsers_thi_nem(self):
        req = _Req(hong={"a@x.vn"}, loi_khac="b@x.vn")
        ns, _ = _nap(req)
        with self.assertRaises(ns["SharePointChuaSan"]):
            ns["cap_quyen"]("I", ["a@x.vn", "b@x.vn"], token="T")

    def test_mot_nguoi_duy_nhat_hong_thi_nem(self):
        req = _Req(hong={"a@x.vn"})
        ns, _ = _nap(req)
        with self.assertRaises(ns["SharePointChuaSan"]):
            ns["cap_quyen"]("I", ["a@x.vn"], token="T")


if __name__ == "__main__":
    unittest.main()
