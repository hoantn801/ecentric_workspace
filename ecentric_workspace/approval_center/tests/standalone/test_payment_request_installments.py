# Copyright (c) 2026, eCentric and contributors
"""Payment Request - thanh toan chia dot (07/09, Hoan).

MOI DOT = MOT PHIEU rieng (duyet + 5 chu ky rieng). Kiem tren CODE THAT (exec/compile, frappe gia):
  1. validate_installment: 100% -> xoa sach truong dot; chia dot: tong bat buoc, dot nay <= con
     lai, dot ke mac dinh = con lai, khong vuot, ngay dot ke bat buoc & sau ngay dot nay; dot
     cuoi -> khong con dot ke; dot 1 tu nhan so 1.
  2. installments_block: chuoi, da chi, con lai, dot ke, can_create_next (chu phieu + Completed
     + con lai + chua co dot ke con hieu luc; phieu bi tu choi khong tinh).
  3. create_next_installment: gate; idempotent (da co dot ke -> tra ve); prepare dien dung
     (installment_of = goc, so dot +1, so tien = con lai/dot ke, ngay = du kien, tieu de hau to
     " — Đợt k", ly do co dong ngu canh, dot truoc's dong ngu canh bi bo).
  4. payment_title: hau to " — Đợt k" chi khi chia dot; khong lap "Đợt 1 — Đợt 2".
  5. command_service.clone_followup: chep nhu clone_request nhung KHONG doi trang thai tu choi;
     chi chu phieu/SM; prepare chay TRUOC draft_preparer/title_builder.
  6. reminders.remind_next_installment: D-7, chi khi chua co dot ke, 1 lan/ngay.
  7. Dinh nghia: editable_fields KHONG chua installment_no/installment_of (server dat);
     detail_extender = installments_block; api co create_next_installment POST; hooks scheduler.
"""
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

    def set(self, k, v):
        setattr(self, k, v)


