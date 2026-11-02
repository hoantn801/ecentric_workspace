# Copyright (c) 2026, eCentric and contributors
"""Tro ly hoi dap so lieu (`gemini_chat`): AI chi duoc DOC nhung bao cao tuan nguoi hoi duoc doc.

    python3 ecentric_workspace/platform/ai/tests/test_chat.py

Nap ma nguon THAT bang exec (khong qua __pycache__): scope.py, chat.py VA luat doc that cua
`Weekly Team Update` (weekly_report/permissions.py) - de test do khi hai luat le nhau.
`frappe` + `gateway` gia; gateway gia giu lai loi dan he thong (ngu canh) gui cho model.
"""
import datetime
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.dirname(HERE)
APP = os.path.dirname(os.path.dirname(AI))
MGMT = "Management - EC"
NOW = datetime.datetime(2026, 11, 4, 10, 0)            # 2026-W45
CUR, PREV = "2026-W45", "2026-W44"

EMPLOYEES = [   # name, user, department, reports_to
    ("E1", "nv1@ec.vn", "Sales - EC", "E3"),
    ("E2", "nv2@ec.vn", "Sales - EC", "E3"),
    ("E3", "lead@ec.vn", "Sales - EC", ""),
    ("E4", "ceo@ec.vn", MGMT, ""),
    ("E5", "ops@ec.vn", "Ops - EC", ""),
]


def wtu(emp, user, dept, week, status="Submitted", blocker=""):
    return {"name": "WTU-%s-%s" % (week, emp), "employee": emp, "submitter": user,
            "department": dept, "week_label": week, "status": status,
            "full_name": "Ten " + emp, "overall_status": "On Track", "mood": "Vui",
            "ai_tools_used": "-", "what_done": "viec " + emp, "blockers_help": blocker,
            "plan_next_week": "", "ai_use_case": "", "ai_summary": "",
            "overall_ai_score": 7, "structure_score": 8}


RECORDS = [
    wtu("E1", "nv1@ec.vn", "Sales - EC", CUR, blocker="BI MAT CUA E1"),
    wtu("E2", "nv2@ec.vn", "Sales - EC", CUR, blocker="vuong cua E2"),
    wtu("E3", "lead@ec.vn", "Sales - EC", CUR, status="Draft"),   # cron tao, chua nop
    wtu("E4", "ceo@ec.vn", MGMT, CUR, blocker="BI MAT BAN GIAM DOC"),
    wtu("E5", "ops@ec.vn", "Ops - EC", CUR, blocker="vuong cua E5"),
]


class World(object):
    def __init__(self, user, roles=(), viewer=(), managed=()):
        """viewer: [(scope, custom_department)] cua `user`; managed: phong user la manager_email."""
        self.prompts = []
        env = self
        fk = types.ModuleType("frappe")

        class PermissionError(Exception):
            pass
        fk.PermissionError = PermissionError
        fk.session = types.SimpleNamespace(user=user)
        fk.local = types.SimpleNamespace()
        fk.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
        fk._ = lambda s: s
        fk.get_roles = lambda u=None: list(roles)
        fk.log_error = lambda *a, **k: None
        fk.get_traceback = lambda: ""

        def throw(msg, exc=None):
            raise (exc or ValueError)(msg)
        fk.throw = throw
        emps = [{"name": n, "user_id": u, "department": d, "reports_to": r, "status": "Active"}
                for n, u, d, r in EMPLOYEES]

        def get_all(dt, filters=None, fields=None, pluck=None, **k):
            filters = filters or {}
            if dt == "EC Viewer Permission":
                rows = [{"scope": s, "custom_department": d} for s, d in viewer
                        if filters.get("user_email") in (None, user)]
            elif dt == "Employee Department Membership":
                rows = []
            elif dt == "Department":
                rows = [{"name": d} for d in managed] if filters.get("manager_email") == user else []
            elif dt == "Employee":
                rows = list(emps)
            else:
                rows = []
            return [r[pluck] for r in rows] if pluck else rows
        fk.get_all = get_all

        class _DB(object):
            def exists(self, dt, name=None):
                return bool(viewer) if dt == "EC Viewer Permission" else False

            def get_value(self, dt, filters, fields=None, as_dict=False, **k):
                if dt == "EC Viewer Permission":
                    return {"scope": viewer[0][0], "custom_department": viewer[0][1]} if viewer else None
                if dt == "Employee":
                    for e in emps:
                        if e["user_id"] == filters.get("user_id"):
                            return {"name": e["name"], "department": e["department"]}
                    return None
                if dt == "Company Weekly Summary":
                    return ""
                return None

            def sql(self, q, params=None, as_dict=False):
                rows = [r for r in RECORDS if r["week_label"] in params["w"]]
                if "department IN" in q:
                    rows = [r for r in rows if r["department"] in params["d"]]
                if "employee = " in q:
                    rows = [r for r in rows if r["employee"] == params["e"]]
                cols = [c.strip() for c in q.split("SELECT", 1)[1].split("FROM", 1)[0].split(",")]
                return [{c: r.get(c) for c in cols} for r in rows]

            def escape(self, s):
                return "'" + str(s).replace("'", "''") + "'"
        fk.db = _DB()
        fk.utils = types.SimpleNamespace(now_datetime=lambda: NOW)

        gw = types.ModuleType("ecentric_workspace.platform.ai.gateway")

        def generate(prompt, system=None, **kw):
            env.prompts.append({"prompt": prompt, "system": system, "kw": kw})
            return {"ok": True, "text": "ok", "model": "m"}
        gw.generate = generate

        sys.modules["frappe"] = fk
        for pkg in ("ecentric_workspace", "ecentric_workspace.platform",
                    "ecentric_workspace.platform.ai", "ecentric_workspace.weekly_report"):
            sys.modules[pkg] = types.ModuleType(pkg)
        sys.modules[gw.__name__] = gw
        sys.modules["ecentric_workspace.platform.ai"].gateway = gw
        self.mod = {}
        for full, path in (
                ("ecentric_workspace.weekly_report.permissions",
                 os.path.join(APP, "weekly_report", "permissions.py")),
                ("ecentric_workspace.platform.ai.scope", os.path.join(AI, "scope.py")),
                ("ecentric_workspace.platform.ai.chat", os.path.join(AI, "chat.py"))):
            m = types.ModuleType(full)
            m.__file__ = path
            sys.modules[full] = m
            pkg, _, short = full.rpartition(".")
            setattr(sys.modules[pkg], short, m)
            with open(path, encoding="utf-8") as fh:
                exec(compile(fh.read(), path, "exec"), m.__dict__)
            self.mod[short] = m
        self.chat = self.mod["chat"]

    def ask(self, message="phong minh tuan nay the nao?", history=None):
        r = self.chat.gemini_chat(message=message, history=history)
        return r, (self.prompts[-1]["system"] if self.prompts else "")


