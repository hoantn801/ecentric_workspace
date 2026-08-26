# Copyright (c) 2026, eCentric and contributors
"""Chỉ định NGƯỜI XỬ LÝ KẾ TIẾP thay vì để nhà cung cấp phát cho cả pool.

Sự việc 27/08/2026: eContract thông báo cho toàn bộ pool 7 người vì lệnh gọi của ERP không
truyền `toUsers`. Một đồng nghiệp ngoài chuỗi duyệt đã ký EC-PAYR-2026-00026 sau 40 giây.
Portal của chính nhà cung cấp luôn truyền `toUsers` và còn bắt buộc phải chọn.

Bất biến khoá ở đây:
  * người kế tiếp lấy TỪ CHUỖI DUYỆT ERP, không suy từ vai trò;
  * chỉ chấp nhận danh tính có mapping ĐÃ XÁC THỰC — không bao giờ giao chứng từ cho một
    danh tính chưa kiểm chứng;
  * cấu hình nửa vời bị coi như KHÔNG có, để không gửi payload nhà cung cấp không hiểu;
  * khi không thể nêu tên người kế tiếp thì lùi về đường cũ nhưng phải NÓI RÕ LÝ DO.

  python -m unittest ecentric_workspace.approval_center.tests.standalone.test_next_handler
"""
import sys
import types
import unittest


class _D(dict):
    __getattr__ = dict.get


STORE = {}
MAPPINGS = {}


def _install_stub():
    fr = types.ModuleType("frappe")

    def get_all(doctype, filters=None, fields=None, **kw):
        out = []
        for rec in STORE.get(doctype, []):
            if all(rec.get(k) == v for k, v in (filters or {}).items()):
                out.append(_D(rec))
        return out

    def get_value(doctype, name, fieldname=None, **kw):
        for rec in STORE.get(doctype, []):
            if rec.get("name") == name:
                return rec.get(fieldname)
        return None

    fr.get_all = get_all
    fr.db = types.SimpleNamespace(get_value=get_value)
    fr._dict = _D
    sys.modules["frappe"] = fr

    perms = types.ModuleType("perms")
    perms.verified_mapping = lambda user, env: MAPPINGS.get((user, env))
    sys.modules["ecentric_workspace.platform.esign.perms"] = perms
    pkg = types.ModuleType("ecentric_workspace.platform.esign")
    pkg.perms = perms
    sys.modules.setdefault("ecentric_workspace.platform.esign", pkg)
    sys.modules["ecentric_workspace.platform.esign"].perms = perms


class Base(unittest.TestCase):
    def setUp(self):
        STORE.clear()
        MAPPINGS.clear()
        _install_stub()
        for m in [m for m in list(sys.modules) if m.endswith("next_handler")]:
            del sys.modules[m]
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "next_handler", "ecentric_workspace/platform/esign/next_handler.py")
        self.nh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.nh)

    def _transition(self, **kw):
        row = {"parent": "PROF", "action": "Sign", "stage": "requester", "transition_id": -2,
               "transition_name": "Trình ký", "process_action": "WfFunctionRunSignedOther",
               "sign_type": "ky-tham-gia", "terminal": 0}
        row.update(kw)
        STORE.setdefault("EC Digital Signature Profile Transition", []).append(row)

    def _approver(self, level_no, user, status="Pending"):
        STORE.setdefault("EC Approval Request Approver", []).append(
            {"approval_request": "AR-1", "level_no": level_no, "approver": user,
             "status": status})

    def _map(self, user, pid, env="UAT"):
        MAPPINGS[(user, env)] = {"scts_user_id": pid}


class TestTransitionConfig(Base):
    def test_exact_stage_wins_over_default(self):
        self._transition(stage="", transition_id=-9, process_action="DEFAULT")
        self._transition(stage="requester", transition_id=-2,
                         process_action="WfFunctionRunSignedOther")
        cfg = self.nh.resolve_transition_config("PROF", "Sign", stage="requester")
        self.assertEqual(cfg["transition_id"], -2)
        self.assertEqual(cfg["process_action"], "WfFunctionRunSignedOther")

    def test_default_row_used_when_no_exact_stage(self):
        self._transition(stage="", transition_id=-9, process_action="DEFAULT")
        cfg = self.nh.resolve_transition_config("PROF", "Sign", stage="approval")
        self.assertEqual(cfg["transition_id"], -9)

    def test_missing_config_is_none(self):
        self.assertIsNone(self.nh.resolve_transition_config("PROF", "Sign", stage="requester"))

    def test_half_configured_treated_as_absent(self):
        """Thiếu process_action thì payload vô nghĩa — thà coi như chưa cấu hình."""
        self._transition(process_action=None)
        self.assertIsNone(self.nh.resolve_transition_config("PROF", "Sign", stage="requester"))

    def test_no_profile_is_none(self):
        self.assertIsNone(self.nh.resolve_transition_config(None, "Sign"))


