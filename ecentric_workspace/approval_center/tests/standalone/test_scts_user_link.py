# Copyright (c) 2026, eCentric and contributors
"""Ket noi tai khoan SCTS theo tung nguoi - chung tu do CHINH nguoi de nghi tao.

Vi sao ton tai (04/09/2026): eContract giao buoc Trinh ky cho tai khoan TAO chung tu va chi
ky bang chung thu cua nguoi giu task. Tao bang tai khoan tich hop thi nguoi de nghi khac
khong bao gio ky duoc. Nguoi dung tu dang nhap SCTS mot lan, ERP giu TOKEN, khong luu mat
khau, va tao chung tu bang token do.

Nam lop, moi lop chay code THAT voi frappe gia:
  1. user_link: needs_own_token; token_for (het han/skew/khong mapping); link luu TOKEN
     chu khong luu mat khau, mat khau khong loi vao event; assert_requester_linked chan.
  2. adapter scts: use_user_token -> moi lenh di bang token do; bi tu choi thi KHONG dang
     nhap lai bang tai khoan tich hop (khong authenticate), ma nem loi rieng.
  3. tasks.py (AST): worker chan Requester khong co token khi Queued, dung use_user_token
     TRUOC _ensure_provider_document, va khong bao gio goi use_user_token cho Approver.
  4. requester.py (AST): requester_submit_and_sign goi assert_requester_linked SAU
     verified_mapping va TRUOC khi tao DSR.
  5. api.py (AST): 3 endpoint chi thao tac tren frappe.session.user, link/unlink la POST,
     khong endpoint nao nhan tham so `user`, link xoa `password` khoi form_dict.
"""
import ast
import io
import os
import sys
import types
import unittest
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

NOW = datetime(2026, 9, 4, 9, 0, 0)
HIEN = "hien.nguyen@ecentric.vn"
HOAN = "hoan.tran@ecentric.vn"
SETTINGS = {"username": HOAN, "site": "ECENTRIC", "provider": "SCTS", "environment": "UAT"}
PASSWORD = "mat-khau-cua-hien-KHONG-DUOC-LUU"
TOKEN = "eyJ.token.cua.hien"


def _read(rel):
    with io.open(os.path.join(_ESIGN, rel), encoding="utf-8") as fh:
        return fh.read()


class _Doc(dict):
    """frappe.get_doc gia: gan thuoc tinh, save() ghi lai vao store."""
    def __init__(self, store, name):
        super().__init__(); self._store = store; self.name = name
        self.__dict__.update(store.get(name, {}))

    def save(self, ignore_permissions=False):
        self.saved_with_ignore = ignore_permissions
        self._store[self.name] = {k: v for k, v in self.__dict__.items()
                                  if k not in ("_store", "saved_with_ignore")}


def _fake_frappe(mapping_store, mapping_by_user):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.PermissionError = type("PermissionError", (Exception,), {})
    fk.thrown = []

    def throw(msg, exc=None):
        fk.thrown.append(msg)
        raise (exc or Exception)(msg)
    fk.throw = throw

    class _DB(object):
        def get_value(self, dt, name, fields=None, as_dict=False, **kw):
            row = mapping_store.get(name)
            if row is None:
                return None
            if isinstance(fields, (list, tuple)):
                return {f: row.get(f) for f in fields}
            return row.get(fields)
    fk.db = _DB()
    fk.get_doc = lambda dt, name: _Doc(mapping_store, name)
    fk.session = types.SimpleNamespace(user=HIEN)
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: NOW
    utils.get_datetime = lambda v: v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
    utils.add_to_date = lambda d, **kw: d + timedelta(minutes=kw.get("minutes", 0),
                                                      hours=kw.get("hours", 0))
    pw = types.ModuleType("frappe.utils.password")
    pw.get_decrypted_password = lambda dt, name, field, raise_exception=False: \
        mapping_store.get(name, {}).get(field)
    utils.password = pw
    fk.utils = utils

    events = types.ModuleType("ecentric_workspace.platform.esign.events")
    events.log = []
    events.emit = lambda et, **kw: events.log.append((et, kw))
    perms = types.ModuleType("ecentric_workspace.platform.esign.permissions")
    perms.verified_mapping = lambda user, env: mapping_by_user.get((user, env))
    providers = types.ModuleType("ecentric_workspace.platform.esign.providers")
    providers.calls = []

    class _Client(object):
        def login(self, site, username, password):
            providers.calls.append({"site": site, "username": username, "password": password})
            if password != PASSWORD:
                raise base.ProviderError("scts_auth_failed", "SCTS authentication failed (HTTP 401)")
            return {"data": {"token": TOKEN, "expiresInMinutes": 525600}}

    class _Adapter(object):
        _client = _Client()

        @staticmethod
        def _extract_token(raw):
            return ((raw or {}).get("data") or {}).get("token")
    providers.get_adapter = lambda settings: _Adapter()
    base = types.ModuleType("ecentric_workspace.platform.esign.providers.base")

    class ProviderError(Exception):
        def __init__(self, code, message, retryable=False, ambiguous=False):
            super().__init__(message); self.code = code; self.message = message
            self.retryable = retryable; self.ambiguous = ambiguous
    base.ProviderError = ProviderError
    mods = {"frappe": fk, "frappe.utils": utils, "frappe.utils.password": pw,
            "ecentric_workspace.platform.esign.events": events,
            "ecentric_workspace.platform.esign.permissions": perms,
            "ecentric_workspace.platform.esign.providers": providers,
            "ecentric_workspace.platform.esign.providers.base": base}
    return fk, mods, events, providers


