# Copyright (c) 2026, eCentric and contributors
"""Tu dung anh xa chu ky SCTS ngay khi nguoi dung ket noi - va chi khi CHAC CHAN.

BOI CANH (09/09/2026). Tam (tam.nguyen) tao tai khoan SCTS xong, len ERP khong thay nut "Ket
noi SCTS" o Approval Center. Nut do co dieu kien hien la `needs_link && has_mapping` -
`has_mapping` = da co dong `EC SCTS User Mapping`. Nguoi CHUA TUNG ket noi thi chua co dong
nao, nen dung nhom can nut nhat lai la nhom bi AN nut, va khong mot dong chu nao noi vi sao.
Va o trong form, `link()` cung nem loi ngay tu dau ("Nho quan tri tao truoc") - tuc no tu
choi TRUOC ca khi ERP kip biet nguoi do la ai ben SCTS.

Hoan chot: bo buoc quan tri go tay `scts_user_id` + `signature_id`.

Cai bi bo KHONG phai phep xac minh danh tinh - dang nhap SCTS thanh cong da chung minh nguoi
do nam tai khoan do, chat hon la mot quan tri go GUID bang tay. Cai bi bo la chot "quan tri
quyet dinh ai duoc ky". De bu lai, bo test nay giu bon rang buoc:

  1. MOI gia tri lay tu SCTS, khong tu nguoi dung khai.
  2. Chi `Verified` khi co DUNG MOT mau chu ky KY DUOC TU MAY CHU. `signToken=1` (ky bang
     token cam tai may) hay khong co HSM deu KHONG tinh - tao anh xa tro vao mau do thi no
     van "Verified" nhung den luc ky se "nhan 2xx roi im", dung cai loi da ton hai dem cua
     thang 8.
  3. Khong ro (0 mau ky duoc, hoac nhieu hon 1) thi tao BAN NHAP va noi ro phai lam gi -
     khong bao gio doan.
  4. Khong doc duoc `userId` thi noi ra payload co nhung KHOA gi - va TUYET DOI khong lo
     token/mat khau ra thong diep hay su kien.
"""
import ast
import base64
import io
import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_UL = ("platform", "esign", "user_link.py")


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


class _Throw(Exception):
    pass


def _load(names, ns_extra=None):
    """Nap RIENG cac ham can thu (ca hang so cap module chung dung), chay THAT.
    exec(compile(...)) chu khong import: user_link keo theo ca chuc module Frappe, va
    __pycache__ tung lam moi phep dot bien song sot (bai hoc 31/08)."""
    src = _read(*_UL)
    tree = ast.parse(src)
    want = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in names:
            want.append(n)
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id.startswith("_UID") for t in n.targets):
            want.append(n)
    want.sort(key=lambda n: n.lineno)
    ns = dict(ns_extra or {})
    ns.setdefault("_", lambda s: s)
    exec(compile(ast.Module(body=want, type_ignores=[]), "user_link.py", "exec"), ns)
    return ns


def _jwt(claims):
    seg = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return "header." + seg + ".chuky"


_UID = "f714b8bf-c7ca-40d8-953a-d5aa84a3cf49"
_SIG = "2ffbc66b-964c-4b58-827a-74f9e71b883d"
_TOKEN = "day-la-token-KHONG-duoc-lo"


def _sig(**kw):
    base = {"id": _SIG, "signerId": _UID, "type": "ky-tham-gia", "company": "ECENTRIC",
            "active": True, "has_hsm": True, "sign_token": None}
    base.update(kw)
    return base


