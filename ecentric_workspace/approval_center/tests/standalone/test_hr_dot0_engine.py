# Copyright (c) 2026, eCentric and contributors
"""Dot 0 HR (23/11/2026): phieu rieng tu, nguoi theo doi, chan tu duyet, muc Gap, chuyen nguoi
duyet khi nghi viec. Chay CODE THAT (transitions / privacy / permissions / scope / approver_handover)
tren frappe gia (_hr_dot0_world).
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hr_dot0_engine.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hr_dot0_world as W  # noqa: E402

WORLD, FR = W.install()

from ecentric_workspace.approval_center.shared.workflow import transitions as tr  # noqa: E402
from ecentric_workspace.approval_center.shared.workflow import privacy  # noqa: E402
from ecentric_workspace.approval_center.shared.workflow import permissions as perm  # noqa: E402
from ecentric_workspace.approval_center.shared.workflow import approver_handover as ho  # noqa: E402
from ecentric_workspace.approval_center.reporting import scope  # noqa: E402

AR, AP, RL, ACT = ("EC Approval Request", "EC Approval Request Approver",
                   "EC Approval Request Level", "EC Approval Action")
BIZ = "EC Adhoc Approval Request"


def _reset():
    WORLD.reset()
    FR.local = type(FR.local)(message_log=[])
    FR.session.user = "Administrator"
    tr._sla = lambda: tr._SLA_OFF
    tr._luong_co_ky_so = lambda req, ctx: False


class _Lvl(object):
    def __init__(self, level_no=1, name="L", participants=()):
        self.level_no, self.level_name, self.participants = level_no, name, list(participants)


def _p(**kw):
    kw.setdefault("participant_purpose", "Approver")
    kw.setdefault("sort_order", 0)
    return W.D(kw)


class PrivateScope(unittest.TestCase):
    def setUp(self):
        _reset()
        WORLD.metas["EC Approval Type"] = W.Meta(["private"])
        WORLD.add("EC Approval Type", {"name": "ADHOC_APPROVAL", "private": 1})
        WORLD.add("EC Approval Type", {"name": "LEAVE", "private": 0})

    def test_private_types_union_code_and_config(self):
        types_ = privacy.private_types()
        self.assertIn("ADHOC_APPROVAL", types_)
        self.assertNotIn("LEAVE", types_)

    def test_scope_sql_excludes_private_unless_participant(self):
        sql, params = privacy.scope_sql("u@x")
        self.assertIn("NOT IN", sql)
        self.assertIn("ADHOC_APPROVAL", params.values())
        for need in ("r.requested_by = %(priv_user)s", "Request Approver", "Request Watcher"):
            self.assertIn(need, sql)

    def test_admin_scope_also_filtered(self):
        sql, params = scope.scope_predicate({"mode": "admin", "user": "sm@x", "departments": [],
                                             "fulfil_types": []})
        self.assertTrue(sql.startswith("(1=1) AND"), sql)
        self.assertEqual(params["priv_user"], "sm@x")

    def test_department_scope_filtered(self):
        sql, _p2 = scope.scope_predicate({"mode": "department", "user": "head@x",
                                          "departments": ["D1"], "fulfil_types": []})
        self.assertIn("requester_department IN", sql)
        self.assertIn("NOT IN", sql)

    def test_no_private_types_keeps_sql_identical(self):
        WORLD.store["EC Approval Type"]["ADHOC_APPROVAL"]["private"] = 0
        FR.local._ec_private_types = None
        orig = privacy._code_private_types
        privacy._code_private_types = lambda: set()
        try:
            self.assertEqual(scope.scope_predicate({"mode": "admin", "user": "a"}), ("1=1", {}))
        finally:
            privacy._code_private_types = orig

    def test_privacy_failure_is_fail_closed(self):
        orig = privacy.scope_sql
        privacy.scope_sql = lambda *a: 1 / 0
        try:
            sql, _x = scope.scope_predicate({"mode": "admin", "user": "a"})
        finally:
            privacy.scope_sql = orig
        self.assertIn("0=1", sql)


class CanView(unittest.TestCase):
    def setUp(self):
        _reset()
        WORLD.user("watch@x")
        WORLD.user("grant@x")
        WORLD.user("other@x")
        WORLD.add(AR, {"name": "APR-1", "approval_type": "ADHOC_APPROVAL", "requested_by": "req@x"})

    def test_watcher_and_grant_can_view_stranger_cannot(self):
        WORLD.add(privacy.WATCHER_DT, {"approval_request": "APR-1", "watcher": "watch@x"})
        WORLD.add(privacy.GRANT_DT, {"target_request": "APR-1", "user": "grant@x", "active": 1})
        self.assertTrue(perm.can_view_request("APR-1", "watch@x"))
        self.assertTrue(perm.can_view_request("APR-1", "grant@x"))
        self.assertFalse(perm.can_view_request("APR-1", "other@x"))

    def test_revoked_grant_denies(self):
        WORLD.add(privacy.GRANT_DT, {"target_request": "APR-1", "user": "grant@x", "active": 0})
        self.assertFalse(perm.can_view_request("APR-1", "grant@x"))

    def test_watcher_is_never_actionable(self):
        WORLD.add(privacy.WATCHER_DT, {"approval_request": "APR-1", "watcher": "watch@x"})
        self.assertFalse(perm.is_actionable("APR-1", 1, "watch@x", "Pending"))


class AccessLog(unittest.TestCase):
    def setUp(self):
        _reset()
        WORLD.metas["EC Approval Type"] = W.Meta(["private"])
        WORLD.add("EC Approval Type", {"name": "ADHOC_APPROVAL", "private": 1})
        WORLD.user("sm@x", ["System Manager"])
        WORLD.add(AR, {"name": "APR-1", "approval_type": "ADHOC_APPROVAL", "requested_by": "req@x"})

    def test_sm_outside_flow_logged_once_per_window(self):
        privacy.note_access("sm@x", "APR-1", "ADHOC_APPROVAL", "req@x")
        privacy.note_access("sm@x", "APR-1", "ADHOC_APPROVAL", "req@x")
        logs = WORLD.rows(privacy.ACCESS_DT)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["via"], "System Manager")

    def test_requester_not_logged(self):
        privacy.note_access("req@x", "APR-1", "ADHOC_APPROVAL", "req@x")
        self.assertEqual(WORLD.rows(privacy.ACCESS_DT), [])

    def test_non_private_not_logged(self):
        privacy.note_access("sm@x", "APR-1", "LEAVE", "req@x")
        self.assertEqual(WORLD.rows(privacy.ACCESS_DT), [])


class SelfBlock(unittest.TestCase):
    def setUp(self):
        _reset()
        for u in ("req@x", "a@x", "fb@x", "mgr@x"):
            WORLD.user(u)
        self.req = W.D({"name": "APR-1", "reference_doctype": BIZ, "reference_name": "B1",
                        "approval_type": "X"})

    def test_drop_requester_keep_others(self):
        out, note = tr._apply_self_block(self.req, _Lvl(), [("req@x", "Role: R"), ("a@x", "Role: R")],
                                         {"req@x"}, "req@x", has_later=True)
        self.assertEqual([u for u, _l in out], ["a@x"])
        self.assertEqual(note[0], "dropped")

    def test_fallback_when_level_empty(self):
        lvl = _Lvl(participants=[_p(source_type="Role", role="R", fallback_user="fb@x")])
        out, note = tr._apply_self_block(self.req, lvl, [("req@x", "Role: R")], {"req@x"},
                                         "req@x", has_later=False)
        self.assertEqual(out[0][0], "fb@x")
        self.assertEqual(note[0], "fallback")

    def test_skip_level_when_later_exists(self):
        out, note = tr._apply_self_block(self.req, _Lvl(), [("req@x", "Role: R")], {"req@x"},
                                         "req@x", has_later=True)
        self.assertEqual(out, [])
        self.assertEqual(note[0], "skip")

    def test_last_level_goes_to_manager(self):
        tr._manager_user_of_employee = lambda ident: "mgr@x"
        out, note = tr._apply_self_block(self.req, _Lvl(), [("req@x", "Role: R")], {"req@x"},
                                         "req@x", has_later=False)
        self.assertEqual(out[0][0], "mgr@x")
        self.assertEqual(note[0], "manager")

    def test_last_level_no_one_blocks_submit(self):
        tr._manager_user_of_employee = lambda ident: None
        with self.assertRaises(W.Err):
            tr._apply_self_block(self.req, _Lvl(), [("req@x", "Role: R")], {"req@x"}, "req@x",
                                 has_later=False)

    def test_esign_flow_keeps_original(self):
        tr._luong_co_ky_so = lambda req, ctx: True
        out, note = tr._apply_self_block(self.req, _Lvl(), [("req@x", "Role: R")], {"req@x"},
                                         "req@x", has_later=True)
        self.assertEqual(out, [("req@x", "Role: R")])
        self.assertEqual(note[0], "kept_esign")

    def test_subject_user_resolution(self):
        WORLD.metas[BIZ] = W.Meta(["employee_email"])
        WORLD.add(BIZ, {"name": "B1", "employee_email": "a@x"})
        orig = tr._subject_fields
        tr._subject_fields = lambda dt: ("employee_email",)
        try:
            self.assertEqual(tr._self_exclusion(self.req, "req@x"), {"req@x", "a@x"})
        finally:
            tr._subject_fields = orig

    def test_each_group_drops_subject(self):
        notes = []
        lvl = _Lvl(participants=[_p(source_type="User", user="req@x", group_label="HR",
                                    fallback_user="fb@x"),
                                 _p(source_type="User", user="a@x", group_label="LM", sort_order=1)])
        groups = tr._resolve_groups(lvl, "x@x", {}, excluded={"req@x"}, notes=notes)
        self.assertEqual(dict((g, [u for u, _l in m]) for g, m in groups),
                         {"HR": ["fb@x"], "LM": ["a@x"]})
        self.assertEqual(notes[0][1][0], "group_fallback")


class Severity(unittest.TestCase):
    def setUp(self):
        _reset()
        WORLD.metas[BIZ] = W.Meta(["urgency"])
        WORLD.add(BIZ, {"name": "B1", "urgency": "Gấp"})
        WORLD.add(BIZ, {"name": "B2", "urgency": "Bình thường"})

    def test_urgent_only_when_gap(self):
        self.assertEqual(tr._sev_kw(BIZ, "B1"), {"severity": "urgent"})
        self.assertEqual(tr._sev_kw(BIZ, "B2"), {})
        self.assertEqual(tr._sev_kw("EC Leave Request", "L1"), {})

    def test_notify_passes_severity_only_when_given(self):
        tr.notify(["a@x"], "s", BIZ, "B1", severity="urgent")
        tr.notify(["b@x"], "s", BIZ, "B2")
        self.assertEqual(WORLD.notified[0][2], "urgent")
        self.assertIsNone(WORLD.notified[1][2])


class Watchers(unittest.TestCase):
    def setUp(self):
        _reset()
        for u in ("ceo@x", "app@x", "req@x"):
            WORLD.user(u)
        WORLD.user("off@x", enabled=0)
        WORLD.add(AR, {"name": "APR-1", "requested_by": "req@x", "reference_doctype": BIZ,
                       "reference_name": "B1", "approval_type": "X"})
        WORLD.add(AP, {"approval_request": "APR-1", "approver": "app@x", "level_no": 1})

    def test_add_watchers_filters(self):
        added = tr.add_watchers("APR-1", ["ceo@x", "app@x", "req@x", "off@x", "ceo@x"],
                                actor="Administrator")
        self.assertEqual(added, ["ceo@x"])
        self.assertEqual(len(WORLD.rows(privacy.WATCHER_DT)), 1)
        self.assertIn((BIZ, "B1", "ceo@x"), WORLD.shares)

    def test_snapshot_watchers_from_notify_rows(self):
        proc = W.D({"participants": [_p(participant_purpose="Notify", source_type="User",
                                         user="ceo@x")]})
        req = W.D(WORLD.store[AR]["APR-1"])
        tr._snapshot_watchers(req, proc, [], "req@x")
        self.assertEqual(privacy.watchers_of("APR-1"), ["ceo@x"])

    def test_notify_watchers_info(self):
        tr.add_watchers("APR-1", ["ceo@x"])
        tr._notify_watchers(W.D(WORLD.store[AR]["APR-1"]), "done")
        self.assertEqual(WORLD.notified[-1], ("ceo@x", "done", "info"))


class Handover(unittest.TestCase):
    def setUp(self):
        _reset()
        for u in ("req@x", "boss@x", "r2@x"):
            WORLD.user(u, ["EC CnB"] if u == "r2@x" else ())
        WORLD.user("gone@x", ["EC CnB"], enabled=0)
        WORLD.add(AR, {"name": "APR-1", "requested_by": "req@x", "reference_doctype": BIZ,
                       "reference_name": "B1", "approval_type": "X", "approval_status": "Pending",
                       "current_level": 1})
        WORLD.add(RL, {"name": "RL-1", "approval_request": "APR-1", "level_no": 1,
                       "level_name": "LM", "approval_mode": "Any One", "level_status": "In Progress"})
        WORLD.add(BIZ, {"name": "B1"})

    def _row(self, source, approver="gone@x"):
        return WORLD.add(AP, {"approval_request": "APR-1", "request_level": "RL-1", "level_no": 1,
                              "approver": approver, "source": source, "status": "Pending"})

    def test_role_row_goes_to_other_role_holder(self):
        r = self._row("Role: EC CnB")
        self.assertEqual(ho.handle_row(r["name"], "gone@x", "khoa"), "reassigned")
        self.assertTrue(WORLD.store[AP][r["name"]]["comment"].startswith(tr.REASSIGN_MARK))
        new = [x for x in WORLD.rows(AP, approver="r2@x")]
        self.assertEqual(new[0]["status"], "Pending")
        self.assertTrue(any(a.get("action") == "Reassigned" for a in WORLD.rows(ACT)))

    def test_manager_row_goes_to_manager_of_old(self):
        r = self._row("Reference Employee Manager")
        tr._manager_user_of_employee = lambda ident: "boss@x" if ident == "gone@x" else None
        self.assertEqual(ho.handle_row(r["name"], "gone@x", "khoa"), "reassigned")
        self.assertTrue(WORLD.rows(AP, approver="boss@x"))

    def test_never_reassign_to_requester(self):
        r = self._row("Reference Employee Manager")
        tr._manager_user_of_employee = lambda ident: "req@x"
        self.assertEqual(ho.handle_row(r["name"], "gone@x", "khoa"), "manual")
        self.assertEqual(WORLD.store[AP][r["name"]]["status"], "Pending")   # khong de cap rong

    def test_other_pending_covers_any_one(self):
        r = self._row("Role: EC CnB")
        self._row("Role: EC CnB", approver="r2@x")
        self.assertEqual(ho.handle_row(r["name"], "gone@x", "khoa"), "skipped")
        self.assertEqual(len(WORLD.rows(AP, approver="r2@x")), 1)

    def test_resubmit_does_not_revive_reassigned_row(self):
        r = self._row("Role: EC CnB")
        ho.handle_row(r["name"], "gone@x", "khoa")
        self.assertTrue(tr._is_reassigned_row(r["name"]))

    def test_user_hook_only_on_disable(self):
        calls = []
        orig = ho.handle_inactive_user
        ho.handle_inactive_user = lambda u, why: calls.append(u)
        try:
            doc = W.Doc(WORLD, "User", W.D({"name": "a@x", "enabled": 0,
                                            "_before": W.D({"enabled": 1})}))
            ho.on_user_update(doc)
            doc2 = W.Doc(WORLD, "User", W.D({"name": "b@x", "enabled": 1,
                                             "_before": W.D({"enabled": 1})}))
            ho.on_user_update(doc2)
        finally:
            ho.handle_inactive_user = orig
        self.assertEqual(calls, ["a@x"])

    def test_sm_endpoint_requires_role_and_reason(self):
        self._row("Reference User Field")
        FR.session.user = "boss@x"
        with self.assertRaises(W.PermErr):
            ho.reassign_approver("APR-1", "gone@x", "r2@x", "x")
        WORLD.roles["boss@x"] = ["System Manager"]
        with self.assertRaises(W.Err):
            ho.reassign_approver("APR-1", "gone@x", "r2@x", "")


if __name__ == "__main__":
    unittest.main()
