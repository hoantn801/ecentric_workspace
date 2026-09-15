# Copyright (c) 2026, eCentric and contributors
"""Chan tan goc loi "ho so Active nhung khong gan tai khoan dang nhap".

TRIEU CHUNG MA NGUOI DUNG THAY
    Nhan vien moi mo /ec-hr/attendance va nhan "Khong tai duoc" / "loi phan mem
    cham cong". Ho bao CnB, CnB bao la loi app, va ai cung di tim bug o cho khong
    co bug. Su that: `Employee.user_id` rong, nen moi truy van "ho so cua toi"
    khong tra ve gi ca - dung nhu thiet ke.

DA XAY RA BA LAN TRONG HAI TUAN
    linh.hoang (07/09), hoang.truong, nguyen.le (14/09). Ba lan deu mat mot vong
    hoi-dap CnB -> IT -> nhan vien, va lan nao cung ket thuc bang MOT o dien thieu.
    Khi mot loi lap lai ba lan thi no khong con la su co, no la lo hong quy trinh:
    man hinh tao Employee KHONG bat buoc `user_id`, va khong co gi nhac.

HAI LOP CHAN, CO Y KHONG CHAN CUNG
    1. Luc luu (autofill_user_id, hook `before_validate`)
       Neu ho so Active ma thieu `user_id`, ta tu do email cong ty tim User dang
       ton tai; co va CHUA bi ho so khac chiem thi dien luon, va IN RA man hinh
       cho nguoi tao thay minh vua dien gi. Khong tim duoc thi hien canh bao mau
       cam, van cho luu.
       VI SAO KHONG frappe.throw: ho so nhan su con duoc tao trong nhieu tinh
       huong hop le truoc khi co tai khoan (nhan onboard som, thuc tap sinh chua
       cap mail). Chan cung se bien mot phien lam viec cua CnB thanh be tac ma ho
       khong tu go duoc - doi lay mot loi hiem gap hon nhung nang hon.
       VI SAO `before_validate` CHU KHONG PHAI `validate`: hook trong doc_events
       chay SAU controller validate cua Employee, tuc la sau doan Frappe dung
       `user_id` de tao User Permission. Dien o `validate` thi truong co gia tri
       nhung quyen khong duoc tao cho tan lan luu sau.

    2. Moi sang (sweep_missing_user_id, cron 08:00)
       Lop 1 chi cuu duoc ho so tao TU HOM NAY tro di, va chi khi email cong ty
       da dung. Ban ra soat quet lai toan bo ho so Active den han vao lam, gui
       CnB mot tin qua Notification Center. No don duoc ca no cu - la ly do chinh
       chon cach nay thay vi chi canh bao luc luu.
       08:00 la co y: truoc moc nhac cham cong 08:30, nen mot nguoi vao lam hom
       nay con kip duoc noi vao he thong truoc khi ho lo lan nhac dau tien.

KENH TEAMS: CHUA BAT, VA DO LA CHU Y
    `hr_data_issue` de teams=False. Luong Power Automate chan event_type hai lop
    (JSON schema enum o trigger + node Condition), nen mot event type moi ban ra
    Teams se ROT voi PA_400 chu khong phai im lang - te hon la khong gui. Muon co
    Teams thi them dung chuoi "hr_data_issue" vao ca hai cho ben Power Automate
    roi doi o duoi thanh True; khong lam nua voi.
"""
import hashlib

import frappe

from ecentric_workspace.notification_center.events import publish_notification_event

EVENT_TYPE = "hr_data_issue"
KILL_SWITCH = "ec_employee_link_sweep_disabled"
HR_ROLE = "HR Manager"
# Danh sach Employee da loc san dung dieu kien nay - bam vao la sua duoc ngay.
ACTION_URL = "/app/employee?status=Active&user_id=%5B%22is%22%2C%22not%20set%22%5D"
# Bao truoc vai ngay cho nguoi sap vao lam, con lai la no qua han.
LOOKAHEAD_DAYS = 2
MAX_ROWS_IN_MESSAGE = 8


# ------------------------------------------------------------------ lop 1: luc luu
def autofill_user_id(doc, method=None):
    """Hook `before_validate` cua Employee."""
    if doc.get("status") != "Active":
        return
    if (doc.get("user_id") or "").strip():
        return

    login = _free_login(doc.get("company_email"), doc.name) \
        or _free_login(doc.get("personal_email"), doc.name)
    if login:
        doc.user_id = login
        _say("Đã tự điền <b>User ID</b> = {0} (lấy từ email công ty). "
             "Nếu không đúng người, sửa lại trước khi lưu.".format(frappe.utils.escape_html(login)),
             "green")
        return

    _say("Hồ sơ đang <b>Active</b> nhưng chưa có <b>User ID</b>. "
         "Bạn này sẽ <b>không mở được app chấm công</b> cho tới khi trường đó được điền. "
         "Tạo tài khoản đăng nhập rồi quay lại điền User ID giúp nhé.", "orange")


def _free_login(email, exclude_employee=None):
    """Email nay co phai mot User dang dung duoc va CHUA bi ho so khac chiem khong?"""
    email = (email or "").strip().lower()
    if not email or email in ("administrator", "guest"):
        return None
    if not frappe.db.get_value("User", email, "enabled"):
        return None
    taken = frappe.db.get_value(
        "Employee", {"user_id": email, "name": ["!=", exclude_employee or ""]}, "name")
    if taken:
        return None
    return email


def _say(html, indicator):
    # Khong lam on trong migrate / import fixtures / chay test: o do khong co ai doc.
    if any(getattr(frappe.flags, f, None)
           for f in ("in_migrate", "in_install", "in_import", "in_patch")):
        return
    try:
        frappe.msgprint(html, title=frappe._("Tài khoản đăng nhập"), indicator=indicator)
    except Exception:
        pass


