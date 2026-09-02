# Copyright (c) 2026, eCentric and contributors
"""Whitelisted esign API - thin, permission-first wrappers over the services.
No provider knowledge here. Mutations POST-only, login required (no allow_guest
anywhere). The client NEVER supplies userId / SignatureId / transitionId / hash -
everything is resolved server-side (SCTS UAT findings A-E compensating controls).

S2A note: endpoints exist for tests and for S2C/S2D UIs; no page calls them yet and
all gates default closed."""
import base64

import frappe
from frappe import _

from ecentric_workspace.platform.esign import guard
from ecentric_workspace.platform.esign import package as pkgsvc
from ecentric_workspace.platform.esign import permissions as perms
from ecentric_workspace.platform.esign import service as svc
from ecentric_workspace.platform.esign import shapes
from ecentric_workspace.platform.esign import events


def _business_args(business_doctype, business_name):
    if not business_doctype or not business_name:
        frappe.throw(_("Thiếu tham số yêu cầu."))
    if not frappe.db.exists(business_doctype, business_name):
        frappe.throw(_("Không tìm thấy yêu cầu."))
    return business_doctype, business_name


def _file_bytes():
    """Multipart file (preferred) or base64 `filedata` fallback. Content is validated
    downstream (magic bytes / denylist / size)."""
    f = frappe.request.files.get("file") if getattr(frappe, "request", None) \
        and getattr(frappe.request, "files", None) else None
    if f:
        return f.filename, f.stream.read()
    fd = frappe.form_dict.get("filedata")
    fn = frappe.form_dict.get("filename")
    if fd and fn:
        return fn, base64.b64decode(fd)
    frappe.throw(_("Không nhận được tệp tải lên."))


# ------------------------------ package (requester) ------------------------------ #
@frappe.whitelist(methods=["POST"])
def upload_package_file(business_doctype, business_name, requires_signature=0,
                        is_supporting_document=0, share_with_partner=0, file_kind=None):
    _business_args(business_doctype, business_name)
    perms.assert_can_view_business(business_doctype, business_name)
    at = frappe.db.get_value(business_doctype, business_name, "approval_type")
    profile = guard.get_active_profile(business_doctype, at)
    if not profile:
        frappe.throw(_("Ký số chưa được bật cho loại yêu cầu này."))
    file_name, content = _file_bytes()
    pkg = pkgsvc.get_or_create_draft(business_doctype, business_name, profile)
    row = pkgsvc.add_file(pkg.name, file_name, content,
                          requires_signature=int(requires_signature or 0),
                          is_supporting_document=int(is_supporting_document or 0),
                          share_with_partner=int(share_with_partner or 0),
                          file_kind=file_kind)
    return {"package": pkg.name, "file_row": row.name, "sha256": row.sha256}


@frappe.whitelist(methods=["POST"])
def set_file_flags(dsf_name, requires_signature=None, is_supporting_document=None,
                   share_with_partner=None, file_kind=None):
    return pkgsvc.set_file_flags(dsf_name, requires_signature, is_supporting_document,
                                 share_with_partner, file_kind)


@frappe.whitelist(methods=["POST"])
def reorder_files(package, ordered_names):
    names = frappe.parse_json(ordered_names) if isinstance(ordered_names, str) else ordered_names
    pkgsvc.reorder_files(package, names or [])
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def remove_file(dsf_name):
    pkgsvc.remove_file(dsf_name)
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def save_placements(package, placements):
    rows = frappe.parse_json(placements) if isinstance(placements, str) else placements
    n = pkgsvc.save_placements(package, rows or [])
    return {"saved": n}


@frappe.whitelist()
def get_signing_status(business_doctype, business_name):
    _business_args(business_doctype, business_name)
    return svc.get_signing_status(business_doctype, business_name)


@frappe.whitelist()
def get_package_file(dsf_name):
    """Permission-checked private PDF/file streaming for the coordinate editor (S2C).
    NEVER exposes a raw /private/files URL to the client."""
    row = frappe.db.get_value("EC Digital Signature File", dsf_name,
                              ["package", "file", "file_name"], as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy tệp."))
    pkg = frappe.db.get_value("EC Digital Signature Package", row.package,
                              ["business_doctype", "business_name"], as_dict=True)
    perms.assert_can_view_business(pkg.business_doctype, pkg.business_name)
    fdoc = frappe.get_doc("File", row.file)
    frappe.local.response.filename = row.file_name
    frappe.local.response.filecontent = fdoc.get_content()
    frappe.local.response.type = "download"


# ------------------------------ signing (approver) ------------------------------ #
@frappe.whitelist(methods=["POST"])
def approve_and_sign(business_doctype, business_name, comment=None):
    _business_args(business_doctype, business_name)
    return svc.approve_and_sign(business_doctype, business_name, comment=comment)


@frappe.whitelist(methods=["POST"])
def reject_and_transition(business_doctype, business_name, comment=None):
    _business_args(business_doctype, business_name)
    if not (comment or "").strip():
        frappe.throw(_("Bắt buộc nhập lý do từ chối."))
    return svc.reject_with_transition(business_doctype, business_name, comment)


# ------------------------------ ops (System Manager) ------------------------------ #
@frappe.whitelist()
def ops_inbox():
    """Nhung viec ky so dang cho nguoi can thiep. CHI DOC.

    Cac ham cuu ho ben duoi da ton tai va chay dung tu lau, nhung khong giao dien nao goi
    chung - nen `Permanent Failure` va `Cancelled` la ngo cut tren thuc te du may trang thai
    co du duong ra. Endpoint nay la danh sach; hanh dong van di qua tung endpoint rieng, moi
    cai tu kiem quyen lay.
    """
    perms.assert_system_manager()
    from ecentric_workspace.platform.esign import ops
    return ops.inbox()


@frappe.whitelist(methods=["POST"])
def settle_signature_debt(level_name, resolution, reason):
    """Dong mot mon no chu ky: `signed` (nguoi do da tu ky lai) hoac `waived` (khong ky duoc
    nua, mien voi ly do). BAT BUOC ly do; ghi vao lich su phieu. System Manager. Xem
    guard.settle_signature_debt - KHONG co duong nao ky ho ai."""
    from ecentric_workspace.platform.esign import guard as esign_guard
    return esign_guard.settle_signature_debt(level_name, resolution, reason)


@frappe.whitelist(methods=["POST"])
def abandon_signed_retrieval(package_name, reason):
    """Ngung thu tai PDF da ky cho mot goi khong con lay ve duoc. BAT BUOC ly do.

    Chi bat mot co de cron bo qua - khong xoa tep nao, khong doi trang thai goi, va mo lai
    duoc. System Manager. Xem signed_files.abandon_retrieval."""
    from ecentric_workspace.platform.esign import signed_files
    return signed_files.abandon_retrieval(package_name, reason)


@frappe.whitelist(methods=["POST"])
def resume_signed_retrieval(package_name):
    """Mo lai mot goi da ngung, khi tai lieu ben nha cung cap song lai."""
    from ecentric_workspace.platform.esign import signed_files
    return signed_files.resume_retrieval(package_name)


@frappe.whitelist(methods=["POST"])
def retry_signature_request(dsr_name):
    return svc.retry_signature_request(dsr_name)


@frappe.whitelist(methods=["POST"])
def cancel_signature_request(dsr_name, reason=None):
    return svc.cancel_signature_request(dsr_name, reason)


@frappe.whitelist(methods=["POST"])
def test_connection(provider, environment):
    perms.assert_system_manager()
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": provider, "environment": environment}, "*",
                            as_dict=True)
    if not s:
        frappe.throw(_("Chưa có Provider Settings cho cặp này."))
    from ecentric_workspace.platform.esign.providers import get_adapter
    from ecentric_workspace.platform.esign.sanitize import safe_error
    from frappe.utils import now_datetime
    try:
        res = get_adapter(s).test_connection()
        out = {"ok": True, "result": res}
    except Exception as e:
        out = {"ok": False, "error": safe_error(e)}
    frappe.db.set_value("EC Digital Signature Provider Settings", s.name,
                        {"last_connection_test": now_datetime(),
                         "last_connection_result": ("OK" if out["ok"] else out["error"])[:130]})
    return out


