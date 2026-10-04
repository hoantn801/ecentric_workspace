# Copyright (c) 2026, eCentric and contributors
"""Luong thuan cua AI Video hang loat (domain/flow.py) - khong can frappe."""
import unittest

from ecentric_workspace.ai_tools.features.ai_video.domain import flow

PROJ = {"brand": "Friso", "host_key": "H_P1", "gate_motion": 1, "gate_hold_a": 1, "night_mode": 0,
        "mix_mode": "mix", "mix_variants": 5, "audio_seconds": 72}


def item(stage, tasks=None, **kw):
    d = {"sku": "F1", "stage": stage, "stage_state": "running", "batch": "lo1",
         "state": {"job": "J1", "tasks": tasks or {}}}
    d.update(kw)
    return d


def W(tasks=None, jobs=None, anchor=False):
    return {"tasks": tasks or {}, "jobs": jobs or {}, "anchor_ready": anchor}


class TestFlow(unittest.TestCase):
    def test_job_id_is_stable_and_safe(self):
        self.assertEqual(flow.job_id("Friso", "FRISO PRO 3/800g", "abc123xyz9", 2), "FRISO_FRISO_PRO_3_800G_ABC123XY_R2")

    def test_tasks_state(self):
        self.assertEqual(flow.tasks_state([], {})[0], "none")
        self.assertEqual(flow.tasks_state(["a"], {})[0], "running")
        self.assertEqual(flow.tasks_state(["a", "b"], {"a": {"state": "done"}, "b": {"state": "running"}})[0], "running")
        self.assertEqual(flow.tasks_state(["a"], {"a": {"state": "done"}})[0], "done")
        self.assertEqual(flow.tasks_state(["a"], {"a": {"state": "failed", "error": "x"}}), ("failed", "x"))

    def test_holds_done_goes_to_pick(self):
        r = flow.decide_item(item("holds", {"holds": ["t1"]}), PROJ,
                             W({"t1": {"state": "done"}}, {"J1": {"candidates": [{"id": "hold_c01", "file": {"path": "x"}}]}}))
        self.assertEqual(r["set"]["stage"], "pick")
        self.assertEqual(r["steps"], [])

    def test_failed_task_marks_error_without_changing_stage(self):
        r = flow.decide_item(item("motion", {"motion": ["t1"]}), PROJ, W({"t1": {"state": "failed", "error": "500"}}))
        self.assertEqual(r["set"], {"stage_state": "error", "error": "500"})

    def test_master_waits_for_anchor_then_motion(self):
        it = item("master", {"master": ["t1"]})
        w = W({"t1": {"state": "done"}}, {"J1": {"master": {"path": "m"}}})
        r = flow.decide_item(it, PROJ, w)
        self.assertEqual(r["set"]["stage"], "wait_anchor")
        self.assertEqual(r["need_anchor_from"], "J1")
        r = flow.decide_item(item("wait_anchor"), PROJ, dict(w, anchor_ready=True))
        self.assertEqual(r["set"]["stage"], "motion")
        self.assertEqual(r["steps"][0][1]["dirs"], ["left", "right", "below"])
        self.assertEqual(r["steps"][0][1]["holds"], 0)

    def test_gates_stop_then_approve(self):
        r = flow.decide_item(item("motion", {"motion": ["t"]}), PROJ, W({"t": {"state": "done"}}))
        self.assertEqual((r["set"]["stage"], r["set"]["stage_state"]), ("qc_motion", "waiting"))
        stage, step = flow.approve_item(item("qc_motion"), PROJ)
        self.assertEqual((stage, step["holds"], step["hold_start"], step["dirs"]), ("hold_a", 1, 1, []))
        stage, step = flow.approve_item(item("qc_hold_a"), PROJ)
        self.assertEqual((stage, step["hold_start"]), ("hold_b", 2))
        with self.assertRaises(ValueError):
            flow.approve_item(item("hold_b"), PROJ)

    def test_night_mode_skips_gates_and_mixes(self):
        night = dict(PROJ, night_mode=1)
        r = flow.decide_item(item("motion", {"motion": ["t"]}), night, W({"t": {"state": "done"}}))
        self.assertEqual(r["set"]["stage"], "hold_a")
        r = flow.decide_item(item("hold_a", {"hold_a": ["t"]}), night, W({"t": {"state": "done"}}))
        self.assertEqual(r["set"]["stage"], "hold_b")
        r = flow.decide_item(item("hold_b", {"hold_b": ["t"]}, audio_seconds=65), night, W({"t": {"state": "done"}}))
        self.assertEqual(r["set"]["stage"], "mixing")
        mix = r["steps"][0][1]
        self.assertEqual((mix["op"], mix["duration_s"], mix["jobs"], mix["batch_id"]), ("mix", 65.0, ["J1"], "lo1"))
        r = flow.decide_item(item("mixing", {"mixing": ["m"]}), night, W({"m": {"state": "done"}}))
        self.assertEqual(r["set"]["stage"], "done")

    def test_gates_off_day_mode_ends_ready(self):
        off = dict(PROJ, gate_motion=0, gate_hold_a=0)
        r = flow.decide_item(item("hold_b", {"hold_b": ["t"]}), off, W({"t": {"state": "done"}}))
        self.assertEqual((r["set"]["stage"], r["steps"]), ("ready", []))

    def test_running_stage_is_idempotent(self):
        r = flow.decide_item(item("motion", {"motion": ["t"]}), PROJ, W({"t": {"state": "running"}}))
        self.assertEqual((r["set"], r["steps"]), ({}, []))

    def test_regen_units(self):
        self.assertEqual(flow.regen_units("qc_motion", ["left"])[0], ["putdown_left"])
        self.assertEqual(flow.regen_units("qc_motion")[1], "motion")
        self.assertEqual(flow.regen_units("qc_hold_a")[0], ["hold_01"])
        with self.assertRaises(ValueError):
            flow.regen_units("holds")

    def test_hold_fields_skip_empty_numbers(self):
        f = flow.hold_fields({"sku": "A", "width_cm": 14.0, "height_cm": None, "size_pct": 0}, "Friso")
        self.assertEqual((f["product_width_cm"], f["product_height_cm"], f["size_adjust_pct"], f["lipsync"]), ("14", "", "", "0"))

    def test_summary(self):
        c = flow.project_summary([{"stage": "pick"}, {"stage": "qc_motion"}, {"stage": "motion", "stage_state": "running"},
                                  {"stage": "ready"}, {"stage": "done"}, {"stage": "hold_a", "stage_state": "error"}])
        self.assertEqual(c, {"total": 6, "pick": 1, "qc": 1, "running": 1, "ready": 1, "done": 1, "error": 1})


