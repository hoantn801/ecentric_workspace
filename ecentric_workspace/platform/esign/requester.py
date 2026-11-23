# Copyright (c) 2026, eCentric and contributors
"""Governed REQUESTER Submit & Sign lifecycle (Option B).

The requester signs BEFORE Approval Level 1 becomes actionable. This is NOT an approval
level: the request + frozen snapshot already exist (created at submit with
`activate_first_level=False`), Level 1 is inactive (no ToDo/notification), and only a
confirmed requester signature atomically activates Level 1 exactly once. The requester is
resolved dynamically from `EC Approval Request.requested_by`; identity comes only from the
requester's Active + Verified `EC SCTS User Mapping`; there is NO Administrator/System
Manager bypass. The approver path (approve_and_sign -> verify_and_complete -> engine.approve)
is untouched - a requester DSR carries `actor_type="Requester"` and completes here, never
through `engine.approve()`.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.platform.esign import events, guard, hashing
from ecentric_workspace.platform.esign import package as pkgsvc
from ecentric_workspace.platform.esign import permissions as perms

DSR = "EC Digital Signature Request"
AR = "EC Approval Request"
PKG = "EC Digital Signature Package"
DSF = "EC Digital Signature File"  # canonical package-file DocType (as in signed_files/pilot/review)
# request may (re)start requester signing from these states (retry-safe).
_START_STATES = ("Pending", "Reconciliation Required", "Failed")
# a DSR that still holds/represents a live or completed provider job.
_LIVE_OR_DONE = ("Draft", "Prepared", "Queued", "Provider Accepted", "Verifying",
                 "Signed", "Approval Completed")


def _profile_and_settings(business_doctype, approval_type, business_name=None):
    pname = guard.get_enabled_profile(business_doctype, approval_type, business_name)
    if not pname:
        return None, None, None
    prof = frappe.db.get_value("EC Digital Signature Profile", pname,
                               ["provider", "environment"], as_dict=True)
    st = frappe.db.get_value("EC Digital Signature Provider Settings",
                             {"provider": prof.provider, "environment": prof.environment},
                             "*", as_dict=True) or {}
    return pname, prof, st


def _draft_approval_type(business_doctype, business_name):
    """Loai yeu cau cua mot phieu CHUA GUI. Truong `approval_type` thuong trong o ban nhap
    (Payment Request 00052: undefined), nen truoc day panel nguoi de nghi khong hien gi truoc
    khi gui - ke ca o ket noi tai khoan SCTS, dung luc nguoi dung can no nhat (Hoan 04/09).
    Khi loai doctype nay chi co DUNG MOT profile ky so dang bat thi dung loai yeu cau cua
    profile do; nhieu hon mot thi khong doan."""
    at = frappe.db.get_value(business_doctype, business_name, "approval_type") \
        if frappe.db.has_column(business_doctype, "approval_type") else None
    if at:
        return at
    # DISTINCT: hop dong co nhieu ho so (moi quy trinh mot ho so) nhung cung MOT loai yeu cau -
    # dem dong ho so thi luon >1 va panel nhap khong bao gio hien (12/11).
    rows = sorted(set(frappe.get_all("EC Digital Signature Profile",
                                     filters={"business_doctype": business_doctype, "enabled": 1},
                                     pluck="approval_type", limit_page_length=20)))
    return rows[0] if len(rows) == 1 else None


def link_context(business_doctype, business_name):
    """(settings, environment) de ket noi tai khoan SCTS cho phieu nay - truoc hay sau khi
    gui deu duoc. Nguoi goi phai xem duoc phieu; khong co cau hinh ky so thi bao ro."""
    perms.assert_can_view_business(business_doctype, business_name)
    ar = perms.business_approval_request(business_doctype, business_name)
    if ar:
        at = frappe.db.get_value(AR, ar, "approval_type")
    else:
        at = _draft_approval_type(business_doctype, business_name)
    _p, prof, st = (_profile_and_settings(business_doctype, at, business_name) if at
                    else (None, None, None))
    if not prof or not st:
        frappe.throw(_("Loại yêu cầu này chưa cấu hình ký số."))
    return st, prof.environment


def requester_signing_readiness(business_doctype, business_name):
    """Read-only, fail-closed readiness for the requester Submit & Sign action."""
    perms.assert_can_view_business(business_doctype, business_name)
    ar = perms.business_approval_request(business_doctype, business_name)
    checks = {}
    if not ar:
        # Pre-submission: report whether this request type WILL require the requester's
        # signature so the panel can show a clear 'not yet signable' note to the owner instead
        # of nothing. approval_type is often blank on the un-submitted business doc; when it is,
        # requester_signature_required stays False (we do not guess).
        owner = frappe.db.get_value(business_doctype, business_name, "owner")
        at = _draft_approval_type(business_doctype, business_name)
        checks["not_submitted"] = True
        checks["is_owner"] = (frappe.session.user == owner)
        checks["requester_signature_required"] = bool(
            at and guard.requester_signature_required(business_doctype, at, business_name))
        # Cho chu phieu ket noi tai khoan SCTS NGAY TU TRUOC KHI GUI - de luc bam Gui khong
        # bi chan quay lai. Chi tinh khi da biet loai yeu cau (co profile/settings).
        if checks["is_owner"] and checks["requester_signature_required"]:
            _p, prof0, st0 = _profile_and_settings(business_doctype, at, business_name)
            if prof0 and st0:
                from ecentric_workspace.platform.esign import user_link
                ls = user_link.link_status(owner, st0, prof0.environment)
                checks["scts_link_required"] = bool(ls["needs_link"])
                checks["scts_linked"] = bool(not ls["needs_link"] or ls["linked"])
                checks["scts_link_days_left"] = ls["days_left"]
        return {"ready": False, "reasons": ["not_submitted"], "checks": checks,
                "stage": "Not Submitted"}
    req = frappe.db.get_value(AR, ar, ["approval_type", "current_level", "approval_status",
                                       "requester_signature_status", "requested_by"], as_dict=True)
    pname, prof, st = _profile_and_settings(business_doctype, req.approval_type, business_name)
    checks["signing_enabled"] = bool(pname)
    checks["requester_signature_required"] = bool(
        pname and guard.requester_signature_required(business_doctype, req.approval_type,
                                                     business_name))
    checks["is_requester"] = frappe.session.user == req.requested_by
    checks["pending_requester_signature"] = req.requester_signature_status in _START_STATES
    # Dang cho nha cung cap xac nhan. Phai bao ra rieng: panel truoc day chi hien khi trang
    # thai nam trong _START_STATES, nen ngay sau khi bam "Trinh ky" (-> Processing) no TU AN,
    # mang theo ca nhan "dang cho" - dung luc nguoi dung can nhin nhat. Hoan bao 28/08: bam
    # xong 3-4 phut khong thay gi.
    checks["requester_signature_processing"] = req.requester_signature_status == "Processing"
    mapping = perms.verified_mapping(req.requested_by, prof.environment) if prof else None
    checks["verified_mapping"] = bool(mapping)
    # Ket noi tai khoan SCTS cua CHINH nguoi de nghi (04/09). Chi doc cho nguoi dang xem la
    # nguoi de nghi - trang thai ket noi cua nguoi khac khong phai viec cua ai.
    from ecentric_workspace.platform.esign import user_link
    if prof and st and checks["is_requester"]:
        ls = user_link.link_status(req.requested_by, st, prof.environment)
        checks["scts_link_required"] = bool(ls["needs_link"])
        checks["scts_linked"] = bool(not ls["needs_link"] or ls["linked"])
        checks["scts_link_days_left"] = ls["days_left"]
    from ecentric_workspace.platform.esign import binding
    checks["provider_environment_ok"] = bool(
        prof and prof.environment in binding.ALLOWED_ENVIRONMENTS
        and (prof.environment != "Production" or (st and st.get("allow_production_signing"))))
    # execution gates (fail-closed for the ACTION; deferral already happened at submit).
    checks["gates_enabled"] = bool(st and st.get("integration_enabled")
                                   and st.get("allow_document_creation")
                                   and st.get("allow_signing"))
    pkg_name = pkgsvc.active_package_for_request(ar)
    pkg = frappe.db.get_value(PKG, pkg_name, ["status", "package_hash"], as_dict=True) if pkg_name else None
    checks["package_active_hash_valid"] = bool(
        pkg and pkg.status == "Active" and pkg.package_hash
        and pkgsvc.compute_hash(pkg_name) == pkg.package_hash)
    checks["placements_complete"] = bool(pkg_name and not pkgsvc.preflight_for_lock(pkg_name))
    # --- ADDITIVE (requester panel state mapping only) ---------------------------------
    # The requester package follows a LOCAL lifecycle (Draft -> Locked) while the write
    # gates are OFF; it never reaches "Active" (only the provider worker sets "Active",
    # which needs Signing ON). The Active-scoped keys above are left byte-identical so
    # `ready`/`reasons` are unchanged; the keys below let the requester UI represent the
    # four local states (no package / placement incomplete / ready to lock / locked)
    # WITHOUT coupling to the gates. Resolve the current requester package for this
    # business doc across statuses (the draft carries business_doctype/business_name and
    # lock_package preserves them), newest non-terminal first.
    cur_name = pkgsvc.active_package_for_request(ar) or frappe.db.get_value(
        PKG, {"business_doctype": business_doctype, "business_name": business_name,
              "status": ["not in", ("Cancelled", "Superseded", "Completed")]},
        "name", order_by="creation desc")
    cur = frappe.db.get_value(PKG, cur_name, ["status", "package_hash"],
                              as_dict=True) if cur_name else None
    checks["package_present"] = bool(cur)
    _req_complete = bool(cur_name and pkgsvc.requester_placements_complete(cur_name))
    # A VALID lock = locked/active AND has >=1 requester placement. A locked package with zero
    # placements is INVALID (never "ready", never a normal "locked") and needs recovery.
    checks["package_locked"] = bool(
        cur and cur.status in ("Locked", "Active") and cur.package_hash and _req_complete)
    checks["package_invalid"] = bool(
        cur and cur.status in ("Locked", "Active") and not _req_complete)
    # Ready to lock ONLY when the Draft actually carries a requester placement.
    checks["placements_ready"] = bool(cur_name and cur and cur.status == "Draft"
                                      and _req_complete)
    required = ["signing_enabled", "requester_signature_required", "is_requester",
                "pending_requester_signature", "verified_mapping", "provider_environment_ok",
                "gates_enabled", "package_active_hash_valid", "placements_complete"]
    ready = all(checks.get(k) for k in required)
    return {"ready": ready, "reasons": [k for k in required if not checks.get(k)],
            "checks": checks, "current_status": req.requester_signature_status}


#: preflight_for_lock tra ve MA MAY ("missing_placement:L2:hoa-don.pdf"). Nem thang ma do
#: vao mat nguoi de nghi thi ho khong biet phai lam gi. Ma khong doc duoc thi giu nguyen -
#: thieu mot dong o day khong duoc bien thanh loi im lang.
_PREFLIGHT_VI = {
    "no_signable_file": "chưa có tệp PDF nào cần ký (hãy đính kèm và bật 'cần chữ ký')",
    "incomplete_upload": "có tệp chưa tải lên xong",
    "no_package": "chưa thiết lập chữ ký cho phiếu này",
}


def _preflight_vi(code):
    code = str(code)
    head = code.split(":", 1)[0]
    if head in _PREFLIGHT_VI:
        return _PREFLIGHT_VI[head]
    if head == "missing_placement":
        bits = code.split(":")
        lvl = bits[1] if len(bits) > 1 else "?"
        fname = bits[2] if len(bits) > 2 else "?"
        return "thiếu vị trí ký của cấp %s trên tệp %s" % (lvl.lstrip("L"), fname)
    if head == "signable_not_pdf":
        return "tệp %s không phải PDF nên không ký trực tiếp được" % code.split(":", 1)[-1]
    if head == "unsignable_producer":
        return ("tệp %s được tạo bằng ReportLab, cổng không ký được - xuất lại PDF từ Word "
                "(hoặc chuyển sang Bộ chứng từ nếu không cần ký)" % code.split(":", 1)[-1])
    if head == "signable_too_large":
        from ecentric_workspace.platform.esign import limits
        return ("tổng tệp cần ký %s vượt mức cổng ký nhận (~%s) - hãy nén PDF hoặc tách bớt"
                % (code.split(":", 1)[-1], limits.raw_budget_mb(2)))
    if head == "missing_hash":
        return "tệp %s chưa tính được mã kiểm tra" % code.split(":", 1)[-1]
    # PR-G: tep ky do nghiep vu khai (ec_esign_signing_files).
    if head == "signing_files_unavailable":
        return "chưa xác định được bản PDF để ký của phiếu (lỗi hệ thống) - liên hệ quản trị"
    if head == "signing_file_missing":
        return "chưa có bản PDF để ký trong gói - tải bản PDF để ký lên rồi đặt ô ký"
    if head == "signing_file_not_declared":
        return ("tệp %s không còn là bản PDF để ký của phiếu - tải đúng bản PDF để ký rồi đặt "
                "ô ký" % code.split(":", 1)[-1])
    if head == "document_verify":
        bits = code.split(":")
        fname = bits[1] if len(bits) > 1 else "?"
        st = bits[2] if len(bits) > 2 else "?"
        if st == "mismatch":
            return ("nội dung tệp %s không khớp phiếu (số hợp đồng / số tiền) - sửa phiếu hoặc "
                    "xuất lại PDF đúng bản đã duyệt" % fname)
        if st == "error":
            return ("không đọc được tệp %s (tệp hỏng) hoặc chưa đối chiếu được với phiếu - "
                    "xuất lại PDF rồi tải lên" % fname)
        if st == "no_text":
            return ("tệp %s không có lớp chữ (bản scan / in ra ảnh) - mở trong Word → Lưu "
                    "thành PDF rồi tải lên lại" % fname)
        return "chưa đối chiếu được nội dung tệp %s với phiếu - thử lại hoặc liên hệ quản trị" % fname
    return code


def _placement_refusal(missing):
    if missing and all(str(m).startswith("document_verify:") for m in missing):
        return _("Chưa gửi được: {0}.").format("; ".join(_preflight_vi(m) for m in missing))
    return _("Chưa gửi được: {0}. Hãy mở 'Thiết lập chữ ký', đặt đủ vị trí ký rồi gửi lại."
             ).format("; ".join(_preflight_vi(m) for m in missing))


def assert_ready_to_submit(business_doctype, business_name):
    """Refuse the submit BEFORE anything is written, when the placements are incomplete.

    sign_on_submit checks the same thing, but it runs after engine.submit() has created the
    request and stamped `approval_request` on the business document. There is no db.commit()
    on that path today, so a throw there does roll everything back - but the guarantee is
    incidental. One commit added anywhere in submit or its notification pipeline would turn a
    refusal into a document that is permanently "already submitted" and permanently unsigned:
    Submitter refuses to submit it again, and nothing ever signs it.

    Reading first costs one query and does not depend on anyone preserving that property.

    Only reads. Returns nothing; raises with the missing items named.
    """
    pkg_name = pkgsvc.draft_package_for_business(business_doctype, business_name)
    if not pkg_name:
        ar = _requester_ar(business_doctype, business_name)
        pkg_name = pkgsvc.signable_package_for_request(ar) if ar else None
    missing = pkgsvc.preflight_for_lock(pkg_name) if pkg_name else ["no_package"]
    if missing:
        frappe.throw(_placement_refusal(missing))
    assert_requester_portal_role(frappe.db.get_value(PKG, pkg_name, "profile"),
                                 frappe.session.user)
    assert_partner_sign_type_ready(pkg_name)


PROFILE = "EC Digital Signature Profile"


def _portal_adapter(prof):
    """Adapter cong (tai khoan tich hop) cho ho so, hoac None khi cong tac tich hop TAT
    (cong tac tong cua ky so - tasks._disabled - hoac Provider Settings tat)."""
    try:
        from ecentric_workspace.platform.esign import tasks
        disabled = tasks._disabled()
    except Exception:            # khong doc duoc cong tac tong -> xet tiep Provider Settings
        disabled = False
    if disabled:
        return None
    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"provider": prof.provider, "environment": prof.environment},
                                   "*", as_dict=True)
    if not settings or not int(settings.get("integration_enabled") or 0):
        return None
    from ecentric_workspace.platform.esign.providers import get_adapter
    return get_adapter(settings)


def _contract_profile_row(profile_name):
    if not profile_name:
        return None
    prof = frappe.db.get_value(PROFILE, profile_name,
                               ["name", "trust_portal_transitions", "allow_external_signers",
                                "workflow_definition_id", "provider", "environment"],
                               as_dict=True)
    if not prof or not (int(prof.trust_portal_transitions or 0)
                        or int(prof.allow_external_signers or 0)):
        return None
    return prof


def assert_requester_portal_role(profile_name, user):
    """Nguoi lap phai giu MOT vai tro cua buoc KHOI TAO tren quy trinh cong (PR-F 23/11/2026; vd
    WF03: "Chuyen vien CnB" / "Khoi tao hop dong"). Cong tu choi tao tai lieu cho nguoi khong co
    vai - bao ngay luc gui thay vi de chan nguoi lap hong sau khi phieu da di.

    Chi ho so hop dong (lay buoc tu cong / co doi tac); DNTT khong doi. CHI CHAN khi chac chan
    (QC 23/11): moi vai can co deu la MA da biet tren cong (Role/GetAll), tim duoc DUNG MOT tai
    khoan cong (theo ma anh xa da xac minh, roi moi toi email), va doc lai KHONG qua cache van
    thieu vai. Thieu bat ky dieu nao -> khong chan."""
    prof = _contract_profile_row(profile_name)
    if not prof or not user or not prof.workflow_definition_id:
        return
    try:
        adapter = _portal_adapter(prof)
        if adapter is None or not (hasattr(adapter, "workflow_nodes")
                                   and hasattr(adapter, "user_roles")
                                   and hasattr(adapter, "role_names")):
            return
        wf = adapter.workflow_nodes(prof.workflow_definition_id)
        start = (wf or {}).get("start_node")
        need = [str(r) for r in (((wf or {}).get("nodes") or {}).get(str(start) if start else "",
                                                                    {}).get("roles") or [])]
        if not need:
            return
        names = adapter.role_names() or {}
        known = {str(k).strip().lower(): v for k, v in names.items()}
        if not known or any(r.strip().lower() not in known for r in need):
            return                      # dang ma vai la / khong doc duoc ten -> khong chan
        mapping = perms.verified_mapping(user, prof.environment)
        pid = (mapping.get("scts_user_id") if isinstance(mapping, dict)
               else getattr(mapping, "scts_user_id", None)) if mapping else None
        want = {r.strip().lower() for r in need}

        def _ok(have):
            return have is None or bool(want & {str(h).strip().lower() for h in have})
        if _ok(adapter.user_roles(user, provider_user_id=pid)):
            return
        if _ok(adapter.user_roles(user, provider_user_id=pid, fresh=True)):
            return                      # vua duoc cap vai - cache cu
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign requester portal role check")
        return
    frappe.throw(_("Tài khoản cổng ký số CMC của bạn chưa có vai trò được khởi tạo tài liệu cho "
                   "quy trình này (cần một trong: {0}). Liên hệ quản trị cổng CMC cấp vai trò "
                   "rồi gửi lại.").format(", ".join(known.get(r.strip().lower()) or r
                                                    for r in need)))


_PARTNER_ERROR_VI = {
    "partner_info_missing": "Phiếu chưa có đủ thông tin người ký phía đối tác (họ tên, email) - "
                            "bổ sung trên phiếu rồi gửi lại.",
    "partner_info_invalid": "Thông tin người ký phía đối tác trên phiếu chưa hợp lệ (thiếu họ tên "
                            "hoặc email sai) - sửa trên phiếu rồi gửi lại.",
    "partner_sign_type_invalid": "Kiểu ký của đối tác trên phiếu không được cổng ký số hỗ trợ - "
                                 "liên hệ quản trị.",
}


def _partner_error_vi(code):
    return _(_PARTNER_ERROR_VI.get(code) or "Thông tin người ký phía đối tác trên phiếu chưa "
                                            "đúng - liên hệ quản trị.")


def assert_partner_sign_type_ready(pkg_name):
    """Ho so co doi tac ky ngoai: kiem LUC GUI (truoc khi phieu di) - thong tin doi tac du, va
    goi CMC con luot cho kieu ky cua doi tac (eKYC...). Truoc day chi lo luc tao tai lieu, sau
    khi phieu da duyet toi buoc cong, chan nguoi lap chet vinh vien (QC 23/11). Khong doc duoc
    giay phep -> khong chan (giong luc tao tai lieu)."""
    if not pkg_name:
        return
    pkg = frappe.db.get_value(PKG, pkg_name, ["name", "profile", "business_doctype",
                                              "business_name"], as_dict=True)
    prof = _contract_profile_row(pkg.profile if pkg else None)
    if not prof or not int(prof.allow_external_signers or 0):
        return
    from ecentric_workspace.platform.esign import tasks
    from ecentric_workspace.platform.esign.providers.base import ProviderError
    try:
        from ecentric_workspace.platform.esign.providers.scts import _external_handlers_payload
        payload = _external_handlers_payload(tasks._external_handlers_for(pkg))
    except ProviderError as e:
        # Cau cho NGUOI DUNG: cau cua nghiep vu neu co, khong thi cau co dinh theo ma loi - khong
        # lo ma noi bo / ten hook / chu khong dau (QC vong 2).
        frappe.throw(getattr(e, "user_message", None) or _partner_error_vi(e.code))
    try:
        adapter = _portal_adapter(prof)
        if adapter is None or not hasattr(adapter, "assert_partner_sign_types_available"):
            return
        adapter.assert_partner_sign_types_available(payload)
    except ProviderError as e:
        if e.code == "partner_sign_type_unavailable":
            frappe.throw(e.message)
        frappe.log_error(frappe.get_traceback(), "esign requester partner licence check")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign requester partner licence check")


def sign_on_submit(business_doctype, business_name):
    """Prepare + lock + sign, as ONE step, right after the request is submitted.

    The requester used to face five separate actions for one intention: place the signature
    boxes, send the request, prepare the package, lock the package, submit for signing. The
    middle three are internal state-machine steps that nobody outside this module should have
    to know exist - and on 27 and 28 August they were also unreachable, so the flow simply
    stopped there twice with "there is no button".

    Prepare and lock are local and fast; the provider call happens in the background worker
    that requester_submit_and_sign enqueues, so submitting stays quick.

    Raises when the placements are not complete: a request that goes out with an unusable
    signing package is worse than one that refuses to go out, because the refusal is visible
    immediately and the broken package is not.
    """
    ar = _requester_ar(business_doctype, business_name)
    if not ar:
        frappe.throw(_("Không tìm thấy yêu cầu duyệt cho phiếu này."))

    prepare_requester_signing_package(business_doctype, business_name)

    pkg_name = (pkgsvc.signable_package_for_request(ar)
                or pkgsvc.draft_package_for_business(business_doctype, business_name))
    missing = pkgsvc.preflight_for_lock(pkg_name) if pkg_name else ["no_package"]
    if missing:
        frappe.throw(_placement_refusal(missing))

    requester_lock_signing_package(business_doctype, business_name)
    return requester_submit_and_sign(business_doctype, business_name)


def lock_on_submit(business_doctype, business_name):
    """KHOA goi ky ngay sau khi phieu duoc gui duyet - cho ho so NGUOI LAP KHONG KY (hop dong
    WF09: buoc nguoi lap tren cong la "trinh", khong ky; PR-C 22/11/2026).

    Nghiep vu goi: `assert_ready_to_submit` TRUOC engine.submit (chan som, chua ghi gi), roi
    `lock_on_submit` SAU engine.submit trong cung giao dich. Goi khoa = chot ma bam tep + o ky;
    portal_steps.start_requester_step se tim thay goi nay khi cap cong dau tien mo (-2).
    Chi nguoi lap. Idempotent: goi da khoa -> tra lai. Ho so khong ky so -> khong lam gi.
    Ho so CO yeu cau nguoi lap ky -> dung sign_on_submit (khong phai ham nay)."""
    ar = _requester_ar(business_doctype, business_name)
    if not ar:
        frappe.throw(_("Không tìm thấy yêu cầu duyệt cho phiếu này."))
    req = frappe.db.get_value(AR, ar, ["approval_type", "requested_by", "approval_status"],
                              as_dict=True)
    if frappe.session.user != req.requested_by:
        frappe.throw(_("Chỉ người lập mới khoá được gói ký."), frappe.PermissionError)
    if req.approval_status != "Pending":
        # QC 22/11: _requester_ar roi ve yeu cau MOI NHAT ke ca da tu choi / huy.
        frappe.throw(_("Yêu cầu duyệt không ở trạng thái chờ duyệt - không khoá gói ký."))
    pname = guard.get_enabled_profile(business_doctype, req.approval_type, business_name)
    if not pname:
        return {"locked": False, "reason": "no_profile"}
    if guard.requester_signature_required(business_doctype, req.approval_type, business_name):
        frappe.throw(_("Hồ sơ ký này cần người lập ký - dùng luồng Gửi & Ký."))
    existing = pkgsvc.signable_package_for_request(ar)
    if existing:
        return {"locked": True, "package": existing, "duplicate": True}
    draft = pkgsvc.draft_package_for_business(business_doctype, business_name, for_update=True)
    if not draft:
        frappe.throw(_("Chưa có gói tài liệu ký: tải bản PDF để ký và đặt ô ký trước khi gửi."))
    if frappe.db.get_value(PKG, draft, "profile") != pname:
        # QC 22/11: luong ky (esign_flow) doi SAU khi dat o ky -> o ky theo ho so cu, chuoi cong
        # khac. Khong tro lai ho so (o ky mat hieu luc) - bao nguoi lap dat lai.
        frappe.throw(_("Luồng ký của phiếu đã đổi sau khi đặt ô ký - mở lại phần Ký số, đặt "
                       "ô ký lại rồi gửi."))
    missing = pkgsvc.preflight_for_lock(draft)
    if missing:
        frappe.throw(_placement_refusal(missing))
    assert_requester_portal_role(pname, frappe.session.user)
    assert_partner_sign_type_ready(draft)
    h = pkgsvc.lock_package(draft, ar)
    return {"locked": True, "package": draft, "package_hash": h}


def requester_submit_and_sign(business_doctype, business_name, comment=None):
    """Governed requester Submit & Sign. Session user MUST be the authoritative requester
    (no admin/SM bypass); creates or reuses exactly one requester-scoped DSR under a request
    row lock; sets requester_signature_status=Processing; enqueues the signing worker."""
    actor = frappe.session.user
    ar = perms.business_approval_request(business_doctype, business_name)
    if not ar:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    req = frappe.db.get_value(AR, ar, ["approval_type", "requester_signature_status",
                                       "requested_by"], as_dict=True)
    requester = req.requested_by
    if actor != requester:  # authoritative requester only; role is never a bypass
        frappe.throw(_("Chỉ người đề nghị mới được thực hiện Gửi & Ký."), frappe.PermissionError)
    pname, prof, st = _profile_and_settings(business_doctype, req.approval_type, business_name)
    if not pname or not guard.requester_signature_required(business_doctype, req.approval_type,
                                                           business_name):
        frappe.throw(_("Loại yêu cầu này không yêu cầu chữ ký của người đề nghị."))
    if req.requester_signature_status == "Signed":
        frappe.throw(_("Người đề nghị đã ký cho yêu cầu này."))
    if req.requester_signature_status not in _START_STATES + ("Processing",):
        frappe.throw(_("Yêu cầu không ở trạng thái chờ ký của người đề nghị."))
    from ecentric_workspace.platform.esign import binding
    binding.assert_provider_environment(st)
    # Execution gates are fail-closed here: with Integration / Document Creation / Signing OFF
    # NO SCTS write is made and no requester DSR is created - the request stays Pending
    # Requester Signature and Level 1 stays inactive.
    if not (st.get("integration_enabled") and st.get("allow_document_creation")
            and st.get("allow_signing")):
        frappe.throw(_("Cổng ký số chưa được bật (Integration / Tạo tài liệu / Ký). "
                       "Không thể Gửi & Ký cho tới khi quản trị bật các cổng này."),
                     frappe.PermissionError)
    perms.assert_allowed_signer(st, requester)
    mapping = perms.verified_mapping(requester, prof.environment)
    if not mapping:
        events.emit("MappingRequired", erp_actor=requester,
                    request_meta={"business": business_name})
        frappe.throw(_("Người đề nghị chưa có ánh xạ chữ ký CMC được xác minh."))
    # Chung tu phai do CHINH nguoi de nghi tao (token cua ho) thi ho moi giu task Trinh ky.
    # Chan o day, TRUOC khi tao DSR - khong de lai chung tu rac ben SCTS (00046/47/48/50).
    from ecentric_workspace.platform.esign import user_link
    user_link.assert_requester_linked(requester, st, prof.environment)
    user_link.assert_signature_ready(requester, st, prof.environment)
    pkg_name = pkgsvc.signable_package_for_request(ar)   # Locked OR Active (see flow docs)
    if not pkg_name:
        frappe.throw(_("Không có gói tài liệu sẵn sàng ký."))
    pkg = frappe.db.get_value(PKG, pkg_name, ["name", "package_version", "package_hash"], as_dict=True)
    if pkgsvc.compute_hash(pkg_name) != pkg.package_hash:
        frappe.throw(_("Gói tài liệu đã thay đổi so với phiên bản đã khóa - cần phiên bản mới."))

    idem = hashing.idempotency_key(prof.provider, prof.environment, ar, "REQUESTER",
                                   requester, "RequesterSign", pkg.package_hash,
                                   "%s@%s" % (mapping.name, mapping.modified))
    frappe.db.get_value(AR, ar, "name", for_update=True)  # lock the request row
    # Locking read: snapshot cua transaction nay lap tu truoc khi khoa (events.current_status).
    existing = frappe.db.get_value(DSR, {"idempotency_key": idem}, ["name", "status"],
                                   as_dict=True, for_update=True)
    if existing and existing.status in _LIVE_OR_DONE:  # reuse - never duplicate a job/document
        frappe.db.set_value(AR, ar, {"requester_signature_status": "Processing",
                                     "requester_signature_request": existing.name})
        return {"signature_request": existing.name, "status": existing.status, "duplicate": True}
    from ecentric_workspace.platform.esign import state as sm
    if existing:
        # Chan cu da chet (Permanent Failure / Cancelled) va CHUA TUNG gui -> nhuong khoa
        # (LegRetired) roi tao dong moi ben duoi. Dang doi soat / co the da gui -> loi than
        # thien thay vi insert trung khoa unique -> 500 (08/09). Xem service.retire_dead_leg.
        from ecentric_workspace.platform.esign import service as _svc
        if not _svc.retire_dead_leg(existing, requester, who_vi="Lượt ký trước của người đề nghị"):
            # Dong chua bao gio xep hang (Mapping/Placement Required): dung lai, xep hang lai.
            events.set_dsr_status(existing.name, "Prepared", erp_actor=requester,
                                  event_type="RetryScheduled")
            events.set_dsr_status(existing.name, "Queued",
                                  extra_fields={"queued_at": now_datetime()}, erp_actor=requester)
            frappe.db.set_value(AR, ar, {"requester_signature_status": "Processing",
                                         "requester_signature_request": existing.name})
            frappe.enqueue("ecentric_workspace.platform.esign.tasks.process_signing_request",
                           dsr_name=existing.name, queue=sm.SIGNING_QUEUE,
                           timeout=sm.SIGNING_JOB_TIMEOUT,
                           job_name="esign_requester_%s" % existing.name,
                           enqueue_after_commit=True)
            return {"signature_request": existing.name, "status": "Queued", "duplicate": False}

    dsr = frappe.get_doc({
        "doctype": DSR, "provider": prof.provider, "environment": prof.environment,
        "package": pkg_name, "approval_request": ar, "action": "Sign",
        "actor_type": "Requester", "actor_user": requester,
        "requested_by": requester, "approver": requester,
        "effective_scts_user_id": mapping.scts_user_id,
        "effective_signature_id": mapping.signature_id, "idempotency_key": idem,
        "status": "Draft", "package_version": pkg.package_version,
        "package_hash": pkg.package_hash,
    }).insert(ignore_permissions=True)  # post-authorization system row
    events.emit("RequesterSignatureSubmitted", signature_request=dsr.name, package=pkg_name,
                erp_actor=requester, scts_effective_user=mapping.scts_user_id)
    events.set_dsr_status(dsr.name, "Prepared", erp_actor=requester, event_type="Prepared")
    events.set_dsr_status(dsr.name, "Queued", extra_fields={"queued_at": now_datetime()},
                          erp_actor=requester)
    frappe.db.set_value(AR, ar, {"requester_signature_status": "Processing",
                                 "requester_signature_request": dsr.name})
    frappe.enqueue("ecentric_workspace.platform.esign.tasks.process_signing_request",
                   dsr_name=dsr.name, queue=sm.SIGNING_QUEUE, timeout=sm.SIGNING_JOB_TIMEOUT,
                   job_name="esign_requester_%s" % dsr.name, enqueue_after_commit=True)
    return {"signature_request": dsr.name, "status": "Queued", "duplicate": False}


def reconcile_and_complete_requester(dsr_name):
    """Worker/reconciliation completion for a Requester DSR. Maps the DSR terminal state to
    requester_signature_status and, on confirmed success ONLY, atomically activates Level 1.
    Never calls engine.approve(). Idempotent under repeated worker/poll/reconcile calls."""
    dsr = frappe.db.get_value(DSR, dsr_name,
                              ["name", "actor_type", "actor_user", "approval_request", "status"],
                              as_dict=True)
    if not dsr or dsr.actor_type != "Requester":
        return {"completed": False, "reason": "not_requester_dsr"}

    def _alert_requester(subject, todo_text):
        """Cham toi NGUOI DE NGHI khi chan ky cua chinh ho ket o mot trang thai khong tu
        thoat ra duoc. Long trong ham cha co chu dich: day la ket cuc cua CHINH luong
        doi soat nay, khong phai mot tien ich chung - tach ra module thi lan sau doc
        `reconcile_and_complete_requester` khong con thay duong nao cham toi nguoi that.

        Thong bao + mot viec tren chinh chung tu: chi thong bao thi phieu van vang mat
        khoi Action Center (feed doc `tabToDo`, ma duong Option B chua tao ToDo nao).
        Nuot loi va ghi Error Log: mot thong bao hong khong duoc lam roll back buoc doi
        soat da ghi trang thai o tren."""
        try:
            from ecentric_workspace.approval_center.shared.workflow import transitions as engine
            ref = frappe.db.get_value(AR, dsr.approval_request,
                                      ["reference_doctype", "reference_name", "requested_by"],
                                      as_dict=True) or {}
            who = ref.get("requested_by") or dsr.actor_user
            if not (who and ref.get("reference_doctype") and ref.get("reference_name")):
                return
            engine.notify([who], subject, ref.get("reference_doctype"), ref.get("reference_name"))
            engine.assign(ref.get("reference_doctype"), ref.get("reference_name"), [who], todo_text)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign.requester alert requester")

    if dsr.status == "Signed":
        # promote to terminal + activate
        events.set_dsr_status(dsr_name, "Approval Completed",
                              extra_fields={"completed_at": now_datetime()},
                              event_type="RequesterSignatureConfirmed", verification_result="verified")
        return activate_level_one_after_requester_signature(dsr.approval_request, dsr_name)
    if dsr.status == "Approval Completed":
        return activate_level_one_after_requester_signature(dsr.approval_request, dsr_name)
    if dsr.status == "Permanent Failure":
        newly_failed = _set_req_status(dsr.approval_request, "Failed")
        events.emit("RequesterSignatureFailed", signature_request=dsr_name,
                    request_meta={"reason": "permanent_failure"})
        # NGO CUT IM LANG NHAT cua duong "Gui & Ky" (Option B), truoc ban va nay:
        # dat mot truong + emit mot event, het. Level 1 chua kich hoat nen KHONG co
        # ToDo nao ton tai cho BAT KY AI, cap duyet khong biet co phieu, va
        # `get_my_requests_summary` van dem phieu nay la "Pending" - trong y het mot
        # phieu dang cho duyet binh thuong. Nguoi de nghi bam "Gui & Ky", man hinh
        # dong, va khong bao gio duoc bao la hong.
        # Bao + giao lai viec cho chinh nguoi de nghi de phieu thoi tang hinh. Chi bao
        # o LAN CHUYEN TRANG THAI (`_set_req_status` tra True): ham nay idempotent va
        # duoc worker/poll goi lai nhieu lan tren cung mot DSR da hong, ma `notify()`
        # cua engine co dedupe_key kem dau thoi gian micro-giay nen KHONG bao gio khu
        # trung - khong chan o day thi moi vong doi soat la mot DM Teams nua.
        if newly_failed:
            _alert_requester(_("Ký số thất bại — yêu cầu chưa được gửi duyệt"),
                             _("Ký số thất bại: cần gửi & ký lại"))
        return {"completed": False, "reason": "failed"}
    if dsr.status in ("Verifying", "Retryable Failure", "Verification Mismatch", "Manual Review"):
        _set_req_status(dsr.approval_request, "Reconciliation Required")
        return {"completed": False, "reason": "reconciliation_required"}
    return {"completed": False, "reason": "in_progress:%s" % dsr.status}


def _set_req_status(ar, status):
    """Tra True khi VUA THAT SU doi trang thai. Nguoi goi dung gia tri do lam chot mot
    lan cho thong bao: ham doi soat la idempotent va bi goi lai nhieu vong tren cung mot
    DSR, nen "co ghi khong" la tin hieu duy nhat phan biet lan dau voi lan lap."""
    cur = frappe.db.get_value(AR, ar, "requester_signature_status")
    if cur != "Signed" and cur != status:  # never downgrade a completed requester signature
        frappe.db.set_value(AR, ar, "requester_signature_status", status)
        return True
    return False


#: Phieu o trang thai nay thi chu ky nguoi de nghi den muon KHONG duoc mo cap duyet nao.
_NOT_ACTIVATABLE = ("Approved", "Rejected", "Cancelled")


def activate_level_one_after_requester_signature(request_name, dsr_name):
    """Idempotent atomic Level-1 activation. Level 1 activates ONLY when: requester signature
    is required, the confirmed requester DSR belongs to the authoritative requester, and the
    request is still in pre-approval (current_level == 0). Concurrent calls return the
    already-activated result without activating (or creating ToDos) twice."""
    # MOT lenh doc CO KHOA cho moi truong (QC 12/11). Truoc day: khoa `name` roi doc cac truong
    # bang lenh THUONG - duoi REPEATABLE READ lenh thuong tra snapshot cua lan doc DAU trong
    # transaction (nguoi goi da doc DSR truoc do), nen mot engine.cancel() vua commit van bi
    # thay la "Pending" va cap 1 van mo; kiem `current_level > 0` cung doc cu y het. Cung lop loi
    # voi events.current_status / transitions._lock_and_read.
    req = frappe.db.get_value(AR, request_name,
                              ["approval_type", "reference_doctype", "current_level",
                               "requester_signature_status", "requested_by", "approval_status",
                               "reference_name"],
                              as_dict=True, for_update=True)
    if not req:
        return {"activated": False, "reason": "request_missing"}
    if not guard.requester_signature_required(req.reference_doctype, req.approval_type,
                                              req.reference_name):
        return {"activated": False, "reason": "requester_signature_not_required"}
    d = frappe.db.get_value(DSR, dsr_name, ["actor_type", "actor_user", "status"], as_dict=True)
    if not d or d.actor_type != "Requester" or d.status != "Approval Completed" \
            or d.actor_user != req.requested_by:
        return {"activated": False, "reason": "requester_dsr_not_confirmed"}
    if req.requester_signature_status != "Signed":
        # Ghi ca khi phieu da dong: nguoi de nghi DA ky that tren cong - ho so phai noi dung su that.
        frappe.db.set_value(AR, request_name, {
            "requester_signature_status": "Signed", "requester_signed_at": now_datetime(),
            "requester_signed_by": req.requested_by})
    # Phieu DA DONG thi khong mo cap nao (QC 12/11): chan ky nguoi de nghi dang chay dung luc
    # phieu bi huy van co the ky xong; truoc day ham nay van mo cap 1 -> nguoi duyet nhan ToDo,
    # thong bao va bi tinh SLA tren mot phieu da huy.
    if req.approval_status in _NOT_ACTIVATABLE:
        return {"activated": False, "reason": "request_closed:%s" % req.approval_status}
    if req.current_level and int(req.current_level) > 0:  # already activated -> idempotent
        return {"activated": False, "reason": "already_activated", "level": req.current_level}
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    req_doc = frappe.get_doc(AR, request_name)
    first = engine._request_levels(request_name)[0]
    engine._activate_level(req_doc, first.level_no)   # creates Level-1 ToDos + notification once
    events.emit("LevelOneActivatedAfterRequester", signature_request=dsr_name,
                erp_actor=req.requested_by,
                request_meta={"approval_request": request_name, "level": first.level_no})
    return {"activated": True, "level": first.level_no}


def _add_requester_pdf_files(pkg_name, business_doctype, business_name):
    """Add the business document's ELIGIBLE private PDF attachments to the package as signable
    files (idempotent by SHA-256). Non-PDF / non-private / invalid content is skipped or fails
    closed inside package.add_file's validation. Never touches SCTS."""
    from ecentric_workspace.platform.esign import hashing
    have_sha = set()
    for row in frappe.get_all(DSF, filters={"package": pkg_name}, fields=["sha256"]):
        if row.sha256:
            have_sha.add(row.sha256)
    seen_url = set()
    added = 0
    # Loai phieu khai tep ky (PR-G): chi them DUNG cac tep do. Khong khai -> moi PDF nhu cu.
    from ecentric_workspace.platform.esign import signing_files
    decl = signing_files.declared(business_doctype, business_name)
    # is_private=1 + attached_to_doctype/name keeps this to PDFs directly linked to THIS
    # Payment Request; attached_to_field is intentionally NOT filtered, so both the
    # request_attachment field-attachment and its null-field twin qualify.
    for f in frappe.get_all("File",
                            filters={"attached_to_doctype": business_doctype,
                                     "attached_to_name": business_name, "is_private": 1},
                            fields=["name", "file_name", "file_url"]):
        # PDF eligibility from canonical File metadata (file_name OR file_url) - never a
        # browser-supplied MIME, which may be absent. add_file re-checks PDF magic bytes.
        name_l = (f.file_name or "").lower()
        url_l = (f.file_url or "").lower()
        if not (name_l.endswith(".pdf") or url_l.endswith(".pdf")):
            continue
        if decl is not None and (f.file_url or "") not in decl["urls"]:
            continue
        # de-dupe multiple File rows for the SAME physical PDF by canonical URL first (cheap),
        # then by content SHA - so the same file is added exactly once per package.
        if f.file_url and f.file_url in seen_url:
            continue
        content = pkgsvc.raw_file_bytes(f.name)
        sha = hashing.sha256_bytes(content)
        if sha in have_sha:
            if f.file_url:
                seen_url.add(f.file_url)
            continue
        display_name = f.file_name or (f.file_url or "").rsplit("/", 1)[-1] or "document.pdf"
        pkgsvc.add_file(pkg_name, display_name, content, requires_signature=1,
                        source_file=f.name)      # lien ket, khong sao chep (05/09)
        have_sha.add(sha)          # update in-loop: identical twins are added once
        if f.file_url:
            seen_url.add(f.file_url)
        added += 1
    return added


