# Copyright (c) 2026, eCentric and contributors
"""Nguoi XU LY phai duoc cap quyen DOC that su, khong chi duoc luat cua app cho phep.

BOI CANH (09/09/2026). Chi Dan (Role EC Finance, Fulfiller cua PAYMENT_REQUEST) bam vao
EC-PAYR-2026-00073 dang o buoc 1-2 thi nhan "Not permitted", va bam vao tep dinh kem thi web
server tra "Forbidden".

Nguyen nhan KHONG nam o luat cua app: `query_service.detail` dong 236 goi
`frappe.get_doc(business_doctype, name)` TRUOC khi hoi `can_view_request`. `get_doc` ap quyen
cua Frappe (DocPerm/DocShare). Ma `EC Payment Request` chi co DocPerm cho System Manager -
moi nguoi khac vao duoc la nho DocShare do engine cap. Engine cap cho NGUOI DUYET (08/09,
p163) va cho nguoi xu ly LUC BUOC XU LY KICH HOAT (kem ToDo). Truoc buoc do: khong ai cap gi.

Dung nguyen lop loi 08/09 (CEO khong mo duoc hop dong): app noi duoc, cong Frappe noi khong.
Va no thanh mau thuan hien ro tu 09/09, khi trang "Tat ca yeu cau" bat dau bay ra cho nguoi
xu ly MOI phieu cua loai ho phu trach - bay ra nhung dong bam vao khong mo duoc.

Bo test giu:
  1. `configured_fulfiller_users` bung dong Role ra thanh NGUOI (DocShare theo tung nguoi,
     khong nhan role), bo nguoi da nghi viec, va chi lay quy trinh dang Active + dung
     purpose "Fulfiller".
  2. Luc dung luong duyet, ca nguoi duyet VA nguoi xu ly deu duoc cap.
  3. Hoi cau hinh nguoi xu ly ma HONG thi VAN cap cho nguoi duyet - khong duoc lam hong
     ca lan gui phieu vi mot phan phu.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_PERM_MOD = "ecentric_workspace.approval_center.shared.workflow.permissions"


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _extract(rel_parts, name):
    src = _read(*rel_parts)
    return next(n for n in ast.parse(src).body
                if isinstance(n, ast.FunctionDef) and n.name == name)


def _compile(node, ns):
    exec(compile(ast.Module(body=[node], type_ignores=[]), "under_test.py", "exec"), ns)
    return ns[node.name]


# --------------------------------------------------------------------------- #
# 1. configured_fulfiller_users
# --------------------------------------------------------------------------- #
class _FakeFrappe(object):
    """get_all gia, dieu phoi theo doctype. Ghi lai bo loc de con khang dinh tren chinh no."""

    def __init__(self, procs=(), participants=(), has_role=(), enabled=()):
        self.procs, self.participants = list(procs), list(participants)
        self.has_role, self.enabled = list(has_role), set(enabled)
        self.filters_seen = []

    @staticmethod
    def _in(f, key):
        """Gia tri cua bo loc `["in", [...]]`. Danh sach RONG thi NEM LOI - dung nhu Frappe
        that: `IN ()` khong phai SQL hop le. Nho vay phep chan `if not procs: return []`
        moi duoc kiem that su, thay vi duoc cai gia am tham do ho."""
        spec = f.get(key)
        if not spec:
            return None
        assert spec[0] == "in", spec
        if not spec[1]:
            raise AssertionError("loc `%s in ()` - Frappe that se no ra o day" % key)
        return spec[1]

    def get_all(self, doctype, filters=None, fields=None, pluck=None, **kw):
        f = dict(filters or {})
        self.filters_seen.append((doctype, f))
        if doctype == "EC Approval Process":
            rows = [p for p in self.procs
                    if p.get("approval_type") == f.get("approval_type")
                    and p.get("status") == f.get("status")]
            return [r["name"] for r in rows] if pluck else rows
        if doctype == "EC Approval Participant":
            parents = self._in(f, "parent") or []
            # CO Y KHONG thi hanh `["is", "set"]`: bo loc do chi la THU HEP o tang DB va
            # hanh vi cua no thay doi theo phien ban Frappe. Cai gia mo phong ban XAU nhat -
            # dong bo trong VAN ve tay ham - de kiem rang phia Python tu no da du chan.
            # Neu de cai gia don ho thi hai lop chan cua ham deu khong bao gio duoc thu.
            out = []
            for p in self.participants:
                if p.get("parent") not in parents:
                    continue
                if p.get("participant_purpose") != f.get("participant_purpose"):
                    continue
                if p.get("source_type") != f.get("source_type"):
                    continue
                out.append(p.get(pluck) if pluck else p)
            return out
        if doctype == "Has Role":
            want = self._in(f, "role")
            rows = self.has_role if want is None else [h for h in self.has_role
                                                       if h["role"] in want]
            return [h["parent"] for h in rows]
        if doctype == "User":
            want = self._in(f, "name") or []
            # TON TRONG gia tri cua bo loc `enabled`, khong tu quyet: neu ham hoi
            # enabled=0 thi phai tra ve nguoi da NGHI VIEC. Cai gia tu loc theo y minh
            # thi doi `enabled: 1` thanh `0` van xanh - mot phep do mu.
            on = f.get("enabled")
            rows = [u for u in want
                    if (u in self.enabled) == (bool(on) if on is not None else True)]
            # TRA VE NGUOC THU TU mot cach co y: neu ham bo `sorted` thi ket qua doi, va
            # test do. Danh sach nguoi duoc cap quyen phai on dinh giua hai lan chay.
            return sorted(rows, reverse=True)
        raise AssertionError("doctype la: %s" % doctype)


def _fulfiller_users(fk):
    node = _extract(("approval_center", "shared", "workflow", "permissions.py"),
                    "configured_fulfiller_users")
    return _compile(node, {"frappe": fk})


_PROCS = [{"name": "PAYMENT_REQUEST-V1", "approval_type": "PAYMENT_REQUEST", "status": "Active"}]


def _fk(**kw):
    kw.setdefault("procs", _PROCS)
    return _FakeFrappe(**kw)


class TestConfiguredFulfillerUsers(unittest.TestCase):
    def test_bung_dong_ROLE_ra_thanh_nguoi(self):
        """DocShare la theo tung NGUOI - no khong nhan role. Khong bung ra thi chi Dan
        khong bao gio co dong chia se nao."""
        fk = _fk(participants=[{"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "Role", "role": "EC Finance"}],
                 has_role=[{"role": "EC Finance", "parent": "dan.ha@ec.vn"},
                           {"role": "EC Finance", "parent": "van.bui@ec.vn"}],
                 enabled=["dan.ha@ec.vn", "van.bui@ec.vn"])
        self.assertEqual(_fulfiller_users(fk)("PAYMENT_REQUEST"),
                         ["dan.ha@ec.vn", "van.bui@ec.vn"])

    def test_lay_ca_dong_USER(self):
        fk = _fk(participants=[{"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "User", "user": "lien.pham@ec.vn"}],
                 enabled=["lien.pham@ec.vn"])
        self.assertEqual(_fulfiller_users(fk)("PAYMENT_REQUEST"), ["lien.pham@ec.vn"])

    def test_gop_ca_hai_nguon_va_KHONG_trung(self):
        fk = _fk(participants=[{"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "User", "user": "dan.ha@ec.vn"},
                               {"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "Role", "role": "EC Finance"}],
                 has_role=[{"role": "EC Finance", "parent": "dan.ha@ec.vn"}],
                 enabled=["dan.ha@ec.vn"])
        self.assertEqual(_fulfiller_users(fk)("PAYMENT_REQUEST"), ["dan.ha@ec.vn"])

    def test_nguoi_da_NGHI_VIEC_khong_duoc_cap(self):
        """Ho so tien. Tai khoan disabled ma con dong DocShare la mot cua con mo."""
        fk = _fk(participants=[{"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "Role", "role": "EC Finance"}],
                 has_role=[{"role": "EC Finance", "parent": "cu.nhan@ec.vn"},
                           {"role": "EC Finance", "parent": "dan.ha@ec.vn"}],
                 enabled=["dan.ha@ec.vn"])
        self.assertEqual(_fulfiller_users(fk)("PAYMENT_REQUEST"), ["dan.ha@ec.vn"])

    def test_khong_co_loai_phieu_thi_rong(self):
        for empty in (None, "", 0):
            self.assertEqual(_fulfiller_users(_fk())(empty), [])

    def test_khong_co_quy_trinh_ACTIVE_thi_rong(self):
        """Va phai DUNG NGAY, khong duoc di tiep voi `parent in ()` - Frappe that no ra."""
        fk = _FakeFrappe(procs=[{"name": "P", "approval_type": "PAYMENT_REQUEST",
                                 "status": "Draft"}])
        self.assertEqual(_fulfiller_users(fk)("PAYMENT_REQUEST"), [])

    def test_dong_cau_hinh_BO_TRONG_khong_lot_qua(self):
        """Dong Fulfiller khai theo Role nhung chua chon role (hoac nguoc lai) la rac cau
        hinh. Khong loc o tang DB thi no ve day thanh mot user rong / role rong."""
        fk = _fk(participants=[{"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "User", "user": ""},
                               {"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "Role", "role": ""},
                               {"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "User", "user": "dan.ha@ec.vn"}],
                 has_role=[{"role": "", "parent": "ai.do@ec.vn"}],
                 enabled=["dan.ha@ec.vn", "ai.do@ec.vn"])
        self.assertEqual(_fulfiller_users(fk)("PAYMENT_REQUEST"), ["dan.ha@ec.vn"])

    def test_danh_sach_ON_DINH_giua_hai_lan_chay(self):
        """Cap quyen la viec chay di chay lai (patch cap bu, gui phieu moi). Thu tu doi
        moi lan thi khong con so sanh duoc hai lan chay voi nhau."""
        fk = _fk(participants=[{"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "Role", "role": "EC Finance"}],
                 has_role=[{"role": "EC Finance", "parent": "van.bui@ec.vn"},
                           {"role": "EC Finance", "parent": "dan.ha@ec.vn"}],
                 enabled=["van.bui@ec.vn", "dan.ha@ec.vn"])
        self.assertEqual(_fulfiller_users(fk)("PAYMENT_REQUEST"),
                         ["dan.ha@ec.vn", "van.bui@ec.vn"])

    def test_chi_hoi_quy_trinh_Active_va_purpose_Fulfiller(self):
        fk = _fk(participants=[{"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "User", "user": "a@ec.vn"}],
                 enabled=["a@ec.vn"])
        _fulfiller_users(fk)("PAYMENT_REQUEST")
        proc_f = [f for dt, f in fk.filters_seen if dt == "EC Approval Process"]
        self.assertEqual(proc_f[0].get("status"), "Active")
        part_f = [f for dt, f in fk.filters_seen if dt == "EC Approval Participant"]
        self.assertTrue(part_f)
        for f in part_f:
            self.assertEqual(f.get("participant_purpose"), "Fulfiller",
                             "cap nham nguoi DUYET thanh nguoi xu ly la noi rong quyen")

    def test_KHONG_cap_cho_Guest(self):
        fk = _fk(participants=[{"parent": "PAYMENT_REQUEST-V1", "participant_purpose": "Fulfiller",
                                "source_type": "Role", "role": "EC Finance"}],
                 has_role=[{"role": "EC Finance", "parent": "Guest"}],
                 enabled=["Guest"])
        self.assertEqual(_fulfiller_users(fk)("PAYMENT_REQUEST"), [])


# --------------------------------------------------------------------------- #
# 2. grant_read_to_snapshot_approvers
# --------------------------------------------------------------------------- #
class _Req(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _grant_fn(approvers, fulfillers=None, fulfil_raises=False):
    """Nap ham that, kem mot module `permissions` GIA cai vao sys.modules (ham dung
    import cuc bo). Ghi lai ai duoc cap."""
    granted = []

    class _FK(object):
        def get_all(self, doctype, filters=None, pluck=None, **kw):
            return list(approvers)

        @staticmethod
        def log_error(*a, **kw):
            granted.append(("log_error",))

        @staticmethod
        def get_traceback():
            return "tb"

    fake_perm = types.ModuleType(_PERM_MOD)

    def _cfu(atype):
        if fulfil_raises:
            raise RuntimeError("cau hinh hong")
        return list(fulfillers or [])
    fake_perm.configured_fulfiller_users = _cfu

    node = _extract(("approval_center", "shared", "workflow", "transitions.py"),
                    "grant_read_to_snapshot_approvers")
    ns = {"frappe": _FK(), "_engine_grant_read": lambda dt, n, u: granted.append(u)}
    fn = _compile(node, ns)

    saved = sys.modules.get(_PERM_MOD)
    sys.modules[_PERM_MOD] = fake_perm
    try:
        fn(_Req({"name": "EC-APR-1", "reference_doctype": "EC Payment Request",
                 "reference_name": "EC-PAYR-2026-00073", "approval_type": "PAYMENT_REQUEST"}))
    finally:
        if saved is None:
            sys.modules.pop(_PERM_MOD, None)
        else:
            sys.modules[_PERM_MOD] = saved
    return granted


class TestCapQuyenDocLucDungLuong(unittest.TestCase):
    def test_cap_cho_CA_nguoi_duyet_VA_nguoi_xu_ly(self):
        g = _grant_fn(approvers=["sep@ec.vn"], fulfillers=["dan.ha@ec.vn"])
        self.assertIn("sep@ec.vn", g, "khong duoc lam mat nguoi duyet")
        self.assertIn("dan.ha@ec.vn", g, "nguoi xu ly phai duoc cap tu luc gui duyet")

    def test_khong_cap_trung_va_bo_Guest(self):
        g = _grant_fn(approvers=["a@ec.vn", "Guest", "a@ec.vn"], fulfillers=["a@ec.vn"])
        self.assertEqual([x for x in g if x != ("log_error",)], ["a@ec.vn"])

    def test_cau_hinh_nguoi_xu_ly_HONG_thi_VAN_cap_cho_nguoi_duyet(self):
        """Ve an toan: quyen doc thieu thi nguoi dung van mo duoc ho so trong app, chi vuong
        tep dinh kem - khong dang de danh doi ca lan gui phieu."""
        g = _grant_fn(approvers=["sep@ec.vn"], fulfil_raises=True)
        self.assertIn("sep@ec.vn", g)
        self.assertIn(("log_error",), g, "hong thi phai GHI LAI, khong duoc im lang")


class TestPatchCapBu(unittest.TestCase):
    def test_p167_duoc_khai_vao_patches_txt(self):
        txt = _read("patches.txt")
        self.assertIn("p167_backfill_fulfiller_file_read", txt,
                      "viet patch ma khong khai = khong bao gio chay")

    def test_p167_chi_dong_den_phieu_dang_MO(self):
        src = _read("approval_center", "patches", "p167_backfill_fulfiller_file_read.py")
        self.assertIn('_OPEN = ("Pending", "Information Required")', src)
        self.assertIn('"approval_status": ["in", list(_OPEN)]', src,
                      "khong duoc moi lai quyen tren ho so da dong")

    def test_p167_KHONG_bao_gio_nem_loi(self):
        """Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116)."""
        src = _read("approval_center", "patches", "p167_backfill_fulfiller_file_read.py")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "execute")
        self.assertFalse([n for n in ast.walk(fn) if isinstance(n, ast.Raise)])
        self.assertGreaterEqual(len([n for n in ast.walk(fn) if isinstance(n, ast.Try)]), 2)

    def test_p167_bo_qua_DocShare_da_co(self):
        src = _read("approval_center", "patches", "p167_backfill_fulfiller_file_read.py")
        self.assertIn('frappe.db.exists("DocShare"', src, "chay lai phai vo hai")


if __name__ == "__main__":
    unittest.main()
