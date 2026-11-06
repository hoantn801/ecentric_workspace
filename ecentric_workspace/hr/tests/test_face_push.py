# Copyright (c) 2026, eCentric and contributors
"""ERP day khuon mat xuong may Hikvision (ec-face-push-v1). KHONG can bench, KHONG goi may that.

python -m unittest ecentric_workspace.hr.tests.test_face_push
"""
import json
import sys
import types
import unittest

from ecentric_workspace.hr.face_photo import isapi

CFG = {"name": "T1", "url": "https://1.2.3.4:44320", "user": "admin", "password": "x"}


class Resp(object):
    def __init__(self, code=200, body=None):
        self.status_code = code
        self.text = body if isinstance(body, str) else json.dumps(body if body is not None else {"statusCode": 1})


class FakeHttp(object):
    """Gia lap may: luu nguoi + mat, ghi lai moi lenh."""

    def __init__(self, users=None, no_setup=False, reject_face=(), code=None, busy_once=(), faces=None):
        self.users = dict(users or {})
        self.faces = dict(faces or {})
        self.busy_once = set(busy_once)
        self.calls = []
        self.no_setup = no_setup
        self.reject_face = set(reject_face)
        self.code = code

    def request(self, method, url, **kw):
        path = url.split("1.2.3.4:44320", 1)[1]
        self.calls.append((method, path.split("?")[0]))
        if self.code:
            return Resp(self.code, "")
        body = json.loads(kw["data"]) if "data" in kw else None
        if path.startswith("/ISAPI/AccessControl/UserInfo/Search"):
            pos = body["UserInfoSearchCond"]["searchResultPosition"]
            items = sorted(self.users.items())[pos:pos + 2]
            more = pos + 2 < len(self.users)
            return Resp(200, {"UserInfoSearch": {"numOfMatches": len(items),
                                                 "responseStatusStrg": "MORE" if more else "OK",
                                                 "UserInfo": [{"employeeNo": k, "name": v, "numOfFace": 1 if k in self.faces else 0}
                                                              for k, v in items]}})
        if path.startswith("/ISAPI/AccessControl/UserInfo/Record"):
            no = body["UserInfo"]["employeeNo"]
            if no in self.users:
                return Resp(400, {"statusCode": 6, "statusString": "Invalid Content",
                                  "subStatusCode": "employeeNoAlreadyExist"})
            self.users[no] = body["UserInfo"]["name"]
            return Resp()
        if path.startswith("/ISAPI/AccessControl/UserInfo/Modify"):
            self.users[body["UserInfo"]["employeeNo"]] = body["UserInfo"]["name"]
            return Resp()
        if path.startswith("/ISAPI/AccessControl/UserInfo/Delete"):
            for e in body["UserInfoDelCond"]["EmployeeNoList"]:
                self.users.pop(e["employeeNo"], None)
            return Resp()
        if path.startswith("/ISAPI/Intelligent/FDLib/FDSetUp") and self.no_setup:
            return Resp(404, {"statusCode": 4, "statusString": "Invalid Operation", "subStatusCode": "notSupport"})
        if path.startswith("/ISAPI/Intelligent/FDLib/FDSetUp") or path.startswith("/ISAPI/Intelligent/FDLib/FaceDataRecord"):
            meta = json.loads(kw["files"]["FaceDataRecord"][1])
            if meta["FPID"] in self.busy_once:
                self.busy_once.discard(meta["FPID"])
                return Resp(503, {"statusCode": 2, "statusString": "Device Busy", "subStatusCode": "deviceBusy"})
            if meta["FPID"] in self.reject_face:
                return Resp(400, {"statusCode": 6, "statusString": "Invalid Content", "subStatusCode": "faceModelingFailed"})
            self.faces[meta["FPID"]] = kw["files"]["img"][1]
            return Resp()
        return Resp(404, {"statusCode": 4, "subStatusCode": "notSupport"})


def ERP(active, left=()):
    return {"active": [{"no": n, "name": nm, "photo": p} for n, nm, p in active], "left": set(left)}


class TestPlan(unittest.TestCase):
    def test_them_moi_doi_anh_xoa_nguoi_nghi(self):
        erp = ERP([("70", "Dong Diep Huu", "F1"), ("74", "Thu Trinh Minh", "F2"), ("80", "Chua Gui", "")],
                  left=["5"])
        dev = {"74": "Thu Trinh Minh", "5": "Da Nghi", "999": "Bao ve"}
        p = isapi.plan(erp, dev, {"74": "F_old"})
        self.assertEqual(p["user"], [("70", "Dong Diep Huu", False)])
        self.assertEqual(p["face"], [("70", "F1"), ("74", "F2")])
        self.assertEqual(p["delete"], ["5"])            # KHONG dung toi "999" (ERP khong biet)

    def test_khong_lam_lai_viec_da_xong_hoac_anh_may_da_tu_choi(self):
        erp = ERP([("70", "A", "F1"), ("71", "B", "F2")])
        dev = {"70": {"name": "A", "faces": 1}, "71": {"name": "B", "faces": 0}}
        p = isapi.plan(erp, dev, {"70": "F1", "71": isapi.bad_mark("F2", "x")})
        self.assertEqual(p, {"user": [], "face": [], "delete": []})

    def test_may_bao_chua_co_mat_thi_day_lai(self):
        # 06/11: T1 co 42 nguoi nhung nhieu nguoi "Credential 0" du ERP ghi da day
        erp = ERP([("70", "A", "F1"), ("71", "B", "F2")])
        dev = {"70": {"name": "A", "faces": 0}, "71": {"name": "B", "faces": 1}}
        p = isapi.plan(erp, dev, {"70": "F1", "71": "fail:F2"})
        self.assertEqual(p["face"], [("70", "F1"), ("71", "F2")])   # fail: (v1) cung thu lai


