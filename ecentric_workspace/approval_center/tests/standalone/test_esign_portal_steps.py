# Copyright (c) 2026, eCentric and contributors
"""Buoc tren cong KHONG KY + buoc NGUOI LAP (12/11/2026, hop dong WF09 - PR-B).

WF09 (doc dinh nghia quy trinh tren cong 12/11): Khoi tao (3) -`-2` Trinh KT-> KTTH (4)
-`-3` Phe duyet-> KTT (5) -`-4` Phe duyet-> CEO (6) -`-5` Chuyen doi tac (ky)-> Doi tac (7).
`-2/-3/-4` KHONG ky, khong co loai canh rieng; tu choi va doi tac ky deu la RETURN_CREATOR.
=> khong the doan canh di tiep theo loai; ho so khai TUNG BUOC (Forward, "level:<n>"), cong chi
XAC NHAN canh do dang mo.

Chot o day:
  1. DNTT (khong dong Approve, khong bat lay-buoc-tu-cong) Y HET truoc.
  2. Cap Approve: nut Duyet thuong bi chan; chi chan Approve da xac minh hoan tat duoc; cong tat
     thi chan (khong ghi no).
  3. Ke hoach: dung buoc khai tren ho so, cong phai dang mo canh do; chua mo -> CHO; thieu
     cau hinh / thieu anh xa / nguoi nhan khong hop le -> DUNG. Khong bao gio pool.
  4. Worker chan Approve: ghi moc buoc TRUOC khi gui, gui MOT lan khong chu ky, xac minh bang
     buoc cong; co the da gui thi khong gui lai; cong sang cho khac -> nguoi xu ly.
  5. Payload khong chu ky: signatureInfo null, signType null - nhu cong gui.
  6. Buoc nguoi lap: chi khi cap cong dau tien mo; nguoi nhan = cap dang mo.
"""
import ast
import io
import json
import os
import sys
import types
import unittest
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_APP = os.path.join(_ROOT, "ecentric_workspace")
_ESIGN = os.path.join(_APP, "platform", "esign")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _read(*parts):
    with io.open(os.path.join(_APP, *parts), encoding="utf-8") as fh:
        return fh.read()


def _fns(src, names):
    tree = ast.parse(src)
    out = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in names:
            out.append(ast.get_source_segment(src, n))
        if (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id in names):
            out.append(ast.get_source_segment(src, n))
    assert len(out) == len(names), (set(names), len(out))
    return "\n\n".join(out)


class _Throw(Exception):
    pass


class _D(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class PE(Exception):
    def __init__(self, code, message, retryable=False, ambiguous=False):
        super().__init__(message)
        self.code, self.retryable, self.ambiguous = code, retryable, ambiguous


# =============================================================================== guard
_GUARD = _read("platform", "esign", "guard.py")


def _guard(sign_levels=(), approve_levels=(), enabled="P", active="P", marker=None):
    calls = []
    g = {"frappe": types.SimpleNamespace(
        db=types.SimpleNamespace(exists=lambda dt, f: (
            f.get("provider_action") == "Approve" and f["parent"] == "P"
            and f["level_no"] in approve_levels)),
        flags=types.SimpleNamespace(ec_esign_completion_dsr=marker),
        throw=lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m)),
        PermissionError=PermissionError),
        "_": lambda s: s, "FLAG_KEY": "ec_esign_completion_dsr",
        "_MSG_SIGN_REQUIRED": "SIGN",
        "level_requires_signature": lambda dt, at, n, **k: n in sign_levels,
        "get_enabled_profile": lambda *a, **k: enabled,
        "get_active_profile": lambda *a, **k: active,
        "request_final_level": lambda r: 4,
        "validate_completion": lambda *a, **k: calls.append(("validate", a, k)),
        "_record_signature_debt": lambda *a, **k: calls.append(("debt", a)),
        }
    exec(compile(_fns(_GUARD, ["_MSG_PORTAL_APPROVE", "_deny", "_approve_level_row",
                               "level_portal_action", "assert_level_completable",
                               "_portal_approve_level"]), "g", "exec"), g)
    g["_calls"] = calls
    return g


REQ = _D(name="AR-1", reference_doctype="EC Contract Review Request", approval_type="CR",
         reference_name="CR-1", current_level=2)


class TestGuard(unittest.TestCase):
    def test_hanh_dong_cap(self):
        g = _guard(sign_levels=(4,), approve_levels=(2, 3))
        f = g["level_portal_action"]
        self.assertEqual([f("D", "CR", n, business_name="CR-1") for n in (1, 2, 3, 4)],
                         [None, "Approve", "Approve", "Sign"])

    def test_ky_thang_approve(self):
        g = _guard(sign_levels=(2,), approve_levels=(2,))
        self.assertEqual(g["level_portal_action"]("D", "CR", 2), "Sign")

    def test_khong_ho_so_la_None(self):
        g = _guard(approve_levels=(2,), enabled=None, active=None)
        self.assertIsNone(g["level_portal_action"]("D", "CR", 2))

    def test_cap_approve_doi_chan_approve(self):
        g = _guard(approve_levels=(2,), marker="DSR-9")
        g["assert_level_completable"](REQ, 2, "ktth@x")
        kind, args, kw = g["_calls"][0]
        self.assertEqual(kind, "validate")
        self.assertEqual(args[0], "DSR-9")
        self.assertEqual(kw, {"expected_action": "Approve"})
        self.assertEqual(args[3], "ktth@x", "danh tinh = nguoi bam, khong lay tu session")

    def test_cong_tat_thi_chan_khong_ghi_no(self):
        g = _guard(approve_levels=(2,), active=None)
        with self.assertRaises(_Throw) as c:
            g["assert_level_completable"](REQ, 2, "ktth@x")
        self.assertIn("portal_gates_closed", str(c.exception))
        self.assertEqual(g["_calls"], [])

    def test_cap_chi_erp_van_di_duong_ghi_no_cu(self):
        g = _guard(approve_levels=(2,))
        g["assert_level_completable"](REQ, 1, "tp@x")
        self.assertEqual([k for k, *_ in g["_calls"]], ["debt"])

    def test_cap_ky_van_validate_kieu_cu(self):
        g = _guard(sign_levels=(4,), marker="DSR-1")
        g["assert_level_completable"](REQ, 4, "ceo@x")
        kind, args, kw = g["_calls"][0]
        self.assertEqual((kind, kw), ("validate", {}))

    def test_ho_so_mo_ho_khong_thanh_duong_nem_moi(self):
        g = _guard(approve_levels=(2,))
        g["get_enabled_profile"] = lambda *a, **k: (_ for _ in ()).throw(_Throw("mo ho"))
        g["assert_level_completable"](REQ, 2, "x@x")
        self.assertEqual([k for k, *_ in g["_calls"]], ["debt"])

    def test_validate_so_action(self):
        fn = [n for n in ast.parse(_GUARD).body if isinstance(n, ast.FunctionDef)
              and n.name == "validate_completion"][0]
        seg = ast.get_source_segment(_GUARD, fn)
        self.assertIn('expected_action="Sign"', seg)
        self.assertIn("dsr.action != expected_action", seg)


