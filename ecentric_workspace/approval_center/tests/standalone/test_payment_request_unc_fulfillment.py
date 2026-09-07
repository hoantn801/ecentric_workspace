# Copyright (c) 2026, eCentric and contributors
"""Payment Request buoc 6 - Finance xu ly UNC (07/09, Hoan).

Code THAT cua features/payment_request/application/service.py + reminders.py nap bang
exec(compile) tren frappe/engine gia (ghi lai moi lenh). Kiem:
  1. on_final_approval: Assigned, han = 17:00 ngay thanh toan, giao ToDo fulfillment cho MOI
     Fulfiller voi date = ngay thanh toan, bao nguoi de nghi + Finance; khong co Fulfiller ->
     log_error, van Assigned.
  2. claim: gate (ToDo / fulfiller / SM), UPDATE co dieu kien (nguoi thu hai bi tu choi),
     ToDo duy nhat, audit Started.
  3. complete: bat buoc file UNC (/private/files...), chi owner hoac SM, gan File mo coi vao
     phieu TRUOC save, dong ToDo, audit Completed, bao ca hai.
  4. reminders: chi phieu dang xu ly & payment_date <= hom nay+3, moi ngay mot lan, Assigned ->
     Fulfiller, In Progress -> owner, loi mot phieu khong chan phieu khac, kill switch.
  5. Dang ky engine: FULFILLMENT_DOCTYPES + _FULFILLMENT_HANDLERS co EC Payment Request;
     definition feature="payment_request"; api dung bind_fulfillment; hooks co scheduler.
  6. permissions.is_fulfiller_participant nhan dong Role (ca phong Finance) lan dong User.
"""
import ast
import datetime as _dt
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.abspath(os.path.join(_HERE, "..", ".."))
_APP = os.path.abspath(os.path.join(_AC, ".."))


def _read(*p):
    with io.open(os.path.join(_AC, *p), encoding="utf-8") as fh:
        return fh.read()


class _Throw(Exception):
    pass


class _Perm(_Throw):
    pass


def _getdate(v):
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


class _Doc(types.SimpleNamespace):
    def get(self, k, d=None):
        return getattr(self, k, d)


