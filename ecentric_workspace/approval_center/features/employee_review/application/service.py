# Copyright (c) 2026, eCentric and contributors
"""Danh gia nhan su (thu viec / thuc tap / hop dong) - dieu phoi tren engine dung chung.

Hoan chot 22-23/11/2026 (HR Dot 2):
  * MOT form cho ca 3 loai. Nguoi gui = C&B (role EC CnB / HR), doi tuong = nhan vien
    (`employee_user`). Ly do: voi engine, nguoi gui duoc huy phieu, nhan "tra lai" va doc het -
    khong hop voi nhan vien duoc danh gia.
  * Nguon ngay = bang hop dong tren ho so (`Employee.ec_contracts`), khong them truong moi.
  * He thong tao NHAP som (thu viec / thuc tap D-21, hop dong D-37) de C&B sua truoc, roi DEN
    NGAY TU GUI (D-14 / D-30) - "co the luu nhap truoc, den ngay tu gui ra".
  * Luong: NV tu danh gia (cap 1) -> Line Manager (cap 2: ket qua + nhan xet BAT BUOC, an voi NV
    toi khi CEO duyet) -> CEO (cap 3). LM = CEO: KHONG de engine bo cap LM.
  * Thieu du lieu (khong co ngay, khong co LM, NV chua co tai khoan) -> KHONG tao phieu; vao hang
    cho C&B + bao C&B (khong co phieu chet im lang).
  * Sau CEO: tao DE XUAT cap nhat ho so (dong hop dong moi / gia han / doi loai nhan su) - C&B
    xac nhan MOT cham (co audit). Khong tu ghi thang vao ho so.

Ghi chu khi duyet (EC Approval Action.comment) KHONG an duoc voi nhan vien, nen buoc NV / LM ghi
mot cau chung chung; noi dung that nam o truong nghiep vu (permlevel 1 + business_redactor)."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.features.employee_review.domain import luat
from ecentric_workspace.approval_center.features.employee_review.infrastructure import (
    repository as default_repo)
from ecentric_workspace.approval_center.shared.workflow import transitions as engine
from ecentric_workspace.hr.hop_dong import domain as hd

BUSINESS_DT = "EC Employee Review"
APPROVAL_TYPE = "EMPLOYEE_REVIEW"
PROCESS_TV = "EMPLOYEE_REVIEW_TV-V1"     # thu viec + thuc tap (SLA NV 2 / LM 3 / CEO 2 ngay LV)
PROCESS_HD = "EMPLOYEE_REVIEW_HD-V1"     # hop dong (SLA NV 3 / LM 5 / CEO 3 ngay LV)
CNB_ROLES = ("EC CnB", "HR", "HR Manager", "System Manager")
OPEN_STATUSES = ("Pending", "Information Required")
CAP_NV, CAP_LM, CAP_CEO = 1, 2, 3
COMMENT_NV = "Đã gửi tự đánh giá."
COMMENT_LM = ("Đã gửi đánh giá của quản lý trực tiếp (nội dung chỉ hiện với nhân viên sau khi "
              "CEO duyệt).")

LY_DO = {
    "thieu_ngay": "Thiếu ngày kết thúc hợp đồng",
    "thieu_lm": "Không có Line Manager (hoặc LM đã nghỉ / bị khoá)",
    "thieu_tai_khoan": "Nhân viên chưa có tài khoản đăng nhập",
    "lm_la_nv": "Line Manager trùng chính nhân viên",
    "nv_nghi": "Nhân viên không còn Active",
    "khong_can": "Dòng hợp đồng hiện hành không cần đánh giá",
    "chua_toi_han": "Chưa tới ngày tạo nháp",
    "qua_han": "Hợp đồng đã kết thúc",
    "khong_nguoi_gui": "Chưa có người gửi mặc định (role EC CnB trống)",
    "nguoi_gui_trung": "Người gửi trùng chính nhân viên hoặc quản lý trực tiếp của họ - để C&B khác gửi",
}


def _hr():
    from ecentric_workspace.hr.hop_dong import repository
    return repository


def _vn(d):
    d = hd.as_date(d)
    return d.strftime("%d/%m/%Y") if d else "—"


def gen_title(doc):
    return ("Đánh giá %s - %s - đến %s" % ((doc.get("review_type") or "").lower(),
                                           doc.get("ten_nhan_vien") or doc.get("nhan_vien") or "",
                                           _vn(doc.get("hd_den_ngay"))))[:255]


def process_code_for(review_type):
    return PROCESS_HD if review_type == hd.DG_HOP_DONG else PROCESS_TV


def la_cnb(user, repo=None):
    repo = repo or default_repo
    return bool(set(repo.roles_of(user)) & set(CNB_ROLES))


def _require_cnb(user, repo=None):
    repo = repo or default_repo
    if not la_cnb(user, repo):
        frappe.throw(_("Chỉ C&B / HR thao tác được trên phiếu đánh giá nhân sự."), frappe.PermissionError)


def prepare_draft(document):
    """draft_preparer (luu nhap qua api chung): KHONG cho tao tay bang save_draft - phieu chi
    sinh ra tu bang hop dong (job hoac nut "Tao nhap" cua C&B, deu qua tao_nhap). Doi mau tieu chi
    tren nhap thi chup lai tieu chi."""
    if document.is_new() and not frappe.flags.get("ec_employee_review_auto"):
        frappe.throw(_("Phiếu đánh giá được tạo từ bảng hợp đồng trên hồ sơ (C&B: trang Hàng chờ "
                       "đánh giá) - không tạo tay."))
    if document.get("approval_request"):
        return
    truoc = None if document.is_new() else document.get_doc_before_save()
    if document.get("mau_tieu_chi") and (not truoc or truoc.get("mau_tieu_chi") != document.mau_tieu_chi):
        document.tieu_chi_json = json.dumps(default_repo.tieu_chi_cua_mau(document.mau_tieu_chi),
                                            ensure_ascii=False)


# --------------------------------------------------------------------------- tao nhap --

def kiem_du_lieu(nv, rows, hom_nay, hr, ngay_le=(), bo_qua_cua_so=False):
    """-> (ly_do | None, ngu canh). Dung chung cho job, nut "Tao nhap" va hang cho."""
    ctx = {}
    if not nv or nv.get("status") != "Active":
        return "nv_nghi", ctx
    row = hd.dong_hien_hanh(rows, hom_nay)
    loai = hd.loai_danh_gia(row)
    ctx.update(row=row, loai=loai)
    if not loai:
        return "khong_can", ctx
    den = hd.as_date(row.get("den_ngay"))
    if not den:
        return "thieu_ngay", ctx
    if den < hom_nay:
        return "qua_han", ctx
    ctx["ngay_nhap"] = hd.ngay_tao_nhap(loai, den, ngay_le)
    ctx["ngay_gui"] = hd.ngay_tu_gui(loai, den, ngay_le)
    if not bo_qua_cua_so and hom_nay < ctx["ngay_nhap"]:
        return "chua_toi_han", ctx
    user = nv.get("user_id")
    if not user or not hr.user_dang_hoat_dong(user):
        return "thieu_tai_khoan", ctx
    lm = hr.quan_ly_truc_tiep(nv["name"])
    if not lm:
        return "thieu_lm", ctx
    if lm == user:
        return "lm_la_nv", ctx
    ctx["lm"] = lm
    return None, ctx


def khoa(nhan_vien, loai, den_ngay):
    return "%s|%s|%s" % (nhan_vien, loai, hd.as_date(den_ngay))


def tao_nhap(nhan_vien, actor=None, auto=False, hom_nay=None, repo=None, hr=None):
    """Tao NHAP danh gia cho mot nhan vien tu dong hop dong hien hanh. Idempotent theo khoa
    (nhan vien, loai, ngay ket thuc). -> {"ok", "name", "duplicate", "ly_do"}."""
    repo = repo or default_repo
    hr = hr or _hr()
    hom_nay = hd.as_date(hom_nay) or repo.today()
    ngay_le = repo.ngay_le()
    nv = hr.nhan_vien(nhan_vien)
    rows = (hr.hop_dong_cua([nhan_vien]) or {}).get(nhan_vien) or []
    ly_do, ctx = kiem_du_lieu(nv, rows, hom_nay, hr, ngay_le, bo_qua_cua_so=not auto)
    if ly_do:
        return {"ok": False, "ly_do": ly_do, "ly_do_text": LY_DO.get(ly_do, ly_do)}
    row, loai = ctx["row"], ctx["loai"]
    key = khoa(nhan_vien, loai, row["den_ngay"])
    old = repo.review_by_key(key)
    if old:
        return {"ok": True, "name": old, "duplicate": True}
    cfg = repo.settings()
    # Nguoi gui KHONG duoc la chinh nhan vien hoac LM cua ho: engine loai nguoi gui khoi cap duyet
    # (Dot 0 chan tu duyet) -> mat buoc tu danh gia / nhan xet (tich hop 23/11).
    tranh = (nv.get("user_id"), ctx.get("lm"))
    nguoi_gui = actor if (actor and not auto) else repo.nguoi_gui_mac_dinh(cfg, tranh=tranh)
    if nguoi_gui and nguoi_gui in [t for t in tranh if t]:
        return {"ok": False, "ly_do": "nguoi_gui_trung", "ly_do_text": LY_DO["nguoi_gui_trung"]}
    if not nguoi_gui:
        return {"ok": False, "ly_do": "khong_nguoi_gui", "ly_do_text": LY_DO["khong_nguoi_gui"]}
    mau, tieu_chi = repo.mau_tieu_chi(loai)
    ngay_gui = max(ctx["ngay_gui"], hom_nay) if ctx.get("ngay_gui") else hom_nay
    fields = {
        "approval_type": APPROVAL_TYPE, "review_type": loai, "nhan_vien": nhan_vien,
        "ten_nhan_vien": nv.get("employee_name"), "employee_user": nv.get("user_id"),
        "phong_ban_nv": nv.get("department"), "chuc_danh": nv.get("designation"),
        "line_manager": ctx["lm"], "dong_hop_dong": row.get("name"),
        "loai_hop_dong": row.get("loai_hop_dong"), "hd_tu_ngay": row.get("tu_ngay"),
        "hd_den_ngay": row.get("den_ngay"), "dedupe_key": key, "requested_by": nguoi_gui,
        "auto_draft": 1 if auto else 0, "draft_created_on": hom_nay, "auto_submit_on": ngay_gui,
        "mau_tieu_chi": mau, "tieu_chi_json": json.dumps(tieu_chi, ensure_ascii=False),
        "company": nv.get("company"),
    }
    fields["request_title"] = gen_title(fields)
    name = repo.insert_review(fields)
    return {"ok": True, "name": name, "duplicate": False, "auto_submit_on": str(ngay_gui)}


# ------------------------------------------------------------------------------ gui --

def submit(name, repo=None, hr=None):
    """C&B bam Gui (submitter cua definition). C&B khac nguoi gui hien tai -> nhan nhap ve minh."""
    repo = repo or default_repo
    actor = frappe.session.user
    _require_cnb(actor, repo)
    doc = repo.get_review(name, for_update=True)
    if doc.approval_request:
        frappe.throw(_("Phiếu đánh giá này đã được gửi."))
    if doc.da_huy_nhap:
        frappe.throw(_("Nháp này đã bị huỷ."))
    doc.requested_by = actor
    doc.auto_draft = 0
    return _gui(doc, repo, hr)


def _gui(doc, repo=None, hr=None):
    """Kiem lai du lieu SONG (LM co the da doi tu luc tao nhap), roi gui qua engine:
    engine.submit(activate_first_level=False) -> khoi phuc cap NV / LM bi luat gop-trung-nguoi
    bo (LM = CEO) -> kich hoat cap 1."""
    repo = repo or default_repo
    hr = hr or _hr()
    nv = hr.nhan_vien(doc.nhan_vien)
    if not nv or nv.get("status") != "Active":
        frappe.throw(_(LY_DO["nv_nghi"]))
    user = nv.get("user_id")
    if not user or not hr.user_dang_hoat_dong(user):
        frappe.throw(_(LY_DO["thieu_tai_khoan"]))
    lm = hr.quan_ly_truc_tiep(doc.nhan_vien)
    if not lm:
        frappe.throw(_("Nhân viên chưa có Line Manager đang hoạt động - cập nhật hồ sơ "
                       "(Người quản lý) rồi gửi lại."))
    if lm == user:
        frappe.throw(_(LY_DO["lm_la_nv"]))
    doc.employee_user = user
    doc.line_manager = lm
    doc.submitted_at = repo.now()
    repo.save(doc)
    req = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, doc.requested_by,
                        process_code=process_code_for(doc.review_type), activate_first_level=False)
    repo.khoi_phuc_cap_bi_bo(req, (CAP_NV, CAP_LM), _(
        "Giữ cấp: tự đánh giá và nhận xét của quản lý là bước bắt buộc của đánh giá nhân sự, "
        "không gộp vào cấp CEO dù cùng một người (Hoàn chốt 22/11)."))
    repo.kich_hoat_cap_dau(req)
    repo.set_review(doc.name, {"approval_request": req})
    return req


def resubmit(name, actor=None):
    doc = default_repo.get_review(name)
    if not doc.approval_request:
        frappe.throw(_("Phiếu chưa được gửi."))
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=False)
    return {"restarted": False}


def nhan_nhap(name, repo=None):
    """C&B nhan mot nhap (tu tao) ve minh de sua / gui. Ghi qua doc.save -> Version (audit)."""
    repo = repo or default_repo
    actor = frappe.session.user
    _require_cnb(actor, repo)
    doc = repo.get_review(name, for_update=True)
    if doc.approval_request or doc.da_huy_nhap:
        frappe.throw(_("Chỉ nhận được nháp chưa gửi."))
    if doc.requested_by != actor:
        doc.requested_by = actor
        repo.save(doc)
    return {"name": doc.name, "requested_by": actor}


def huy_nhap(name, ly_do, repo=None):
    repo = repo or default_repo
    actor = frappe.session.user
    _require_cnb(actor, repo)
    if not (ly_do or "").strip():
        frappe.throw(_("Vui lòng ghi lý do huỷ nháp."))
    doc = repo.get_review(name, for_update=True)
    if doc.approval_request:
        frappe.throw(_("Phiếu đã gửi - dùng nút Huỷ yêu cầu trên phiếu."))
    doc.da_huy_nhap = 1
    doc.ly_do_huy_nhap = ly_do.strip()[:500]
    repo.save(doc)
    return {"name": doc.name, "da_huy_nhap": 1}


# ------------------------------------------------------------------- hanh dong tung cap --

def _tieu_chi(doc):
    return default_repo.json_load(doc.get("tieu_chi_json"), [])


def _dong_va_lich_su(doc, hr=None):
    hr = hr or _hr()
    rows = (hr.hop_dong_cua([doc.nhan_vien]) or {}).get(doc.nhan_vien) or []
    dong = next((r for r in rows if r.get("name") == doc.dong_hop_dong), None) or {
        "name": doc.dong_hop_dong, "loai_hop_dong": doc.loai_hop_dong,
        "tu_ngay": doc.hd_tu_ngay, "den_ngay": doc.hd_den_ngay}
    # Danh gia chup ngay luc tao: dung ngay cua PHIEU (ho so co the vua duoc sua sau do).
    dong = dict(dong, tu_ngay=doc.hd_tu_ngay or dong.get("tu_ngay"),
                den_ngay=doc.hd_den_ngay or dong.get("den_ngay"))
    return dong, rows


def lua_chon_cho(doc, repo=None, hr=None):
    repo = repo or default_repo
    hr = hr or _hr()
    dong, rows = _dong_va_lich_su(doc, hr)
    cfg = repo.settings()
    nv = hr.nhan_vien(doc.nhan_vien) or {}
    tran = luat.tran_thu_viec(nv, cfg.get("quy_tac"), cfg.get("tran_mac_dinh"))
    da_gh = repo.da_gia_han_thu_viec(doc.nhan_vien) if doc.review_type == hd.DG_THU_VIEC else False
    return luat.lua_chon(doc.review_type, dong, rows, tran, da_gh), dong, rows


def _cap(doc, user, repo):
    return repo.cap_dang_cho_toi(doc.approval_request, user) if doc.approval_request else None


def _lm_nhap_o_cap_ceo(doc, cap, user, repo):
    """LM = CEO: neu engine van bo cap LM (vd sau "tra lai" engine ap lai luat gop trung nguoi),
    CEO nhap phan LM ngay o cap CEO - khong mat buoc nhan xet bat buoc."""
    return cap == CAP_CEO and (not doc.lm_ket_qua or user == doc.line_manager
                               or repo.level_status(doc.approval_request, CAP_LM) == "Skipped")


def nop_tu_danh_gia(name, payload=None, repo=None):
    repo = repo or default_repo
    user = frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = repo.get_review(name, for_update=True)
    if _cap(doc, user, repo) != CAP_NV or user != doc.employee_user:
        frappe.throw(_("Chỉ nhân viên được đánh giá mới tự đánh giá, ở bước tự đánh giá."),
                     frappe.PermissionError)
    try:
        diem = luat.diem_hop_le(data.get("nv_diem"), _tieu_chi(doc), bat_buoc=True)
    except luat.LoiDanhGia as e:
        frappe.throw(str(e))
    doc.nv_danh_gia_json = json.dumps(diem, ensure_ascii=False)
    doc.nv_nhan_xet = str(data.get("nv_nhan_xet") or "").strip()[:3000]
    doc.nv_gui_luc = repo.now()
    repo.save(doc)
    engine.approve(doc.approval_request, actor=user, comment=_(COMMENT_NV))
    return {"name": doc.name}


def nop_danh_gia_lm(name, payload=None, repo=None, hr=None):
    repo = repo or default_repo
    user = frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = repo.get_review(name, for_update=True)
    cap = _cap(doc, user, repo)
    o_cap_ceo = _lm_nhap_o_cap_ceo(doc, cap, user, repo)
    if cap != CAP_LM and not o_cap_ceo:
        frappe.throw(_("Bạn không ở bước đánh giá của quản lý trên phiếu này."), frappe.PermissionError)
    chon, _dong, _rows = lua_chon_cho(doc, repo, hr)
    try:
        clean = luat.kiem_danh_gia_lm(doc.review_type, data, chon, doc.hd_den_ngay, _tieu_chi(doc))
    except luat.LoiDanhGia as e:
        frappe.throw(str(e))
    clean["lm_danh_gia_json"] = json.dumps(clean["lm_danh_gia_json"], ensure_ascii=False)
    doc.update(clean)
    doc.lm_gui_luc = repo.now()
    doc.lm_boi = user
    repo.save(doc)
    if cap == CAP_LM:
        engine.approve(doc.approval_request, actor=user, comment=_(COMMENT_LM))
    return {"name": doc.name, "da_gui": cap == CAP_LM}


def approve(name, comment=None, repo=None):
    """Duong "Duyet" chung (nut form, duyet nhanh tren dien thoai). Cap 1 / 2 KHONG duyet
    chay duoc: phai nop noi dung qua nop_tu_danh_gia / nop_danh_gia_lm. Comment cua cap 1 / 2
    bi thay bang cau chung (nhat ky duyet khong an duoc voi nhan vien)."""
    repo = repo or default_repo
    user = frappe.session.user
    doc = repo.get_review(name)
    cap = _cap(doc, user, repo)
    if cap == CAP_NV:
        frappe.throw(_("Mở phiếu để tự đánh giá (chấm điểm từng tiêu chí) rồi bấm Gửi."))
    if cap == CAP_LM:
        frappe.throw(_("Mở phiếu để nhập kết quả và nhận xét của quản lý rồi bấm Gửi CEO."))
    if cap == CAP_CEO and not doc.lm_ket_qua:
        frappe.throw(_("Phiếu chưa có kết quả + nhận xét của quản lý - nhập phần quản lý trước khi duyệt."))
    engine.approve(doc.approval_request, actor=user, comment=comment)
    return {"name": doc.name}


def tra_lai(name, ly_do, repo=None):
    """LM tra lai NV (cap 2 -> 1); CEO tra lai LM (cap 3 -> 2). Engine chi co "yeu cau bo sung"
    (ve nguoi gui) nen di qua hai lenh cong khai cua engine: request_information (ghi nhat ky +
    tam dung SLA) roi resubmit tu cap dich. Noi dung ly do HIEN voi moi nguoi trong luong."""
    repo = repo or default_repo
    user = frappe.session.user
    if not (ly_do or "").strip():
        frappe.throw(_("Vui lòng ghi lý do trả lại."))
    doc = repo.get_review(name, for_update=True)
    cap = _cap(doc, user, repo)
    if cap not in (CAP_LM, CAP_CEO):
        frappe.throw(_("Chỉ quản lý (trả nhân viên) hoặc CEO (trả quản lý) mới trả lại được."),
                     frappe.PermissionError)
    if cap == CAP_CEO and user == doc.line_manager:
        frappe.throw(_("Bạn vừa là quản lý trực tiếp vừa là CEO - sửa phần quản lý ngay tại bước này."))
    dich = cap - 1
    nhan = _("nhân viên tự đánh giá lại") if dich == CAP_NV else _("quản lý trực tiếp đánh giá lại")
    engine.request_information(doc.approval_request, actor=user,
                               comment=_("Trả lại {0}: {1}").format(nhan, ly_do.strip()))
    repo.dat_cap_tra_lai(doc.approval_request, dich)
    engine.resubmit(doc.approval_request, actor=user, restart=False)
    return {"name": doc.name, "ve_cap": dich}


def reject(name, comment=None):
    frappe.throw(_("Đánh giá nhân sự không có Từ chối: kết quả (Đạt / Không đạt / Gia hạn...) "
                   "nằm trong phần đánh giá; không đồng ý thì Trả lại."))


# ------------------------------------------------------------------------- sau CEO --

def on_final_approval(name, repo=None, hr=None):
    """CEO duyet xong: chot ket qua + tao DE XUAT cap nhat ho so cho C&B (khong ghi ho so).
    Idempotent: da co ket qua thi thoi."""
    repo = repo or default_repo
    doc = repo.get_review(name, for_update=True)
    if doc.ket_qua:
        return
    dong, rows = _dong_va_lich_su(doc, hr)
    de_xuat = luat.de_xuat_ho_so(doc.review_type, doc.lm_ket_qua, dong, rows,
                                 doc.lm_thoi_han_hd, doc.lm_gia_han_den)
    doc.ket_qua = (doc.lm_ket_qua or "") + ((" - " + doc.lm_thoi_han_hd) if doc.lm_thoi_han_hd else "") \
        + ((" đến " + _vn(doc.lm_gia_han_den)) if doc.lm_gia_han_den else "")
    doc.ket_qua_luc = repo.now()
    doc.completed_at = doc.ket_qua_luc
    doc.ho_so_de_xuat_json = json.dumps(de_xuat, ensure_ascii=False, default=str)
    doc.ho_so_trang_thai = "Chờ C&B xác nhận" if de_xuat["kieu"] != "khong" else "Không cần cập nhật"
    repo.save(doc)
    cnb = sorted(set([doc.requested_by] + repo.users_with_roles(("EC CnB", "HR"))) - {None})
    nhan = engine.request_label(BUSINESS_DT, name)
    if doc.ho_so_trang_thai == "Chờ C&B xác nhận":
        engine.notify(cnb, _("Đánh giá đã duyệt - xác nhận cập nhật hồ sơ: {0}").format(nhan),
                      BUSINESS_DT, name)
    else:
        engine.notify(cnb, _("Đánh giá đã duyệt ({0}) - C&B làm thủ tục tiếp theo: {1}").format(
            doc.lm_ket_qua, nhan), BUSINESS_DT, name)
    engine.notify([doc.employee_user], _("Kết quả đánh giá của bạn đã có: {0}").format(nhan),
                  BUSINESS_DT, name)


def xac_nhan_ho_so(name, payload=None, repo=None, hr=None):
    """C&B xac nhan DE XUAT -> ghi ho so (doc.save Employee -> Version) + nhat ky phieu.
    payload (tuy chon) sua ngay / so HD cua dong moi truoc khi ghi."""
    repo = repo or default_repo
    actor = frappe.session.user
    _require_cnb(actor, repo)
    hr = hr or _hr()
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = repo.get_review(name, for_update=True)
    info = repo.request_info(doc.approval_request) or {}
    if info.get("approval_status") != "Approved":
        frappe.throw(_("Phiếu chưa được CEO duyệt."))
    if doc.ho_so_trang_thai != "Chờ C&B xác nhận":
        frappe.throw(_("Không có đề xuất cập nhật hồ sơ đang chờ xác nhận."))
    de_xuat = repo.json_load(doc.ho_so_de_xuat_json, {})
    values, sua = None, None
    if de_xuat.get("kieu") == "them_dong":
        values = dict(de_xuat.get("dong_moi") or {})
        for k in ("tu_ngay", "den_ngay", "so_hop_dong"):
            if data.get(k) not in (None, ""):
                values[k] = data[k]
        if data.get("khong_thoi_han") not in (None, ""):
            values["khong_thoi_han"] = 1 if int(data["khong_thoi_han"]) else 0
            if values["khong_thoi_han"]:
                values["den_ngay"] = None
        tu, den = hd.as_date(values.get("tu_ngay")), hd.as_date(values.get("den_ngay"))
        if not tu:
            frappe.throw(_("Thiếu ngày bắt đầu của hợp đồng mới."))
        if den and den < tu:
            frappe.throw(_("Ngày kết thúc phải sau ngày bắt đầu."))
        if not den and not values.get("khong_thoi_han"):
            frappe.throw(_("Hợp đồng xác định thời hạn phải có ngày kết thúc."))
    elif de_xuat.get("kieu") == "sua_den_ngay":
        s = de_xuat.get("sua") or {}
        den = hd.as_date(data.get("den_ngay") or s.get("den_ngay"))
        if not den:
            frappe.throw(_("Thiếu ngày gia hạn."))
        sua = (s.get("dong"), {"den_ngay": str(den)})
    hr.cap_dong_hop_dong(doc.nhan_vien, values=values, sua_dong=sua,
                         employment_type=de_xuat.get("employment_type"))
    doc.ho_so_trang_thai = "Đã cập nhật hồ sơ"
    doc.ho_so_xac_nhan_boi = actor
    doc.ho_so_xac_nhan_luc = repo.now()
    repo.save(doc)
    engine.log_action(doc.approval_request, "Commented", actor,
                      comment=_("C&B xác nhận cập nhật hồ sơ nhân sự ({0}).").format(
                          de_xuat.get("ghi_chu") or de_xuat.get("kieu")))
    return {"name": doc.name, "ho_so_trang_thai": doc.ho_so_trang_thai}


def huy_danh_gia_dang_mo(nhan_vien, ly_do, actor="Administrator", repo=None):
    """Huy moi danh gia DANG MO cua mot nhan vien (nhap -> danh dau huy; dang duyet -> engine.cancel).
    Goi tu luong nghi viec (Agent C) / job khi NV khong con Active. Khong nem loi tung phieu."""
    repo = repo or default_repo
    n = 0
    for r in repo.reviews({"nhan_vien": nhan_vien}):
        try:
            if not r.get("approval_request"):
                if not r.get("da_huy_nhap"):
                    repo.set_review(r["name"], {"da_huy_nhap": 1, "ly_do_huy_nhap": (ly_do or "")[:500]})
                    n += 1
                continue
            info = repo.request_info(r["approval_request"]) or {}
            if info.get("approval_status") in OPEN_STATUSES:
                engine.cancel(r["approval_request"], actor=actor, reason=ly_do or "Nhân viên nghỉ việc")
                n += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "employee_review.huy_danh_gia_dang_mo %s" % r.get("name"))
    return n


# ------------------------------------------------------------------- man hinh chi tiet --

def _quyen_xem(business, request, user, repo=None):
    repo = repo or default_repo
    get = business.get
    approved = bool(request and request.get("approval_status") == "Approved")
    req_name = request.get("name") if request else None
    return luat.xem_phan_lm(
        user, get("employee_user"), approved, repo.roles_of(user),
        approver_tu_cap_2=repo.la_nguoi_duyet_tu_cap(req_name, user, CAP_LM),
        la_nguoi_gui=(get("requested_by") == user))


def redact(biz, request):
    """business_redactor: bo phan LM / ket qua khoi man hinh nguoi khong duoc xem. Fail-closed."""
    try:
        ok = _quyen_xem(biz, request, frappe.session.user)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "employee_review.redact")
        ok = False
    if not ok:
        for f in luat.LM_FIELDS:
            biz.pop(f, None)


def review_block(business, request, repo=None, hr=None):
    """Ngu canh man hinh chi tiet: tieu chi, lich su hop dong, lua chon hop le (Dieu 20/25), vai
    tro nguoi xem, khao sat moc (da ap quyen), de xuat ho so. CHI DOC."""
    repo = repo or default_repo
    user = frappe.session.user
    hr = hr or _hr()
    xem_lm = _quyen_xem(business, request, user, repo)
    req_name = request.get("name") if request else None
    cap = repo.cap_dang_cho_toi(req_name, user) if req_name else None
    out = {"tieu_chi": repo.json_load(business.get("tieu_chi_json"), []),
           "nv_diem": repo.json_load(business.get("nv_danh_gia_json"), {}),
           "xem_lm": 1 if xem_lm else 0, "cap_cua_toi": cap or 0,
           "la_nv": 1 if user == business.get("employee_user") else 0,
           "la_cnb": 1 if la_cnb(user, repo) else 0,
           "lm_nhap_o_cap_ceo": 0, "lich_su_hd": [], "lua_chon": None, "khao_sat": [],
           "ho_so": None}
    # Lich su hop dong cua chinh NV - ai trong luong cung xem duoc (LM can de chon thoi han).
    rows = (hr.hop_dong_cua([business.get("nhan_vien")]) or {}).get(business.get("nhan_vien")) or []
    out["lich_su_hd"] = [{"loai_hop_dong": r.get("loai_hop_dong"), "tu_ngay": str(r.get("tu_ngay") or ""),
                          "den_ngay": str(r.get("den_ngay") or ""),
                          "khong_thoi_han": int(r.get("khong_thoi_han") or 0)} for r in rows]
    if xem_lm:
        out["lm_diem"] = repo.json_load(business.get("lm_danh_gia_json"), {})
        if cap in (CAP_LM, CAP_CEO):
            chon, _d, _r = lua_chon_cho(business, repo, hr)
            out["lua_chon"] = chon
            out["lm_nhap_o_cap_ceo"] = 1 if _lm_nhap_o_cap_ceo(business, cap, user, repo) else 0
        if business.get("ho_so_de_xuat_json"):
            out["ho_so"] = {"trang_thai": business.get("ho_so_trang_thai") or "",
                            "de_xuat": repo.json_load(business.get("ho_so_de_xuat_json"), {}),
                            "co_the_xac_nhan": 1 if (out["la_cnb"] and business.get("ho_so_trang_thai")
                                                     == "Chờ C&B xác nhận") else 0}
        try:
            from ecentric_workspace.surveys.application import ca_nhan
            out["khao_sat"] = ca_nhan.ket_qua_cho_danh_gia(
                user, repo.roles_of(user), business.get("employee_user"),
                is_admin="System Manager" in repo.roles_of(user))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "employee_review.review_block khao_sat")
    return {"danh_gia": out}


# ------------------------------------------------------------------- hang cho C&B --

def thieu_ngay_ket_thuc(hom_nay=None, repo=None, hr=None):
    """NV Probation / Intern / Full-time thieu dong hop dong hien hanh / thieu den_ngay."""
    repo = repo or default_repo
    hr = hr or _hr()
    hom_nay = hd.as_date(hom_nay) or repo.today()
    emps = hr.nhan_vien_dang_lam()
    rows_by = hr.hop_dong_cua([e["name"] for e in emps])
    out = []
    for e in emps:
        r = hd.thieu_ngay_ket_thuc(e, rows_by.get(e["name"]) or [], hom_nay)
        if r:
            out.append({"nhan_vien": e["name"], "ten": e.get("employee_name"),
                        "employment_type": e.get("employment_type"), "phong_ban": e.get("department"),
                        "ngay_vao": str(e.get("date_of_joining") or ""), "ly_do": r["ly_do"],
                        "goi_y_den_ngay": str(r["goi_y_den_ngay"] or "")})
    out.sort(key=lambda x: (x["ly_do"], x["ten"] or ""))
    return out


def hang_cho(hom_nay=None, repo=None, hr=None):
    """Trang C&B: nhap cho gui, thieu du lieu (khong tao duoc phieu), cho xac nhan ho so, dang chay
    (chi ten buoc + han - khong co noi dung danh gia), thieu ngay ket thuc."""
    repo = repo or default_repo
    actor = frappe.session.user
    _require_cnb(actor, repo)
    hr = hr or _hr()
    hom_nay = hd.as_date(hom_nay) or repo.today()
    ngay_le = repo.ngay_le()
    all_rows = repo.reviews(fields=["name", "request_title", "review_type", "nhan_vien", "ten_nhan_vien",
                                    "hd_den_ngay", "auto_submit_on", "approval_request", "requested_by",
                                    "da_huy_nhap", "auto_draft", "ho_so_trang_thai", "dedupe_key"])
    st = repo.request_statuses([r["approval_request"] for r in all_rows])
    lv = repo.level_names([r["approval_request"] for r in all_rows])
    nhap, dang_chay, cho_ho_so = [], [], []
    for r in all_rows:
        if not r.get("approval_request"):
            if not r.get("da_huy_nhap"):
                nhap.append(r)
            continue
        s = st.get(r["approval_request"]) or {}
        if s.get("approval_status") in OPEN_STATUSES:
            l = lv.get((r["approval_request"], s.get("current_level"))) or {}
            dang_chay.append(dict(r, trang_thai=s.get("approval_status"), buoc=l.get("level_name") or "",
                                  han=str(l.get("due_at") or "")[:16]))
        elif s.get("approval_status") == "Approved" and r.get("ho_so_trang_thai") == "Chờ C&B xác nhận":
            cho_ho_so.append(r)
    keys = {r.get("dedupe_key") for r in all_rows}
    thieu = []
    emps = hr.nhan_vien_dang_lam()
    rows_by = hr.hop_dong_cua([e["name"] for e in emps])
    for e in emps:
        ly_do, ctx = kiem_du_lieu(e, rows_by.get(e["name"]) or [], hom_nay, hr, ngay_le)
        if ly_do in ("thieu_lm", "thieu_tai_khoan", "lm_la_nv"):
            k = khoa(e["name"], ctx["loai"], ctx["row"]["den_ngay"])
            if k not in keys:
                thieu.append({"nhan_vien": e["name"], "ten": e.get("employee_name"), "loai": ctx["loai"],
                              "den_ngay": str(ctx["row"]["den_ngay"]), "ly_do": LY_DO[ly_do]})
    return {"nhap": nhap, "thieu_du_lieu": thieu, "cho_ho_so": cho_ho_so, "dang_chay": dang_chay,
            "thieu_ngay": thieu_ngay_ket_thuc(hom_nay, repo, hr)}


def tao_nhap_tay(nhan_vien):
    """Nut "Tao nhap" cua C&B tren trang hang cho (bo qua cua so D-21, van chan trung)."""
    actor = frappe.session.user
    _require_cnb(actor)
    res = tao_nhap(nhan_vien, actor=actor, auto=False)
    if not res.get("ok"):
        frappe.throw(_("Không tạo được phiếu: {0}").format(res.get("ly_do_text") or res.get("ly_do")))
    return res
