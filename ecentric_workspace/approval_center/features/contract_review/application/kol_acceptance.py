# Copyright (c) 2026, eCentric and contributors
"""Cac dot nghiem thu (BBNT) cua hop dong KOL/KOC va tran chi cho DNTT.

Luat chot 11/11/2026:
  * BBNT chi tao khi hop dong da duyet xong VA da ky du. BBNT di cung chuoi ky voi hop dong
    (KTTH -> KTT -> CEO ky -> creator ky); truoc giai doan 4 thi ky tren cong roi tai ban da
    ky len, bam "Hoàn tất".
  * Han thanh toan = ngay hoan tat + so ngay cua hop dong (ngay lich, T7/CN doi sang thu Hai).
  * DNTT: coc duoc chi khi DA KY; phan con lai chi theo BBNT da hoan tat. Mot hop dong nhan
    nhieu dot (hoa hong affiliate theo thang).

PO chot 24/11/2026 (claude/thiet-ke-bbnt-tung-dot.md): moi dot la MOT phieu `EC KOL Acceptance`
(kho kol_rounds) co chuoi duyet rieng KOL_ACCEPTANCE (Ke toan tong hop -> Ke toan truong -> CEO).
"Gui duyet" thay "Danh dau da gui ky"; tai ban ky chi khi dot da duyet xong. Dot bi Tu choi / Huy
khong tinh vao ke hoach, gui duyet lai duoc (yeu cau moi).
"""
import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup, kol_rounds
from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
    APPROVED, approval_status, can_manage, creator_row, is_signed)
from ecentric_workspace.approval_center.features.contract_review.domain import kol, kol_calc, kol_values


def _load(name, user):
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc) or not can_manage(doc, user):
        frappe.throw(_("Chỉ người tạo hợp đồng hoặc Kế toán được thao tác nghiệm thu."),
                     frappe.PermissionError)
    return doc


def _row(doc, row_name):
    """Document cua dot (ghi) - dot phai thuoc hop dong `doc`."""
    return kol_rounds.get(doc, row_name)


def _no(row):
    return row.get("round_no") or row.get("idx")


def done_amount(doc):
    return sum(flt(r.amount) for r in kol_rounds.rows(doc) if r.status == kol.BBNT_DONE)


def _planned(doc, exclude=None):
    """Coc + cac dot con hieu luc (dot bi tu choi / huy khong tinh - PO 24/11)."""
    return kol_rounds.planned_amount(doc, exclude) + flt(doc.get("advance_amount"))


def _check_cap(doc, amount, exclude=None):
    planned = _planned(doc, exclude)
    if planned + flt(amount) > flt(doc.payable_amount) + 0.5:
        frappe.throw(_("Vượt số tiền trả creator ({0}): sau cọc và các đợt đã tạo, đợt này tối đa {1}.")
                     .format(kol.fmt_money(doc.payable_amount),
                             kol.fmt_money(max(flt(doc.payable_amount) - planned, 0))))


def _payee_note(doc, row_idx):
    """PO 17/11 (D): STK creator doi sau khi ky ma Ke toan chua xac nhan -> ghi canh bao (khong chan)."""
    from ecentric_workspace.approval_center.features.contract_review.application import kol_access
    if kol_access.payee_changed(doc):
        doc.add_comment("Info", _("Cảnh báo: tài khoản nhận tiền của creator đã đổi so với lúc gửi phiếu "
                                  "(BBNT đợt {0}). Kế toán kiểm thông tin creator rồi bấm \"Xác nhận tài khoản "
                                  "mới\" trước khi chi.").format(row_idx))
        return True
    return False