def _load(docs, roles=("Employee",), user="fin@ec.vn", todos=None, participants=None, case=None):
    """docs: {name: dict} cua EC Payment Request. Tra ve (service_mod, reminders_mod, world, frappe).
    service.py import engine/command_service LUC GOI (lazy) nen stub phai o lai trong
    sys.modules toi het test: `case.addCleanup` tra lai."""
    world = {"set_value": [], "sql": [], "assign": [], "notify": [], "log": [], "ensure_sole": [],
             "closed": [], "attached": [], "saved": [], "log_error": [], "docs": docs,
             "todos": set(todos or [])}
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=user)
    fk.PermissionError = _Perm
    fk.conf = {}
    fk.get_roles = lambda u=None: list(roles)
    fk.parse_json = lambda s: __import__("json").loads(s)
    fk.get_traceback = lambda: "tb"
    fk.log_error = lambda msg, title=None: world["log_error"].append((title, msg))
    fk.utils = types.SimpleNamespace(now_datetime=lambda: _dt.datetime(2026, 9, 7, 10, 0),
                                     formatdate=lambda d: "%02d-%02d-%d" % (_getdate(d).day, _getdate(d).month, _getdate(d).year),
                                     getdate=_getdate,
                                     add_days=lambda d, n: _getdate(d) + _dt.timedelta(days=n))

    def get_doc(dt, name=None):
        if dt == "EC Payment Request":
            d = _Doc(**docs[name]); d.doctype = dt; d.name = name
            d.meta = types.SimpleNamespace(fields=[types.SimpleNamespace(fieldname="completed_attachment", fieldtype="Attach")])

            def save(ignore_permissions=False, _d=d):
                world["saved"].append(dict(vars(_d)))
                docs[name].update({k: v for k, v in vars(_d).items() if k not in ("meta", "save", "doctype")})
            d.save = save
            return d
        if dt == "EC Approval Process":
            return types.SimpleNamespace(name=name, participants=participants if participants is not None else [
                types.SimpleNamespace(participant_purpose="Fulfiller", source_type="Role", role="EC Finance"),
                types.SimpleNamespace(participant_purpose="Approver", source_type="User", user="ceo@ec.vn")])
        raise AssertionError("get_doc %s" % dt)
    fk.get_doc = get_doc

    def db_get_value(dt, name, field=None, as_dict=False, **k):
        if dt == "EC Approval Request":
            return "PAYMENT_REQUEST-V1"
        if dt == "EC Payment Request":
            return docs[name].get(field)
        raise AssertionError("get_value %s" % dt)

    def db_set_value(dt, name, field, value=None, update_modified=True):
        if isinstance(field, dict):
            docs[name].update(field); world["set_value"].append((name, dict(field)))
        else:
            docs[name][field] = value; world["set_value"].append((name, {field: value}))

    def db_sql(q, params=None):
        world["sql"].append((" ".join(q.split()), params))
        if q.strip().lower().startswith("update"):
            # Stub KHONG tu tra loi: dieu kien 'Assigned' phai nam trong SQL that.
            u, name = params
            cond = "fulfillment_status='Assigned'" in q
            if not cond or docs[name].get("fulfillment_status") == "Assigned":
                docs[name]["fulfillment_status"] = "In Progress"; docs[name]["fulfillment_owner"] = u
            return None
        name, u = params
        return [(1,)] if docs[name].get("fulfillment_owner") == u else []

    def db_exists(dt, f):
        if dt == "ToDo":
            return (f["reference_name"], f["allocated_to"]) in world["todos"]
        return False

    def get_all(dt, filters=None, fields=None, limit_page_length=None, **k):
        assert dt == "EC Payment Request"
        out = []
        for n, d in docs.items():
            if d.get("fulfillment_status") not in filters["fulfillment_status"][1]:
                continue
            if _getdate(d["payment_date"]) > _getdate(filters["payment_date"][1]):
                continue
            out.append(types.SimpleNamespace(name=n, unc_reminded_on=d.get("unc_reminded_on")))
        return out
    fk.get_all = get_all
    fk.db = types.SimpleNamespace(get_value=db_get_value, set_value=db_set_value, sql=db_sql, exists=db_exists)

    def throw(msg, exc=_Throw):
        raise exc(msg)
    fk.throw = throw

    fs = types.ModuleType("ecentric_workspace.approval_center.shared.finance_support")
    fs.frappe = fk; fs._ = fk._; fs.getdate = _getdate
    funding = types.ModuleType("ecentric_workspace.approval_center.features.payment_request.application.funding")
    funding.validate_funding = lambda doc: None
    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
    eng.resolve_participants = lambda rows, requester: [("fin1@ec.vn", "Role: EC Finance"), ("fin2@ec.vn", "Role: EC Finance")] if any(
        r.participant_purpose == "Fulfiller" for r in rows) else []
    eng.assign = lambda dt, name, users, desc=None, date=None, fulfillment=False: world["assign"].append(
        {"name": name, "users": list(users), "date": date, "fulfillment": fulfillment})
    eng.notify = lambda users, subject, dt, name: world["notify"].append((list(users), subject, name))
    eng.request_label = lambda dt, name: "PR " + name
    eng.is_active_process_fulfiller = lambda at, u: u in ("fin1@ec.vn", "fin2@ec.vn")
    eng.ensure_sole_todo = lambda dt, name, u, desc=None, date=None: world["ensure_sole"].append((name, u, date))
    eng.log_action = lambda ar, action, actor, **k: world["log"].append((action, actor, k.get("new_status")))
    eng.close_fulfillment_todos = lambda dt, name: world["closed"].append(name)
    cs = types.ModuleType("ecentric_workspace.approval_center.shared.requests.command_service")
    cs.attach_extra_files = lambda doc, urls: world["attached"].append((doc.name, list(urls), doc.get("completed_attachment"), len(world["saved"])))
    fu = types.ModuleType("frappe.utils")
    for k in ("now_datetime", "formatdate", "getdate", "add_days"):
        setattr(fu, k, getattr(fk.utils, k))
    svc_mod = types.ModuleType("ecentric_workspace.approval_center.features.payment_request.application.service")
    mods = {"frappe": fk, "frappe.utils": fu,
            "ecentric_workspace.approval_center.shared.finance_support": fs,
            "ecentric_workspace.approval_center.features.payment_request.application.funding": funding,
            "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
            "ecentric_workspace.approval_center.shared.requests.command_service": cs,
            "ecentric_workspace.approval_center.features.payment_request.application.service": svc_mod}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)

    def restore():
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    if case is not None:
        case.addCleanup(restore)
    try:
        exec(compile(_read("features", "payment_request", "application", "service.py"), "service.py", "exec"),
             svc_mod.__dict__)
        rem = types.ModuleType("_reminders_under_test")
        exec(compile(_read("features", "payment_request", "application", "reminders.py"), "reminders.py", "exec"),
             rem.__dict__)
    except Exception:
        restore()
        raise
    if case is None:
        restore()
    return svc_mod, rem, world, fk


