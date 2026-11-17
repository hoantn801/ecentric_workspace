# Copyright (c) 2026, eCentric and contributors
"""Day tin Teams "may cho duyet" / "nghi nhan ban" ra hang doi nen - API cho app KHONG cho goi mang (app chi doi ~10 s).
Service goi SAU commit; hang doi loi (Redis tat) thi bo qua: tin bao la phu, khong duoc lam hong license_request."""

JOB = "ecentric_workspace.ai_tools.features.ai_live.jobs.license_notify_job.run"


class LicenseNotifyQueue:
    def enqueue(self, kind, machine):
        import frappe
        try:
            frappe.enqueue(JOB, queue="short", timeout=120, kind=kind, machine=machine)
        except Exception:
            frappe.log_error(title="ai_live license notify enqueue")
