# Copyright (c) 2026, eCentric and contributors
"""p541: tao bu Clearance cho 5 Don nghi viec da duyet tu thang 9-10 ma chua co Clearance, va
HOAN TAT luon - KHONG gui thong bao (Hoan chot 24/11/2026: "a nhe" = tao im lang).

Vi sao im lang: nhan vien da nghi + da khoa tai khoan tu lau; ban giao da lam xong ngoai he thong.
Tao bang duong thuong (tao_bu_clearance) se ban Teams / chuong / ToDo toi ~20 nguoi duyet cho
viec da xong. Patch nay chi bo sung ho so cho day du lich su.

PHAM VI: 5 ten go tay ben duoi. KHONG co EC-RESN-2026-00002 (nhan vien van di lam - cho PO quyet).
Moi don: tao Clearance bang DUNG ham cua feature (create_from_resignation), roi "Duyet thay" tung cap
bang DUNG ham engine (admin_override_current_level, actor Administrator, co ly do) - de lai dau vet
day du trong EC Approval Action. Thong bao bi tat bang cach thay tam publish_notification_event +
mute_emails TRONG LUC patch chay, tra lai nguyen trang trong finally. ToDo con mo cua Clearance
nay dong lai (Closed, khong xoa). Don da co Clearance da gui -> bo qua. Idempotent."""
import frappe

DON = [
    "EC-RESN-2026-00003",
    "EC-RESN-2026-00004",
    "EC-RESN-2026-00005",
    "EC-RESN-2026-00006",
    "EC-RESN-2026-00008",
]
LY_DO = ("Tạo bù sau khi nhân viên đã nghỉ (PO duyệt 24/11/2026). Bàn giao đã hoàn tất ngoài hệ "
         "thống; ghi nhận để đủ lịch sử, không gửi thông báo.")
BUSINESS_DT = "EC Clearance Request"


def execute():
    from ecentric_workspace.notification_center import events as ncev
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    from ecentric_workspace.approval_center.features.clearance_request.application import service

    goc_pub = ncev.publish_notification_event
    goc_mute = frappe.flags.mute_emails
    ncev.publish_notification_event = lambda *a, **k: None
    frappe.flags.mute_emails = True
    ket = []
    try:
        for don in DON:
            ket.append("%s: %s" % (don, _mot_don(don, service, engine)))
    finally:
        ncev.publish_notification_event = goc_pub
        frappe.flags.mute_emails = goc_mute
    print("[p541] " + " | ".join(ket))


def _mot_don(don, service, engine):
    if not frappe.db.exists("EC Resignation Request", don):
        return "khong co don"
    if frappe.db.get_value("EC Resignation Request", don, "withdrawn_at"):
        return "don da rut - bo qua"
    clr = frappe.db.get_value(BUSINESS_DT, {"resignation_request": don}, ["name", "approval_request"],
                              as_dict=True)
    if not (clr and clr.approval_request):
        name = service.create_from_resignation(don)
        if not name:
            return "LOI tao (xem Error Log / clearance_error tren don)"
        clr = frappe.db.get_value(BUSINESS_DT, name, ["name", "approval_request"], as_dict=True)
    req = clr.approval_request
    for _i in range(10):
        if frappe.db.get_value("EC Approval Request", req, "approval_status") != "Pending":
            break
        engine.admin_override_current_level(req, actor="Administrator", reason=LY_DO)
        frappe.db.commit()
    st = frappe.db.get_value("EC Approval Request", req, "approval_status")
    for dt, n in ((BUSINESS_DT, clr.name), ("EC Approval Request", req)):
        for td in frappe.get_all("ToDo", filters={"reference_type": dt, "reference_name": n,
                                                  "status": "Open"}, pluck="name"):
            frappe.db.set_value("ToDo", td, "status", "Closed", update_modified=False)
    frappe.db.commit()
    return "%s %s" % (clr.name, st)