@frappe.whitelist(methods=["POST"])
def verify_mapping(mapping_name):
    """SM-gated mapping verification: pulls provider signatures for the mapped user and
    confirms signature_id ownership. Stores SAFE metadata only (no images, no HSM)."""
    perms.assert_system_manager()
    m = frappe.get_doc("EC SCTS User Mapping", mapping_name)
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"environment": m.environment,
                             "integration_enabled": 1}, "*", as_dict=True)
    if not s:
        frappe.throw(_("Không có Provider Settings đang bật cho môi trường này."))
    from ecentric_workspace.platform.esign.providers import get_adapter
    from frappe.utils import now_datetime
    sigs = get_adapter(s).list_user_signatures(m.scts_user_id)
    owned = [x for x in (sigs or []) if str(x.get("id")) == str(m.signature_id)
             and str(x.get("signerId")) == str(m.scts_user_id)]
    if not owned:
        frappe.throw(_("Signature ID không thuộc user SCTS này - từ chối xác minh."))
    meta = owned[0]
    m.db_set({"mapping_status": "Verified", "verified_at": now_datetime(),
              "verified_by": frappe.session.user,
              "signature_meta_summary": ("%s / %s" % (meta.get("type") or "?",
                                                      meta.get("company") or "?"))[:130]})
    return {"verified": True}


@frappe.whitelist()
def list_scts_signatures(scts_user_id, environment=None):
    """READ-ONLY, System Manager only: which signature slots a given SCTS user owns.

    Why this has to exist. `EC SCTS User Mapping.signature_id` is mandatory, and
    `verify_mapping` refuses any id that is not owned by that user - correctly so. But
    nothing exposed the list, so the only way to obtain a valid `signature_id` was to read
    it out of a captured browser request or to guess. Onboarding a signer therefore
    depended on luck, and a wrong guess would have targeted somebody else's signature.

    Returns identifiers and safe labels ONLY: no images, no certificate or HSM material.
    """
    perms.assert_system_manager()
    flt = {"integration_enabled": 1}
    if environment:
        flt["environment"] = environment
    s = frappe.db.get_value("EC Digital Signature Provider Settings", flt, "*", as_dict=True)
    if not s:
        frappe.throw(_("Không có Provider Settings đang bật cho môi trường này."))
    from ecentric_workspace.platform.esign.providers import get_adapter
    rows = get_adapter(s).list_user_signatures(scts_user_id) or []
    return {
        "environment": s.get("environment"),
        "scts_user_id": scts_user_id,
        "signatures": [{"id": r.get("id"), "signerId": r.get("signerId"),
                        "type": r.get("type"), "company": r.get("company"),
                        "active": bool(r.get("active"))} for r in rows],
    }


@frappe.whitelist()
def provider_document_shape(payment_request_name):
    """READ-ONLY, System Manager only: WHICH FIELDS eContract returns for this document.

    Written to end a specific guessing loop. `POST /api/Workflow/transition` is rejected with
    a bare 400 and the suspicion is that `instanceId` must be a WORKFLOW/TASK id while we send
    the DOCUMENT id - the portal's own task screen is `view-tasks.html?id=...`, which is not
    the document id. Rather than try candidate values against a non-idempotent write, this
    reports what the provider actually carries.

    Deliberately returns SHAPE, not content: every key with the TYPE of its value, and the
    VALUE only for keys that look like identifiers and hold a GUID-ish token. No amounts, no
    names, no comments, no file content - so a diagnostic call can never become a data dump.
    """
    perms.assert_system_manager()
    _business_args("EC Payment Request", payment_request_name)
    pkg_name = frappe.db.get_value(
        "EC Digital Signature Package",
        {"business_doctype": "EC Payment Request", "business_name": payment_request_name,
         "status": ["not in", ("Cancelled", "Superseded")]},
        "name", order_by="creation desc")
    if not pkg_name:
        return {"ok": False, "reason": "no_package"}
    doc_id = frappe.db.get_value("EC Digital Signature Package", pkg_name, "scts_document_id")
    if not doc_id:
        return {"ok": False, "reason": "no_provider_document", "package": pkg_name}
    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"integration_enabled": 1}, "*", as_dict=True)
    if not settings:
        frappe.throw(_("Không có Provider Settings đang bật."))
    from ecentric_workspace.platform.esign.providers import get_adapter
    raw = get_adapter(settings).get_document(doc_id)
    return {"ok": True, "package": pkg_name, "document_id": doc_id,
            "shape": shapes.shape_of(raw), "identifiers": shapes.identifiers_of(raw)}