def add_acceptance(name, user, description, acceptance_date=None, amount=None):
    doc = _load(name, user)
    from ecentric_workspace.approval_center.features.contract_review.application import kol_access
    kol_access.require_open(doc)
    if approval_status(doc) != APPROVED or not is_signed(doc):
        frappe.throw(_("Chỉ tạo BBNT khi hợp đồng đã duyệt xong và đã ký đủ hai bên."))
    amount = flt(amount)
    if not amount > 0:                     # "not >" bat ca nan
        frappe.throw(_("Số tiền đợt nghiệm thu phải lớn hơn 0."))
    if abs(amount - round(amount)) > 1e-6:
        # QC 15/11 (C7): 3 x 333.333,5 qua san 0,5 nhung moi BBNT in 333.334 -> tong in 1.000.002.
        frappe.throw(_("Số tiền đợt nghiệm thu phải là số đồng chẵn (không có phần lẻ)."))
    _check_cap(doc, amount)
    acceptance_date = _check_acceptance_date(doc, acceptance_date or nowdate())
    row = kol_rounds.create(doc, {"description": (description or "").strip()[:140] or "Nghiệm thu",
                                  "acceptance_date": acceptance_date, "amount": amount,
                                  "status": kol.BBNT_DRAFT}, user)
    from ecentric_workspace.approval_center.features.contract_review.application import kol_files
    url, missing = kol_files.generate_acceptance(doc, row, creator_row(doc.creator))
    row.bbnt_file = url
    kol_rounds.save(row)
    # Vet: ai tao dot nao, bao nhieu tien (QC 18/11).
    doc.add_comment("Info", _("{0} tạo BBNT đợt {1}: {2} đ.").format(user, _no(row), "{:,.0f}".format(flt(amount)).replace(",", ".")))
    from ecentric_workspace.approval_center.features.contract_review.domain import kol_values
    return {"row": row.name, "bbnt_file": url, "missing": missing,
            "missing_labels": kol_values.missing_labels(missing)}


def _check_acceptance_date(doc, value):
    """Ngay in tren BBNT: khong truoc ngay ky hop dong, khong o tuong lai (QC3 12/11 - truoc do nhan
    bat ky ngay nao, BBNT co the ghi nghiem thu truoc khi ky hop dong)."""
    import datetime as _dt
    try:
        day = _dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        frappe.throw(_("Ngày nghiệm thu không hợp lệ."))
    today = _dt.date.fromisoformat(str(nowdate())[:10])
    if day > today:
        frappe.throw(_("Ngày nghiệm thu không được ở tương lai."))
    signed = str(doc.get("contract_date") or "")[:10]
    if signed and day < _dt.date.fromisoformat(signed):
        sd = _dt.date.fromisoformat(signed)
        # Live lam som hon lich (PO 12/11): BBNT ghi tu ngay ky tro di; chua toi ngay ky thi doi
        # (KOL khong lam phu luc - PO 17/11) - KHONG cho nghiem thu truoc khi co hop dong.
        if sd > today:
            frappe.throw(_("Hợp đồng ghi ngày ký {0}, sau hôm nay nên chưa lập BBNT được. Buổi làm sớm hơn "
                           "lịch: đợi tới ngày ký, hoặc báo Kế toán.").format(
                               sd.strftime("%d/%m/%Y")))
        frappe.throw(_("Ngày nghiệm thu ({0}) trước ngày ký hợp đồng ({1}). Chọn từ {1} tới hôm nay; "
                       "ngày BBNT không cần trùng ngày live.").format(day.strftime("%d/%m/%Y"),
                                                                      sd.strftime("%d/%m/%Y")))
    return str(day)