def _pr(**over):
    base = {"approval_request": "EC-APR-1", "requested_by": "req@ec.vn", "payment_date": "2026-09-10",
            "fulfillment_status": "Not Started", "fulfillment_owner": None, "completed_attachment": None,
            "fulfillment_summary": None, "company": "EC", "unc_reminded_on": None}
    base.update(over)
    return base


class TestOnFinalApproval(unittest.TestCase):
    def test_giao_finance_han_17h_ngay_thanh_toan_todo_theo_ngay(self):
        svc, _r, w, _f = _load({"PR-1": _pr()}, case=self)
        svc.on_final_approval("PR-1")
        d = w["docs"]["PR-1"]
        self.assertEqual(d["fulfillment_status"], "Assigned")
        self.assertEqual(d["fulfillment_due_at"], _dt.datetime(2026, 9, 10, 17, 0))
        self.assertEqual(w["assign"], [{"name": "PR-1", "users": ["fin1@ec.vn", "fin2@ec.vn"],
                                        "date": _dt.date(2026, 9, 10), "fulfillment": True}])
        users, subject, _n = w["notify"][0]
        self.assertEqual(users, ["req@ec.vn", "fin1@ec.vn", "fin2@ec.vn"])
        self.assertIn("UNC", subject)
        self.assertIn("10-09-2026", subject)

    def test_khong_co_fulfiller_van_assigned_va_log(self):
        svc, _r, w, _f = _load({"PR-1": _pr()}, participants=[], case=self)
        svc.on_final_approval("PR-1")
        self.assertEqual(w["docs"]["PR-1"]["fulfillment_status"], "Assigned")
        self.assertEqual(w["assign"], [])
        self.assertTrue(any("Fulfiller" in m for _t, m in w["log_error"]))

    def test_unc_due_at(self):
        svc, _r, _w, _f = _load({}, case=self)
        self.assertIsNone(svc.unc_due_at(None))
        self.assertEqual(svc.unc_due_at("2026-09-30"), _dt.datetime(2026, 9, 30, 17, 0))


class TestClaim(unittest.TestCase):
    def test_finance_nhan_viec(self):
        svc, _r, w, _f = _load({"PR-1": _pr(fulfillment_status="Assigned")}, user="fin1@ec.vn", case=self)
        self.assertEqual(svc.claim_fulfillment("PR-1"), {"owner": "fin1@ec.vn"})
        self.assertEqual(w["docs"]["PR-1"]["fulfillment_status"], "In Progress")
        self.assertEqual(w["ensure_sole"], [("PR-1", "fin1@ec.vn", _dt.date(2026, 9, 10))])
        self.assertEqual(w["log"], [("Started", "fin1@ec.vn", "In Progress")])
        self.assertEqual(w["notify"][0][0], ["req@ec.vn"])

    def test_nguoi_ngoai_nhom_bi_chan(self):
        svc, _r, w, _f = _load({"PR-1": _pr(fulfillment_status="Assigned")}, user="ke.la@ec.vn", case=self)
        with self.assertRaises(_Perm):
            svc.claim_fulfillment("PR-1")
        self.assertEqual(w["sql"], [])

    def test_nguoi_co_todo_tren_phieu_duoc_nhan_du_khong_trong_nhom(self):
        svc, _r, w, _f = _load({"PR-1": _pr(fulfillment_status="Assigned")}, user="tam@ec.vn",
                               todos=[("PR-1", "tam@ec.vn")], case=self)
        svc.claim_fulfillment("PR-1")
        self.assertEqual(w["docs"]["PR-1"]["fulfillment_owner"], "tam@ec.vn")

    def test_nguoi_thu_hai_bi_tu_choi(self):
        svc, _r, w, _f = _load({"PR-1": _pr(fulfillment_status="In Progress", fulfillment_owner="fin1@ec.vn")},
                               user="fin2@ec.vn", case=self)
        with self.assertRaises(_Throw) as cm:
            svc.claim_fulfillment("PR-1")
        self.assertIn("người khác", str(cm.exception))
        self.assertEqual(w["docs"]["PR-1"]["fulfillment_owner"], "fin1@ec.vn")
        self.assertEqual(w["ensure_sole"], [])