# =============================================================================== next_handler
def _load(rel, name, fk_extra=None):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.conf = {}
    fk.db = types.SimpleNamespace(get_value=lambda *a, **k: None, exists=lambda *a, **k: None)
    fk.get_all = lambda *a, **k: []
    fk.get_doc = lambda *a, **k: None
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: "tb"
    fk.enqueue = lambda *a, **k: None
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: datetime(2026, 11, 12)
    utils.add_to_date = lambda *a, **k: None
    utils.get_datetime = lambda v: v
    for k, v in (fk_extra or {}).items():
        setattr(fk, k, v)
    mods = {"frappe": fk, "frappe.utils": utils}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        mod = types.ModuleType(name)
        exec(compile(_read("platform", "esign", rel), rel, "exec"), mod.__dict__)
        return mod, fk
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


ROWS = [_D(action="Forward", stage="requester", transition_id=-2, transition_name="Trinh KT",
           process_action=None, sign_type=None, terminal=0),
        _D(action="Forward", stage="level:2", transition_id=-3, transition_name="Phe duyet",
           process_action=None, sign_type=None, terminal=0),
        _D(action="Forward", stage="level:3", transition_id=-4, transition_name="Phe duyet",
           process_action=None, sign_type=None, terminal=0),
        _D(action="Sign", stage="level:4", transition_id=-5, transition_name="Chuyen doi tac",
           process_action="WfFunctionRunSignedA", sign_type="ky-chinh", terminal=0)]


def _edge(tid, signed=False, to="5", ttype="normal", pa=None):
    return {"transition_id": tid, "transition_name": "x", "transition_type": ttype,
            "requires_signature": signed, "process_action": pa, "sign_type": None,
            "to_state": to, "terminal": False}


def _nh(rows=ROWS, approvers=None, mapped=None, eligible=None, current_level=2):
    nh, fk = _load("next_handler.py", "_nh_portal")
    nh.frappe.get_doc = lambda dt, n: _D(transitions=rows)
    nh.frappe.db.get_value = lambda dt, n, f=None, **k: current_level if f == "current_level" \
        else None
    seen = {}

    def nla(ar, level):
        seen["level"] = level
        return (approvers if approvers is not None else {1: ["ktt@x"], 2: ["ktt@x"],
                                                         3: ["ceo@x"]}).get(level, [])
    nh.next_level_approvers = nla
    nh.provider_ids_for = lambda users, env: (
        mapped if mapped is not None else (["P-" + u for u in users], []))
    nh._level_of = lambda dsr: dsr.get("lvl", 2)
    nh._seen = seen
    adapter = types.SimpleNamespace(eligible_recipients=lambda *a: eligible)
    return nh, adapter


DSR_KTTH = _D(name="DSR-1", approval_request="AR-1", action="Approve",
              actor_type="Approval Level", effective_scts_user_id="U-KTTH", lvl=2)
STATE_4 = {"current_state_id": "4", "transitions": [_edge(-3, to="5"),
                                                   _edge(-8, ttype="RETURN_CREATOR",
                                                         to="STOP")]}