class TestCostView(unittest.TestCase):
    def test_chia_chi_phi(self):
        costs = {"usd_per_credit": 0.005,
                 "job": {"P_111_X_R1": {"usd": 0.24, "est_credits": 0}, "P_111_X_R2": {"usd": 1.2, "est_credits": 0},
                         "P_222_X_R1": {"usd": 0.5, "est_credits": 0}, "P_1112_X_R1": {"usd": 9, "est_credits": 0}},
                 "host": {"H": {"usd": 1.0, "est_credits": 10}}, "videos": {"111": 4}}
        items = [{"sku": "111"}, {"sku": "222"}]
        v = flow.cost_view(costs, items)
        self.assertEqual(items[0]["cost_usd"], 1.44)            # 2 lan lam, khong lan SKU 1112
        self.assertEqual(items[0]["cost_share_usd"], 0.5)       # clip noi $1 chia 2 SKU
        self.assertAlmostEqual(items[0]["cost_per_video_usd"], 0.485, delta=0.006)  # (1.44+0.5)/4
        self.assertIsNone(items[1]["cost_per_video_usd"])       # chua tron video nao
        self.assertEqual(v["total_usd"], 2.94)
        self.assertTrue(v["estimated"])

    def test_khong_co_du_lieu(self):
        items = [{"sku": "1"}]
        v = flow.cost_view(None, items)
        self.assertEqual(v["total_usd"], 0)
        self.assertEqual(items[0]["cost_usd"], 0)


if __name__ == "__main__":
    unittest.main()
