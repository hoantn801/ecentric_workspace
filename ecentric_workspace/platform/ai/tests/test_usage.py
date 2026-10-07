# Copyright (c) 2026, eCentric and contributors
"""So lieu dung AI (/ai-usage): ghi log, tinh chi phi, gom so, va PHAM VI XEM.

    python3 ecentric_workspace/platform/ai/tests/test_usage.py

Nap ma nguon THAT bang exec (khong qua __pycache__) voi frappe gia.
"""
import datetime
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.dirname(HERE)


def load(name, mods=None):
    m = types.ModuleType("ecentric_workspace.platform.ai." + name)
    m.__file__ = os.path.join(AI, name + ".py")
    sys.modules[m.__name__] = m
    for pkg in ("ecentric_workspace", "ecentric_workspace.platform", "ecentric_workspace.platform.ai"):
        sys.modules.setdefault(pkg, types.ModuleType(pkg))
    setattr(sys.modules["ecentric_workspace.platform.ai"], name, m)
    with open(m.__file__, encoding="utf-8") as fh:
        exec(compile(fh.read(), m.__file__, "exec"), m.__dict__)
    return m


class FakeFrappe(types.ModuleType):
    def __init__(self, roles=(), user="nv@ec.vn", employees=(), depts=(), logs=(), conf=None):
        super().__init__("frappe")
        self.inserted, self.queries = [], []
        self.conf = dict(conf or {})
        self.session = types.SimpleNamespace(user=user)
        self._roles, self._emps, self._depts, self._logs = list(roles), list(employees), list(depts), list(logs)
        env = self

        class PermissionError(Exception):
            pass
        self.PermissionError = PermissionError
        self._ = lambda s: s
        self.whitelist = lambda *a, **k: (lambda f: f)
        self.log_error = lambda **k: None

        def throw(msg, exc=None):
            raise (exc or ValueError)(msg)
        self.throw = throw
        self.get_roles = lambda u=None: list(env._roles)
        self.utils = types.SimpleNamespace(nowdate=lambda: "2026-10-07")

        class _DB(object):
            def get_value(self, dt, filters, field=None, *a, **k):
                if dt == "Employee":
                    for e in env._emps:
                        if e["user_id"] == filters.get("user_id"):
                            return e["department"]
                    return None
                if dt == "User":
                    return "Ten " + str(filters)
                return None
        self.db = _DB()

        class _Doc(dict):
            flags = types.SimpleNamespace()

            def insert(self, **k):
                env.inserted.append(dict(self))
                self.name = "LOG-%d" % len(env.inserted)
                return self
        self.get_doc = lambda d: _Doc(d)

        def get_all(dt, filters=None, fields=None, pluck=None, **k):
            env.queries.append((dt, filters))
            if dt == "Department":
                return [d for d in env._depts if d["manager_email"] == filters["manager_email"]] if not pluck else \
                    [d["name"] for d in env._depts if d["manager_email"] == filters["manager_email"]]
            if dt == "Employee":
                out = []
                for e in env._emps:
                    f = filters or {}
                    uf = f.get("user_id")
                    if isinstance(uf, str) and e["user_id"] != uf:
                        continue
                    df = f.get("department")
                    if isinstance(df, str) and e["department"] != df:
                        continue
                    if isinstance(df, list) and e["department"] not in df[1]:
                        continue
                    out.append(types.SimpleNamespace(user_id=e["user_id"], employee_name=e["name"],
                                                     department=e["department"]))
                return out
            if dt == "EC AI Usage Log":
                users = None
                for f in filters or []:
                    if f[0] == "user" and f[1] == "in":
                        users = set(f[2])
                return [dict(l) for l in env._logs if users is None or l["user"] in users]
            return []
        self.get_all = get_all


EMPS = [{"user_id": "a@ec.vn", "name": "An", "department": "Media - EC"},
        {"user_id": "b@ec.vn", "name": "Bình", "department": "Media - EC"},
        {"user_id": "c@ec.vn", "name": "Chi", "department": "Finance - EC"},
        {"user_id": "boss@ec.vn", "name": "Sếp Media", "department": "Management - EC"}]
