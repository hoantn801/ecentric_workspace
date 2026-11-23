# Copyright (c) 2026, eCentric and contributors
"""Job 09:00 cua Danh gia nhan su (khai trong hooks.py, chi noi them).

  * tao_nhap_va_tu_gui_job (moi ngay 09:00, chi NGAY LAM VIEC cua cong ty):
      1. nhap som: dong hop dong sap het (thu viec / thuc tap D-21, hop dong D-37) -> tao nhap;
         thieu LM / tai khoan -> KHONG tao, bao C&B (moi truong hop mot lan - dedupe_key);
      2. den ngay tu gui (D-14 / D-30): gui nhap C&B chua gui (nguoi gui = nguoi dang giu nhap);
      3. NV khong con Active -> huy danh gia dang mo.
  * nhac_thieu_ngay_job (thu Hai 09:00): bao C&B so NV Probation / Intern / Full-time thieu dong
    hop dong hien hanh / thieu ngay ket thuc (trang /ec-hr/danh-gia-nhan-su, tab "Thieu ngay").
Idempotent: chay lai trong ngay khong tao / gui / bao them. Tat khan: Settings.tat_tu_dong hoac
site_config `ec_employee_review_jobs_disabled`. Gio yen lang: job chay 09:00, thong bao di qua
notification_center (giu tin ngoai gio)."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.features.employee_review.application import service
from ecentric_workspace.approval_center.features.employee_review.infrastructure import (
    repository as default_repo)
from ecentric_workspace.approval_center.shared.workflow import transitions as engine
from ecentric_workspace.hr.hop_dong import domain as hd
from ecentric_workspace.notification_center.nhip_gui import gop_tin_job

PAGE = "/ec-hr/danh-gia-nhan-su"


def _tat(repo):
    return bool(frappe.conf.get("ec_employee_review_jobs_disabled")) or bool(repo.settings().get("tat_tu_dong"))


def _bao_cnb(repo, tieu_de, khoa, extra_users=()):
    """Bao C&B (role EC CnB + HR) MOT lan cho moi `khoa` (notification_center chong trung)."""
    from ecentric_workspace.notification_center import events as ncev
    for u in sorted(set(repo.users_with_roles(("EC CnB", "HR"))) | set(u for u in extra_users if u)):
        try:
            ncev.publish_notification_event("approval_required", u, tieu_de, action_url=PAGE,
                                            reference_doctype=service.BUSINESS_DT,
                                            dedupe_key="employee_review|%s|%s" % (khoa, u))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "employee_review bao C&B")


@gop_tin_job
def tao_nhap_va_tu_gui_job(hom_nay=None, repo=default_repo, hr=None):
    """-> {"tao": n, "gui": n, "thieu": n, "huy": n}."""
    out = {"tao": 0, "gui": 0, "thieu": 0, "huy": 0}
    if _tat(repo):
        return out
    hr = hr or service._hr()
    hom_nay = hd.as_date(hom_nay) or repo.today()
    ngay_le = repo.ngay_le()
    if not hd.la_ngay_lam_viec(hom_nay, ngay_le):
        return out
    emps = hr.nhan_vien_dang_lam()
    rows_by = hr.hop_dong_cua([e["name"] for e in emps])
    # Tich hop 23/11: nhap VUA tao trong lan chay nay khong tu gui ngay ca khi ngay tu gui da qua
    # (lan chay dau sau deploy: hop dong het trong < 14 / 30 ngay). C&B co it nhat mot ngay lam viec
    # de xem / sua / tat tu dong; lan chay ke moi gui.
    vua_tao = set()
    for e in emps:
        try:
            ly_do, ctx = service.kiem_du_lieu(e, rows_by.get(e["name"]) or [], hom_nay, hr, ngay_le)
            if ly_do in ("thieu_lm", "thieu_tai_khoan", "lm_la_nv"):
                k = service.khoa(e["name"], ctx["loai"], ctx["row"]["den_ngay"])
                if not repo.review_by_key(k):
                    out["thieu"] += 1
                    _bao_cnb(repo, _("Không tạo được phiếu đánh giá {0} cho {1}: {2}").format(
                        ctx["loai"].lower(), e.get("employee_name") or e["name"],
                        service.LY_DO[ly_do]), "thieu|" + k)
                continue
            if ly_do:
                continue
            res = service.tao_nhap(e["name"], auto=True, hom_nay=hom_nay, repo=repo, hr=hr)
            if res.get("ok") and not res.get("duplicate"):
                out["tao"] += 1
                vua_tao.add(res["name"])
                doc = repo.get_review(res["name"])
                engine.notify([doc.requested_by], _("Đã tạo nháp đánh giá - tự gửi ngày {0}: {1}").format(
                    service._vn(doc.auto_submit_on), doc.request_title), service.BUSINESS_DT, doc.name)
            elif not res.get("ok"):
                _bao_cnb(repo, _("Không tạo được nháp đánh giá cho {0}: {1}").format(
                    e.get("employee_name") or e["name"], res.get("ly_do_text")), "taonhap|%s|%s" % (
                    e["name"], hom_nay))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "employee_review.tao_nhap %s" % e.get("name"))
    for name in repo.drafts_due(hom_nay):
        if name in vua_tao:
            continue
        try:
            doc = repo.get_review(name, for_update=True)
            if doc.approval_request or doc.da_huy_nhap:
                continue
            nv = hr.nhan_vien(doc.nhan_vien)
            if not nv or nv.get("status") != "Active":
                repo.set_review(name, {"da_huy_nhap": 1, "ly_do_huy_nhap": service.LY_DO["nv_nghi"]})
                out["huy"] += 1
                frappe.db.commit()
                continue
            service._gui(doc, repo, hr)
            out["gui"] += 1
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "employee_review.tu_gui %s" % name)
            _bao_cnb(repo, _("Không tự gửi được phiếu đánh giá {0} - mở phiếu để kiểm tra.").format(name),
                     "tugui|%s|%s" % (name, hom_nay))
    for nv_name in sorted({r["nhan_vien"] for r in repo.reviews({"da_huy_nhap": 0}) if r.get("nhan_vien")}):
        try:
            nv = hr.nhan_vien(nv_name)
            if nv and nv.get("status") == "Active":
                continue
            out["huy"] += service.huy_danh_gia_dang_mo(nv_name, service.LY_DO["nv_nghi"], repo=repo)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "employee_review.huy %s" % nv_name)
    return out


@gop_tin_job
def nhac_thieu_ngay_job(hom_nay=None, repo=default_repo, hr=None):
    """Thu Hai 09:00: mot tin cho C&B neu con NV thieu ngay ket thuc. -> so NV thieu."""
    if frappe.conf.get("ec_employee_review_jobs_disabled"):
        return 0
    hom_nay = hd.as_date(hom_nay) or repo.today()
    if not hd.la_ngay_lam_viec(hom_nay, repo.ngay_le()):
        return 0
    ds = service.thieu_ngay_ket_thuc(hom_nay, repo, hr)
    if ds:
        _bao_cnb(repo, _("{0} nhân sự thiếu ngày kết thúc hợp đồng - cập nhật để hệ thống tạo "
                         "phiếu đánh giá đúng hạn.").format(len(ds)), "thieungay|%s" % hom_nay)
    return len(ds)