def delete_acceptance(name, user, row_name):
    """Xoa dot nghiem thu NHAP (nhap sai so tien / noi dung). Dot da gui duyet / hoan tat thi giu."""
    doc = _load(name, user)
    row = _row(doc, row_name)
    if row.status != kol.BBNT_DRAFT or row.get("approval_request"):
        # Dot da tung gui duyet: yeu cau duyet tro toi phieu nay (vet duyet) - khong xoa. Bi tu choi
        # thi khong tinh vao ke hoach nua; can so khac thi tao dot moi (PO 24/11 cau 4).
        frappe.throw(_("Chỉ xoá được đợt nghiệm thu còn nháp (chưa gửi duyệt)."))
    last = max([int(r.round_no or 0) for r in kol_rounds.rows(doc)] or [0])
    if int(row.round_no or 0) != last:
        # Xoa dot giua thi cac dot sau bi danh so lai, ma tep BBNT / goi ky cua chung da in "dot n" cu -
        # KE CA khi da thanh ly (QC vong cuoi 17/11). Dot nhap con lai khong anh huong tien duoc tra:
        # tran DNTT chi tinh dot da hoan tat.
        frappe.throw(_("Chỉ xoá được đợt nghiệm thu cuối cùng. Đợt nháp còn lại không làm thay đổi số "
                       "tiền được thanh toán (chỉ tính các đợt đã hoàn tất)."))
    idx, amount, bbnt, rname = _no(row), flt(row.amount), row.bbnt_file, row.name
    kol_rounds.delete(row)
    doc.add_comment("Info", _("Xoá đợt nghiệm thu nháp {0} ({1}).").format(idx, kol.fmt_money(amount)))
    from ecentric_workspace.approval_center.features.contract_review.application import kol_files
    kol_files._drop_generated(doc, bbnt, prefix="BBNT_", keep_if_sent=False)
    return {"deleted": rname}


def acceptance_remaining(doc):
    """So tien con chua dua vao dot nghiem thu nao (sau coc)."""
    return max(flt(doc.get("payable_amount")) - _planned(doc), 0.0)


def send_acceptance(name, user, row_name):
    """"Gui duyet" dot nghiem thu (PO 24/11/2026): kiem thieu thong tin creator voi du lieu HIEN TAI,
    sinh lai BBNT neu du lieu doi, roi gui chuoi KOL_ACCEPTANCE (KTTH -> KTT -> CEO). Duyet xong moi
    ky (cong ky so hoac ky tay roi tai ban ky). Gui lai duoc khi bi "Can bo sung" (tiep tuc yeu cau
    cu) hoac bi Tu choi / Huy (yeu cau moi)."""
    doc = _load(name, user)
    row = _row(doc, row_name)
    from ecentric_workspace.approval_center.features.contract_review.application import kol_access
    kol_access.require_open(doc)
    if approval_status(doc) != APPROVED or not is_signed(doc):
        frappe.throw(_("Chỉ gửi duyệt BBNT khi hợp đồng đã duyệt xong và đã ký đủ hai bên."))
    if (kol_rounds.lock(row.name) or None) != (row.get("approval_request") or None):
        frappe.throw(_("Đợt này vừa được gửi duyệt ở nơi khác - tải lại trang."))
    mode = _send_mode(doc, row)
    # Dot bi tu choi da ra khoi ke hoach; trong luc do co the da tao dot khac - kiem lai tran.
    _check_cap(doc, row.amount, exclude=row.name)
    # Tool cu khong cho BBNT con cho trong di ky; kiem lai voi du lieu HIEN TAI (creator co the
    # vua duoc bo sung) - thieu thi chan, kem nhan tieng Viet (QC 12/11).
    from ecentric_workspace.approval_center.features.contract_review.application import kol_files
    from ecentric_workspace.approval_center.features.contract_review.domain import kol_values
    content, missing = kol_files.acceptance_content(doc, row, creator_row(doc.creator))
    if missing:
        frappe.throw(_("BBNT đợt {0} còn thiếu: {1}. Bổ sung (thường là thông tin creator) rồi bấm gửi "
                       "lại - hệ thống tạo lại BBNT theo dữ liệu mới.").format(
            _no(row), ", ".join(kol_values.missing_labels(missing))))
    # Tep nguoi duyet xem = tep sinh tu du lieu HIEN TAI. Frappe gop tep trung noi dung -> du lieu
    # khong doi thi URL giu nguyen. URL doi: giu ca tep cu lam vet (QC3 12/11).
    old = row.bbnt_file
    new = kol_files.attach(doc, "BBNT_%s_dot%s.docx" % (kol_files._safe(doc.contract_no), _no(row)), content)
    regenerated = bool(old and new != old)
    row.bbnt_file = new
    req = _submit_round(doc, row, user, mode, restart=regenerated)
    if regenerated:
        # Khong ghi URL vao binh luan: ban du PII chi nguoi lap + nguoi tao creator + Ke toan tai (PO 17/11).
        doc.add_comment("Info", _("BBNT đợt {0} được tạo lại theo dữ liệu mới trước khi gửi duyệt (bản cũ vẫn "
                                  "đính kèm).").format(_no(row)))
    return {"status": row.status, "approval_request": req, "regenerated": regenerated,
            "bbnt_file": new, "payee_changed": _payee_note(doc, _no(row))}