DEPTS = [{"name": "Media - EC", "manager_email": "boss@ec.vn"}]
LOGS = [
    {"user": "a@ec.vn", "department": "Media - EC", "purpose": "khay", "model": "gemini-3-8-flash-openai",
     "ok": 1, "latency_ms": 5000, "total_tokens": 900, "credits": 0.05, "cost_source": "kie", "images": 0,
     "creation": "2026-10-06 09:00:00"},
    {"user": "a@ec.vn", "department": "Media - EC", "purpose": "formfill", "model": "grok-4-7",
     "ok": 0, "latency_ms": 30000, "total_tokens": 0, "credits": 0, "cost_source": "", "images": 0,
     "creation": "2026-10-07 10:00:00"},
    {"user": "c@ec.vn", "department": "Finance - EC", "purpose": "chat", "model": "grok-4-7",
     "ok": 1, "latency_ms": 12000, "total_tokens": 2000, "credits": 0.8, "cost_source": "estimate",
     "images": 0, "creation": "2026-10-07 11:00:00"},
    {"user": "Administrator", "department": "", "purpose": "weekly_report", "model": "gemini-3-8-flash",
     "ok": 1, "latency_ms": 20000, "total_tokens": 5000, "credits": 0, "cost_source": "", "images": 0,
     "creation": "2026-10-07 03:00:00"},
]


class GhiLog(unittest.TestCase):
    def setUp(self):
        self.fk = FakeFrappe(employees=EMPS, user="a@ec.vn")
        sys.modules["frappe"] = self.fk
        self.U = load("usage")

    def test_dem_token_ba_ho_model(self):
        U = self.U
        self.assertEqual(U.token_counts({"promptTokenCount": 10, "candidatesTokenCount": 5,
                                         "thoughtsTokenCount": 7, "totalTokenCount": 22}), (10, 12, 22))
        self.assertEqual(U.token_counts({"prompt_tokens": 530, "completion_tokens": 21}), (530, 21, 551))
        self.assertEqual(U.token_counts({"input_tokens": 100, "output_tokens": 1500, "total_tokens": 1600}),
                         (100, 1500, 1600))
        self.assertEqual(U.token_counts(None), (0, 0, 0))

    def test_chi_phi_uu_tien_so_cua_kie_roi_moi_uoc_tinh(self):
        U = self.U
        self.assertEqual(U.credits_for("gemini-3-8-flash-openai", {"credits_consumed": 0.05}, 1, 1, {}),
                         (0.05, "kie"))
        self.assertEqual(U.credits_for("grok-4-7", {}, 1000000, 1000000, U.DEFAULT_PRICES), (640.0, "estimate"))
        self.assertEqual(U.credits_for("gemini-3-6-flash-openai", {}, 10, 10, {"gemini-3-6-flash": (100, 100)}),
                         (0.002, "estimate"), "bo duoi -openai khi tra gia")
        self.assertEqual(U.credits_for("gpt-6-luna", {}, 10, 10, U.DEFAULT_PRICES), (0.0, ""),
                         "khong biet gia thi KHONG doan")

    def test_ghi_mot_dong_khong_luu_noi_dung(self):
        self.U.record("khay", {"ok": True, "model": "gemini-3-8-flash-openai", "latency_ms": 5100,
                               "text": "BI MAT", "attempts": [{}, {}, {}], "fell_back": True,
                               "usage": {"prompt_tokens": 500, "completion_tokens": 20,
                                         "credits_consumed": 0.05}})
        row = self.fk.inserted[0]
        self.assertEqual((row["user"], row["department"], row["purpose"], row["ok"], row["attempts"]),
                         ("a@ec.vn", "Media - EC", "khay", 1, 3))
        self.assertEqual((row["total_tokens"], row["credits"], row["cost_source"]), (520, 0.05, "kie"))
        self.assertNotIn("BI MAT", json.dumps(row, ensure_ascii=False), "khong luu noi dung")
        self.assertNotIn("text", row)

    def test_bo_qua_luot_thu_ky_thuat(self):
        self.U.record("probe_llm_health", {"ok": True})
        self.assertEqual(self.fk.inserted, [])

    def test_gia_them_qua_site_config(self):
        self.fk.conf["ec_ai_prices"] = json.dumps({"gpt-6-luna": [50, 200], "rac": [1]})
        p = self.U.prices()
        self.assertEqual(p["gpt-6-luna"], (50.0, 200.0))
        self.assertNotIn("rac", p)
        self.assertIn("grok-4-7", p)

    def test_log_hong_khong_lam_hong_luot_ai(self):
        def boom(d):
            raise RuntimeError("db chet")
        self.fk.get_doc = boom
        self.assertIsNone(self.U.record("khay", {"ok": True}))


