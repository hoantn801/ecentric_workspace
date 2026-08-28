# Copyright (c) 2026, eCentric and contributors
"""Who handles the provider document NEXT, and with which provider transition.

Why this module exists
----------------------
eContract's workflow notifies a whole ROLE POOL unless the caller names the next handler.
On 2026-08-27 that let a colleague who was not the designated approver sign
EC-PAYR-2026-00026 forty seconds after it was submitted, bypassing the ERP approval chain
entirely. The portal itself always names the next handler (`toUsers`), and it refuses to
proceed without one - our API path simply never sent it.

Design
------
* The ERP approval chain is the ONLY source of truth for who comes next. We read the
  persisted approver rows, never a role or a guess.
* The provider-side transition metadata (transition id / name / action code / sign type) is
  CONFIG on the profile, never constants in code: they differ per workflow and per stage,
  and inventing them is how you sign the wrong stage.
* Fail SOFT, but never SILENT: when the next handler cannot be named (no verified provider
  mapping for that person, or no configured transition) the caller keeps the old pool-wide
  path and records exactly why, so the gap is visible in the audit trail instead of being
  discovered months later on a signed document.
"""
import frappe

AR = "EC Approval Request"
APPROVER = "EC Approval Request Approver"
LEVEL = "EC Approval Request Level"


def resolve_transition_config(profile_name, action, stage=None):
    """Provider transition metadata for (action, stage) from the profile, or None.

    `stage` lets one profile describe several steps of the same action - e.g. the requester
    submission and an approval level are both "Sign" but carry different provider ids.
    An exact stage match wins; a row with no stage acts as the default.
    """
    if not profile_name:
        return None
    # Read the rows off the PARENT document. `EC Digital Signature Profile Transition` is a
    # child table (istable=1) and Frappe refuses a get_all() on one without a parent - the
    # first version of this function did exactly that, so every signing job died right after
    # BindingValidated with the DSR left sitting at Queued.
    try:
        profile = frappe.get_doc("EC Digital Signature Profile", profile_name)
    except Exception:
        return None
    rows = [{"transition_id": r.transition_id, "transition_name": r.transition_name,
             "process_action": r.process_action, "sign_type": r.sign_type,
             "stage": r.stage, "terminal": r.terminal}
            for r in (profile.get("transitions") or []) if r.action == action]
    if not rows:
        return None
    exact = [r for r in rows if (r.get("stage") or "") == (stage or "")]
    default = [r for r in rows if not (r.get("stage") or "")]
    row = (exact or default or [None])[0]
    if not row:
        return None
    if row.get("transition_id") is None or not row.get("process_action"):
        # Half-configured is worse than unconfigured: it would send a payload the provider
        # cannot act on. Treat it as absent so the caller falls back and says so.
        return None
    return {"transition_id": row["transition_id"],
            "transition_name": row.get("transition_name") or "",
            "process_action": row["process_action"],
            "sign_type": row.get("sign_type") or "",
            "terminal": bool(row.get("terminal"))}


def next_level_approvers(approval_request, current_level):
    """ERP users who may act on the level AFTER `current_level` (pending rows only).

    `current_level` 0 means the requester leg: the next actors are level 1. Returns [] when
    the chain has no further level - the caller then has nobody to hand over to.
    """
    if not approval_request:
        return []
    nxt = int(current_level or 0) + 1
    rows = frappe.get_all(APPROVER,
                          filters={"approval_request": approval_request, "level_no": nxt,
                                   "status": "Pending"},
                          fields=["approver"], limit_page_length=0)
    seen, out = set(), []
    for r in rows:
        if r.approver and r.approver not in seen:
            seen.add(r.approver)
            out.append(r.approver)
    return out


def provider_ids_for(users, environment):
    """(ids, unmapped): provider user ids for `users` that have a VERIFIED mapping.

    Unverified or missing mappings are reported, never silently skipped - handing the
    document to an unverified identity is exactly the failure mode this module prevents.
    """
    # The module is `permissions`; every other file in this package imports it as `perms`.
    # Getting that alias wrong made the whole signing leg die on an ImportError.
    from ecentric_workspace.platform.esign import permissions as perms
    ids, unmapped = [], []
    for u in users or []:
        mapping = perms.verified_mapping(u, environment)
        pid = mapping and (mapping.get("scts_user_id") if isinstance(mapping, dict)
                           else getattr(mapping, "scts_user_id", None))
        if pid:
            ids.append(str(pid))
        else:
            unmapped.append(u)
    return ids, unmapped


