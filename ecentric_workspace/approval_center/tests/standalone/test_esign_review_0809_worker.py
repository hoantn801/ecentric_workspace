# Copyright (c) 2026, eCentric and contributors
"""Ra soat SCTS dem 08/09 - WORKER (tasks.process_signing_request chay THAT tren frappe gia).

Ba lo hong o duong "co the da gui":
  A. Lenh ky ket qua KHONG RO (timeout/5xx): truoc day chi de lai status Verifying. Lan poll
     sau gap loi mang tam thoi -> Retryable Failure (de len error_code) -> poll_pending dua ve
     Queued (khong tang attempt) -> may_have_sent False -> GUI LAN HAI. Nay: BulkOutcomeUnknown
     dong chot `accepted_at` (mot chieu, song qua moi trang thai sau).
  B. AddDocument ket qua khong ro (chua goi lenh ky) thi KHONG dong chot - `sent_attempted`.
  C. Poll tam thoi hong tren chan DA GUI (Provider Accepted / Verifying + accepted_at): giu
     nguyen trang thai + PollTick (+ fast_verify), khong xuong Retryable Failure. Truoc day mot
     GET truot 1 giay sau khi gui = Manual Review "prior_bulk_submit_uncertain".
  D. Chan Verifying KHONG co accepted_at (create-ambiguous) gap loi tam thoi: van Retryable
     Failure nhu cu (duong nay can RF -> Queued de gui sau khi doi soat tao chung tu).
  E. Moi duong DUNG (MR/PF) deu goi _leg_stopped -> chan nguoi de nghi duoc chieu sang
     requester_signature_status (truoc day 8 duong bo sot).
Trang thai ap dung qua state.assert_transition THAT: canh nao khong hop le thi test no.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


class _PErr(Exception):
    def __init__(self, code, msg="", retryable=False, ambiguous=False):
        super().__init__(msg); self.code = code; self.retryable = retryable; self.ambiguous = ambiguous


class _VR(object):
    def __init__(self, ok, reason):
        self.ok = ok; self.reason = reason


class _Doc(object):
    status = "processing"; signers = []; files = []
    def signer(self, *a):
        return None


def _state():
    m = types.ModuleType("sm")
    exec(compile(_read("platform", "esign", "state.py"), "state.py", "exec"), m.__dict__)
    return m


def _harness(row, adapter, create_raises=None):
    """exec tasks.py voi frappe gia; `row` la dong DSR duy nhat (dict, bi ghi tai cho)."""
    sm = _state()
    fk = types.ModuleType("frappe"); fk._ = lambda s: s
    fk.enqueued = []; fk.logs = []; fk.todos = []
    fk.conf = {}
    row.setdefault("request_attempt", 1); row.setdefault("action", "Sign")
    row.setdefault("provider", "scts"); row.setdefault("environment", "Production")
    row.setdefault("package", "PKG-1"); row.setdefault("actor_type", "Approval Level")
    row.setdefault("approver", "sep@ec.vn"); row.setdefault("effective_scts_user_id", "U1")
    row.setdefault("effective_signature_id", "S1"); row.setdefault("name", "DSR-1")

    def get_value(dt, name=None, fields=None, as_dict=False, for_update=False, **k):
        if dt == "EC Digital Signature Provider Settings":
            return {"integration_enabled": 1, "environment": "Production"}
        if dt == "EC Digital Signature Request":
            if fields == "*":
                return frappe_dict(dict(row))
            if isinstance(fields, (list, tuple)):
                return frappe_dict({f: row.get(f) for f in fields})
            return row.get(fields)
        if dt == "EC Digital Signature Package":
            return "PROF" if fields == "profile" else frappe_dict({"scts_document_id": "doc-1"})
        return None

    class frappe_dict(dict):                  # nhu frappe._dict: thieu khoa -> None
        def __getattr__(self, k):
            return self.get(k)
        def __setattr__(self, k, v):
            self[k] = v

    fk._dict = frappe_dict
    fk.commits = []
    fk.db = types.SimpleNamespace(get_value=get_value, exists=lambda *a, **k: False,
                                  count=lambda *a, **k: 0, commit=lambda: fk.commits.append(1),
                                  set_value=lambda dt, n, v=None, *a, **k: row.update(v if isinstance(v, dict) else {v: a[0]}))
    fk.get_all = lambda *a, **k: []
    fk.enqueue = lambda *a, **k: fk.enqueued.append((a, k))
    fk.log_error = lambda *a, **k: fk.logs.append(a)
    fk.get_traceback = lambda: "tb"
    fk.session = types.SimpleNamespace(user="Administrator")
    fk.get_doc = lambda *a, **k: types.SimpleNamespace(insert=lambda **kk: None)
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: "2026-09-08 03:00:00"; utils.add_to_date = lambda *a, **k: None

    ev = types.ModuleType("events"); ev.calls = []
    def set_dsr_status(name, status, extra_fields=None, **k):
        sm.assert_transition(sm.DSR, row["status"], status)      # canh THAT
        row["status"] = status; row.update(extra_fields or {})
        ev.calls.append(("set", status, extra_fields or {}, k))
    ev.set_dsr_status = set_dsr_status
    ev.set_package_status = lambda *a, **k: None
    ev.emit = lambda et, **k: ev.calls.append(("emit", et, k))

    base = types.ModuleType("base"); base.ProviderError = _PErr; base.VerificationResult = _VR
    base.SignatureProviderAdapter = type("A", (), {"verify_signed_result": staticmethod(lambda d, e: _VR(False, "not_signed_yet"))})
    prov = types.ModuleType("providers"); prov.get_adapter = lambda s: adapter
    san = types.ModuleType("sanitize"); san.safe_error = lambda e: "safe:" + str(e)
    binding = types.ModuleType("binding"); binding.BindingError = type("BindingError", (Exception,), {})
    binding.assert_outbound_binding = lambda *a, **k: None
    svc = types.ModuleType("service"); svc.completed = []
    svc._expected_for = lambda d: {}
    svc.verify_and_complete = lambda n: svc.completed.append(n) or {"completed": False}
    pkg = types.ModuleType("package"); pkg.workflow_instance_id = lambda p: "inst-1"
    nh = types.ModuleType("next_handler"); nh.plans = []
    nh.plan_handover = lambda *a, **k: nh.plans.append(k) or {"mode": "pool", "reason": "test"}
    nh.requester_actor = lambda *a, **k: None
    ul = types.ModuleType("user_link"); ul.needs_own_token = lambda *a, **k: False
    req = types.ModuleType("requester"); req.reconciled = []
    req.reconcile_and_complete_requester = lambda n: req.reconciled.append(n) or {"completed": False}
    mods = {"frappe": fk, "frappe.utils": utils,
            "ecentric_workspace.platform.esign.binding": binding,
            "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.package": pkg,
            "ecentric_workspace.platform.esign.service": svc,
            "ecentric_workspace.platform.esign.state": sm,
            "ecentric_workspace.platform.esign.next_handler": nh,
            "ecentric_workspace.platform.esign.user_link": ul,
            "ecentric_workspace.platform.esign.requester": req,
            "ecentric_workspace.platform.esign.providers": prov,
            "ecentric_workspace.platform.esign.providers.base": base,
            "ecentric_workspace.platform.esign.sanitize": san}
    # Stub PHAI o lai trong sys.modules: tasks.py import lazy (user_link, next_handler,
    # requester, package.workflow_instance_id) NGAY TRONG process_signing_request. Go stub sau
    # exec thi lan goi that se import frappe that -> ModuleNotFoundError bi nuot vao log_error
    # va test "xanh" tren mot worker chua chay gi ca.
    sys.modules.update(mods)
    m = types.ModuleType("_tasks_under_test")
    exec(compile(_read("platform", "esign", "tasks.py"), "tasks.py", "exec"), m.__dict__)

    def _ensure(dsr, settings, adapter_):
        if create_raises:
            raise create_raises
        return "doc-1"
    m._ensure_provider_document = _ensure
    m._dead_letter_todo = lambda name: fk.todos.append(name)
    m._fk = fk; m._ev = ev; m._sm = sm; m._svc = svc; m._req = req; m._nh = nh; m._row = row
    fk.get_traceback = lambda: __import__("traceback").format_exc()
    return m


class _Adapter(object):
    def __init__(self, poll_raise=None, sign_raise=None):
        self.poll_raise = poll_raise; self.sign_raise = sign_raise; self.sends = 0; self.polls = 0
    def poll_status(self, doc_id):
        self.polls += 1
        if self.poll_raise:
            raise self.poll_raise
        return _Doc()
    def approve_and_sign(self, *a, **k):
        self.sends += 1
        if self.sign_raise:
            raise self.sign_raise
        return {"bulk_job_transaction_id": None}


def _sets(m, status):
    return [c for c in m._ev.calls if c[0] == "set" and c[1] == status]


class TestAmbiguousSendLatch(unittest.TestCase):
    def test_A_lenh_ky_khong_ro_ket_qua_dong_chot_accepted_at(self):
        ad = _Adapter(sign_raise=_PErr("scts_bulk_outcome_unknown", "timeout", ambiguous=True))
        m = _harness({"status": "Queued"}, ad)
        m.process_signing_request("DSR-1")
        self.assertEqual(ad.sends, 1)
        self.assertEqual(m._row["status"], "Verifying")
        self.assertTrue(m._row.get("accepted_at"), "BulkOutcomeUnknown phai dong chot accepted_at")
        self.assertTrue(m._sm.may_have_sent(m._row))
        # vong sau: poll loi tam thoi -> KHONG xuong Retryable Failure, KHONG gui lai
        ad.poll_raise = _PErr("scts_http_503", "x", retryable=True)
        m.process_signing_request("DSR-1")
        self.assertEqual(m._row["status"], "Verifying")
        self.assertEqual(ad.sends, 1, "khong duoc gui lan hai")
        self.assertTrue([c for c in m._ev.calls if c[0] == "emit" and c[1] == "PollTick"
                         and str(c[2].get("verification_result", "")).startswith("poll_error:")])

    def test_A2_du_co_ve_Queued_chot_van_dong(self):
        """Ke ca khi ai do dua chan nay ve Queued (RF -> Queued cua poll_pending), worker van
        khong gui vi accepted_at da co - do la y nghia cua chot mot chieu."""
        ad = _Adapter(sign_raise=_PErr("scts_bulk_outcome_unknown", "timeout", ambiguous=True))
        m = _harness({"status": "Queued"}, ad)
        m.process_signing_request("DSR-1")
        m._row["status"] = "Queued"                       # gia lap RetryScheduled
        ad.sign_raise = None
        m.process_signing_request("DSR-1")
        self.assertEqual(ad.sends, 1)
        self.assertEqual(m._row["status"], "Manual Review")
        self.assertEqual(m._row.get("manual_review_reason"), "prior_bulk_submit_uncertain")
        self.assertEqual(m._fk.todos, ["DSR-1"], "Manual Review phai co dead-letter ToDo")

    def test_B_addDocument_khong_ro_KHONG_dong_chot(self):
        ad = _Adapter()
        m = _harness({"status": "Queued"}, ad,
                     create_raises=_PErr("scts_create_outcome_unknown", "timeout", ambiguous=True))
        m.process_signing_request("DSR-1")
        self.assertEqual(ad.sends, 0)
        self.assertEqual(m._row["status"], "Verifying")
        self.assertFalse(m._row.get("accepted_at"), "chua goi lenh ky thi khong duoc dong chot")

    def test_C_poll_tam_thoi_hong_tren_chan_da_gui_giu_nguyen(self):
        for st in ("Provider Accepted", "Verifying"):
            ad = _Adapter(poll_raise=_PErr("scts_http_503", "x", retryable=True))
            m = _harness({"status": st, "accepted_at": "2026-09-08 02:59:00"}, ad)
            m.process_signing_request("DSR-1")
            self.assertEqual(m._row["status"], st, st)
            self.assertEqual(_sets(m, "Retryable Failure"), [], st)
            self.assertEqual(ad.sends, 0)
            ticks = [c for c in m._ev.calls if c[0] == "emit" and c[1] == "PollTick"]
            self.assertEqual(len(ticks), 1, "moi lan poll phai de lai vet")
            fast = [a for a, k in m._fk.enqueued if a and "fast_verify" in a[0]]
            self.assertEqual(len(fast), 1 if st == "Provider Accepted" else 0, st)

    def test_C2_gui_xong_poll_ngay_hong_van_Provider_Accepted(self):
        """Lenh gui thanh cong, GET ngay sau do truot: chan o Provider Accepted + accepted_at,
        fast_verify duoc bam - khong roi vao Retryable Failure."""
        ad = _Adapter()
        m = _harness({"status": "Queued"}, ad)
        calls = {"n": 0}
        def poll(doc_id):
            calls["n"] += 1
            if calls["n"] >= 2:                     # lan 1: poll-first (song), lan 2: sau gui
                raise _PErr("scts_http_502", "x", retryable=True)
            return _Doc()
        ad.poll_status = poll
        m.process_signing_request("DSR-1")
        self.assertEqual(ad.sends, 1)
        self.assertEqual(m._row["status"], "Provider Accepted")
        self.assertTrue(m._row.get("accepted_at"))
        self.assertTrue([a for a, k in m._fk.enqueued if "fast_verify" in a[0]])

    def test_D_verifying_khong_accepted_at_van_RF_nhu_cu(self):
        ad = _Adapter(poll_raise=_PErr("scts_http_503", "x", retryable=True))
        m = _harness({"status": "Verifying"}, ad)
        m.process_signing_request("DSR-1")
        self.assertEqual(m._row["status"], "Retryable Failure")

    def test_loi_vinh_vien_van_Permanent_Failure(self):
        ad = _Adapter(poll_raise=_PErr("scts_auth_401", "x", retryable=False))
        m = _harness({"status": "Verifying", "accepted_at": "2026-09-08 02:59:00"}, ad)
        m.process_signing_request("DSR-1")
        self.assertEqual(m._row["status"], "Permanent Failure")
        self.assertEqual(m._fk.todos, ["DSR-1"])


class TestLegStoppedRoutesRequester(unittest.TestCase):
    def test_chan_nguoi_de_nghi_dung_o_MR_thi_reconcile(self):
        ad = _Adapter(sign_raise=_PErr("scts_bulk_outcome_unknown", "t", ambiguous=True))
        m = _harness({"status": "Queued", "actor_type": "Requester", "actor_user": "hien@ec.vn"}, ad)
        m.process_signing_request("DSR-1")
        m._row["status"] = "Queued"
        ad.sign_raise = None
        m.process_signing_request("DSR-1")              # -> Manual Review prior_bulk_submit_uncertain
        self.assertEqual(m._row["status"], "Manual Review")
        self.assertEqual(m._req.reconciled, ["DSR-1"], "chan nguoi de nghi dung -> reconcile")
        self.assertEqual(m._svc.completed, [], "khong duoc re sang duong approver")

    def test_chan_cap_duyet_dung_khong_goi_reconcile(self):
        ad = _Adapter(poll_raise=_PErr("scts_auth_401", "x", retryable=False))
        m = _harness({"status": "Verifying", "accepted_at": "x"}, ad)
        m.process_signing_request("DSR-1")
        self.assertEqual(m._req.reconciled, [])

    def test_moi_duong_dung_trong_tasks_deu_qua_leg_stopped(self):
        src = _read("platform", "esign", "tasks.py")
        tree = ast.parse(src)
        stops = 0; leg = 0
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Attribute) and f.attr == "set_dsr_status" and len(n.args) >= 2 \
                        and isinstance(n.args[1], ast.Constant) \
                        and n.args[1].value in ("Manual Review", "Permanent Failure"):
                    stops += 1
                if isinstance(f, ast.Name) and f.id == "_leg_stopped":
                    leg += 1
        self.assertGreaterEqual(stops, 7, "cach doc AST lac hau")
        self.assertGreaterEqual(leg, stops,
                                "co %d cho ghi Manual Review/Permanent Failure nhung chi %d cho goi "
                                "_leg_stopped - mot duong dung bo sot chan nguoi de nghi" % (stops, leg))

    def test_document_id_di_kem_ke_hoach_handover(self):
        ad = _Adapter()
        m = _harness({"status": "Queued"}, ad)
        m.process_signing_request("DSR-1")
        self.assertEqual(m._nh.plans[0].get("document_id"), "doc-1")
        self.assertEqual(m._nh.plans[0].get("instance_id"), "inst-1")
        nh = _read("platform", "esign", "next_handler.py")
        self.assertIn("provider_step_index(adapter, document_id or instance_id)", nh,
                      "dem chu ky phai hoi GET /api/Document/{documentId}, khong phai instance id")


class TestCronCommitsPerLeg(unittest.TestCase):
    def test_moi_vong_cron_chot_sau_tung_chan(self):
        src = _read("platform", "esign", "tasks.py")
        tree = ast.parse(src)
        for name in ("poll_pending", "flag_silent_legs", "sweep_stale", "retrieve_signed_bundles"):
            fn = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name][0]
            loops = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
            self.assertTrue(loops, name)
            last = loops[0].body[-1]
            self.assertTrue(isinstance(last, ast.Expr) and isinstance(last.value, ast.Call)
                            and getattr(last.value.func, "id", "") == "_commit_step",
                            "%s: cau cuoi cua vong for phai la _commit_step() - khong thi khoa hang "
                            "cua chan dau giu toi khi chan cuoi xong" % name)
        fv = ast.unparse([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "fast_verify"][0])
        i = fv.index("process_signing_request(dsr_name)")
        self.assertIn("_commit_step()", fv[i:i + 300], "fast_verify phai nha khoa truoc khi ngu")

    def test_poll_pending_chot_sau_moi_chan(self):
        ad = _Adapter()
        m = _harness({"status": "Verifying", "accepted_at": "x"}, ad)
        rows = [types.SimpleNamespace(name="DSR-1", status="Verifying", provider="scts",
                                      environment="Production", request_attempt=1)] * 2
        m._fk.get_all = lambda *a, **k: rows
        m.poll_pending()
        self.assertEqual(len(m._fk.commits), 2)


if __name__ == "__main__":
    unittest.main()
