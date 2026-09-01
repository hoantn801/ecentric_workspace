# Copyright (c) 2026, eCentric and contributors
"""E2E vong doi: chan ky NGUOI DE NGHI ket o 'Signed' -> cron phai hoan tat DUNG DUONG.

Boi canh. Chan ky co hai loai, hoan tat bang hai duong KHAC NHAU:

  * Approval Level -> svc.verify_and_complete -> engine.approve() dong cap duyet;
  * Requester      -> requester.reconcile_and_complete_requester -> kich hoat Cap 1
                      (KHONG BAO GIO engine.approve - nguoi de nghi khong phai approver).

tasks._complete_dsr (dong 240-246) ton tai dung de re nhanh nay. Nhung:

  [BUG - test do thu nhat] tasks.poll_pending dong ~478: gap DSR o trang thai 'Signed'
  thi goi THANG svc.verify_and_complete, khong nhin actor_type. Voi chan NGUOI DE NGHI
  bi ket o 'Signed' (worker chet giua chung - duong da xay ra 27-28/08), engine.approve
  se tu choi ("You are not a pending approver"), verify_and_complete phien dich cai tu
  choi do thanh Signed -> Manual Review. Roi duong cuu ho cua nguoi (api.reconcile ->
  service.reconcile_manual_review dong ~326) CUNG goi verify_and_complete -> lai Manual
  Review. Chan nguoi de nghi thanh ngo cut vinh vien: requester_signature_status ket o
  'Processing', Cap 1 khong bao gio kich hoat, va khoa idempotency unique chan viec tao
  chan moi. Sua: ca hai cho phai route qua tasks._complete_dsr (hoac kiem actor_type).

  [XANH - test thu hai] cron retrieve_signed_bundles phai THAT SU bo qua goi da
  retrieval_abandoned=1 (loc ngay trong truy van) va bo qua goi chua co chan ky
  Approval Completed - do bang cach GHI LAI truy van/loi goi that, khong grep nguon.

tasks.py duoc exec voi toan bo phu thuoc gia lap qua sys.modules; cac stub chi GHI LAI
loi goi (khong tu tra loi cau hoi cua chinh test - bay stub da biet).
"""
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


