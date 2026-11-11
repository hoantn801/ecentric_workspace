# Copyright (c) 2026, eCentric and contributors
"""Chang 3 ky so (11/11/2026): endpoint ky so dung chung cho moi loai chung tu.

Truoc chang 3, ~26 endpoint trong platform/esign/api.py chi nhan `payment_request_name` va viet
cung "EC Payment Request" ben trong - du lop ben duoi da nhan (business_doctype, business_name).
Form Hop dong khong goi duoc chung.

Sau chang 3 moi endpoint nhan HAI kieu goi:
  * cu  `payment_request_name=X`               -> DNTT, giao dien hien tai KHONG phai sua;
  * moi `business_doctype=D, business_name=N`  -> D phai co ho so ky.

Bon dieu duoc chot o day:
  1. KHONG con endpoint nao nhan DNTT ma bo sot kieu goi moi (quet ma - them endpoint thu 27
     ma quen thi do).
  2. Kieu goi moi KHONG mo cua sau: loai chung tu chua co ho so ky thi bi tu choi.
  3. Kieu goi cu cho ket qua y het truoc: van la "EC Payment Request", cung ten.
  4. Thu tu kiem quyen KHONG doi: endpoint chi danh cho System Manager van kiem quyen TRUOC
     khi cham DB; mat khau SCTS duoc go khoi request data truoc moi phep kiem.
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_API = os.path.join(_APP, "ecentric_workspace", "platform", "esign", "api.py")
_SRC = io.open(_API, encoding="utf-8").read()
_TREE = ast.parse(_SRC)
_FNS = {n.name: n for n in _TREE.body if isinstance(n, ast.FunctionDef)}

#: Co chu dich KHONG mo rong. Pilot la cong cu UAT rieng cua DNTT; `pr_approve_and_sign` da
#: co ban dung chung `approve_and_sign(business_doctype, business_name)` tu truoc.
_GIU_RIENG_DNTT = {"uat_pilot_readiness", "run_scts_uat_pilot_probe", "pr_approve_and_sign"}


def _whitelisted(fn):
    for d in fn.decorator_list:
        node = d.func if isinstance(d, ast.Call) else d
        if getattr(node, "attr", None) == "whitelist":
            return True
    return False


def _params(fn):
    return [a.arg for a in fn.args.args]


def _body_src(fn):
    """Than ham, bo docstring - loi giai thich duoc phep nhac ten cu."""
    seg = ast.get_source_segment(_SRC, fn)
    first = fn.body[0]
    if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
        doc = ast.get_source_segment(_SRC, first)
        seg = seg.replace(doc, "", 1)
    return seg


def _endpoints_dntt():
    return [f for f in _FNS.values()
            if _whitelisted(f) and "payment_request_name" in _params(f)
            and f.name not in _GIU_RIENG_DNTT]


class TestKhongEndpointNaoBiBoSot(unittest.TestCase):
    def test_du_so_luong(self):
        self.assertGreaterEqual(len(_endpoints_dntt()), 26,
                                "it hon 26 = quet ma khong con thay het endpoint")

    def test_moi_endpoint_nhan_kieu_goi_moi(self):
        for f in _endpoints_dntt():
            p = _params(f)
            self.assertIn("business_doctype", p, f.name)
            self.assertIn("business_name", p, f.name)
            self.assertIn("_target(payment_request_name, business_doctype, business_name)",
                          _body_src(f), "%s khong di qua _target" % f.name)

    def test_khong_con_viet_cung_DNTT_trong_than(self):
        for f in _endpoints_dntt():
            body = _body_src(f)
            self.assertNotIn('"EC Payment Request"', body, f.name)
            # sau _target, ten cu chi con o dong goi _target
            rest = body.replace("_target(payment_request_name,", "")
            self.assertNotIn("payment_request_name", rest.split("):", 1)[1],
                             "%s con dung payment_request_name sau khi da chon chung tu" % f.name)

    def test_kieu_goi_cu_van_la_tham_so_dau_tien(self):
        """Giao dien va test cu goi `api.placement_editor_config(ten_phieu)` theo VI TRI."""
        for f in _endpoints_dntt():
            self.assertEqual(_params(f)[0], "payment_request_name", f.name)
            p = _params(f)
            self.assertGreater(p.index("business_doctype"), 0, f.name)
            # hai tham so moi o CUOI de khong xo lech vi tri cua tham so cu
            self.assertEqual(p[-2:], ["business_doctype", "business_name"], f.name)

    #: Tham so von TUY CHON tu truoc (mac dinh None o ban cu) - khong phai bat buoc.
    _VON_TUY_CHON = {"comment", "username"}
    #: Bat buoc nhung lop duoi tu bao loi THAN THIEN hon `_need`: giu cau cu cho nguoi dung.
    _LOP_DUOI_TU_KIEM = {("link_scts_account", "password")}

    def test_tham_so_bat_buoc_cu_van_duoc_kiem(self):
        """Tham so sau payment_request_name phai co mac dinh None de goi kieu moi; thieu thi
        `_need` phai bat, khong chay voi None. Kiem bang LOI GOI `_need(...)` that (AST), khong
        bang chuoi `x=x` - `comment=comment` chuyen tiep cung khop chuoi do (QC 11/11)."""
        for f in _endpoints_dntt():
            a = f.args
            names = _params(f)
            defaults = dict(zip(names[len(names) - len(a.defaults):], a.defaults))
            needed = set()
            for c in ast.walk(f):
                if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "_need":
                    needed |= {k.arg for k in c.keywords}
            for n in names[1:]:
                if n in ("business_doctype", "business_name") or n in self._VON_TUY_CHON:
                    continue
                if (f.name, n) in self._LOP_DUOI_TU_KIEM:
                    self.assertNotIn(n, needed, "%s.%s: de lop duoi bao loi" % (f.name, n))
                    continue
                d = defaults.get(n)
                if isinstance(d, ast.Constant) and d.value is None:
                    self.assertIn(n, needed,
                                  "%s.%s mac dinh None ma khong qua _need" % (f.name, n))


class TestThuTuKiemQuyen(unittest.TestCase):
    def test_system_manager_kiem_truoc_khi_cham_DB(self):
        for f in _endpoints_dntt():
            body = _body_src(f)
            if "perms.assert_system_manager()" not in body:
                continue
            self.assertLess(body.find("perms.assert_system_manager()"), body.find("_target("),
                            "%s: _target doc DB truoc khi kiem quyen SM" % f.name)

    def test_mat_khau_go_truoc_moi_phep_kiem(self):
        body = _body_src(_FNS["link_scts_account"])
        self.assertLess(body.find('form_dict.pop("password"'), body.find("_target("))

    def test_endpoint_doc_van_kiem_quyen_xem(self):
        """Ba endpoint tra du lieu nhay cam (anh chu ky, cau hinh tep) tu kiem quyen xem."""
        for name in ("document_signature_overlay", "placement_editor_config",
                     "my_signature_preview"):
            self.assertIn("perms.assert_can_view_business(biz_dt, biz_name)",
                          _body_src(_FNS[name]), name)


class _Throw(Exception):
    pass


def _helpers(profiles=("EC Payment Request",), records=None):
    """Chay THAT `_target`, `_need`, `_business_args` voi frappe gia."""
    records = set(records or [("EC Payment Request", "PR-1"), ("EC Contract Review Request",
                                                                "CR-1"), ("User", "a@b")])
    fk = types.SimpleNamespace()

    def exists(dt, name_or_filters):
        if isinstance(name_or_filters, dict):
            return dt == "EC Digital Signature Profile" and \
                name_or_filters.get("business_doctype") in profiles
        return (dt, name_or_filters) in records

    def throw(msg, *a, **k):
        raise _Throw(msg)
    fk.db = types.SimpleNamespace(exists=exists)
    fk.throw = throw
    g = {"frappe": fk, "_": lambda s: s}
    code = ""
    for n in ("_business_args", "_target", "_need"):
        code += ast.get_source_segment(_SRC, _FNS[n]) + "\n\n"
    for n in _TREE.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") in
                                             ("LEGACY_BUSINESS_DOCTYPE", "PROFILE")
                                             for t in n.targets):
            code = ast.get_source_segment(_SRC, n) + "\n" + code
    exec(compile(code, "api_helpers", "exec"), g)
    return g


class TestChonChungTu(unittest.TestCase):
    def test_kieu_cu_y_het_truoc(self):
        g = _helpers()
        self.assertEqual(g["_target"]("PR-1"), ("EC Payment Request", "PR-1"))

    def test_kieu_moi_co_ho_so(self):
        g = _helpers(profiles=("EC Payment Request", "EC Contract Review Request"))
        self.assertEqual(g["_target"](None, "EC Contract Review Request", "CR-1"),
                         ("EC Contract Review Request", "CR-1"))

    def test_kieu_moi_khong_co_ho_so_bi_tu_choi(self):
        """Khong co ho so = endpoint khong duoc thanh cua sau doc DocType bat ky."""
        g = _helpers()
        with self.assertRaises(_Throw):
            g["_target"](None, "User", "a@b")
        with self.assertRaises(_Throw):
            g["_target"](None, "EC Contract Review Request", "CR-1")

    def test_tron_hai_kieu_bi_tu_choi(self):
        g = _helpers(profiles=("EC Payment Request", "EC Contract Review Request"))
        with self.assertRaises(_Throw):
            g["_target"]("PR-1", "EC Contract Review Request", "CR-1")

    def test_thieu_doctype_hoac_ten(self):
        g = _helpers()
        for args in ((None, None, "PR-1"), (None, "EC Payment Request", None), (None, None, None)):
            with self.assertRaises(_Throw, msg=repr(args)):
                g["_target"](*args)

    def test_ban_ghi_khong_ton_tai(self):
        g = _helpers()
        with self.assertRaises(_Throw):
            g["_target"]("PR-KHONG-CO")

    def test_chi_nhan_chuoi(self):
        """Body JSON co the mang list - ["like", "%"] lot qua bo loc ho so (QC 11/11)."""
        g = _helpers(profiles=("EC Payment Request", "EC Contract Review Request"))
        for args in ((["like", "%"],), (None, ["like", "%"], "CR-1"),
                     (None, "EC Contract Review Request", {"x": 1})):
            with self.assertRaises(_Throw, msg=repr(args)):
                g["_target"](*args)

    def test_need(self):
        g = _helpers()
        g["_need"](a="x", b=0)
        with self.assertRaises(_Throw) as c:
            g["_need"](a=None, b="", c="ok")
        self.assertIn("a", str(c.exception))
        self.assertIn("b", str(c.exception))


class TestKieuCuDenLopDuoiYHet(unittest.TestCase):
    """Chay THAT than endpoint: kieu goi cu phai den lop duoi voi dung ("EC Payment Request", X)
    va dung thu tu tham so nhu truoc chang 3 (QC 11/11: truoc chi kiem chuoi nguon)."""

    def _run(self, fn_name, modname, **kwargs):
        import sys
        calls = []

        class Fake(types.ModuleType):
            def __getattr__(self, attr):
                if attr.startswith("__"):
                    raise AttributeError(attr)
                return lambda *a, **k: calls.append((attr, a, k)) or "OK"
        full = "ecentric_workspace.platform.esign." + modname
        import ecentric_workspace.platform.esign as pkg
        fake = Fake(full)
        saved_mod, had_attr = sys.modules.get(full), hasattr(pkg, modname)
        saved_attr = getattr(pkg, modname, None)
        sys.modules[full] = fake
        setattr(pkg, modname, fake)
        try:
            g = _helpers(profiles=("EC Payment Request", "EC Contract Review Request"))
            g["perms"] = types.SimpleNamespace(assert_can_view_business=lambda *a: None)
            exec(compile(ast.get_source_segment(_SRC, _FNS[fn_name]), "ep", "exec"), g)
            out = g[fn_name](**kwargs)
        finally:
            if saved_mod is None:
                sys.modules.pop(full, None)
            else:
                sys.modules[full] = saved_mod
            if had_attr:
                setattr(pkg, modname, saved_attr)
            else:
                delattr(pkg, modname)
        return out, calls

    def test_document_setup_state(self):
        _o, calls = self._run("document_setup_state", "document_setup", payment_request_name="PR-1")
        self.assertEqual(calls, [("get_document_setup_state", ("EC Payment Request", "PR-1"), {})])

    def test_save_placement_giu_thu_tu(self):
        _o, calls = self._run("save_placement", "placement_service",
                              payment_request_name="PR-1", document_ref="F1", box="{}")
        self.assertEqual(calls, [("save_placement", ("EC Payment Request", "PR-1", "F1", "{}"), {})])

    def test_kieu_moi(self):
        _o, calls = self._run("save_placement", "placement_service",
                              business_doctype="EC Contract Review Request",
                              business_name="CR-1", document_ref="F1", box="{}")
        self.assertEqual(calls[0][1][:2], ("EC Contract Review Request", "CR-1"))

    def test_requester_submit_and_sign(self):
        _o, calls = self._run("requester_submit_and_sign", "requester",
                              payment_request_name="PR-1", comment="ok")
        self.assertEqual(calls, [("requester_submit_and_sign", ("EC Payment Request", "PR-1"),
                                  {"comment": "ok"})])


class TestQuyenXemKhongDocCotKhongCo(unittest.TestCase):
    """QC 11/11 (Fable + Opus): `can_view_business` doc mu `fulfillment_owner` - Hop dong khong
    co cot do -> nguoi duoc CC (CEO) nhan loi DB thay vi co/khong."""

    def _run(self, cols_on_doctype):
        path = os.path.join(_APP, "ecentric_workspace", "platform", "esign", "permissions.py")
        src = io.open(path, encoding="utf-8").read()
        fn = [n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "can_view_business"][0]
        asked = []

        def get_value(dt, name, fields, as_dict=False):
            asked.append(list(fields))
            for f in fields:
                if f not in cols_on_doctype:
                    raise RuntimeError("Unknown column %s" % f)
            return {"requested_by": "a@b"}
        fk = types.SimpleNamespace(
            session=types.SimpleNamespace(user="ceo@x"),
            db=types.SimpleNamespace(has_column=lambda dt, c: c in cols_on_doctype,
                                     get_value=get_value),
            log_error=lambda *a, **k: None, get_traceback=lambda: "")
        seen = {}

        def can_view_request(ar, user, **kw):
            seen.update(kw)
            return True
        import sys
        mod = types.ModuleType("fake_perm_root")
        mod.can_view_request = can_view_request
        key = "ecentric_workspace.approval_center.shared.workflow.permissions"
        saved = sys.modules.get(key)
        sys.modules[key] = mod
        try:
            g = {"frappe": fk, "can_setup_package": lambda *a: False,
                 "business_approval_request": lambda *a: "AR-1"}
            exec(compile(ast.get_source_segment(src, fn), "perm", "exec"), g)
            return g["can_view_business"]("EC Contract Review Request", "CR-1"), asked, seen
        finally:
            if saved is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = saved

    def test_doctype_khong_co_fulfillment_owner(self):
        ok, asked, seen = self._run({"requested_by", "approval_type"})
        self.assertTrue(ok)
        self.assertNotIn("fulfillment_owner", asked[0])
        self.assertIsNone(seen.get("fulfillment_owner"))

    def test_doctype_co_du_cot_van_doc_du(self):
        ok, asked, _s = self._run({"requested_by", "fulfillment_owner", "approval_type"})
        self.assertEqual(sorted(asked[0]), ["approval_type", "fulfillment_owner", "requested_by"])


if __name__ == "__main__":
    unittest.main()
