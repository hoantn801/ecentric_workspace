# Copyright (c) 2026, eCentric and contributors
"""Cho DUY NHAT cua module SLA co `@frappe.whitelist()`.

Moi ham: doc tham so -> goi service -> boc phong bi -> tra ve. Khong `frappe.db`,
khong nhanh nghiep vu. Tham so tu HTTP luon la chuoi, nen ep kieu tuong minh -
`only_failed=0` nhan duoc "0" se la truthy neu khong ep, va bo loc se im lang
lam nguoc lai y nguoi dung.
"""
import frappe
from frappe import _

from ecentric_workspace.sla import permissions
from ecentric_workspace.sla.application import obligation_service, scoreboard_service
from ecentric_workspace.sla.constants import (
    ADJ_EXCLUDE, ADJ_EXTEND_DUE, ADJ_MARK_MET, ADJ_MARK_MISSED, ADJ_RESTORE,
    ALL_ADJUSTMENTS, DT_ADJUSTMENT, DT_OBLIGATION, OVERALL_MIN_SAMPLE,
    STATUS_MET, STATUS_MISSED,
    STATUS_OPEN,
)


def _ok(data, message=""):
    return {"success": True, "message": message, "data": data}


def _fail(message):
    return {"success": False, "message": message, "data": None}


@frappe.whitelist()
def my_board(period=None):
    """Bang diem cua chinh nguoi dang dang nhap."""
    try:
        return _ok(scoreboard_service.person_board(frappe.session.user, period))
    except frappe.PermissionError as e:
        return _fail(str(e))


@frappe.whitelist()
def person_board(user, period=None):
    try:
        return _ok(scoreboard_service.person_board(user, period))
    except frappe.PermissionError as e:
        return _fail(str(e))


@frappe.whitelist()
def person_items(user=None, period=None, group_key=None, only_failed=0):
    user = user or frappe.session.user
    try:
        return _ok(scoreboard_service.person_items(
            user, period, group_key, int(only_failed or 0)))
    except frappe.PermissionError as e:
        return _fail(str(e))


@frappe.whitelist()
def department_board(department=None, period=None):
    return _ok(scoreboard_service.department_board(department, period))


@frappe.whitelist()
def scope():
    """UI can biet nguoi nay duoc thay den dau TRUOC khi ve tab, de khong ve mot
    tab phong ban rong roi de nguoi ta tuong he thong hong."""
    s, depts = permissions.get_scope()
    return _ok({"scope": s, "departments": depts,
                "overall_min_sample": OVERALL_MIN_SAMPLE,
                "can_adjust": permissions.can_adjust(),
                "period": scoreboard_service.current_period()})


@frappe.whitelist()
def adjust(obligation, action, reason, new_due_at=None,
           source_doctype=None, source_name=None):
    """Sua diem mot dau viec - luon de lai dau vet."""
    if not permissions.can_adjust():
        return _fail(_("Chi HR Manager hoac System Manager duoc dieu chinh diem SLA."))
    if action not in ALL_ADJUSTMENTS:
        return _fail(_("Hanh dong khong hop le."))
    # Kiem tra TRUOC khi cham vao du lieu. Neu de ban ghi nhat ky validate sau,
    # thi mot lan goi thieu ly do se: doi xong diem -> nhat ky nem loi -> API
    # bao that bai -> nhung diem DA doi va khong co dau vet nao. Mot diem doi ma
    # khong ai ky ten la thu ca he thong nay duoc dung de ngan.
    if not (reason or "").strip():
        return _fail(_("Phai ghi ly do dieu chinh."))
    if action == ADJ_EXTEND_DUE and not new_due_at:
        return _fail(_("Hanh dong gia han can han moi."))
    try:
        return _ok(_apply_adjustment(obligation, action, reason, new_due_at,
                                     source_doctype, source_name))
    except Exception as e:
        frappe.log_error(title="sla.adjust", message=frappe.get_traceback())
        return _fail(str(e))