def _send_mode(doc, row):
    """"new" (yeu cau duyet moi) / "resubmit" (tiep tuc sau "Can bo sung"); con lai bao loi."""
    view = kol_rounds.find(doc, row.name) or {}
    ap = view.get("approval_status") or ""
    if not row.get("approval_request"):
        if row.status != kol.BBNT_DRAFT:
            # Dot cu (truoc 24/11) da danh dau gui ky ngoai ERP: tai ban ky nhu truoc.
            frappe.throw(_("Đợt này đã gửi ký."))
        return "new"
    if ap == "Information Required":
        return "resubmit"
    if ap in kol_rounds.CLOSED_APPROVAL and row.status in (kol.BBNT_DRAFT, kol.BBNT_SENT):
        return "new"
    if ap == "Pending":
        frappe.throw(_("Đợt này đang chờ duyệt."))
    frappe.throw(_("Đợt này đã duyệt xong - ký rồi tải bản ký lên."))


def _engine():
    from ecentric_workspace.approval_center.shared.workflow import transitions
    return transitions


def _submit_round(doc, row, user, mode, restart=False):
    engine = _engine()
    if mode == "resubmit":
        row.status = kol.BBNT_SENT
        kol_rounds.save(row)
        # BBNT doi (thong tin creator vua bo sung) -> nguoi duyet truoc da duyet ban cu: duyet lai tu dau.
        engine.resubmit(row.approval_request, actor=user, restart=bool(restart))
        req = row.approval_request
        doc.add_comment("Info", _("{0} gửi duyệt lại BBNT đợt {1} sau khi bổ sung.").format(user, _no(row)))
    else:
        old_req = row.get("approval_request")
        row.requested_by = user
        row.submitted_at = now_datetime()
        row.status = kol.BBNT_SENT
        row.approval_request = None
        kol_rounds.save(row)
        req = engine.submit(kol_rounds.DT, row.name, kol_rounds.APPROVAL_TYPE, user)
        kol_rounds.set_values(row.name, {"approval_request": req})
        row.approval_request = req
        doc.add_comment("Info", (_("{0} gửi duyệt BBNT đợt {1} ({2}).") if not old_req else
                                 _("{0} gửi duyệt lại BBNT đợt {1} ({2}) - yêu cầu trước đã bị từ chối / huỷ."))
                        .format(user, _no(row), req))
    _grant_contract_view(doc, req, user)
    return req


def _grant_contract_view(doc, req, user):
    """Nguoi duyet dot (KTTH, KTT, CEO) mo duoc trang hop dong (the KOL, ban BBNT cua dot - PO 24/11
    cau 3): them ho lam NGUOI THEO DOI phieu hop dong (quyen doc, co vet, qua API engine). Loi khong
    chan viec gui duyet - nguoi duyet van duyet duoc o "Cho toi duyet"."""
    if not doc.get("approval_request") or not req:
        return
    try:
        users = sorted(set(frappe.get_all("EC Approval Request Approver", filters={"approval_request": req},
                                          pluck="approver") or []))
        _engine().add_watchers(doc.approval_request, users, actor=user, source="BBNT")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "kol bbnt grant view %s" % doc.name)