def _load(rel, name, mods, drop_prefix="ecentric_workspace.platform.esign"):
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        for k in list(sys.modules):
            if k.startswith(drop_prefix) and k not in mods:
                sys.modules.pop(k)
        mod = types.ModuleType(name)
        mod.__file__ = os.path.join(_ESIGN, rel)
        exec(compile(_read(rel), rel, "exec"), mod.__dict__)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


# ------------------------------------------------------------------------ lop 1: user_link
def _user_link(token=None, expires_at=None, with_mapping=True):
    store = {"EC-DSM-00001": {"name": "EC-DSM-00001", "frappe_user": HIEN, "environment": "UAT",
                              "scts_user_id": "541f8e96", "api_token": token,
                              "api_token_expires_at": expires_at,
                              "api_token_linked_at": None, "api_token_username": None}}
    by_user = {(HIEN, "UAT"): {"name": "EC-DSM-00001", "scts_user_id": "541f8e96"}} \
        if with_mapping else {}
    fk, mods, events, providers = _fake_frappe(store, by_user)
    ul = _load("user_link.py", "_user_link_under_test", mods)
    ul._fk = fk; ul._events = events; ul._providers = providers; ul._store = store
    return ul


class TestUserLink(unittest.TestCase):
    def test_tai_khoan_tich_hop_khong_can_token(self):
        ul = _user_link()
        self.assertFalse(ul.needs_own_token("Hoan.Tran@ecentric.vn", SETTINGS))
        self.assertTrue(ul.needs_own_token(HIEN, SETTINGS))

    def test_token_con_han_thi_tra_ve(self):
        ul = _user_link(token=TOKEN, expires_at=NOW + timedelta(days=300))
        self.assertEqual(ul.token_for(HIEN, "UAT"), TOKEN)

    def test_token_het_han_hoac_sap_het_thi_None(self):
        self.assertIsNone(_user_link(token=TOKEN, expires_at=NOW - timedelta(minutes=1))
                          .token_for(HIEN, "UAT"))
        # trong khoang skew: con 30 phut nhung skew 60 -> coi nhu het
        self.assertIsNone(_user_link(token=TOKEN, expires_at=NOW + timedelta(minutes=30))
                          .token_for(HIEN, "UAT"))
        self.assertIsNone(_user_link(token=TOKEN, expires_at=None).token_for(HIEN, "UAT"))

    def test_khong_mapping_thi_None_va_link_bi_chan(self):
        ul = _user_link(with_mapping=False)
        self.assertIsNone(ul.token_for(HIEN, "UAT"))
        with self.assertRaises(Exception):
            ul.link(HIEN, SETTINGS, "UAT", PASSWORD)
        self.assertEqual(ul._providers.calls, [], "khong mapping thi KHONG goi login")

    def test_link_luu_TOKEN_khong_luu_mat_khau(self):
        ul = _user_link()
        st = ul.link(HIEN, SETTINGS, "UAT", PASSWORD)
        row = ul._store["EC-DSM-00001"]
        self.assertEqual(row["api_token"], TOKEN)
        self.assertEqual(row["api_token_username"], HIEN)
        self.assertEqual(row["api_token_expires_at"], NOW + timedelta(minutes=525600))
        self.assertTrue(st["linked"]); self.assertEqual(st["days_left"], 365)
        # mat khau: chi den client.login, khong nam o dau khac
        self.assertEqual(ul._providers.calls[0]["site"], "ECENTRIC")
        self.assertEqual(ul._providers.calls[0]["username"], HIEN)
        for k, v in row.items():
            self.assertNotEqual(v, PASSWORD, "mat khau bi luu o truong %s" % k)
        for et, kw in ul._events.log:
            self.assertNotIn(PASSWORD, repr(kw), "mat khau loi vao su kien %s" % et)
        self.assertIn("UserTokenLinked", [e[0] for e in ul._events.log])

    def test_expires_doc_ca_boc_data_lan_phang_thieu_thi_0(self):
        ul = _user_link()
        self.assertEqual(ul._expires_in_minutes({"data": {"expiresInMinutes": 10}}), 10)
        self.assertEqual(ul._expires_in_minutes({"expiresInMinutes": "7"}), 7)
        self.assertEqual(ul._expires_in_minutes({"data": {"token": "x"}}), 0)
        self.assertEqual(ul._expires_in_minutes(None), 0)

    def test_link_sai_mat_khau_bao_chung_va_khong_lo_gi(self):
        ul = _user_link()
        with self.assertRaises(Exception):
            ul.link(HIEN, SETTINGS, "UAT", "sai")
        self.assertIsNone(ul._store["EC-DSM-00001"]["api_token"])
        self.assertIn("UserTokenLinkFailed", [e[0] for e in ul._events.log])
        self.assertNotIn("sai", " ".join(ul._fk.thrown))

    def test_username_khac_email_khi_khai(self):
        ul = _user_link()
        ul.link(HIEN, SETTINGS, "UAT", PASSWORD, username="nv00151")
        self.assertEqual(ul._providers.calls[0]["username"], "nv00151")
        self.assertEqual(ul._store["EC-DSM-00001"]["api_token_username"], "nv00151")

    def test_unlink_xoa_sach(self):
        ul = _user_link(token=TOKEN, expires_at=NOW + timedelta(days=10))
        st = ul.unlink(HIEN, SETTINGS, "UAT")
        row = ul._store["EC-DSM-00001"]
        self.assertIsNone(row["api_token"]); self.assertIsNone(row["api_token_expires_at"])
        self.assertFalse(st["linked"])

    def test_assert_requester_linked(self):
        # tai khoan tich hop: khong can
        self.assertIsNone(_user_link().assert_requester_linked(HOAN, SETTINGS, "UAT"))
        # nguoi khac, co token: tra token
        ul = _user_link(token=TOKEN, expires_at=NOW + timedelta(days=10))
        self.assertEqual(ul.assert_requester_linked(HIEN, SETTINGS, "UAT"), TOKEN)
        # nguoi khac, khong token: chan bang PermissionError + su kien
        ul = _user_link()
        with self.assertRaises(ul._fk.PermissionError):
            ul.assert_requester_linked(HIEN, SETTINGS, "UAT")
        self.assertIn("RequesterNotLinked", [e[0] for e in ul._events.log])
        self.assertIn("kết nối", ul._fk.thrown[-1])