#: Cac truong DUY NHAT duoc phep roi khoi endpoint chan doan cho moi chan ky.
#:
#: Payload nguoi ky cua eContract do duoc 02/09 gom: id, role, roleText, user, email, mobile,
#: cccd, status, date, time, isExternal, icon, rejectReason, identityPlace, identityDate, dob.
#: Tuc la HO TEN, SO CCCD, SO DIEN THOAI va NGAY SINH nam ngay canh cai minh can doc. Day la
#: bo loc TRANG (chi cai co ten o day di ra), khong phai bo loc DEN: nha cung cap them truong
#: moi thi no KHONG tu chay ra ngoai theo.
#:
#: `user_id` giu lai co chu dich - payload KHONG he co userId/signerId/signatureId, nen
#: `_norm_signer` luon cho user_id=None. Nhin thay ca cot None chinh la bang chung rang moi
#: viec doi soat chan ky deu phai dua vao EMAIL, khong con duong nao khac.
_SAFE_SIGNER_KEYS = ("status", "email", "role", "role_text", "sign_type",
                     "signed_at", "is_external", "user_id", "signature_id")

#: Tran so canh chuyen se hoi tiep "ai duoc nhan". Mot lan goi chan doan khong duoc bien
#: thanh mot tran request len nha cung cap.
_MAX_PROBED_TRANSITIONS = 10


@frappe.whitelist()
def provider_workflow_view(dsr_name, transition_id=None, provider_user_id=None):
    """READ-ONLY, System Manager only: eContract NGHI GI ve mot chan ky.

    Viet cho su co 02/09, EC-PAYR-2026-00041 / EC-DSP-2026-00028, chan ky EC-DSR-2026-00027:
    `transition_with_recipients` bi tra 400 "Duong chuyen khong hop le hoac khong khop trang
    thai", code lui ve `approve_and_sign` pool-wide, nha cung cap tra 2xx kem ma giao dich -
    va roi khong co chu ky nao, lich su workflow ben ho cung khong ghi nhan hanh dong nao.
    Hai dau deu bao "on", cai sai nam O GIUA. Khong co cach nao doc duoc phia ho nghi gi ma
    khong ban mot lenh ghi len ho so tien - nen co endpoint nay.

    Tra loi ba cau, moi cau mot khoi rieng:
      1. `document`   - tai lieu dang o trang thai nao, va tung O KY dang o trang thai nao;
      2. `transitions`- voi `provider_user_id` nay thi hien co NHUNG canh chuyen nao;
      3. `recipients` - voi tung canh chuyen, AI duoc phep nhan buoc do
                        (`includes_provider_user` la cau tra loi cho su co tren).

    CHI DOC. Khong gui lenh ky, khong doi trang thai, khong ghi gi vao DB. Tham so
    `provider_user_id` de doi soat mot nguoi KHAC voi nguoi ghi tren chan ky - hoi ho nghi gi
    ve ai la mot cau hoi, khong phai mot hanh dong.

    Du lieu tra ve: dinh danh (GUID), ma trang thai, ten canh chuyen, email cong viec. KHONG
    co so tien, KHONG co noi dung tai lieu, KHONG co ho ten / CCCD / dien thoai / ngay sinh -
    xem `_SAFE_SIGNER_KEYS`. Email PHAI co: payload cua eContract khong mang userId nen day
    la khoa doi soat duy nhat con lai.

    Moi khoi mang bo ba `asked` / `ok` / `error`. "Hoi duoc va danh sach RONG" va "khong hoi
    duoc" la HAI KET LUAN KHAC HAN nhau - gop chung lai la dung cai loi im lang da lam mat
    hai dem cua thang 8.
    """
    perms.assert_system_manager()
    from ecentric_workspace.platform.esign.providers import get_adapter
    from ecentric_workspace.platform.esign.sanitize import safe_error

    dsr = frappe.db.get_value(
        "EC Digital Signature Request", dsr_name,
        ["name", "status", "action", "actor_type", "actor_user", "approver", "package",
         "provider", "environment", "transition_id", "request_attempt",
         "effective_scts_user_id"], as_dict=True)
    if not dsr:
        frappe.throw(_("Không tìm thấy yêu cầu ký."))
    pid = provider_user_id or dsr.get("effective_scts_user_id")
    doc_id = (frappe.db.get_value("EC Digital Signature Package", dsr.get("package"),
                                  "scts_document_id") if dsr.get("package") else None)
    out = {"ok": True, "reason": None,
           # actor_user / approver la email cong viec (User cua Frappe dinh danh bang email),
           # can de doi chieu voi cot email ben duoi.
           "dsr": {k: dsr.get(k) for k in
                   ("name", "status", "action", "actor_type", "actor_user", "approver",
                    "transition_id", "request_attempt")},
           "package": dsr.get("package"), "document_id": doc_id,
           "environment": dsr.get("environment"), "provider_user_id": pid,
           "document": None, "transitions": None, "recipients": []}
    if not doc_id:
        out["ok"], out["reason"] = False, "no_provider_document"
        return out
    if not pid:
        out["ok"], out["reason"] = False, "no_provider_user_id"
        return out
    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"provider": dsr.get("provider"),
                                    "environment": dsr.get("environment")}, "*", as_dict=True)
    if not settings:
        out["ok"], out["reason"] = False, "no_provider_settings"
        return out
    adapter = get_adapter(settings)

    # 1. Tai lieu dang o trang thai nao, va moi o ky dang o trang thai nao.
    try:
        state = adapter.poll_status(doc_id)
        rows = [s for s in (getattr(state, "signers", None) or []) if isinstance(s, dict)]
        signers = [{k: s.get(k) for k in _SAFE_SIGNER_KEYS} for s in rows]
        out["document"] = {"asked": True, "ok": True, "error": None,
                           "status": getattr(state, "status", None),
                           "identity": getattr(state, "identity", None) or {},
                           "signer_count": len(signers), "signers": signers}
    except Exception as exc:
        # Khong doc duoc tai lieu thi NOI RA. Mot khoi rong khong kem ly do se bi doc thanh
        # "tai lieu khong co nguoi ky nao" - dung ket luan sai da tung dong mot cap duyet.
        out["document"] = {"asked": True, "ok": False, "error": safe_error(exc),
                           "status": None, "identity": {}, "signer_count": None,
                           "signers": []}

    # 2. Voi nguoi nay, hien co nhung canh chuyen nao.
    try:
        items = adapter.available_transitions(doc_id, pid) or []
        out["transitions"] = {"asked": True, "ok": True, "error": None,
                              "count": len(items), "items": items}
    except Exception as exc:
        items = []
        out["transitions"] = {"asked": True, "ok": False, "error": safe_error(exc),
                              "count": None, "items": []}

    # 3. Voi tung canh chuyen, ai duoc phep nhan.
    names = {}
    for t in items:
        if isinstance(t, dict) and t.get("transition_id") is not None:
            names[str(t.get("transition_id"))] = t.get("transition_name")
    wanted = [str(transition_id)] if transition_id else sorted(names)
    for tid in wanted[:_MAX_PROBED_TRANSITIONS]:
        row = {"transition_id": tid, "transition_name": names.get(tid), "asked": True,
               "ok": False, "error": None, "count": None, "eligible": [],
               "includes_provider_user": None}
        # `_last_eligible_error` chi duoc GHI luc that bai va khong bao gio duoc xoa. Khong
        # dat lai truoc moi luot thi mot canh hoi duoc nhung tra ve None (payload la) se doi
        # ly do that bai cua canh TRUOC do - mot cau tra loi sai trong tin hon la khong co.
        adapter._last_eligible_error = None
        try:
            eligible = adapter.eligible_recipients(doc_id, tid, pid)
        except Exception as exc:
            row["error"] = safe_error(exc)
            out["recipients"].append(row)
            continue
        if eligible is None:
            row["error"] = (getattr(adapter, "_last_eligible_error", None)
                            or "khong hoi duoc: nha cung cap tra ve du lieu khong doc duoc")
            out["recipients"].append(row)
            continue
        ids = sorted(str(x) for x in eligible)
        row.update({"ok": True, "count": len(ids), "eligible": ids,
                    # Cau tra loi cho su co: eContract nhan 2xx nhung khong lam gi, vi nguoi
                    # nay khong nam trong danh sach duoc nhan buoc do.
                    "includes_provider_user": str(pid) in ids})
        out["recipients"].append(row)
    return out