class TestKeHoach(unittest.TestCase):
    def test_dung_buoc_khai_cong_xac_nhan(self):
        nh, ad = _nh()
        p = nh.plan_portal_step(DSR_KTTH, STATE_4, "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["mode"], "transition")
        self.assertEqual(p["config"]["transition_id"], -3)
        self.assertFalse(p["config"]["requires_signature"])
        self.assertEqual((p["state_before"], p["to_state"]), ("4", "5"))
        self.assertEqual(p["to_users"], ["P-ktt@x"])
        self.assertEqual(nh._seen["level"], 2, "nguoi nhan = cap 3 (KTT)")

    def test_canh_chua_mo_thi_cho(self):
        nh, ad = _nh()
        st = {"current_state_id": "3", "transitions": [_edge(-2, to="4")]}
        p = nh.plan_portal_step(DSR_KTTH, st, "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["mode"], "wait")

    def test_khong_doan_theo_loai_canh(self):
        """Cong mo DUY NHAT canh 'approve' khac buoc khai -> van CHO, khong gui canh do."""
        nh, ad = _nh()
        st = {"current_state_id": "4", "transitions": [_edge(-99, ttype="approve")]}
        self.assertEqual(nh.plan_portal_step(DSR_KTTH, st, "P", "UAT")["mode"], "wait")

    def test_thieu_cau_hinh_thi_dung(self):
        nh, ad = _nh(rows=[r for r in ROWS if r.stage != "level:2"])
        p = nh.plan_portal_step(DSR_KTTH, STATE_4, "P", "UAT")
        self.assertEqual((p["mode"], p["reason"]), ("stop", "no_step_config:Forward/level:2"))

    def test_hai_dong_cung_buoc_la_dung(self):
        nh, ad = _nh(rows=ROWS + [ROWS[1]])
        self.assertEqual(nh.plan_portal_step(DSR_KTTH, STATE_4, "P", "UAT")["mode"], "stop")

    def test_thieu_anh_xa_mot_nguoi_la_dung(self):
        nh, ad = _nh(mapped=(["P-1"], ["b@x"]))
        p = nh.plan_portal_step(DSR_KTTH, STATE_4, "P", "UAT")
        self.assertEqual(p["mode"], "stop")
        self.assertIn("b@x", p["reason"])

    def test_nguoi_nhan_khong_hop_le_la_dung(self):
        nh, ad = _nh(eligible={"P-khac"})
        p = nh.plan_portal_step(DSR_KTTH, STATE_4, "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["mode"], "stop")

    def test_khong_hoi_duoc_nguoi_nhan_thi_ghi_lai(self):
        nh, ad = _nh(eligible=None)
        p = nh.plan_portal_step(DSR_KTTH, STATE_4, "P", "UAT", adapter=ad, instance_id="I")
        self.assertTrue(p["recipients_unverified"])

    def test_nguoi_lap_trinh_cho_cap_DANG_MO(self):
        nh, ad = _nh(current_level=2)
        d = _D(DSR_KTTH, actor_type="Requester")
        st = {"current_state_id": "3", "transitions": [_edge(-2, to="4")]}
        p = nh.plan_portal_step(d, st, "P", "UAT")
        self.assertEqual(p["config"]["transition_id"], -2)
        self.assertEqual(nh._seen["level"], 1, "next_level_approvers(ar, 1) = cap 2 (KTTH)")

    def test_cap_ky_dung_dong_Sign(self):
        nh, ad = _nh(approvers={3: []})
        d = _D(DSR_KTTH, action="Sign", lvl=4)
        st = {"current_state_id": "6", "transitions": [_edge(-5, signed=True, to="7",
                                                             pa="WfFunctionRunSignedA")]}
        p = nh.plan_portal_step(d, st, "P", "UAT")
        self.assertEqual((p["mode"], p["reason"]), ("stop", "no_next_level_approver:partner_step_not_supported"),
                         "buoc doi tac (PR-D) chua lam: dung, khong gui mo")

    def test_khong_bao_gio_pool(self):
        src = _read("platform", "esign", "next_handler.py")
        fn = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)
              and n.name == "plan_portal_step"][0]
        fn.body = fn.body[1:]                 # bo docstring
        self.assertNotIn("pool", ast.unparse(fn))


# =============================================================================== worker
_TASKS = _read("platform", "esign", "tasks.py")


class _W(object):
    """Moi truong cho _process_portal_approve."""

    def __init__(self, dsr, states, plan, may_have_sent=False, send_raises=None):
        self.log = []
        self.sets = {}
        self.states = list(states)
        self.sent = []
        g = {"frappe": types.SimpleNamespace(
            db=types.SimpleNamespace(set_value=lambda dt, n, f, v=None: self.sets.update(
                {f: v} if isinstance(f, str) else f))),
             "sm": types.SimpleNamespace(may_have_sent=lambda d: may_have_sent),
             "svc": types.SimpleNamespace(mark_verified=lambda n, r: self.log.append(
                 ("verified", r))),
             "events": types.SimpleNamespace(
                 emit=lambda et, **k: self.log.append(("emit", et)),
                 set_dsr_status=lambda n, st, **k: self.log.append(("status", st))),
             "ProviderError": PE, "DSR": "DSR", "now_datetime": lambda: "NOW",
             "_complete_dsr": lambda n, d: self.log.append(("complete",)) or {"ok": 1},
             "_dead_letter_todo": lambda n: self.log.append(("todo",)),
             "_leg_stopped": lambda n, d=None: self.log.append(("stopped",)),
             "_enqueue_fast_verify": lambda n: self.log.append(("fast",)),
             "_profile_of": lambda d: "P"}
        nh = types.ModuleType("ecentric_workspace.platform.esign.next_handler")
        nh.plan_portal_step = lambda *a, **k: plan
        nh.requester_actor = lambda d, s, stage: "ACT-" + stage
        pk = types.ModuleType("ecentric_workspace.platform.esign.package")
        pk.workflow_instance_id = lambda p: None
        self.mods = {"ecentric_workspace.platform.esign.next_handler": nh,
                     "ecentric_workspace.platform.esign.package": pk}
        exec(compile(_fns(_TASKS, ["_portal_moved", "_same_shape", "_process_portal_approve"]),
                     "t", "exec"), g)
        self.g = g
        me = self

        class Ad(object):
            def workflow_state_for_document(self, doc, uid):
                s = me.states.pop(0) if me.states else None
                return (s, None) if s else (None, "het")

            def transition_with_recipients(self, inst, uid, to, cfg, sig, actor_user_id=None):
                me.sent.append((inst, uid, to, cfg, sig, dict(me.sets)))
                me.actor = actor_user_id
                if send_raises:
                    raise send_raises
                return {"bulk_job_transaction_id": None}
        self.ad = Ad()
        self.dsr = dsr

    def run(self):
        saved = {k: sys.modules.get(k) for k in self.mods}
        sys.modules.update(self.mods)
        box = {}
        try:
            return self.g["_process_portal_approve"]("DSR-1", self.dsr, {"environment": "UAT"},
                                                     self.ad, "DOC", box), box
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v


PLAN = {"mode": "transition", "to_users": ["P-ktt"], "erp_users": ["ktt@x"],
        "config": {"transition_id": -3, "requires_signature": False},
        "state_before": "4", "to_state": "5", "transition_source": "discovered"}


def _q(**kw):
    return _D(dict(name="DSR-1", status="Queued", package="PKG", action="Approve",
                   effective_scts_user_id="U-KTTH"), **kw)


class TestWorker(unittest.TestCase):
    def test_gui_mot_lan_ghi_moc_truoc_roi_xac_minh(self):
        w = _W(_q(), [{"current_state_id": "4"}, {"current_state_id": "5"}], PLAN)
        out, box = w.run()
        self.assertEqual(len(w.sent), 1)
        inst, uid, to, cfg, sig, sets_at_send = w.sent[0]
        self.assertIsNone(sig, "khong chu ky")
        self.assertEqual(w.actor, "ACT-approval", "nguoi giu task tu requester_actor")
        self.assertEqual(sets_at_send.get("provider_state_before"), "4|5",
                         "moc buoc phai ghi TRUOC khi gui")
        self.assertTrue(box["sent"])
        self.assertIn(("verified", "portal_advanced:4->5"), w.log)
        self.assertIn(("complete",), w.log)

    def test_chua_roi_buoc_thi_verifying_va_hoi_nhanh(self):
        w = _W(_q(), [{"current_state_id": "4"}, {"current_state_id": "4"}], PLAN)
        w.run()
        self.assertIn(("status", "Verifying"), w.log)
        self.assertIn(("fast",), w.log)
        self.assertNotIn(("complete",), w.log)

    def test_lan_sau_thay_roi_buoc_thi_xong_khong_gui_lai(self):
        w = _W(_q(status="Verifying", provider_state_before="4|5"),
               [{"current_state_id": "5"}], PLAN, may_have_sent=True)
        w.run()
        self.assertEqual(w.sent, [])
        self.assertIn(("complete",), w.log)

    def test_cong_sang_cho_khac_la_nguoi_xu_ly(self):
        w = _W(_q(status="Verifying", provider_state_before="4|5"),
               [{"current_state_id": "9"}], PLAN, may_have_sent=True)
        w.run()
        self.assertIn(("status", "Manual Review"), w.log)
        self.assertIn(("stopped",), w.log, "chan nguoi lap dung -> bao nguoi lap")
        self.assertNotIn(("complete",), w.log)

    def test_khong_so_duoc_thi_giao_nguoi(self):
        f = _W(_q(), [], PLAN).g["_portal_moved"]
        self.assertIsNone(f("6|STOP", "9")[0], "ma dich la chu, ma hien tai la so")
        self.assertIsNone(f("4|", "5")[0], "khong biet buoc dich")
        self.assertIs(f("4|5", "4")[0], False, "chua roi buoc")
        self.assertIs(f("4|5", "5")[0], True)
        self.assertIs(f("", "5")[0], False, "khong co moc")

    def test_co_the_da_gui_thi_khong_gui_lai(self):
        w = _W(_q(provider_state_before="4|5"), [{"current_state_id": "4"}], PLAN,
               may_have_sent=True)
        w.run()
        self.assertEqual(w.sent, [])
        self.assertIn(("status", "Manual Review"), w.log)

    def test_cong_chua_toi_buoc_thi_cho(self):
        w = _W(_q(), [{"current_state_id": "3"}], {"mode": "wait", "reason": "step_not_open"})
        with self.assertRaises(PE) as c:
            w.run()
        self.assertTrue(c.exception.retryable)
        self.assertIn(("emit", "PortalStepWaiting"), w.log)
        self.assertEqual(w.sent, [])

    def test_dung_thi_loi_vinh_vien(self):
        w = _W(_q(), [{"current_state_id": "4"}], {"mode": "stop", "reason": "x"})
        with self.assertRaises(PE) as c:
            w.run()
        self.assertFalse(c.exception.retryable)

    def test_buoc_cong_doi_ky_thi_khong_gui(self):
        plan = dict(PLAN, config={"transition_id": -5, "requires_signature": True})
        w = _W(_q(), [{"current_state_id": "6"}], plan)
        with self.assertRaises(PE) as c:
            w.run()
        self.assertEqual(c.exception.code, "portal_step_requires_signature")
        self.assertEqual(w.sent, [])

    def test_khong_doc_duoc_cong_thi_cho(self):
        w = _W(_q(), [], PLAN)
        with self.assertRaises(PE) as c:
            w.run()
        self.assertTrue(c.exception.retryable)

    def test_gui_loi_mo_ho_van_danh_dau_da_gui(self):
        w = _W(_q(), [{"current_state_id": "4"}], PLAN,
               send_raises=PE("scts_bulk_outcome_unknown", "x", ambiguous=True))
        box = {}
        saved = {k: sys.modules.get(k) for k in w.mods}
        sys.modules.update(w.mods)
        try:
            with self.assertRaises(PE):
                w.g["_process_portal_approve"]("DSR-1", w.dsr, {"environment": "UAT"}, w.ad,
                                               "DOC", box)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        self.assertTrue(box.get("sent"), "nhanh except phai biet lenh da roi ERP")

    def test_chan_approve_khong_bao_gio_roi_ve_pool(self):
        fn = [n for n in ast.parse(_TASKS).body if isinstance(n, ast.FunctionDef)
              and n.name == "_process_portal_approve"][0]
        seg = ast.get_source_segment(_TASKS, fn)
        self.assertNotIn("approve_and_sign", seg)
        self.assertNotIn("plan_handover", seg)

    def test_worker_re_nhanh_truoc_duong_ky(self):
        fn = [n for n in ast.parse(_TASKS).body if isinstance(n, ast.FunctionDef)
              and n.name == "process_signing_request"][0]
        seg = ast.get_source_segment(_TASKS, fn)
        i = seg.index('if dsr.action == "Approve":')
        self.assertLess(i, seg.index("may_have_sent = sm.may_have_sent(dsr)"))
        self.assertIn("sent_attempted = bool(sent_box.get(\"sent\"))", seg)
        i = seg.index('if getattr(exc, "ambiguous", False):')
        self.assertIn("if trust:", seg[i:i + 200],
                      "ho so lay buoc tu cong: cong tu choi thi dung, khong pool")


# =============================================================================== payload
class Resp(object):
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


class TestPayloadKhongKy(unittest.TestCase):
    def _send(self, sig):
        _load("next_handler.py", "_warm")      # dam bao frappe gia lap ton tai khi import
        fr = sys.modules.get("frappe")
        if fr is None:
            fr = types.ModuleType("frappe")
            fr._ = lambda s: s
            fr.conf = {}
            fr.db = types.SimpleNamespace(get_value=lambda *a, **k: None,
                                          set_value=lambda *a, **k: None)
            u = types.ModuleType("frappe.utils")
            u.now_datetime = lambda: datetime.now()
            u.get_datetime = lambda v: v
            u.add_to_date = lambda d, **k: d
            pw = types.ModuleType("frappe.utils.password")
            pw.get_decrypted_password = lambda *a, **k: ""
            u.password = pw
            fr.utils = u
            sys.modules.update({"frappe": fr, "frappe.utils": u, "frappe.utils.password": pw})
        from ecentric_workspace.platform.esign.providers.scts import SctsAdapter
        from ecentric_workspace.platform.esign.providers.scts_client import SctsClient
        calls = []

        def transport(method, url, headers=None, json_body=None, **kw):
            calls.append((url, json_body))
            if "GetSignatures" in url:
                return Resp(200, [])
            return Resp(200, {"success": True, "data": "t"})
        a = SctsAdapter.__new__(SctsAdapter)
        a._client = SctsClient(base_url="https://x", transport=transport, timeout=5)
        a._with_auth = lambda fn: fn("TOKEN")
        a.transition_with_recipients("I", "U", ["P"], {"transition_id": -3,
                                                       "transition_name": "Phe duyet",
                                                       "process_action": "",
                                                       "sign_type": ""}, sig)
        return calls

    def test_khong_chu_ky_null_nhu_cong(self):
        calls = self._send(None)
        self.assertEqual([u for u, _ in calls if "GetSignatures" in u], [],
                         "khong tra cuu chu ky")
        body = [b for u, b in calls if u.endswith("/api/Workflow/transition")][0]
        self.assertIsNone(body["signatureInfo"])
        self.assertIsNone(body["signType"])
        self.assertIsNone(body["processAction"])
        self.assertEqual(body["transitionId"], "-3")
        self.assertEqual(body["toUsers"], ["P"])

    def test_co_chu_ky_van_nhu_cu(self):
        body = [b for u, b in self._send("SIG") if u.endswith("/api/Workflow/transition")][0]
        self.assertEqual(body["signatureInfo"]["id"], "SIG")


# =============================================================================== nguoi lap
_PS = _read("platform", "esign", "portal_steps.py")


class TestBuocNguoiLap(unittest.TestCase):
    def _ps(self, trust=1, levels=(1, 2, 3, 4), portal=(2, 3, 4), status="Pending", skipped=()):
        q = []
        ps, fk = _load("portal_steps.py", "_ps", {
            "enqueue": lambda *a, **k: q.append(k)})
        ps.frappe.db.get_value = lambda dt, n, f=None, **k: (
            _D(name="AR-1", reference_doctype="D", reference_name="CR-1", approval_type="CR",
               approval_status=status) if dt == "EC Approval Request"
            else trust)
        ps.frappe.get_all = lambda dt, filters=None, **k: (
            list(skipped) if (filters or {}).get("level_status") == "Skipped" else list(levels))
        ps.frappe.db.exists = lambda *a, **k: True
        ps.guard = types.SimpleNamespace(
            get_active_profile=lambda *a, **k: "P", request_final_level=lambda r: 4,
            level_portal_action=lambda dt, at, n, **k: "Approve" if n in portal else None)
        return ps, q

    def test_cap_cong_dau_tien_thi_xep_hang(self):
        ps, q = self._ps()
        self.assertEqual(ps.on_level_activated("AR-1", 2), "queued")
        self.assertEqual(len(q), 1)
        self.assertTrue(q[0]["enqueue_after_commit"])

    def test_cap_khac_thi_thoi(self):
        ps, q = self._ps()
        self.assertIsNone(ps.on_level_activated("AR-1", 1))
        self.assertIsNone(ps.on_level_activated("AR-1", 3))
        self.assertEqual(q, [])

    def test_khong_tin_cong_DNTT_thi_thoi(self):
        ps, q = self._ps(trust=0)
        self.assertIsNone(ps.on_level_activated("AR-1", 2))
        self.assertEqual(q, [])

    def test_chua_co_ho_so_tin_cong_thi_mot_truy_van(self):
        ps, q = self._ps()
        n = {"c": 0}
        def gv(*a, **k):
            n["c"] += 1
            return None
        ps.frappe.db.exists = lambda *a, **k: None
        ps.frappe.db.get_value = gv
        self.assertIsNone(ps.on_level_activated("AR-1", 2))
        self.assertEqual(n["c"], 0, "DNTT: chi mot lenh exists, khong doc phieu")

    def test_cap_skipped_khong_tinh(self):
        ps, q = self._ps()
        seen = {}
        ps.frappe.get_all = lambda dt, filters=None, **k: seen.update(filters) or [1, 2]
        ps.first_portal_level(_D(name="AR-1", reference_doctype="D", approval_type="CR",
                                 reference_name="CR-1"))
        self.assertEqual(seen.get("level_status"), ["!=", "Skipped"])

    def _pending(self, rows, level=2, skipped=()):
        ps, q = self._ps(skipped=skipped)
        ps._requester_step_rows = lambda n, pkg=None: [_D(x) for x in rows]
        ps.frappe.enqueue = lambda *a, **k: q.append(k)
        pk = types.ModuleType("ecentric_workspace.platform.esign.package")
        pk.signable_package_for_request = lambda n: "PKG"
        saved = sys.modules.get(pk.__name__)
        sys.modules[pk.__name__] = pk
        try:
            return ps.requester_step_pending(_D(name="AR-1", reference_doctype="D",
                                                reference_name="CR-1", approval_type="CR",
                                                current_level=level)), q
        finally:
            if saved is None:
                sys.modules.pop(pk.__name__, None)
            else:
                sys.modules[pk.__name__] = saved

    def test_buoc_nguoi_lap_chua_co_thi_xep_hang_va_bao_cho(self):
        msg, q = self._pending([])
        self.assertTrue(msg)
        self.assertEqual(len(q), 1)
        self.assertFalse(q[0]["enqueue_after_commit"],
                         "nguoi goi nem loi ngay sau -> rollback xoa hang doi sau-commit")
        self.assertTrue(q[0]["quiet"], "bam nhieu lan khong bao lap")

    def test_buoc_nguoi_lap_dung_han_thi_bao_loi_khong_xep(self):
        msg, q = self._pending([{"status": "Permanent Failure"}])
        self.assertIn("lỗi", msg)
        self.assertEqual(q, [])

    def test_cap_cong_bi_bo_thi_bao(self):
        msg, q = self._pending([], skipped=(3,))
        self.assertIn("bỏ qua", msg)
        self.assertEqual(q, [])

    def test_buoc_nguoi_lap_dang_chay_thi_bao_cho_khong_xep_them(self):
        msg, q = self._pending([{"status": "Verifying"}])
        self.assertTrue(msg)
        self.assertEqual(q, [])

    def test_buoc_nguoi_lap_xong_thi_khong_cho(self):
        msg, q = self._pending([{"status": "Approval Completed"}])
        self.assertIsNone(msg)

    def test_khong_phai_cap_cong_dau_thi_khong_cho(self):
        msg, q = self._pending([], level=3)
        self.assertIsNone(msg)

    def test_luoi_an_toan_khong_tao_lai_chan_da_chet(self):
        ps, q = self._ps()
        ps.frappe.get_all = lambda dt, filters=None, **k: (
            [_D(business_doctype="D", approval_type="CR")] if dt == ps.PROFILE else [1, 2, 3, 4])
        sqls = []
        ps.frappe.db.sql = lambda q, v=None, **k: sqls.append(q) or [
            _D(name="AR-1", reference_doctype="D", reference_name="CR-1", approval_type="CR",
               current_level=2)]
        ps.frappe.db.commit = lambda: None
        ps.frappe.db.rollback = lambda: None
        calls = []
        ps.start_requester_step = lambda n, quiet=False: calls.append((n, quiet)) or {}
        pk = types.ModuleType("ecentric_workspace.platform.esign.package")
        pk.signable_package_for_request = lambda n: "PKG"
        saved = sys.modules.get(pk.__name__)
        sys.modules[pk.__name__] = pk
        try:
            ps._requester_step_rows = lambda n, pkg=None: [_D(status="Permanent Failure")]
            ps.sweep_missing_requester_steps()
            self.assertEqual(calls, [], "chan da chet: de van hanh, khong tao lai moi gio")
            ps._requester_step_rows = lambda n, pkg=None: []
            ps.sweep_missing_requester_steps()
            self.assertEqual(calls, [("AR-1", True)], "chua co chan nao: tao, im lang")
            self.assertIn("NOT EXISTS", sqls[0], "loc phieu da co chan ngay trong SQL")
        finally:
            if saved is None:
                sys.modules.pop(pk.__name__, None)
            else:
                sys.modules[pk.__name__] = saved

    def test_luoi_an_toan_moi_gio(self):
        src = _read("platform", "esign", "tasks.py")
        fn = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)
              and n.name == "sweep_stale"][0]
        self.assertIn("_sweep_requester_steps()", ast.get_source_segment(src, fn))

    def test_khong_bao_gio_nem(self):
        ps, q = self._ps()
        ps.frappe.db.get_value = lambda *a, **k: 1 / 0
        self.assertIsNone(ps.on_level_activated("AR-1", 2))

    def test_engine_goi_o_cuoi_activate_level_va_boc_try(self):
        src = _read("approval_center", "shared", "workflow", "transitions.py")
        fns = {n.name: ast.get_source_segment(src, n) for n in ast.parse(src).body
               if isinstance(n, ast.FunctionDef)}
        act = fns["_activate_level"]
        self.assertTrue(act.rstrip().endswith("_esign_on_level_activated(req.name, level_no)"))
        self.assertIn("except Exception", fns["_esign_on_level_activated"])

    def test_start_khong_insert_trung_khoa(self):
        fn = [n for n in ast.parse(_PS).body if isinstance(n, ast.FunctionDef)
              and n.name == "start_requester_step"][0]
        seg = ast.get_source_segment(_PS, fn)
        self.assertLess(seg.index("existing.status in _LIVE_OR_DONE"), seg.index(".insert("))
        self.assertLess(seg.index("existing.status in _PRE_QUEUE"), seg.index(".insert("))
        self.assertIn("first_portal_level(req)", seg.split(".insert(")[0])
        self.assertIn("for_update=True", seg.split("existing =")[0], "khoa dong phieu truoc")
        self.assertIn("_requester_step_rows(req.name, pkg_name)", seg.split(".insert(")[0],
                      "idempotent theo phieu + goi, khong chi theo khoa")

    def test_hoan_tat_khong_goi_engine(self):
        self.assertNotIn("engine.approve", _PS)
        self.assertIn("portal_steps.complete_requester_step", _TASKS)