def _apply_adjustment(obligation, action, reason, new_due_at,
                      source_doctype, source_name):
    """Ghi NHAT KY TRUOC, doi diem SAU.

    Thu tu nay la co y. Nhat ky la thu co the tu choi (ly do rong, ban ghi bat
    bien); diem la thu khong the lay lai neu doi roi ma nhat ky hong. Ghi nhat
    ky truoc nghia la: khong bao gio co mot diem doi ma khong co dong giai thich
    di kem - cung lam la co mot dong nhat ky thua neu buoc sau hong, va mot dong
    thua thi doi chieu duoc, con mot diem doi lang le thi khong.
    """
    prev = frappe.db.get_value(DT_OBLIGATION, obligation, "status")
    if not prev:
        frappe.throw(_("Khong tim thay nghia vu."))
    log = frappe.get_doc({
        "doctype": DT_ADJUSTMENT, "obligation": obligation, "action": action,
        "reason": reason, "new_due_at": new_due_at, "previous_status": prev,
        "resulting_status": prev, "source_doctype": source_doctype,
        "source_name": source_name,
    })
    log.insert(ignore_permissions=True)
    if action == ADJ_EXCLUDE:
        obligation_service.exclude_obligation(obligation, reason)
    elif action == ADJ_MARK_MET:
        frappe.db.set_value(DT_OBLIGATION, obligation,
                            {"status": STATUS_MET, "late_seconds": 0, "is_breached": 0},
                            update_modified=False)
    elif action == ADJ_MARK_MISSED:
        frappe.db.set_value(DT_OBLIGATION, obligation,
                            {"status": STATUS_MISSED, "is_breached": 0},
                            update_modified=False)
    elif action == ADJ_RESTORE:
        frappe.db.set_value(DT_OBLIGATION, obligation,
                            {"status": STATUS_OPEN, "closed_at": None,
                             "excluded_reason": None, "late_seconds": 0},
                            update_modified=False)
    elif action == ADJ_EXTEND_DUE:
        frappe.db.set_value(DT_OBLIGATION, obligation, {"due_at": new_due_at},
                            update_modified=False)
    after = frappe.db.get_value(DT_OBLIGATION, obligation, "status")
    # `resulting_status` la o duy nhat cua ban ghi nhat ky duoc phep ghi sau khi
    # tao - ban ghi la bat bien voi nguoi dung, khong bat bien voi buoc dong so
    # cua chinh no. Ghi thang qua db de khong dung phai `validate` chan sua.
    frappe.db.set_value(DT_ADJUSTMENT, log.name, {"resulting_status": after},
                        update_modified=False)
    frappe.db.set_value(DT_OBLIGATION, obligation, {"adjusted": 1}, update_modified=False)
    return {"obligation": obligation, "from": prev, "to": after}


# --------------------------------------------------------------------------- #
# Cau hinh SLA cua cac buoc duyet
#
# Hai endpoint nay ton tai de viec CAP NHAT SLA khong phai viet patch moi moi
# lan. Chu so huu doi so trong `fixtures/approval_sla.json`, deploy, goi
# `reimport_approval_sla` mot lan la xong. Va vi patch nap lan dau la fail-safe
# (luon ket thuc xanh, ke ca khi 65/65 dong hong), `verify_approval_sla` la
# duong doc lai doc lap de phan biet "deploy xanh" voi "cau hinh dung" - hai
# dieu khac nhau ma neu khong co cho doi chieu thi khong ai phan biet duoc.
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def verify_approval_sla():
    """Doi chieu he thong voi tep cau hinh. CHI DOC."""
    if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
        return _fail(_("Chi System Manager duoc xem doi chieu cau hinh SLA."))
    from ecentric_workspace.sla.application import policy_import
    return _ok(policy_import.verify())


@frappe.whitelist()
def reimport_approval_sla():
    """Nap lai cau hinh SLA tu tep fixture. Chay lai duoc, khong nhan doi gi."""
    if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
        return _fail(_("Chi System Manager duoc nap lai cau hinh SLA."))
    from ecentric_workspace.sla.application import policy_import
    report = policy_import.apply()
    return _ok(report, policy_import.summarize(report) or _("Khong co gi thay doi."))


# --------------------------------------------------------------------------- #
# Nhom Bao cao tuan
# --------------------------------------------------------------------------- #
def _require_admin():
    return ("System Manager" in frappe.get_roles()
            or frappe.session.user == "Administrator")