# camelCase la quy uoc cua eContract ("workflowInstanceId", "fileId"), nen KHONG the doi hoi
# mot ranh gioi truoc "Id" - lan dau viet the va tuot mat dung cai field dang di tim.
@frappe.whitelist(methods=["POST"])
def reconcile_signature_request(dsr_name):
    """System Manager: re-verify a leg parked in Manual Review against what the provider says
    NOW. Completes it when the signature really is there. NEVER sends anything.

    The case this exists for, observed 2026-08-28: a leg was moved to Manual Review because
    the provider had accepted the job and then done nothing for twenty minutes. Hours later
    the signer went to the provider's own portal and signed by hand. The signature is real,
    on the real document - but the ERP had stopped polling, so the approval sat blocked with
    no way forward that did not involve re-sending a signing command. Re-sending would have
    produced a SECOND signature on the same document.

    So this reads, verifies, and completes. It cannot create a signature; the worst it can do
    is refuse.
    """
    perms.assert_system_manager()
    dsr = frappe.db.get_value("EC Digital Signature Request", dsr_name, "*", as_dict=True)
    if not dsr:
        frappe.throw(_("Không tìm thấy yêu cầu ký."))
    if dsr.status != "Manual Review":
        return {"ok": False, "reason": "not_in_manual_review:%s" % dsr.status}
    out = svc.reconcile_manual_review(dsr_name)
    return out



def _source_level_of(request_level_name):
    """Doi ten cap: EC Approval REQUEST Level (ban sao rieng tung phieu) -> EC Approval
    LEVEL (mau quy trinh dung chung).

    O ky tren tai lieu dinh danh cap bang cai THU HAI (signer_plan lay
    `lvl.source_process_level`); con chan ky thi tro toi cai THU NHAT. So thang cai nay voi
    cai kia thi khong bao gio khop.

    Khong doi duoc thi tra None, TUYET DOI khong tra lai id goc: ve chu ky vao o cua nguoi
    khac con te hon la khong ve.
    """
    try:
        return frappe.db.get_value("EC Approval Request Level", request_level_name,
                                   "source_process_level")
    except Exception:
        return None


@frappe.whitelist()
def document_signature_overlay(payment_request_name):
    """Who has ACTUALLY signed this document at the provider, and what their signature looks
    like - so the screen can show the real thing instead of a tick mark.

    Scope is deliberately narrow. Images are returned ONLY for people the provider reports as
    having signed THIS document, and only to someone already allowed to view the request. That
    audience can open the signed PDF and see the very same signatures, so nothing is exposed
    that was not already visible; what is NOT offered is a way to look up an arbitrary person's
    signature image, which would be a much wider door.

    Read-only. Never returns certificate or HSM material.
    """
    _business_args("EC Payment Request", payment_request_name)
    # _business_args CHI kiem ban ghi co ton tai - no khong phai mot phep kiem quyen. Moi
    # endpoint doc khac trong file nay deu goi assert_can_view_business; ban dau tien cua ham
    # nay thi khong, va no tra ve ANH CHU KY. Bat ky ai dang nhap doan duoc ten mot yeu cau
    # deu lay duoc email nguoi ky, gio ky va anh chu ky cua ho.
    perms.assert_can_view_business("EC Payment Request", payment_request_name)
    pkg_name = frappe.db.get_value(
        "EC Digital Signature Package",
        {"business_doctype": "EC Payment Request", "business_name": payment_request_name,
         "status": ["not in", ("Cancelled", "Superseded")]},
        "name", order_by="creation desc")
    if not pkg_name:
        return {"ok": False, "reason": "no_package", "signed": []}
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["scts_document_id", "environment"], as_dict=True)
    if not pkg or not pkg.scts_document_id:
        return {"ok": False, "reason": "no_provider_document", "signed": []}
    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"environment": pkg.environment, "integration_enabled": 1},
                                   "*", as_dict=True)
    if not settings:
        return {"ok": False, "reason": "integration_closed", "signed": []}

    from ecentric_workspace.platform.esign.providers import get_adapter
    adapter = get_adapter(settings)
    state = adapter.poll_status(pkg.scts_document_id)
    signed_emails = {(sg.get("email") or "").strip().lower(): sg
                     for sg in (getattr(state, "signers", None) or [])
                     if (sg.get("status") or "").lower() == "signed" and sg.get("email")}

    # WHICH SLOT was signed comes from OUR OWN completed signing legs, never from matching an
    # email against a slot's candidate list.
    #
    # The first version matched by email, and on 2026-08-28 it drew a signature into the
    # "Direct Manager Review" box because the same person had signed as REQUESTER and also
    # happened to be a candidate for that level. The provider had exactly one signature; the
    # screen showed two, on a box nobody had approved yet. That is the same "email matching is
    # too loose" defect that was fixed in the VERIFICATION path on 2026-08-27, reintroduced in
    # the display path - a screen that misreports who signed is not a cosmetic problem.
    legs = frappe.get_all(
        "EC Digital Signature Request",
        filters={"package": pkg_name, "status": "Approval Completed"},
        fields=["name", "actor_type", "actor_user", "approver", "request_level"])

    out = []
    seen_images = {}
    for leg in legs:
        who = (leg.get("actor_user") or leg.get("approver") or "").strip()
        sg = signed_emails.get(who.lower())
        if not sg:
            continue          # provider has no signature for this leg: say nothing
        image = None
        mapping = perms.verified_mapping(who, pkg.environment)
        if mapping:
            key = mapping.get("signature_id")
            if key not in seen_images:
                # signature_image() is the existing accessor. list_user_signatures() would NOT
                # work here: it normalizes rows through _norm_signature, which drops
                # base64Image - so it returns None every time, silently.
                try:
                    seen_images[key] = adapter.signature_image(mapping.get("scts_user_id"), key)
                except Exception:
                    # A missing picture must never hide the FACT that somebody signed.
                    seen_images[key] = None
            image = seen_images[key]
        # O ky tren PDF nhan dien cap bang `source_process_level` - ten cua EC Approval
        # LEVEL, tuc mau quy trinh dung chung. Con chan ky thi tro toi EC Approval REQUEST
        # Level, ban sao rieng cua tung phieu. Hai cai la hai DocType khac nhau, nen tra
        # thang `request_level` ra day thi KHONG BAO GIO khop mot o ky nao: chu ky cua moi
        # cap duyet khong duoc ve len tai lieu, du da ky that.
        #
        # Chu ky "Nguoi de nghi" van hien vi no khop theo `kind`, khong can level_ref -
        # dung nen mai moi lo ra: 28/08 "ben ERP chua co chu ky, ben SCTS thi co roi".
        level_ref = None
        if leg.get("request_level"):
            level_ref = _source_level_of(leg.get("request_level"))
        out.append({"email": who,
                    "kind": "requester" if leg.get("actor_type") == "Requester" else "approval_level",
                    "level_ref": level_ref,
                    "signed_at": sg.get("signed_at"),
                    "image_base64": image})
    return {"ok": True, "document_id": pkg.scts_document_id, "signed": out}


