# Copyright (c) 2026, eCentric and contributors
"""Buoc tren cong cua NGUOI LAP o quy trinh "lay buoc tu cong" (12/11/2026, hop dong WF09).

WF09: nguoi lap trinh Ke toan (`-2`, khong ky) -> KTTH `-3` -> KTT `-4` -> CEO ky `-5` -> doi
tac. Truong phong chi duyet tren ERP (cap khong co buoc cong). Nen tai lieu tren cong CHI tao,
va buoc `-2` CHI gui, khi cap ERP DAU TIEN co buoc cong vua mo - Truong phong yeu cau sua thi
khong co gi tren cong phai huy.

Ai lam: ERP, tu dong, bang tai khoan cong cua chinh nguoi lap (chan "Requester" + "Approve"),
nguoi nhan = nguoi duyet cua cap vua mo. Nguoi lap khong bam gi them.

Diem vao: `on_level_activated` - engine goi o `_activate_level` (choke point moi duong mo cap).
KHONG BAO GIO nem ra engine: mot loi ky so khong duoc chan duyet. Loi -> Error Log + su kien.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign import guard

AR = "EC Approval Request"
DSR = "EC Digital Signature Request"
PROFILE = "EC Digital Signature Profile"
_LIVE_OR_DONE = ("Prepared", "Queued", "Provider Accepted", "Verifying", "Signed",
                 "Approval Completed", "Manual Review", "Retryable Failure")


def _trusting_profile(req):
    """Ho so dang bat + cong mo + bat 'Lay buoc tu cong', hoac None."""
    profile = guard.get_active_profile(req.reference_doctype, req.approval_type,
                                       req.reference_name)
    if not profile:
        return None
    if not int(frappe.db.get_value(PROFILE, profile, "trust_portal_transitions") or 0):
        return None
    return profile


def first_portal_level(req):
    """Cap ERP nho nhat co buoc tren cong (Sign / Approve), hoac None. Cap da Skipped khong
    tinh (QC 12/11): khong ai duyet no thi no khong bao gio mo."""
    levels = sorted(set(frappe.get_all("EC Approval Request Level",
                                       filters={"approval_request": req.name,
                                                "level_status": ["!=", "Skipped"]},
                                       pluck="level_no")))
    final = guard.request_final_level(req.name)
    for n in levels:
        if guard.level_portal_action(req.reference_doctype, req.approval_type, n,
                                     final_level=final, business_name=req.reference_name):
            return int(n)
    return None


def on_level_activated(request_name, level_no):
    """Cap `level_no` vua mo. La cap cong dau tien cua ho so lay-buoc-tu-cong -> xep hang buoc
    cua nguoi lap (sau commit). Moi truong hop khac: khong lam gi (DNTT: mot truy van ho so)."""
    try:
        # Cua nhanh: chua co ho so nao lay buoc tu cong (DNTT hom nay) -> MOT truy van roi thoi.
        if not frappe.db.exists(PROFILE, {"enabled": 1, "trust_portal_transitions": 1}):
            return None
        req = frappe.db.get_value(AR, request_name,
                                  ["name", "reference_doctype", "reference_name", "approval_type",
                                   "approval_status"], as_dict=True)
        if not req or req.approval_status != "Pending" or not req.reference_doctype:
            return None
        if not _trusting_profile(req):
            return None
        if int(level_no or 0) != first_portal_level(req):
            return None
        from ecentric_workspace.platform.esign import state as sm
        frappe.enqueue("ecentric_workspace.platform.esign.portal_steps.start_requester_step",
                       request_name=request_name, queue=sm.SIGNING_QUEUE,
                       timeout=sm.SIGNING_JOB_TIMEOUT,
                       job_name="esign_requester_step_%s" % request_name,
                       enqueue_after_commit=True)
        return "queued"
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign.portal_steps.on_level_activated")
        return None


def skipped_portal_levels(req):
    """Cap co buoc cong ma bi Skipped tren phieu nay. Moi cap cong la MOT buoc co dinh tren
    quy trinh; bo mot cap thi buoc do khong ai gui va chuoi tren cong ket (QC vong 2)."""
    final = guard.request_final_level(req.name)
    skipped = frappe.get_all("EC Approval Request Level",
                             filters={"approval_request": req.name, "level_status": "Skipped"},
                             pluck="level_no")
    return [int(n) for n in skipped
            if guard.level_portal_action(req.reference_doctype, req.approval_type, n,
                                         final_level=final, business_name=req.reference_name)]


def start_requester_step(request_name, quiet=False):
    """Tao + xep hang chan "nguoi lap trinh" (Requester / Approve). Idempotent THEO PHIEU + GOI:
    da co chan song / da xong cho goi nay thi thoi (khoa idempotency doi khi nguoi lap ket noi
    lai token - khong duoc dua vao no, QC vong 2). `quiet`: luoi an toan chay moi gio - khong
    bao lai nguoi dung moi lan (lan dau da bao)."""
    from ecentric_workspace.platform.esign import hashing
    from ecentric_workspace.platform.esign import package as pkgsvc
    from ecentric_workspace.platform.esign import permissions as perms
    req = frappe.db.get_value(AR, request_name,
                              ["name", "reference_doctype", "reference_name", "approval_type",
                               "approval_status", "requested_by", "current_level"],
                              as_dict=True, for_update=True)
    if not req or req.approval_status != "Pending":
        return {"started": False, "reason": "request_not_pending"}
    profile = _trusting_profile(req)
    if not profile:
        return {"started": False, "reason": "no_trusting_profile"}
    if int(req.current_level or 0) != first_portal_level(req):
        return {"started": False, "reason": "not_first_portal_level"}
    if skipped_portal_levels(req):
        if not quiet:
            _bao(req, _("Phiếu có cấp duyệt trên cổng ký số bị bỏ qua ({0}) - chuỗi ký trên "
                        "cổng sẽ kẹt. Liên hệ quản trị.").format(skipped_portal_levels(req)),
                 also_level=True)
        return {"started": False, "reason": "portal_level_skipped"}
    pkg_name = pkgsvc.signable_package_for_request(req.name)
    if not pkg_name:
        if not quiet:
            _bao(req, _("Không có gói tài liệu đã khoá để gửi sang cổng ký số."))
        return {"started": False, "reason": "no_signable_package"}
    rows = _requester_step_rows(req.name, pkg_name)
    done = [r for r in rows if r.status in _LIVE_OR_DONE]
    if done:
        return {"started": False, "reason": "exists", "signature_request": done[0].name}
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["name", "package_version", "package_hash", "provider",
                               "environment"], as_dict=True)
    mapping = perms.verified_mapping(req.requested_by, pkg.environment)
    if not mapping:
        if not quiet:
            events.emit("MappingRequired", erp_actor=req.requested_by,
                        request_meta={"approval_request": req.name, "stage": "requester"})
            _bao(req, _("Người lập chưa có tài khoản cổng ký số được xác minh - ERP chưa gửi "
                        "được phiếu sang cổng. Liên hệ quản trị."))
        return {"started": False, "reason": "requester_mapping_missing"}
    idem = hashing.idempotency_key(pkg.provider, pkg.environment, req.name, "requester-step",
                                   req.requested_by, "Approve", pkg.package_hash,
                                   "%s@%s" % (mapping.name, mapping.modified))
    existing = frappe.db.get_value(DSR, {"idempotency_key": idem}, ["name", "status"],
                                   as_dict=True, for_update=True)
    if existing and existing.status in _LIVE_OR_DONE:
        return {"started": False, "reason": "exists", "signature_request": existing.name}
    if existing and existing.status in _PRE_QUEUE:
        # Dong chua bao gio xep hang: dung lai, KHONG insert trung khoa (QC 12/11).
        events.set_dsr_status(existing.name, "Prepared", erp_actor=req.requested_by,
                              event_type="RetryScheduled")
        events.set_dsr_status(existing.name, "Queued", extra_fields={"queued_at": now_datetime()},
                              erp_actor=req.requested_by)
        _enqueue(existing.name)
        return {"started": True, "signature_request": existing.name, "reused": True}
    if existing:
        from ecentric_workspace.platform.esign import service as svc
        try:
            svc.retire_dead_leg(existing, req.requested_by,
                                who_vi="Lượt gửi trước của người lập")
        except Exception:
            # Chan cu co the da toi cong (dang doi soat) - khong tao chan moi, bao nguoi.
            frappe.log_error(frappe.get_traceback(), "esign.portal_steps retire")
            if not quiet:
                _bao(req, _("Bước gửi phiếu sang cổng ký số của người lập đang chờ bộ phận vận "
                            "hành đối soát ({0}).").format(existing.name), also_level=True)
            return {"started": False, "reason": "previous_leg_needs_review"}
    dsr = frappe.get_doc({
        "doctype": DSR, "provider": pkg.provider, "environment": pkg.environment,
        "package": pkg_name, "approval_request": req.name, "action": "Approve",
        "actor_type": "Requester", "actor_user": req.requested_by,
        "requested_by": req.requested_by, "approver": req.requested_by,
        "effective_scts_user_id": mapping.scts_user_id, "effective_signature_id": None,
        "idempotency_key": idem, "status": "Draft",
        "package_version": pkg.package_version, "package_hash": pkg.package_hash,
    }).insert(ignore_permissions=True)  # he thong tao, sau khi da kiem o tren
    events.emit("Created", signature_request=dsr.name, package=pkg_name,
                erp_actor=req.requested_by, scts_effective_user=mapping.scts_user_id,
                request_meta={"stage": "requester", "level": req.current_level})
    events.set_dsr_status(dsr.name, "Prepared", erp_actor=req.requested_by,
                          event_type="Prepared")
    events.set_dsr_status(dsr.name, "Queued", extra_fields={"queued_at": now_datetime()},
                          erp_actor=req.requested_by)
    _enqueue(dsr.name)
    return {"started": True, "signature_request": dsr.name}


_PRE_QUEUE = ("Draft", "Mapping Required", "Placement Required")


def _enqueue(dsr_name):
    from ecentric_workspace.platform.esign import state as sm
    frappe.enqueue("ecentric_workspace.platform.esign.tasks.process_signing_request",
                   dsr_name=dsr_name, queue=sm.SIGNING_QUEUE, timeout=sm.SIGNING_JOB_TIMEOUT,
                   job_name="esign_dsr_%s" % dsr_name, enqueue_after_commit=True)


def _requester_step_rows(request_name, package=None, bridge=False):
    """Chan "nguoi lap trinh" (buoc dau) - hoac, bridge=True, chan buoc nguoi lap SAU doi tac
    (WF03 `-11`, co `transition_id`; PR-F 23/11). Hai loai KHONG duoc lan vao nhau."""
    f = {"approval_request": request_name, "actor_type": "Requester", "action": "Approve"}
    if package:
        f["package"] = package
    rows = frappe.get_all(DSR, filters=f, fields=["name", "status", "transition_id", "error_code"],
                          order_by="creation desc", limit_page_length=20)
    return [r for r in rows if bool(r.get("transition_id")) == bool(bridge)]


#: Chan nguoi lap DUNG HAN - can van hanh (khong tu thoat).
_STOPPED = ("Manual Review", "Permanent Failure", "Verification Mismatch")


def requester_step_pending(req):
    """Cho approve_and_sign (QC 12/11): ho so lay buoc tu cong, phieu dang o cap cong DAU TIEN
    ma buoc nguoi lap CHUA xong -> cau bao (va xep hang lai neu chua co chan nao song).
    None = khong phai cho."""
    if int(req.current_level or 0) != first_portal_level(req):
        return None
    if skipped_portal_levels(req):
        return _("Phiếu có cấp duyệt trên cổng ký số bị bỏ qua - không gửi được bước nào trên "
                 "cổng. Liên hệ quản trị.")
    from ecentric_workspace.platform.esign import package as pkgsvc
    rows = _requester_step_rows(req.name, pkgsvc.signable_package_for_request(req.name))
    if any(r.status == "Approval Completed" for r in rows):
        return None
    if any(r.status in _STOPPED for r in rows) and not any(
            r.status in _LIVE_OR_DONE and r.status != "Manual Review" for r in rows):
        return _("Bước gửi phiếu sang cổng ký số của người lập đang lỗi - bộ phận vận hành "
                 "đang xử lý. Vui lòng chờ.")
    if not any(r.status in _LIVE_OR_DONE for r in rows):
        # KHONG enqueue_after_commit: nguoi goi nem loi ngay sau day -> rollback -> hang doi
        # sau-commit bi xoa, job khong bao gio chay (QC vong 2). start_requester_step khoa
        # dong phieu + co khoa idempotency nen chay som / chay lap deu an toan.
        from ecentric_workspace.platform.esign import state as sm
        frappe.enqueue("ecentric_workspace.platform.esign.portal_steps.start_requester_step",
                       request_name=req.name, quiet=True, queue=sm.SIGNING_QUEUE,
                       timeout=sm.SIGNING_JOB_TIMEOUT,
                       job_name="esign_requester_step_%s" % req.name,
                       enqueue_after_commit=False)
    return _("ERP đang gửi phiếu sang cổng ký số thay người lập (bước 'Trình kế toán'). Vui lòng "
             "thử lại sau ít phút.")


# --------------------------------------------------------------------------- buoc sau doi tac
# HD lao dong WF03 (PR-F 23/11/2026, doc dinh nghia quy trinh tren cong): nguoi lap `-8` chuyen
# doi tac -> doi tac ky `-7` -> tai lieu VE LAI nguoi lap -> `-11` "Doi tac ky xong va trinh CEO"
# -> CEO ky `-5`. Buoc `-11` khong ai bam tren cong (duyet mot lan): ERP gui thay nguoi lap,
# ngay khi cong MO canh do (doi tac da ky). Ho so khai dong (Forward, "requester:after_partner").

def _bridge_profile(req):
    """(ho so, dong cau hinh buoc sau doi tac) hoac (None, None)."""
    profile = _trusting_profile(req)
    if not profile:
        return None, None
    from ecentric_workspace.platform.esign import next_handler
    step = next_handler.bridge_step(profile)
    return (profile, step) if step else (None, None)


def bridge_done(req, package):
    """None = ho so khong co buoc sau doi tac; True/False = chan buoc do da xong chua."""
    _profile, step = _bridge_profile(req)
    if not step:
        return None
    return any(r.status == "Approval Completed"
               for r in _requester_step_rows(req.name, package, bridge=True))


def bridge_gate_message(req, package):
    """Cau chan cap duyet khi buoc nguoi lap SAU doi tac chua xong, hoac None (khong chan).

    Chi ho so co buoc sau doi tac, va CHI o cap cong DAU TIEN (WF03: CEO) - cap cong nao nam
    giua nguoi lap va doi tac ma bi chan o day thi ket vong tron (QC 23/11). Cau theo TRANG
    THAI chan buoc do (chua co / dang chay / dung han) - khong noi "doi tac chua ky" khi doi tac
    da ky ma ERP dang loi."""
    _profile, step = _bridge_profile(req)
    if not step:
        return None
    fpl = first_portal_level(req)
    if fpl is None or int(req.get("current_level") or 0) != int(fpl):
        return None
    rows = _requester_step_rows(req.name, package, bridge=True)
    if any(r.status == "Approval Completed" for r in rows):
        return None
    if any(r.status in _LIVE_OR_DONE and r.status != "Manual Review" for r in rows):
        return _("ERP đang trình bước sau khi đối tác ký sang cổng ký số - thử lại sau ít phút.")
    if rows:
        return _("Bước trình duyệt sau khi đối tác ký đang lỗi ({0}) - bộ phận vận hành đang "
                 "xử lý.").format(_STATUS_VI.get(rows[0].status, rows[0].status))
    return _("Đối tác chưa ký xong trên cổng ký số (hoặc ERP đang chuyển bước, tối đa khoảng 5 "
             "phút) - chờ rồi duyệt lại.")


#: Trang thai chan -> chu cho nguoi dung (khong in "Permanent Failure" vao cau tieng Viet).
_STATUS_VI = {"Manual Review": "chờ đối soát", "Permanent Failure": "dừng hẳn",
              "Verification Mismatch": "lệch khi đối soát", "Retryable Failure": "đang thử lại",
              "Cancelled": "đã huỷ"}

#: Loi chan buoc sau doi tac do KET NOI CMC cua nguoi lap - chi loai nay duoc tu tao lai, va
#: chi khi nguoi lap da ket noi lai SAU lan hong (QC vong 2: loi khac tao lai moi 5 phut = vong
#: vo tan, moi vong mot ToDo + thong bao).
_TOKEN_ERRORS = ("requester_not_linked", "signer_not_linked", "scts_user_token_rejected",
                 "scts_user_token_missing")

#: Bao nguoi lap MOT lan / ngay khi thieu ket noi CMC cho buoc sau doi tac (sweep 5 phut).
_BRIDGE_NOTICE_SECONDS = 86400


def _once_per_day(key):
    """True lan dau trong ngay cho `key` (cache). Cache hong -> True (ghi nhieu con hon im)."""
    ck = "esign:bridge:once:%s" % key
    try:
        if frappe.cache().get_value(ck):
            return False
        frappe.cache().set_value(ck, 1, expires_in_sec=_BRIDGE_NOTICE_SECONDS)
    except Exception:
        pass
    return True


def _relinked_since(user, environment, when):
    """Nguoi lap da KET NOI LAI CMC sau thoi diem `when` (chan cu hong) chua."""
    from ecentric_workspace.platform.esign import user_link
    try:
        row = user_link._token_row(user, environment) or {}
        linked = row.get("api_token_linked_at")
        if not linked or not when:
            return False
        from frappe.utils import get_datetime
        return get_datetime(linked) > get_datetime(when)
    except Exception:
        return False


def _notify_once(req, key, msg):
    ck = "esign:bridge:notice:%s:%s" % (req.name, key)
    try:
        if frappe.cache().get_value(ck):
            return
        frappe.cache().set_value(ck, 1, expires_in_sec=_BRIDGE_NOTICE_SECONDS)
    except Exception:
        pass
    _bao(req, msg)


def start_bridge_step(request_name):
    """Tao + xep hang chan buoc nguoi lap SAU doi tac. Idempotent theo phieu + goi; chi khi buoc
    nguoi lap dau tien da xong. KHONG tu hoi cong - nguoi goi (sweep_partner_bridges) da thay
    doi tac ky xong va canh dang mo."""
    from ecentric_workspace.platform.esign import hashing
    from ecentric_workspace.platform.esign import package as pkgsvc
    from ecentric_workspace.platform.esign import permissions as perms
    from ecentric_workspace.platform.esign import user_link
    req = frappe.db.get_value(AR, request_name,
                              ["name", "reference_doctype", "reference_name", "approval_type",
                               "approval_status", "requested_by", "current_level"],
                              as_dict=True, for_update=True)
    if not req or req.approval_status != "Pending":
        return {"started": False, "reason": "request_not_pending"}
    _profile, step = _bridge_profile(req)
    if not step:
        return {"started": False, "reason": "no_bridge_step"}
    pkg_name = pkgsvc.signable_package_for_request(req.name)
    if not pkg_name:
        return {"started": False, "reason": "no_signable_package"}
    if not any(r.status == "Approval Completed" for r in _requester_step_rows(req.name, pkg_name)):
        return {"started": False, "reason": "requester_step_not_done"}
    rows = _requester_step_rows(req.name, pkg_name, bridge=True)
    live = [r for r in rows if r.status in _LIVE_OR_DONE]
    if live:
        return {"started": False, "reason": "exists", "signature_request": live[0].name}
    # Chan sau doi tac DA HONG vi ly do KHAC ket noi (nguoi nhan khong hop le, chua anh xa...):
    # de van hanh, KHONG tu tao lai (QC vong 2 B-1).
    dead = [r for r in rows if r.status not in _LIVE_OR_DONE and r.status not in _PRE_QUEUE]
    if any(str(r.get("error_code") or "") not in _TOKEN_ERRORS for r in dead):
        return {"started": False, "reason": "previous_bridge_needs_review",
                "signature_request": dead[0].name}
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["name", "package_version", "package_hash", "provider",
                               "environment"], as_dict=True)
    mapping = perms.verified_mapping(req.requested_by, pkg.environment)
    if not mapping:
        _notify_once(req, "mapping", _("Người lập chưa có tài khoản cổng ký số được xác minh - "
                                       "ERP chưa trình được bước sau khi đối tác ký. Liên hệ "
                                       "quản trị."))
        return {"started": False, "reason": "requester_mapping_missing"}
    # Chan nay gui bang token CHINH nguoi lap (user_link.signer_token_needed). Doi doi tac co the
    # mat nhieu ngay - token het han thi bao nguoi lap ket noi lai, KHONG tao chan se chet ngay
    # (QC 23/11).
    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"provider": pkg.provider, "environment": pkg.environment},
                                   "*", as_dict=True) or {}
    if user_link.needs_own_token(req.requested_by, settings) and \
            not user_link.token_for(req.requested_by, pkg.environment):
        _notify_once(req, "token", _("Đối tác đã ký trên cổng ký số nhưng kết nối CMC của bạn đã "
                                     "hết hạn - bấm 'Kết nối CMC' trên trang Phê duyệt để ERP "
                                     "trình bước tiếp theo."))
        return {"started": False, "reason": "requester_not_linked"}
    idem = hashing.idempotency_key(pkg.provider, pkg.environment, req.name, "requester-bridge",
                                   req.requested_by, "Approve", pkg.package_hash,
                                   "%s@%s#%s" % (mapping.name, mapping.modified,
                                                 step["transition_id"]))
    existing = frappe.db.get_value(DSR, {"idempotency_key": idem},
                                   ["name", "status", "error_code", "modified"],
                                   as_dict=True, for_update=True)
    if existing and existing.status in _LIVE_OR_DONE:
        return {"started": False, "reason": "exists", "signature_request": existing.name}
    if existing and existing.status in _PRE_QUEUE:
        events.set_dsr_status(existing.name, "Prepared", erp_actor=req.requested_by,
                              event_type="RetryScheduled")
        events.set_dsr_status(existing.name, "Queued", extra_fields={"queued_at": now_datetime()},
                              erp_actor=req.requested_by)
        _enqueue(existing.name)
        return {"started": True, "signature_request": existing.name, "reused": True}
    if existing:
        # Chan cu DUNG HAN. CHI tao lai khi hong vi KET NOI CMC va nguoi lap DA ket noi lai sau
        # lan hong; con lai de van hanh (QC vong 2 B-1: tranh vong tao lai vo tan).
        if str(existing.get("error_code") or "") not in _TOKEN_ERRORS or \
                not _relinked_since(req.requested_by, pkg.environment, existing.get("modified")):
            return {"started": False, "reason": "previous_bridge_needs_review",
                    "signature_request": existing.name}
        # Chua tung gui -> nhuong khoa, tao chan moi. Co the da gui -> retire_dead_leg tu choi.
        from ecentric_workspace.platform.esign import service as svc
        try:
            svc.retire_dead_leg(existing, req.requested_by,
                                who_vi="Bước trình duyệt sau khi đối tác ký")
        except Exception:
            if _once_per_day("retire:%s" % existing.name):
                frappe.log_error(frappe.get_traceback(), "esign.portal_steps bridge retire")
            return {"started": False, "reason": "previous_bridge_needs_review",
                    "signature_request": existing.name}
    dsr = frappe.get_doc({
        "doctype": DSR, "provider": pkg.provider, "environment": pkg.environment,
        "package": pkg_name, "approval_request": req.name, "action": "Approve",
        "actor_type": "Requester", "actor_user": req.requested_by,
        "requested_by": req.requested_by, "approver": req.requested_by,
        "effective_scts_user_id": mapping.scts_user_id, "effective_signature_id": None,
        # Dau hieu chan buoc SAU doi tac (next_handler.portal_stage_for -> BRIDGE_STAGE).
        "transition_id": int(step["transition_id"]),
        "idempotency_key": idem, "status": "Draft",
        "package_version": pkg.package_version, "package_hash": pkg.package_hash,
    }).insert(ignore_permissions=True)
    events.emit("Created", signature_request=dsr.name, package=pkg_name,
                erp_actor=req.requested_by, scts_effective_user=mapping.scts_user_id,
                request_meta={"stage": "requester:after_partner",
                              "transition_id": step["transition_id"]})
    events.set_dsr_status(dsr.name, "Prepared", erp_actor=req.requested_by,
                          event_type="Prepared")
    events.set_dsr_status(dsr.name, "Queued", extra_fields={"queued_at": now_datetime()},
                          erp_actor=req.requested_by)
    _enqueue(dsr.name)
    return {"started": True, "signature_request": dsr.name}


#: Gioi han moi luot quet (giay) - vong 5 phut cua DNTT (flag_silent_legs) khong bi giu lau.
SWEEP_TIME_BUDGET = 60
_PARTNER_FINAL = ("partner_rejected", "partner_returned")


def sweep_partner_bridges(limit=50):
    """Moi 5 phut (tasks.flag_silent_legs): phieu Pending cua ho so co buoc sau doi tac, buoc
    nguoi lap dau da xong, chua co chan buoc sau doi tac SONG / XONG -> doc tai lieu tren cong:
      * moi doi tac DA KY va canh buoc sau doi tac DANG MO -> xep hang chan do (QC 23/11: canh
        mo thoi CHUA DU - tu choi / tra lai cung co the dua tai lieu ve buoc nguoi lap);
      * doi tac tu choi / tra lai, tai lieu bi huy -> bao nghiep vu (2 vong lien tiep, nhu vong
        tai PDF - tasks._handle_partner_round) - phieu Pending, vong tai PDF khong cham toi.
    Quay vong theo ma phieu (con tro trong cache) + gioi han thoi gian: phieu cho doi tac lau
    khong che phieu moi. Ho so khong khai buoc nay (DNTT, WF09) -> mot truy van roi thoi."""
    import time
    from ecentric_workspace.platform.esign import next_handler
    from ecentric_workspace.platform.esign import package as pkgsvc
    from ecentric_workspace.platform.esign import tasks
    t0 = time.monotonic()
    profiles = frappe.get_all(PROFILE, filters={"enabled": 1, "trust_portal_transitions": 1},
                              fields=["name", "business_doctype", "approval_type"],
                              limit_page_length=50)
    started = []
    for p in profiles:
        step = next_handler.bridge_step(p.name)
        if not step:
            continue
        cursor_key = "esign:bridge_sweep:%s" % p.name
        try:
            after = frappe.cache().get_value(cursor_key) or ""
        except Exception:
            after = ""
        reqs = frappe.db.sql("""
            SELECT ar.name, ar.reference_doctype, ar.reference_name, ar.approval_type,
                   ar.requested_by, ar.current_level
            FROM `tabEC Approval Request` ar
            WHERE ar.reference_doctype = %(dt)s AND ar.approval_type = %(at)s
              AND ar.approval_status = 'Pending' AND ar.name > %(after)s
              AND EXISTS (SELECT 1 FROM `tabEC Digital Signature Request` d
                          WHERE d.approval_request = ar.name AND d.actor_type = 'Requester'
                            AND d.action = 'Approve' AND IFNULL(d.transition_id, 0) = 0
                            AND d.status = 'Approval Completed')
              AND NOT EXISTS (SELECT 1 FROM `tabEC Digital Signature Request` b
                              WHERE b.approval_request = ar.name AND b.actor_type = 'Requester'
                                AND b.action = 'Approve' AND IFNULL(b.transition_id, 0) != 0
                                AND (b.status IN %(live)s
                                     OR IFNULL(b.error_code, '') NOT IN %(token_errs)s))
            ORDER BY ar.name ASC LIMIT %(lim)s""",
            {"dt": p.business_doctype, "at": p.approval_type, "after": after,
             "live": tuple(_LIVE_OR_DONE), "token_errs": tuple(_TOKEN_ERRORS),
             "lim": int(limit)}, as_dict=True)
        # Con tro = phieu DA XU LY cuoi cung. Het gio giua lo -> nho cho dung; lo KHONG du gioi han
        # va da xu ly het -> ve dau (QC vong 2 M-1: truoc day ghi con tro truoc khi xu ly).
        done_upto, out_of_time = None, False
        for r in reqs:
            if time.monotonic() - t0 > SWEEP_TIME_BUDGET:
                out_of_time = True
                break
            done_upto = r.name
            try:
                if guard.get_active_profile(r.reference_doctype, r.approval_type,
                                            r.reference_name) != p.name:
                    continue
                pkg_name = pkgsvc.signable_package_for_request(r.name)
                if not pkg_name or tasks._outcome_closed(pkg_name):
                    continue
                state = _partner_gate(pkg_name)
                if state == "signed":
                    if _bridge_edge_open(r, pkg_name, step["transition_id"]):
                        if start_bridge_step(r.name).get("started"):
                            started.append(r.name)
                elif state in _PARTNER_FINAL or state.startswith("document_dead:"):
                    events.emit("SignedRetrievalNotReady", package=pkg_name,
                                verification_result=state[:140])
                    tasks._handle_partner_round(pkg_name, state)
            except Exception:
                frappe.db.rollback()
                if _once_per_day("sweep:%s" % r.name):
                    frappe.log_error(frappe.get_traceback(), "esign.portal_steps.bridge %s"
                                     % r.name)
            frappe.db.commit()
        if out_of_time or len(reqs) >= int(limit):
            nxt = done_upto if done_upto is not None else after
        else:
            nxt = ""
        try:
            frappe.cache().set_value(cursor_key, nxt, expires_in_sec=86400)
        except Exception:
            pass
        if out_of_time:
            return started
    return started


def _adapter_for(pkg):
    """(adapter) cho goi, hoac None khi cong tac tich hop TAT (khong goi mang)."""
    from ecentric_workspace.platform.esign import tasks
    if tasks._disabled() or not tasks._integration_open(pkg.provider, pkg.environment):
        return None
    _settings, adapter = tasks._settings_and_adapter(frappe._dict(provider=pkg.provider,
                                                                  environment=pkg.environment))
    return adapter


def _partner_gate(pkg_name):
    """Tinh trang DOI TAC tren tai lieu: "signed" (moi doi tac da gui deu da ky) |
    "waiting_partner" | "partner_rejected" | "partner_returned" | "document_dead:<x>" |
    "partner_info_missing" | "unreadable" | "no_document" | "integration_off".
    Chi DOC (poll_status)."""
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["name", "scts_document_id", "provider", "environment", "profile",
                               "business_doctype", "business_name"], as_dict=True)
    if not pkg or not pkg.scts_document_id:
        return "no_document"
    adapter = _adapter_for(pkg)
    if adapter is None:
        return "integration_off"
    try:
        # Vong quet nen: doc nhanh (5 giay, khong thu lai) neu adapter ho tro (QC vong 2 M-1).
        try:
            doc = adapter.poll_status(pkg.scts_document_id, quick=True)
        except TypeError:
            doc = adapter.poll_status(pkg.scts_document_id)
    except Exception:
        return "unreadable"
    if not doc:
        return "unreadable"
    status = str(getattr(doc, "status", "") or "").strip().lower()
    if status == "cancelled" or (getattr(doc, "identity", None) or {}).get("destroyed"):
        return "document_dead:%s" % (status or "destroyed")
    from ecentric_workspace.platform.esign import signed_files
    ext = signed_files._external_expectation(pkg)
    if not ext:
        return "partner_info_missing"
    signers = getattr(doc, "signers", None) or []
    why = signed_files._partner_state(signers, ext)
    if why:
        return why
    signed = {str(x.get("email") or "").strip().lower() for x in signers
              if str(x.get("status") or "").strip().lower() == "signed"}
    return "signed" if set(ext) <= signed else "waiting_partner"


def _bridge_edge_open(req, pkg_name, transition_id):
    """Canh buoc sau doi tac dang MO tren cong (doc bang tai khoan tich hop)."""
    if not pkg_name:
        return False
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["scts_document_id", "provider", "environment"], as_dict=True)
    if not pkg or not pkg.scts_document_id:
        return False
    from ecentric_workspace.platform.esign import permissions as perms
    mapping = perms.verified_mapping(req.requested_by, pkg.environment)
    if not mapping:
        return False
    adapter = _adapter_for(pkg)
    if adapter is None or not hasattr(adapter, "workflow_state_for_document"):
        return False
    state, _why = adapter.workflow_state_for_document(pkg.scts_document_id, mapping.scts_user_id)
    return bool(state) and any(str(t.get("transition_id")) == str(transition_id)
                               for t in (state.get("transitions") or []))


def sweep_missing_requester_steps(limit=50):
    """Luoi an toan (sweep_stale, moi gio): phieu Pending dang o cap cong dau tien cua ho so lay
    buoc tu cong ma chua co chan nguoi lap nao song / xong -> xep hang (lan mo cap bi lo: cong
    tat luc mo, job mat, anh xa vua sua...)."""
    pairs = frappe.get_all(PROFILE, filters={"enabled": 1, "trust_portal_transitions": 1},
                           fields=["business_doctype", "approval_type"], limit_page_length=50)
    started = []
    for p in pairs:
        # CHI phieu chua co chan nguoi lap nao (loc trong SQL): khong thi 50 phieu cu nhat da
        # co chan bi xet lai moi gio va phieu moi khong bao gio toi luot (QC 12/11).
        reqs = frappe.db.sql("""
            SELECT ar.name, ar.reference_doctype, ar.reference_name, ar.approval_type,
                   ar.current_level
            FROM `tabEC Approval Request` ar
            WHERE ar.reference_doctype = %(dt)s AND ar.approval_type = %(at)s
              AND ar.approval_status = 'Pending' AND ar.current_level > 0
              AND NOT EXISTS (SELECT 1 FROM `tabEC Digital Signature Request` d
                              WHERE d.approval_request = ar.name
                                AND d.actor_type = 'Requester' AND d.action = 'Approve')
            ORDER BY ar.modified ASC LIMIT %(lim)s""",
            {"dt": p.business_doctype, "at": p.approval_type, "lim": int(limit)}, as_dict=True)
        from ecentric_workspace.platform.esign import package as pkgsvc
        for r in reqs:
            try:
                if not _trusting_profile(r) or int(r.current_level) != first_portal_level(r):
                    continue
                # CHI phieu CHUA CO chan nguoi lap nao cho goi nay (lan mo cap bi lo). Chan da
                # chet thi de van hanh - tu tao lai moi gio la spam + rac (QC vong 2).
                if _requester_step_rows(r.name, pkgsvc.signable_package_for_request(r.name)):
                    continue
                if start_requester_step(r.name, quiet=True).get("started"):
                    started.append(r.name)
            except Exception:
                # Bo phan dang do (vd dong DSR vua insert) TRUOC khi commit - khong de lai mot
                # chan Draft/Prepared mo coi khien phieu bi coi la "da co chan" mai mai.
                frappe.db.rollback()
                frappe.log_error(frappe.get_traceback(), "esign.portal_steps.sweep %s" % r.name)
            # Nha khoa dong phieu (start_requester_step khoa FOR UPDATE) sau moi phieu.
            frappe.db.commit()
    return started


def complete_requester_step(dsr_name):
    """Chan nguoi lap da xong (Signed = cong da roi buoc) -> Approval Completed. Khong goi engine:
    cap ERP da mo san, chan nay chi dua tai lieu tren cong toi dung cap do.
    Chan dung han (Manual Review / Permanent Failure) -> bao nguoi lap + nguoi duyet cap dang mo."""
    from ecentric_workspace.platform.esign import service as svc
    dsr = frappe.db.get_value(DSR, dsr_name, ["name", "status", "approval_request",
                                              "actor_user"], as_dict=True, for_update=True)
    if not dsr:
        return {"completed": False, "reason": "dsr_missing"}
    if dsr.status == "Signed":
        if svc._guarded_dsr_transition(dsr_name, "Signed", "Approval Completed",
                                       extra={"completed_at": now_datetime()},
                                       event_type="ApprovalCompleted", erp_actor=dsr.actor_user):
            return {"completed": True}
        return {"completed": True, "note": "already_terminal"}
    if dsr.status in ("Manual Review", "Permanent Failure"):
        req = frappe.db.get_value(AR, dsr.approval_request,
                                  ["name", "reference_doctype", "reference_name",
                                   "requested_by", "current_level"], as_dict=True)
        if req:
            _bao(req, _("ERP chưa chuyển được phiếu sang cổng ký số (bước người lập). Bộ phận "
                        "vận hành đang xử lý - người duyệt chờ trước khi bấm Duyệt."),
                 also_level=True)
        return {"completed": False, "reason": "stopped:%s" % dsr.status}
    return {"completed": False, "reason": "not_in_signed_state"}


def _bao(req, msg, also_level=False):
    """Bao nguoi lap (va nguoi duyet cap dang mo). Nuot loi: kenh phu."""
    try:
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        users = [req.requested_by] if req.get("requested_by") else []
        if also_level and req.get("current_level"):
            users += frappe.get_all("EC Approval Request Approver",
                                    filters={"approval_request": req.name,
                                             "level_no": req.current_level,
                                             "status": "Pending"}, pluck="approver")
        if users:
            engine.notify(sorted(set(users)), msg, req.reference_doctype, req.reference_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign.portal_steps._bao")
