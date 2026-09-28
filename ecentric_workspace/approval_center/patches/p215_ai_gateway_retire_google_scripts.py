# Copyright (c) 2026, eCentric and contributors
"""p215_ai_gateway_retire_google_scripts: tat Server Script lich `auto_company_summary_weekly`.

28/09/2026 - moi tinh nang AI di qua cong AI chung (platform/ai). Script nay chay 12:00 thu
Hai va goi THANG Google 2.5 bang ec_gemini_api_key; viec cua no nay do
`platform.ai.company_summary.weekly_job` lam (hooks.py, 12:10 thu Hai). De ca hai chay thi
cung mot ban ghi Company Weekly Summary bi ghi hai lan, lan cua script qua Google - dung cai
Hoan chot bo.

Hai Server Script API `gemini_chat` va `gemini_company_summary` KHONG can tat: hooks.py
override hai ten do, Frappe xet override truoc Server Script nen chung khong con chay. De
nguyen cho de doi chieu; don cung dot voi 11 script *_backup_* sau.

Chi TAT (disabled=1), khong xoa: bat lai la mot o tick.
"""
import frappe

SCRIPTS = ("auto_company_summary_weekly",)


def execute():
    if not frappe.db.exists("DocType", "Server Script"):
        return
    for name in SCRIPTS:
        if not frappe.db.exists("Server Script", name):
            continue
        # doc.save chu khong phai db.set_value: on_update cua Server Script dong bo lai
        # Scheduled Job Type. set_value bo qua hook -> script tat ma lich VAN chay.
        doc = frappe.get_doc("Server Script", name)
        if not doc.disabled:
            doc.disabled = 1
            doc.save(ignore_permissions=True)
        # Chac an: dung han moi Scheduled Job Type tro vao script nay, du hook o ban
        # Frappe nay co dong bo hay khong.
        for job in frappe.get_all("Scheduled Job Type", filters={"server_script": name},
                                  pluck="name"):
            frappe.db.set_value("Scheduled Job Type", job, "stopped", 1)