# ------------------------------ Payment Request e2e (S2B-B) ------------------------------ #
@frappe.whitelist(methods=["POST"])
def pr_approve_and_sign(payment_request_name, comment=None):
    """Payment-Request-scoped governed Duyệt & Ký. The client supplies ONLY the PR name
    and an optional comment - never userId / signatureId / transitionId / hash. Identity,
    level, package, placements and transition are all resolved and validated server-side
    by the governed service (which runs the pre-write signer binding)."""
    _business_args("EC Payment Request", payment_request_name)
    return svc.approve_and_sign("EC Payment Request", payment_request_name, comment=comment)


@frappe.whitelist()
def pdf_page_geometry(dsf_name):
    """Page count + per-page point dimensions for governed placement entry. Permission is
    enforced against the owning package's business document; no raw file URL is exposed."""
    pkg_name = frappe.db.get_value("EC Digital Signature File", dsf_name, "package")
    if not pkg_name:
        frappe.throw(_("Không tìm thấy tệp."))
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["business_doctype", "business_name"], as_dict=True)
    perms.assert_can_view_business(pkg.business_doctype, pkg.business_name)
    return pkgsvc.pdf_page_geometry(dsf_name)


@frappe.whitelist(methods=["POST"])
def reconcile_document_creation(package, scts_document_id=None):
    """SM-gated reconciliation of an AMBIGUOUS AddDocument outcome. Either records the
    provider document id that ops found in SCTS, or clears the unknown marker to permit
    exactly one clean recreate. NEVER runs automatically; never creates a document itself."""
    perms.assert_system_manager()
    return svc.reconcile_document_creation(package, scts_document_id)


@frappe.whitelist()
def signing_readiness(payment_request_name):
    """Backend-computed Duyệt & Ký readiness for the Payment Request panel (read-only)."""
    _business_args("EC Payment Request", payment_request_name)
    return svc.signing_readiness("EC Payment Request", payment_request_name)


# ------------------------------ UAT pilot (S2B-C1) ------------------------------ #
@frappe.whitelist()
def uat_pilot_readiness(payment_request_name=None):
    """Administrator/System Manager-only READ-ONLY UAT pilot readiness checklist."""
    from ecentric_workspace.platform.esign import pilot
    return pilot.uat_pilot_readiness(payment_request_name)


@frappe.whitelist(methods=["POST"])
def run_scts_uat_pilot_probe(payment_request_name, apply=0):
    """Manual opt-in UAT probe. apply=0 (default) = redacted preview with NO external
    calls; apply=1 = heavily gated real UAT submit. Never runs automatically."""
    from ecentric_workspace.platform.esign import pilot
    return pilot.run_scts_uat_pilot_probe(payment_request_name, apply=apply)


