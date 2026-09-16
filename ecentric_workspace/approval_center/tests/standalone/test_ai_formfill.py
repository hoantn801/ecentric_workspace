# Copyright (c) 2026, eCentric and contributors
"""Cong loc + schema + probe cua AI dien ho. Chay code THAT voi frappe gia.

NGHIEM THU BANG HAI MAU. Moi luat co mot mau chac chan DAT va mot mau chac chan TRUOT - cong
nao khong phan biet duoc hai mau do la cong vo dung (xem QUY_TAC_TRANH_CONFLICT / A56).

Phep kiem dat nhat o day la `test_probe_rollback_du_validator_ghi_db`: `validate_payment`
that co goi `chot_brand_ngoai` -> `Brand.insert()`. Neu probe khong rollback thi mot ten
brand AI doc nham se thanh mot hang vinh vien trong danh muc.
"""
import io
import os
import sys
import types
import unittest
from datetime import date, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(
    _HERE, "..", "..", "shared", "integrations", "ai_formfill.py"))


class _Perm(Exception):
    pass


class _Validation(Exception):
    pass


def _load(*, exists=None, perm=True, conf=None, meta_fields=(), on_insert=None):
    """Nap module that voi mot frappe gia. Tra (module, fk) - `fk` la frappe gia de doc lai."""
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.ValidationError = _Validation
    fk.PermissionError = _Perm
    fk.conf = dict(conf or {})
    fk.session = types.SimpleNamespace(user="hoan.tran@ecentric.vn")
    fk.savepoints, fk.rollbacks, fk.inserted = [], [], []
    fk.logged = []

    _exists = set(exists or ())

    class _DB:
        def exists(self, dt, name=None):
            if name is None:
                return True          # frappe.db.exists("DocType", X) mot tham so
            return (dt, name) in _exists
        def count(self, dt, filters=None):
            return 0
        def savepoint(self, sp):
            fk.savepoints.append(sp)
        def rollback(self, save_point=None):
            fk.rollbacks.append(save_point)
    fk.db = _DB()
    fk.has_permission = lambda dt, ptype=None, doc=None: perm
    fk.get_all = lambda dt, **kw: []
    fk.log_error = lambda *a, **k: fk.logged.append(a)
    fk.get_traceback = lambda: "tb"

    class _Meta:
        def __init__(self, fields):
            self._f = {f["fieldname"]: types.SimpleNamespace(**f) for f in fields}
        def get_field(self, name):
            return self._f.get(name)
        def has_field(self, name):
            return name in self._f
    meta = _Meta(meta_fields)
    fk.get_meta = lambda dt: meta

    class _Doc(dict):
        def __init__(self):
            super().__init__()
            self.meta = meta
        def __setattr__(self, k, v):
            if k == "meta":
                super().__setattr__(k, v)
            else:
                self[k] = v
        def __getattr__(self, k):
            try:
                return self[k]
            except KeyError:
                raise AttributeError(k)
        def update(self, d):
            super().update(d)
            return self
        def insert(self, **kw):
            fk.inserted.append(dict(self))
            self["name"] = "NEW-1"
            return self
    def _new_doc(dt):
        d = _Doc()
        if on_insert:
            on_insert(d)
        return d
    fk.new_doc = _new_doc

    utils = types.ModuleType("frappe.utils")
    utils.nowdate = lambda: "2026-09-16"
    def _getdate(v):
        if isinstance(v, date):
            return v
        return date.fromisoformat(str(v)[:10])
    utils.getdate = _getdate

    mods = {"frappe": fk, "frappe.utils": utils}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_ai_formfill_under_test")
        with io.open(_SRC, encoding="utf-8") as fh:
            exec(compile(fh.read(), "ai_formfill.py", "exec"), m.__dict__)
        m._fk, m._mods = fk, mods
        return m, fk
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _run(m, fn):
    saved = {k: sys.modules.get(k) for k in m._mods}
    sys.modules.update(m._mods)
    try:
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _F(fieldname, fieldtype, **kw):
    base = {"fieldname": fieldname, "fieldtype": fieldtype, "label": fieldname,
            "reqd": 0, "description": "", "options": None, "length": 0}
    base.update(kw)
    return base