#: What the provider calls the transitions we are allowed to drive. "Tu choi" is a rejection
#: and must never be taken by the approve path.
_APPROVE_TYPES = ("approve",)


def discover_transition(adapter, instance_id, provider_user_id):
    """Ask the PROVIDER which transition applies right now, instead of configuring one.

    Captured from the portal 2026-08-28:

        GET /api/Workflow/{instanceId}?userid={userId}
        -> availableTransitions[{transitionId, processAction, signType, isSigned, ...}]

    This replaces the per-stage config, which could not have worked. In one real workflow the
    four "Phe duyet" edges are -9, -10, -11 and -4, and the LAST one wants processAction
    WfFunctionRunSignedA with signType ky-chinh while the others want WfFunctionRunSignedOther
    with ky-tham-gia. One configured value per stage is therefore wrong on at least one step
    of every single document - which is exactly what happened.

    Returns (config, reason). config is None when we must not act.
    """
    if not hasattr(adapter, "available_transitions"):
        return None, "adapter_cannot_discover_transitions"
    try:
        avail = adapter.available_transitions(instance_id, provider_user_id) or []
    except Exception as exc:
        # Ghi CA noi dung loi, khong chi ten loai. Ban dau chi ghi type(exc).__name__ va lan
        # chay that 28/08 tra ve dung mot chu "SctsHttpError" - biet la hong nhung khong biet
        # ma trang thai, khong biet provider noi gi, nen lai phai doan. Dung cai sai da ton hai
        # dem: dung cong cu de nhin roi tu bit mat o dong cuoi.
        from ecentric_workspace.platform.esign.sanitize import safe_error
        return None, "transition_discovery_failed:%s" % safe_error(exc)
    if not avail:
        return None, "no_available_transition"
    picks = [t for t in avail if (t.get("transition_type") or "") in _APPROVE_TYPES]
    if not picks:
        # Never fall back to "the first one": the other edge on this state is "Tu choi".
        return None, "no_approve_transition:%s" % ",".join(
            str(t.get("transition_name") or "?") for t in avail)
    if len(picks) > 1:
        # Two ways forward is a business choice, not something to pick blindly.
        return None, "ambiguous_approve_transition:%s" % ",".join(
            str(t.get("transition_id")) for t in picks)
    t = picks[0]
    if t.get("transition_id") is None or not t.get("process_action"):
        return None, "incomplete_transition:%s" % t.get("transition_id")
    return t, None


#: Nhung ly do nghia la "nha cung cap noi KHONG duoc di" - phai dung lai, khong duoc lay cau
#: hinh cu ra dung thay. Khac han voi "khong hoi duoc" (mang loi, 4xx, adapter cu).
_REFUSALS = ("no_available_transition", "no_approve_transition",
             "ambiguous_approve_transition", "incomplete_transition")


def why_is_refusal(why):
    return bool(why) and any(str(why).startswith(r) for r in _REFUSALS)


def signature_type_matches(required, mapping_type):
    """The transition says which KIND of signature the slot takes ("ky-chinh" /
    "ky-tham-gia"). Sending the wrong kind is how a document walks the whole workflow with
    its main-signature box left empty and nothing reported - observed on the portal test of
    2026-08-28, where four approvals completed and "Ky chinh" still read "Chua co".

    An unstated requirement is not a licence to send anything; it just cannot be checked.
    """
    want = str(required or "").strip().lower()
    if not want:
        return True
    return want == str(mapping_type or "").strip().lower()


def _mapped_signature_type(dsr, environment):
    """Which KIND of signature this leg is about to use. The DSR stores the signature id, not
    its type, so read it back off the verified mapping - the same row the id came from."""
    user = dsr.get("actor_user") or dsr.get("approver")
    if not user:
        return None
    try:
        from ecentric_workspace.platform.esign import permissions as perms
        m = perms.verified_mapping(user, environment) or {}
    except Exception:
        return None
    return m.get("signature_type")


