# -*- coding: utf-8 -*-
"""G2b: lo chi TAO BAN NHAP. Chay code THAT voi frappe gia.

PHEP KIEM DAT NHAT: `test_o_phan_doan_cua_nguoi_KHONG_bi_may_tra_loi_ho`.

23/09 tren prod, hai ban nhap do lo tao ra co `is_cost_valid = "Yes"` va
`has_purchase_request = "Yes"` - khong ai chon ca. `frappe.new_doc` lap mot Select BAT BUOC
khong co default bang LUA CHON DAU TIEN, va options la "Yes\\nNo". Nghia la may da tra loi
"Chi phi hop le? -> Co" thay nguoi dung, im lang, tren mot phieu chua ai doc.

Loi do khong lam gi do; no chi lam mot cau khang dinh sai nam trong ho so tai chinh. Khong
co test nay thi mot lan refactor bat ky cung co the tra no ve.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "api", "ai_formfill.py"))

TOI = "hoan.tran@ecentric.vn"

# Hinh dang THAT cua EC Payment Request, rut gon (do tren prod 23/09).
FIELDS = [
    {"fieldname": "payee_full_name", "fieldtype": "Data", "reqd": 1, "label": "Người nhận"},
    {"fieldname": "payment_amount", "fieldtype": "Currency", "reqd": 1, "label": "Số tiền"},
    {"fieldname": "ec_brand", "fieldtype": "Link", "reqd": 0, "label": "Brand liên quan"},
    # Hai o duoi day la bay: Select BAT BUOC, KHONG co default, options bat dau bang "Yes".
    {"fieldname": "is_cost_valid", "fieldtype": "Select", "reqd": 1,
     "options": "Yes\nNo", "label": "Chi phí hợp lệ?"},
    {"fieldname": "has_purchase_request", "fieldtype": "Select", "reqd": 1,
     "options": "Yes\nNo", "label": "Có chứng từ mua hàng?"},
    # Co default nen thoat - nhung chi la may man.
    {"fieldname": "details_and_attachments_correct", "fieldtype": "Select", "reqd": 1,
     "options": "Yes\nNo", "default": "No", "label": "Xác nhận thông tin & tệp"},
    {"fieldname": "request_attachment", "fieldtype": "Attach", "reqd": 1, "label": "Tệp đính kèm"},
    # Hai o duoi nam trong danh sach chan NHUNG KHONG PHAI cai bay, va phai duoc tha ra:
    #  - `no_purchase_request_reason`: bat buoc nhung KHONG phai Select -> `new_doc` khong
    #    lap gi ca. Xoa no di la xoa mat cau AI vua viet.
    #  - `payment_mode` o day de reqd=0 -> khong bat buoc thi khong co gi de "tra lai".
    {"fieldname": "no_purchase_request_reason", "fieldtype": "Small Text", "reqd": 1,
     "label": "Lý do không có chứng từ"},
    {"fieldname": "payment_mode", "fieldtype": "Select", "reqd": 0,
     "options": "Full\nInstallment", "label": "Hình thức thanh toán"},
]

EDITABLE = tuple(f["fieldname"] for f in FIELDS)
AI_EXCLUDE = ("is_cost_valid", "has_purchase_request",
              "no_purchase_request_reason", "payment_mode")
CLONE_EXCLUDE = ("details_and_attachments_correct",)


class _DF(object):
    def __init__(self, d):
        self.__dict__.update({"options": None, "default": None, "label": None})
        self.__dict__.update(d)


class _Meta(object):
    def __init__(self):
        self.fields = [_DF(f) for f in FIELDS]

    def get_field(self, name):
        for f in self.fields:
            if f.fieldname == name:
                return f
        return None


def _load(disabled=False, roles=("System Manager",), saved=None):
    """saved: dict gia lap ban ghi sau khi luu (mo phong new_doc lap Select bat buoc)."""
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=TOI)
    fk.get_roles = lambda u=None: list(roles)
    fk.get_meta = lambda dt: _Meta()
    fk.parse_json = lambda s: __import__("json").loads(s)
    fk.log_error = lambda **kw: None
    fk.get_traceback = lambda: ""

    def _whitelist(*a, **kw):
        def deco(fn):
            return fn
        return deco
    fk.whitelist = _whitelist

    class PermissionError_(Exception):
        pass
    fk.PermissionError = PermissionError_

    class _Throw(Exception):
        pass
    fk.ValidationError = _Throw

    def _throw(msg, exc=None):
        raise (exc or _Throw)(msg)
    fk.throw = _throw

    # Ban ghi gia: BAT DAU bang dung cai bay - hai o Select bat buoc = "Yes".
    ban_ghi = dict(saved if saved is not None else
                   {"is_cost_valid": "Yes", "has_purchase_request": "Yes",
                    "details_and_attachments_correct": "No"})
    ghi = []

    def _set_value(dt, name, field, value, update_modified=True):
        ghi.append((field, value))
        ban_ghi[field] = value
    fk.db = types.SimpleNamespace(set_value=_set_value)

    class _Doc(object):
        def get(self, k):
            return ban_ghi.get(k)
    fk.get_doc = lambda dt, name: _Doc()

    pkg = types.ModuleType("ecentric_workspace"); pkg.__path__ = []
    gem = types.ModuleType("ecentric_workspace.gemini_api")
    gem.generate_json = lambda **kw: {"ok": False, "error": "khong duoc goi"}

    ac = types.ModuleType("ecentric_workspace.approval_center"); ac.__path__ = []
    shared = types.ModuleType("ecentric_workspace.approval_center.shared"); shared.__path__ = []
    integ = types.ModuleType("ecentric_workspace.approval_center.shared.integrations")
    integ.__path__ = []

    att = types.ModuleType("...ai_attachments")
    att.MAX_FILES = 5; att.MIME_BY_EXT = {"pdf": "application/pdf"}
    att.collect = lambda urls: ([], []); att.prompt_block = lambda p: ""

    svc = types.ModuleType("...ai_formfill_svc")
    svc.is_disabled = lambda: disabled
    svc.used_today = lambda: 0
    svc.daily_cap = lambda: 50
    svc.MAX_NOTE_CHARS = 8000
    svc.MAX_BATCH_DRAFTS = 10

    definition = types.SimpleNamespace(
        business_doctype="EC Payment Request", editable_fields=EDITABLE,
        ai_exclude_fields=AI_EXCLUDE, clone_exclude_fields=CLONE_EXCLUDE,
        batch_flagger=None, feature="payment_request")

    reg = types.ModuleType("...registry")
    reg.get_definition = lambda code: definition

    da_luu = {}

    def _save_draft(defn, name=None, payload=None):
        da_luu["payload"] = dict(payload or {})
        for k, v in (payload or {}).items():
            ban_ghi[k] = v
        return {"name": "EC-PAYR-2026-00232"}
    cs = types.ModuleType("...command_service")
    cs.save_draft = _save_draft

    mods = {"frappe": fk, "ecentric_workspace": pkg,
            "ecentric_workspace.gemini_api": gem,
            "ecentric_workspace.approval_center": ac,
            "ecentric_workspace.approval_center.shared": shared,
            "ecentric_workspace.approval_center.shared.integrations": integ,
            "ecentric_workspace.approval_center.shared.integrations.ai_attachments": att,
            "ecentric_workspace.approval_center.shared.integrations.ai_formfill": svc,
            "ecentric_workspace.approval_center.shared.registry": reg,
            "ecentric_workspace.approval_center.shared.requests": types.ModuleType("...requests"),
            "ecentric_workspace.approval_center.shared.requests.command_service": cs}
    mods["ecentric_workspace.approval_center.shared.requests"].command_service = cs
    saved_mods = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_ai_formfill_api_under_test")
        with io.open(_SRC, encoding="utf-8") as fh:
            exec(compile(fh.read(), "ai_formfill.py", "exec"), m.__dict__)
        m._ghi, m._ban_ghi, m._da_luu, m._dn = ghi, ban_ghi, da_luu, definition
        return m
    finally:
        for k, v in saved_mods.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class TestOBayMay(unittest.TestCase):
    def test_nhan_dien_dung_hai_o_Select_bat_buoc_bi_chan(self):
        m = _load()
        ra = sorted(m._o_bat_buoc_may_tu_dien(m._dn))
        self.assertEqual(ra, ["details_and_attachments_correct", "has_purchase_request",
                              "is_cost_valid"])

    def test_KHONG_dinh_toi_o_binh_thuong(self):
        m = _load()
        ra = m._o_bat_buoc_may_tu_dien(m._dn)
        self.assertNotIn("payee_full_name", ra)   # Data, khong phai Select
        self.assertNotIn("ec_brand", ra)          # Link, va khong bat buoc

    def test_o_bi_chan_nhung_KHONG_phai_Select_thi_de_yen(self):
        # `new_doc` chi lap Select. Xoa mot o Small Text la xoa mat cau AI vua viet.
        m = _load()
        self.assertNotIn("no_purchase_request_reason", m._o_bat_buoc_may_tu_dien(m._dn))

    def test_Select_KHONG_bat_buoc_thi_de_yen(self):
        # Khong bat buoc thi khong co "cau tra loi bi ep" nao de tra lai.
        m = _load()
        self.assertNotIn("payment_mode", m._o_bat_buoc_may_tu_dien(m._dn))

    def test_o_phan_doan_cua_nguoi_KHONG_bi_may_tra_loi_ho(self):
        """SU CO 23/09. Sau khi tao nhap, `is_cost_valid` phai TRONG, khong phai "Yes"."""
        m = _load()
        m.create_draft("PAYMENT_REQUEST", {"payee_full_name": "Nguyễn Thanh Phụng"})
        self.assertEqual(m._ban_ghi["is_cost_valid"], "")
        self.assertEqual(m._ban_ghi["has_purchase_request"], "")
        self.assertEqual(m._ban_ghi["details_and_attachments_correct"], "")

    def test_xoa_bang_db_set_value_chu_KHONG_luu_lai_ca_phieu(self):
        # Luu lai se vap chinh phep kiem bat buoc ma ta dang muon de ngo.
        m = _load()
        m.create_draft("PAYMENT_REQUEST", {"payee_full_name": "A"})
        self.assertEqual(sorted(f for f, _ in m._ghi),
                         ["details_and_attachments_correct", "has_purchase_request",
                          "is_cost_valid"])
        self.assertTrue(all(v == "" for _, v in m._ghi))


class TestKhongTinClient(unittest.TestCase):
    def test_client_KHONG_nhet_duoc_o_cam_ket_qua_duong_nay(self):
        m = _load()
        m.create_draft("PAYMENT_REQUEST",
                       {"payee_full_name": "A", "is_cost_valid": "Yes",
                        "details_and_attachments_correct": "Yes"})
        payload = m._da_luu["payload"]
        self.assertNotIn("is_cost_valid", payload)
        self.assertNotIn("details_and_attachments_correct", payload)
        self.assertEqual(m._ban_ghi["is_cost_valid"], "")

    def test_truong_la_bi_bo(self):
        m = _load()
        m.create_draft("PAYMENT_REQUEST", {"payee_full_name": "A", "docstatus": 1,
                                           "owner": "ai.do@ecentric.vn"})
        self.assertEqual(set(m._da_luu["payload"]), {"payee_full_name"})


class TestConThieu(unittest.TestCase):
    def test_liet_ke_o_bat_buoc_con_trong_kem_nhan(self):
        m = _load()
        ra = m.create_draft("PAYMENT_REQUEST", {"payee_full_name": "A"})
        thieu = {x["fieldname"]: x["label"] for x in ra["missing"]}
        self.assertIn("is_cost_valid", thieu)
        self.assertEqual(thieu["is_cost_valid"], "Chi phí hợp lệ?")
        self.assertIn("request_attachment", thieu)
        self.assertNotIn("payee_full_name", thieu)   # da co gia tri

    def test_tra_ve_ma_phieu(self):
        m = _load()
        self.assertEqual(m.create_draft("PAYMENT_REQUEST", {})["name"],
                         "EC-PAYR-2026-00232")


class TestCong(unittest.TestCase):
    def test_tat_cong_tac_thi_khong_tao_duoc(self):
        m = _load(disabled=True)
        with self.assertRaises(Exception):
            m.create_draft("PAYMENT_REQUEST", {})

    def test_khong_co_role_thi_khong_tao_duoc(self):
        m = _load(roles=("Employee",))
        with self.assertRaises(Exception):
            m.create_draft("PAYMENT_REQUEST", {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