class TestNextLevelApprovers(Base):
    def test_requester_leg_points_at_level_one(self):
        self._approver(1, "hoan.tran@ecentric.vn")
        self._approver(2, "lien.vu@ecentric.vn")
        self.assertEqual(self.nh.next_level_approvers("AR-1", 0), ["hoan.tran@ecentric.vn"])

    def test_level_one_points_at_level_two(self):
        self._approver(1, "hoan.tran@ecentric.vn")
        self._approver(2, "lien.vu@ecentric.vn")
        self.assertEqual(self.nh.next_level_approvers("AR-1", 1), ["lien.vu@ecentric.vn"])

    def test_only_pending_rows_count(self):
        self._approver(1, "da.duyet@ecentric.vn", status="Approved")
        self._approver(1, "cho@ecentric.vn")
        self.assertEqual(self.nh.next_level_approvers("AR-1", 0), ["cho@ecentric.vn"])

    def test_any_one_level_returns_every_candidate_deduped(self):
        self._approver(1, "a@ec.vn")
        self._approver(1, "b@ec.vn")
        self._approver(1, "a@ec.vn")
        self.assertEqual(self.nh.next_level_approvers("AR-1", 0), ["a@ec.vn", "b@ec.vn"])

    def test_last_level_has_nobody_after(self):
        self._approver(4, "ceo@ec.vn")
        self.assertEqual(self.nh.next_level_approvers("AR-1", 4), [])


class TestProviderIds(Base):
    def test_only_verified_mappings_are_used(self):
        self._map("co@ec.vn", "pid-1")
        ids, unmapped = self.nh.provider_ids_for(["co@ec.vn", "khong@ec.vn"], "UAT")
        self.assertEqual(ids, ["pid-1"])
        self.assertEqual(unmapped, ["khong@ec.vn"])

    def test_environment_is_respected(self):
        self._map("u@ec.vn", "pid-uat", env="UAT")
        ids, unmapped = self.nh.provider_ids_for(["u@ec.vn"], "Production")
        self.assertEqual(ids, [])
        self.assertEqual(unmapped, ["u@ec.vn"])


class TestPlanHandover(Base):
    def _dsr(self, **kw):
        d = {"action": "Sign", "approval_request": "AR-1", "actor_type": "Requester",
             "request_level_no": 0}
        d.update(kw)
        return _D(d)

    def test_the_governed_path_when_everything_is_known(self):
        self._transition()
        self._approver(1, "hoan.tran@ecentric.vn")
        self._map("hoan.tran@ecentric.vn", "73f72e15")
        plan = self.nh.plan_handover(self._dsr(), "PROF", "UAT", stage="requester")
        self.assertEqual(plan["mode"], "transition")
        self.assertEqual(plan["to_users"], ["73f72e15"])
        self.assertEqual(plan["config"]["transition_id"], -2)

    def test_falls_back_when_transition_unconfigured_and_says_so(self):
        self._approver(1, "hoan.tran@ecentric.vn")
        self._map("hoan.tran@ecentric.vn", "73f72e15")
        plan = self.nh.plan_handover(self._dsr(), "PROF", "UAT", stage="approval")
        self.assertEqual(plan["mode"], "pool")
        self.assertIn("no_transition_config", plan["reason"])
        self.assertIn("approval", plan["reason"])

    def test_falls_back_when_next_handler_has_no_verified_mapping(self):
        self._transition()
        self._approver(1, "chua.map@ecentric.vn")
        plan = self.nh.plan_handover(self._dsr(), "PROF", "UAT", stage="requester")
        self.assertEqual(plan["mode"], "pool")
        self.assertIn("next_handler_unmapped", plan["reason"])
        self.assertIn("chua.map@ecentric.vn", plan["reason"])

    def test_falls_back_when_chain_has_no_next_level(self):
        self._transition()
        plan = self.nh.plan_handover(self._dsr(), "PROF", "UAT", stage="requester")
        self.assertEqual(plan["mode"], "pool")
        self.assertEqual(plan["reason"], "no_next_level_approver")

    def test_terminal_step_hands_over_to_nobody_on_purpose(self):
        """Bước cuối: không còn ai phía sau, và cấu hình nói rõ điều đó."""
        self._transition(stage="approval", terminal=1, transition_id=-7,
                         process_action="WfFunctionDone")
        plan = self.nh.plan_handover(self._dsr(actor_type="Approval Level",
                                               request_level_no=4), "PROF", "UAT",
                                     stage="approval")
        self.assertEqual(plan["mode"], "transition")
        self.assertEqual(plan["to_users"], [])

    def test_multiple_candidates_all_named(self):
        self._transition()
        self._approver(1, "a@ec.vn")
        self._approver(1, "b@ec.vn")
        self._map("a@ec.vn", "pid-a")
        self._map("b@ec.vn", "pid-b")
        plan = self.nh.plan_handover(self._dsr(), "PROF", "UAT", stage="requester")
        self.assertEqual(sorted(plan["to_users"]), ["pid-a", "pid-b"])

    def test_partially_mapped_still_targets_the_mapped_ones_and_reports_the_rest(self):
        self._transition()
        self._approver(1, "co@ec.vn")
        self._approver(1, "khong@ec.vn")
        self._map("co@ec.vn", "pid-co")
        plan = self.nh.plan_handover(self._dsr(), "PROF", "UAT", stage="requester")
        self.assertEqual(plan["mode"], "transition")
        self.assertEqual(plan["to_users"], ["pid-co"])
        self.assertEqual(plan["unmapped"], ["khong@ec.vn"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
