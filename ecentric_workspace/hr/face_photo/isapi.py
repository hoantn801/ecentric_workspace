# Copyright (c) 2026, eCentric and contributors
"""Goi ISAPI may Hikvision (DS-K1T341CMFW / MinMoe) tu ERP: them nguoi, nap mat, xoa nguoi.

KHONG import frappe (test khong can bench). `http` = doi tuong co .request(method, url, **kw)
(requests.Session that, hoac gia lap trong test).

May dung chung chi tu ky -> khong xac minh CA duoc. Thay vao do GHIM VAN TAY chung chi
(sha256): cau hinh co `fingerprint` ma may tra chung chi khac -> DUNG, khong gui mat khau.
"""
import hashlib
import json

USER_BEGIN = "2026-01-01T00:00:00"
USER_END = "2037-12-31T23:59:59"
FDID = "1"
FACE_LIB = "blackFD"
PAGE = 30
NAME_MAX = 32


class DeviceError(Exception):
    """Loi doc duoc, tieng Viet, dua thang len trang HR."""


def fingerprint_of(der):
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def norm_fp(s):
    return "".join(ch for ch in str(s or "").upper() if ch in "0123456789ABCDEF")


def _ok(body):
    """ISAPI JSON: statusCode 1 = OK. Mot so lenh tra rong khi OK."""
    if not body:
        return True, ""
    try:
        d = json.loads(body)
    except ValueError:
        return False, body[:200]
    code = d.get("statusCode")
    if code in (None, 1, "1"):
        return True, ""
    return False, "%s/%s" % (d.get("statusString") or "", d.get("subStatusCode") or "")