class TestDocUserIdTuPhanHoi(unittest.TestCase):
    """Chua ai nhin thay payload dang nhap that (muon thay phai co mat khau cua mot nguoi
    thuc). Nen ham do NHIEU kha nang, va bao ra khi khong thay - khong chot mot khoa."""

    def setUp(self):
        self.ns = _load(("_dig", "_uid_from_jwt", "_provider_user_id"))

    def test_cap_ngoai(self):
        for k in ("userId", "userID", "user_id", "id", "guid"):
            self.assertEqual(self.ns["_provider_user_id"]({k: _UID}, None), _UID, k)

    def test_boc_trong_data(self):
        """eContract boc trong `data` - da dinh mot lan o `expiresInMinutes` (04/09): doc o
        cap ngoai nen luon None, dan toi DANG NHAP LAI TRUOC MOI LENH suot 7 tuan."""
        self.assertEqual(self.ns["_provider_user_id"]({"data": {"userId": _UID}}, None), _UID)

    def test_boc_trong_user(self):
        self.assertEqual(self.ns["_provider_user_id"]({"user": {"id": _UID}}, None), _UID)

    def test_lui_ve_claim_cua_JWT(self):
        for claim in ("sub", "nameid", "userId"):
            tok = _jwt({claim: _UID})
            self.assertEqual(self.ns["_provider_user_id"]({"token": tok}, tok), _UID, claim)

    def test_JWT_thieu_dau_bang_van_giai_duoc(self):
        """base64url thuong bi cat `=` - khong bu lai thi hong, va hong o day nghia la moi
        nguoi dung moi deu ket noi that bai."""
        for n in range(1, 6):
            tok = _jwt({"sub": _UID + "x" * n})
            self.assertTrue(self.ns["_uid_from_jwt"](tok), "do dai le %d" % n)

    def test_khong_thay_thi_tra_None_chu_khong_no(self):
        for raw, tok in (({}, None), (None, None), ({"a": 1}, "khong-phai-jwt"),
                         ({"data": {}}, "a.b.c")):
            self.assertIsNone(self.ns["_provider_user_id"](raw, tok), repr(raw))

    def test_KHONG_nham_token_thanh_userId(self):
        """`token` khong nam trong danh sach khoa - neu lot, ERP se ghi ca token vao mot
        truong Data khong ma hoa cua anh xa."""
        self.assertIsNone(self.ns["_provider_user_id"]({"token": "abc", "expiresIn": 5}, None))


class TestChonChuKyKyDuoc(unittest.TestCase):
    def setUp(self):
        self.f = _load(("_usable_signatures",))["_usable_signatures"]

    def test_mau_binh_thuong_thi_lay(self):
        self.assertEqual(len(self.f([_sig()])), 1)

    def test_signToken_1_thi_LOAI(self):
        """Ky bang token cam tai may qua OfficeSignTool - ERP khong ky thay duoc."""
        self.assertEqual(self.f([_sig(sign_token=1)]), [])

    def test_khong_co_HSM_thi_LOAI(self):
        self.assertEqual(self.f([_sig(has_hsm=False)]), [])

    def test_khong_active_thi_LOAI(self):
        self.assertEqual(self.f([_sig(active=False)]), [])

    def test_thieu_id_thi_LOAI(self):
        self.assertEqual(self.f([_sig(id=None)]), [])

    def test_signToken_0_van_lay(self):
        """0 = ky duoc tu may chu. Chi ENG 1 moi la loai tru."""
        self.assertEqual(len(self.f([_sig(sign_token=0)])), 1)

    def test_danh_sach_rong_hoac_None(self):
        self.assertEqual(self.f([]), [])
        self.assertEqual(self.f(None), [])


class _Doc(dict):
    def __init__(self, d):
        super(_Doc, self).__init__(d)
        self.name = "EC-DSM-00099"
        self.inserted = False
        self.set_values = {}

    def insert(self, **kw):
        self.inserted = True

    def db_set(self, vals):
        self.set_values.update(vals)


def _auto(sigs, raw=None, token=_TOKEN, uid_ok=True):
    made = {}

    class _FK(object):
        session = type("s", (), {"user": "admin@ec.vn"})()

        @staticmethod
        def throw(msg, *a, **kw):
            raise _Throw(str(msg))

        @staticmethod
        def get_doc(d):
            made["doc"] = _Doc(d)
            return made["doc"]

    class _Ev(object):
        @staticmethod
        def emit(t, **kw):
            made.setdefault("events", []).append((t, kw))

    class _Ad(object):
        @staticmethod
        def list_user_signatures(uid):
            made["asked_uid"] = uid
            return sigs

    ns = _load(("_dig", "_uid_from_jwt", "_provider_user_id", "_usable_signatures",
                "_auto_create_mapping"),
               {"frappe": _FK, "events": _Ev, "now_datetime": lambda: "2026-09-09 15:00:00",
                "MAPPING_DT": "EC SCTS User Mapping",
                "_token_row": lambda u, e: {"name": made.get("doc").name if made.get("doc") else None}})
    if raw is None:
        raw = {"userId": _UID} if uid_ok else {"expiresInMinutes": 525600, "token": token}
    try:
        out = ns["_auto_create_mapping"]("tam.nguyen@ec.vn", "UAT", _Ad, raw, token, "nv00129")
        return made, out, None
    except _Throw as e:
        return made, None, str(e)