@frappe.whitelist()
def sync_weekly():
    """Dong bo ngay cac ban bao cao gan day, khong doi job hang gio."""
    if not _require_admin():
        return _fail(_("Chi System Manager duoc chay dong bo."))
    from ecentric_workspace.sla.infrastructure import weekly_source
    r = weekly_source.sync()
    return _ok({k: (len(v) if isinstance(v, list) else v) for k, v in r.items()},
               _("Quét {0} bản báo cáo.").format(r.get("quet", 0)))


@frappe.whitelist()
def backfill_weekly(weeks=26):
    """Dung lai nghia vu cho cac tuan DA QUA tu du lieu co san.

    Duong ngan nhat de biet engine cham diem co dung khong: doi chieu ngay voi
    nhung tuan da co nguoi nop dung han va nguoi nop muon, thay vi doi bon tuan.
    """
    if not _require_admin():
        return _fail(_("Chi System Manager duoc chay bu du lieu."))
    from ecentric_workspace.sla.infrastructure import weekly_source
    r = weekly_source.backfill(weeks=int(weeks or 26))
    return _ok({k: (len(v) if isinstance(v, list) else v) for k, v in r.items()},
               _("Quét {0} bản báo cáo trong {1} tuần.").format(r.get("quet", 0), weeks))


@frappe.whitelist()
def weekly_coverage(period=None):
    """Ai KHONG co nghia vu bao cao tuan nao trong ky - va thuoc phong nao.

    Cau hoi nay quan trong ngang voi "ai tre": mot nguoi khong co nghia vu nao
    thi khong bi do, va ly do gan nhu luon la phong ban do chua co
    `Department Reporting Window` chu khong phai ho duoc mien.
    """
    from ecentric_workspace.sla.infrastructure import weekly_source
    if not _require_admin():
        return _fail(_("Chi System Manager duoc xem do phu."))
    return _ok(weekly_source.coverage(period))


@frappe.whitelist()
def weekly_preview(weeks=26):
    """Engine SE cham diem the nao cho cac tuan da qua - CHI DOC, khong ghi gi.

    Dung de kiem chung cong thuc bang du lieu that TRUOC khi no cham diem ai.
    Khac `backfill_weekly`: ham do TAO nghia vu that va bi chan boi ngay bat dau
    ap dung; ham nay khong bi chan vi no khong tao gi ca.
    """
    if not _require_admin():
        return _fail(_("Chi System Manager duoc xem ban chay kho."))
    from ecentric_workspace.sla.infrastructure import weekly_source
    return _ok(weekly_source.preview(weeks=int(weeks or 26)))


@frappe.whitelist()
def effective_dates():
    """Ngay bat dau cham diem cua tung nhom - de doi chieu sau khi deploy."""
    from ecentric_workspace.sla.constants import DT_TYPE
    rows = frappe.get_all(DT_TYPE, fields=["type_code", "group_key", "effective_from",
                                           "counts_toward_sla", "min_sample", "active"],
                          order_by="sort_order asc", limit_page_length=0)
    return _ok(rows)


# --------------------------------------------------------------------------- #
# Nhom Cham cong
# --------------------------------------------------------------------------- #
def _att():
    from ecentric_workspace.sla.infrastructure import attendance_source
    return attendance_source


def _counts(r):
    return {k: (len(v) if isinstance(v, list) else v) for k, v in r.items()}


@frappe.whitelist()
def sync_attendance(start=None, end=None):
    """Dong bo ngay cong, khong doi job hang ngay."""
    if not _require_admin():
        return _fail(_("Chi System Manager duoc chay dong bo."))
    return _ok(_counts(_att().sync(start=start, end=end)))


@frappe.whitelist()
def backfill_attendance(start="2026-09-01", end=None):
    """Dung lai ngay cong tu 01/09 - moc chu so huu chot cho nhom nay."""
    if not _require_admin():
        return _fail(_("Chi System Manager duoc chay bu du lieu."))
    return _ok(_counts(_att().backfill(start=start, end=end)))


@frappe.whitelist()
def attendance_coverage(period=None):
    """Ai KHONG co ngay cong nao trong ky - khong co nghia vu thi khong bi do."""
    if not _require_admin():
        return _fail(_("Chi System Manager duoc xem do phu."))
    return _ok(_att().coverage(period))


