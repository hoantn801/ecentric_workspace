# Copyright (c) 2026, eCentric and contributors
"""Man duyet cua lead / truong phong: bang ca phong + chinh va duyet tung phieu.

`actionable` doc tu chinh bang nguoi duyet cua engine (dong Pending o DUNG cap hien tai),
khong suy ra tu cay to chuc: co luat bo cap (routing.py), nen 'lead cua nguoi nop' chua
chac la nguoi dang phai bam. Suy tu cay la cach ma don nghi phep tung hien nut duyet cho
nguoi bam vao se bi tu choi.

Ghi ty trong TRUOC roi moi goi engine.approve trong cung transaction: engine kiem nguoi
bam co phai nguoi duyet dung cap khong (co khoa hang). Neu khong phai, engine nem loi va
ca transaction rollback - so vua ghi khong bao gio duoc luu. Van kiem `pending_for` truoc
de tra loi than thien va khong ghi gi khi biet chac la khong duoc phep."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.workflow import transitions as engine
from ecentric_workspace.approval_center.features.brand_weight.application.period_service import check_period
from ecentric_workspace.approval_center.features.brand_weight.application.weights import (
    diff_text, parse_weights, prev_period, same,
)
from ecentric_workspace.approval_center.features.brand_weight.domain.status import stage_of_level, status_of
from ecentric_workspace.approval_center.features.brand_weight.infrastructure import (
    brand_weight_repository as repo,
)


def _payload(r, employee, period):
    name = r.find_doc(employee, period)
    return r.payload(name) if name else None


class GetTeamPeriodService:
    def __init__(self, r=repo):
        self.r = r

    def execute(self, user, period):
        check_period(period)
        me = self.r.employee_of(user)
        pending = self.r.pending_for(user)
        members = self.r.team_employees(user, me and me.name)
        known = {m.name for m in members}
        # Phieu dang cho minh nhung nguoi nop nam ngoai pham vi (vd CEO tu xac nhan) van phai hien.
        owners = [self.r.doc_owner(d) for d in pending]
        extra = {o.employee for o in owners if o and o.period == period} - known
        members += self.r.employees_by_name(extra)
        rows = []
        for m in members:
            cur = _payload(self.r, m.name, period)
            actionable = bool(cur and cur["name"] in pending)
            if me and m.name == me.name and not actionable:
                continue
            last = _payload(self.r, m.name, prev_period(period))
            rows.append({
                "id": m.name, "name": m.employee_name, "department": m.department,
                "doc": cur and cur["name"], "status": status_of(cur), "actionable": actionable,
                "stage": stage_of_level(pending[cur["name"]]) if actionable else None,
                "proposed": cur["proposed"] if cur else {}, "lead": cur["lead"] if cur else {},
                "current": cur["weights"] if cur else {}, "last": last["weights"] if last else {},
            })
        return {"period": period, "members": rows, "brands": self.r.active_brands()}


class DecideWeightsService:
    def __init__(self, r=repo):
        self.r = r

    def execute(self, user, name, action, raw_weights=None, note=None):
        pending = self.r.pending_for(user)
        if name not in pending:
            frappe.throw(_("Phiếu này không còn chờ bạn duyệt. Tải lại trang để xem trạng thái mới."))
        p = self.r.payload(name)
        if action == "return":
            if not (note or "").strip():
                frappe.throw(_("Ghi lý do trả lại để người nộp biết cần sửa gì."))
            engine.request_information(p["request"], actor=user, comment=note.strip())
            return {"action": "return"}
        if action != "approve":
            frappe.throw(_("Thao tác không hợp lệ."))
        stage = stage_of_level(pending[name])
        weights = parse_weights(raw_weights) if raw_weights else p["weights"]
        inactive = sorted(set(weights) - self.r.active_brand_ids())
        if inactive:
            frappe.throw(_("Brand không còn hoạt động: {0}.").format(", ".join(inactive)))
        if stage == "lead" or not same(weights, p["weights"]):
            self.r.write_weights(name, weights, stage)
        changed = diff_text(p["weights"], weights)
        engine.approve(p["request"], actor=user, comment=("Chỉnh tỷ trọng: " + changed) if changed else None)
        return {"action": "approve", "stage": stage, "changed": bool(changed)}
