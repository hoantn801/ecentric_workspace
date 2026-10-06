# Copyright (c) 2026, eCentric and contributors
"""Nghi viec -> ho so nhan vien + khoa tai khoan (29/09/2026, spec Hoan gui 28/09).

1. Don nghi viec duyet xong: `mark_resignation` ghi Employee.resignation_letter_date (ngay nop)
   va relieving_date (ngay lam viec cuoi). KHONG doi status luc nay - nguoi do van Active toi
   het ngay lam viec cuoi.
2. Job 00:30 hang ngay (lock_left_employees_job.run): Employee Active co relieving_date < hom
   nay -> status "Left" (doc.save, co validate) + User.enabled = 0 (user.save, da phien dang
   nhap ra ngay). KHONG go role, KHONG xoa User Permission (de tra cuu, tuyen lai nguoi cu).
   Bo qua Administrator / Guest; ai giu System Manager hoac co API key thi KHONG tu khoa - bao.
   Review Phan quyen 29/09 (P4): KHOA USER TRUOC, roi moi chuyen Left (ERPNext chan chuyen Left
   khi con nguoi Active report cho nguoi nay - neu Left lam truoc thi tai khoan mo mai mai);
   Left loi -> bao ro "con N nguoi report, HR doi quan ly" + cac cho nguoi do dang la nguoi duyet.
   RUNBOOK rut don / doi y: bat lai User TRUOC, roi moi doi Employee ve Active + xoa relieving_date.
3. Rut don / doi ngay: HR sua hoac xoa relieving_date tren ho so; job chi doc relieving_date.

relieving_date anh huong tinh luong theo ngay o ky cuoi (dung y) - C&B nhan thong bao tong.
ERP khong tu khoa email / Google / tai san: thong bao nhac HR va IT lam."""
import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

EMPLOYEE = "Employee"
SKIP_USERS = ("Administrator", "Guest")
PROTECTED_ROLE = "System Manager"
#: Nguoi nhan thong bao tong sau moi lan khoa: HR, C&B (luong ky cuoi), IT (tai khoan ngoai).
NOTIFY_ROLES = ("HR Manager", "EC CnB", "EC Ops System")


def _employee_of(email):
    email = (email or "").strip()
    if not email:
        return None
    for f in ("user_id", "company_email", "personal_email"):
        emp = frappe.db.get_value(EMPLOYEE, {f: email}, "name")
        if emp:
            return emp
    return None


#: Cong khai cho patch ghi bu / module khac.
employee_of = _employee_of


def mark_resignation(employee_email, letter_date=None, relieving_date=None, source=None):
    """Ghi hai ngay nghi viec vao ho so. Idempotent. -> chuoi ket qua ngan (cho nhat ky)."""
    emp_name = _employee_of(employee_email)
    if not emp_name:
        frappe.log_error(title="Nghi viec: khong thay ho so nhan vien",
                         message="%s (%s) - chua ghi ngay nghi, HR ghi tay." % (employee_email, source))
        return "khong thay ho so %s" % employee_email
    emp = frappe.get_doc(EMPLOYEE, emp_name)
    if not relieving_date:
        return "thieu ngay lam viec cuoi"
    emp.resignation_letter_date = getdate(letter_date) if letter_date else emp.resignation_letter_date
    emp.relieving_date = getdate(relieving_date)
    emp.flags.ec_offboarding_source = source
    emp.save(ignore_permissions=True)
    return "ho so %s: relieving_date=%s" % (emp_name, emp.relieving_date)


def due_employees(today=None):
    """Employee Active co relieving_date TRUOC hom nay (hom nay van con la ngay lam viec).

    SU CO 01/10/2026: filter `relieving_date < hom nay` cua Frappe so sanh
    ifnull(relieving_date, '0001-01-01') - nguoi KHONG co ngay nghi viec cung lot vao,
    va job da khoa 71 tai khoan dang lam. Bat buoc "is set" + loc lai bang Python.
    """
    today = getdate(today or nowdate())
    rows = frappe.get_all(EMPLOYEE, filters=[["status", "=", "Active"],
                                             ["relieving_date", "is", "set"],
                                             ["relieving_date", "<", str(today)]],
                          fields=["name", "employee_name", "user_id", "relieving_date"],
                          order_by="relieving_date asc", limit_page_length=0)
    return [r for r in rows if r.relieving_date and getdate(r.relieving_date) < today]


def _has_api_key(user):
    try:
        return bool(frappe.db.get_value("User", user, "api_key"))
    except Exception:
        return True                                   # khong doc duoc -> coi nhu co, khong khoa


