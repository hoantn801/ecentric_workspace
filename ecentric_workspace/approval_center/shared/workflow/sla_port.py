# Copyright (c) 2026, eCentric and contributors
"""Cong noi mot chieu tu Approval Center sang module SLA.

TAI SAO CAN MOT FILE RIENG cho vai ham goi thang:

Luong duyet don la thu dang chay tren ban song va cham vao tien that. Module SLA
la thu moi. Neu `transitions.py` import thang `ecentric_workspace.sla...` thi
mot loi bat ky trong module moi - mot DocType chua migrate, mot chinh sach cau
hinh thieu, mot loi go trong query - se nem nguoc vao giua giao dich duyet don
va lam NGUOI DUNG KHONG DUYET DUOC DON. Do la mot danh doi khong ai chap nhan:
do luong khong duoc phep lam hong cai no do luong.

Nen moi loi goi o day deu:
  * import TRE (trong than ham) - module SLA chua ton tai thi Approval Center
    van nap binh thuong;
  * boc trong `_safe` - moi Exception bi nuot va ghi vao Error Log;
  * khong tra ve gia tri ma ben goi phai dung de quyet dinh gi.

Doi lai: SLA co the mat mot vai ban ghi khi co su co. Chap nhan duoc vi moi
duong ghi deu idempotent qua `dedupe_key` - goi lai khong nhan doi - nen mot lan
chay bu se va duoc. Ban than lan chay bu do (doi chieu nguoc tu ho so duyet ve
nghia vu) CHUA co trong dot nay; no thuoc lo cam hook, cung lan voi viec sua
`transitions.py`. Den luc do, `sweep_overdue` chi lam cho co `is_breached` khop
voi su that, khong tao lai duoc ban ghi da mat.

Mat du lieu tam thoi thi va lai duoc; chan duyet don thi khong.

Chieu nguoc lai (SLA -> Approval Center) KHONG di qua file nay: module SLA
import thang `shared.workflow.business_hours` vi do la phep tinh thuan, dong
bo, va da chay on dinh. Mot chieu, khong vong.
"""
import frappe

_SLA_HOOKS = "ecentric_workspace.sla.application.hooks"


def _safe(fn_name, **kwargs):
    """Goi mot ham cua module SLA va nuot moi loi. Tra ve None khi that bai."""
    try:
        mod = frappe.get_module(_SLA_HOOKS)
    except ModuleNotFoundError:
        # Module chua duoc cai/migrate: im lang. Day la trang thai HOP LE trong
        # giai doan trien khai tung dot, khong phai su co dang bao.
        return None
    except Exception:
        # Module CO nhung nap khong duoc (loi cu phap, import hong, hang so bi
        # doi ten). Khac han truong hop tren va PHAI co tieng: neu khong, moi
        # duong ghi SLA im lang khong lam gi suot may tuan, va khong ai phat
        # hien cho den khi mo bang diem ra thay trong. Mot he do luong hong im
        # lang la mot he do luong noi doi.
        frappe.log_error(title="sla_port: khong nap duoc module SLA",
                         message=frappe.get_traceback())
        return None
    # Cat MOC cua message_log truoc khi goi, de sau do chi cat bo phan do module
    # SLA them vao. Xoa sach ca danh sach se nuot luon thong bao ma chinh luong
    # duyet don da dat truoc do ("Da gui phe duyet", canh bao ngan sach...) -
    # sua mot phien toai bang cach tao ra mot phien toai lon hon.
    mark = _log_len()
    try:
        fn = getattr(mod, fn_name, None)
        if fn is None:
            frappe.log_error(title="sla_port: thieu ham %s" % fn_name,
                             message="Module %s khong co %s" % (_SLA_HOOKS, fn_name))
            return None
        return fn(**kwargs)
    except Exception:
        frappe.log_error(title="sla_port.%s" % fn_name, message=frappe.get_traceback())
        return None
    finally:
        # Mot `frappe.throw` ben trong module SLA da kip nhet thong bao vao
        # message_log truoc khi bi nuot o tren. Khong don thi Frappe van gui no
        # ve client, va nguoi dang duyet don thay mot toast do khong lien quan.
        _trim_messages(mark)


def _log_len():
    try:
        return len(frappe.local.message_log or [])
    except Exception:
        return None


def _trim_messages(mark):
    if mark is None:
        return
    try:
        if len(frappe.local.message_log or []) > mark:
            frappe.local.message_log = frappe.local.message_log[:mark]
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Cac diem cam - Approval Center goi sang. Chua duoc cam vao transitions.py
# trong dot nay; cam la viec cua dot sau, tung diem mot, co kiem chung rieng.
# --------------------------------------------------------------------------- #
def on_level_activated(request_doctype, request_name, level_no, approvers,
                       opened_at=None, sla_policy_code=None, attempt=1):
    """Mot cap duyet vua mo -> mo mot nghia vu cho MOI nguoi duyet cua cap do."""
    return _safe("open_approval_step_obligations",
                 request_doctype=request_doctype, request_name=request_name,
                 level_no=level_no, approvers=approvers, opened_at=opened_at,
                 sla_policy_code=sla_policy_code, attempt=attempt)


def on_level_closed(request_doctype, request_name, level_no, acted_by,
                    closed_at=None, attempt=1):
    """Cap duyet da xong (duyet/tu choi). Nguoi bam nut duoc ghi la dong dung han
    hay tre; nhung nguoi con lai cua cung cap - truong hop Any-One - duoc ghi la
    Excluded chu KHONG phai Missed. Ho khong lam sai gi ca."""
    return _safe("close_approval_step_obligations",
                 request_doctype=request_doctype, request_name=request_name,
                 level_no=level_no, acted_by=acted_by, closed_at=closed_at,
                 attempt=attempt)


def on_request_cancelled(request_doctype, request_name):
    """Ho so bi huy -> moi nghia vu con mo cua no bien khoi phep tinh."""
    return _safe("cancel_obligations_for_source",
                 source_doctype=request_doctype, source_name=request_name)


def on_information_requested(request_doctype, request_name, level_no, from_dt, attempt=1):
    """Yeu cau bo sung thong tin -> dong ho dung, vi bong dang o phia nguoi gui."""
    return _safe("start_pause",
                 source_doctype=request_doctype, source_name=request_name,
                 level_no=level_no, from_dt=from_dt, attempt=attempt)


def on_resubmitted(request_doctype, request_name, level_no, to_dt, attempt=1):
    """Nguoi gui da bo sung -> dong ho chay lai."""
    return _safe("end_pause",
                 source_doctype=request_doctype, source_name=request_name,
                 level_no=level_no, to_dt=to_dt, attempt=attempt)
