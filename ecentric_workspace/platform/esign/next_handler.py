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


def plan_handover(dsr, profile_name, environment, stage=None):
    """What to send for this leg: {mode, ...}.

    mode == "transition" -> name the next handler explicitly (the governed path).
    mode == "pool"       -> provider decides the recipients; `reason` says why we had to.
    """
    cfg = resolve_transition_config(profile_name, dsr.get("action") or "Sign", stage=stage)
    if not cfg:
        return {"mode": "pool", "reason": "no_transition_config:%s" % (stage or "default")}

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
    return {"mode": "transition", "to_users": ids, "config": cfg,
            "unmapped": unmapped, "erp_users": users}


def _level_of(dsr):
    rl = dsr.get("request_level")
    if not rl:
        return 0
    return int(frappe.db.get_value(LEVEL, rl, "level_no") or 0)