_DEF_FIELDS = [
    _F("payee_full_name", "Data", length=140),
    _F("payment_amount", "Currency"),
    _F("payment_date", "Date"),
    _F("ec_vat_pct", "Select", options="0\n8\n10"),
    _F("ec_brand", "Link", options="Brand"),
    _F("request_attachment", "Attach"),          # phai bi bo: kieu truong
    _F("ec_brand_moi", "Check"),                 # phai bi bo: moi Check deu la khang dinh
    _F("details_and_attachments_correct", "Select", options="Yes\nNo"),  # clone_exclude
    _F("is_cost_valid", "Select", options="Yes\nNo"),                    # ai_exclude
]


def _definition(**kw):
    d = types.SimpleNamespace(
        business_doctype="EC Payment Request",
        editable_fields=tuple(f["fieldname"] for f in _DEF_FIELDS),
        clone_exclude_fields=("details_and_attachments_correct",),
        ai_exclude_fields=("is_cost_valid",),
        submitter=types.SimpleNamespace(validator=None),
    )
    for k, v in kw.items():
        setattr(d, k, v)
    return d


class TestSchema(unittest.TestCase):
    def test_bo_dung_ba_nhom_va_giu_phan_con_lai(self):
        m, _ = _load(meta_fields=_DEF_FIELDS)
        names = [f["fieldname"] for f in _run(m, lambda: m.build_schema(_definition()))]
        # DAT: bon truong binh thuong phai co mat
        self.assertEqual(names, ["payee_full_name", "payment_amount", "payment_date",
                                 "ec_vat_pct", "ec_brand"])
        # TRUOT: ba nhom loai tru, moi nhom mot ly do khac nhau
        self.assertNotIn("request_attachment", names)               # kieu truong
        self.assertNotIn("ec_brand_moi", names)                     # Check
        self.assertNotIn("details_and_attachments_correct", names)  # clone_exclude_fields
        self.assertNotIn("is_cost_valid", names)                    # ai_exclude_fields

    def test_truong_khong_co_trong_meta_thi_bo_chu_khong_no(self):
        m, _ = _load(meta_fields=_DEF_FIELDS)
        d = _definition(editable_fields=("payee_full_name", "khong_ton_tai"))
        names = [f["fieldname"] for f in _run(m, lambda: m.build_schema(d))]
        self.assertEqual(names, ["payee_full_name"])

    def test_select_mang_theo_options(self):
        m, _ = _load(meta_fields=_DEF_FIELDS)
        s = _run(m, lambda: m.build_schema(_definition()))
        vat = [f for f in s if f["fieldname"] == "ec_vat_pct"][0]
        self.assertEqual(vat["options"], ["0", "8", "10"])


class TestGate(unittest.TestCase):
    def _gate(self, raw, **kw):
        m, _ = _load(meta_fields=_DEF_FIELDS, **kw)
        schema = _run(m, lambda: m.build_schema(_definition()))
        return _run(m, lambda: m.gate(schema, raw))

    def test_moi_ma_ly_do_co_mot_mau_dat_va_mot_mau_truot(self):
        exists = {("Brand", "FES-VN")}
        cases = [
            # (raw, truong, co_duoc_nhan, ma_ly_do_neu_truot)
            ({"payee_full_name": "Nguyen Thu Ha"}, "payee_full_name", True, None),
            ({"payee_full_name": "   "}, "payee_full_name", False, "rong"),
            ({"payee_full_name": "x" * 141}, "payee_full_name", False, "qua_dai"),
            ({"payment_amount": "45000000"}, "payment_amount", True, None),
            ({"payment_amount": "bon lam trieu"}, "payment_amount", False, "khong_phai_so"),
            ({"payment_amount": -5}, "payment_amount", False, "so_khong_duong"),
            ({"payment_date": "2026-09-22"}, "payment_date", True, None),
            ({"payment_date": "khong phai ngay"}, "payment_date", False, "ngay_khong_hop_le"),
            ({"payment_date": "2031-01-01"}, "payment_date", False, "ngay_ngoai_khoang"),
            ({"ec_vat_pct": "8"}, "ec_vat_pct", True, None),
            ({"ec_vat_pct": "12"}, "ec_vat_pct", False, "sai_option"),
            ({"ec_brand": "FES-VN"}, "ec_brand", True, None),
            ({"ec_brand": "Brand Bia Ra"}, "ec_brand", False, "khong_co_ban_ghi"),
            ({"khong_co_truong_nay": "x"}, "khong_co_truong_nay", False, "khong_trong_schema"),
        ]
        for raw, field, should_pass, reason in cases:
            accepted, dropped = self._gate(raw, exists=exists)
            with self.subTest(raw=raw):
                if should_pass:
                    self.assertIn(field, accepted)
                    self.assertEqual(dropped, [])
                else:
                    self.assertNotIn(field, accepted)
                    self.assertEqual(dropped, [{"field": field, "reason": reason}])

    def test_select_nhan_ca_so_lan_chuoi(self):
        """`ec_vat_pct` co options "0"/"8"/"10" - chuoi trong nhu so. Model tra ve 10 (so)
        ma khong ep str() thi truong VAT khong bao gio len duoc form, lang le."""
        accepted, dropped = self._gate({"ec_vat_pct": 10})
        self.assertEqual(accepted, {"ec_vat_pct": "10"})
        self.assertEqual(dropped, [])

    def test_link_ton_tai_nhung_khong_co_quyen_thi_bo(self):
        accepted, dropped = self._gate({"ec_brand": "FES-VN"},
                                       exists={("Brand", "FES-VN")}, perm=False)
        self.assertEqual(accepted, {})
        self.assertEqual(dropped, [{"field": "ec_brand", "reason": "khong_co_quyen"}])

    def test_khong_cat_bot_va_khong_sua_cho_vua(self):
        """Cat cut mot so tai khoan trong im lang te hon mot o de trong."""
        accepted, _ = self._gate({"payee_full_name": "y" * 200})
        self.assertEqual(accepted, {})


