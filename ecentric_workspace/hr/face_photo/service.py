# Copyright (c) 2026, eCentric and contributors
"""Thu anh khuon mat qua ERP -> goi ZIP + danh sach cho iVMS-4200 nap vao may Hikvision.

Moi nhan vien tu chup / chon MOT anh tren /khuon-mat (dien thoai). Anh duoc nen ve JPG <= 200 KB
(chuan nhap hang loat cua iVMS-4200) va luu thanh File RIENG TU gan vao Employee, ten
`ec_face_<ma>.jpg`. Lan sau gui lai -> dung anh MOI NHAT. Khong them truong vao Employee.

Ai xem duoc: chinh nguoi do (anh cua minh) + HR/CnB. Anh khuon mat la du lieu sinh trac hoc =
du lieu ca nhan nhay cam (ND 13/2023) -> bat buoc tick dong y; loi dong y ghi Comment tren Employee.
"""
import io
import zipfile

import frappe

from ecentric_workspace.hr.face_photo import constants as C
from ecentric_workspace.hr.face_photo import imaging, naming


class Forbidden(Exception):
    pass


def is_hr(user):
    if user == "Administrator":
        return True
    return bool(frappe.db.sql(
        "select 1 from `tabHas Role` where parent=%s and parenttype='User' and role in %s limit 1",
        (user, C.HR_ROLES)))


def my_employee(user):
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"},
                               ["name", "employee_name", "department", "attendance_device_id"],
                               as_dict=True)


def _photos(employees=None):
    """{employee: {name, file_url, creation}} - anh MOI NHAT cua tung nguoi."""
    filters = {"attached_to_doctype": "Employee", "file_name": ("like", C.FILE_PREFIX + "%"),
               "is_private": 1}
    if employees is not None:
        if not employees:
            return {}
        filters["attached_to_name"] = ("in", list(employees))
    out = {}
    for f in frappe.get_all("File", filters=filters,
                            fields=["name", "attached_to_name", "file_url", "creation"],
                            order_by="creation desc", limit_page_length=0):
        out.setdefault(f.attached_to_name, f)
    return out


def status(user):
    emp = my_employee(user)
    if not emp:
        return {"employee": None, "is_hr": is_hr(user)}
    p = _photos([emp.name]).get(emp.name)
    return {"employee": emp.name, "employee_name": emp.employee_name,
            "device_no": naming.device_no(emp.name, emp.attendance_device_id),
            "has_photo": bool(p), "uploaded_at": str(p.creation)[:16] if p else "",
            "photo_url": p.file_url if p else "", "is_hr": is_hr(user),
            "consent_text": C.CONSENT_TEXT}


