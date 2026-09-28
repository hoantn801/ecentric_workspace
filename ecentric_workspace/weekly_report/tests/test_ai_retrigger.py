# Copyright (c) 2026, eCentric and contributors
"""Cron cham bu (28/09): khong ket o ban ghi hong, moi ban ghi mot job rieng.

    python3 ecentric_workspace/weekly_report/tests/test_ai_retrigger.py

SO LIEU THAT lam ra bo test nay (Error Log 22-28/09): 200 luot cron tim 800 luot can
cham, chi 26 diem + 31 tom tat thanh cong. Cung vai ban ghi hong vinh vien (deck khong tai
duoc) bi boc lai 41 lan moi ban, chiem het 4 cho moi luot -> ban khac khong toi luot.
"""
import io
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "ai_retrigger.py")


def load(rows=None, score=None, summ=None):
    st = {"cache": {}, "enqueued": [], "logs": [], "rows": list(rows or []), "done": []}
    fk = types.ModuleType("frappe")

    class _Cache(object):
        def get_value(self, k):
            return st["cache"].get(k)

        def set_value(self, k, v, expires_in_sec=None):
            st["cache"][k] = v
            st["ttl"] = expires_in_sec

        def delete_value(self, k):
            st["cache"].pop(k, None)
    fk.cache = lambda: _Cache()
    fk.db = types.SimpleNamespace(
        sql=lambda q, params=None, as_dict=False: list(st["rows"])[:params["limit"]],
        get_value=lambda dt, name, fields, as_dict=False: next(
            (r for r in st["rows"] if r["name"] == name), None))
    fk.enqueue = lambda method, **kw: st["enqueued"].append(dict(kw, method=method))
    fk.log_error = lambda title=None, message=None: st["logs"].append((title, message))
    sys.modules["frappe"] = fk
    scoring = types.ModuleType("scoring")

    def _score(name, **kw):
        st["done"].append(("score", name, kw))
        return (score or (lambda n: {"success": True}))(name)

    def _summ(name, **kw):
        st["done"].append(("sum", name, kw))
        return (summ or (lambda n: {"success": True}))(name)
    scoring.score_report, scoring.summarize_report = _score, _summ
    sl = types.ModuleType("scoring_llm")
    sl.JOB_BUDGET, sl.JOB_ATTEMPT_TIMEOUT = 200, 150
    wr = types.ModuleType("ecentric_workspace.weekly_report")
    wr.scoring, wr.scoring_llm = scoring, sl
    sys.modules["ecentric_workspace"] = types.ModuleType("ecentric_workspace")
    sys.modules["ecentric_workspace.weekly_report"] = wr
    m = types.ModuleType("ai_retrigger_under_test")
    exec(compile(io.open(SRC, encoding="utf-8").read(), SRC, "exec"), m.__dict__)
    return m, st


def row(n, score=0, summary=""):
    return {"name": n, "week_label": "2026-W39", "overall_ai_score": score, "ai_summary": summary}


class Chon(unittest.TestCase):
    def test_ban_hong_nhieu_lan_nhuong_cho(self):
        m, _ = load()
        rows = [row("A"), row("B"), row("C"), row("D")]
        chosen, resting = m.pick(rows, 2, {"A": m.MAX_FAILS, "B": 1})
        self.assertEqual([r["name"] for r in chosen], ["B", "C"])
        self.assertEqual(resting, ["A"])

    def test_cron_xep_hang_job_rieng_tren_queue_long(self):
        rows = [row("R%d" % i) for i in range(10)]
        m, st = load(rows=rows)
        st["cache"][m.FAIL_KEY % "R0"] = m.MAX_FAILS
        out = m.run()
        self.assertEqual(out["enqueued"], m.BATCH_LIMIT)
        self.assertEqual(out["resting_names"], ["R0"])
        job = st["enqueued"][0]
        self.assertEqual((job["queue"], job["name"], job["job_id"], job["deduplicate"]),
                         ("long", "R1", "wr_ai::R1", True))
        self.assertGreater(job["timeout"], 300, "phai rong hon tran 300s cua worker thuong")


class MotBanGhi(unittest.TestCase):
    def test_thanh_cong_thi_xoa_dem(self):
        m, st = load(rows=[row("A")])
        st["cache"][m.FAIL_KEY % "A"] = 2
        out = m.process_one("A")
        self.assertTrue(out["ok"])
        self.assertNotIn(m.FAIL_KEY % "A", st["cache"])
        self.assertEqual([d[0] for d in st["done"]], ["score", "sum"])
        self.assertEqual(st["done"][0][2], {"budget": 200, "attempt_timeout": 150})

    def test_hong_thi_tang_dem_co_han_va_ghi_ly_do(self):
        m, st = load(rows=[row("A", score=80)],
                     summ=lambda n: {"success": False, "error": "deck khong tai duoc"})
        out = m.process_one("A")
        self.assertFalse(out["ok"])
        self.assertEqual(st["cache"][m.FAIL_KEY % "A"], 1)
        self.assertEqual(st["ttl"], m.COOLDOWN_HOURS * 3600, "nghi CO HAN, khong bo han")
        self.assertEqual([d[0] for d in st["done"]], ["sum"], "da co diem thi khong cham lai")
        self.assertIn("deck khong tai duoc", st["logs"][0][1])

    def test_loi_ngoai_y_muon_khong_giet_job(self):
        def boom(n):
            raise RuntimeError("no tung")
        m, st = load(rows=[row("A")], score=boom)
        out = m.process_one("A")
        self.assertFalse(out["ok"])
        self.assertTrue(any("no tung" in e for e in out["errors"]))
        self.assertEqual(len(st["done"]), 2, "hong cham diem van phai thu tom tat")


if __name__ == "__main__":
    unittest.main(verbosity=1)
