# Copyright (c) 2026, eCentric and contributors
"""Tep da ky KHONG BAO GIO duoc xoa (Hoan, 08/09: "voi file da signed thi khong duoc phep xoa").

Ban ky (SIGNED-*.pdf, DSF.signed_file tro vao) la bang chung phap ly cua 5 chu ky - mat no la
mat chu ky, khong tai lai duoc neu SCTS khong con giu. Cac duong xoa File trong app deu da co
dieu kien rieng (remove_attachment chi Draft, package.remove_file khong xoa File dang duoc DSF
khac tro vao...), nhung mot dong lenh delete_doc("File") o Desk, mot cong cu don du lieu, hay
mot patch sau nay van xoa duoc. Chot mot cua duy nhat bang hook on_trash cua File: tep la ban
ky -> tu choi, ke ca Administrator. Cong cu QUAN TRI co ly do that (vd don du lieu test) phai
bat co `frappe.flags.ec_allow_signed_file_delete = True` NGAY TRUOC lenh xoa va ghi ro ly do -
co la trace, khong phai tien nghi.
"""
import frappe
from frappe import _

DSF = "EC Digital Signature File"
SIGNED_PREFIX = "SIGNED-"


def is_signed_file(doc):
    """Ban ky = DSF.signed_file tro vao, hoac ban dang cho doi chieu (signed_review_candidate,
    REVIEW-*), hoac ten bat dau bang SIGNED- (ban ghi tao boi signed_files._retrieve_one)."""
    if not doc or not getattr(doc, "name", None):
        return False
    if frappe.db.exists(DSF, {"signed_file": doc.name}):
        return True
    if frappe.db.has_column(DSF, "signed_review_candidate") \
            and frappe.db.exists(DSF, {"signed_review_candidate": doc.name}):
        return True
    return str(doc.get("file_name") or "").startswith(SIGNED_PREFIX)


def forbid_signed_file_delete(doc, method=None):
    """hooks.doc_events File.on_trash."""
    if getattr(frappe.flags, "ec_allow_signed_file_delete", False):
        frappe.log_error("%s (%s) xoa voi co ec_allow_signed_file_delete boi %s"
                         % (doc.name, doc.get("file_name"), frappe.session.user),
                         "esign signed file delete OVERRIDE")
        return
    if is_signed_file(doc):
        frappe.throw(_("Không được xoá tệp đã ký số ({0}) — đây là bằng chứng chữ ký. "
                       "Nếu thật sự cần, liên hệ kỹ thuật.").format(doc.get("file_name") or doc.name),
                     frappe.PermissionError)