class TestComplete(unittest.TestCase):
    def _inprog(self, **o):
        return {"PR-1": _pr(fulfillment_status="In Progress", fulfillment_owner="fin1@ec.vn", **o)}

    def test_hoan_tat_gan_file_truoc_save_dong_todo_bao_ca_hai(self):
        svc, _r, w, _f = _load(self._inprog(), user="fin1@ec.vn", case=self)
        out = svc.complete_fulfillment("PR-1", payload='{"completed_attachment": "/private/files/unc.pdf", "fulfillment_summary": " UNC 123 "}')
        self.assertEqual(out, {"completed": True})
        d = w["docs"]["PR-1"]
        self.assertEqual(d["fulfillment_status"], "Completed")
        self.assertEqual(d["completed_attachment"], "/private/files/unc.pdf")
        self.assertEqual(d["fulfillment_summary"], "UNC 123")
        self.assertEqual(d["completed_by"], "fin1@ec.vn")
        # attach_extra_files goi khi truong da mang url va TRUOC save (saved_count == 0)
        self.assertEqual(w["attached"], [("PR-1", ["/private/files/unc.pdf"], "/private/files/unc.pdf", 0)])
        self.assertEqual(len(w["saved"]), 1)
        self.assertEqual(w["closed"], ["PR-1"])
        self.assertEqual(w["log"], [("Completed", "fin1@ec.vn", "Completed")])
        self.assertEqual(sorted(w["notify"][0][0]), ["fin1@ec.vn", "req@ec.vn"])

    def test_thieu_file_unc_thi_tu_choi(self):
        for bad in ('{}', '{"completed_attachment": ""}', '{"completed_attachment": "http://x/y.pdf"}'):
            svc, _r, w, _f = _load(self._inprog(), user="fin1@ec.vn", case=self)
            with self.assertRaises(_Throw) as cm:
                svc.complete_fulfillment("PR-1", payload=bad)
            self.assertIn("UNC", str(cm.exception))
            self.assertEqual(w["saved"], [])
            self.assertEqual(w["closed"], [])

    def test_khong_phai_owner_bi_chan_sm_thi_duoc(self):
        svc, _r, w, _f = _load(self._inprog(), user="fin2@ec.vn", case=self)
        with self.assertRaises(_Perm):
            svc.complete_fulfillment("PR-1", payload='{"completed_attachment": "/private/files/u.pdf"}')
        svc, _r, w, _f = _load(self._inprog(), user="admin@ec.vn", roles=("System Manager",), case=self)
        svc.complete_fulfillment("PR-1", payload='{"completed_attachment": "/private/files/u.pdf"}')
        self.assertEqual(w["docs"]["PR-1"]["completed_by"], "admin@ec.vn")
        self.assertEqual(w["docs"]["PR-1"]["fulfillment_owner"], "fin1@ec.vn")   # khong cuop owner

    def test_phieu_chua_toi_buoc_6_thi_tu_choi(self):
        svc, _r, w, _f = _load({"PR-1": _pr(fulfillment_status="Not Started")}, user="admin@ec.vn",
                               roles=("System Manager",), case=self)
        with self.assertRaises(_Throw):
            svc.complete_fulfillment("PR-1", payload='{"completed_attachment": "/private/files/u.pdf"}')