def approver_seats(user):
    """Cho nguoi do dang la NGUOI DUYET dich danh - HR thay nguoi de phieu khong treo."""
    out = []
    try:
        for r in frappe.get_all("EC Department Approver Item", filters={"approver_user": user},
                                fields=["parent"], limit_page_length=0):
            out.append("EC Department Approver %s" % r.parent)
    except Exception:
        pass
    try:
        for r in frappe.get_all("EC Approval Participant", filters={"user": user},
                                fields=["parent", "parenttype", "participant_purpose"], limit_page_length=0):
            out.append("%s %s (%s)" % (r.parenttype, r.parent, r.participant_purpose))
        for r in frappe.get_all("EC Approval Participant", filters={"fallback_user": user},
                                fields=["parent", "parenttype"], limit_page_length=0):
            out.append("%s %s (fallback)" % (r.parenttype, r.parent))
    except Exception:
        pass
    return sorted(set(out))


def lock_one(row):
    """-> (ket_qua, ghi_chu). KHOA USER TRUOC (try rieng), roi moi chuyen Left (try rieng).
    ket_qua: locked | locked_not_left | left_no_user | skipped_protected | skipped_service |
             skipped_api_key."""
    user = (row.user_id or "").strip()
    # Chot chan cuoi: doc lai ngay nghi viec tu DB, khong tin vao danh sach ben goi.
    rd = frappe.db.get_value(EMPLOYEE, row.name, "relieving_date")
    if not rd or getdate(rd) >= getdate(nowdate()):
        return "skipped_no_date", row.name
    if user in SKIP_USERS:
        return "skipped_service", user
    if user and PROTECTED_ROLE in frappe.get_roles(user):
        return "skipped_protected", user
    if user and _has_api_key(user):
        return "skipped_api_key", user
    locked = False
    if user and frappe.db.exists("User", user):
        u = frappe.get_doc("User", user)
        if u.enabled:
            u.enabled = 0
            u.save(ignore_permissions=True)
        locked = True
        frappe.db.commit()                            # khoa da xong, du buoc sau co loi
    try:
        emp = frappe.get_doc(EMPLOYEE, row.name)
        emp.status = "Left"
        emp.flags.ec_offboarding_source = "lock_left_employees_job"
        emp.save(ignore_permissions=True)
    except Exception:
        frappe.db.rollback()
        n = frappe.db.count(EMPLOYEE, {"reports_to": row.name, "status": "Active"})
        frappe.log_error(title="Nghi viec: khong chuyen Left %s" % row.name, message=frappe.get_traceback())
        note = "con %d nguoi report cho %s - HR doi quan ly" % (n, row.name) if n else "xem Error Log"
        return ("locked_not_left" if locked else "error"), note
    return ("locked" if locked else "left_no_user"), user or row.name


def notify_summary(results):
    """Mot thong bao tong cho HR / C&B / IT. Khong gui gi neu khong co ai."""
    if not results:
        return
    from ecentric_workspace.notification_center.events import publish_notification_event
    lines = []
    for row, (kind, note) in results:
        label = {"locked": _("đã khoá tài khoản + chuyển Left"),
                 "locked_not_left": _("đã khoá tài khoản, CHƯA chuyển Left: {0}").format(note),
                 "left_no_user": _("chuyển Left (không có tài khoản)"),
                 "skipped_protected": _("KHÔNG khoá - giữ System Manager, cần xử lý tay"),
                 "skipped_api_key": _("KHÔNG khoá - tài khoản có API key, cần xử lý tay"),
                 "skipped_service": _("bỏ qua tài khoản dịch vụ"),
                 "skipped_no_date": _("KHÔNG khoá - hồ sơ chưa có ngày làm việc cuối"),
                 "error": _("LỖI - xem Error Log")}.get(kind, kind)
        lines.append("%s (%s, nghỉ %s): %s" % (row.employee_name or row.name, row.user_id or "—",
                                               row.relieving_date, label))
        seats = approver_seats(row.user_id) if row.user_id else []
        if seats:
            lines.append("  " + _("Đang là người duyệt ở: {0} - HR thay người để phiếu không treo").format(", ".join(seats)))
    msg = "\n".join(lines) + "\n" + _("Nhắc: khoá email / Google / Lark, thu hồi tài sản - ERP không tự làm được.")
    recipients = set()
    for role in NOTIFY_ROLES:
        for r in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"):
            if r not in SKIP_USERS and frappe.db.get_value("User", r, "enabled"):
                recipients.add(r)
    stamp = nowdate()
    for u in sorted(recipients):
        try:
            publish_notification_event("task_assigned", u, _("Nghỉ việc: đã xử lý {0} người").format(len(results)),
                                       message=msg, action_url="/app/employee?status=Left",
                                       actor="Administrator",
                                       dedupe_key="offboarding|%s|%s" % (stamp, u))
        except Exception:
            frappe.log_error(title="Nghi viec: khong gui duoc thong bao tong cho %s" % u,
                             message=frappe.get_traceback())