def _load_tasks(dsr_rows, pkg_rows=(), dsr_table=None, completed_exists=None):
    """Exec tasks.py that. Tra ve (env, calls, restore)."""
    import sys

    calls = {"svc_verify": [], "requester_reconcile": [], "get_all_filters": [],
             "retrieve_pkg": [], "enqueue": [], "events": [], "logs": []}

    class _DB(object):
        @staticmethod
        def get_value(dt, name_or_filters, fields=None, as_dict=False, for_update=False,
                      **kw):
            if dt == "EC Digital Signature Provider Settings":
                return 1                                    # integration_enabled
            if dt == "EC Digital Signature Request":
                row = (dsr_table or {}).get(name_or_filters, {})
                if isinstance(fields, str):
                    return row.get(fields)
                return _D(row)
            return None

        @staticmethod
        def exists(dt, filters):
            if dt == "EC Digital Signature Request":
                return completed_exists
            return None

        @staticmethod
        def count(dt, filters=None):
            return 0

        @staticmethod
        def set_value(*a, **kw):
            calls["logs"].append(("set_value", a))

    def get_all(dt, filters=None, fields=None, limit_page_length=None, **kw):
        calls["get_all_filters"].append((dt, dict(filters or {})))
        if dt == "EC Digital Signature Request":
            return [_D(r) for r in dsr_rows]
        if dt == "EC Digital Signature Package":
            out = []
            for r in pkg_rows:
                if (filters or {}).get("retrieval_abandoned") == 0 and r.get("retrieval_abandoned"):
                    continue            # stub CU XU nhu DB that: ap dung dieu kien loc
                out.append(_D(r))
            return out
        return []

    frappe_mod = types.ModuleType("frappe")
    frappe_mod.db = _DB
    frappe_mod.get_all = get_all
    frappe_mod._ = lambda s: s
    frappe_mod._dict = _D
    frappe_mod.conf = types.SimpleNamespace(get=lambda k: 0)
    frappe_mod.enqueue = lambda *a, **kw: calls["enqueue"].append((a, kw))
    frappe_mod.log_error = lambda *a, **kw: calls["logs"].append(("error_log", a))
    frappe_mod.get_traceback = lambda: "tb"
    frappe_mod.get_doc = lambda *a, **kw: None
    frappe_mod.session = types.SimpleNamespace(user="Administrator")

    utils_mod = types.ModuleType("frappe.utils")
    utils_mod.now_datetime = lambda: "2026-09-01 12:00:00"
    utils_mod.add_to_date = lambda d, **kw: d
    frappe_mod.utils = utils_mod

    binding_mod = types.ModuleType("binding")

    class BindingError(Exception):
        pass

    binding_mod.BindingError = BindingError
    binding_mod.assert_outbound_binding = lambda *a, **kw: None

    events_mod = types.ModuleType("events")
    events_mod.emit = lambda *a, **kw: calls["events"].append((a, kw))
    events_mod.set_dsr_status = lambda *a, **kw: calls["events"].append(("set_dsr", a, kw))
    events_mod.set_package_status = lambda *a, **kw: calls["events"].append(("set_pkg", a, kw))

    pkgsvc_mod = types.ModuleType("package")
    svc_mod = types.ModuleType("service")

    def verify_and_complete(dsr_name):
        calls["svc_verify"].append(dsr_name)
        return {"completed": True}

    svc_mod.verify_and_complete = verify_and_complete
    svc_mod._expected_for = lambda dsr: {}

    requester_mod = types.ModuleType("requester")

    def reconcile_and_complete_requester(dsr_name):
        calls["requester_reconcile"].append(dsr_name)
        return {"completed": True, "activated": True}

    requester_mod.reconcile_and_complete_requester = reconcile_and_complete_requester

    signed_files_mod = types.ModuleType("signed_files")
    signed_files_mod.retrieve_and_store_for_package = \
        lambda name, **kw: calls["retrieve_pkg"].append(name) or {"ok": True}
    signed_files_mod.retrieval_rounds = lambda name: 0

    base_mod = types.ModuleType("providers.base")

    class ProviderError(Exception):
        def __init__(self, code, msg, retryable=False):
            super(ProviderError, self).__init__(msg)
            self.code, self.retryable, self.ambiguous = code, retryable, False

    class SignatureProviderAdapter(object):
        @staticmethod
        def verify_signed_result(doc_state, expected):
            return types.SimpleNamespace(ok=False, reason="not_signed")

    class VerificationResult(object):
        def __init__(self, ok, reason):
            self.ok, self.reason = ok, reason

    base_mod.ProviderError = ProviderError
    base_mod.SignatureProviderAdapter = SignatureProviderAdapter
    base_mod.VerificationResult = VerificationResult

    providers_mod = types.ModuleType("providers")
    providers_mod.get_adapter = lambda settings: None
    providers_mod.base = base_mod

    sanitize_mod = types.ModuleType("sanitize")
    sanitize_mod.safe_error = lambda e: str(e)[:200]

    # `state` la module THAT, khong phai ban gia: no thuan (khong import frappe) va no giu
    # phep chan `may_have_sent` - chinh cai quyet dinh worker co gui lai lenh ky hay khong.
    # Gia lap no o day thi bo test se xac nhan mot luat do chinh no bia ra, dung lop sai ma
    # "stub tu tra loi chinh minh" da vap ba lan truoc do.
    state_mod = types.ModuleType("ecentric_workspace.platform.esign.state")
    exec(compile(_read("platform", "esign", "state.py"), "state.py", "exec"),  # noqa: S102
         state_mod.__dict__)

    esign_pkg = types.ModuleType("ecentric_workspace.platform.esign")
    for attr, m in (("binding", binding_mod), ("events", events_mod),
                    ("package", pkgsvc_mod), ("service", svc_mod),
                    ("providers", providers_mod), ("sanitize", sanitize_mod),
                    ("requester", requester_mod), ("signed_files", signed_files_mod),
                    ("state", state_mod)):
        setattr(esign_pkg, attr, m)

    mods = {
        "frappe": frappe_mod,
        "frappe.utils": utils_mod,
        "ecentric_workspace.platform.esign": esign_pkg,
        "ecentric_workspace.platform.esign.binding": binding_mod,
        "ecentric_workspace.platform.esign.events": events_mod,
        "ecentric_workspace.platform.esign.package": pkgsvc_mod,
        "ecentric_workspace.platform.esign.service": svc_mod,
        "ecentric_workspace.platform.esign.requester": requester_mod,
        "ecentric_workspace.platform.esign.signed_files": signed_files_mod,
        "ecentric_workspace.platform.esign.state": state_mod,
        "ecentric_workspace.platform.esign.providers": providers_mod,
        "ecentric_workspace.platform.esign.providers.base": base_mod,
        "ecentric_workspace.platform.esign.sanitize": sanitize_mod,
    }
    saved = {k: sys.modules.get(k) for k in mods}
    for k, v in mods.items():
        sys.modules[k] = v
    env = {}
    try:
        exec(compile(_read("platform", "esign", "tasks.py"), "tasks.py", "exec"), env)
        return env, calls, (saved, sys)
    except Exception:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        raise