# --------------------------------------------------------------------------- #
# Cau hinh dang chay cua cac buoc duyet (tab "Quy trinh duyet" tren /sla)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def approval_config():
    """Han SLA cua tung cap duyet / buoc xu ly. CHI DOC.

    MO CHO MOI NHAN VIEN, khong gioi han System Manager nhu hai endpoint doi
    chieu o tren. Hai thu khac nhau: `verify_approval_sla` doi chieu he thong
    voi tep cau hinh (viec van hanh), con ham nay tra loi "toi co bao lau de
    duyet" - cau hoi ma nguoi bi tru diem phai tra loi duoc TRUOC khi bi tru,
    khong phai sau. Bang tra ve khong co du lieu ca nhan nao: ten quy trinh, so
    cap, so gio - het.
    """
    from ecentric_workspace.sla.application import approval_config as cfg
    return _ok(cfg.approval_steps())


# --------------------------------------------------------------------------- #
# Trang /sla
# --------------------------------------------------------------------------- #
@frappe.whitelist(methods=["POST"])
def sync_sla_page(force=0):
    """Nap lai HTML trang /sla tu ma nguon trong repo.

    Ton tai de viec sua trang khong phai viet patch moi moi lan - patch p005
    chi la lan chay dau. `force=1` chi bo khoa chong ghi de, khong bao gio ep
    publish mot trang nguoi van hanh da tat.
    """
    if not _require_admin():
        return _fail(_("Chi System Manager duoc dong bo trang /sla."))
    # Tham so tu HTTP luon la chuoi. `int("yes")` nem ValueError tho kem
    # traceback ra client; o day mot tham so go sai chi co nghia la "khong ep".
    force = 1 if str(force or "").strip().lower() in ("1", "true", "yes", "on") else 0
    from ecentric_workspace.sla.pages.scoreboard import page_sync
    return _ok(page_sync.sync(force=force))


# --------------------------------------------------------------------------- #
# Nhom Phan hoi phe duyet
#
# Duong CHINH cua nhom nay la cac loi goi hook trong `transitions.py`, chay dong
# bo ngay luc cap duyet mo va dong. Ba endpoint duoi day thuoc ve LUOI DO: chung
# quet lai va va vao nhung cho hook da truot. Giu chung tach bach voi duong chinh
# la co y - mot con so khac 0 o `approval_coverage` la dau hieu hook dang thung,
# chu khong phai chuyen binh thuong.
# --------------------------------------------------------------------------- #
def _appr():
    from ecentric_workspace.sla.infrastructure import approval_source
    return approval_source


@frappe.whitelist(methods=["POST"])
def sync_approvals(days=14, limit=500):
    """Doi chieu nguoc tu ho so duyet ve nghia vu SLA. Chay lai duoc."""
    if not _require_admin():
        return _fail(_("Chi System Manager duoc chay dong bo."))
    r = _appr().sync(days=int(days or 14), limit=int(limit or 500))
    return _ok(_counts(r), _("Quét {0} hồ sơ duyệt.").format(r.get("ho_so", 0)))


@frappe.whitelist(methods=["POST"])
def backfill_approvals(start="2026-09-21", limit=2000):
    """Dung lai tu moc ap dung cua nhom nay (21/09)."""
    if not _require_admin():
        return _fail(_("Chi System Manager duoc chay bu du lieu."))
    r = _appr().backfill(start=start, limit=int(limit or 2000))
    return _ok(_counts(r), _("Quét {0} hồ sơ duyệt từ {1}.").format(r.get("ho_so", 0), start))


@frappe.whitelist()
def approval_coverage(days=14):
    """Ho so nao co cap duyet DA KICH HOAT ma khong co mot nghia vu nao.

    Day la phep kiem chinh HOOK, khong phai kiem nguoi duyet: khac 0 nghia la co
    mot duong kich hoat cap nao do chua goi sang SLA.
    """
    if not _require_admin():
        return _fail(_("Chi System Manager duoc xem do phu."))
    r = _appr().coverage(days=int(days or 14))
    return _ok({"ho_so": r["ho_so"], "cap": r["cap"], "tu_ngay": r["tu_ngay"],
                "thieu": len(r["thieu"]), "danh_sach": r["thieu"][:50]})