class TestTuDungAnhXa(unittest.TestCase):
    def test_dung_MOT_mau_ky_duoc_thi_Verified(self):
        made, out, err = _auto([_sig()])
        self.assertIsNone(err, err)
        doc = made["doc"]
        self.assertTrue(doc.inserted)
        self.assertEqual(doc["scts_user_id"], _UID)
        self.assertEqual(doc["signature_id"], _SIG)
        self.assertEqual(doc["frappe_user"], "tam.nguyen@ec.vn")
        self.assertEqual(doc["environment"], "UAT")
        self.assertEqual(doc.set_values.get("mapping_status"), "Verified")

    def test_hoi_SCTS_bang_dung_uid_vua_doc_duoc(self):
        made, _o, _e = _auto([_sig()])
        self.assertEqual(made["asked_uid"], _UID)

    def test_tao_ra_luon_o_trang_thai_Draft_TRUOC_khi_xac_minh(self):
        """Chen thang `Verified` thi mot loi giua chung se de lai anh xa da xac minh ma
        chua ai kiem chu ky."""
        made, _o, _e = _auto([_sig()])
        self.assertEqual(made["doc"]["mapping_status"], "Draft")

    def test_KHONG_co_mau_ky_duoc_thi_KHONG_Verified(self):
        for bad in (_sig(sign_token=1), _sig(has_hsm=False)):
            made, out, err = _auto([bad])
            self.assertIsNone(out)
            self.assertIn("chứng thư", err)
            self.assertNotEqual(made["doc"].set_values.get("mapping_status"), "Verified")

    def test_NHIEU_mau_ky_duoc_thi_khong_doan_ho(self):
        """Anh Lam co hai `ky-chinh`; doan bua la ky bang mau sai."""
        made, out, err = _auto([_sig(), _sig(id="mau-B")])
        self.assertIsNone(out)
        self.assertIn("không tự", err)
        self.assertNotEqual(made["doc"].set_values.get("mapping_status"), "Verified")

    def test_khong_doc_duoc_userId_thi_noi_ro_va_KHONG_tao_gi(self):
        made, out, err = _auto([_sig()], uid_ok=False)
        self.assertIsNone(out)
        self.assertNotIn("doc", made, "chua biet la ai thi khong duoc tao anh xa")
        self.assertIn("expiresInMinutes", err, "phai liet ke khoa de lan sau biet doc o dau")

    def test_TUYET_DOI_khong_lo_token(self):
        """Thong diep loi va su kien deu di ra ngoai (nguoi dung / Error Log). Token la bi
        mat song mot nam."""
        made, _o, err = _auto([_sig()], uid_ok=False)
        self.assertNotIn(_TOKEN, err or "")
        self.assertNotIn(_TOKEN, json.dumps(made.get("events") or [], default=str))

    def test_ghi_su_kien_khi_tao_thanh_cong(self):
        made, _o, _e = _auto([_sig()])
        kinds = [t for t, _kw in (made.get("events") or [])]
        self.assertIn("UserMappingAutoCreated", kinds)


class TestThuTuTrongLink(unittest.TestCase):
    """DANG NHAP TRUOC, roi moi lo chuyen anh xa - do la ca diem cua ban sua."""

    def test_khong_con_tu_choi_ngay_tu_dau_khi_chua_co_anh_xa(self):
        src = _read(*_UL)
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "link")
        self.assertNotIn("Bạn chưa có ánh xạ chữ ký SCTS được xác minh", fn,
                         "cau tu choi cu phai bien mat, khong thi nguoi moi van bi chan")
        i_login = fn.index("adapter._client.login")
        i_auto = fn.index("_auto_create_mapping")
        self.assertLess(i_login, i_auto, "phai dang nhap TRUOC khi tao anh xa")

    def test_mat_khau_khong_di_vao_su_kien_hay_anh_xa(self):
        src = _read(*_UL)
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "link")
        sau = fn[fn.index("adapter._client.login"):]
        self.assertNotIn("password", sau.replace("password)", ""),
                         "sau khi dang nhap, mat khau khong duoc xuat hien o dau nua")


class TestNutTrenHub(unittest.TestCase):
    def test_khong_con_doi_has_mapping(self):
        html = _read("approval_center", "ui", "hub", "main_section.html")
        self.assertNotIn("st.needs_link && st.has_mapping", html,
                         "dieu kien cu an nut voi dung nhom can no nhat")
        self.assertIn("st && st.needs_link)", html)

    def test_co_patch_resync_va_da_khai(self):
        self.assertIn("p169_resync_hub_scts_button_no_mapping", _read("patches.txt"))


if __name__ == "__main__":
    unittest.main()