def complete_acceptance(name, user, row_name, signed_file):
    doc = _load(name, user)
    row = _row(doc, row_name)
    if row.status == kol.BBNT_DONE:
        frappe.throw(_("Đợt này đã hoàn tất."))
    if row.status == kol.BBNT_REVIEW:
        frappe.throw(_("Đợt này đang chờ Kế toán kiểm bản ký."))
    if row.status != kol.BBNT_SENT:
        # Bo qua buoc gui duyet = bo qua kiem thieu thong tin + tao lai BBNT + chuoi duyet (QC3, PO 24/11).
        frappe.throw(_("Bấm \"Gửi duyệt\" trước (hệ thống kiểm và tạo lại BBNT theo dữ liệu mới, rồi "
                       "Kế toán tổng hợp → Kế toán trưởng → CEO duyệt), rồi mới tải bản ký."))
    if row.get("approval_request") and (kol_rounds.find(doc, row.name) or {}).get("approval_status") != APPROVED:
        frappe.throw(_("Đợt này chưa duyệt xong (Kế toán tổng hợp → Kế toán trưởng → CEO) nên chưa tải bản ký."))
    if not is_signed(doc):
        frappe.throw(_("Hợp đồng chưa được xác nhận ký đủ."))
    if not (signed_file or "").lower().endswith(".pdf"):
        frappe.throw(_("Tải lên BBNT đã ký (PDF) trước khi hoàn tất."))
    used = {r.signed_file for r in kol_rounds.rows(doc) if r.name != row.name and r.signed_file}
    if signed_file in used or signed_file == doc.get("signed_file"):
        frappe.throw(_("Tệp này đã dùng cho hợp đồng hoặc đợt nghiệm thu khác. Tải BBNT đã ký của đợt này."))
    from ecentric_workspace.approval_center.features.contract_review.application.kol_files import claim_upload
    findings = finish_round(doc, row, claim_upload(doc, signed_file, user), now_datetime(), user)
    return {"status": row.status, "due_date": str(row.due_date), "findings": findings}


def finish_round(doc, row, signed_file, when, by):
    """Ghi ban BBNT ky xong cua mot dot (nguoi tai len, hoac nen tang ky so qua esign_hooks): han
    thanh toan + may kiem + vet. `row` = Document dot (kol_rounds). `by` = user (Link) hoac nhan nguon
    (vd "Ky so (cong)")."""
    row.signed_file = signed_file
    row.completed_at = when
    row.completed_by = by if (by and frappe.db.exists("User", by)) else None
    # Han thanh toan tinh tu NGAY KY XONG (ngay tai ban ky), ke ca khi Ke toan xac nhan sau.
    due = kol.due_date(when.date(), doc.payment_term_days, doc.get("creator_type"),
                       doc.get("platform"), kol_lookup.holidays())
    row.due_date = due
    from ecentric_workspace.approval_center.features.contract_review.application import kol_verify
    findings = kol_verify.apply_acceptance_check(doc, row)
    kol_rounds.save(row)
    no = _no(row)
    src = "" if row.completed_by else (" (%s)" % by if by else "")
    if findings:
        doc.add_comment("Info", _("BBNT đợt {0}{1}: bản ký - chờ Kế toán kiểm: {2}").format(
            no, src, "; ".join(findings)))
    else:
        doc.add_comment("Info", _("BBNT đợt {0}{1} hoàn tất (máy kiểm đạt), hạn thanh toán {2}.").format(
            no, src, due.strftime("%d/%m/%Y")))
    if not kol_lookup.holidays_cover(due):
        doc.add_comment("Info", _("Hạn thanh toán BBNT đợt {0} ({1}) chưa tính ngày lễ: chưa có lịch nghỉ lễ năm {2} "
                                  "- Kế toán cập nhật Holiday List rồi kiểm lại hạn.").format(
            no, due.strftime("%d/%m/%Y"), due.year))
    _payee_note(doc, no)
    return findings


def effective_advance(doc):
    """Tien coc duoc tinh vao tran chi. Ban ky TAI LEN / cong ky ghi nhan SAU khi thanh ly: khong mo coc
    (QC ban do 17/11). Ban ky da co TRUOC khi thanh ly (Ke toan xac nhan sau) van tinh: hop dong da ky
    truoc khi dung."""
    closed = doc.get("kol_closed_at")
    if closed and (not doc.get("signed_at") or str(doc.get("signed_at")) > str(closed)):
        return 0.0
    return flt(doc.get("advance_amount"))


