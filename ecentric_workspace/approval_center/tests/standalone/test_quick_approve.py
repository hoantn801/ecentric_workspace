"""Duyet nhanh "Cho toi duyet" (06/10/2026): list dung cap / khong lo phieu nguoi khac;
quick_decide di qua controller cua loai phieu, rollback khi loi, bao loi ro rang.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_quick_approve.py
"""
import datetime as dt
import importlib.util
import pathlib
import sys
import types

import pytest

APP = pathlib.Path(__file__).resolve().parents[3]


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return self.get(k)


class Doc(Obj):
    def as_dict(self):
        return dict(self)


class ValidationError(Exception):
    pass


class PermissionError_(Exception):
    pass


class DoesNotExistError(Exception):
    pass


def _match(row, filters):
    for k, v in (filters or {}).items():
        if isinstance(v, list) and v and v[0] == "in":
            if row.get(k) not in v[1]:
                return False
        elif row.get(k) != v:
            return False
    return True


def build(boom=None):
    W = types.SimpleNamespace(calls=[], savepoints=[], rollbacks=[], logs=[])
    W.approvers = [
        # me@x o cap 1 dang chay cua R1 (Leave)
        Obj(approval_request="R1", level_no=1, approver="me@x", status="Pending"),
        # me@x o cap 3 cua R2 - cap hien tai la 2 -> CHUA toi luot, khong duoc hien
        Obj(approval_request="R2", level_no=2, approver="other@x", status="Pending"),
        Obj(approval_request="R2", level_no=3, approver="me@x", status="Pending"),
        # R3 cua nguoi khac hoan toan
        Obj(approval_request="R3", level_no=1, approver="other@x", status="Pending"),
        # R4 dang Information Required -> khong hien
        Obj(approval_request="R4", level_no=1, approver="me@x", status="Pending"),
        # R5 payment co ky so -> needs_input
        Obj(approval_request="R5", level_no=1, approver="me@x", status="Pending"),
        # R6 cap 1 chua kich hoat (level Pending) -> khong hien
        Obj(approval_request="R6", level_no=1, approver="me@x", status="Pending"),
    ]
    W.requests = {
        "R1": Obj(name="R1", approval_type="LEAVE", reference_doctype="EC Leave Request",
                  reference_name="LV-1", requested_by="a@x", submitted_at="2026-10-05 09:00",
                  current_level=1, approval_status="Pending"),
        "R2": Obj(name="R2", approval_type="LEAVE", reference_doctype="EC Leave Request",
                  reference_name="LV-2", requested_by="a@x", submitted_at="2026-10-05 09:00",
                  current_level=2, approval_status="Pending"),
        "R3": Obj(name="R3", approval_type="LEAVE", reference_doctype="EC Leave Request",
                  reference_name="LV-3", requested_by="b@x", submitted_at="2026-10-05 09:00",
                  current_level=1, approval_status="Pending"),
        "R4": Obj(name="R4", approval_type="LEAVE", reference_doctype="EC Leave Request",
                  reference_name="LV-4", requested_by="a@x", submitted_at="2026-10-05 09:00",
                  current_level=1, approval_status="Information Required"),
        "R5": Obj(name="R5", approval_type="PAY", reference_doctype="EC Payment Request",
                  reference_name="PAY-1", requested_by="a@x", submitted_at="2026-10-04 09:00",
                  current_level=1, approval_status="Pending"),
        "R6": Obj(name="R6", approval_type="LEAVE", reference_doctype="EC Leave Request",
                  reference_name="LV-6", requested_by="a@x", submitted_at="2026-10-05 09:00",
                  current_level=1, approval_status="Pending"),
    }
    W.levels = {("R1", 1): Obj(level_name="Manager", level_status="In Progress", due_at="2026-10-07 18:00"),
                ("R2", 2): Obj(level_name="HR", level_status="In Progress", due_at=None),
                ("R3", 1): Obj(level_name="Manager", level_status="In Progress", due_at=None),
                ("R4", 1): Obj(level_name="Manager", level_status="In Progress", due_at=None),
                ("R5", 1): Obj(level_name="Finance", level_status="In Progress", due_at=None),
                ("R6", 1): Obj(level_name="Manager", level_status="Pending", due_at=None)}
    W.docs = {
        "LV-1": Doc(name="LV-1", requested_by="a@x", request_title="Nghi phep", leave_type="Annual",
                    duration_days=2.0, current_salary=99000000, start_date="2026-10-08"),
        "LV-2": Doc(name="LV-2", requested_by="a@x", request_title="x"),
        "LV-3": Doc(name="LV-3", requested_by="b@x", request_title="cua nguoi khac"),
        "LV-4": Doc(name="LV-4", requested_by="a@x", request_title="x"),
        "LV-6": Doc(name="LV-6", requested_by="a@x", request_title="x"),
        "PAY-1": Doc(name="PAY-1", requested_by="a@x", request_title="Thanh toan", payment_amount=12500000),
    }
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.ValidationError, fr.PermissionError, fr.DoesNotExistError = ValidationError, PermissionError_, DoesNotExistError
    fr.session = types.SimpleNamespace(user="me@x")
    fr.local = types.SimpleNamespace(message_log=[])
    fr.log_error = lambda *a, **k: W.logs.append(a)
    fr.get_traceback = lambda: "tb"

    def get_all(dt_, filters=None, fields=None, **k):
        if dt_ == "EC Approval Request Approver":
            return [r for r in W.approvers if _match(r, filters)]
        if dt_ == "EC Approval Request":
            return [r for r in W.requests.values() if _match(r, filters)]
        if dt_ == "EC Digital Signature Package":
            return [Obj(name="PKG-1", superseded_by=None, status="Locked")] if filters.get("business_name") == "PAY-1" else []
        if dt_ == "EC Digital Signature File":
            return [Obj(name="DSF-1", file_name="UNC-KOL-T9.pdf")] if filters.get("package") == "PKG-1" else []
        raise AssertionError(dt_)
    fr.get_all = get_all

    def get_doc(dt_, name):
        if dt_ == "EC Approval Request":
            return W.requests[name]
        if name not in W.docs:
            raise DoesNotExistError(name)
        return W.docs[name]
    fr.get_doc = get_doc

    def get_value(dt_, name, fields=None, as_dict=False):
        if dt_ == "EC Approval Request Level":
            lv = W.levels.get((name["approval_request"], name["level_no"]))
            return (lv.get(fields) if isinstance(fields, str) else lv) if lv else None
        if dt_ == "EC Approval Request":
            r = W.requests.get(name)
            return Obj({f: r.get(f) for f in fields}) if r else None
        if dt_ == "EC Approval Type":
            return Obj(approval_title={"LEAVE": "Nghỉ phép", "PAY": "Thanh toán"}[name],
                       route={"LEAVE": "approvals/leave", "PAY": "approvals/payment-request"}[name])
        if dt_ == "User":
            return {"a@x": "Anh A", "b@x": "Chi B"}.get(name)
        raise AssertionError(dt_)
    fr.db = types.SimpleNamespace(get_value=get_value,
                                  savepoint=lambda sp: W.savepoints.append(sp),
                                  rollback=lambda save_point=None: W.rollbacks.append(save_point))

    class _DF:
        def __init__(self, f, t):
            self.fieldname, self.fieldtype = f, t
    fr.get_meta = lambda d: types.SimpleNamespace(fields=[
        _DF("duration_days", "Float"), _DF("start_date", "Date"), _DF("payment_amount", "Currency"),
        _DF("current_salary", "Currency"), _DF("leave_type", "Select")])
    fu = types.ModuleType("frappe.utils")
    fu.getdate = lambda v: dt.date.fromisoformat(str(v)[:10])
    fu.get_datetime = lambda v: dt.datetime.fromisoformat(str(v))
    fr.utils = fu

    LEAVE = types.SimpleNamespace(code="LEAVE", business_doctype="EC Leave Request", feature="leave",
                                  quick_summary=(("Loại nghỉ", "leave_type"), ("Số ngày", "duration_days"),
                                                 ("Từ", "start_date"), ("Lương", "current_salary")),
                                  quick_comment_required=False, business_redactor=None)
    PAY = types.SimpleNamespace(code="PAY", business_doctype="EC Payment Request", feature="payment_request",
                                quick_summary=(("Số tiền", "payment_amount"),),
                                quick_comment_required=False, business_redactor=None)
    defs = {"LEAVE": LEAVE, "PAY": PAY}
    reg = types.ModuleType("ecentric_workspace.approval_center.shared.registry")
    reg.get_definition = lambda c: defs[c]
    reg.feature_of = lambda c: defs[c].feature
    caps = types.ModuleType("ecentric_workspace.approval_center.shared.requests.capabilities")

    def derive(user, biz, req):
        act = any(a.approval_request == req.name and a.level_no == req.current_level
                  and a.approver == user and a.status == "Pending" for a in W.approvers)
        return {"can_approve": act, "can_reject": act, "can_request_information": act,
                "requires_signature": act and req.approval_type == "PAY"}
    caps.derive = derive
    perm = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.permissions")
    perm.can_view_request = lambda req, user, *a, **k: any(
        x.approval_request == req and x.approver == user for x in W.approvers)

    def is_actionable(req, cur, user, status):
        return status == "Pending" and any(
            x.approval_request == req and x.level_no == cur and x.approver == user and x.status == "Pending"
            for x in W.approvers)
    perm.is_actionable = is_actionable

    ctl = types.ModuleType("ecentric_workspace.approval_center.features.leave.controllers.api")

    def _mk(action):
        def fn(name, comment=None):
            W.calls.append((action, name, comment))
            if boom:
                raise boom
            return {"ok": 1}
        return fn
    ctl.approve, ctl.reject, ctl.request_information = _mk("approve"), _mk("reject"), _mk("request_information")
    pay_ctl = types.ModuleType("ecentric_workspace.approval_center.features.payment_request.controllers.api")
    pay_ctl.approve = _mk("pay_approve")

    esg = types.ModuleType("ecentric_workspace.platform.esign.api")
    esg.approve_and_sign = lambda dt, name, comment=None: W.calls.append(("approve_and_sign", dt, name, comment)) or {"ok": 1}
    pkgs = ["ecentric_workspace", "ecentric_workspace.platform", "ecentric_workspace.platform.esign", "ecentric_workspace.approval_center", "ecentric_workspace.approval_center.shared",
            "ecentric_workspace.approval_center.shared.requests", "ecentric_workspace.approval_center.shared.workflow",
            "ecentric_workspace.approval_center.features", "ecentric_workspace.approval_center.features.leave",
            "ecentric_workspace.approval_center.features.leave.controllers",
            "ecentric_workspace.approval_center.features.payment_request",
            "ecentric_workspace.approval_center.features.payment_request.controllers"]
    for p in pkgs:
        sys.modules[p] = types.ModuleType(p)
    sys.modules["ecentric_workspace.approval_center.shared.requests"].capabilities = caps
    sys.modules["ecentric_workspace.approval_center.shared.workflow"].permissions = perm
    sys.modules.update({"frappe": fr, "frappe.utils": fu, reg.__name__: reg, caps.__name__: caps,
                        perm.__name__: perm, ctl.__name__: ctl, pay_ctl.__name__: pay_ctl,
                        esg.__name__: esg})
    sys.modules["ecentric_workspace.platform.esign"].api = esg
    spec = importlib.util.spec_from_file_location(
        "quick_approve_ut", APP / "approval_center/shared/requests/quick_approve.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m, W


# ------------------------------------------------------------------------------- list
def test_list_chi_dung_cap_hien_tai_khong_lo_phieu_nguoi_khac():
    m, W = build()
    out = m.list_my_pending("me@x")
    names = [r["request"] for r in out["rows"]]
    assert sorted(names) == ["R1", "R5"]           # R2 chua toi cap, R3 nguoi khac, R4 IR, R6 chua kich hoat
    assert out["count"] == 2
    other = m.list_my_pending("other@x")
    assert sorted(r["request"] for r in other["rows"]) == ["R2", "R3"]


def test_list_tom_tat_dinh_dang_va_khong_co_luong():
    m, W = build()
    r1 = next(r for r in m.list_my_pending("me@x")["rows"] if r["request"] == "R1")
    assert r1["summary"] == [{"label": "Loại nghỉ", "value": "Annual"}, {"label": "Số ngày", "value": "2"},
                             {"label": "Từ", "value": "08/10/2026"}]
    assert not any("99" in s["value"] for s in r1["summary"])        # luong khai nham -> van chan
    assert r1["detail_url"] == "/approvals/leave?id=LV-1" and r1["type_label"] == "Nghỉ phép"
    assert r1["requester_name"] == "Anh A" and r1["level_name"] == "Manager"
    assert r1["capabilities"]["can_approve"] and not r1["capabilities"]["needs_input"]


def test_list_phieu_ky_so_duyet_va_ky_ngay_tai_the():
    # 07/10 (Hoan chot "vao thang B"): cap ky so KHONG con bat mo trang chi tiet.
    m, W = build()
    r5 = next(r for r in m.list_my_pending("me@x")["rows"] if r["request"] == "R5")
    assert r5["capabilities"]["sign_required"] and not r5["capabilities"]["needs_input"]
    assert r5["sign_files"] == [{"dsf": "DSF-1", "file_name": "UNC-KOL-T9.pdf"}]
    assert r5["summary"] == [{"label": "Số tiền", "value": "12.500.000"}]
    r1 = next(r for r in m.list_my_pending("me@x")["rows"] if r["request"] == "R1")
    assert not r1["capabilities"]["sign_required"] and r1["sign_files"] == []


def test_duyet_ky_di_qua_chuc_nang_ky_chinh_thuc():
    m, W = build()
    m.quick_decide("R5", "approve_sign", "ok", user="me@x")
    assert W.calls == [("approve_and_sign", "EC Payment Request", "PAY-1", "ok")]


def test_cap_ky_khong_duyet_thuong_va_nguoc_lai():
    m, W = build()
    with pytest.raises(m.QuickDecideError, match="Duyệt & Ký"):
        m.quick_decide("R5", "approve", None, user="me@x")
    with pytest.raises(m.QuickDecideError, match="không yêu cầu ký số"):
        m.quick_decide("R1", "approve_sign", None, user="me@x")
    assert W.calls == []


# ----------------------------------------------------------------------------- decide
def test_duyet_di_qua_controller_cua_loai_phieu():
    m, W = build()
    out = m.quick_decide("R1", "approve", "ok", user="me@x")
    assert W.calls == [("approve", "LV-1", "ok")] and out["ok"]
    assert W.savepoints == ["ec_quick_decide"] and W.rollbacks == []


def test_tu_choi_bat_buoc_ly_do():
    m, W = build()
    with pytest.raises(m.QuickDecideError, match="lý do"):
        m.quick_decide("R1", "reject", "  ", user="me@x")
    assert W.calls == []
    m.quick_decide("R1", "request_info", "bo sung", user="me@x")
    assert W.calls == [("request_information", "LV-1", "bo sung")]


def test_khong_phai_luot_minh_thi_tu_choi_ro_ly_do():
    m, W = build()
    for req in ("R2", "R3"):
        with pytest.raises(m.QuickDecideError, match="không còn là người duyệt"):
            m.quick_decide(req, "approve", None, user="me@x")
    assert W.calls == []


def test_loi_nghiep_vu_thi_rollback_va_bao_nguyen_van():
    m, W = build(boom=ValidationError("Phiếu đang chờ bổ sung"))
    with pytest.raises(m.QuickDecideError, match="Phiếu đang chờ bổ sung"):
        m.quick_decide("R1", "approve", None, user="me@x")
    assert W.rollbacks == ["ec_quick_decide"]


def test_thieu_quyen_bao_loi_nghiep_vu_khong_phai_403():
    m, W = build(boom=PermissionError_("not allowed"))
    with pytest.raises(m.QuickDecideError) as ei:
        m.quick_decide("R1", "approve", None, user="me@x")
    assert "Không đủ quyền" in str(ei.value) and not isinstance(ei.value, PermissionError_)
    assert W.rollbacks == ["ec_quick_decide"]


def test_loi_khong_luong_truoc_cung_rollback():
    m, W = build(boom=RuntimeError("db"))
    with pytest.raises(m.QuickDecideError, match="hoàn tác"):
        m.quick_decide("R1", "approve", None, user="me@x")
    assert W.rollbacks == ["ec_quick_decide"] and W.logs


def test_bat_buoc_nhan_xet_khi_loai_phieu_yeu_cau():
    m, W = build()
    sys.modules["ecentric_workspace.approval_center.shared.registry"].get_definition("LEAVE").quick_comment_required = True
    with pytest.raises(m.QuickDecideError, match="nhận xét"):
        m.quick_decide("R1", "approve", "", user="me@x")
    assert W.calls == []