# ------------------------------------------------------------------------ lop 2: adapter
def _scts_adapter():
    fk = types.ModuleType("frappe"); fk._ = lambda s: s
    utils = types.ModuleType("frappe.utils")
    utils.add_to_date = lambda *a, **k: None; utils.get_datetime = lambda v: v
    utils.now_datetime = lambda: NOW
    pw = types.ModuleType("frappe.utils.password"); pw.get_decrypted_password = lambda *a, **k: None
    utils.password = pw; fk.utils = utils
    mods = {"frappe": fk, "frappe.utils": utils, "frappe.utils.password": pw}
    scts = _load("providers/scts.py", "_scts_under_test", mods)
    a = scts.SctsAdapter.__new__(scts.SctsAdapter)
    a.auth_calls = 0
    a.authenticate = lambda: setattr(a, "auth_calls", a.auth_calls + 1)
    a.refresh_or_get_token = lambda: "SERVICE-TOKEN"
    a._password = lambda f: "SERVICE-TOKEN"
    return a, scts


class TestAdapterUserToken(unittest.TestCase):
    def test_moi_lenh_di_bang_token_nguoi_dung(self):
        a, _ = _scts_adapter()
        a.use_user_token(TOKEN)
        seen = []
        a._with_auth(lambda t: seen.append(t))
        self.assertEqual(seen, [TOKEN])
        self.assertEqual(a.auth_calls, 0)

    def test_khong_token_thi_van_tai_khoan_tich_hop(self):
        a, _ = _scts_adapter()
        seen = []
        a._with_auth(lambda t: seen.append(t))
        self.assertEqual(seen, ["SERVICE-TOKEN"])

    def test_bi_tu_choi_thi_KHONG_roi_ve_tai_khoan_tich_hop(self):
        a, scts = _scts_adapter()
        a.use_user_token(TOKEN)

        def fn(t):
            raise scts.ProviderError("scts_auth_error_401", "rejected")
        with self.assertRaises(scts.ProviderError) as cm:
            a._with_auth(fn)
        self.assertEqual(cm.exception.code, "scts_user_token_rejected")
        self.assertFalse(cm.exception.retryable)
        self.assertEqual(a.auth_calls, 0, "khong duoc dang nhap lai bang tai khoan tich hop")

    def test_loi_khac_giu_nguyen(self):
        a, scts = _scts_adapter()
        a.use_user_token(TOKEN)

        def fn(t):
            raise scts.ProviderError("scts_transition_rejected_400", "bad")
        with self.assertRaises(scts.ProviderError) as cm:
            a._with_auth(fn)
        self.assertEqual(cm.exception.code, "scts_transition_rejected_400")

    def test_authenticate_doc_expiry_trong_data(self):
        """Truoc 04/09: doc expiresInMinutes o cap ngoai -> luon None -> khong cache -> dang
        nhap lai truoc MOI lenh (Provider Settings.token_expires_at = null tren prod, modified
        doi lien tuc). eContract boc trong `data`."""
        _, scts = _scts_adapter()
        self.assertEqual(scts.SctsAdapter._extract_expiry(
            {"success": True, "data": {"token": "t", "expiresInMinutes": 525600}}), 525600)
        self.assertEqual(scts.SctsAdapter._extract_expiry({"expiresInMinutes": "5"}), 5)
        self.assertIsNone(scts.SctsAdapter._extract_expiry({"data": {"token": "t"}}))
        self.assertIsNone(scts.SctsAdapter._extract_expiry(None))
        fn = _fn(_tree("providers/scts.py"), "authenticate")
        self.assertIn("_extract_expiry(raw)", ast.unparse(fn))

    def test_token_rong_bi_tu_choi_ngay(self):
        a, scts = _scts_adapter()
        with self.assertRaises(scts.ProviderError):
            a.use_user_token("")


