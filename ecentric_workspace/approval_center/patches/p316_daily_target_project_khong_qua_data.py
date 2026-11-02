# Copyright (c) 2026, eCentric and contributors
"""Daily Target cap Project: duyet xong la xong, KHONG qua buoc "Data xu ly" (02/11/2026, Hoan).

VI SAO. Ca hai process (PROJECT + CONSOLIDATED) deu co Fulfiller = Role EC Data Team (p244), nen
moi phieu project (chi Linh Ngo duyet) cung day sang team Data - linh.vuong nhan ToDo + Teams cho
ca chuc phieu/ngay ma Data khong lam gi voi chung. Hoan chot: Data CHI nhan Consolidated / Total.

HAI VIEC (ca hai Hoan da chon trong chat 02/11):
  1. Go dong Fulfiller khoi DAILY_TARGET_PROJECT-V1 (frappe.db.delete tren bang con, KHONG
     proc.save - p242 da hong vi validate process khi save, xem p244). Ghi lai dong da go vao
     Error Log de dung lai duoc neu can.
  2. Phieu Project level dang mo o buoc Data (Assigned / In Progress): dong ToDo xu ly, dua
     fulfillment_status ve "Not Started" (giong phieu project moi tu nay - trang an khoi Data),
     bo fulfillment_owner, ghi MOT dong lich su "System Transition" ke ca nguoi da nhan.
     KHONG gui thong bao (khong ai phai lam gi them).
Idempotent: chay lai khong con gi de lam. KHONG BAO GIO nem loi (exception lam chet deploy, p116).
"""
import frappe

PROC = "DAILY_TARGET_PROJECT-V1"
BDT = "EC Daily Target Request"
PART = "EC Approval Participant"
LY_DO = "Bỏ bước Data xử lý cho Daily Target cấp Project (Hoàn chốt 02/11/2026 - chỉ Consolidated / Total qua Data)"


def execute():
    ket = []
    try:
        rows = frappe.get_all(PART, filters={"parenttype": "EC Approval Process", "parent": PROC,
                                             "participant_purpose": "Fulfiller"},
                              fields=["name", "source_type", "role", "user", "sort_order"])
        if rows:
            frappe.db.delete(PART, {"name": ["in", [r.name for r in rows]]})
            ket.append("go Fulfiller khoi %s: %s" % (PROC, rows))
        else:
            ket.append("%s khong con Fulfiller" % PROC)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p316 go fulfiller")
    try:
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        mo = frappe.get_all(BDT, filters={"request_scope": "Project level",
                                          "fulfillment_status": ["in", ["Assigned", "In Progress"]]},
                            fields=["name", "approval_request", "fulfillment_status", "fulfillment_owner"])
        for d in mo:
            try:
                engine.close_fulfillment_todos(BDT, d.name)
                frappe.db.set_value(BDT, d.name, {"fulfillment_status": "Not Started",
                                                  "fulfillment_owner": None}, update_modified=False)
                if d.approval_request:
                    ghi = LY_DO + (" - đã nhận: %s" % d.fulfillment_owner if d.fulfillment_owner else "")
                    engine.log_action(d.approval_request, "System Transition", "Administrator",
                                      comment=ghi)
                ket.append("%s (%s, %s) -> Not Started" % (d.name, d.fulfillment_status,
                                                          d.fulfillment_owner or "-"))
            except Exception:
                frappe.log_error(frappe.get_traceback(), "p316 dong buoc Data %s" % d.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p316 dong buoc Data")
    frappe.log_error("\n".join(ket) or "khong co gi", "p316 daily target project khong qua Data")