class TestReminders(unittest.TestCase):
    TODAY = _dt.date(2026, 9, 7)

    def test_chi_phieu_dang_xu_ly_trong_cua_so_D3_va_chua_nhac_hom_nay(self):
        docs = {
            "A": _pr(fulfillment_status="Assigned", payment_date="2026-09-10"),                # D-3 -> nhac
            "B": _pr(fulfillment_status="In Progress", payment_date="2026-09-01", fulfillment_owner="fin1@ec.vn"),  # qua han -> nhac
            "C": _pr(fulfillment_status="Assigned", payment_date="2026-09-11"),                # D-4 -> chua
            "D": _pr(fulfillment_status="Completed", payment_date="2026-09-07"),               # xong -> khong
            "E": _pr(fulfillment_status="Assigned", payment_date="2026-09-08", unc_reminded_on="2026-09-07"),  # da nhac hom nay
            "F": _pr(fulfillment_status="Assigned", payment_date="2026-09-08", unc_reminded_on="2026-09-06"),  # nhac hom qua -> nhac lai
        }
        _s, rem, w, _f = _load(docs, case=self)
        self.assertEqual(sorted(rem.due_candidates(self.TODAY)), ["A", "B", "F"])
        n = rem.remind_unc_due(self.TODAY)
        self.assertEqual(n, 3)
        by = {name: (users, subj) for users, subj, name in w["notify"]}
        self.assertEqual(by["A"][0], ["fin1@ec.vn", "fin2@ec.vn"])       # Assigned -> ca nhom
        self.assertIn("còn 3 ngày", by["A"][1])
        self.assertEqual(by["B"][0], ["fin1@ec.vn"])                     # In Progress -> owner
        self.assertIn("QUÁ HẠN 6 ngày", by["B"][1])
        for k in ("A", "B", "F"):
            self.assertEqual(w["docs"][k]["unc_reminded_on"], self.TODAY)
        self.assertIsNone(w["docs"]["C"]["unc_reminded_on"])
        # chay lan hai cung ngay: khong nhac lai
        self.assertEqual(rem.remind_unc_due(self.TODAY), 0)

    def test_hom_nay_la_ngay_thanh_toan(self):
        _s, rem, w, _f = _load({"A": _pr(fulfillment_status="Assigned", payment_date="2026-09-07")}, case=self)
        rem.remind_unc_due(self.TODAY)
        self.assertIn("HÔM NAY", w["notify"][0][1])

    def test_loi_mot_phieu_khong_chan_phieu_khac_va_kill_switch(self):
        docs = {"A": _pr(fulfillment_status="Assigned", payment_date="2026-09-08"),
                "B": _pr(fulfillment_status="Assigned", payment_date="2026-09-08")}
        _s, rem, w, fk = _load(docs, case=self)
        real = fk.get_doc

        def boom(dt, name=None):
            if name == "A":
                raise RuntimeError("db hong")
            return real(dt, name)
        fk.get_doc = boom
        self.assertEqual(rem.remind_unc_due(self.TODAY), 1)
        self.assertEqual([n for _u, _s2, n in w["notify"]], ["B"])
        self.assertTrue(any("remind_unc_due A" in (t or "") for t, _m in w["log_error"]))
        # kill switch: nap moi, chua nhac gi, bat cong tac -> 0 va KHONG bao ai
        _s2, rem2, w2, fk2 = _load({"A": _pr(fulfillment_status="Assigned", payment_date="2026-09-08")}, case=self)
        fk2.conf["ec_payment_unc_reminder_disabled"] = 1
        self.assertEqual(rem2.remind_unc_due(self.TODAY), 0)
        self.assertEqual(w2["notify"], [])