def prepare_requester_signing_package(business_doctype, business_name):
    """Governed 'Prepare Signing Package' for a requester in pre-approval. Session user must be
    the authoritative requester (NO admin/SM bypass); creates OR reuses exactly one internal
    package (idempotent), adds eligible private PDFs, and returns the placement-editor config.
    Makes NO SCTS call and creates NO DSR/provider document (gates may be OFF)."""
    actor = frappe.session.user
    ar = perms.business_approval_request(business_doctype, business_name) \
        or _requester_ar(business_doctype, business_name)
    if not ar:
        frappe.throw(_("Không tìm thấy yêu cầu duyệt cho phiếu này."))
    req = frappe.db.get_value(AR, ar, ["approval_type", "reference_doctype", "requested_by",
                                       "requester_signature_status", "current_level"], as_dict=True)
    if actor != req.requested_by:
        frappe.throw(_("Chỉ người đề nghị mới được chuẩn bị gói ký."), frappe.PermissionError)
    if req.requester_signature_status not in _START_STATES + ("Processing",):
        frappe.throw(_("Yêu cầu không ở giai đoạn chờ người đề nghị ký."))
    pname = guard.get_enabled_profile(req.reference_doctype, req.approval_type, business_name)
    if not pname or not guard.requester_signature_required(req.reference_doctype, req.approval_type,
                                                           business_name):
        frappe.throw(_("Loại yêu cầu này không yêu cầu chữ ký của người đề nghị."))
    mapping = perms.verified_mapping(req.requested_by,
                                     frappe.db.get_value("EC Digital Signature Profile", pname,
                                                         "environment"))
    if not mapping:
        frappe.throw(_("Người đề nghị chưa có ánh xạ chữ ký CMC được xác minh."))
    frappe.db.get_value(AR, ar, "name", for_update=True)  # idempotency lock
    pkg = pkgsvc.get_or_create_draft(business_doctype, business_name, pname, allow_submitted=True)
    if pkg.status == "Draft":
        _add_requester_pdf_files(pkg.name, business_doctype, business_name)
    # Build the editor config directly from THIS package. ui_state/get_signing_status resolve
    # a package by Active status or approval_request link, and an unlocked requester Draft has
    # NEITHER (approval_request is set only at lock), so routing through it would report zero
    # files here even though the Draft holds them.
    files = [{"name": r.name, "file_name": r.file_name, "is_pdf": r.is_pdf,
              "requires_signature": r.requires_signature}
             for r in pkgsvc.package_files(pkg.name)]
    return {"package": pkg.name, "status": pkg.status,
            "config": {"package": pkg.name, "files": files,
                       "version": pkg.package_version,
                       "locked": bool(pkg.status != "Draft")}}


