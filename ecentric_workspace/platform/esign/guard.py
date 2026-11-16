# Copyright (c) 2026, eCentric and contributors
"""Signing-required approve guard - the server-side bypass control.

SECURITY MODEL (user directives 2026-07-11):
  1. NO ROLE BYPASS. When the active approval level requires digital signature,
     the normal approve path AND the admin override fail closed for every role.
     Approval may complete only through the governed verified-signature path.
     No break-glass override exists in S2A.
  2. frappe.flags IS ONLY A CALL MARKER. The flag carries the candidate
     EC Digital Signature Request name set in-process by the orchestrator
     (HTTP arguments cannot populate frappe.flags). Authorization NEVER rests
     on the flag: every completion is validated against PERSISTED rows -
     request, runtime level, approver row, business document, package
     version+hash, provider-verified signature, idempotency/likeness - under a
     row lock, at the moment engine.approve() runs.

Fail-closed: any lookup miss, mismatch, or error blocks the approval.
Types without an enabled signing profile: one indexed query, behavior unchanged.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign import permissions as perms

FLAG_KEY = "ec_esign_completion_dsr"

_MSG_SIGN_REQUIRED = "Cấp duyệt này yêu cầu ký số. Vui lòng dùng chức năng 'Duyệt & Ký'."


def _gates_open(provider, environment):
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": provider, "environment": environment},
                            ["integration_enabled", "allow_signing", "allow_production_signing"],
                            as_dict=True)
    if not s or not s.integration_enabled or not s.allow_signing:
        return False
    if environment == "Production" and not s.allow_production_signing:
        return False
    return True


PROFILE = "EC Digital Signature Profile"
#: Goi da qua Draft (da khoa / da gui cong / da xong): ho so cua goi la ho so cua phieu.
_FROZEN_PACKAGE_STATES = ("Locked", "Provider Creating", "Provider Created",
                          "Provider Create Failed", "Active", "Completed")


def _frozen_profile(reference_doctype, business_name):
    """Ho so cua goi ky DA KHOA moi nhat cua phieu, hoac None (QC2 12/11).

    Goi khoa giu profile/provider/environment; worker tao tai lieu tren cong theo do. Neu guard
    doc lai `esign_flow` sau luc khoa ma truong da doi -> ERP tinh cap ky / cai dat theo ho so B
    trong khi cong chay ho so A (lop "chuoi ERP lech chuoi cong"). Nen: co goi khoa thi theo goi.
    CHI goi khi loai dung selector - DNTT khong ton them truy van nao.
    TODO PR-C (nhieu goi / phieu theo `purpose`): loc them theo purpose."""
    rows = frappe.get_all("EC Digital Signature Package",
                          filters={"business_doctype": reference_doctype,
                                   "business_name": business_name,
                                   "status": ["in", list(_FROZEN_PACKAGE_STATES)]},
                          fields=["profile"], order_by="creation desc", limit_page_length=1)
    return (rows[0].get("profile") if rows else None) or None


def _profile_rows(reference_doctype, approval_type, business_name=None):
    """Ho so DANG BAT cho (doctype, loai yeu cau), da LOC theo phieu cu the neu co.

    Hop dong (12/11/2026): MOT loai chung tu co NHIEU ho so ky - moi quy trinh tren cong
    (KOL/KOC WF09, HD lao dong WF03...) mot ho so - va phieu chon quy trinh qua mot truong
    (`esign_flow`). Ho so khai `selector_field` + `selector_value`; ham nay doc gia tri truong
    do tren phieu `business_name` va giu ho so khop.

      * Khong ho so nao khai selector (DNTT hien nay) -> tra nguyen danh sach: Y HET truoc.
      * Co `business_name`: ho so co selector khop gia tri tren phieu; khong ho so nao khop thi
        ho so KHONG khai selector la mac dinh. Gia tri trong / khong khop + khong co mac dinh
        -> rong = phieu nay khong ky so (vd `khong_ky_cong`).
      * Khong co `business_name` ma co ho so khai selector -> tra nguyen danh sach; nguoi goi
        thay >1 thi bao "khong chon duoc" (get_enabled_profile) - KHONG doan.
    """
    rows = frappe.get_all(PROFILE, filters={"business_doctype": reference_doctype,
                                            "approval_type": approval_type, "enabled": 1},
                          fields=["name", "provider", "environment", "selector_field",
                                  "selector_value"],
                          order_by="name asc", limit_page_length=20)
    if not business_name or not any(r.get("selector_field") for r in rows):
        return rows
    frozen = _frozen_profile(reference_doctype, business_name)
    if frozen:
        # Ho so cua goi da tat thi coi nhu tat (y het truoc PR: tat ho so = khong ky) - KHONG
        # roi xuong chon theo truong, vi se ra ho so khac voi cai cong dang chay.
        return [r for r in rows if r.get("name") == frozen]
    values = {}
    picked = []
    for r in rows:
        field = (r.get("selector_field") or "").strip()
        if not field:
            continue
        if field not in values:
            values[field] = (frappe.db.get_value(reference_doctype, business_name, field)
                             if frappe.db.has_column(reference_doctype, field) else None)
        have = values[field]
        if have not in (None, "") and str(have) == str(r.get("selector_value") or ""):
            picked.append(r)
    if picked:
        return picked
    return [r for r in rows if not (r.get("selector_field") or "").strip()]


def get_active_profile(reference_doctype, approval_type, business_name=None):
    """Enabled profile whose provider gates are open, or None. None => signing layer
    inert for this type (existing behavior, bit-identical). `business_name`: chon ho so theo
    phieu khi mot loai co nhieu ho so (xem _profile_rows)."""
    rows = _profile_rows(reference_doctype, approval_type, business_name)
    if len(rows) > 1 and any((r.get("selector_field") or "").strip() for r in rows):
        # Con nhieu ho so co selector = nguoi goi quen truyen ten phieu (hoac cau hinh hai truong
        # chon khac nhau cung khop). KHONG doan (QC 12/11): tra None o day lai la "khong can ky"
        # cho assert_level_completable - con te hon. Nem nhu get_enabled_profile.
        frappe.throw(_("Cấu hình sai: nhiều Hồ sơ ký số khớp {0} / {1}{2} - không chọn được.")
                     .format(reference_doctype, approval_type,
                             (" " + business_name) if business_name else ""))
    for r in rows:
        if _gates_open(r.provider, r.environment):
            return r.name
    return None


def selector_in_use(reference_doctype, approval_type):
    """Co ho so DANG BAT nao cua cap nay chon theo truong tren phieu khong. Dung de nguoi goi
    biet ket qua chinh sach co phu thuoc TUNG PHIEU hay chi phu thuoc loai (nho dem theo loai
    duoc thi nho, vd reporting)."""
    return bool(frappe.db.exists(PROFILE, {"business_doctype": reference_doctype,
                                           "approval_type": approval_type, "enabled": 1,
                                           "selector_field": ["is", "set"]}))


def get_enabled_profile(reference_doctype, approval_type, business_name=None):
    """The exact ENABLED Digital Signature Profile for (business_doctype, approval_type),
    resolved INDEPENDENTLY of provider execution gates (integration / document-creation /
    signing / bulk / callback / production). Profile POLICY (e.g. requester_signature_required
    and approver signature policy intent) is a configuration question and must not depend on
    whether the external write gate is open - the gates only govern the actual provider call.
    Fails closed if MORE THAN ONE enabled profile exists for the exact pair (ambiguous config);
    never silently picks an arbitrary row. `business_name`: chon ho so theo phieu khi mot loai
    co nhieu ho so (xem _profile_rows)."""
    rows = _profile_rows(reference_doctype, approval_type, business_name)
    if not rows:
        return None
    if len(rows) > 1:
        frappe.throw(_("Cấu hình sai: có nhiều hơn một Hồ sơ ký số đang bật cho {0} / {1} "
                       "mà không chọn được theo phiếu{2}. Mỗi hồ sơ cần 'Trường chọn' + 'Giá trị "
                       "chọn' khác nhau, hoặc chỉ bật đúng một hồ sơ.").format(
            reference_doctype, approval_type,
            (" " + business_name) if business_name else ""))
    return rows[0].name


def request_final_level(approval_request):
    """The highest frozen runtime approver level for a request (resolved dynamically per
    request from the Approval Engine's frozen approver rows - never from the profile)."""
    if not approval_request:
        return None
    rows = frappe.get_all("EC Approval Request Approver",
                          filters={"approval_request": approval_request},
                          fields=["level_no"], order_by="level_no desc", limit_page_length=1)
    return rows[0].level_no if rows else None


def _approver_signature_policy(profile):
    """The profile's approver signature policy. An unset value (existing pre-migration
    profiles) maps to 'Selected Approval Levels', which reproduces the OLD per-level-row
    behavior EXACTLY - so existing profiles are unchanged (backward compatible)."""
    return (frappe.db.get_value("EC Digital Signature Profile", profile,
                                "approver_signature_policy") or "Selected Approval Levels")


def requester_signature_required(reference_doctype, approval_type, business_name=None):
    """Whether the requester must Submit & Sign before Level 1 (policy flag on the profile).
    Uses the gate-INDEPENDENT enabled-profile lookup: the requester-signature policy defers
    Level 1 even while provider write gates are OFF (the actual signing write stays fenced by
    the gates in the worker/binding). Requester signing is NOT an approval level."""
    profile = get_enabled_profile(reference_doctype, approval_type, business_name)
    if not profile:
        return False
    return bool(frappe.db.get_value("EC Digital Signature Profile", profile,
                                    "requester_signature_required"))


# Default requester role title when the profile leaves it blank (item 4/5 derivation).
_DEFAULT_REQUESTER_ROLE = "Nguoi de nghi"


def derive_signature_type(mapping):
    """signatureType from the resolved Verified SCTS mapping metadata (never hand-entered per
    level).  is a row/dict from permissions.verified_mapping. Returns None when the
    mapping carries no signature_type (the adapter may then omit it)."""
    if mapping is None:
        return None
    if isinstance(mapping, dict):
        return mapping.get("signature_type")
    return getattr(mapping, "signature_type", None)


def derive_role_title(profile, level_no=None, is_requester=False, process_role_title=None,
                      override=None):
    """Governed roleTitle so admins need not type one per level. Precedence:
    explicit override (profile Level override / provider-required exact value) -> requester
    role title (profile field or the safe default) -> Approval Process level/runtime role
    title -> a derived 'Cap duyet <n>'. Never stores a fixed signer user."""
    if override:
        return override
    if is_requester:
        rt = frappe.db.get_value("EC Digital Signature Profile", profile,
                                 "requester_role_title") if profile else None
        return rt or _DEFAULT_REQUESTER_ROLE
    if process_role_title:
        return process_role_title
    return ("Cap duyet %s" % level_no) if level_no is not None else None


_UNSET = object()


def level_requires_signature(reference_doctype, approval_type, level_no, final_level=None,
                             ignore_gates=False, business_name=None, _profile=_UNSET):
    """True when the active profile's Approver Signature Policy makes THIS Approval Engine
    level require a digital signature. Policy-driven so admins need not recreate every level:
      * None                     -> no level requires signing;
      * All Approval Levels      -> every level requires signing (no per-level rows needed);
      * Final Approval Level Only-> only the highest runtime level (final_level, resolved
                                    dynamically from the request's frozen approvers);
      * Selected Approval Levels -> only levels with a requires_signature Signing Levels row
                                    (the OLD behavior; also the backward-compat default).
    The Approval Engine still owns approvers/order/completion; this only decides WHICH levels
    are signable."""
    # `ignore_gates=True` hoi CHINH SACH thay vi hoi "co gui duoc ngay khong": duong ghi no
    # chu ky can biet cap nay LE RA co phai ky khong, ke ca khi cong dang tat. Dung chung mot
    # than de hai cau tra loi khong the troi khoi nhau - ban dau viet thanh mot ham song song
    # va do dung la cach hai luat bat dau lech nhau.
    # `_profile`: level_portal_action da resolve ho so roi thi truyen vao - khong hoi lai.
    if _profile is not _UNSET:
        profile = _profile
    else:
        profile = (get_enabled_profile(reference_doctype, approval_type, business_name)
                   if ignore_gates
                   else get_active_profile(reference_doctype, approval_type, business_name))
    if not profile:
        return False
    policy = _approver_signature_policy(profile)
    if policy == "None":
        return False
    if policy == "All Approval Levels":
        return True
    if policy == "Final Approval Level Only":
        return bool(final_level is not None and int(level_no) == int(final_level))
    # Selected Approval Levels (default / backward-compatible)
    return bool(frappe.db.exists("EC Digital Signature Profile Level",
                                 {"parent": profile, "level_no": level_no,
                                  "requires_signature": 1}))


_MSG_PORTAL_APPROVE = ("Cấp duyệt này duyệt qua cổng ký số (không ký) - dùng nút 'Duyệt & Ký' "
                       "để ERP chuyển luôn bước của bạn trên cổng (không đặt chữ ký).")


def _deny(reason_code, msg=None):
    frappe.throw(_(msg or _MSG_SIGN_REQUIRED) + " [%s]" % reason_code, frappe.PermissionError)


def _approve_level_row(profile, level_no):
    """Ho so khai cap nay la buoc DUYET KHONG KY tren cong (`provider_action` = Approve)."""
    if not profile or level_no is None:
        return False
    return bool(frappe.db.exists("EC Digital Signature Profile Level",
                                 {"parent": profile, "level_no": level_no,
                                  "provider_action": "Approve"}))


def level_portal_action(reference_doctype, approval_type, level_no, final_level=None,
                        ignore_gates=False, business_name=None):
    """Cap nay lam gi tren cong: "Sign" (ky) | "Approve" (chuyen buoc, khong ky) | None (chi
    ERP). 12/11/2026, hop dong WF09: Ke toan bam Duyet tren ERP = ERP gui buoc cua ho tren
    cong, khong ky. "Sign" thang "Approve" (cap da bat ky thi ky). Ho so khong co dong
    Approve nao (DNTT) -> y het level_requires_signature."""
    profile = (get_enabled_profile(reference_doctype, approval_type, business_name)
               if ignore_gates
               else get_active_profile(reference_doctype, approval_type, business_name))
    if not profile:
        return None
    if level_requires_signature(reference_doctype, approval_type, level_no,
                                final_level=final_level, ignore_gates=ignore_gates,
                                business_name=business_name, _profile=profile):
        return "Sign"
    return "Approve" if _approve_level_row(profile, level_no) else None


def validate_completion(dsr_name, req, level_no, actor, expected_action="Sign"):
    """Persisted-DB validation of a verified signing request. Every check reads the
    database; the in-process flag only NAMES the candidate row. Throws on the first
    failure with a short reason code (safe to surface).

    `expected_action` "Approve" (12/11/2026): cap duyet KHONG KY tren cong. Cung moi phep kiem;
    "Signed" + verified_at o day nghia la cong DA ROI buoc cua nguoi nay (tasks)."""
    msg = _MSG_PORTAL_APPROVE if expected_action == "Approve" else None
    if not dsr_name:
        _deny("no_completion_marker", msg)

    # Freshness + concurrency: locking read in ONE statement (lock-then-plain-read returns
    # the transaction's stale snapshot under REPEATABLE READ - see events.current_status).
    dsr = frappe.db.get_value(
        "EC Digital Signature Request", dsr_name,
        ["name", "approval_request", "request_level", "approver_row", "approver", "action",
         "status", "package", "package_version", "package_hash", "verified_at"],
        as_dict=True, for_update=True)
    if not dsr:
        _deny("dsr_missing")
    if dsr.action != expected_action:
        _deny("dsr_wrong_action", msg)
    if dsr.status != "Signed":
        # Also covers 'completion already occurred' (status would be Approval Completed)
        _deny("dsr_not_in_signed_state:%s" % dsr.status)
    if not dsr.verified_at:
        _deny("dsr_not_verified")
    if dsr.approval_request != req.name:
        _deny("approval_request_mismatch")
    if dsr.approver != actor:
        _deny("actor_mismatch")

    # Runtime level match (persisted snapshot, not caller-supplied).
    rl = frappe.db.get_value("EC Approval Request Level", dsr.request_level,
                             ["level_no", "approval_request", "level_status"], as_dict=True)
    if not rl or rl.approval_request != req.name:
        _deny("request_level_mismatch")
    if rl.level_no != level_no or req.current_level != level_no:
        _deny("level_no_mismatch")

    # Current approver row still pending (also proves the level is not completed).
    ar = frappe.db.get_value("EC Approval Request Approver", dsr.approver_row,
                             ["approver", "level_no", "status", "approval_request"], as_dict=True)
    if not ar or ar.approval_request != req.name or ar.approver != actor:
        _deny("approver_row_mismatch")
    if ar.level_no != level_no:
        _deny("approver_row_level_mismatch")
    if ar.status != "Pending":
        _deny("approver_row_not_pending:%s" % ar.status)

    if req.approval_status != "Pending":
        _deny("request_not_pending:%s" % req.approval_status)

    # Package: business document + version + hash + not superseded/cancelled.
    pkg = frappe.db.get_value(
        "EC Digital Signature Package", dsr.package,
        ["approval_request", "business_doctype", "business_name", "status",
         "package_version", "package_hash"], as_dict=True)
    if not pkg or pkg.approval_request != req.name:
        _deny("package_mismatch")
    if pkg.status != "Active":
        _deny("package_not_active:%s" % pkg.status)
    if pkg.business_doctype != req.reference_doctype or pkg.business_name != req.reference_name:
        _deny("business_document_mismatch")
    if not pkg.package_hash or dsr.package_hash != pkg.package_hash:
        _deny("package_hash_mismatch")
    if int(dsr.package_version or 0) != int(pkg.package_version or -1):
        _deny("package_version_mismatch")

    # Idempotency/concurrency still hold: no OTHER completion for this level.
    other = frappe.db.exists("EC Digital Signature Request",
                             {"approval_request": req.name, "request_level": dsr.request_level,
                              "status": "Approval Completed", "name": ["!=", dsr.name]})
    if other:
        _deny("level_already_completed_by:%s" % other)
    return True


def assert_level_completable(req, level_no, actor):
    """Called from engine.service.approve() AND admin_override_current_level() for every
    request. No-op unless the active level requires signature under an enabled+gated
    profile; then the persisted verified-signature completion is mandatory - for
    EVERY role, with NO override."""
    # final_level PHAI duoc truyen. Thieu no thi voi chinh sach "Final Approval Level Only"
    # nhanh kiem la `final_level is not None and ...` -> luon False -> ham nay thoat som va
    # cong bat buoc ky so KHONG BAO GIO chay. Day la cong duy nhat ma engine.approve() va
    # admin_override_current_level() dua vao, nen hau qua la nut "Duyet" thuong hoan tat cap
    # cuoi ma khong can chu ky nao - trong khi giao dien van bao "phai Duyet & Ky", vi
    # service.py va inbox.py deu truyen final_level.
    # Cung ho voi allow_production_signing: cong nhin chat nhung khong kiem duoc gi.
    if not level_requires_signature(req.reference_doctype, req.approval_type, level_no,
                                    final_level=request_final_level(req.name),
                                    business_name=req.reference_name):
        # Cong DONG nhung CHINH SACH van doi chu ky o cap nay -> khong chan, nhung GHI NO.
        #
        # Truoc 31/08 nhanh nay im hoan toan: tat `allow_signing` la nut "Duyet" thuong hoan
        # tat mot cap le ra bat buoc ky so, khong chu ky, khong canh bao, khong mot dong nao
        # trong lich su noi rang cap do duoc duyet trong luc ky so dang tat. Nhin lai sau vai
        # thang thi phieu do trong y het mot phieu da ky day du.
        #
        # Chu y su bat doi xung: `requester_signature_required` dung duong tra cuu KHONG phu
        # thuoc cong, con duong cap duyet thi phu thuoc. Nen nguoi de nghi van bi bat ky trong
        # khi cap duyet thi khong.
        if _portal_approve_level(req, level_no, actor):
            return
        _record_signature_debt(req, level_no, actor)
        return
    dsr_name = getattr(frappe.flags, FLAG_KEY, None)  # call marker ONLY (see module docstring)
    validate_completion(dsr_name, req, level_no, actor)


def _portal_approve_level(req, level_no, actor):
    """Cap DUYET KHONG KY tren cong (12/11/2026): chi hoan tat qua chan "Approve" da xac minh
    (cong da roi buoc cua nguoi nay). Tra True = da kiem xong o day (nguoi goi dung lai).

    Cong ky so TAT ma chinh sach van la buoc tren cong -> CHAN, khong ghi no nhu cap ky: duyet
    tren ERP ma cong dung yen thi moi buoc sau tren cong lech mot nac (nguoi sau gui buoc cua
    minh khi cong con cho nguoi truoc) - khong co duong "duyet bu" nhu "ky bu"."""
    dt, at, bn = req.reference_doctype, req.approval_type, req.reference_name
    try:
        profile = get_enabled_profile(dt, at, bn)
    except Exception:
        # Cau hinh mo ho cu (hai ho so khong selector): truoc day nhanh nay chi ghi no va NUOT
        # loi. Khong de no thanh duong nem moi cho moi cap khong ky (QC 12/11).
        return False
    if not _approve_level_row(profile, level_no):
        return False
    if not get_active_profile(dt, at, bn):
        _deny("portal_gates_closed", "Cổng ký số đang tắt - cấp này phải duyệt qua cổng, "
                                     "vui lòng chờ cổng mở lại.")
    dsr_name = getattr(frappe.flags, FLAG_KEY, None)
    validate_completion(dsr_name, req, level_no, actor, expected_action="Approve")
    return True


def _record_signature_debt(req, level_no, actor):
    """Danh dau mot cap duyet hoan tat MA CHUA CO chu ky so, khi cong ky so dang tat.

    Chi ghi khi CHINH SACH that su doi chu ky o cap nay (`get_enabled_profile` - doc lap voi
    cong). Cac loai yeu cau khong dung ky so thi khong co gi de no.

    Ghi hong KHONG duoc lam gay viec duyet: mot cap duyet khong hoan tat duoc vi so ke toan
    ghi loi thi te hon la mot mon no khong ghi lai duoc. Nhung cung khong nuot im lang -
    Error Log giu lai de con lan ra.

    Duong tra no la `settle_signature_debt` o duoi: mot NGUOI doc danh sach roi danh dau `da
    ky bu` hoac `mien`, kem ly do. KHONG co duong tu dong ky bu - cap da Approved khong co
    canh quay lai trong may trang thai, va tai lieu ben SCTS co the da dong, nen khong phai
    luc nao cung ky duoc nua. Dong lich su o duoi ban dau hua "chu ky se duoc yeu cau lai khi
    cong mo" - mot loi hua khong co gi dang sau; da sua cho dung su that.
    """
    try:
        profile = get_enabled_profile(req.reference_doctype, req.approval_type,
                                      req.reference_name)
        if not profile:
            return                                    # loai nay khong dung ky so
        if not level_requires_signature(req.reference_doctype, req.approval_type, level_no,
                                        final_level=request_final_level(req.name),
                                        ignore_gates=True, business_name=req.reference_name):
            return                                    # chinh sach khong doi ky o cap nay
        rl = frappe.db.get_value("EC Approval Request Level",
                                 {"approval_request": req.name, "level_no": level_no}, "name")
        if not rl:
            return
        frappe.db.set_value("EC Approval Request Level", rl,
                            {"signature_deferred": 1,
                             "signature_deferred_at": now_datetime(),
                             "signature_deferred_by": actor or frappe.session.user})
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        engine.log_action(req.name, "Commented", actor,
                          level_no=level_no,
                          comment=_("Cấp này hoàn tất khi cổng ký số đang tắt — CÒN NỢ chữ ký "
                                    "số. Món nợ được liệt kê tại trang “Chân ký cần can "
                                    "thiệp”; chỉ chính người duyệt này ký bù được."))
        events.emit("SignatureDeferred", request_meta={
            "approval_request": req.name, "level_no": level_no,
            "actor": actor or frappe.session.user,
            "reference_doctype": req.reference_doctype, "reference_name": req.reference_name})
        # Bao cho CHINH NGUOI DUYET DO. Dong lich su o tren viet "chi chinh nguoi duyet
        # nay ky bu duoc" ma khong he bao cho ho: mon no chi hien o /ec-esign/ops -
        # trang cua nguoi truc van hanh, khong phai cua nguoi duyet. Nguoi DUY NHAT tra
        # duoc no lai la nguoi duy nhat khong biet minh dang no; nhin tu ngoai, mot phieu
        # no chu ky trong y het mot phieu da ky day du.
        # Dat SAU phan ghi so va boc try RIENG: ghi no + dong lich su + su kien la bat
        # buoc, thong bao la kenh phu. Gop chung mot try thi mot loi khi gui thong bao
        # se nuot luon ca mon no - dung cai ma ban va nay sinh ra de tranh.
        try:
            engine.notify([actor or frappe.session.user],
                          _("Còn nợ chữ ký số ở cấp {0}").format(level_no),
                          req.reference_doctype, req.reference_name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign.guard debt notify")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign.guard._record_signature_debt")


def settle_signature_debt(level_name, resolution, reason):
    """Dong mot mon no chu ky - bang GHI NHAN, khong bang ky ho.

    Vi sao khong co nut "ky bu tu dong": chu ky so la hanh dong cua nguoi giu chung thu tren
    he thong cua nha cung cap. He thong nay khong ky thay ai duoc, va mot co che "tu ky khi
    cong mo lai" chinh la lop loi da gay ra su co UAT 27/08. Nen o day chi co hai ket cuc
    trung thuc:

      * `signed`  - nguoi duyet do DA tu ky lai tren cong SCTS, va quan tri xac nhan dieu do;
      * `waived`  - khong ky duoc nua (tai lieu ben nha cung cap da dong, nguoi do da nghi
                    viec...), nen mon no duoc mien VOI LY DO, va ly do do nam lai vinh vien.

    Ca hai deu BAT BUOC ly do, deu ghi vao lich su phieu, va deu la viec cua System Manager.
    Khong co duong nao dong mot mon no ma khong de lai ai dong, luc nao, vi sao - mot danh
    sach no tu no rong di la mot danh sach vo nghia.
    """
    perms.assert_system_manager()
    if resolution not in ("signed", "waived"):
        frappe.throw(_("Cách xử lý không hợp lệ."), frappe.ValidationError)
    if not (reason or "").strip():
        frappe.throw(_("Bắt buộc nêu lý do: đây là hồ sơ duyệt chi, và món nợ chữ ký chỉ "
                       "đóng lại được kèm giải trình."), frappe.ValidationError)

    row = frappe.db.get_value("EC Approval Request Level", level_name,
                              ["name", "approval_request", "level_no",
                               "signature_deferred", "signature_settled_at",
                               "signature_deferred_by"], as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy cấp duyệt này."))
    if not row.signature_deferred:
        frappe.throw(_("Cấp duyệt này không có nợ chữ ký."))
    if row.signature_settled_at:
        return {"ok": True, "already": True}          # idempotent

    frappe.db.set_value("EC Approval Request Level", row.name,
                        "signature_settled_at", now_datetime())
    label = _("đã ký bù") if resolution == "signed" else _("được miễn")
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    engine.log_action(row.approval_request, "Commented", frappe.session.user,
                      level_no=row.level_no,
                      comment=_("Nợ chữ ký số của cấp này {0}. Người nợ: {1}. Lý do: {2}"
                                ).format(label, row.signature_deferred_by or "?",
                                         reason.strip()))
    events.emit("SignatureDebtSettled", request_meta={
        "approval_request": row.approval_request, "level_no": row.level_no,
        "resolution": resolution, "owed_by": row.signature_deferred_by,
        "settled_by": frappe.session.user, "reason": reason.strip()[:500]})
    return {"ok": True, "resolution": resolution}