class _Row(dict):
    """Nhu frappe._dict: doc bang thuoc tinh lan khoa, gan duoc bang khoa."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _load(docs, user="req@ec.vn", roles=("Employee",), case=None):
    """docs: {name: dict}. 'approval_status' trong dict = trang thai EC Approval Request gia."""
    world = {"notify": [], "set_value": [], "inserted": [], "log_error": []}
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=user)
    fk.PermissionError = _Perm
    fk.conf = {}
    fk.get_roles = lambda u=None: list(roles)
    fk.get_traceback = lambda: "tb"
    fk.log_error = lambda msg, title=None: world["log_error"].append((title, msg))
    fk.utils = types.SimpleNamespace(now_datetime=lambda: _dt.datetime(2026, 9, 7, 10, 0),
                                     formatdate=lambda d: "%02d-%02d-%d" % (_getdate(d).day, _getdate(d).month, _getdate(d).year),
                                     getdate=_getdate,
                                     add_days=lambda d, n: _getdate(d) + _dt.timedelta(days=n))

    def get_doc(dt, name=None):
        assert dt == "EC Payment Request", dt
        d = _Doc(**docs[name]); d.doctype = dt; d.name = name
        return d
    fk.get_doc = get_doc

    def new_doc(dt):
        d = _Doc(doctype=dt, name=None, request_title=None, reason=None, payment_amount=None, payment_date=None,
                 payment_mode=None, total_amount=None, installment_no=None, installment_of=None,
                 next_installment_amount=None, next_installment_date=None, requested_by=None,
                 employee=None, department=None, company=None, details_and_attachments_correct=None,
                 funding_source_doctype=None, funding_source_name=None, purchase_request=None)

        def insert(ignore_permissions=False, _d=d):
            _d.name = "EC-PAYR-NEW"
            docs["EC-PAYR-NEW"] = {k: v for k, v in vars(_d).items() if k not in ("insert", "doctype")}
            world["inserted"].append(docs["EC-PAYR-NEW"])
        d.insert = insert
        return d
    fk.new_doc = new_doc

    def get_all(dt, filters=None, fields=None, limit_page_length=None, pluck=None, order_by=None, **k):
        if dt == "File":
            return []
        assert dt == "EC Payment Request"
        out = []
        for n, d in docs.items():
            okrow = True
            flist = filters if isinstance(filters, list) else [[kk, "=", vv] if not isinstance(vv, (list, tuple)) else [kk] + list(vv) for kk, vv in (filters or {}).items()]
            for f in flist:
                fld, op, val = f[0], f[1], f[2]
                cur = n if fld == "name" else d.get(fld)
                if op == "=" and cur != val: okrow = False
                if op == "<=" and (cur is None or _getdate(cur) > _getdate(val)): okrow = False
                if op == ">" and not ((cur or 0) > val): okrow = False
            if okrow:
                row = _Row({f: (n if f == "name" else d.get(f)) for f in (fields or ["name"])})
                out.append(row)
        return out
    fk.get_all = get_all

    def db_get_value(dt, name, field=None, as_dict=False, **k):
        if dt == "EC Approval Request":
            # name = "AR-<pr>" -> trang thai luu tren phieu
            pr = name[3:] if name else None
            return (docs.get(pr) or {}).get("approval_status")
        return (docs.get(name) or {}).get(field)

    def db_set_value(dt, name, field, value=None, update_modified=True):
        docs[name][field] = value; world["set_value"].append((name, field, value))
    fk.db = types.SimpleNamespace(get_value=db_get_value, set_value=db_set_value, exists=lambda *a, **k: False,
                                  sql=lambda *a, **k: [])

    def throw(msg, exc=_Throw):
        raise exc(msg)
    fk.throw = throw

    fs = types.ModuleType("ecentric_workspace.approval_center.shared.finance_support")
    fs.frappe = fk; fs._ = fk._; fs.getdate = _getdate
    funding = types.ModuleType("ecentric_workspace.approval_center.features.payment_request.application.funding")
    funding.validate_funding = lambda doc: None
    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
    eng.notify = lambda users, subject, dt, name: world["notify"].append((list(users), subject, name))
    eng.request_label = lambda dt, name: "PR " + name
    # command_service THAT (clone_followup + _copy_to_new_draft + _copy_attachments)
    caps = types.ModuleType("ecentric_workspace.approval_center.shared.requests.capabilities")
    caps.is_system_manager = lambda u=None: "System Manager" in roles
    caps.approval_request_for = lambda definition, name: None
    caps.derive = lambda user, doc, req: {"can_edit": True}
    qs = types.ModuleType("ecentric_workspace.approval_center.shared.requests.query_service")
    qs.employee_context = lambda u: {"employee": "EMP-1", "department": "Finance - EC", "company": "EC"}
    cs = types.ModuleType("ecentric_workspace.approval_center.shared.requests.command_service")
    svc_mod = types.ModuleType("ecentric_workspace.approval_center.features.payment_request.application.service")
    reg = types.ModuleType("ecentric_workspace.approval_center.shared.registry")
    defn = types.SimpleNamespace(
        code="PAYMENT_REQUEST", business_doctype="EC Payment Request",
        editable_fields=("request_title", "reason", "payment_amount", "payment_date", "payee_full_name",
                         "account_bank", "bank_account_number", "has_purchase_request", "purchase_request",
                         "funding_source_doctype", "funding_source_name", "no_purchase_request_reason",
                         "is_cost_valid", "details_and_attachments_correct", "request_attachment",
                         "department", "company", "payment_mode", "total_amount",
                         "next_installment_amount", "next_installment_date"),
        clone_exclude_fields=("details_and_attachments_correct",),
        draft_preparer=lambda d: svc_mod.normalize_payment(d),
        title_builder=lambda d: svc_mod.payment_title(d),
        status_label_map={"Approved": "Đã duyệt"})
    reg.get_definition = lambda code: defn
    mods = {"frappe": fk, "frappe.utils": types.SimpleNamespace(),
            "ecentric_workspace.approval_center.shared.finance_support": fs,
            "ecentric_workspace.approval_center.features.payment_request.application.funding": funding,
            "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
            "ecentric_workspace.approval_center.shared.requests.capabilities": caps,
            "ecentric_workspace.approval_center.shared.requests.query_service": qs,
            "ecentric_workspace.approval_center.shared.requests.command_service": cs,
            "ecentric_workspace.approval_center.shared.registry": reg,
            "ecentric_workspace.approval_center.features.payment_request.application.service": svc_mod}
    for k in ("now_datetime", "formatdate", "getdate", "add_days"):
        setattr(mods["frappe.utils"], k, getattr(fk.utils, k))
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
        exec(compile(_read("shared", "requests", "command_service.py"), "command_service.py", "exec"), cs.__dict__)
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
    return svc_mod, rem, world, fk, cs, defn


def _pr(**o):
    b = {"requested_by": "req@ec.vn", "request_title": "Camera meeting", "reason": "Mua camera",
         "payee_full_name": "Cty A", "account_bank": "VCB", "bank_account_number": "123",
         "has_purchase_request": "No", "no_purchase_request_reason": "x", "is_cost_valid": "Yes",
         "details_and_attachments_correct": "Yes", "request_attachment": "/private/files/a.pdf",
         "department": "IT", "company": "EC", "payment_amount": 5000, "payment_date": "2026-09-10",
         "payment_mode": "Installment", "total_amount": 10000, "installment_no": 1, "installment_of": None,
         "next_installment_amount": None, "next_installment_date": "2026-10-10",
         "approval_request": None, "approval_status": None, "fulfillment_status": "Not Started", "completed_at": None,
         "next_installment_reminded_on": None, "purchase_request": None, "funding_source_doctype": None,
         "funding_source_name": None, "docstatus": 0}
    b.update(o)
    if b.get("approval_status") and not b.get("approval_request"):
        b["approval_request"] = "AR-" + (o.get("_name") or "")
    return b


def _docs(**named):
    out = {}
    for n, d in named.items():
        d = dict(d); d.setdefault("approval_request", "AR-" + n if d.get("approval_status") else None)
        if d.get("approval_status"):
            d["approval_request"] = "AR-" + n
        out[n] = d
    return out


class TestValidateInstallment(unittest.TestCase):
    def _doc(self, svc, **o):
        d = _Doc(**_pr(**o)); d.name = o.get("name", "PR-1"); return d

    def test_full_xoa_sach_truong_dot(self):
        svc, *_ = _load({}, case=self)
        d = self._doc(svc, payment_mode="Full", total_amount=999, installment_no=2, installment_of="X",
                      next_installment_amount=1, next_installment_date="2026-12-01")
        svc.validate_installment(d)
        self.assertEqual(d.payment_mode, "Full")
        self.assertIsNone(d.total_amount); self.assertIsNone(d.installment_no); self.assertIsNone(d.installment_of)
        self.assertIsNone(d.next_installment_amount); self.assertIsNone(d.next_installment_date)

    def test_dot_1_tu_nhan_so_1_va_dot_ke_mac_dinh_bang_con_lai(self):
        svc, *_ = _load({}, case=self)
        d = self._doc(svc, installment_no=None, next_installment_amount=None)
        svc.validate_installment(d)
        self.assertEqual(d.installment_no, 1)
        self.assertEqual(d.next_installment_amount, 5000)

    def test_thieu_tong_hoac_vuot_tong(self):
        svc, *_ = _load({}, case=self)
        with self.assertRaises(_Throw) as cm:
            svc.validate_installment(self._doc(svc, total_amount=0))
        self.assertIn("Tổng giá trị", str(cm.exception))
        with self.assertRaises(_Throw) as cm:
            svc.validate_installment(self._doc(svc, payment_amount=12000))
        self.assertIn("vượt", str(cm.exception))

    def test_dot_ke_khong_vuot_con_lai_va_can_ngay_sau_dot_nay(self):
        svc, *_ = _load({}, case=self)
        with self.assertRaises(_Throw):
            svc.validate_installment(self._doc(svc, next_installment_amount=6000))
        with self.assertRaises(_Throw) as cm:
            svc.validate_installment(self._doc(svc, next_installment_date=None))
        self.assertIn("Ngày dự kiến", str(cm.exception))
        with self.assertRaises(_Throw) as cm:
            svc.validate_installment(self._doc(svc, next_installment_date="2026-09-10"))
        self.assertIn("sau ngày", str(cm.exception))
        d = self._doc(svc, next_installment_amount=3000)      # chia 3 dot: hop le
        svc.validate_installment(d)
        self.assertEqual(d.next_installment_amount, 3000)

    def test_dot_cuoi_khong_con_dot_ke(self):
        svc, *_ = _load({}, case=self)
        d = self._doc(svc, payment_amount=10000, next_installment_amount=1, next_installment_date="2026-12-01")
        svc.validate_installment(d)
        self.assertIsNone(d.next_installment_amount); self.assertIsNone(d.next_installment_date)

    def test_dot_2_tinh_phan_da_de_nghi_o_dot_1(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed"),
                        "PR-2": _pr(installment_no=2, installment_of="PR-1", payment_amount=5000,
                                    next_installment_date=None)})
        svc, *_ = _load(docs, case=self)
        d = _Doc(**docs["PR-2"]); d.name = "PR-2"
        svc.validate_installment(d)                      # 5000 + 5000 = 10000 -> dot cuoi, OK
        self.assertIsNone(d.next_installment_amount)
        d2 = _Doc(**docs["PR-2"]); d2.name = "PR-2"; d2.payment_amount = 6000
        with self.assertRaises(_Throw):
            svc.validate_installment(d2)                 # 5000 + 6000 > 10000

    def test_dot_1_bi_tu_choi_khong_tinh_vao_da_de_nghi(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Rejected"),
                        "PR-1b": _pr(approval_status="Approved", fulfillment_status="Completed"),
                        "PR-2": _pr(installment_no=2, installment_of="PR-1b", payment_amount=5000, next_installment_date=None)})
        svc, *_ = _load(docs, case=self)
        self.assertEqual(svc.paid_before(_Doc(**docs["PR-2"], name="PR-2")), 5000)


class TestTitle(unittest.TestCase):
    def test_hau_to_dot(self):
        svc, *_ = _load({}, case=self)
        self.assertEqual(svc.payment_title(_Doc(request_title="Camera", payment_mode="Installment", installment_no=2)), "Camera — Đợt 2")
        self.assertEqual(svc.payment_title(_Doc(request_title="Camera — Đợt 1", payment_mode="Installment", installment_no=2)), "Camera — Đợt 2")
        self.assertEqual(svc.payment_title(_Doc(request_title="Camera", payment_mode="Full", installment_no=None)), "Camera")
        self.assertEqual(svc.payment_title(_Doc(request_title="", payment_mode="Installment", installment_no=1,
                                                payee_full_name="A", payment_amount=5000)), "Payment Request - A - 5000 — Đợt 1")


class TestInstallmentsBlock(unittest.TestCase):
    def test_chuoi_con_lai_va_can_create(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed", completed_at="2026-09-10 15:00:00")})
        svc, *_ = _load(docs, case=self)
        b = svc.installments_block(_Doc(**docs["PR-1"], name="PR-1"), None)["installments"]
        self.assertEqual(b["total_amount"], 10000); self.assertEqual(b["paid_amount"], 5000)
        self.assertEqual(b["remaining_after_this"], 5000); self.assertIsNone(b["next_request"])
        self.assertEqual(b["next_expected"], {"amount": None, "date": "2026-10-10"})
        self.assertTrue(b["can_create_next"])
        self.assertEqual([c["name"] for c in b["chain"]], ["PR-1"]); self.assertTrue(b["chain"][0]["is_current"])

    def test_chua_unc_thi_chua_tao_duoc_nguoi_khac_cung_khong(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Assigned")})
        svc, *_ = _load(docs, case=self)
        self.assertFalse(svc.installments_block(_Doc(**docs["PR-1"], name="PR-1"), None)["installments"]["can_create_next"])
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed")})
        svc, *_ = _load(docs, user="ke.la@ec.vn", case=self)
        self.assertFalse(svc.installments_block(_Doc(**docs["PR-1"], name="PR-1"), None)["installments"]["can_create_next"])

    def test_da_co_dot_ke_thi_khong_tao_them_tru_khi_dot_ke_bi_tu_choi(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed"),
                        "PR-2": _pr(installment_no=2, installment_of="PR-1", approval_status="Pending")})
        svc, *_ = _load(docs, case=self)
        b = svc.installments_block(_Doc(**docs["PR-1"], name="PR-1"), None)["installments"]
        self.assertEqual(b["next_request"], "PR-2"); self.assertFalse(b["can_create_next"])
        self.assertEqual([c["installment_no"] for c in b["chain"]], [1, 2])
        docs["PR-2"]["approval_status"] = "Rejected"
        b = svc.installments_block(_Doc(**docs["PR-1"], name="PR-1"), None)["installments"]
        self.assertIsNone(b["next_request"]); self.assertTrue(b["can_create_next"])

    def test_phieu_100_phan_tram(self):
        svc, *_ = _load({}, case=self)
        self.assertEqual(svc.installments_block(_Doc(payment_mode="Full"), None), {"installments": None})


class TestCreateNext(unittest.TestCase):
    def test_tao_dot_2_dien_dung(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed",
                                    completed_at="2026-09-10 15:00:00", request_title="Camera — Đợt 1",
                                    reason="[Đợt 0 — cũ]\nMua camera")})
        svc, _r, w, _f, _cs, _d = _load(docs, case=self)
        out = svc.create_next_installment("PR-1")
        self.assertEqual(out["name"], "EC-PAYR-NEW"); self.assertEqual(out["installment_no"], 2)
        n = docs["EC-PAYR-NEW"]
        self.assertEqual(n["payment_mode"], "Installment"); self.assertEqual(n["installment_of"], "PR-1")
        self.assertEqual(n["installment_no"], 2); self.assertEqual(n["total_amount"], 10000)
        self.assertEqual(n["payment_amount"], 5000); self.assertEqual(n["payment_date"], "2026-10-10")
        self.assertIsNone(n["next_installment_amount"]); self.assertIsNone(n["next_installment_date"])
        self.assertEqual(n["request_title"], "Camera — Đợt 2")
        self.assertTrue(n["reason"].startswith("[Đợt 2 — tổng 10,000 VND; đợt 1 (PR-1) đã thanh toán UNC ngày 10-09-2026]\nMua camera"), n["reason"])
        self.assertEqual(n["details_and_attachments_correct"], "No")     # cam ket ca nhan khong chep
        self.assertEqual(n["requested_by"], "req@ec.vn")

    def test_gate(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Assigned")})
        svc, *_ = _load(docs, case=self)
        with self.assertRaises(_Throw) as cm:
            svc.create_next_installment("PR-1")
        self.assertIn("UNC", str(cm.exception))
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed")})
        svc, *_ = _load(docs, user="ke.la@ec.vn", case=self)
        with self.assertRaises(_Perm):
            svc.create_next_installment("PR-1")
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed", payment_mode="Full")})
        svc, *_ = _load(docs, case=self)
        with self.assertRaises(_Throw):
            svc.create_next_installment("PR-1")

    def test_idempotent_da_co_dot_ke(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed"),
                        "PR-2": _pr(installment_no=2, installment_of="PR-1", approval_status=None)})
        svc, _r, w, *_ = _load(docs, case=self)
        self.assertEqual(svc.create_next_installment("PR-1"), {"name": "PR-2", "existing": True})
        self.assertEqual(w["inserted"], [])

    def test_dot_3_van_tro_ve_phieu_goc_dot_1(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed", payment_amount=3000,
                                    next_installment_amount=3000),
                        "PR-2": _pr(installment_no=2, installment_of="PR-1", payment_amount=3000, approval_status="Approved",
                                    fulfillment_status="Completed", next_installment_amount=4000, next_installment_date="2026-11-10")})
        svc, *_ = _load(docs, case=self)
        out = svc.create_next_installment("PR-2")
        n = docs["EC-PAYR-NEW"]
        self.assertEqual(out["installment_no"], 3)
        self.assertEqual(n["installment_of"], "PR-1", "goc cua chuoi luon la dot 1, khong phai dot truoc")
        self.assertEqual(n["payment_amount"], 4000)      # 10000 - 3000 - 3000

    def test_so_tien_dot_ke_theo_du_kien_nhung_khong_vuot_con_lai(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed", next_installment_amount=3000)})
        svc, *_ = _load(docs, case=self)
        svc.create_next_installment("PR-1")
        self.assertEqual(docs["EC-PAYR-NEW"]["payment_amount"], 3000)
        docs = _docs(**{"PR-1": _pr(approval_status="Approved", fulfillment_status="Completed", next_installment_amount=9000)})
        svc, *_ = _load(docs, case=self)
        svc.create_next_installment("PR-1")
        self.assertEqual(docs["EC-PAYR-NEW"]["payment_amount"], 5000)


class TestCloneFollowup(unittest.TestCase):
    def test_khong_doi_tu_choi_va_prepare_chay_truoc_title(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved")})
        _s, _r, w, _f, cs, defn = _load(docs, case=self)
        seen = []
        out = cs.clone_followup(defn, "PR-1", lambda t, src: (seen.append(t.request_title), setattr(t, "installment_no", 7)))
        self.assertEqual(out["name"], "EC-PAYR-NEW")
        self.assertEqual(seen, ["Camera meeting"])               # prepare thay gia tri da chep, TRUOC title_builder
        self.assertEqual(docs["EC-PAYR-NEW"]["request_title"], "Camera meeting — Đợt 7")
        with self.assertRaises(_Throw):
            cs.clone_request(defn, "PR-1")                         # duong cu van chi nhan Rejected/Cancelled

    def test_chi_chu_phieu(self):
        docs = _docs(**{"PR-1": _pr(approval_status="Approved")})
        _s, _r, _w, _f, cs, defn = _load(docs, user="ke.la@ec.vn", case=self)
        with self.assertRaises(_Perm):
            cs.clone_followup(defn, "PR-1", lambda t, s: None)


class TestReminderNextInstallment(unittest.TestCase):
    TODAY = _dt.date(2026, 10, 3)

    def test_D7_chi_khi_chua_co_dot_ke_mot_lan_mot_ngay(self):
        docs = _docs(**{
            "A": _pr(approval_status="Approved", fulfillment_status="Completed", next_installment_date="2026-10-10"),   # D-7 -> nhac
            "B": _pr(approval_status="Approved", fulfillment_status="Completed", next_installment_date="2026-10-11"),   # D-8 -> chua
            "C": _pr(approval_status="Approved", fulfillment_status="Completed", next_installment_date="2026-10-05"),   # co dot ke -> khong
            "C2": _pr(installment_no=2, installment_of="C", approval_status="Pending"),
            "D": _pr(approval_status="Approved", fulfillment_status="Assigned", next_installment_date="2026-10-04"),    # chua UNC -> khong
            "E": _pr(approval_status="Approved", fulfillment_status="Completed", next_installment_date="2026-10-01",
                     next_installment_reminded_on="2026-10-03"),                                                          # da nhac hom nay
        })
        for d in docs.values():
            d["next_installment_amount"] = d.get("next_installment_amount") or 5000
        _s, rem, w, *_ = _load(docs, case=self)
        self.assertEqual(rem.remind_next_installment(self.TODAY), 1)
        self.assertEqual([n for _u, _s2, n in w["notify"]], ["A"])
        users, subj, _n = w["notify"][0]
        self.assertEqual(users, ["req@ec.vn"]); self.assertIn("đợt 2", subj); self.assertIn("còn 7 ngày", subj)
        self.assertEqual(docs["A"]["next_installment_reminded_on"], self.TODAY)
        self.assertEqual(docs["C"]["next_installment_reminded_on"], self.TODAY)   # da co dot ke: danh dau, khong bao
        self.assertEqual(rem.remind_next_installment(self.TODAY), 0)


class TestWiring(unittest.TestCase):
    def test_definition_api_hooks_doctype(self):
        d = _read("features", "payment_request", "domain", "definition.py")
        i = d.index("PAYMENT_REQUEST_DEFINITION = _make("); ed = d[i:d.index('("name", "request_title"', i)]
        for f in ("payment_mode", "total_amount", "next_installment_amount", "next_installment_date"):
            self.assertIn('"%s"' % f, ed, f)
        for f in ("installment_no", "installment_of"):
            self.assertNotIn('"%s"' % f, ed, f + " do SERVER dat, khong duoc la editable")
        # Tu 09/09 `detail_extender` tro vao `detail_extra` = installments_block + unc_fix_block
        # (`detail_extender` chi nhan MOT ham). Dieu can giu la khoi chia dot VAN toi duoc man
        # hinh - nen kiem cai do, chu khong kiem ten ham: buoc moi lan them mot khoi phu la
        # phai sua test nay thi test dang giu mot chi tiet, khong giu mot dam bao.
        self.assertIn("detail_extender=detail_extra", d)
        svc_src = _read("features", "payment_request", "application", "service.py")
        i = svc_src.index("def detail_extra(")
        self.assertIn("installments_block(business, request)", svc_src[i:i + 400],
                      "detail_extra phai GOP khoi chia dot, khong duoc thay the no")
        a = _read("features", "payment_request", "controllers", "api.py")
        j = a.index("def create_next_installment(")
        self.assertIn('@frappe.whitelist(methods=["POST"])', a[:j].rstrip().splitlines()[-1])
        with io.open(os.path.join(_APP, "hooks.py"), encoding="utf-8") as fh:
            self.assertIn("reminders.remind_next_installment", fh.read())
        import json
        dt = json.loads(_read("doctype", "ec_payment_request", "ec_payment_request.json"))
        names = {f["fieldname"]: f for f in dt["fields"]}
        for f in ("payment_mode", "total_amount", "installment_no", "installment_of",
                  "next_installment_amount", "next_installment_date", "next_installment_reminded_on"):
            self.assertIn(f, names, f); self.assertIn(f, dt["field_order"], f)
        self.assertEqual(names["installment_of"]["options"], "EC Payment Request")
        self.assertEqual(names["installment_no"].get("read_only"), 1)
        self.assertEqual(names["payment_mode"]["options"], "Full\nInstallment")
        q = _read("shared", "requests", "query_service.py")
        self.assertIn('"extra": extra', q); self.assertIn("definition.detail_extender(business, request)", q)
        c = _read("shared", "requests", "contracts.py")
        self.assertIn("detail_extender: Optional[Callable] = None", c)
        with io.open(os.path.join(_APP, "patches.txt"), encoding="utf-8") as fh:
            self.assertIn("p153_resync_payment_request_installments", fh.read())


if __name__ == "__main__":
    unittest.main()