def requester_lock_signing_package(business_doctype, business_name):
    """Lock the requester's package locally (freezes the hash) after placements are set - no
    SCTS call. Requester-only; idempotent (a Locked/Active package is returned as-is)."""
    actor = frappe.session.user
    ar = perms.business_approval_request(business_doctype, business_name) \
        or _requester_ar(business_doctype, business_name)
    req = frappe.db.get_value(AR, ar, ["requested_by"], as_dict=True) if ar else None
    if not req or actor != req.requested_by:
        frappe.throw(_("Chỉ người đề nghị mới được khóa gói ký."), frappe.PermissionError)
    pkg_name = pkgsvc.draft_package_for_business(business_doctype, business_name) \
        or pkgsvc.active_package_for_request(ar)
    if not pkg_name:
        frappe.throw(_("Chưa có gói tài liệu để khóa."))
    status = frappe.db.get_value(PKG, pkg_name, "status")
    if status in ("Locked", "Active"):
        return {"package": pkg_name, "status": status, "locked": True, "duplicate": True}
    # INVARIANT: a package with zero requester placements is never lockable. Enforced here
    # (server-side) independent of the approver-level preflight in lock_package.
    if not pkgsvc.requester_placements_complete(pkg_name):
        frappe.throw(_("Cần ít nhất một vị trí ký hợp lệ trước khi khóa gói."))
    h = pkgsvc.lock_package(pkg_name, ar)
    return {"package": pkg_name, "status": "Locked", "package_hash": h, "locked": True}