def targeted_handover_enabled():
    """ON by default from 2026-08-28 chieu, sau khi co capture doi chieu duoc.

    Sang cung ngay minh TAT duong nay: mot lan eContract nhan transition (2xx,
    EC-PAYR-2026-00032) roi de chung tu ket - khong dong workflow, khong chu ky, khong con
    nut "Xu ly" cho chinh nguoi duoc chi dinh. Duong pool tho hon thi ky duoc, nen duong
    dung tren giay phai nhuong duong dang chay.

    Chieu 28/08 Hoan chup duoc lenh "Xu ly" cua chinh portal tren dung mot chung tu do ERP
    tao ra, va no THANH CONG:

        POST /api/Workflow/transition   (Content-Length 19169)
        { instanceId, userId, toUsers:[...], transitionId:"-2",
          transitionName:"Trinh ky", processAction:"WfFunctionRunSignedOther",
          signType:"ky-tham-gia", signatureInfo:{id,name,image}, comment:"" }

    Doi chieu tung truong voi cai minh gui: HINH DANG GIONG HET, va cau hinh bac nguoi
    trinh (p088) trung tung chu. Khac biet duy nhat tim duoc la `signatureInfo.name`:
    portal gui ten hien thi "Ky tham gia", minh gui ma "ky-tham-gia" vi khong co ten nao
    khac de gui. Da sua bang cach doc ten thang tu GetSignatures thay vi suy ra.

    Khong khang dinh do la nguyen nhan - khong co bang chung. Nhung mot bien so da bi loai,
    con duong pool thi dang BAO DAM phat cho ca 7 truong bo phan, nen can can da nghieng
    lai. Tat khan cap: `bench set-config ec_esign_targeted_handover 0`.
    """
    v = frappe.conf.get("ec_esign_targeted_handover")
    if v is None or v == "":
        return True
    try:
        return bool(int(v))
    except Exception:
        # Cau hinh sai kieu ("yes", "on") khong duoc am tham tro ve mac dinh - noi ro roi
        # giu duong dang chay.
        return str(v).strip().lower() not in ("0", "false", "no", "off")


def plan_handover(dsr, profile_name, environment, stage=None, adapter=None, instance_id=None):
    """What to send for this leg: {mode, ...}.

    mode == "transition" -> name the next handler explicitly (the governed path).
    mode == "pool"       -> provider decides the recipients; `reason` says why we had to.
    """
    if not targeted_handover_enabled():
        return {"mode": "pool", "reason": "targeted_handover_disabled"}
    cfg = None
    why = None
    discovery_note = None
    if adapter is not None and instance_id:
        cfg, why = discover_transition(adapter, instance_id,
                                       dsr.get("effective_scts_user_id"))
    if cfg is None and why_is_refusal(why):
        # Nha cung cap noi ro KHONG duoc di: dung lai. Khac han voi "khong hoi duoc".
        return {"mode": "pool", "reason": why}
    if cfg is None and why:
        # Khong HOI duoc (mang loi, 4xx, adapter cu) thi van con cau hinh tren ho so lam duong
        # lui. Ro rang la kem hon - id co the sai o mot so cap - nhung van dich danh nguoi ky
        # tiep theo, con hon phat cho ca vai tro. Lan chay 28/08 rot thang ve pool va SCTS gui
        # cho BAY truong bo phan chi vi mot loi HTTP.
        discovery_note = why
    if cfg is not None:
        want = cfg.get("sign_type")
        have = _mapped_signature_type(dsr, environment)
        if cfg.get("requires_signature") and not signature_type_matches(want, have):
            return {"mode": "pool",
                    "reason": "signature_type_mismatch:need=%s have=%s" % (want, have or "?")}
    if cfg is None:
        cfg = resolve_transition_config(profile_name, dsr.get("action") or "Sign", stage=stage)
    if not cfg:
        return {"mode": "pool",
                "reason": "no_transition_config:%s%s" % (
                    stage or "default",
                    (" after " + discovery_note) if discovery_note else "")}

    ar = dsr.get("approval_request")
    level = dsr.get("request_level_no")
    if level is None:
        level = 0 if (dsr.get("actor_type") == "Requester") else _level_of(dsr)
    users = next_level_approvers(ar, level)
    if not users:
        if cfg.get("terminal"):
            # Final step: nobody comes after, and the config says so explicitly.
            return {"mode": "transition", "to_users": [], "config": cfg}
        return {"mode": "pool", "reason": "no_next_level_approver"}

    ids, unmapped = provider_ids_for(users, environment)
    if not ids:
        return {"mode": "pool", "reason": "next_handler_unmapped:%s" % ",".join(unmapped)}
    out = {"mode": "transition", "to_users": ids, "config": cfg,
           "unmapped": unmapped, "erp_users": users}
    if discovery_note:
        # Dung duong lui thi phai NOI RA, khong de no trong nhu duong chinh dang chay tot.
        out["fallback_config"] = True
        out["discovery_error"] = discovery_note
    return out


def _level_of(dsr):
    rl = dsr.get("request_level")
    if not rl:
        return 0
    return int(frappe.db.get_value(LEVEL, rl, "level_no") or 0)