# =============================================================================== ho so
class TestLuuHoSo(unittest.TestCase):
    def _v(self, levels, trust=1, policy="Selected Approval Levels", rows=ROWS):
        src = _read("approval_center", "doctype", "ec_digital_signature_profile",
                    "ec_digital_signature_profile.py")
        cls = [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)][0]
        import textwrap
        g = {"_": lambda s: s, "frappe": types.SimpleNamespace(
            throw=lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m)))}
        for name in ("_validate_portal_approve_levels", "_validate_trusted_steps"):
            fn = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name][0]
            exec(compile(textwrap.dedent(ast.get_source_segment(src, fn)), "v", "exec"), g)
        me = _D(levels=[_D(x) for x in levels], trust_portal_transitions=trust,
                approver_signature_policy=policy, transitions=rows,
                requester_signature_required=0)
        me["_validate_trusted_steps"] = lambda: g["_validate_trusted_steps"](me)
        g["_validate_portal_approve_levels"](me)

    L2 = {"level_no": 2, "provider_action": "Approve", "requires_signature": 0}

    def _vt(self, levels, rows=ROWS, requester=0):
        src = _read("approval_center", "doctype", "ec_digital_signature_profile",
                    "ec_digital_signature_profile.py")
        cls = [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)][0]
        import textwrap
        g = {"_": lambda s: s, "frappe": types.SimpleNamespace(
            throw=lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m)))}
        for name in ("_validate_portal_approve_levels", "_validate_trusted_steps"):
            fn = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name][0]
            exec(compile(textwrap.dedent(ast.get_source_segment(src, fn)), "v", "exec"), g)
        me = _D(levels=[_D(x) for x in levels], trust_portal_transitions=1,
                approver_signature_policy="Selected Approval Levels", transitions=rows,
                requester_signature_required=requester)
        me["_validate_trusted_steps"] = lambda: g["_validate_trusted_steps"](me)
        g["_validate_portal_approve_levels"](me)

    def test_tin_cong_can_buoc_nguoi_lap(self):
        with self.assertRaises(_Throw):
            self._vt([self.L2], rows=[r for r in ROWS if r.stage != "requester"])

    def test_tin_cong_cap_ky_can_dong_sign(self):
        with self.assertRaises(_Throw):
            self._vt([{"level_no": 4, "requires_signature": 1}],
                     rows=[r for r in ROWS if r.stage != "level:4"])

    def test_tin_cong_cam_ky_nguoi_de_nghi(self):
        with self.assertRaises(_Throw):
            self._vt([self.L2], requester=1)

    def test_tin_cong_day_du_thi_qua(self):
        self._vt([self.L2, {"level_no": 3, "provider_action": "Approve", "requires_signature": 0},
                  {"level_no": 4, "requires_signature": 1}])

    def test_hop_le(self):
        self._v([self.L2, {"level_no": 4, "requires_signature": 1}])

    def test_khong_dong_approve_khong_kiem(self):
        self._v([{"level_no": 4, "requires_signature": 1}], trust=0, policy="All Approval Levels",
                rows=[])

    def test_approve_ma_tick_ky(self):
        with self.assertRaises(_Throw):
            self._v([dict(self.L2, requires_signature=1)])

    def test_approve_can_lay_buoc_tu_cong(self):
        with self.assertRaises(_Throw):
            self._v([self.L2], trust=0)

    def test_approve_can_chinh_sach_selected(self):
        with self.assertRaises(_Throw):
            self._v([self.L2], policy="All Approval Levels")

    def test_hai_dong_forward_cung_cap_bi_tu_choi(self):
        with self.assertRaises(_Throw):
            self._v([self.L2], rows=ROWS + [ROWS[1]])

    def test_tin_cong_can_chinh_sach_selected(self):
        with self.assertRaises(_Throw):
            self._v([], policy="Final Approval Level Only")

    def test_approve_can_dong_buoc(self):
        with self.assertRaises(_Throw):
            self._v([self.L2], rows=[r for r in ROWS if r.stage != "level:2"])


