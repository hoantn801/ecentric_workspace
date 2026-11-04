"""p031 - close "Cần đồng ý" requests left open on tasks that are already Done/Cancelled (04/11/2026).

Before this fix a state write never closed them, so they kept showing in the recipient's
"Cần bạn trả lời" + badge and Nhận việc failed (live 04/11: 29 of 48 open requests, 10 people).
From now on task_flow.write_state + the Task on_update hook close them. Idempotent (only OPEN
requests on terminal tasks are touched); each close leaves a Withdrawn event; logs, never raises."""

import frappe


def execute():
    try:
        from ecentric_workspace.pm import permissions as pmperm
        from ecentric_workspace.pm.api import assignment as pmasg
        rows = frappe.get_all(pmasg.DT, filters={"status": ["in", list(pmasg.OPEN_STATUSES)]},
                              fields=["task", "kind"], limit_page_length=0)
        tasks = sorted({r["task"] for r in rows if (r.get("kind") or "Assignment") != "Deadline"})
        if not tasks:
            print("[p031] no open assignment requests")
            return
        done = [t["name"] for t in frappe.get_all("Task", filters={"name": ["in", tasks]},
                                                  fields=["name", "workflow_state", "status"],
                                                  limit_page_length=0)
                if pmperm.is_task_terminal(t)]
        n = 0
        for t in done:
            n += pmasg.close_open_requests_on_terminal(
                t, "Tự đóng (dọn dữ liệu 04/11/2026): việc đã xong hoặc đã huỷ.")
        print("[p031] closed %d open requests on %d finished tasks" % (n, len(done)))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p031 close requests on finished tasks")