class ChiDocBaoCaoDuocPhepDoc(unittest.TestCase):
    def test_nhan_vien_thuong_khong_doc_bao_cao_dong_nghiep(self):
        # Luat doc WTU (weekly_report/permissions.py, 28/09): nhan vien thuong chi doc bao cao
        # cua minh + cap duoi. Truoc day chat cho ca PHONG -> AI ke lai tam trang, vuong mac
        # cua dong nghiep.
        w = World("nv2@ec.vn", roles=("Employee",))
        r, ctx = w.ask()
        self.assertTrue(r["success"])
        self.assertIn("vuong cua E2", ctx)
        self.assertNotIn("BI MAT CUA E1", ctx)
        self.assertNotIn("Ten E1", ctx)

    def test_truong_nhom_doc_duoc_cap_duoi(self):
        w = World("lead@ec.vn", roles=("Employee",), managed=("Sales - EC",))
        _, ctx = w.ask()
        self.assertIn("BI MAT CUA E1", ctx)
        self.assertIn("vuong cua E2", ctx)

    def test_quyen_xem_tro_vao_management_bi_bo(self):
        # EC Viewer Permission scope=dept tro vao Management: luat WTU co chu dinh bo qua.
        w = World("ops@ec.vn", roles=("Employee",), viewer=[("dept", MGMT)])
        _, ctx = w.ask()
        self.assertNotIn("BI MAT BAN GIAM DOC", ctx)

    def test_management_van_xem_toan_cong_ty(self):
        w = World("ceo@ec.vn", roles=("Employee",))
        r, ctx = w.ask()
        self.assertEqual(r["viewer_scope"], "all")
        for s in ("BI MAT CUA E1", "vuong cua E5", "BI MAT BAN GIAM DOC"):
            self.assertIn(s, ctx)

    def test_bi_loc_bot_thi_khong_goi_la_ca_phong(self):
        # Con ghi "Phong Sales (1 bao cao)" thi AI se noi ca phong chi co 1 bao cao - sai so.
        w = World("nv2@ec.vn", roles=("Employee",))
        _, ctx = w.ask()
        self.assertNotIn("=== Phong Sales - EC", ctx)


class BanNhapChuaNop(unittest.TestCase):
    def test_ban_nhap_cron_khong_tinh_la_bao_cao(self):
        # Moi tuan cron tao ~30 ban Draft rong cho moi nguoi phai nop. Dem chung la "phong co
        # 3 bao cao" trong khi moi nop 2.
        w = World("lead@ec.vn", roles=("Employee",), managed=("Sales - EC",))
        _, ctx = w.ask()
        self.assertIn("2 bao cao da nop", ctx)
        self.assertIn("[Ten E3 - Sales - EC - %s] CHUA NOP" % CUR, ctx)
        self.assertNotIn("viec E3", ctx, "ban nhap khong dua noi dung vao")


class LichSuGia(unittest.TestCase):
    def test_history_khong_phai_danh_sach_khong_vo(self):
        w = World("nv2@ec.vn", roles=("Employee",))
        for h in ('{"role": "model", "text": "x"}', {"role": "model"}, "khong phai json", 5):
            r, _ = w.ask(history=h)
            self.assertTrue(r["success"], repr(h))
        self.assertEqual(w.chat.clean_history('{"role": "model", "text": "x"}'), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