class TestProbe(unittest.TestCase):
    def test_probe_rollback_du_validator_GHI_DB(self):
        """`validate_payment` that goi `chot_brand_ngoai` -> `Brand.insert()`. Probe phai
        rollback ca khi validator DAT lan khi no NEM LOI."""
        def validator_ghi_db(doc):
            b = frappe_mod.new_doc("Brand")
            b.brand = doc.get("ec_brand_ten") or "Brand AI bia ra"
            b.insert()
        for nem_loi in (False, True):
            m, fk = _load(meta_fields=_DEF_FIELDS)
            frappe_mod = fk

            def v(doc, _fail=nem_loi):
                validator_ghi_db(doc)
                if _fail:
                    raise _Validation("thieu tep dinh kem")

            d = _definition(submitter=types.SimpleNamespace(validator=v))
            res = _run(m, lambda: m.probe(d, {"payee_full_name": "Ha"}))
            with self.subTest(nem_loi=nem_loi):
                self.assertEqual(res["ok"], not nem_loi)
                # ban ghi CO duoc tao trong savepoint...
                self.assertEqual(len(fk.inserted), 1)
                # ...va savepoint PHAI duoc rollback trong ca hai nhanh
                self.assertEqual(fk.savepoints, [m.PROBE_SAVEPOINT])
                self.assertEqual(fk.rollbacks, [m.PROBE_SAVEPOINT])

    def test_khong_co_validator_thi_bao_ra_chu_khong_im_lang_bao_dat(self):
        m, _ = _load(meta_fields=_DEF_FIELDS)
        res = _run(m, lambda: m.probe(_definition(), {}))
        self.assertIsNone(res["ok"])
        self.assertEqual(res["skipped"], "khong_co_validator")

    def test_loi_ngoai_ValidationError_van_rollback(self):
        def v(doc):
            raise RuntimeError("ham nghiep vu vo tinh no")
        m, fk = _load(meta_fields=_DEF_FIELDS)
        d = _definition(submitter=types.SimpleNamespace(validator=v))
        res = _run(m, lambda: m.probe(d, {}))
        self.assertFalse(res["ok"])
        self.assertEqual(fk.rollbacks, [m.PROBE_SAVEPOINT])


class TestCongTac(unittest.TestCase):
    def test_site_config_ghi_chuoi_0_KHONG_phai_la_tat(self):
        """`bool("0")` la True trong Python - hotfix 09/06 cua alerts, giu dung ngu nghia."""
        for value, expect in ((None, False), (0, False), ("0", False), ("false", False),
                              ("no", False), ("", False),
                              (1, True), ("1", True), (True, True), ("yes", True),
                              ("TRUE", True), ("on", True)):
            m, _ = _load(conf={"ec_ai_formfill_disabled": value})
            with self.subTest(value=value):
                self.assertEqual(_run(m, m.is_disabled), expect)

    def test_tran_ngay_doc_tu_site_config_va_co_mac_dinh(self):
        m, _ = _load(conf={})
        self.assertEqual(_run(m, m.daily_cap), m.DEFAULT_DAILY_CAP)
        m2, _ = _load(conf={"ec_ai_formfill_daily_cap": "7"})
        self.assertEqual(_run(m2, m2.daily_cap), 7)
        m3, _ = _load(conf={"ec_ai_formfill_daily_cap": "khong phai so"})
        self.assertEqual(_run(m3, m3.daily_cap), m3.DEFAULT_DAILY_CAP)


