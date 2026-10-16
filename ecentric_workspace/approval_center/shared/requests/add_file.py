# Copyright (c) 2026, eCentric and contributors
"""Nut "Them tep" o buoc duyet cho moi form phe duyet (16/10/2026, Hoan).

Vi du that: Finance cap 1 soan hop dong roi dinh kem vao phieu de Finance cap 2 xem tiep.

Ai bam duoc: NGUOI DANG GIU PHIEU luc bam - khong ai khac.
  * phieu "Pending" -> nguoi co dong duyet Pending CON HIEU LUC o CAP HIEN TAI (dong kieu
    "Role: X" chi tinh khi nguoi do van giu role X - cung luat `transitions._actor_pending_row`
    ma Duyet / Tu choi / Yeu cau bo sung dung);
  * phieu da duyet, dang o buoc xu ly (fulfillment Assigned / In Progress) -> CHI
    `fulfillment_owner` (nguoi da nhan xu ly).
  * "Information Required" -> bong o san nguoi gui; nguoi gui da co duong sua + gui lai rieng.
  Nguoi duyet cap khac, nguoi gui, quan tri khong giu phieu: khong.

CHI THEM, KHONG XOA (audit). Moi lan them ghi MOT dong `EC Approval Action` action
"Attachment Added" - dung bang ma tab "Lich su" cua moi form doc - kem cau de doc
("Thu Trinh dinh kem Plan_Vinasoy.xlsx o cap 2").

Tep: client tai len /api/method/upload_file KHONG kem doctype/docname (is_private=1) - giong
moi form khac, vi nguoi duyet khong co quyen GHI tren DocType nghiep vu. Server o day kiem tep
thuoc CHINH nguoi bam, chua gan vao dau, la tep rieng tu, roi moi gan vao phieu. Khong cho dua
`file_url` cua nguoi khac vao: tep rieng tu cua nguoi khac se lo ra cho ca luong duyet.

Contract Review (loai phieu trong `sharepoint_mirror.THU_MUC_THEO_PHIEU`): tep MOI duoc dua
len SharePoint + cap quyen cho ca luong, chay nen SAU commit. Chi tep moi - tep cu tren
SharePoint la ban SONG (nguoi duyet dang sua), tuyet doi khong tai lai.
"""
import os

import frappe
from frappe import _

ACTION = "Attachment Added"
_REQ = "EC Approval Request"
_FULFILLMENT_OPEN = ("Assigned", "In Progress")
_PRIVATE_PREFIX = "/private/files/"

#: Duoi tep KHONG nhan. Danh sach CAM (khong phai cho phep): nguoi duyet dinh kem du loai ho so
#: (hop dong, bang tinh, anh chup, ban scan, file nen...), liet ke het loai hop le se chan nham
#: viec that. Cam nhung thu chay duoc hoac trinh duyet co the chay khi mo (html/svg -> script).
BLOCKED_EXT = (".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".js", ".jar",
               ".sh", ".php", ".py", ".html", ".htm", ".xhtml", ".svg", ".hta", ".dll")
MAX_NAME_LEN = 140


def _ext(name):
    return os.path.splitext((name or "").strip().lower())[1]


def holder_stage(user, business_doc, approval_request):
    """Neu `user` DANG giu phieu: dict(kind, level_no). Khong thi None.

    kind = "level" (nguoi duyet Pending o cap hien tai) | "fulfillment" (chu viec xu ly)."""
    if not approval_request or not user or user == "Guest":
        return None
    st = approval_request.get("approval_status")
    level = approval_request.get("current_level")
    if st == "Pending" and level:
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        if engine._actor_pending_row(approval_request.get("name"), level, user):
            return {"kind": "level", "level_no": level}
        return None
    if (st == "Approved" and business_doc.get("fulfillment_status") in _FULFILLMENT_OPEN
            and business_doc.get("fulfillment_owner") == user):
        return {"kind": "fulfillment", "level_no": None}
    return None


NO_CAPABILITY = {"can_add_attachment": False, "add_attachment_request": None}


def capability(user, business_doc, approval_request):
    """Co hien nut "Them tep" khong. Chi la goi y cho giao dien - `add` kiem lai tu dau.

    Kem ma EC Approval Request: nut dung chung (ec_addfile.bundle.js) goi MOT endpoint router
    (`reporting.actions.add_attachment`) cho moi form, nen can biet phieu duyet nao."""
    stage = holder_stage(user, business_doc, approval_request)
    return {
        "can_add_attachment": bool(stage),
        "add_attachment_request": approval_request.get("name") if stage else None,
    }