@frappe.whitelist()
def esign_document_state(payment_request_name):
    """READ-ONLY diagnosis: what the provider actually says, and why verification decides
    what it decides.

    Until now nothing could answer "why is this leg not verifying?" without shipping code -
    every question cost a deploy cycle, and the 2026-08-27 pilot was spent guessing at a
    document whose signature was in fact already applied. This returns the provider's own
    normalized view side by side with the expectation the verifier is matching against, so
    the mismatch is visible in ONE call.

    System Manager only. No secrets: tokens are never part of the normalized state, and the
    raw provider payload is deliberately NOT returned.
    """
    from ecentric_workspace.platform.esign.providers import get_adapter
    from ecentric_workspace.platform.esign.sanitize import safe_error
    perms.assert_system_manager()
    _business_args("EC Payment Request", payment_request_name)

    pkg_name = frappe.db.get_value(
        "EC Digital Signature Package",
        {"business_doctype": "EC Payment Request", "business_name": payment_request_name,
         "status": ["not in", ("Cancelled", "Superseded")]},
        "name", order_by="creation desc")
    if not pkg_name:
        return {"ok": False, "reason": "no_package"}
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["name", "status", "scts_document_id", "provider", "environment"],
                              as_dict=True)
    if not pkg.scts_document_id:
        return {"ok": False, "reason": "no_provider_document", "package": pkg}

    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"provider": pkg.provider, "environment": pkg.environment},
                                   "*", as_dict=True)
    if not settings:
        return {"ok": False, "reason": "no_provider_settings", "package": pkg}
    adapter = get_adapter(settings)
    try:
        state = adapter.poll_status(pkg.scts_document_id)
    except Exception as exc:
        return {"ok": False, "reason": "poll_failed", "detail": safe_error(exc), "package": pkg}

    dsrs = frappe.get_all("EC Digital Signature Request",
                          filters={"package": pkg_name},
                          # Every field `_expected_for` reads must be here, otherwise the
                          # replay silently differs from what the worker actually computed -
                          # which would make this endpoint lie about the verdict.
                          fields=["name", "status", "actor_type", "approver", "actor_user",
                                  "effective_scts_user_id", "effective_signature_id",
                                  "queued_at", "creation"],
                          order_by="creation desc", limit_page_length=0)
    out = {"ok": True, "package": pkg,
           "provider_status": getattr(state, "status", None),
           # role / role_text / sign_type: eContract noi ro moi o ky thuoc VAI TRO nao va
           # thuoc loai gi. Thieu chung thi mot o chua ai ky hien ra la "(chua gan)" vo danh
           # - khong biet cua cap nao, khong biet dang cho ai.
           "signers": [{"email": s.get("email"), "user_id": s.get("user_id"),
                        "display_name": s.get("display_name"), "status": s.get("status"),
                        "role": s.get("role"), "role_text": s.get("role_text"),
                        "sign_type": s.get("sign_type"),
                        "signed_at": s.get("signed_at")}
                       for s in (getattr(state, "signers", None) or [])],
           "files": [{"file_id": f.get("file_id"), "name": f.get("name")}
                     for f in (getattr(state, "files", None) or [])],
           "requests": dsrs, "verdicts": []}
    # Replay the exact verification for every non-terminal leg: the reason string here is the
    # same one the worker records, so what you read is what the worker decided.
    from ecentric_workspace.platform.esign.providers.base import SignatureProviderAdapter
    for row in dsrs:
        if row.status in ("Approval Completed", "Cancelled", "Superseded", "Rejected"):
            continue
        expected = svc._expected_for(frappe._dict(row, package=pkg_name))
        res = SignatureProviderAdapter.verify_signed_result(state, expected)
        out["verdicts"].append({"request": row.name, "status": row.status,
                                "ok": bool(res.ok), "reason": res.reason,
                                "matched_on_email": expected.get("email"),
                                "signed_after": str(expected.get("signed_after") or "")})
    return out


@frappe.whitelist(methods=["POST"])
def retrieve_signed_files(payment_request_name):
    """SM-gated manual retrieval of the signed PDF(s) for a Payment Request's active
    package (safe read; idempotent; never resends AddDocument/bulk-process)."""
    perms.assert_system_manager()
    _business_args("EC Payment Request", payment_request_name)
    ar = perms.business_approval_request("EC Payment Request", payment_request_name)
    pkg = pkgsvc.active_package_for_request(ar) if ar else None
    if not pkg:
        frappe.throw(_("Không có gói tài liệu đang hoạt động."))
    from ecentric_workspace.platform.esign import signed_files
    return signed_files.retrieve_and_store_for_package(pkg)


# --------------------- signing UX / inbox / multi-select / review (overnight) --------------- #
@frappe.whitelist()
def signing_ui_state(business_doctype, business_name):
    """Backend-authoritative, sanitized signing state for the detail panel (read-only)."""
    _business_args(business_doctype, business_name)
    from ecentric_workspace.platform.esign import ui_state
    return ui_state.signing_ui_state(business_doctype, business_name)


@frappe.whitelist()
def signing_inbox(filters=None, start=0, page_length=20):
    """Permission-scoped, server-paginated Signing Inbox (governed VIEW; not an engine)."""
    from ecentric_workspace.platform.esign import inbox
    return inbox.signing_inbox(filters=filters, start=start, page_length=page_length)


@frappe.whitelist(methods=["POST"])
def preview_multi_select_sign(items):
    """Read-only eligibility preview for multi-select SEQUENTIAL signing - NO writes, NO
    provider calls. (Not provider bulk; SCTS multi-instance batching is deferred.)"""
    from ecentric_workspace.platform.esign import multi_sign
    return multi_sign.preview_multi_select(items)


@frappe.whitelist(methods=["POST"])
def multi_select_sequential_sign(items, comment=None):
    """Governed multi-select SEQUENTIAL signing across business requests. Fail-closed
    whole-selection validation; gated OFF by default; each item is signed independently
    through the verified single-item path - no provider batch call is made or implied."""
    from ecentric_workspace.platform.esign import multi_sign
    return multi_sign.multi_select_sequential_sign(items, comment=comment)


@frappe.whitelist()
def signed_file_reviews(package):
    """List signed-file rows awaiting hash-mismatch review (System Manager)."""
    from ecentric_workspace.platform.esign import review
    return review.pending_reviews(package)


@frappe.whitelist(methods=["POST"])
def resolve_signed_file_review(dsf_name, action, reason=None):
    """Resolve a signed-file hash mismatch: action in {accept, reject, keep}. SM-only,
    idempotent, immutable-audited; never overwrites the accepted file silently."""
    from ecentric_workspace.platform.esign import review
    if action == "accept":
        return review.accept_candidate(dsf_name, reason)
    if action == "reject":
        return review.reject_candidate(dsf_name, reason)
    if action == "keep":
        return review.keep_existing(dsf_name, reason)
    frappe.throw(_("Hành động không hợp lệ."))


