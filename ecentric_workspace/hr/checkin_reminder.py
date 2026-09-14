# Copyright (c) 2026, eCentric and contributors
"""Nhac cham cong - hai moc trong buoi sang, di qua Notification Center.

BOI CANH (do chinh telemetry tren prod)
    Ban cu la mot Server Script chay cron "30 * * * *" va tu loc `now.hour == 8`.
    No CHAY TOT: Error Log ghi sent=48..60 moi ngay lam viec. Cai no khong lam duoc
    la dua thong bao RA NGOAI app - no chi tao Notification Log, tuc la chuong trong
    trang. Nguoi de quen cham cong lai chinh la nguoi khong mo ERP buoi sang.

VI SAO CHUYEN SANG CODE APP
    Chi code app moi goi duoc `publish_notification_event`, noi da co san quat ra
    Teams (698 tin gui thanh cong trong mot tuan) va - tu ban nay - web push. Server
    Script chay trong RestrictedPython, khong import duoc module cua app.
    Ngoai ra fixtures tu dong ghi de Server Script moi lan migrate, nen sua tay tren
    prod khong bao gio song qua lan deploy ke tiep.

HAI MOC, HAI KENH KHAC NHAU
    08:30  attendance_missing        -> inbox + toast + TEAMS + web push
    09:30  attendance_missing_final  -> inbox + toast + web push (KHONG Teams)
    Han cham cong la 10:00. Luc 8h30 con ~54 nguoi chua cham nhung phan lon chua he
    tre, nen lan hai co chu y KHONG ban Teams: mot nguoi chi nhan toi da mot DM
    Teams moi sang. Khong lam vay thi moi nguoi se tat thong bao Teams - va mat luon
    ca thong bao duyet don, von la thu quan trong hon nhieu.

HAI HAM KHAC NHAU, KHONG PHAI MOT HAM O HAI CRON
    Frappe khoa Scheduled Job Type theo dotted path cua `method`, nen khai cung mot
    ham o hai bieu thuc cron chi giu lai MOT - da do tren prod 10/09 (xem ghi chu o
    hooks.py cho esign). Vi the co remind_0830() va remind_0930() rieng biet.
"""
import frappe

from ecentric_workspace.notification_center.events import publish_notification_event

ACTION_URL = "/ec-hr/attendance"
KILL_SWITCH = "ec_checkin_reminder_disabled"


def remind_0830():
    """Cron 30 8 * * * (gio site = Asia/Ho_Chi_Minh)."""
    return _run("attendance_missing",
                "Nhắc chấm công hôm nay",
                "Bạn <b>chưa chấm công</b> hôm nay.<br>Mở app eCentric ERP để chấm công trước <b>10:00</b>.")


def remind_0930():
    """Cron 30 9 * * * - loi nhac cuoi truoc han 10:00."""
    return _run("attendance_missing_final",
                "Sắp hết giờ chấm công",
                "Bạn <b>vẫn chưa chấm công</b> hôm nay.<br>Còn khoảng 30 phút trước <b>10:00</b> — chấm công ngay để không bị thiếu công.")