def _own_unattached_file(file_url, user):
    """Ban ghi File cua CHINH `user`, chua gan vao ho so nao, rieng tu. Khong thi throw."""
    url = (file_url or "").strip() if isinstance(file_url, str) else ""
    if not url.startswith(("/private/files/", "/files/")):
        frappe.throw(_("Đường dẫn tệp không hợp lệ."))
    if not url.startswith(_PRIVATE_PREFIX):
        frappe.throw(_("Tệp phải được tải lên ở chế độ riêng tư."))
    if ".." in url:
        frappe.throw(_("Đường dẫn tệp không hợp lệ."))
    rows = frappe.get_all("File", filters={"file_url": url, "owner": user, "is_private": 1,
                                           "is_folder": 0},
                          fields=["name", "file_name", "attached_to_doctype", "attached_to_name"],
                          order_by="creation desc")
    rows = [r for r in rows if not r.get("attached_to_name")]
    if not rows:
        # Khong noi "tep cua nguoi khac" hay "da gan roi": mot cau chung, khong lo thong tin.
        frappe.throw(_("Không tìm thấy tệp bạn vừa tải lên. Vui lòng tải lại."),
                     frappe.PermissionError)
    return rows[0]


def _unique_name(name, taken):
    """Ten tep khong trung (khong phan biet hoa thuong) voi dinh kem dang co cua phieu.

    Trung ten thi SharePoint (conflictBehavior=replace) se GHI DE tep cu - ma tep cu la ban song
    nguoi duyet dang sua. Nen dat lai ten ngay tu Frappe: moi lan dong bo ve sau cung khong de."""
    name = (name or "tep").strip()[:MAX_NAME_LEN] or "tep"
    low = {(t or "").strip().lower() for t in taken}
    if name.lower() not in low:
        return name
    stem, ext = os.path.splitext(name)
    for i in range(2, 100):
        cand = "%s (%d)%s" % (stem, i, ext)
        if cand.lower() not in low:
            return cand
    frappe.throw(_("Phiếu đã có quá nhiều tệp cùng tên."))


def _level_label(request_name, level_no):
    name = frappe.db.get_value("EC Approval Request Level",
                               {"approval_request": request_name, "level_no": level_no},
                               "level_name") or ""
    return name


def add(definition, name, file_url):
    """Gan tep `file_url` (vua tai len, cua chinh nguoi bam) vao phieu + ghi lich su."""
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    user = frappe.session.user
    doctype = definition.business_doctype
    doc = frappe.get_doc(doctype, name)
    if not doc.get("approval_request"):
        frappe.throw(_("Phiếu chưa được gửi."))
    # Khoa phieu duyet: chan dua voi Duyet / Tu choi cung luc (bam xong cap da chuyen thi
    # nguoi nay khong con giu phieu nua).
    frappe.db.get_value(_REQ, doc.approval_request, "name", for_update=True)
    req = frappe.get_doc(_REQ, doc.approval_request)
    stage = holder_stage(user, doc, req)
    if not stage:
        frappe.throw(_("Chỉ người đang xử lý phiếu ở bước hiện tại mới thêm được tệp."),
                     frappe.PermissionError)
    f = _own_unattached_file(file_url, user)
    if _ext(f.get("file_name")) in BLOCKED_EXT or _ext(file_url) in BLOCKED_EXT:
        frappe.throw(_("Loại tệp này không được phép đính kèm."))
    taken = frappe.get_all("File", filters={"attached_to_doctype": doctype,
                                            "attached_to_name": name},
                           pluck="file_name") or []
    file_name = _unique_name(f.get("file_name") or file_url.rsplit("/", 1)[-1], taken)
    frappe.db.set_value("File", f["name"], {"attached_to_doctype": doctype,
                                            "attached_to_name": name,
                                            "file_name": file_name})
    who = frappe.db.get_value("User", user, "full_name") or user
    level_no = stage.get("level_no")
    level_name = _level_label(req.name, level_no) if level_no else None
    where = (_("ở cấp {0}").format(level_no) if level_no else _("ở bước xử lý"))
    engine.log_action(req.name, ACTION, user, level_no, level_name=level_name,
                      comment=_("{0} đính kèm {1} {2}").format(who, file_name, where))
    _mirror_new_file(doctype, name, file_url)
    return {"file_name": file_name, "file_url": file_url, "stage": stage.get("kind"),
            "level_no": level_no}


def _mirror_new_file(doctype, name, file_url):
    """Contract Review: dua RIENG tep nay len SharePoint, chay nen sau commit. Nuot loi enqueue:
    tep da nam an toan trong Frappe; SharePoint hong khong duoc lam hong lan them tep."""
    from ecentric_workspace.approval_center.shared.integrations import sharepoint_mirror as sp
    if not sp.duoc_soi_guong(doctype):
        return False
    try:
        frappe.enqueue(
            "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror.dong_bo_mot_tep_nen",
            queue="long", business_doctype=doctype, business_name=name, file_url=file_url,
            enqueue_after_commit=True)
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "enqueue SharePoint them tep %s" % name)
        return False
