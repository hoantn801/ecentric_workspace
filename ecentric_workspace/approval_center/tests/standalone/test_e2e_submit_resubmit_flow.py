# Copyright (c) 2026, eCentric and contributors
"""E2E vong doi: gui phieu / gui lan hai / gui lai sau khi bi tra (finance_support).

Nhung dieu bo test nay giu, tren HAM THAT (Submitter/Resubmitter cua Payment Request):

  1. Gui phieu HAI LAN lien tiep: lan hai bi chan ("da duoc gui"), engine.submit khong
     duoc goi them - mot phieu khong bao gio de ra hai EC Approval Request.
  2. Khi loai phieu yeu cau nguoi de nghi ky: assert_ready_to_submit phai chay TRUOC
     document.save() - tu choi truoc khi ghi (mot commit len o giua se bien loi tu choi
     thanh phieu "da gui" vinh vien khong ai ky duoc); engine.submit nhan
     activate_first_level=False; sign_on_submit chay SAU engine.submit.
  3. Khong yeu cau ky: activate_first_level=True, khong dung toi module ky.
  4. Gui lai: goi ky duoc lam PHIEN BAN MOI (revised) -> Resubmitter PHAI goi
     sign_on_submit ngay trong cung mot lenh; khong doi (unchanged) -> KHONG ky lai;
     engine chan (tai lieu doi) -> loi lan len, khong ky gi.
  5. Dinh nghia PAYMENT_REQUEST that su bat esign=True, manager=True va loai o cam ket
     ca nhan khoi danh sach chep khi clone - doc bang AST tu definition.py, khong grep
     trung chu thich.

finance_support.py duoc exec voi frappe + engine + esign gia lap qua sys.modules
(pattern test_esign_ops_inbox). Cac stub GHI LAI THU TU loi goi de kiem thu tu that.
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()


def _read(*parts):
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class _Throw(Exception):
    pass


class _PermissionError(_Throw):
    pass


class _FakeDoc(object):
    """Business document gia lap: thuoc tinh tu do + save() ghi vao nhat ky thu tu."""

    def __init__(self, log, **fields):
        self.__dict__["_log"] = log
        self.__dict__["_data"] = dict(fields)

    def __getattr__(self, k):
        try:
            return self._data[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self._data[k] = v

    def save(self, **kw):
        self._log.append("doc.save")

    def get(self, k, default=None):
        return self._data.get(k, default)


def _load_finance(doc, signature_required, resubmit_result=None, resubmit_raises=None,
                  manager_user="manager@ec.vn", roles=("Employee",),
                  user="hoan.tran@ec.vn", log=None):
    """Exec finance_support.py that; tra ve (env, log, calls)."""
    import sys

    if log is None:   # thu tu loi goi - de kiem "tu choi truoc khi ghi"
        log = []
    calls = {"engine_submit": [], "engine_resubmit": [], "sign_on_submit": [],
             "assert_ready": [], "set_value": []}

    class _DB(object):
        @staticmethod
        def get_value(dt, filters, fields=None, as_dict=False, **kw):
            if dt == "Employee":
                if isinstance(fields, list) and "reports_to" in fields:
                    return _D({"name": "EMP-1", "reports_to": "EMP-BOSS"})
                if filters == "EMP-BOSS" or (isinstance(filters, str) and filters == "EMP-BOSS"):
                    return manager_user
                return _D({"name": "EMP-1", "company": "eCentric"})
            if dt == "User":
                if manager_user is None:
                    return None
                return _D({"enabled": 1, "user_type": "System User"})
            return None

        @staticmethod
        def set_value(dt, name, field, value=None):
            calls["set_value"].append((dt, name, field, value))
            log.append("db.set_value:%s" % (field if isinstance(field, str) else
                                            ",".join(sorted(field))))

    frappe_mod = types.ModuleType("frappe")
    frappe_mod.db = _DB
    frappe_mod._ = lambda s: s
    frappe_mod._dict = _D
    frappe_mod.session = types.SimpleNamespace(user=user)
    frappe_mod.get_roles = lambda u=None: list(roles)
    frappe_mod.get_doc = lambda dt, name: doc
    frappe_mod.flags = types.SimpleNamespace(mute_messages=False)
    frappe_mod.local = types.SimpleNamespace(message_log=[])
    frappe_mod.PermissionError = _PermissionError

    def _throw(msg, exc=None):
        raise (exc or _Throw)(msg)

    frappe_mod.throw = _throw

    utils_mod = types.ModuleType("frappe.utils")
    utils_mod.getdate = lambda v: v
    utils_mod.now_datetime = lambda: "2026-09-01 10:00:00"
    frappe_mod.utils = utils_mod

    engine_mod = types.ModuleType("transitions")

    def _submit(doctype, name, code, requested_by, **kw):
        log.append("engine.submit")
        calls["engine_submit"].append({"doctype": doctype, "name": name, "code": code,
                                       "kwargs": kw})
        return "AR-NEW-1"

    def _resubmit(request_name, actor=None):
        log.append("engine.resubmit")
        calls["engine_resubmit"].append(request_name)
        if resubmit_raises:
            raise resubmit_raises
        return resubmit_result

    engine_mod.submit = _submit
    engine_mod.resubmit = _resubmit

    guard_mod = types.ModuleType("guard")
    guard_mod.requester_signature_required = lambda dt, code: signature_required

    requester_mod = types.ModuleType("requester")

    def _assert_ready(dt, name):
        log.append("assert_ready_to_submit")
        calls["assert_ready"].append((dt, name))

    def _sign_on_submit(dt, name):
        log.append("sign_on_submit")
        calls["sign_on_submit"].append((dt, name))

    requester_mod.assert_ready_to_submit = _assert_ready
    requester_mod.sign_on_submit = _sign_on_submit

    saved = {}
    mods = {
        "frappe": frappe_mod,
        "frappe.utils": utils_mod,
        "ecentric_workspace.approval_center.shared.workflow.transitions": engine_mod,
        "ecentric_workspace.platform.esign.guard": guard_mod,
        "ecentric_workspace.platform.esign.requester": requester_mod,
    }
    # cha goi bang `from X import Y`: can ca goi cha co attribute
    wf_pkg = types.ModuleType("ecentric_workspace.approval_center.shared.workflow")
    wf_pkg.transitions = engine_mod
    esign_pkg = types.ModuleType("ecentric_workspace.platform.esign")
    esign_pkg.guard = guard_mod
    esign_pkg.requester = requester_mod
    mods["ecentric_workspace.approval_center.shared.workflow"] = wf_pkg
    mods["ecentric_workspace.platform.esign"] = esign_pkg

    import sys
    for k, v in mods.items():
        saved[k] = sys.modules.get(k)
        sys.modules[k] = v
    env = {}
    try:
        exec(compile(_read("approval_center", "shared", "finance_support.py"),
                     "finance_support.py", "exec"), env)
        yield_env = env
    finally:
        # finance_support dung _LazyFrappe (import luc goi) va import engine/esign BEN TRONG
        # ham - nen KHONG khoi phuc sys.modules o day; nguoi goi phai giu context.
        pass
    return yield_env, log, calls, (saved, mods)


class _Ctx(object):
    """Giu sys.modules gia trong khi test chay ham, roi tra lai nguyen trang."""

    def __init__(self, *args, **kw):
        self._args, self._kw = args, kw

    def __enter__(self):
        self.env, self.log, self.calls, (self._saved, _m) = _load_finance(*self._args, **self._kw)
        return self

    def __exit__(self, *exc):
        import sys
        for k, v in self._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        return False


def _payment_doc(log, **over):
    base = dict(approval_request=None, requested_by="hoan.tran@ec.vn", employee=None,
                company=None, request_title=None, name="EC-PAYR-2026-00001",
                submitted_at=None)
    base.update(over)
    return _FakeDoc(log, **base)


def _submitter(env, validator=None):
    return env["Submitter"](
        doctype="EC Payment Request", code="PAYMENT_REQUEST",
        validator=validator or (lambda d: None),
        title_builder=lambda d: "Thanh toan test",
        manager_required=True, requester_esign=True)


class TestSubmitTwiceIsBlocked(unittest.TestCase):
    def test_gui_lan_hai_bi_chan_va_khong_tao_request_thu_hai(self):
        log = []
        doc = _payment_doc(log)
        with _Ctx(doc, signature_required=False) as c:
            sub = _submitter(c.env)
            first = sub("EC-PAYR-2026-00001")
            self.assertEqual(first, "AR-NEW-1")
            # phieu gio da mang approval_request (nhu frappe.db.set_value ngoai doi)
            doc.approval_request = "AR-NEW-1"
            with self.assertRaises(_Throw) as ctx:
                sub("EC-PAYR-2026-00001")
            self.assertIn("đã được gửi", str(ctx.exception))
            self.assertEqual(len(c.calls["engine_submit"]), 1,
                             "lan hai khong duoc phep tao them EC Approval Request")

    def test_khong_phai_chu_phieu_thi_khong_gui_ho_duoc(self):
        log = []
        doc = _payment_doc(log, requested_by="nguoi.khac@ec.vn")
        with _Ctx(doc, signature_required=False, roles=("Employee",)) as c:
            sub = _submitter(c.env)
            with self.assertRaises(_PermissionError):
                sub("EC-PAYR-2026-00001")
            self.assertEqual(c.calls["engine_submit"], [])

    def test_thieu_quan_ly_truc_tiep_thi_chan_truoc_khi_gui(self):
        log = []
        doc = _payment_doc(log)
        with _Ctx(doc, signature_required=False, manager_user=None) as c:
            sub = _submitter(c.env)
            with self.assertRaises(_Throw) as ctx:
                sub("EC-PAYR-2026-00001")
            self.assertIn("Quản lý trực tiếp", str(ctx.exception))
            self.assertEqual(c.calls["engine_submit"], [])


class TestSubmitWithRequesterSignature(unittest.TestCase):
    def test_tu_choi_truoc_khi_ghi_va_ky_ngay_sau_khi_gui(self):
        log = []
        doc = _payment_doc(log)
        with _Ctx(doc, signature_required=True, log=log) as c:
            sub = _submitter(c.env)
            sub("EC-PAYR-2026-00001")
            # 1. thu tu: kiem tra vi tri ky TRUOC khi save - nem sau khi ghi la mo cua cho
            #    mot commit tuong lai bien loi tu choi thanh phieu ket vinh vien
            self.assertIn("assert_ready_to_submit", log)
            self.assertLess(log.index("assert_ready_to_submit"), log.index("doc.save"),
                            "phai tu choi TRUOC document.save() - thu tu thuc te: %r" % log)
            # 2. cap 1 KHONG kich hoat khi con cho nguoi de nghi ky
            kw = c.calls["engine_submit"][0]["kwargs"]
            self.assertEqual(kw.get("activate_first_level"), False,
                             "cap 1 phai cho den khi nguoi de nghi ky xong")
            # 3. trang thai cho ky duoc danh dau, roi ky ngay trong cung mot lenh
            self.assertIn(("EC Approval Request", "AR-NEW-1",
                           "requester_signature_status", "Pending"), c.calls["set_value"])
            self.assertEqual(c.calls["sign_on_submit"],
                             [("EC Payment Request", "EC-PAYR-2026-00001")])
            self.assertLess(log.index("engine.submit"), log.index("sign_on_submit"))

    def test_khong_yeu_cau_ky_thi_kich_hoat_cap_1_ngay_va_khong_dung_module_ky(self):
        log = []
        doc = _payment_doc(log)
        with _Ctx(doc, signature_required=False) as c:
            sub = _submitter(c.env)
            sub("EC-PAYR-2026-00001")
            kw = c.calls["engine_submit"][0]["kwargs"]
            self.assertEqual(kw.get("activate_first_level"), True)
            self.assertEqual(c.calls["sign_on_submit"], [])
            self.assertEqual(c.calls["assert_ready"], [])
            for (_dt, _n, field, value) in c.calls["set_value"]:
                self.assertNotEqual((field, value), ("requester_signature_status", "Pending"))


class TestResubmitSignsExactlyWhenRevised(unittest.TestCase):
    def test_goi_ky_lam_moi_thi_phai_ky_lai_ngay(self):
        log = []
        doc = _payment_doc(log, approval_request="AR-1")
        with _Ctx(doc, signature_required=True,
                  resubmit_result={"esign": {"revised": True, "new_package": "PKG-2"}}) as c:
            resub = c.env["Resubmitter"]("EC Payment Request", lambda d: "title")
            out = resub("EC-PAYR-2026-00001")
            self.assertTrue(out["restarted"])
            self.assertEqual(c.calls["sign_on_submit"],
                             [("EC Payment Request", "EC-PAYR-2026-00001")],
                             "goi Draft moi khong co nut nao ngoai duong nay - bo sot la "
                             "phieu ket vinh vien o 'cho nguoi de nghi ky'")

    def test_khong_doi_thi_khong_bat_ky_lai(self):
        log = []
        doc = _payment_doc(log, approval_request="AR-1")
        with _Ctx(doc, signature_required=True,
                  resubmit_result={"esign": {"revised": False, "unchanged": True}}) as c:
            resub = c.env["Resubmitter"]("EC Payment Request", lambda d: "title")
            out = resub("EC-PAYR-2026-00001")
            self.assertTrue(out["restarted"])
            self.assertEqual(c.calls["sign_on_submit"], [],
                             "chi dinh kem them bang chung ma bat ca chuoi ky lai la dung "
                             "cai phien toai da bo di hom 28/08")

    def test_engine_chan_thi_loi_lan_len_va_khong_ky_gi(self):
        log = []
        doc = _payment_doc(log, approval_request="AR-1")
        boom = _Throw("Tài liệu cần ký đã thay đổi so với bộ đã ký.")
        with _Ctx(doc, signature_required=True, resubmit_raises=boom) as c:
            resub = c.env["Resubmitter"]("EC Payment Request", lambda d: "title")
            with self.assertRaises(_Throw):
                resub("EC-PAYR-2026-00001")
            self.assertEqual(c.calls["sign_on_submit"], [])

    def test_chua_gui_thi_khong_gui_lai_duoc(self):
        log = []
        doc = _payment_doc(log, approval_request=None)
        with _Ctx(doc, signature_required=True) as c:
            resub = c.env["Resubmitter"]("EC Payment Request", lambda d: "title")
            with self.assertRaises(_Throw) as ctx:
                resub("EC-PAYR-2026-00001")
            self.assertIn("chưa được gửi", str(ctx.exception))
            self.assertEqual(c.calls["engine_resubmit"], [])


class TestPaymentDefinitionContract(unittest.TestCase):
    """Doc definition.py bang AST - khong grep de khoi trung chu thich."""

    def _make_call(self):
        src = _read("approval_center", "features", "payment_request", "domain", "definition.py")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_make":
                return src, tree, node
        raise AssertionError("khong tim thay loi goi _make trong definition.py")

    def test_payment_request_bat_esign_va_manager(self):
        _src, _tree, call = self._make_call()
        kw = {k.arg: k.value for k in call.keywords}
        self.assertIn("esign", kw)
        self.assertTrue(getattr(kw["esign"], "value", None) is True,
                        "PAYMENT_REQUEST phai co esign=True - toan bo duong Submit & Sign "
                        "dua vao co nay")
        self.assertTrue(getattr(kw["manager"], "value", None) is True)

    def test_o_cam_ket_ca_nhan_khong_duoc_chep_khi_clone(self):
        src = _read("approval_center", "features", "payment_request", "domain", "definition.py")
        tree = ast.parse(src)
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "clone_exclude_fields":
                for c in ast.walk(node.value):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        found.append(c.value)
        self.assertIn("details_and_attachments_correct", found,
                      "o 'toi xac nhan thong tin... chinh xac' la cam ket CA NHAN - chep "
                      "sang phieu moi la ky thay nguoi dung")


if __name__ == "__main__":
    unittest.main()
