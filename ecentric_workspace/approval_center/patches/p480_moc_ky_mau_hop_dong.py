# Copyright (c) 2026, eCentric and contributors
"""23/11/2026: chen moc o ky [[KY_BEN_A]] (eCentric) / [[KY_BEN_B]] (creator) vao mau Word hop dong +
BBNT KOL (EC Contract Template) - ban giao chat Ky so 23/11, B3; chot 18/11 (THIETKE_ky_so_hop_dong 2e).

Moi mau .docx: domain/sign_anchors.add_markers (chu trang 1pt ngay tren dong ten nguoi ky, lui vao giua
cot). Doi tep that su thi:
  * tao File MOI (rieng tu, gan mau), tro template_file sang tep moi, version + 1;
  * GIU tep cu (ban sao luu) va ghi duong dan vao Ghi chu cua mau -> khoi phuc = tro template_file ve.
Hop dong da sinh KHONG doi; phieu nhap tao lai tu mau thi co moc (dau van tay doi theo tep mau).
Idempotent: mau da co moc -> bo qua. Khong nhan ra bo cuc chu ky -> bo qua + Error Log (Ke toan /
nguoi lap van keo o ky tay duoc). Loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

TPL = "EC Contract Template"


def _new_name(old_name):
    base = (old_name or "mau.docx").rsplit(".", 1)[0]
    return "%s_moc-ky.docx" % base[:120]


def execute():
    if not frappe.db.exists("DocType", TPL):
        return
    from ecentric_workspace.approval_center.features.contract_review.domain import sign_anchors
    from ecentric_workspace.approval_center.features.contract_review.application.kol_files import file_bytes
    report = {"added": [], "already": [], "skipped": []}
    for t in frappe.get_all(TPL, fields=["name", "template_file", "version", "notes"]):
        try:
            url = t.template_file or ""
            if not url.lower().endswith(".docx"):
                report["skipped"].append("%s: không phải .docx" % t.name)
                continue
            new, rep = sign_anchors.add_markers(file_bytes(url))
            if rep["status"] == "already":
                report["already"].append(t.name)
                continue
            if rep["status"] != "added":
                report["skipped"].append("%s: %s" % (t.name, rep["status"]))
                continue
            old_name = frappe.db.get_value("File", {"file_url": url}, "file_name")
            f = frappe.get_doc({"doctype": "File", "file_name": _new_name(old_name), "content": new,
                                "is_private": 1, "attached_to_doctype": TPL, "attached_to_name": t.name,
                                "attached_to_field": "template_file"})
            f.flags.ignore_permissions = True
            f.insert(ignore_permissions=True)
            note = ("23/11/2026 p480: thêm mốc ký [[KY_BEN_A]]/[[KY_BEN_B]] (%s). Bản trước: %s"
                    % (rep.get("how"), url))
            frappe.db.set_value(TPL, t.name, {
                "template_file": f.file_url, "version": int(t.version or 1) + 1,
                "notes": ((t.notes or "").rstrip() + "\n" + note).strip()})
            report["added"].append(t.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p480 moc ky %s" % t.name)
    frappe.logger("approval_center").info("p480 moc ky mau: %s" % report)
    if report["skipped"]:
        frappe.log_error(title="p480 moc ky - mau bo qua", message="\n".join(report["skipped"]))