class _Ctx(object):
    def __init__(self, *a, **kw):
        self._a, self._kw = a, kw

    def __enter__(self):
        self.env, self.calls, (self._saved, self._sys) = _load_tasks(*self._a, **self._kw)
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                self._sys.modules.pop(k, None)
            else:
                self._sys.modules[k] = v
        return False


class TestBugPollPendingRoutesRequesterLegWrong(unittest.TestCase):
    """[BUG TAI HIEN - do la dung] tasks.py:478 khong re nhanh theo actor_type."""

    def test_BUG_chan_nguoi_de_nghi_signed_phai_di_duong_requester(self):
        dsr_rows = [{"name": "DSR-REQ-1", "status": "Signed", "provider": "SCTS",
                     "environment": "UAT", "request_attempt": 1}]
        dsr_table = {"DSR-REQ-1": {"name": "DSR-REQ-1", "actor_type": "Requester",
                                   "actor_user": "hoan.tran@ec.vn", "package": "PKG-9",
                                   "status": "Signed"}}
        with _Ctx(dsr_rows, dsr_table=dsr_table) as c:
            c.env["poll_pending"]()
            self.assertEqual(
                c.calls["svc_verify"], [],
                "BUG tasks.py:478 - poll_pending day chan NGUOI DE NGHI dang 'Signed' vao "
                "svc.verify_and_complete (duong approver). engine.approve se tu choi "
                "('not a pending approver') va chan ky bi dong dau Manual Review; duong "
                "cuu ho service.py:326 (reconcile_manual_review) cung goi y het nen ket "
                "vinh vien: requester_signature_status ket 'Processing', Cap 1 khong bao "
                "gio kich hoat. Phai route qua tasks._complete_dsr (re theo actor_type).")
            self.assertEqual(c.calls["requester_reconcile"], ["DSR-REQ-1"],
                             "chan nguoi de nghi phai hoan tat bang "
                             "requester.reconcile_and_complete_requester")

    def test_chan_approval_level_signed_van_di_duong_engine(self):
        # doi chung: chan CAP DUYET o Signed thi duong cu (verify_and_complete) la DUNG
        dsr_rows = [{"name": "DSR-APP-1", "status": "Signed", "provider": "SCTS",
                     "environment": "UAT", "request_attempt": 1}]
        dsr_table = {"DSR-APP-1": {"name": "DSR-APP-1", "actor_type": "Approval Level",
                                   "approver": "sep@ec.vn", "package": "PKG-9",
                                   "status": "Signed"}}
        with _Ctx(dsr_rows, dsr_table=dsr_table) as c:
            c.env["poll_pending"]()
            self.assertEqual(c.calls["svc_verify"], ["DSR-APP-1"])
            self.assertEqual(c.calls["requester_reconcile"], [])
            # hoan tat that -> phai bam viec tai PDF da ky
            self.assertEqual(len(c.calls["enqueue"]), 1)


class TestRetrieveCronSkipsAbandonedAndUnfinished(unittest.TestCase):
    def test_cron_loc_goi_da_ngung_ngay_trong_truy_van(self):
        pkg_rows = [{"name": "PKG-LIVE", "provider": "SCTS", "environment": "UAT",
                     "retrieval_abandoned": 0},
                    {"name": "PKG-DEAD", "provider": "SCTS", "environment": "UAT",
                     "retrieval_abandoned": 1}]
        with _Ctx([], pkg_rows=pkg_rows, completed_exists="DSR-DONE") as c:
            c.env["retrieve_signed_bundles"]()
            pkg_filters = [f for (dt, f) in c.calls["get_all_filters"]
                           if dt == "EC Digital Signature Package"]
            self.assertTrue(pkg_filters, "cron phai truy van bang get_all")
            self.assertEqual(pkg_filters[0].get("retrieval_abandoned"), 0,
                             "khong loc trong truy van thi nut 'Ngung thu lai' chi la "
                             "trang tri - cron van goi mang moi 30 phut")
            self.assertEqual(c.calls["retrieve_pkg"], ["PKG-LIVE"],
                             "goi da ngung khong duoc cham toi")

    def test_goi_chua_co_chan_ky_hoan_tat_thi_cron_chua_tai(self):
        pkg_rows = [{"name": "PKG-EARLY", "provider": "SCTS", "environment": "UAT",
                     "retrieval_abandoned": 0}]
        with _Ctx([], pkg_rows=pkg_rows, completed_exists=None) as c:
            c.env["retrieve_signed_bundles"]()
            self.assertEqual(c.calls["retrieve_pkg"], [],
                             "chua co Approval Completed nao thi PDF chua the du chu ky")


if __name__ == "__main__":
    unittest.main()