# ------------------------------------------------------------- lop 2: quet moi sang
def sweep_missing_user_id():
    """Cron 0 8 * * * (gio site = Asia/Ho_Chi_Minh)."""
    if frappe.conf.get(KILL_SWITCH):
        return {"skipped": "kill switch"}

    rows = _offenders()
    if not rows:
        return {"offenders": 0, "notified": 0}

    recipients = _hr_recipients()
    title = "{0} hồ sơ nhân sự chưa có tài khoản đăng nhập".format(len(rows))
    message = _message(rows)
    # Van tay cua CHINH danh sach: chay lai cron trong ngay khong tao tin thu hai,
    # nhung neu co them mot ho so hong thi danh sach doi -> van tay doi -> van bao.
    stamp = hashlib.sha1("|".join(r["name"] for r in rows).encode("utf-8")).hexdigest()[:10]
    today = frappe.utils.nowdate()

    sent = failed = 0
    for usr in recipients:
        try:
            publish_notification_event(
                event_type=EVENT_TYPE,
                recipient=usr,
                title=title,
                message=message,
                action_url=ACTION_URL,
                actor="Administrator",
                from_user="Administrator",
                dedupe_key="|".join([EVENT_TYPE, usr, str(today), stamp]),
            )
            sent += 1
        except Exception:
            failed += 1
            frappe.log_error(frappe.get_traceback(), "employee_guard sweep")

    frappe.db.commit()
    frappe.log_error(
        "employee_guard offenders=%s notified=%s failed=%s list=%s"
        % (len(rows), sent, failed, ",".join(r["name"] for r in rows)),
        "ec_hr_employee_guard",
    )
    return {"offenders": len(rows), "notified": sent, "failed": failed,
            "employees": [r["name"] for r in rows]}


def _offenders():
    """Ho so Active, den han vao lam (hoac sap), ma chua gan user_id."""
    limit = frappe.utils.add_days(frappe.utils.nowdate(), LOOKAHEAD_DAYS)
    rows = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "employee_number", "user_id",
                "company_email", "personal_email", "date_of_joining", "department"],
        order_by="date_of_joining asc",
        limit_page_length=0,
    )
    out = []
    for r in rows:
        if (r.get("user_id") or "").strip():
            continue
        doj = r.get("date_of_joining")
        if doj and str(doj) > str(limit):
            continue
        out.append(r)
    return out


def _message(rows):
    parts = ["<b>{0} hồ sơ</b> đang Active nhưng chưa gắn tài khoản đăng nhập — "
             "những bạn này <b>không mở được app chấm công</b>.".format(len(rows))]
    for r in rows[:MAX_ROWS_IN_MESSAGE]:
        parts.append("• " + _one_line(r))
    if len(rows) > MAX_ROWS_IN_MESSAGE:
        parts.append("… và {0} hồ sơ nữa.".format(len(rows) - MAX_ROWS_IN_MESSAGE))
    parts.append("Mở danh sách và điền <b>User ID</b> giúp nhé.")
    return "<br>".join(parts)


def _one_line(r):
    bits = [str(r.get("employee_number") or r.get("name") or ""),
            str(r.get("employee_name") or "")]
    doj = r.get("date_of_joining")
    if doj:
        bits.append("vào làm " + frappe.utils.formatdate(doj, "dd/MM"))
    login = _free_login(r.get("company_email"), r.get("name"))
    if login:
        bits.append("<i>đã có tài khoản {0}, chỉ cần điền</i>".format(frappe.utils.escape_html(login)))
    else:
        bits.append("<i>chưa có tài khoản đăng nhập</i>")
    return " · ".join(b for b in bits if b)


def _hr_recipients():
    """Nguoi giu vai tro HR Manager va con dung duoc tai khoan.

    `tabHas Role` la BANG CON: `frappe.get_all` tren bang con bi tu choi neu khong
    noi ro bang cha (DatabaseQuery nem "Cannot query child table without parent").
    Trong mot scheduled job thi loi do chi hien ra trong Error Log - tuc la ban ra
    soat im lang khong gui gi va khong ai biet. Nen uu tien API san co cua Frappe,
    va con duong tu di la duong lui co khai bao day du `parent_doctype`."""
    users = []
    try:
        from frappe.utils.user import get_users_with_role
        users = get_users_with_role(HR_ROLE) or []
    except Exception:
        users = frappe.get_all(
            "Has Role", filters={"role": HR_ROLE, "parenttype": "User"},
            pluck="parent", parent_doctype="User",
            ignore_permissions=True, limit_page_length=0) or []
    out = []
    for u in sorted(set(users)):
        if u in ("Administrator", "Guest"):
            continue
        if frappe.db.get_value("User", u, "enabled"):
            out.append(u)
    return out


@frappe.whitelist(methods=["GET"])
def preview():
    """CHAY KHO: ai dang thieu user_id, va tin se gui cho ai - khong gui gi ca.

    Site chay tren Frappe Cloud, khong co shell, nen day la cach duy nhat kiem
    tra ban quet truoc khi no chay that luc 8h sang."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(frappe._("Chỉ System Manager."))
    rows = _offenders()
    return {"date": frappe.utils.nowdate(),
            "offenders": len(rows),
            "recipients": _hr_recipients(),
            "message": _message(rows) if rows else "",
            "employees": [{"employee": r["name"], "name": r.get("employee_name"),
                           "joining": str(r.get("date_of_joining") or ""),
                           "company_email": r.get("company_email")} for r in rows]}