class TestWiring(unittest.TestCase):
    def test_engine_dang_ky_payment_request(self):
        src = _read("shared", "workflow", "transitions.py")
        tree = ast.parse(src)
        handlers = docs = None
        for n in tree.body:
            if isinstance(n, ast.Assign):
                tid = [t.id for t in n.targets if isinstance(t, ast.Name)]
                if "_FULFILLMENT_HANDLERS" in tid:
                    handlers = {k.value: v.value for k, v in zip(n.value.keys, n.value.values)}
                if "FULFILLMENT_DOCTYPES" in tid:
                    docs = [e.value for e in n.value.elts]
        self.assertIn("EC Payment Request", docs)
        self.assertEqual(handlers.get("EC Payment Request"),
                         "ecentric_workspace.approval_center.features.payment_request.application.service.on_final_approval")

    def test_definition_api_hooks_doctype(self):
        d = _read("features", "payment_request", "domain", "definition.py")
        self.assertIn('feature="payment_request"', d)
        self.assertIn('"fulfillment_status"', d)
        a = _read("features", "payment_request", "controllers", "api.py")
        self.assertIn('bind_fulfillment("PAYMENT_REQUEST"', a)
        self.assertNotIn('bind("PAYMENT_REQUEST")', a)
        with io.open(os.path.join(_APP, "hooks.py"), encoding="utf-8") as fh:
            h = fh.read()
        self.assertIn("features.payment_request.application.reminders.remind_unc_due", h)
        import json
        dt = json.loads(_read("doctype", "ec_payment_request", "ec_payment_request.json"))
        names = {f["fieldname"]: f for f in dt["fields"]}
        for f in ("fulfillment_status", "fulfillment_owner", "fulfillment_due_at", "completed_by",
                  "completed_attachment", "fulfillment_summary", "unc_reminded_on"):
            self.assertIn(f, names, f)
            self.assertIn(f, dt["field_order"], f)
            self.assertEqual(names[f].get("read_only"), 1, f)     # chi backend ghi
        self.assertEqual(names["completed_attachment"]["fieldtype"], "Attach")
        with io.open(os.path.join(_APP, "patches.txt"), encoding="utf-8") as fh:
            p = fh.read()
        self.assertIn("p149_payment_request_finance_unc_fulfiller", p)
        self.assertIn("p150_resync_payment_request_unc_step", p)

    def test_setup_va_patch_them_fulfiller_role_ec_finance(self):
        s = _read("features", "payment_request", "infrastructure", "setup.py")
        self.assertIn('FULFILLER_ROLE = "EC Finance"', s)
        self.assertIn('"participant_purpose": "Fulfiller", "source_type": "Role"', s)
        p = _read("patches", "p149_payment_request_finance_unc_fulfiller.py")
        self.assertIn('"participant_purpose": "Fulfiller", "source_type": "Role"', p)
        self.assertIn('"status": "Active"', p)
        self.assertIn('any(p.participant_purpose == "Fulfiller"', p)     # idempotent


def _permissions(participants, user_roles):
    """participants: list of dict(parent, purpose, source_type, user, role)."""
    fk = types.ModuleType("frappe")
    fk.session = types.SimpleNamespace(user="u@ec.vn")
    fk.get_roles = lambda u=None: list(user_roles)

    def exists(dt, f):
        assert dt == "EC Approval Participant"
        return any(p["parent"] in f["parent"][1] and p["purpose"] == "Fulfiller"
                   and p["source_type"] == "User" and p.get("user") == f["user"] for p in participants)

    def get_all(dt, fields=None, filters=None, **k):
        if dt == "EC Approval Process":
            return ["P1"]
        return [types.SimpleNamespace(role=p["role"]) for p in participants
                if p["parent"] in filters["parent"][1] and p["purpose"] == "Fulfiller"
                and p["source_type"] == "Role" and p.get("role")]
    fk.db = types.SimpleNamespace(exists=exists, get_value=lambda *a, **k: None)
    fk.get_all = get_all
    saved = sys.modules.get("frappe"); sys.modules["frappe"] = fk
    try:
        m = types.ModuleType("_perm_under_test")
        exec(compile(_read("shared", "workflow", "permissions.py"), "permissions.py", "exec"), m.__dict__)
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved
    return m


class TestFulfillerByRole(unittest.TestCase):
    ROLE_ROW = {"parent": "P1", "purpose": "Fulfiller", "source_type": "Role", "role": "EC Finance"}
    USER_ROW = {"parent": "P1", "purpose": "Fulfiller", "source_type": "User", "user": "x@ec.vn"}

    def test_role_match(self):
        m = _permissions([self.ROLE_ROW], ("Employee", "EC Finance"))
        self.assertTrue(m.is_fulfiller_participant(["P1"], "u@ec.vn"))
        self.assertTrue(m._is_configured_fulfiller("u@ec.vn", "PAYMENT_REQUEST"))

    def test_khong_co_role_thi_khong(self):
        m = _permissions([self.ROLE_ROW], ("Employee",))
        self.assertFalse(m.is_fulfiller_participant(["P1"], "u@ec.vn"))

    def test_user_row_van_nhu_cu(self):
        m = _permissions([self.USER_ROW], ("Employee",))
        self.assertTrue(m.is_fulfiller_participant(["P1"], "x@ec.vn"))
        self.assertFalse(m.is_fulfiller_participant(["P1"], "y@ec.vn"))
        self.assertFalse(m.is_fulfiller_participant([], "x@ec.vn"))

    def test_transitions_dung_chung_ham(self):
        src = _read("shared", "workflow", "transitions.py")
        i = src.index("def is_active_process_fulfiller(")
        self.assertIn("is_fulfiller_participant(procs, user)", src[i:i + 900])


if __name__ == "__main__":
    unittest.main()