class TestKhongBietFormNao(unittest.TestCase):
    def test_module_khong_nhac_ten_mot_form_cu_the_nao(self):
        """Bo dong chu thich TRUOC khi grep - khong thi bat trung chu trong chu thich cua
        chinh minh (bai hoc 31/08-01/09, 4 lan)."""
        with io.open(_SRC, encoding="utf-8") as fh:
            src = fh.read()
        code = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
        # bo docstring cap module
        if code.count('"""') >= 2:
            code = code.split('"""', 2)[2]
        for cam in ('PAYMENT_REQUEST', 'if code ==', 'if definition.code'):
            self.assertNotIn(cam, code, "ai_formfill khong duoc biet form nao ca")


class TestResponseSchema(unittest.TestCase):
    def _schema(self):
        m, _ = _load(meta_fields=_DEF_FIELDS)
        return m, _run(m, lambda: m.build_schema(_definition()))

    def test_select_khai_string_chu_khong_phai_number(self):
        """`ec_vat_pct` co options "0"/"8"/"10". Khai la number thi model tra ve 10 va nhanh
        Select cua `gate` (so khop chuoi) se bo truong do trong im lang."""
        m, schema = self._schema()
        rs = _run(m, lambda: m.response_schema(schema))
        vat = rs["properties"]["ec_vat_pct"]
        self.assertEqual(vat["type"], "string")
        self.assertEqual(vat["enum"], ["0", "8", "10"])

    def test_so_tien_la_number_con_ten_la_string(self):
        m, schema = self._schema()
        rs = _run(m, lambda: m.response_schema(schema))
        self.assertEqual(rs["properties"]["payment_amount"]["type"], "number")
        self.assertEqual(rs["properties"]["payee_full_name"]["type"], "string")

    def test_chi_hai_o_dat_nhat_moi_co_khoa_trich_dan(self):
        m, schema = self._schema()
        props = _run(m, lambda: m.response_schema(schema))["properties"]
        self.assertIn("payment_amount__source", props)      # DAT: o tien
        self.assertNotIn("payee_full_name__source", props)  # TRUOT: o thuong
        self.assertNotIn("payment_date__source", props)

    def test_moi_truong_deu_nullable(self):
        """Luat "khong chac thi de trong" chi thuc thi duoc neu schema cho phep null."""
        m, schema = self._schema()
        props = _run(m, lambda: m.response_schema(schema))["properties"]
        self.assertTrue(all(p.get("nullable") for p in props.values()))


class TestPrompt(unittest.TestCase):
    def test_prompt_mang_options_va_khong_ghi_de_o_da_go(self):
        m, _ = _load(meta_fields=_DEF_FIELDS)
        schema = _run(m, lambda: m.build_schema(_definition()))
        p = _run(m, lambda: m.build_prompt(schema, "van ban nguon",
                                           {"payee_full_name": "Ha", "payment_amount": ""}))
        self.assertIn("chi nhan: 0 / 8 / 10", p)
        self.assertIn("DE NGUYEN", p)
        self.assertIn("payee_full_name = Ha", p)
        # o rong KHONG duoc ke la "da dien"
        self.assertNotIn("payment_amount =", p)
        self.assertIn("van ban nguon", p)


class TestSplitSources(unittest.TestCase):
    def test_trich_dan_tach_khoi_gia_tri(self):
        m, _ = _load()
        v, s = _run(m, lambda: m.split_sources({
            "payment_amount": 45000000,
            "payment_amount__source": "...so tien 45.000.000d da gom VAT...",
            "payee_full_name": "Ha"}))
        self.assertEqual(v, {"payment_amount": 45000000, "payee_full_name": "Ha"})
        self.assertEqual(list(s), ["payment_amount"])
        # trich dan KHONG duoc lan vao gia tri truong
        self.assertNotIn("payment_amount__source", v)


if __name__ == "__main__":
    unittest.main()