class GomSo(unittest.TestCase):
    def setUp(self):
        sys.modules["frappe"] = FakeFrappe()
        self.R = load("usage_report")

    def test_gom_theo_nguoi_tinh_nang_phong_ngay(self):
        people = {e["user_id"]: {"name": e["name"], "department": e["department"]} for e in EMPS}
        d = self.R.aggregate(LOGS, people, "2026-10-05", "2026-10-07")
        t = d["totals"]
        self.assertEqual((t["calls"], t["user_calls"], t["system_calls"], t["active_users"], t["headcount"]),
                         (4, 3, 1, 2, 4))
        self.assertEqual(t["adoption_pct"], 50.0)
        self.assertEqual((t["credits"], t["cost_estimated_calls"], t["cost_unpriced_calls"]), (0.85, 1, 2))
        an = [p for p in d["by_person"] if p["user"] == "a@ec.vn"][0]
        self.assertEqual((an["calls"], an["days"], an["ok_rate"]), (2, 2, 50.0))
        self.assertNotIn("Administrator", [p["user"] for p in d["by_person"]], "he thong khong la nhan su")
        f = {x["purpose"]: x for x in d["by_feature"]}
        self.assertEqual(f["weekly_report"]["system_calls"], 1)
        self.assertEqual(f["formfill"]["error_calls"], 1)
        self.assertEqual(f["khay"]["label"], "eC Mate (trợ lý góc trang)")
        self.assertEqual([x["date"] for x in d["daily"]], ["2026-10-05", "2026-10-06", "2026-10-07"],
                         "ngay khong ai dung van hien (cot 0)")
        self.assertEqual([x["calls"] for x in d["daily"]], [0, 1, 3])
        self.assertEqual(sorted(x["user"] for x in d["never"]), ["b@ec.vn", "boss@ec.vn"])
        media = [x for x in d["by_department"] if x["department"] == "Media - EC"][0]
        self.assertEqual((media["headcount"], media["active"], media["adoption_pct"]), (2, 1, 50.0))

    def test_ty_le_gui_cua_nhap_ai(self):
        f = self.R.funnel([{"outcome": "ok", "business_doc": "P1"}, {"outcome": "ok", "business_doc": "P2"},
                           {"outcome": "ok", "business_doc": None}, {"outcome": "error"}],
                          {"P1": "Pending", "P2": "Draft"})
        self.assertEqual(f, {"suggested": 3, "drafts": 2, "sent": 1, "sent_pct": 50.0})


class PhamViXem(unittest.TestCase):
    """Hoan 07/10: lanh dao xem toan cong ty, truong phong xem phong minh, con lai chi minh."""

    def api(self, user, roles=()):
        self.fk = FakeFrappe(roles=roles, user=user, employees=EMPS, depts=DEPTS, logs=LOGS)
        sys.modules["frappe"] = self.fk
        load("usage")
        load("usage_report")
        return load("usage_api")

    def test_nhan_vien_chi_thay_minh(self):
        d = self.api("c@ec.vn").summary(days=7)
        self.assertEqual(d["scope"]["kind"], "self")
        self.assertEqual([p["user"] for p in d["by_person"]], ["c@ec.vn"])
        self.assertEqual(d["totals"]["calls"], 1, "khong thay luot cua nguoi khac hay he thong")

    def test_nhan_vien_loc_phong_khac_bi_bo_qua(self):
        d = self.api("c@ec.vn").summary(days=7, department="Media - EC")
        self.assertEqual([p["user"] for p in d["by_person"]], ["c@ec.vn"])

    def test_truong_phong_thay_phong_minh_va_chinh_minh(self):
        d = self.api("boss@ec.vn").summary(days=7)
        self.assertEqual(d["scope"], {"kind": "dept", "departments": ["Media - EC"]})
        self.assertEqual([p["user"] for p in d["by_person"]], ["a@ec.vn"])
        self.assertNotIn("c@ec.vn", json.dumps(d), "khong lo nguoi phong khac")
        self.assertEqual(sorted(x["user"] for x in d["never"]), ["b@ec.vn", "boss@ec.vn"])

    def test_truong_phong_loc_phong_khac_bi_chan(self):
        api = self.api("boss@ec.vn")
        with self.assertRaises(self.fk.PermissionError):
            api.summary(days=7, department="Finance - EC")

    def test_lanh_dao_thay_toan_cong_ty(self):
        for role in ("System Manager", "EC CEO", "EC AI Usage Viewer"):
            d = self.api("ceo@ec.vn", roles=(role,)).summary(days=7)
            self.assertEqual(d["scope"]["kind"], "all", role)
            self.assertEqual(d["totals"]["calls"], 4, role)
            self.assertIn("Finance - EC", d["departments"])

    def test_lanh_dao_loc_mot_phong(self):
        d = self.api("ceo@ec.vn", roles=("EC CEO",)).summary(days=7, department="Finance - EC")
        self.assertEqual([p["user"] for p in d["by_person"]], ["c@ec.vn"])
        self.assertEqual(d["totals"]["system_calls"], 0)

    def test_khach_bi_chan(self):
        with self.assertRaises(Exception):
            self.api("Guest").summary()

    def test_khoang_ngay_bi_kep_toi_da_mot_nam(self):
        d = self.api("c@ec.vn").summary(from_date="2020-01-01", to_date="2026-10-07")
        self.assertEqual(d["period"]["from"], str(datetime.date(2026, 10, 7) - datetime.timedelta(days=365)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