def payable_cap(doc):
    """Tran chi hien tai cho DNTT (truoc khi tru phan da de nghi)."""
    if approval_status(doc) != APPROVED:
        return 0.0
    return kol.acceptance_cap(is_signed(doc), effective_advance(doc), done_amount(doc), doc.get("payable_amount"))


def rows_view(doc):
    base = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc or {})
    return [{"name": r.name, "idx": r.idx, "description": r.description,
             "acceptance_date": str(r.acceptance_date or ""), "amount": flt(r.amount),
             "status": r.status, "bbnt_file": r.bbnt_file, "signed_file": r.signed_file,
             "completed_at": str(r.completed_at or ""), "due_date": str(r.due_date or ""),
             "check_note": r.get("check_note") or "", "verified_by": r.get("verified_by") or "",
             "completed_by": r.get("completed_by") or "", "calc": _round_calc(doc, kol_rounds.contract_view(doc, keep=r.name, base=base), r),
             # Chuoi duyet rieng cua dot (PO 24/11): trang thai + nut "Gui duyet" / "Gui duyet lai".
             "approval_request": r.get("approval_request") or "",
             "approval_status": r.get("approval_status") or "",
             "can_send": _can_send(r)}
            for r in kol_rounds.rows(doc)]


def _can_send(r):
    if not r.get("approval_request"):
        return r.get("status") == kol.BBNT_DRAFT
    return (r.get("approval_status") == "Information Required"
            or (kol_rounds.is_closed(r) and r.get("status") in (kol.BBNT_DRAFT, kol.BBNT_SENT)))


def _round_calc(doc, cv, row):
    try:
        # Dot phu het hop dong: BBNT in so cua CA hop dong (kol_values.is_whole_round) -> bang tinh
        # cung lay so da luu cua hop dong, khong quy nguoc tu so dot (lech 1d - QC6 12/11).
        if kol_values.is_whole_round(cv, flt(row.amount)):
            return kol_calc.contract_steps(doc)
        return kol_calc.round_steps(doc.get("creator_type"), flt(row.amount), doc.get("pit_rate"),
                                    doc.get("vat_rate"), cv, dict(row))
    except Exception:
        return []                 # bang tinh chi de soat: loi du lieu cu khong lam hong trang chi tiet


def funding_view(doc):
    from ecentric_workspace.approval_center.features.payment_request.application import funding
    cap = payable_cap(doc)
    used = funding.consumed_amount(kol_lookup.CR_DT, doc.name)
    return {"payable": flt(doc.payable_amount), "advance": effective_advance(doc),
            "accepted": done_amount(doc), "cap": cap, "used": used, "remaining": cap - used}


def round_contract(round_name, user):
    """Link "mo trang day du" cua phieu dot (route KOL_ACCEPTANCE = trang Hop dong ?id=EC-BBNT-...) ->
    {contract, round} de trang mo dung hop dong. Chi nguoi xem duoc phieu dot (nguoi lap, nguoi duyet,
    nguoi theo doi, SM)."""
    row = frappe.db.get_value(kol_rounds.DT, round_name, ["name", "contract", "requested_by", "approval_request"],
                              as_dict=True) if round_name else None
    if not row:
        frappe.throw(_("Không tìm thấy đợt nghiệm thu."))
    from ecentric_workspace.approval_center.shared.workflow.permissions import can_view_request
    if not can_view_request(row.approval_request, user=user, business_doctype=kol_rounds.DT,
                            requested_by=row.requested_by, approval_type=kol_rounds.APPROVAL_TYPE,
                            business_name=row.name):
        frappe.throw(_("Bạn không có quyền xem đợt nghiệm thu này."), frappe.PermissionError)
    return {"contract": row.contract, "round": row.name}
