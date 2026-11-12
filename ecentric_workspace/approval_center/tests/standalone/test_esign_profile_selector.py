# Copyright (c) 2026, eCentric and contributors
"""Chon ho so ky THEO PHIEU (12/11/2026, chang hop dong PR-A).

Hop dong: MOT loai chung tu (EC Contract Review Request, loai CONTRACT_REVIEW) co NHIEU ho so ky
- moi quy trinh tren cong mot ho so (KOL/KOC WF09, HD lao dong WF03, ...). Phieu chon quy trinh
bang truong `esign_flow`; ho so khai `selector_field` + `selector_value`.

Chot o day:
  1. DNTT (mot ho so, khong selector) Y HET truoc - co hay khong co ten phieu.
  2. Co ten phieu: chon dung ho so khop; khong khop + khong co mac dinh -> KHONG ky so.
  3. Khong co ten phieu ma co nhieu ho so -> bao loi cau hinh, KHONG doan.
  4. Moi cho goi trong platform/esign + approval_center deu TRUYEN ten phieu (quet ma) - sot
     mot cho la cho do nem "nhieu ho so" tren trang hop dong.
  5. Luu ho so: hai ho so dang bat trung (truong, gia tri) -> tu choi ngay luc luu.
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_ESIGN = os.path.join(_APP, "platform", "esign")


def _read(*parts):
    with io.open(os.path.join(_APP, *parts), encoding="utf-8") as fh:
        return fh.read()


_GUARD = _read("platform", "esign", "guard.py")


class _Throw(Exception):
    pass


class _D(dict):
    __getattr__ = dict.get


def _guard(profiles, doc_values, gates_open=lambda p, e: True, columns=None, packages=()):
    tree = ast.parse(_GUARD)
    code = ""
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in ("_profile_rows", "get_active_profile",
                                                         "get_enabled_profile", "_frozen_profile"):
            code += ast.get_source_segment(_GUARD, n) + "\n\n"
        if (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id == "_FROZEN_PACKAGE_STATES"):
            code += ast.get_source_segment(_GUARD, n) + "\n\n"
    calls = {"get_value": 0, "package": 0}

    def get_all(dt, filters=None, fields=None, order_by=None, limit_page_length=None, **kw):
        f = filters or {}
        if dt == "EC Digital Signature Package":
            calls["package"] += 1
            ok = f["status"][1]
            rows = [p for p in packages if p["business_doctype"] == f["business_doctype"]
                    and p["business_name"] == f["business_name"] and p["status"] in ok]
            rows.sort(key=lambda p: p["creation"], reverse=(order_by == "creation desc"))
            return [_D(r) for r in rows[:limit_page_length]]
        rows = [p for p in profiles if p.get("business_doctype") == f.get("business_doctype")
                and p.get("approval_type") == f.get("approval_type") and p.get("enabled")]
        return [_D(r) for r in sorted(rows, key=lambda r: r["name"])]

    def get_value(dt, name, field):
        calls["get_value"] += 1
        return doc_values.get((dt, name, field))
    cols = columns if columns is not None else {"esign_flow"}
    fk = types.SimpleNamespace(
        get_all=get_all,
        db=types.SimpleNamespace(get_value=get_value, has_column=lambda dt, c: c in cols),
        throw=lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m)))
    g = {"frappe": fk, "_": lambda s: s, "PROFILE": "EC Digital Signature Profile",
         "_gates_open": gates_open}
    exec(compile(code, "guard", "exec"), g)
    g["_calls"] = calls
    return g


PR = {"name": "PAYMENT-REQUEST-SCTS-UAT", "business_doctype": "EC Payment Request",
      "approval_type": "PAYMENT_REQUEST", "enabled": 1, "provider": "SCTS",
      "environment": "UAT"}
CR = "EC Contract Review Request"


def _cr(name, value, field="esign_flow"):
    return {"name": name, "business_doctype": CR, "approval_type": "CONTRACT_REVIEW",
            "enabled": 1, "provider": "SCTS", "environment": "UAT",
            "selector_field": field, "selector_value": value}


KOL, HDLD = _cr("CR-KOL-WF09", "kol_wf09"), _cr("CR-HDLD-WF03", "hd_lao_dong")


class TestDNTTYHetTruoc(unittest.TestCase):
    def test_khong_ten_phieu(self):
        g = _guard([PR], {})
        self.assertEqual(g["get_enabled_profile"]("EC Payment Request", "PAYMENT_REQUEST"),
                         PR["name"])
        self.assertEqual(g["get_active_profile"]("EC Payment Request", "PAYMENT_REQUEST"),
                         PR["name"])

    def test_co_ten_phieu_khong_doc_phieu(self):
        g = _guard([PR], {})
        self.assertEqual(g["get_enabled_profile"]("EC Payment Request", "PAYMENT_REQUEST",
                                                  "EC-PAYR-1"), PR["name"])
        self.assertEqual(g["_calls"]["get_value"], 0, "DNTT khong co selector: khong doc phieu")
        self.assertEqual(g["_calls"]["package"], 0, "DNTT: khong them truy van goi")

    def test_hai_ho_so_khong_selector_van_bao_loi_nhu_cu(self):
        g = _guard([PR, dict(PR, name="PR-2")], {})
        with self.assertRaises(_Throw):
            g["get_enabled_profile"]("EC Payment Request", "PAYMENT_REQUEST", "EC-PAYR-1")


class TestChonTheoPhieu(unittest.TestCase):
    def test_chon_dung(self):
        vals = {(CR, "CR-1", "esign_flow"): "kol_wf09", (CR, "CR-2", "esign_flow"): "hd_lao_dong"}
        g = _guard([KOL, HDLD], vals)
        self.assertEqual(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-1"), "CR-KOL-WF09")
        self.assertEqual(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-2"), "CR-HDLD-WF03")
        self.assertEqual(g["get_active_profile"](CR, "CONTRACT_REVIEW", "CR-2"), "CR-HDLD-WF03")

    def test_khong_ky_cong_la_khong_ky_so(self):
        g = _guard([KOL, HDLD], {(CR, "CR-3", "esign_flow"): "khong_ky_cong"})
        self.assertIsNone(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-3"))
        self.assertIsNone(g["get_active_profile"](CR, "CONTRACT_REVIEW", "CR-3"))

    def test_gia_tri_trong_khong_bao_gio_khop(self):
        """Ho so cau hinh do (co truong, gia tri trong) + phieu de trong: KHONG khop - neu khop
        thi moi phieu chua chon quy trinh deu bi ky theo ho so do."""
        bad = _cr("CR-BAD", "")
        g = _guard([bad, KOL], {(CR, "CR-7", "esign_flow"): ""})
        self.assertIsNone(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-7"))

    def test_truong_trong_la_khong_ky_so(self):
        g = _guard([KOL, HDLD], {(CR, "CR-4", "esign_flow"): ""})
        self.assertIsNone(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-4"))

    def test_ho_so_khong_selector_la_mac_dinh(self):
        default = _cr("CR-DEFAULT", None, field=None)
        g = _guard([KOL, default], {(CR, "CR-5", "esign_flow"): "la"})
        self.assertEqual(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-5"), "CR-DEFAULT")
        g2 = _guard([KOL, default], {(CR, "CR-6", "esign_flow"): "kol_wf09"})
        self.assertEqual(g2["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-6"), "CR-KOL-WF09",
                         "khop selector thang mac dinh")

    def test_khong_ten_phieu_ma_nhieu_ho_so_thi_bao_loi_khong_doan(self):
        g = _guard([KOL, HDLD], {})
        with self.assertRaises(_Throw) as c:
            g["get_enabled_profile"](CR, "CONTRACT_REVIEW")
        self.assertIn("Trường chọn", str(c.exception))

    def test_truong_khong_ton_tai_khong_doc_mu(self):
        g = _guard([KOL, HDLD], {}, columns=set())
        self.assertIsNone(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-1"))
        self.assertEqual(g["_calls"]["get_value"], 0)

    def test_doc_moi_truong_mot_lan(self):
        g = _guard([KOL, HDLD], {(CR, "CR-1", "esign_flow"): "kol_wf09"})
        g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-1")
        self.assertEqual(g["_calls"]["get_value"], 1)

    def test_active_khong_ten_phieu_ma_nhieu_ho_so_cung_khong_doan(self):
        """Tra None o day = "khong can ky" cho assert_level_completable - phai nem (QC 12/11)."""
        g = _guard([KOL, HDLD], {})
        with self.assertRaises(_Throw):
            g["get_active_profile"](CR, "CONTRACT_REVIEW")

    def test_cong_dong_thi_active_tra_None(self):
        g = _guard([KOL, HDLD], {(CR, "CR-1", "esign_flow"): "kol_wf09"},
                   gates_open=lambda p, e: False)
        self.assertIsNone(g["get_active_profile"](CR, "CONTRACT_REVIEW", "CR-1"))
        self.assertEqual(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-1"), "CR-KOL-WF09")


def _pkg(status, profile, creation=1, name="CR-1"):
    return {"business_doctype": CR, "business_name": name, "status": status,
            "profile": profile, "creation": creation}


class TestDongBangTheoGoi(unittest.TestCase):
    """QC2 12/11: goi da khoa -> ho so theo GOI, khong doc lai truong (doi truong sau khoa thi
    ERP van tinh theo quy trinh cong dang chay)."""
    VALS = {(CR, "CR-1", "esign_flow"): "hd_lao_dong"}

    def test_goi_khoa_thang_truong_da_doi(self):
        for st in ("Locked", "Active", "Provider Create Failed", "Completed"):
            g = _guard([KOL, HDLD], self.VALS, packages=[_pkg(st, "CR-KOL-WF09")])
            self.assertEqual(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-1"),
                             "CR-KOL-WF09", st)
            self.assertEqual(g["get_active_profile"](CR, "CONTRACT_REVIEW", "CR-1"),
                             "CR-KOL-WF09", st)
            self.assertEqual(g["_calls"]["get_value"], 0, "khong doc truong khi da dong bang")

    def test_goi_nhap_huy_thay_the_khong_dong_bang(self):
        for st in ("Draft", "Cancelled", "Superseded"):
            g = _guard([KOL, HDLD], self.VALS, packages=[_pkg(st, "CR-KOL-WF09")])
            self.assertEqual(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-1"),
                             "CR-HDLD-WF03", st)

    def test_lay_goi_moi_nhat(self):
        g = _guard([KOL, HDLD], {}, packages=[_pkg("Completed", "CR-HDLD-WF03", 1),
                                              _pkg("Active", "CR-KOL-WF09", 2)])
        self.assertEqual(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-1"), "CR-KOL-WF09")

    def test_ho_so_cua_goi_da_tat_thi_khong_ky_khong_doi_ho_so(self):
        g = _guard([HDLD], self.VALS, packages=[_pkg("Active", "CR-KOL-WF09")])
        self.assertIsNone(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-1"))

    def test_goi_phieu_khac_khong_anh_huong(self):
        g = _guard([KOL, HDLD], self.VALS, packages=[_pkg("Active", "CR-KOL-WF09", name="CR-9")])
        self.assertEqual(g["get_enabled_profile"](CR, "CONTRACT_REVIEW", "CR-1"), "CR-HDLD-WF03")


#: Cho goi DUOC phep khong truyen ten phieu: cong cu rieng cua DNTT (pilot, drift khoa cung
#: "EC Payment Request").
_MIEN = {"flow/drift.py", "pilot.py"}
_HAM = {"get_enabled_profile": 2, "get_active_profile": 2, "requester_signature_required": 2,
        "level_requires_signature": None, "_profile_doc": 2, "_profile_and_settings": 2}


def _calls_missing_name(src, rel):
    out = []
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.Call):
            continue
        name = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
        if name not in _HAM:
            continue
        kw = {k.arg: k.value for k in n.keywords}
        pos = _HAM[name]
        arg = kw.get("business_name")
        if arg is None and pos is not None and len(n.args) > pos:
            arg = n.args[pos]
        if arg is not None and not (isinstance(arg, ast.Constant) and arg.value is None):
            continue
        out.append("%s:%s %s" % (rel, n.lineno, name))
    return out


class TestMoiChoGoiDeuTruyenTenPhieu(unittest.TestCase):
    def test_quet_ma(self):
        missing = []
        roots = [("platform", "esign"), ("approval_center", "shared"),
                 ("approval_center", "reporting"), ("approval_center", "features")]
        for root in roots:
            base = os.path.join(_APP, *root)
            for dp, _dn, fns in os.walk(base):
                if "tests" in dp or "__pycache__" in dp:
                    continue
                for fn in fns:
                    if not fn.endswith(".py"):
                        continue
                    path = os.path.join(dp, fn)
                    rel = os.path.relpath(path, _ESIGN).replace(os.sep, "/")
                    if rel in _MIEN:
                        continue
                    src = io.open(path, encoding="utf-8").read()
                    for m in _calls_missing_name(src, rel):
                        # dinh nghia ham trong guard tu goi nhau co truyen; loai dong `def`
                        missing.append(m)
        self.assertEqual(missing, [], "cho goi chua truyen ten phieu: %s" % missing)


class TestNguonDuLieu(unittest.TestCase):
    """Diet dot bien QC2: cac cho chi kiem duoc bang doc ma."""

    def _fn(self, parts, name, cls=False):
        src = _read(*parts)
        nodes = ast.parse(src).body
        if cls:
            nodes = [n for c in nodes if isinstance(c, ast.ClassDef) for n in c.body]
        return ast.get_source_segment(src, [n for n in nodes if isinstance(n, ast.FunctionDef)
                                            and n.name == name][0])

    def test_kich_hoat_doc_ten_phieu(self):
        seg = self._fn(("platform", "esign", "requester.py"),
                       "activate_level_one_after_requester_signature")
        self.assertIn('"reference_name"', seg)
        self.assertIn("req.reference_name", seg)

    def test_validate_goi_kiem_selector(self):
        seg = self._fn(("approval_center", "doctype", "ec_digital_signature_profile",
                        "ec_digital_signature_profile.py"), "validate", cls=True)
        self.assertIn("self._validate_selector()", seg)

    def test_audit_drift_truyen_ten_phieu(self):
        seg = self._fn(("platform", "esign", "service.py"), "_audit_drift")
        self.assertIn('r.get("reference_name")', seg)

    def test_create_revision_giu_ho_so_cu_co_ghi_chu(self):
        seg = self._fn(("platform", "esign", "package.py"), "create_revision")
        self.assertIn('"profile": old.profile', seg)
        self.assertIn("_repoint_profile", seg, "ghi chu cho ai hoi sinh ham")


class TestLuuHoSo(unittest.TestCase):
    def _validate(self, me, others, fields_on_doc=("esign_flow",)):
        src = _read("approval_center", "doctype", "ec_digital_signature_profile",
                    "ec_digital_signature_profile.py")
        tree = ast.parse(src)
        cls = [n for n in tree.body if isinstance(n, ast.ClassDef)][0]
        fn = [n for n in cls.body if isinstance(n, ast.FunctionDef)
              and n.name == "_validate_selector"][0]
        def get_all(dt, filters=None, fields=None, **kw):
            f = filters or {}
            rows = [o for o in others if o.get("business_doctype") == f.get("business_doctype")
                    and o.get("approval_type") == f.get("approval_type")
                    and o.get("enabled") == f.get("enabled")
                    and o.get("name") != f.get("name", ["!=", None])[1]]
            return [_D(o) for o in rows]
        types_of = dict(fields_on_doc) if isinstance(fields_on_doc, dict) \
            else {f: "Data" for f in fields_on_doc}
        meta = types.SimpleNamespace(get_field=lambda f: (
            _D(fieldtype=types_of[f], is_virtual=(types_of[f] == "VIRTUAL"))
            if f in types_of else None))
        g = {"_": lambda s: s, "frappe": types.SimpleNamespace(
            get_all=get_all, get_meta=lambda dt: meta,
            throw=lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m)))}
        import sys
        import textwrap
        fm = types.ModuleType("frappe.model")
        fm.data_fieldtypes = ("Data", "Select", "Link", "Int", "Check")
        saved = sys.modules.get("frappe.model")
        sys.modules["frappe.model"] = fm
        self.addCleanup(lambda: sys.modules.pop("frappe.model", None) if saved is None
                        else sys.modules.__setitem__("frappe.model", saved))
        isv = [n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "_is_value_field"][0]
        exec(compile(ast.get_source_segment(src, isv), "i", "exec"), g)
        exec(compile(textwrap.dedent(ast.get_source_segment(src, fn)), "v", "exec"), g)
        doc = types.SimpleNamespace(**me)
        g["_validate_selector"](doc)
        return doc

    def test_trung_gia_tri_bi_tu_choi(self):
        with self.assertRaises(_Throw):
            self._validate(dict(KOL, name="NEW"), [KOL])

    def test_khac_gia_tri_thi_qua(self):
        self._validate(dict(HDLD), [KOL])

    def test_hai_ho_so_khong_selector_bi_tu_choi(self):
        with self.assertRaises(_Throw):
            self._validate(dict(PR, name="PR-2", selector_field=None, selector_value=None), [PR])

    def test_luu_lai_chinh_minh_khong_trung(self):
        """Loc `name != self.name`: luu lai mot ho so dang bat khong duoc va voi chinh no."""
        self._validate(dict(KOL), [KOL])

    def test_ho_so_tat_khong_tinh(self):
        self._validate(dict(KOL, name="NEW"), [dict(KOL, enabled=0)])

    def test_cat_khoang_trang_va_ghi_lai(self):
        doc = self._validate(dict(KOL, name="NEW", selector_value=" kol_x "), [KOL])
        self.assertEqual(doc.selector_value, "kol_x")

    def test_sai_ten_truong_bi_tu_choi(self):
        with self.assertRaises(_Throw):
            self._validate(dict(KOL, selector_field="esign_flw"), [])

    def test_hai_truong_chon_khac_nhau_bi_tu_choi(self):
        with self.assertRaises(_Throw):
            self._validate(dict(KOL, name="NEW", selector_field="loai", selector_value="x"),
                           [HDLD], fields_on_doc=("esign_flow", "loai"))

    def test_truong_khong_co_cot_bi_tu_choi(self):
        for ft in ("Table", "HTML", "Section Break", "VIRTUAL"):
            with self.assertRaises(_Throw, msg=ft):
                self._validate(dict(KOL), [], fields_on_doc={"esign_flow": ft})

    def test_truong_select_qua(self):
        self._validate(dict(KOL), [], fields_on_doc={"esign_flow": "Select"})

    def test_khai_truong_ma_thieu_gia_tri(self):
        with self.assertRaises(_Throw):
            self._validate(dict(KOL, selector_value=""), [])



class TestNhoDemReporting(unittest.TestCase):
    """DNTT: hoi guard MOT lan cho N dong (theo loai). Hop dong: theo tung phieu (QC 12/11)."""

    def _fn(self, selector):
        src = _read("approval_center", "reporting", "service.py")
        fn = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)
              and n.name == "_requires_signature"][0]
        calls = []
        guard = types.ModuleType("ecentric_workspace.platform.esign.guard")
        guard.selector_in_use = lambda dt, at: selector
        guard.level_requires_signature = lambda *a, **k: calls.append(k.get("business_name")) or True
        import sys
        pkg = types.ModuleType("ecentric_workspace.platform.esign")
        pkg.guard = guard
        saved = {k: sys.modules.get(k) for k in ("ecentric_workspace.platform.esign",
                                                 "ecentric_workspace.platform.esign.guard")}
        sys.modules["ecentric_workspace.platform.esign"] = pkg
        sys.modules["ecentric_workspace.platform.esign.guard"] = guard
        g = {}
        exec(compile(ast.get_source_segment(src, fn), "r", "exec"), g)
        memo = {}
        try:
            for name in ("P-1", "P-2", "P-3"):
                g["_requires_signature"]("EC Payment Request", "PAYMENT_REQUEST", 1, 4, memo,
                                         business_name=name)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        return calls

    def test_khong_selector_hoi_mot_lan(self):
        self.assertEqual(len(self._fn(False)), 1)

    def test_co_selector_hoi_theo_phieu(self):
        self.assertEqual(self._fn(True), ["P-1", "P-2", "P-3"])


class TestLoaiYeuCauNhap(unittest.TestCase):
    def test_nhieu_ho_so_cung_loai_van_ra_loai(self):
        src = _read("platform", "esign", "requester.py")
        fn = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)
              and n.name == "_draft_approval_type"][0]
        fk = types.SimpleNamespace(
            db=types.SimpleNamespace(has_column=lambda *a: False, get_value=lambda *a: None),
            get_all=lambda *a, **k: ["CONTRACT_REVIEW", "CONTRACT_REVIEW", "CONTRACT_REVIEW"])
        g = {"frappe": fk}
        exec(compile(ast.get_source_segment(src, fn), "q", "exec"), g)
        self.assertEqual(g["_draft_approval_type"](CR, "CR-1"), "CONTRACT_REVIEW")


class TestGoiTheoPhieuHienTai(unittest.TestCase):
    """QC 12/11: doi quy trinh khi da co goi nhap -> goi phai theo ho so MOI (worker tao tai
    lieu tren cong theo ho so cua goi)."""

    def _env(self, pkg):
        src = _read("platform", "esign", "package.py")
        tree = ast.parse(src)
        code = "\n\n".join(ast.get_source_segment(src, n) for n in tree.body
                            if isinstance(n, ast.FunctionDef)
                            and n.name in ("get_or_create_draft", "_repoint_profile"))
        writes, evts = [], []
        if not callable(pkg.get("db_set")):
            def db_set(vals):
                writes.append(("db_set", pkg.name, vals))
                pkg.update(vals)
            pkg["db_set"] = db_set
        fk = types.SimpleNamespace(
            db=types.SimpleNamespace(
                get_value=lambda dt, name, f=None, **k: (
                    "X" if dt != "EC Digital Signature Profile"
                    else _D({"provider": "SCTS", "environment": "UAT"})),
                set_value=lambda *a, **k: writes.append(a)),
            throw=lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m)))
        g = {"frappe": fk, "_": lambda s: s,
             "draft_package_for_business": lambda *a, **k: "PKG-1",
             "get_package": lambda n: pkg,
             "package_placements": lambda n: [_D(name="PL-1", status="Placed"),
                                              _D(name="PL-2", status="Invalid"),
                                              _D(name="PL-3", status="Draft")],
             "events": types.SimpleNamespace(emit=lambda *a, **k: evts.append((a, k)))}
        exec(compile(code, "p", "exec"), g)
        return g, writes, evts

    def test_doi_quy_trinh_goi_nhap_tro_sang_ho_so_moi(self):
        pkg = _D(name="PKG-1", status="Draft", profile="CR-KOL-WF09")
        g, writes, evts = self._env(pkg)
        out = g["get_or_create_draft"](CR, "CR-1", "CR-HDLD-WF03")
        self.assertEqual(out.profile, "CR-HDLD-WF03")
        self.assertEqual(out.environment, "UAT")
        self.assertEqual(writes[0][0], "db_set")
        self.assertEqual(sorted(w[1] for w in writes[1:]), ["PL-1", "PL-3"],
                         "o ky dat theo quy trinh cu -> Invalid")
        self.assertTrue(all(w[2:] == ("status", "Invalid") for w in writes[1:]))
        self.assertEqual(evts[0][0][0], "PackageProfileChanged")
        self.assertEqual(evts[0][1]["request_meta"]["o_ky_huy"], 2)

    def test_cung_ho_so_khong_ghi_gi(self):
        pkg = _D(name="PKG-1", status="Draft", profile="CR-KOL-WF09")
        g, writes, evts = self._env(pkg)
        g["get_or_create_draft"](CR, "CR-1", "CR-KOL-WF09")
        self.assertEqual((writes, evts), ([], []))

    def test_goi_da_gui_khong_doi_duoc(self):
        pkg = _D(name="PKG-1", status="Draft", profile="CR-KOL-WF09", scts_document_id="D")
        g, writes, evts = self._env(pkg)
        with self.assertRaises(_Throw):
            g["get_or_create_draft"](CR, "CR-1", "CR-HDLD-WF03")


if __name__ == "__main__":
    unittest.main()