# =============================================================================== QC vong 1
class TestQC1(unittest.TestCase):
    def test_mot_buoc_cong_mot_nguoi(self):
        src = _read("platform", "esign", "service.py")
        g = {"frappe": None, "_": lambda s: s}
        exec(compile(_fns(src, ["_assert_single_portal_approval"]), "s", "exec"), g)

        def run(mode, minimum=0, people=2):
            g["frappe"] = types.SimpleNamespace(
                db=types.SimpleNamespace(
                    get_value=lambda *a, **k: _D(approval_mode=mode, minimum_approvals=minimum),
                    count=lambda *a, **k: people),
                throw=lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m)))
            g["_assert_single_portal_approval"](_D(name="AR-1", current_level=2))
        run("Any One")
        run("")
        run("Minimum Count", 1)
        run("All Required", people=1)
        for m, mn in (("All Required", 0), ("Minimum Count", 2), ("Each Group", 0)):
            with self.assertRaises(_Throw, msg=m):
                run(m, mn)

    def test_approve_and_sign_noi_day_du(self):
        src = _read("platform", "esign", "service.py")
        seg = _fns(src, ["approve_and_sign"])
        self.assertIn("_assert_single_portal_approval(req)", seg)
        self.assertIn("portal_steps.requester_step_pending(req)", seg)
        self.assertIn('(mapping.signature_id if action == "Sign"', seg)
        self.assertIn("level_portal_action", seg)

    def test_giao_dien_hop_thu_san_sang_deu_thay_cap_approve(self):
        for parts, fn in ((("platform", "esign", "service.py"), "signing_readiness"),
                          (("platform", "esign", "inbox.py"), "_derive_row"),
                          (("approval_center", "shared", "requests", "capabilities.py"),
                           "_requires_signature")):
            seg = _fns(_read(*parts), [fn])
            self.assertIn("level_portal_action", seg, fn)
            self.assertNotIn("level_requires_signature(", seg, fn)

    def test_binding_chan_approve_bo_phan_chu_ky(self):
        src = _read("platform", "esign", "binding.py")
        seg = _fns(src, ["_run_binding_checks"])
        self.assertIn("if live and adapter is not None and signs:", seg)
        self.assertIn("signs and str(mapping.signature_id)", seg)
        req = _fns(src, ["_run_requester_portal_step_checks"])
        self.assertIn("first_portal_level(req)", req)
        self.assertIn("actor_not_authoritative_requester", req)

    def _complete(self, actor_type, action):
        g = {"frappe": types.SimpleNamespace(db=types.SimpleNamespace(
            get_value=lambda *a, **k: action)), "DSR": "DSR",
             "svc": types.SimpleNamespace(verify_and_complete=lambda n: "approver")}
        ps = types.ModuleType("ecentric_workspace.platform.esign.portal_steps")
        ps.complete_requester_step = lambda n: "portal_step"
        rq = types.ModuleType("ecentric_workspace.platform.esign.requester")
        rq.reconcile_and_complete_requester = lambda n: "requester_sign"
        mods = {"ecentric_workspace.platform.esign.portal_steps": ps,
                "ecentric_workspace.platform.esign.requester": rq}
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            exec(compile(_fns(_TASKS, ["_complete_dsr"]), "c", "exec"), g)
            return g["_complete_dsr"]("DSR-1", {"actor_type": actor_type})
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_hoan_tat_re_nhanh_dung(self):
        self.assertEqual(self._complete("Requester", "Approve"), "portal_step")
        self.assertEqual(self._complete("Requester", "Sign"), "requester_sign")
        self.assertEqual(self._complete("Approval Level", "Approve"), "approver")

    def test_chan_ky_tin_cong_doi_canh_co_ky(self):
        g = {"frappe": None, "events": types.SimpleNamespace(emit=lambda *a, **k: None),
             "ProviderError": PE, "_profile_of": lambda d: "P"}
        nh = types.ModuleType("ecentric_workspace.platform.esign.next_handler")
        plan = {"mode": "transition", "config": {"transition_id": -4,
                                                 "requires_signature": False}}
        nh.plan_portal_step = lambda *a, **k: plan
        saved = sys.modules.get(nh.__name__)
        sys.modules[nh.__name__] = nh
        try:
            exec(compile(_fns(_TASKS, ["_trusted_plan"]), "t", "exec"), g)
            ad = types.SimpleNamespace(workflow_state_for_document=lambda *a: (
                {"current_state_id": "5"}, None))
            with self.assertRaises(PE) as c:
                g["_trusted_plan"]("D", _D(package="P", effective_scts_user_id="U"),
                                   {"environment": "UAT"}, ad, "DOC", "I")
            self.assertEqual(c.exception.code, "portal_step_not_signed")
            plan["config"]["requires_signature"] = True
            self.assertIs(g["_trusted_plan"]("D", _D(package="P", effective_scts_user_id="U"),
                                             {"environment": "UAT"}, ad, "DOC", "I"), plan)
        finally:
            if saved is None:
                sys.modules.pop(nh.__name__, None)
            else:
                sys.modules[nh.__name__] = saved

    def _reconcile(self, open_ids, reason="KTTH bam tren cong roi", doc_status="processing",
                   cur="5", before_to=None, observed=None, prev_target=None):
        src = _read("platform", "esign", "service.py")
        log = []
        g = {"frappe": types.SimpleNamespace(
            db=types.SimpleNamespace(get_value=lambda *a, **k: "Approval Completed"
                                     if a[0] == "DSR" else "P"),
            get_all=lambda *a, **k: ([_D(provider_state_before="3|%s" % prev_target)]
                                     if prev_target else []),
            session=types.SimpleNamespace(user="sm@x")),
             "DSR": "DSR", "events": types.SimpleNamespace(emit=lambda *a, **k: log.append(a)),
             "mark_verified": lambda n, r: log.append(("verified", r)),
             "safe_error": lambda e: str(e)}
        nh = types.ModuleType("ecentric_workspace.platform.esign.next_handler")
        nh._configured_step = lambda p, a, s: {"transition_id": -3}
        nh.STEP_ACTION = {"Approve": "Forward"}
        nh.portal_stage_for = lambda d: "level:2"
        pv = types.ModuleType("ecentric_workspace.platform.esign.providers")
        pv.get_adapter = lambda s: types.SimpleNamespace(
            poll_status=lambda d: types.SimpleNamespace(status=doc_status),
            workflow_state_for_document=lambda d, u: (
                {"current_state_id": cur,
                 "transitions": [{"transition_id": i} for i in open_ids]}, None))
        pb = types.ModuleType("ecentric_workspace.platform.esign.providers.base")
        pb.ProviderError = PE
        tk = types.ModuleType("ecentric_workspace.platform.esign.tasks")
        tk._complete_dsr = lambda n, d: log.append(("complete",))
        exec(compile(_fns(_TASKS, ["_portal_moved", "_same_shape"]), "pm", "exec"),
             tk.__dict__)
        mods = {nh.__name__: nh, pv.__name__: pv, pb.__name__: pb, tk.__name__: tk}
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            exec(compile(_fns(src, ["MIN_PORTAL_RECONCILE_REASON", "_reconcile_portal_step",
                                    "_previous_portal_target"]),
                         "r", "exec"), g)
            out = g["_reconcile_portal_step"](
                _D(name="DSR-1", package="PKG", effective_scts_user_id="U",
                   provider_state_before=before_to), {}, "DOC", reason, observed)
            return out, log
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_doi_soat_chan_da_gui_cong_o_dung_buoc_dich(self):
        out, log = self._reconcile([-4], before_to="4|5", cur="5")
        self.assertTrue(out["ok"])
        self.assertIn(("complete",), log)

    def test_doi_soat_bi_tra_lai_tren_cong_thi_KHONG(self):
        """QC vong 2: KTT tu choi tren cong, buoc ve 3, khong canh nao mo -> truoc day 'ok'."""
        out, log = self._reconcile([], before_to="4|5", cur="3")
        self.assertFalse(out["ok"])
        self.assertNotIn(("complete",), log)

    def test_doi_soat_chan_chua_gui_can_ma_buoc_nguoi_truc_go(self):
        out, log = self._reconcile([-4], cur="5")
        self.assertFalse(out["ok"])
        self.assertIn("need_observed_state", out["reason"])
        out, log = self._reconcile([], cur="4", observed="4", prev_target="4")
        self.assertEqual(out["reason"], "portal_still_at_this_step:4",
                         "cong van o buoc ma canh nay mo -> chua ai duyet")
        out, log = self._reconcile([-4], cur="5", observed="4")
        self.assertFalse(out["ok"], "ma go khong khop buoc cong dang dung")
        out, log = self._reconcile([-4], cur="5", observed="5")
        self.assertTrue(out["ok"])

    def test_doi_soat_chan_da_gui_nguoi_sau_bam_thang_tren_cong(self):
        """Cong da qua buoc dich (5 -> 6) vi KTT bam thang tren cong: tu dong khong ket luan,
        nguoi truc go ma buoc 6 thi xac nhan."""
        out, log = self._reconcile([-5], before_to="4|5", cur="6")
        self.assertFalse(out["ok"])
        out, log = self._reconcile([-5], before_to="4|5", cur="6", observed="6")
        self.assertTrue(out["ok"])
        out, log = self._reconcile([], before_to="4|5", cur="4", observed="4")
        self.assertFalse(out["ok"], "van o buoc truoc = chua duyet")

    def test_api_truyen_ma_buoc(self):
        seg = _fns(_read("platform", "esign", "api.py"), ["reconcile_signature_request"])
        self.assertIn("observed_state_id=None", seg)
        self.assertIn("observed_state_id=(", seg)

    def test_doi_soat_chan_chua_gui_canh_con_mo_thi_khong(self):
        out, log = self._reconcile([-3], cur="4", observed="4")
        self.assertEqual(out["reason"], "portal_still_waiting_for_this_step")
        self.assertNotIn(("complete",), log)

    def test_doi_soat_can_ly_do_du_dai(self):
        out, log = self._reconcile([-4], before_to="4|5", reason="ok")
        self.assertFalse(out["ok"])

    def test_doi_soat_tai_lieu_huy_thi_khong(self):
        out, log = self._reconcile([-4], before_to="4|5", doc_status="cancelled")
        self.assertFalse(out["ok"])

    def test_gui_lai_khong_cho_chan_approve(self):
        seg = _fns(_read("platform", "esign", "api.py"), ["authorize_resend"])
        self.assertIn('if dsr.action == "Approve":', seg)

    def test_chan_khong_ky_khong_tinh_la_chu_ky(self):
        src = _read("platform", "esign", "service.py")
        for fn in ("_completed_legs_of_same_signer", "_audit_drift",
                   "sync_signatures_from_provider"):
            self.assertIn('"action": "Sign"', _fns(src, [fn]), fn)

    def test_mot_lan_resolve_ho_so(self):
        n = {"profile": 0}
        g = _guard(approve_levels=(2,))
        def prof(*a, **k):
            n["profile"] += 1
            return "P"
        g["get_active_profile"] = prof
        exec(compile(_fns(_GUARD, ["_UNSET", "level_requires_signature"]), "l", "exec"), g)
        g["_approver_signature_policy"] = lambda p: "Selected Approval Levels"
        g["frappe"].db.exists = lambda dt, f: (dt.endswith("Level") and f.get("level_no") == 2
                                               and f.get("provider_action") == "Approve")
        self.assertEqual(g["level_portal_action"]("D", "CR", 2), "Approve")
        self.assertEqual(n["profile"], 1)

    def test_doi_soat_re_nhanh_approve(self):
        seg = _fns(_read("platform", "esign", "service.py"), ["reconcile_manual_review"])
        self.assertIn('if dsr.action == "Approve":', seg)


if __name__ == "__main__":
    unittest.main()