@frappe.whitelist()
def placement_editor_config(payment_request_name):
    """Backend-computed EC_PPH_CONFIG for the bundled placement editor. Permission-checked;
    the client supplies ONLY the PR name and receives package/files/version/locked resolved
    server-side (never a raw private-file URL)."""
    _business_args("EC Payment Request", payment_request_name)
    perms.assert_can_view_business("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import ui_state
    st = ui_state.signing_ui_state("EC Payment Request", payment_request_name)
    pkg = st.get("package") or {}
    files = [{"name": f.get("name"), "file_name": f.get("file_name"),
              "is_pdf": f.get("is_pdf"), "requires_signature": f.get("requires_signature")}
             for f in (pkg.get("files") or [])]
    return {"package": pkg.get("name"), "files": files,
            "version": pkg.get("package_version"),
            "locked": bool(pkg.get("status") and pkg.get("status") != "Draft")}


@frappe.whitelist()
def document_setup_state(payment_request_name):
    """Phase A1 read model for the future 'Tài liệu & ký số' UI. Permission-safe; ZERO writes /
    side effects; no SCTS call."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import document_setup as ds
    return ds.get_document_setup_state("EC Payment Request", payment_request_name)


@frappe.whitelist(methods=["POST"])
def set_document_requires_signature(payment_request_name, document_ref, requires_signature,
                                    confirm=0):
    """Phase A1 governed classification write (requester-scoped; package-Draft-only; idempotent;
    no provider/DSR/SCTS/approval side effects). requires_signature canonical; supporting mirror
    written server-side."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import document_setup as ds
    return ds.set_document_requires_signature("EC Payment Request", payment_request_name,
                                              document_ref, requires_signature, confirm=confirm)


@frappe.whitelist(methods=["POST"])
def remove_supporting_attachment(payment_request_name, document_ref):
    """Go mot chung tu BO SUNG vua dinh kem nham, khi phieu dang o "Cần bổ sung".

    Tu choi neu tep nam trong bat ky goi ky nao cua phieu - tep do da/dang duoc ky len.
    Chi nguoi de nghi. Co ghi vet vao lich su phieu. Xem document_setup de biet luat day du.
    """
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import document_setup as ds
    return ds.remove_supporting_attachment("EC Payment Request", payment_request_name,
                                           document_ref)


@frappe.whitelist(methods=["POST"])
def set_representative_attachment(payment_request_name, file_url):
    """Phase A2: set the backward-compatible request_attachment pointer to an uploaded File only
    when currently empty (requester-scoped; never overwrites; no other field touched)."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import document_setup as ds
    return ds.set_representative_attachment("EC Payment Request", payment_request_name, file_url)


@frappe.whitelist()
def placement_state(payment_request_name, document_ref):
    """Phase C read-only placement + progress state for one document (permission-checked)."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import placement_service as ps
    return ps.placement_state("EC Payment Request", payment_request_name, document_ref)


@frappe.whitelist(methods=["POST"])
def save_placement(payment_request_name, document_ref, box):
    """Phase C: create/update one signer-slot signature box (requester-scoped; slot-validated;
    document-scoped; editable Draft only; no provider/freeze)."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import placement_service as ps
    return ps.save_placement("EC Payment Request", payment_request_name, document_ref, box)


@frappe.whitelist(methods=["POST"])
def delete_placement(payment_request_name, document_ref, placement_name):
    """Phase C: delete one signature box (requester-scoped; document-scoped)."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import placement_service as ps
    return ps.delete_placement("EC Payment Request", payment_request_name, document_ref, placement_name)


@frappe.whitelist()
def signer_plan(payment_request_name):
    """Read-only signer plan for the Payment Request signing UI (Phase B1). Permission-safe
    (business view permission required); no writes / side effects; no SCTS call."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import signer_plan as sp
    return sp.resolve_signer_plan("EC Payment Request", payment_request_name)


@frappe.whitelist()
def my_signature_preview(payment_request_name):
    """Self-service SIZE PREVIEW: the CURRENT session user's own mapped SCTS signature image
    (base64 PNG) for the placement drawer's 'Ky thu'. Governed: viewer of the business doc +
    their OWN verified mapping only; provider integration gate must be open; image only -
    no ids/secrets; nothing is stored."""
    from ecentric_workspace.platform.esign import signer_plan as sp
    perms.assert_can_view_business("EC Payment Request", payment_request_name)
    at, prof, err = sp._resolve_type_and_profile(
        "EC Payment Request", payment_request_name,
        perms.business_approval_request("EC Payment Request", payment_request_name))
    if err or not prof:
        return {"image_base64": None, "reason": err or "profile_not_configured"}
    pmeta = frappe.db.get_value("EC Digital Signature Profile", prof,
                                ["provider", "environment"], as_dict=True)
    if not pmeta:
        return {"image_base64": None, "reason": "profile_not_configured"}
    mapping = perms.verified_mapping(frappe.session.user, pmeta.environment)
    if not mapping:
        return {"image_base64": None, "reason": "no_verified_mapping"}
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": pmeta.provider, "environment": pmeta.environment,
                             "integration_enabled": 1}, "*", as_dict=True)
    if not s:
        return {"image_base64": None, "reason": "integration_gated"}
    from ecentric_workspace.platform.esign.providers import get_adapter
    try:
        img = get_adapter(s).signature_image(mapping.scts_user_id, mapping.signature_id)
    except Exception:
        return {"image_base64": None, "reason": "provider_unavailable"}
    return {"image_base64": img}


@frappe.whitelist()
def requester_signing_readiness(payment_request_name):
    """Read-only requester Submit & Sign readiness (fail-closed)."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import requester
    return requester.requester_signing_readiness("EC Payment Request", payment_request_name)


@frappe.whitelist(methods=["POST"])
def requester_submit_and_sign(payment_request_name, comment=None):
    """Governed requester Submit & Sign. Session user must be the authoritative requester
    (no Administrator/System Manager bypass); creates/reuses one requester-scoped DSR."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import requester
    return requester.requester_submit_and_sign("EC Payment Request", payment_request_name,
                                               comment=comment)


@frappe.whitelist(methods=["POST"])
def prepare_requester_signing_package(payment_request_name):
    """Requester 'Prepare Signing Package': create/reuse the package + add eligible PDFs +
    return the editor config. No SCTS call, no DSR. Requester-only (no admin bypass)."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import requester
    return requester.prepare_requester_signing_package("EC Payment Request", payment_request_name)


@frappe.whitelist(methods=["POST"])
def requester_lock_signing_package(payment_request_name):
    """Requester-local package lock (freezes hash; no SCTS). Requester-only; idempotent."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import requester
    return requester.requester_lock_signing_package("EC Payment Request", payment_request_name)


@frappe.whitelist(methods=["POST"])
def requester_reset_invalid_package(payment_request_name):
    """Governed recovery of an INVALID locked requester package (Locked/Active with zero
    requester placements). Authorized STRICTLY for the actual requester (no Administrator /
    System Manager / role bypass); audited; no provider/SCTS/DSR mutation; cancels the invalid
    local package so a fresh Draft can be prepared."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.platform.esign import requester
    return requester.requester_reset_invalid_package("EC Payment Request", payment_request_name)


@frappe.whitelist()
def signature_geometry_check(package):
    """CHI DOC, chi System Manager: chu ky co roi DUNG cho nguoi dat o hay khong.

    VI SAO CAN.
    02/09 do tay tren mot tai lieu that: o ky ERP dat 240x120 point, chu ky SCTS dat thuc te
    180x90 va lech ~238 point. Bon phep do doc lap deu ra ty le 0.75 = 72/96 - SCTS doc con
    so minh gui nhu PIXEL 96 DPI trong khi minh gui POINT. Da bu nghich dao trong
    `providers/scts.py` (`to_provider_box`), nhung do la HIEU CHINH TU DO DAC, chua co xac
    nhan cua nha cung cap. Neu ho sua phia ho thi phep bu lam lech NGUOC LAI - va khong ai
    biet, vi chu ky sai vi tri khong lam hong gi ca, no chi nam sai cho tren chung tu.

    Nen viec doi chieu phai LAM LAI DUOC BAT CU LUC NAO, khong phai mot lan roi thoi: moi lan
    doi hang so, moi lan SCTS len phien ban moi, chay lai mot lenh la biet.

    TRA VE CON SO, KHONG TRA NOI DUNG.
    Ham nay CO tai ban PDF tu nha cung cap, nhung chi de doc hinh hoc cua o chu ky roi vut di.
    No khong tra ve file, khong tra ve chu, khong tra ve ten nguoi, khong tra ve so tien -
    mot lenh chan doan khong duoc phep bien thanh mot duong rut du lieu.
    """
    perms.assert_system_manager()
    pkg = frappe.db.get_value("EC Digital Signature Package", package,
                              ["name", "scts_document_id", "status"], as_dict=True)
    if not pkg:
        frappe.throw(_("Không tìm thấy gói ký."))
    if not pkg.scts_document_id:
        return {"ok": False, "reason": "no_provider_document", "package": pkg.name}

    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"integration_enabled": 1}, "*", as_dict=True)
    if not settings:
        frappe.throw(_("Không có Provider Settings đang bật."))
    from ecentric_workspace.platform.esign.providers import get_adapter
    from ecentric_workspace.platform.esign.sanitize import safe_error
    adapter = get_adapter(settings)

    out = {"ok": True, "package": pkg.name, "document_id": pkg.scts_document_id,
           "package_status": pkg.status, "files": []}

    # CHUA KY XONG thi khong the co ban PDF da ky de doc - va cai can noi ra la "chua ky
    # xong", KHONG phai "SCTS tu choi HTTP 400".
    #
    # 02/09 chinh lenh nay tra ve `SCTS refused get_pdf (HTTP 400)` tren mot tai lieu moi ky
    # 2/5 chan. Toi doc thanh mot loi cua nha cung cap, roi di truy tiep sang `scts_document_
    # file_id` dang trong va suyt ket luan do la nguyen nhan goc - trong khi truong do von
    # duoc backfill o `signed_files` va khong lien quan gi. Mot lenh chan doan bao sai ly do
    # con hai hon mot lenh khong bao gi, vi no dieu nguoi doc di duong khac.
    #
    # Dung CHUNG cong voi duong tai that (`signed_files._terminal_signed_ok`) de khong bao
    # gio ton tai hai dinh nghia "da ky xong" lech nhau giua chan doan va san xuat.
    from ecentric_workspace.platform.esign.signed_files import _terminal_signed_ok
    try:
        da_ky, ly_do = _terminal_signed_ok(adapter, pkg)
    except Exception as exc:
        da_ky, ly_do = False, "khong hoi duoc nha cung cap: %s" % safe_error(exc)
    out["signed_check"] = {"asked": True, "signed": bool(da_ky), "reason": ly_do}

    for f in frappe.get_all("EC Digital Signature File",
                            filters={"package": pkg.name, "requires_signature": 1},
                            fields=["name", "scts_document_file_id"], order_by="creation asc"):
        row = {"file": f.name, "asked": True, "ok": False, "error": None,
               "page_size": None, "signature_rects": None, "placements": [], "diff": None}
        if not da_ky:
            # `asked=False`: khong hoi ban PDF that, va phai noi ro la KHONG hoi - de nguoi
            # doc khong tuong day la cau tra loi cua nha cung cap.
            row["asked"] = False
            row["error"] = "chua ky xong nen chua co ban PDF da ky (%s)" % ly_do
            out["files"].append(row)
            continue
        try:
            res = adapter.get_signed_document(pkg.scts_document_id, f.scts_document_file_id)
        except Exception as exc:
            # Khong hoi duoc thi PHAI noi ro - mot khoi rong im lang tung lam mat nua buoi.
            row["error"] = safe_error(exc)
            out["files"].append(row)
            continue
        try:
            row.update(_pdf_signature_geometry(res["content"]))
            row["ok"] = True
        except Exception as exc:
            row["error"] = "khong doc duoc hinh hoc PDF: %s" % safe_error(exc)
        row["placements"] = [
            {"slot": p.signer_slot_key, "page": p.page_index,
             "x": p.x, "y_top": p.y, "w": p.width, "h": p.height,
             # `lly` la con so ERP THAT SU gui di sau khi lat truc doc - day moi la cai
             # dem so voi PDF, khong phai `y_top`.
             "lly_sent": round(float(_page_height_or(row, 842.0))
                               - float(p.y or 0) - float(p.height or 0), 2)}
            for p in frappe.get_all(
                "EC Digital Signature Placement",
                filters={"package": pkg.name, "signature_file": f.name,
                         "status": ["!=", "Invalid"]},
                fields=["signer_slot_key", "page_index", "x", "y", "width", "height"],
                order_by="creation asc")]
        out["files"].append(row)
    return out


def _page_height_or(row, mac_dinh):
    ps = (row or {}).get("page_size") or {}
    return ps.get("height") or mac_dinh


def _pdf_signature_geometry(content):
    """{page_size, signature_rects[]} doc tu annotation chu ky cua PDF. KHONG tra noi dung."""
    try:
        from pypdf import PdfReader
    except Exception:
        from PyPDF2 import PdfReader  # bench cu
    import io as _io
    reader = PdfReader(_io.BytesIO(content))
    page = reader.pages[0]
    mb = page.mediabox
    rects = []
    for a in (page.get("/Annots") or []):
        o = a.get_object()
        if str(o.get("/FT") or "") != "/Sig":
            continue
        r = [round(float(v), 2) for v in (o.get("/Rect") or [])]
        if len(r) != 4:
            continue
        llx, lly, urx, ury = r
        rects.append({"llx": llx, "lly": lly,
                      "w": round(urx - llx, 2), "h": round(ury - lly, 2)})
    return {"page_size": {"width": round(float(mb.width), 2),
                          "height": round(float(mb.height), 2)},
            "signature_rects": rects}