# ------------------------------------------------------------------------ lop 3-5: AST
def _tree(rel):
    return ast.parse(_read(rel))


def _fn(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError("khong thay ham %s" % name)


def _calls(node, attr):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)
            and ((isinstance(n.func, ast.Attribute) and n.func.attr == attr)
                 or (isinstance(n.func, ast.Name) and n.func.id == attr))]


def _line(node):
    return node.lineno


class TestTasksWorker(unittest.TestCase):
    def setUp(self):
        self.fn = _fn(_tree("tasks.py"), "process_signing_request")
        self.src = ast.unparse(self.fn)

    def test_use_user_token_truoc_ensure_provider_document(self):
        use = _calls(self.fn, "use_user_token")
        ens = _calls(self.fn, "_ensure_provider_document")
        self.assertEqual(len(use), 1); self.assertTrue(ens)
        self.assertLess(_line(use[0]), _line(ens[0]),
                        "token nguoi dung phai duoc dat TRUOC khi tao chung tu")

    def test_chi_Requester_moi_dung_token_nguoi_dung(self):
        # loi goi use_user_token phai nam trong mot nhanh if kiem actor_type == "Requester"
        for n in ast.walk(self.fn):
            if isinstance(n, ast.If) and 'actor_type == \'Requester\'' in ast.unparse(n.test):
                self.assertTrue(_calls(n, "use_user_token"))
                self.assertIn("needs_own_token", ast.unparse(n.test))
                return
        self.fail("khong thay nhanh if actor_type == 'Requester' and needs_own_token")

    def test_khong_token_khi_Queued_thi_nem_requester_not_linked_khong_retry(self):
        raises = [n for n in ast.walk(self.fn) if isinstance(n, ast.Raise)
                  and "requester_not_linked" in ast.unparse(n)]
        self.assertEqual(len(raises), 1)
        self.assertIn("retryable=False", ast.unparse(raises[0]))
        # va no nam sau mot kiem tra status == 'Queued'
        for n in ast.walk(self.fn):
            if isinstance(n, ast.If) and "status == 'Queued'" in ast.unparse(n.test) \
                    and any(r is x for r in raises for x in ast.walk(n)):
                return
        self.fail("raise requester_not_linked phai duoc gac boi status == 'Queued'")

    def test_raise_nam_truoc_moi_lenh_ghi(self):
        raises = [n for n in ast.walk(self.fn) if isinstance(n, ast.Raise)
                  and "requester_not_linked" in ast.unparse(n)]
        ens = _calls(self.fn, "_ensure_provider_document")
        self.assertLess(_line(raises[0]), _line(ens[0]))