class Device(object):
    def __init__(self, cfg, http, cert_der=None, timeout=15):
        self.name = str(cfg.get("name") or "?")
        self.base = str(cfg.get("url") or "").rstrip("/")
        self.user = str(cfg.get("user") or "admin")
        self.password = str(cfg.get("password") or "")
        self.want_fp = norm_fp(cfg.get("fingerprint"))
        self.http = http
        self.cert_der = cert_der        # callable(host, port) -> bytes DER
        self.timeout = timeout
        self.seen_fp = ""
        self._checked = False
        if not self.base.startswith("https://"):
            raise DeviceError("Máy %s: url phải là https://IP:cổng" % self.name)
        if not self.password:
            raise DeviceError("Máy %s: chưa có mật khẩu trong cấu hình" % self.name)

    # ---------------- ket noi ----------------
    def _hostport(self):
        rest = self.base[len("https://"):].split("/", 1)[0]
        if ":" in rest:
            h, p = rest.rsplit(":", 1)
            return h, int(p)
        return rest, 443

    def check_cert(self):
        if self._checked or not self.cert_der:
            return
        try:
            der = self.cert_der(*self._hostport())
        except Exception as e:
            raise DeviceError("Không kết nối được máy %s (%s). Kiểm tra router đã mở cổng, máy đang bật."
                              % (self.name, type(e).__name__))
        self.seen_fp = fingerprint_of(der)
        if self.want_fp and norm_fp(self.seen_fp) != self.want_fp:
            raise DeviceError("Máy %s: chứng chỉ không khớp vân tay đã ghim - dừng, không gửi mật khẩu."
                              % self.name)
        self._checked = True

    def call(self, method, path, body=None, files=None):
        self.check_cert()
        from requests.auth import HTTPDigestAuth
        kw = {"auth": HTTPDigestAuth(self.user, self.password), "timeout": self.timeout,
              "verify": False}
        if files is not None:
            kw["files"] = files
        elif body is not None:
            kw["data"] = json.dumps(body)
            kw["headers"] = {"Content-Type": "application/json"}
        try:
            r = self.http.request(method, self.base + path, **kw)
        except Exception as e:
            raise DeviceError("Không kết nối được máy %s (%s)." % (self.name, type(e).__name__))
        if r.status_code == 401:
            raise DeviceError("Máy %s từ chối đăng nhập (sai tài khoản / mật khẩu). Sửa cấu hình - "
                              "sai nhiều lần máy sẽ tạm khoá." % self.name)
        text = r.text or ""
        ok, why = _ok(text) if r.status_code < 400 else (False, "")
        if r.status_code >= 400:
            ok2, why2 = _ok(text)
            why = why2 or ("HTTP %d" % r.status_code)
        return ok, why, text

    # ---------------- nguoi ----------------
    def list_users(self):
        """-> {employeeNo: name}."""
        out, pos = {}, 0
        for _ in range(200):
            ok, why, text = self.call("POST", "/ISAPI/AccessControl/UserInfo/Search?format=json", {
                "UserInfoSearchCond": {"searchID": "ec", "searchResultPosition": pos,
                                       "maxResults": PAGE}})
            if not ok:
                raise DeviceError("Máy %s: không đọc được danh sách người (%s)" % (self.name, why))
            d = (json.loads(text or "{}").get("UserInfoSearch") or {})
            for u in d.get("UserInfo") or []:
                out[str(u.get("employeeNo"))] = u.get("name") or ""
            n = int(d.get("numOfMatches") or 0)
            pos += n
            if n == 0 or str(d.get("responseStatusStrg")) != "MORE":
                break
        return out

    @staticmethod
    def user_body(no, name):
        return {"UserInfo": {
            "employeeNo": str(no), "name": (name or "NV")[:NAME_MAX], "userType": "normal",
            "Valid": {"enable": True, "beginTime": USER_BEGIN, "endTime": USER_END,
                      "timeType": "local"},
            "doorRight": "1", "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}]}}

    def upsert_user(self, no, name, exists):
        body = self.user_body(no, name)
        if exists:
            ok, why, _ = self.call("PUT", "/ISAPI/AccessControl/UserInfo/Modify?format=json", body)
        else:
            ok, why, _ = self.call("POST", "/ISAPI/AccessControl/UserInfo/Record?format=json", body)
            if not ok and "AlreadyExist" in why:
                ok, why, _ = self.call("PUT", "/ISAPI/AccessControl/UserInfo/Modify?format=json", body)
        if not ok:
            raise DeviceError("thêm/sửa người lỗi: %s" % why)

    def set_face(self, no, jpeg):
        meta = json.dumps({"faceLibType": FACE_LIB, "FDID": FDID, "FPID": str(no)})

        def files():
            return {"FaceDataRecord": (None, meta, "application/json"),
                    "img": ("%s.jpg" % no, jpeg, "image/jpeg")}
        # FDSetUp = them hoac thay. May cu khong co -> xoa mat cu roi them.
        ok, why, _ = self.call("PUT", "/ISAPI/Intelligent/FDLib/FDSetUp?format=json", files=files())
        if ok:
            return
        ok, why2, _ = self.call("POST", "/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json", files=files())
        if not ok and "Exist" in why2:
            self.call("PUT", "/ISAPI/Intelligent/FDLib/FDSearch/Delete?format=json&FDID=%s&faceLibType=%s"
                      % (FDID, FACE_LIB), {"FPID": [{"value": str(no)}]})
            ok, why2, _ = self.call("POST", "/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json",
                                    files=files())
        if not ok:
            raise DeviceError("máy không nhận ảnh: %s" % (why2 or why))

    def delete_users(self, nos):
        if not nos:
            return
        ok, why, _ = self.call("PUT", "/ISAPI/AccessControl/UserInfo/Delete?format=json", {
            "UserInfoDelCond": {"EmployeeNoList": [{"employeeNo": str(n)} for n in nos]}})
        if not ok:
            raise DeviceError("xoá người lỗi: %s" % why)


def plan(erp, device_users, state):
    """Tinh viec can lam cho MOT may.

    erp: {"active": [{no, name, photo}], "left": set(no)}  - photo = khoa anh (ten File) hoac ""
    device_users: {no: name} tren may.  state: {no: photo da day thanh cong | "fail:<photo>"}.
    -> {"user": [(no, name, exists)], "face": [(no, photo)], "delete": [no]}

    CHI xoa nguoi ERP biet la DA NGHI. Nguoi tren may ma ERP khong biet (khach, bao ve, the
    tam...) -> KHONG dung toi. Nguoi chua co anh -> chua them (may khong mo cua cho ho duoc).
    """
    users, faces = [], []
    for r in erp.get("active") or []:
        no, name, photo = str(r["no"]), r["name"], r.get("photo") or ""
        if not photo:
            continue
        exists = no in device_users
        if not exists or (device_users.get(no) or "") != name[:NAME_MAX]:
            users.append((no, name, exists))
        last = state.get(no) or ""
        if not exists or (last != photo and last != "fail:" + photo):
            faces.append((no, photo))
    left = {str(n) for n in (erp.get("left") or ())}
    delete = sorted(n for n in device_users if n in left)
    return {"user": users, "face": faces, "delete": delete}
