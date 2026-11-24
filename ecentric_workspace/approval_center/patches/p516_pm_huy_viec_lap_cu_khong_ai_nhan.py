# Copyright (c) 2026, eCentric and contributors
"""PO duyet 24/11/2026: huy 137 viec lap lai cu khong nguoi nhan, chua ai dung toi (ra soat PM 24/11:
hoang.le 119, lan.dinh 18). Chi huy viec CON dung dieu kien luc chay: Backlog / To Do, khong nguoi nhan.
Ghi Version (task_flow.write_state) + Comment Info tren tung viec. Khong xoa viec nao. Tu bat loi."""
import json

import frappe

NAMES = ['TASK-2026-01329', 'TASK-2026-01398', 'TASK-2026-01400', 'TASK-2026-01401', 'TASK-2026-01726', 'TASK-2026-01727', 'TASK-2026-01728', 'TASK-2026-01730', 'TASK-2026-01733', 'TASK-2026-01735', 'TASK-2026-01757', 'TASK-2026-01765', 'TASK-2026-01795', 'TASK-2026-01796', 'TASK-2026-01797', 'TASK-2026-01799', 'TASK-2026-01802', 'TASK-2026-01804', 'TASK-2026-01816', 'TASK-2026-01817', 'TASK-2026-01818', 'TASK-2026-01820', 'TASK-2026-01823', 'TASK-2026-01824', 'TASK-2026-01825', 'TASK-2026-01828', 'TASK-2026-01829', 'TASK-2026-01830', 'TASK-2026-01832', 'TASK-2026-01835', 'TASK-2026-01836', 'TASK-2026-01837', 'TASK-2026-01840', 'TASK-2026-01841', 'TASK-2026-01842', 'TASK-2026-01844', 'TASK-2026-01847', 'TASK-2026-01848', 'TASK-2026-01850', 'TASK-2026-01865', 'TASK-2026-01866', 'TASK-2026-01867', 'TASK-2026-01869', 'TASK-2026-01872', 'TASK-2026-01873', 'TASK-2026-01874', 'TASK-2026-01877', 'TASK-2026-01878', 'TASK-2026-01879', 'TASK-2026-01881', 'TASK-2026-01884', 'TASK-2026-01885', 'TASK-2026-01886', 'TASK-2026-01892', 'TASK-2026-01893', 'TASK-2026-01894', 'TASK-2026-01896', 'TASK-2026-01899', 'TASK-2026-01900', 'TASK-2026-01901', 'TASK-2026-01904', 'TASK-2026-01905', 'TASK-2026-01906', 'TASK-2026-01908', 'TASK-2026-01911', 'TASK-2026-01912', 'TASK-2026-01913', 'TASK-2026-01916', 'TASK-2026-01917', 'TASK-2026-01918', 'TASK-2026-01920', 'TASK-2026-01923', 'TASK-2026-01924', 'TASK-2026-01925', 'TASK-2026-01928', 'TASK-2026-01929', 'TASK-2026-01930', 'TASK-2026-01932', 'TASK-2026-01935', 'TASK-2026-01936', 'TASK-2026-01937', 'TASK-2026-01940', 'TASK-2026-01941', 'TASK-2026-01942', 'TASK-2026-01944', 'TASK-2026-01947', 'TASK-2026-01948', 'TASK-2026-01950', 'TASK-2026-01956', 'TASK-2026-01957', 'TASK-2026-01958', 'TASK-2026-01960', 'TASK-2026-01963', 'TASK-2026-01964', 'TASK-2026-01965', 'TASK-2026-01972', 'TASK-2026-01973', 'TASK-2026-01974', 'TASK-2026-01976', 'TASK-2026-01979', 'TASK-2026-01980', 'TASK-2026-01981', 'TASK-2026-01989', 'TASK-2026-01990', 'TASK-2026-01991', 'TASK-2026-01993', 'TASK-2026-02004', 'TASK-2026-02005', 'TASK-2026-02006', 'TASK-2026-02016', 'TASK-2026-02017', 'TASK-2026-02018', 'TASK-2026-02027', 'TASK-2026-02030', 'TASK-2026-02031', 'TASK-2026-02032', 'TASK-2026-02054', 'TASK-2026-02055', 'TASK-2026-02056', 'TASK-2026-02058', 'TASK-2026-02068', 'TASK-2026-02069', 'TASK-2026-02070', 'TASK-2026-02073', 'TASK-2026-02074', 'TASK-2026-02075', 'TASK-2026-02077', 'TASK-2026-02080', 'TASK-2026-02081', 'TASK-2026-02082', 'TASK-2026-02089', 'TASK-2026-02090', 'TASK-2026-02091', 'TASK-2026-02093', 'TASK-2026-02096', 'TASK-2026-02097', 'TASK-2026-02099']
NOTE = "Tự huỷ (PO duyệt 24/11/2026): việc lặp lại cũ không ai nhận, chưa ai làm."


def execute():
    from ecentric_workspace.pm import task_flow as tflow
    done = 0
    for name in NAMES:
        try:
            row = frappe.db.get_value("Task", name, ["workflow_state", "_assign"], as_dict=True)
            if not row or row.get("workflow_state") not in ("Backlog", "To Do"):
                continue
            if [u for u in json.loads(row.get("_assign") or "[]") if u]:
                continue
            tflow.write_state(name, "Cancelled", "Administrator", notify=False)
            frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Task",
                            "reference_name": name, "content": NOTE}).insert(ignore_permissions=True)
            done += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p516_pm_huy_viec_lap_cu_khong_ai_nhan " + str(name))
    frappe.logger("approval_center").info("p516_pm_huy_viec_lap_cu_khong_ai_nhan: huy %s/%s viec" % (done, len(NAMES)))