class TestRequesterSubmit(unittest.TestCase):
    def test_submit_goi_assert_requester_linked_sau_mapping_truoc_DSR(self):
        fn = _fn(_tree("requester.py"), "requester_submit_and_sign")
        link = _calls(fn, "assert_requester_linked")
        self.assertEqual(len(link), 1)
        vm = _calls(fn, "verified_mapping")
        self.assertTrue(vm)
        self.assertGreater(_line(link[0]), _line(vm[0]))
        insert = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                  and "insert" in ast.unparse(n.func)]
        self.assertTrue(insert, "khong thay cho tao DSR")
        self.assertLess(_line(link[0]), _line(insert[0]))
        args = [ast.unparse(a) for a in link[0].args]
        self.assertEqual(args[0], "requester", "phai chot dung NGUOI DE NGHI, khong phai session")

    def test_readiness_bao_trang_thai_ket_noi(self):
        fn = _fn(_tree("requester.py"), "requester_signing_readiness")
        src = ast.unparse(fn)
        self.assertIn("checks['scts_link_required']", src)
        self.assertIn("checks['scts_linked']", src)
        self.assertEqual(src.count("link_status("), 2, "ca truoc va sau khi gui")


class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.tree = _tree("api.py")

    def _ep(self, name):
        fn = _fn(self.tree, name)
        decos = [ast.unparse(d) for d in fn.decorator_list]
        self.assertTrue(any(d.startswith("frappe.whitelist") for d in decos), name)
        return fn, decos

    def test_link_va_unlink_la_POST_va_chi_session_user(self):
        for name in ("link_scts_account", "unlink_scts_account"):
            fn, decos = self._ep(name)
            self.assertTrue(any("POST" in d for d in decos), "%s phai POST" % name)
            self.assertNotIn("user", [a.arg for a in fn.args.args],
                             "%s khong duoc nhan tham so user" % name)
            self.assertIn("frappe.session.user", ast.unparse(fn))

    def test_status_chi_session_user(self):
        fn, _ = self._ep("scts_link_status")
        self.assertNotIn("user", [a.arg for a in fn.args.args])
        self.assertIn("frappe.session.user", ast.unparse(fn))

    def test_link_xoa_password_khoi_form_dict(self):
        fn, _ = self._ep("link_scts_account")
        src = ast.unparse(fn)
        self.assertIn("form_dict.pop('password'", src)

    def test_moi_endpoint_kiem_phieu_ton_tai(self):
        for name in ("link_scts_account", "unlink_scts_account", "scts_link_status"):
            fn, _ = self._ep(name)
            self.assertTrue(_calls(fn, "_business_args"), name)


class TestPanelHtml(unittest.TestCase):
    def setUp(self):
        self.h = _read("ui/requester_signing_panel.html")

    def test_khoi_ket_noi_va_goi_dung_endpoint_bang_POST(self):
        self.assertIn('id="ecReqLinkForm"', self.h)
        self.assertIn('type="password"', self.h)
        i = self.h.index("api.link_scts_account")
        self.assertIn('type: "POST"', self.h[i:i + 200])

    def test_mat_khau_bi_xoa_khoi_o_nhap_ngay_khi_gui(self):
        i = self.h.index("api.link_scts_account")
        before = self.h[:i]
        self.assertIn('inLinkPass.value = ""', before[-900:],
                      "o mat khau phai duoc xoa TRUOC khi lenh di")

    def test_hien_khoi_theo_backend_khong_tu_suy(self):
        self.assertIn('b(c, "scts_link_required")', self.h)
        self.assertIn('b(c, "scts_linked")', self.h)
        self.assertEqual(self.h.count("renderLink(c);"), 2, "ca truoc va sau khi gui")


if __name__ == "__main__":
    unittest.main()