def _run(event_type, title, message):
    if frappe.conf.get(KILL_SWITCH):
        return {"skipped": "kill switch"}

    today = frappe.utils.nowdate()
    rows = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "user_id", "holiday_list", "date_of_joining"],
        limit_page_length=0,
    )

    sent = skipped = failed = 0
    for r in rows:
        usr = (r.get("user_id") or "").strip()
        if not usr:
            continue
        try:
            if _should_skip(r, today):
                skipped += 1
                continue
            # Dedupe theo NGAY + LOAI su kien: chay lai cron trong cung mot phut
            # (Frappe co the enqueue lai khi worker restart) khong tao thong bao thu hai,
            # nhung moc 9h30 van la mot su kien KHAC nen van duoc gui.
            publish_notification_event(
                event_type=event_type,
                recipient=usr,
                title=title,
                message=message,
                action_url=ACTION_URL,
                # CO tham chieu Employee.
                #
                # DINH CHINH (14/09): ly do ghi o ban truoc la SAI. Minh doc thay 300
                # tin Teams thanh cong gan nhat deu co reference_doctype, roi ket luan
                # luong Power Automate BAT BUOC co tham chieu - tuong quan doc thanh
                # nhan qua. JSON schema cua trigger cho thay `reference_doctype` KHONG
                # nam trong `required`; thu pham that su la `event_type` kieu enum,
                # chua khai `attendance_missing`. Sua bang cach them ten su kien vao
                # CA HAI cong: enum o trigger va node Condition.
                # Giu tham chieu o day khong phai vi flow doi, ma vi no lam cho
                # Delivery Log / Notification Log tro ve dung ho so nguoi nhan.
                #
                # Rui ro lo du lieu phu cap (power_automate._request_fields do TEN
                # TRUONG de bom "So tien" vao the Teams) da duoc chan tan goc o phia
                # provider: _NO_AMOUNT_DOCTYPES chan han Employee khoi phep do tien,
                # nen khong phu thuoc vao viec tuong lai khong ai them truong `amount`.
                reference_doctype="Employee",
                reference_name=r["name"],
                actor="Administrator",
                from_user="Administrator",
                dedupe_key="|".join([event_type, usr, str(today)]),
            )
            sent += 1
        except Exception:
            failed += 1
            frappe.log_error(frappe.get_traceback(), "checkin_reminder " + event_type)

    frappe.db.commit()
    frappe.log_error(
        "checkin_reminder %s sent=%s skipped=%s failed=%s date=%s"
        % (event_type, sent, skipped, failed, today),
        "ec_hr_checkin_reminder",
    )
    return {"event_type": event_type, "sent": sent, "skipped": skipped, "failed": failed}


@frappe.whitelist(methods=["GET"])
def preview():
    """CHAY KHO: tra ve danh sach nhung ai SE bi nhac, KHONG gui gi ca.

    VI SAO CAN: site chay tren Frappe Cloud, khong co shell de chay thu. Ke tu khi
    Server Script cu bi tat, loi nhac chi con chay bang duong nay - khong con luoi
    do. Neu no loi luc 8h30 thi khong ai duoc nhac va ta chi biet sau khi da lo.
    Ham nay di het dung mot duong ma `_run` di (cung truy van, cung logic bo qua),
    chi khac la khong goi publish_notification_event - nen chay no truoc la du de
    biet ngay hom sau co chay duoc khong.

    Chi System Manager: day la danh sach ai chua cham cong hom nay."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(frappe._("Chi System Manager."))
    today = frappe.utils.nowdate()
    rows = frappe.get_all(
        "Employee", filters={"status": "Active"},
        fields=["name", "employee_name", "user_id", "holiday_list", "date_of_joining"],
        limit_page_length=0,
    )
    would, skipped, no_user = [], 0, 0
    for r in rows:
        if not (r.get("user_id") or "").strip():
            no_user += 1
            continue
        if _should_skip(r, today):
            skipped += 1
            continue
        would.append({"employee": r["name"], "name": r.get("employee_name"),
                      "user": r["user_id"]})
    return {"date": today, "active": len(rows), "no_user_id": no_user,
            "skipped": skipped, "would_notify": len(would), "people": would}


def _should_skip(emp, today):
    """True khi khong duoc phep nhac nguoi nay hom nay."""
    # 1) Chua den ngay vao lam -> khong ton tai nghia vu cham cong.
    doj = emp.get("date_of_joining")
    if doj and str(today) < str(doj):
        return True
    # 2) Ngay nghi theo lich nghi cua chinh ho (khong gia dinh thu 7/CN cho ca cong ty).
    hl = emp.get("holiday_list")
    if hl and frappe.db.exists("Holiday", {"parent": hl, "holiday_date": today}):
        return True
    # 3) Da duoc duyet nghi phep hom nay.
    if frappe.db.exists("Leave Application", {
        "employee": emp["name"], "docstatus": 1, "status": "Approved",
        "from_date": ["<=", today], "to_date": [">=", today],
    }):
        return True
    # 4) Da cham cong roi.
    if frappe.db.sql(
        "select name from `tabEmployee Checkin` where employee=%s and date(time)=%s limit 1",
        (emp["name"], today),
    ):
        return True
    return False
