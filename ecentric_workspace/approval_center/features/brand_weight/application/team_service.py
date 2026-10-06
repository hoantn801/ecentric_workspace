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
from ecentric_workspace.approval_center.features.brand_weight.application import service
from ecentric_workspace.approval_center.features.brand_weight.application.routing import (
    is_self_final, proxy_rule,
)
from ecentric_workspace.approval_center.features.brand_weight.application.period_service import check_period
from ecentric_workspace.approval_center.features.brand_weight.application.weights import (
    diff_text, parse_weights, prev_period, same,
)
from ecentric_workspace.approval_center.features.brand_weight.domain.status import stage_of_level, status_of
from ecentric_workspace.approval_center.features.brand_weight.infrastructure import (
    brand_weight_repository as repo, employee_reader,
)


def _payload(r, employee, period):
    name = r.find_doc(employee, period)
    return r.payload(name) if name else None


class _Proxy:
    """ec-bw-proxy-v1: ai duoc nop thay ai. Doc lead / truong phong mot lan cho moi nguoi."""

    def __init__(self, reader=employee_reader, head_resolver=None):
        self.reader = reader
        self.head_resolver = head_resolver or engine.resolve_department_manager_user
        self._heads = {}

    def head(self, dept):
        if dept not in self._heads:
            self._heads[dept] = self.head_resolver(dept)
        return self._heads[dept]

    def check(self, actor, m, status):
        return proxy_rule(actor, m.user_id, self.reader.lead_user(m.name), self.head(m.department),
                          status, is_self_final(m.department))


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
        proxy = _Proxy()
        for m in members:
            cur = _payload(self.r, m.name, period)
            actionable = bool(cur and cur["name"] in pending)
            if me and m.name == me.name and not actionable:
                continue
            last = _payload(self.r, m.name, prev_period(period))
            can_proxy, _why, proxy_final = (False, "", False) if actionable else proxy.check(user, m, status_of(cur))
            rows.append({
                "can_proxy": can_proxy, "proxy_final": proxy_final,
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


class ProxySubmitService:
    """ec-bw-proxy-v1 (Hoan 06/10): lead dien va nop thay cho nguoi chua nop.

    Nop thay = tao phieu cho nhan vien (requester la nhan vien) + duyet ngay buoc cua chinh
    nguoi nop thay, trong CUNG transaction (api._run rollback neu buoc nao loi). Lead cung la
    truong phong thi phieu chot luon; con khong thi chuyen truong phong chot nhu thuong.
    Nhan vien nhan thong bao; phieu ghi binh luan ai nop thay; submitted_at la luc nop thay
    nen tre han van la tre han."""

    def __init__(self, r=repo, proxy=None):
        self.r = r
        self.proxy = proxy or _Proxy()

    def execute(self, actor, employee, period, raw_weights):
        check_period(period)
        weights = parse_weights(raw_weights)
        inactive = sorted(set(weights) - self.r.active_brand_ids())
        if inactive:
            frappe.throw(_("Brand không còn hoạt động: {0}.").format(", ".join(inactive)))
        emp = self.r.employee_row(employee)
        if not emp:
            frappe.throw(_("Không tìm thấy nhân viên đang làm việc này."))
        name = self.r.find_doc(emp.name, period)
        cur = self.r.payload(name) if name else None
        ok, why, _final = self.proxy.check(actor, emp, status_of(cur))
        if not ok:
            frappe.throw(why)
        target = name or self.r.create_doc(emp, period, emp.user_id)
        name = self.r.write_weights(target, weights, "submit")
        req = service.submit_on_behalf(name, actor)
        pending = self.r.pending_for(actor)
        if name not in pending:
            frappe.throw(_("Không nộp thay được: phiếu không chuyển tới bạn duyệt. Tải lại trang rồi thử lại."))
        stage = stage_of_level(pending[name])
        self.r.write_weights(name, weights, stage)
        engine.approve(req, actor=actor, comment="Nộp thay cho nhân viên chưa nộp")
        final = status_of(self.r.payload(name)) == "final"
        who = self.r.full_name(actor) or actor
        self.r.notify(emp.user_id, actor, name,
                      "%s đã nộp thay phiếu phân bổ công việc kỳ %s của bạn" % (who, period),
                      "Phiếu đã " + ("được chốt." if final else "chuyển trưởng phòng chốt."))
        return {"name": name, "final": final}
