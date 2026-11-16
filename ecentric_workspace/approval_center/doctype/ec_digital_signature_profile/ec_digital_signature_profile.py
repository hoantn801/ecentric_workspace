# Copyright (c) 2026, eCentric and contributors
"""Per-form signing enablement + provider targets + level/field/transition maps.
Generic layer: enabling a new form = a new profile row, zero provider-specific code."""
import frappe
from frappe import _
from frappe.model.document import Document


def _is_value_field(meta, field):
    """Truong co COT trong bang (doc duoc bang db.get_value)."""
    df = meta.get_field(field)
    if not df or df.get("is_virtual"):
        return False
    from frappe.model import data_fieldtypes
    return df.fieldtype in data_fieldtypes


class ECDigitalSignatureProfile(Document):
    def validate(self):
        # Duplicate Selected Level Override rows are always rejected.
        seen = set()
        for row in (self.levels or []):
            if row.level_no in seen:
                frappe.throw(_("Duplicate signing level {0} in profile.").format(row.level_no))
            seen.add(row.level_no)
        # An ENABLED profile must have a governed signing actor consistent with its policy.
        self._validate_portal_approve_levels()
        if self.enabled:
            self._validate_enabled_signing_actor()
            self._validate_selector()
        # Deadline rules (unchanged).
        if self.deadline_rule == "Fixed Days" and not (self.deadline_days or 0) > 0:
            frappe.throw(_("deadline_days required for Fixed Days rule."))
        if self.deadline_rule == "From Field" and not (self.deadline_source or "").strip():
            frappe.throw(_("deadline_source required for From Field rule."))

    def _validate_portal_approve_levels(self):
        """Dong cap 'Approve' (duyet KHONG KY tren cong, 12/11/2026) chi co nghia khi:
          * cap do KHONG ky (requires_signature = 0) - ky thi la buoc ky;
          * chinh sach la 'Selected Approval Levels' - 'All' / 'Final' bat ky theo cap, de
            dong Approve bi lan im lang;
          * ho so bat 'Lay buoc tu cong' - buoc khong ky khong dem duoc bang chu ky."""
        rows = [r for r in (self.levels or []) if (r.get("provider_action") or "") == "Approve"]
        if int(self.get("trust_portal_transitions") or 0):
            self._validate_trusted_steps()
        if not rows:
            return
        for r in rows:
            if int(r.get("requires_signature") or 0):
                frappe.throw(_("Cấp {0}: 'Bước trên cổng' = Approve (duyệt không ký) thì phải "
                               "bỏ chọn 'Requires Signature'.").format(r.level_no))
        if (self.approver_signature_policy or "Selected Approval Levels") != \
                "Selected Approval Levels":
            frappe.throw(_("Có cấp 'Approve' (duyệt không ký) thì Approver Signature Policy phải "
                           "là 'Selected Approval Levels'."))
        if not int(self.get("trust_portal_transitions") or 0):
            frappe.throw(_("Có cấp 'Approve' (duyệt không ký) thì phải bật 'Lấy bước từ cổng'."))
        for r in rows:
            stage = "level:%s" % int(r.level_no or 0)
            steps = [t for t in (self.transitions or [])
                     if t.action == "Forward" and (t.stage or "").strip() == stage
                     and t.transition_id not in (None, 0)]
            if len(steps) != 1:
                frappe.throw(_("Cấp {0} (Approve) cần ĐÚNG MỘT dòng Transitions: Action = "
                               "Forward, Stage = '{1}', có Transition Id (vd WF09: -3 / -4).")
                             .format(r.level_no, stage))

    def _validate_trusted_steps(self):
        """'Lay buoc tu cong' (QC 12/11): moi buoc ERP gui di phai khai san - thieu thi chan ky dung
        luc chay (no_step_config). Ky nguoi de nghi kieu DNTT + buoc nguoi lap kieu cong = hai chan
        nguoi lap tranh nhau mot buoc -> cam."""
        if int(self.requester_signature_required or 0):
            frappe.throw(_("'Lấy bước từ cổng' không đi cùng 'Requester Signature Required' - "
                           "người lập trình trên cổng bằng bước Forward / stage 'requester'."))
        if (self.approver_signature_policy or "Selected Approval Levels") != \
                "Selected Approval Levels":
            # 'All' / 'Final' bat ky theo cap luc chay - khong khai buoc cong tung cap duoc.
            frappe.throw(_("'Lấy bước từ cổng' cần Approver Signature Policy = 'Selected "
                           "Approval Levels' (khai từng cấp)."))
        def one(action, stage):
            return len([t for t in (self.transitions or []) if t.action == action
                        and (t.stage or "").strip() == stage
                        and t.transition_id not in (None, 0)]) == 1
        if not one("Forward", "requester"):
            frappe.throw(_("'Lấy bước từ cổng' cần ĐÚNG MỘT dòng Transitions: Action = Forward, "
                           "Stage = 'requester' (bước người lập trình, vd WF09: -2)."))
        for r in (self.levels or []):
            if int(r.get("requires_signature") or 0) and not one("Sign", "level:%s"
                                                                  % int(r.level_no or 0)):
                frappe.throw(_("Cấp {0} (ký) cần ĐÚNG MỘT dòng Transitions: Action = Sign, "
                               "Stage = 'level:{0}'.").format(r.level_no))

    def _validate_selector(self):
        """Nhieu ho so DANG BAT cho cung (doctype, loai yeu cau) phai phan biet duoc theo phieu
        (12/11/2026, hop dong: moi quy trinh tren cong mot ho so). Bat loi CAU HINH ngay luc luu,
        khong de toi luc nguoi dung bam Gui moi gap "khong chon duoc ho so"."""
        field = (self.selector_field or "").strip()
        value = (self.selector_value or "").strip()
        # Ghi lai ban da cat khoang trang: luc chay so CHINH XAC tung ky tu (QC 12/11 - "kol_wf09 "
        # qua duoc buoc luu roi khong bao gio khop).
        self.selector_field, self.selector_value = field or None, value or None
        if field and not _is_value_field(frappe.get_meta(self.business_doctype), field):
            # Sai ten truong / truong khong co cot (Table, HTML, ao...) = luc chay doc ra rong =
            # moi phieu "khong ky so", im lang (QC 12/11).
            frappe.throw(_("Loại chứng từ {0} không có trường dữ liệu '{1}'.").format(
                self.business_doctype, field))
        if field and not value:
            frappe.throw(_("Đã khai 'Trường chọn hồ sơ' thì phải khai 'Giá trị chọn'."))
        if value and not field:
            frappe.throw(_("'Giá trị chọn' cần đi kèm 'Trường chọn hồ sơ'."))
        others = frappe.get_all(
            "EC Digital Signature Profile",
            filters={"business_doctype": self.business_doctype,
                     "approval_type": self.approval_type, "enabled": 1,
                     "name": ["!=", self.name or ""]},
            fields=["name", "selector_field", "selector_value"])
        for o in others:
            other_field = (o.selector_field or "").strip()
            if field and other_field and other_field != field:
                # Hai truong chon khac nhau cung khop mot phieu thi khong chon duoc (QC 12/11).
                frappe.throw(_("Hồ sơ {0} đang bật cùng loại chứng từ nhưng chọn theo trường "
                               "'{1}' - mọi hồ sơ cùng loại phải chọn theo CÙNG một trường.")
                             .format(o.name, other_field))
            if (other_field == field
                    and (o.selector_value or "").strip() == value):
                frappe.throw(_("Hồ sơ {0} đang bật cùng loại chứng từ, cùng trường chọn và cùng "
                               "giá trị chọn - ERP sẽ không chọn được hồ sơ nào cho phiếu. Đổi "
                               "giá trị chọn hoặc tắt một hồ sơ.").format(o.name))

    def _validate_enabled_signing_actor(self):
        """Policy-aware signing-actor validation (replaces the legacy 'needs at least one
        requires_signature level' rule which contradicted the policy model).
          * All Approval Levels / Final Approval Level Only -> valid with ZERO override rows;
          * Selected Approval Levels (and legacy blank/unset -> Selected) -> require >= 1
            override row with requires_signature = 1;
          * None -> valid only when a requester signature is required (otherwise the enabled
            profile has no signing actor at all).
        A disabled profile skips this entirely.
        """
        # Legacy blank/unset policy keeps the old behaviour = Selected Approval Levels.
        policy = self.approver_signature_policy or "Selected Approval Levels"
        requester = bool(self.requester_signature_required)
        has_signing_level = any(r.requires_signature for r in (self.levels or []))
        if policy == "Selected Approval Levels":
            if not has_signing_level:
                frappe.throw(_(
                    "Approver Signature Policy 'Selected Approval Levels' needs at least one "
                    "Selected Level Override row with requires_signature."))
        elif policy == "None":
            if not requester:
                frappe.throw(_(
                    "An enabled profile with Approver Signature Policy 'None' must require a "
                    "requester signature - otherwise it has no signing actor."))
        # All Approval Levels / Final Approval Level Only: valid with zero override rows;
        # a requester signature is optional and independently configured.