def requester_reset_invalid_package(business_doctype, business_name):
    """Governed recovery for an INVALID locked requester package (Locked/Active with zero
    requester placements - only reachable from the pre-guard defect). Authorized STRICTLY for
    the actual requester resolved through the Approval Engine (EC Approval Request.requested_by
    for this business doc) - NO Administrator bypass, NO System Manager bypass, NO generic role
    check, NO ignore_permissions. Audited via the package state machine; performs NO
    provider/SCTS/DSR mutation and NO direct SQL. It cancels the invalid local package
    (Locked/Active -> Cancelled) via the governed transition so a subsequent
    prepare_requester_signing_package builds a fresh Draft. A VALID package is refused."""
    actor = frappe.session.user
    ar = perms.business_approval_request(business_doctype, business_name) \
        or _requester_ar(business_doctype, business_name)
    req = frappe.db.get_value(AR, ar, ["requested_by"], as_dict=True) if ar else None
    # Requester-scoped ONLY: the session user must BE the authoritative requester. No System
    # Manager / Administrator / role-membership / ignore_permissions bypass.
    if not req or actor != req.requested_by:
        frappe.throw(_("Chỉ người đề nghị mới được khôi phục gói ký."), frappe.PermissionError)
    cur = frappe.db.get_value(
        PKG, {"business_doctype": business_doctype, "business_name": business_name,
              "status": ["in", ("Locked", "Active", "Provider Creating", "Provider Created",
                                 "Provider Create Failed")]},
        ["name", "status"], order_by="creation desc", as_dict=True)
    if not cur:
        frappe.throw(_("Không có gói đã khóa để khôi phục."))
    if pkgsvc.requester_placements_complete(cur.name):
        frappe.throw(_("Gói hợp lệ (đã có vị trí ký) - không cần khôi phục."))
    from ecentric_workspace.platform.esign import state as sm, events
    frappe.db.get_value(PKG, cur.name, "name", for_update=True)  # row lock
    sm.assert_transition(sm.PACKAGE, cur.status, "Cancelled")     # governed transition only
    events.set_package_status(cur.name, "Cancelled", event_type="RequesterPackageReset",
                              request_meta={"reason": "invalid_locked_zero_placements",
                                            "actor": actor})
    return {"package": cur.name, "from_status": cur.status, "status": "Cancelled",
            "recovered": True}


def _requester_ar(business_doctype, business_name):
    """Resolve the active Approval Request by its OWN reference fields (authoritative)."""
    rows = frappe.get_all(AR, filters={"reference_doctype": business_doctype,
                                       "reference_name": business_name},
                          fields=["name", "approval_status"], order_by="creation desc",
                          limit_page_length=20)
    return next((r.name for r in rows if r.approval_status == "Pending"),
                (rows[0].name if rows else None))