def save(user, raw, consent):
    if not int(consent or 0):
        raise imaging.PhotoError("Bạn cần tick đồng ý trước khi gửi ảnh.")
    emp = my_employee(user)
    if not emp:
        raise Forbidden("Không tìm thấy hồ sơ nhân viên đang làm việc của tài khoản này.")
    jpg, size = imaging.prepare(raw)
    f = frappe.get_doc({"doctype": "File", "file_name": "%s%s.jpg" % (C.FILE_PREFIX, emp.name),
                        "is_private": 1, "content": jpg, "attached_to_doctype": "Employee",
                        "attached_to_name": emp.name})
    f.flags.ignore_permissions = True
    f.insert(ignore_permissions=True)
    c = frappe.get_doc({"doctype": "Comment", "comment_type": "Info",
                        "reference_doctype": "Employee", "reference_name": emp.name,
                        "content": "Gửi ảnh khuôn mặt cho máy chấm công (%dx%d, %d KB). Đồng ý: %s"
                                   % (size[0], size[1], len(jpg) // 1024, C.CONSENT_TEXT)})
    c.flags.ignore_permissions = True
    c.insert(ignore_permissions=True)
    return status(user)


def _active():
    return frappe.get_all("Employee", filters={"status": "Active"},
                          fields=["name", "employee_name", "department", "user_id",
                                  "attendance_device_id"],
                          order_by="department asc, employee_name asc", limit_page_length=0)


def overview(user):
    if not is_hr(user):
        raise Forbidden("Chỉ Nhân sự (HR/CnB) xem được danh sách ảnh khuôn mặt.")
    emps = _active()
    ph = _photos([e.name for e in emps])
    rows = [{"employee": e.name, "employee_name": e.employee_name, "department": e.department or "",
             "device_no": naming.device_no(e.name, e.attendance_device_id),
             "has_photo": e.name in ph, "uploaded_at": str(ph[e.name].creation)[:16] if e.name in ph else "",
             "photo_url": ph[e.name].file_url if e.name in ph else "", "has_user": bool(e.user_id)}
            for e in emps]
    return {"rows": rows, "done": sum(1 for r in rows if r["has_photo"]), "total": len(rows)}


def _file_bytes(file_name):
    return frappe.get_doc("File", file_name).get_content()


def build_zip(user):
    """ZIP gom: anh/<ma>_<Ten>.jpg + danh_sach_nhan_vien.csv + HUONG_DAN.txt."""
    if not is_hr(user):
        raise Forbidden("Chỉ Nhân sự (HR/CnB) tải được gói ảnh.")
    emps = _active()
    ph = _photos([e.name for e in emps])
    buf = io.BytesIO()
    lines = ["Employee No,Name,Department,ERP Employee,Co anh"]
    n = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for e in emps:
            no = naming.device_no(e.name, e.attendance_device_id)
            nm = naming.ascii_name(e.employee_name)
            lines.append('%s,"%s","%s",%s,%s' % (no, nm, (e.department or "").replace('"', "'"),
                                                  e.name, "x" if e.name in ph else ""))
            if e.name in ph:
                z.writestr("anh/" + naming.file_name(no, e.employee_name), _file_bytes(ph[e.name].name))
                n += 1
        z.writestr("danh_sach_nhan_vien.csv", ("﻿" + "\r\n".join(lines) + "\r\n").encode("utf-8"))
        z.writestr("HUONG_DAN.txt", HUONG_DAN.encode("utf-8"))
    return buf.getvalue(), n, len(emps)


def remind_missing(user):
    """Gui nhac (chuong ERP + Teams) cho nguoi CHUA gui anh. Moi ngay toi da 1 lan / nguoi."""
    if not is_hr(user):
        raise Forbidden("Chỉ Nhân sự (HR/CnB) gửi nhắc được.")
    from ecentric_workspace.notification_center.events import publish_notification_event
    emps = _active()
    ph = _photos([e.name for e in emps])
    today = frappe.utils.nowdate()
    sent = 0
    for e in emps:
        if e.name in ph or not e.user_id:
            continue
        try:
            publish_notification_event(
                event_type=C.REMIND_EVENT, recipient=e.user_id,
                title="Gửi ảnh khuôn mặt cho máy chấm công",
                message="Văn phòng dùng máy nhận diện khuôn mặt để mở cửa và chấm công. "
                        "Mở trang và chụp 1 ảnh chính diện (mất khoảng 1 phút).",
                action_url=C.ROUTE, reference_doctype="Employee", reference_name=e.name,
                actor=user, from_user=user,
                dedupe_key="|".join(["ec_face_photo", e.user_id, today]))
            sent += 1
        except Exception:
            frappe.log_error(title="face_photo remind " + e.name, message=frappe.get_traceback())
    return {"sent": sent}


HUONG_DAN = """GOI ANH KHUON MAT CHO MAY HIKVISION (xuat tu ERP /khuon-mat)

1. Mo iVMS-4200 tren laptop cung mang voi may cham cong, them may (Device Management).
2. Person -> Import -> Person information: nhap danh_sach_nhan_vien.csv vao FILE MAU cua iVMS
   (tai mau tu nut Import; cot Employee No + Name lay tu file csv nay). Employee No PHAI giu
   nguyen - day la ma ERP dung de khop luot quet voi nhan vien.
3. Nen thu muc anh/ thanh ZIP (hoac dung thang ZIP nay neu iVMS nhan), Person -> Import -> Face,
   bat "Verify by Device", chon ZIP -> Import. Ten moi anh = "<Employee No>_<Ten>.jpg".
4. Access Control -> ap quyen (Access Group) cho moi nguoi -> Apply xuong may.
5. Anh nao bi bao khong dat: nguoi do chup lai tren ERP /khuon-mat, xuat goi moi, nhap lai.
"""