class TestDevice(unittest.TestCase):
    def test_doc_danh_sach_nhieu_trang(self):
        http = FakeHttp({"1": "a", "2": "b", "3": "c", "4": "d", "5": "e"})
        self.assertEqual(len(isapi.Device(CFG, http).list_users()), 5)

    def test_them_trung_thi_sua(self):
        http = FakeHttp({"70": "Cu"})
        isapi.Device(CFG, http).upsert_user("70", "Moi", exists=False)
        self.assertEqual(http.users["70"], "Moi")

    def test_may_cu_khong_co_fdsetup(self):
        http = FakeHttp(no_setup=True)
        isapi.Device(CFG, http).set_face("70", b"JPG")
        self.assertEqual(http.faces["70"], b"JPG")

    def test_sai_mat_khau_bao_ro(self):
        with self.assertRaises(isapi.DeviceError) as cm:
            isapi.Device(CFG, FakeHttp(code=401)).list_users()
        self.assertIn("mật khẩu", str(cm.exception))

    def test_ghim_van_tay_sai_thi_khong_goi(self):
        http = FakeHttp()
        cfg = dict(CFG, fingerprint="AA:BB")
        dev = isapi.Device(cfg, http, cert_der=lambda h, p: b"cert-gia")
        with self.assertRaises(isapi.DeviceError):
            dev.list_users()
        self.assertEqual(http.calls, [])                 # chua gui mat khau
        ok = isapi.Device(dict(CFG, fingerprint=isapi.fingerprint_of(b"cert-gia")), http,
                          cert_der=lambda h, p: b"cert-gia")
        ok.list_users()
        self.assertTrue(http.calls)

    def test_cau_hinh_thieu(self):
        with self.assertRaises(isapi.DeviceError):
            isapi.Device(dict(CFG, url="http://1.2.3.4"), FakeHttp())
        with self.assertRaises(isapi.DeviceError):
            isapi.Device(dict(CFG, password=""), FakeHttp())


class TestSyncDevice(unittest.TestCase):
    def _push(self):
        import importlib
        fr = types.ModuleType("frappe")
        fr.conf = {}
        fr.log_error = lambda **k: None
        ut = types.ModuleType("frappe.utils")
        ut.now = lambda: "2026-11-05 16:00:00"
        fr.utils = ut
        sys.modules["frappe"] = fr
        sys.modules["frappe.utils"] = ut
        try:
            from ecentric_workspace.hr.face_photo import push
            return importlib.reload(push)
        finally:
            sys.modules.pop("frappe", None)
            sys.modules.pop("frappe.utils", None)

    def test_dong_bo_mot_may(self):
        push = self._push()
        http = FakeHttp({"5": "Da Nghi", "999": "Bao ve"}, reject_face={"71"})
        erp = ERP([("70", "A", "F1"), ("71", "B", "F2")], left=["5"])
        sys.modules["frappe.utils"] = push.frappe.utils
        try:
            state, st = push.sync_device(CFG, erp, {}, lambda f: b"IMG-" + f.encode(), http=http,
                                         cert_der=lambda h, p: b"c", sleep=lambda s: None)
        finally:
            sys.modules.pop("frappe.utils", None)
        self.assertTrue(st["ok"], st)
        self.assertEqual(sorted(http.users), ["70", "71", "999"])   # 5 nghi viec bi xoa
        self.assertEqual(http.faces, {"70": b"IMG-F1"})
        self.assertEqual(state["70"], "F1")
        self.assertTrue(isapi.is_bad(state["71"], "F2"))
        self.assertEqual((st["faces"], st["deleted"], st["on_device"], st["no_face"]), (1, 1, 3, 1))
        self.assertEqual([f["no"] for f in st["failed"]], ["71"])
        self.assertIn("faceModelingFailed", st["failed"][0]["why"])
        # lan sau: KHONG day lai anh bi tu choi, nhung VAN hien trong danh sach loi
        sys.modules["frappe.utils"] = push.frappe.utils
        try:
            state, st = push.sync_device(CFG, erp, state, lambda f: b"IMG-" + f.encode(), http=http,
                                         cert_der=lambda h, p: b"c", sleep=lambda s: None)
        finally:
            sys.modules.pop("frappe.utils", None)
        self.assertEqual(st["faces"], 0)
        self.assertEqual([f["no"] for f in st["failed"]], ["71"])

    def test_may_ban_thi_thu_lai(self):
        push = self._push()
        http = FakeHttp(busy_once={"70"})
        sys.modules["frappe.utils"] = push.frappe.utils
        try:
            state, st = push.sync_device(CFG, ERP([("70", "A", "F1")]), {}, lambda f: b"I", http=http,
                                         cert_der=lambda h, p: b"c", sleep=lambda s: None)
        finally:
            sys.modules.pop("frappe.utils", None)
        self.assertEqual((state, st["faces"], st["failed"]), ({"70": "F1"}, 1, []))

    def test_may_tat_khong_raise(self):
        push = self._push()
        sys.modules["frappe.utils"] = push.frappe.utils
        try:
            def down(h, p):
                raise OSError("timeout")
            state, st = push.sync_device(CFG, ERP([("70", "A", "F1")]), {}, lambda f: b"", http=FakeHttp(),
                                         cert_der=down)
        finally:
            sys.modules.pop("frappe.utils", None)
        self.assertFalse(st["ok"])
        self.assertIn("Không kết nối được", st["error"])
        self.assertEqual(state, {})


if __name__ == "__main__":
    unittest.main()
