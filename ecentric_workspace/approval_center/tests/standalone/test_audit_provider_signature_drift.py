# Copyright (c) 2026, eCentric and contributors
"""Soi lech: phieu nao co chu ky ben SCTS ma ERP chua dung.

BOI CANH (09/09/2026). EC-PAYR-2026-00051 treo o "HOF Review" trong khi tai lieu ben SCTS da
"Da ket thuc" - HOF ky luc 08:20, CEO luc 13:08, khong ai bam gi tren ERP. Loai su co nay VO
HINH: trang van hanh chi liet ke CHAN KY bi ket, ma o day chua bao gio co chan ky nao duoc
tao. Toi da quet "con phieu nao ket khong" va tra loi "chi con 00053" - cau do chi dung voi
nhung phieu CO chan ky, va toi khong noi ra gioi han do.

HAI DIEU BO TEST NAY GIU, ca hai deu la bai hoc phai tra gia:

  1. DEM, khong khop theo email. Mot nguoi vua trinh ky vua duyet cap 1 thi email ho xuat
     hien tren tai lieu du ERP DA dung chu ky do roi. Phep quet ngay tho cua toi bao dong gia
     dung 3 phieu (00045/00049/00050) chieu 09/09; phep dung la so SO CHU KY voi SO CHAN KY
     DA HOAN TAT cua chinh nguoi do.

  2. "Hoi duoc va SACH" KHAC "KHONG HOI DUOC". Gop lam mot la lap lai dung cai loi im lang
     da lam mat hai dem cua thang 8 - va cung la loi cua chinh cong QC sang nay (thieu `node`
     bi bao thanh "23 test hong").
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_SVC = ("platform", "esign", "service.py")
_BASE = "ecentric_workspace.platform.esign.providers.base"
_SAN = "ecentric_workspace.platform.esign.sanitize"


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _fn(name):
    return next(n for n in ast.parse(_read(*_SVC)).body
                if isinstance(n, ast.FunctionDef) and n.name == name)


class _Throw(Exception):
    pass


def _run(signers, legs, pending=("hof@ec.vn",), level=3, doc_id="doc-1", poll_raises=False,
         profiles=(("EC Payment Request", "PAYMENT_REQUEST"),)):
    """Chay THAT ham audit voi mot phieu duy nhat."""
    class _FK(object):
        @staticmethod
        def get_all(dt, filters=None, fields=None, pluck=None, limit_page_length=None):
            if dt == "EC Digital Signature Profile":
                return [{"business_doctype": d, "approval_type": a} for d, a in profiles]
            if dt == "EC Approval Request":
                return [{"name": "EC-APR-1", "reference_doctype": "EC Payment Request",
                         "reference_name": "EC-PAYR-2026-00051", "current_level": level}]
            if dt == "EC Digital Signature Request":
                return [{"approver": a} for a in legs]
            if dt == "EC Approval Request Approver":
                return list(pending)
            raise AssertionError("doctype la: %s" % dt)

        class db(object):
            @staticmethod
            def get_value(dt, name, field, **kw):
                return doc_id if dt == "EC Digital Signature Package" else "PAYMENT_REQUEST"

    class _Adapter(object):
        @staticmethod
        def poll_status(d):
            if poll_raises:
                raise RuntimeError("cong khong tra loi")
            return types.SimpleNamespace(signers=list(signers))

    fake_base = types.ModuleType(_BASE)
    fake_base.SignatureProviderAdapter = object
    fake_san = types.ModuleType(_SAN)
    fake_san.safe_error = lambda e: "loi-da-lam-sach"

    ns = {"frappe": _FK, "_": lambda s: s,
          "perms": types.SimpleNamespace(assert_system_manager=lambda: None),
          "pkgsvc": types.SimpleNamespace(active_package_for_request=lambda r: "EC-DSP-1"),
          "_profile_doc": lambda dt, at: {"x": 1}, "_settings_for": lambda p: {"y": 1},
          "get_adapter": lambda s: _Adapter,
          "DSR": "EC Digital Signature Request"}
    saved = {k: sys.modules.get(k) for k in (_BASE, _SAN)}
    sys.modules[_BASE], sys.modules[_SAN] = fake_base, fake_san
    try:
        # Tu 09/09 loi cua phep soi lech nam o `_audit_drift`; `audit_provider_signature_drift`
        # chi con la vo: `assert_system_manager()` roi goi xuong. Tach ra de cong viec dinh ky
        # (chay duoi Administrator, khong co nguoi nao bam) khong phai di qua hang rao quyen.
        # Nap DUNG cai vo thi bo test nay chay tren hai dong va khong kiem gi ca.
        exec(compile(ast.Module(body=[_fn("_audit_drift")], type_ignores=[]),
                     "service.py", "exec"), ns)
        return ns["_audit_drift"]()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _s(email, status="signed"):
    return {"email": email, "status": status}


class TestDemChuKhongKhopEmail(unittest.TestCase):
    """Bai hoc 09/09: phep quet khop theo email bao dong gia 3 phieu."""

    def test_da_dung_het_chu_ky_thi_KHONG_bao(self):
        """Nguoi trinh ky = nguoi duyet cap 1: 1 chu ky, 1 chan da xong -> khong du."""
        out = _run(signers=[_s("hoan@ec.vn")], legs=["hoan@ec.vn"], pending=("hoan@ec.vn",))
        self.assertEqual(out["drift"], [], "khop theo email se bao nham o day")
        self.assertEqual(out["checked"], 1)

    def test_con_du_mot_chu_ky_thi_BAO(self):
        out = _run(signers=[_s("hof@ec.vn")], legs=[], pending=("hof@ec.vn",))
        self.assertEqual(len(out["drift"]), 1)
        d = out["drift"][0]
        self.assertEqual(d["approver"], "hof@ec.vn")
        self.assertEqual((d["signatures"], d["completed_legs"], d["surplus"]), (1, 0, 1))

    def test_hai_chu_ky_mot_chan_thi_van_con_du_mot(self):
        out = _run(signers=[_s("a@ec.vn"), _s("a@ec.vn")], legs=["a@ec.vn"],
                   pending=("a@ec.vn",))
        self.assertEqual(out["drift"][0]["surplus"], 1)

    def test_chu_ky_CHUA_ky_thi_khong_tinh(self):
        out = _run(signers=[_s("hof@ec.vn", "pending")], legs=[], pending=("hof@ec.vn",))
        self.assertEqual(out["drift"], [])

    def test_dong_thieu_email_thi_bo_qua_chu_khong_no(self):
        out = _run(signers=[{"status": "signed"}, _s("hof@ec.vn")], legs=[],
                   pending=("hof@ec.vn",))
        self.assertEqual(len(out["drift"]), 1)


class TestXuLyDuocNgayHayChua(unittest.TestCase):
    def test_dang_cho_o_cap_hien_tai_thi_xu_ly_duoc_ngay(self):
        out = _run(signers=[_s("hof@ec.vn")], legs=[], pending=("hof@ec.vn",))
        self.assertTrue(out["drift"][0]["actionable_now"])

    def test_ky_TRUOC_cho_cap_sau_thi_KHONG_phai_viec_bay_gio(self):
        """Ho ky som cho mot cap chua toi luot: de yen, chu ky do se duoc dung khi toi luot.
        Dong bo som la nhay cap."""
        out = _run(signers=[_s("ceo@ec.vn")], legs=[], pending=("hof@ec.vn",))
        self.assertEqual(len(out["drift"]), 1)
        self.assertFalse(out["drift"][0]["actionable_now"])


class TestHoiDuocSachKHACKhongHoiDuoc(unittest.TestCase):
    """Gop hai cai nay lam mot la lap lai loi im lang cua thang 8."""

    def test_khong_hoi_duoc_thi_vao_danh_sach_RIENG(self):
        out = _run(signers=[], legs=[], poll_raises=True)
        self.assertEqual(out["drift"], [])
        self.assertEqual(len(out["unreadable"]), 1)
        self.assertEqual(out["unreadable"][0]["business_name"], "EC-PAYR-2026-00051")
        self.assertEqual(out["checked"], 0, "khong hoi duoc thi KHONG duoc dem la da xet")

    def test_loi_da_duoc_lam_sach_truoc_khi_tra_ra(self):
        out = _run(signers=[], legs=[], poll_raises=True)
        self.assertEqual(out["unreadable"][0]["error"], "loi-da-lam-sach")

    def test_hoi_duoc_va_sach_thi_checked_van_tang(self):
        out = _run(signers=[_s("a@ec.vn")], legs=["a@ec.vn"])
        self.assertEqual(out["checked"], 1)
        self.assertEqual(out["unreadable"], [])


class TestPhamVi(unittest.TestCase):
    def test_khong_co_profile_nao_bat_thi_noi_ro(self):
        out = _run(signers=[], legs=[], profiles=())
        self.assertEqual(out["reason"], "no_enabled_profile")
        self.assertEqual(out["checked"], 0)

    def test_goi_chua_co_tai_lieu_thi_bo_qua_khong_hoi(self):
        out = _run(signers=[], legs=[], doc_id=None)
        self.assertEqual(out["checked"], 0)
        self.assertEqual(out["drift"], [])
        self.assertEqual(out["unreadable"], [], "khong co tai lieu != khong hoi duoc")

    def test_chi_xet_phieu_DANG_CHO(self):
        src = ast.unparse(_fn("_audit_drift"))
        self.assertIn("Pending", src)
        self.assertIn("Information Required", src)

    def test_KHONG_GHI_GI(self):
        """Day la duong chan doan. Mot dong ghi o day la mot tac dung phu khong ai ngo.

        Kiem CA HAI: cai vo co hang rao quyen VA cai loi. Chi kiem mot cai thi lan sau ai do
        them mot dong ghi vao nua kia ma khong bi chan."""
        src = "\n".join(ast.unparse(_fn(n))
                        for n in ("audit_provider_signature_drift", "_audit_drift"))
        for cam in ("set_value", "insert(", "db_set", "save(", "enqueue", "set_dsr_status",
                    "mark_verified", "engine.approve"):
            self.assertNotIn(cam, src, cam)

    def test_diem_vao_API_la_GET_va_chi_System_Manager(self):
        src = _read("platform", "esign", "api.py")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "audit_provider_signature_drift")
        deco = " ".join(ast.unparse(d) for d in fn.decorator_list)
        self.assertIn("whitelist", deco)
        self.assertNotIn("POST", deco, "chi doc thi khong can POST")
        self.assertIn("assert_system_manager", ast.unparse(fn))


if __name__ == "__main__":
    unittest.main()
