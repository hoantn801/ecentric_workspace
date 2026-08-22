# Copyright (c) 2026, eCentric and contributors
"""Action Center: canonical route resolvers.

Single source of truth for converting (reference_type, reference_name) into:
  - source_key / source_label / action_label   (UI metadata)
  - action_url                                  (the link the user clicks)

The previous homepage widget hard-coded `/approval?id=...&type=...` for
EVERY ToDo, which broke Weekly Team Update and Task items. Centralise the
mapping here so the rule lives in one place and is reused by:
  - ecentric_workspace.action_center.api.get_action_items  (homepage feed)
  - ecentric_workspace.api._notify_approver                 (email link)

All path/query params are URL-encoded via urllib.parse.quote.
"""

from urllib.parse import quote as _q

import frappe


WTU = "Weekly Team Update"
TASK = "Task"

#: Approval Center hub -- the portal home for engine-governed business forms
#: whose per-record route cannot be resolved.
APPROVAL_HUB_ROUTE = "/approvals"

#: reference_type -> PORTAL destination for sources that own a portal page but
#: have no per-record deep link. Without this the resolver fell through to the
#: Desk fallback (/app/<doctype>/<name>), a permission-denied dead end for
#: portal users -- the reminder pointed at a page they cannot open.
#: Every DocType this app files ToDos against MUST resolve to a portal route;
#: action_center/tests/test_no_desk_urls.py scans the repo and enforces it.
PORTAL_FALLBACK = {
    "EC Alert": "/alerts",          # alert case handling lives on the dashboard
    "Brand": "/alerts",             # per-brand setup ToDo (missing mapping/price)
    "EC Order Retry": "/alerts",    # retry queue
    # hrms DocType, not ours: hrms files the ToDo when an employee submits the
    # request, so NOTHING in this repo mentions it and the source scan in
    # tests/test_no_desk_urls.py could never have found it. Reported from
    # production UAT 2026-08-21 (HR-ARQ-26-08-00010..12 opened Desk).
    "Attendance Request": "/ec-hr/attendance",
}

#: DocTypes owned by OTHER installed apps (hrms, erpnext) that file ToDos at our
#: users. They are listed by hand because the repo scan is structurally blind to
#: them -- their producer lives outside this codebase. Anything added here must
#: resolve to a portal route; the gate enforces that.
EXTERNAL_TODO_DOCTYPES = ("Attendance Request",)

# Approval-style DocTypes (route /approval?id=&type=).
APPROVAL_DOCTYPES = frozenset({
    "GBS Purchase Order",
    "GBS Sales Order",
    "MSO Request",
    "SO Request",
    "PO Request",
    "REC Request",
    "Vendor Code Request",
    "Sales Order",
})

#: Leave Application is DELIBERATELY not in APPROVAL_DOCTYPES above. That set
#: means "goes to the legacy /approval inbox", and /approval's TYPE_MAP only
#: knows mso / so / po / gbs_so / gbs_po -- it silently ignores an unknown type
#: and renders the generic 771-row ticket list, so the approver lands somewhere
#: unrelated with no error to tell them why. Leave lives on its own HR portal
#: page instead. Removing it from the set is not enough on its own either: the
#: unknown-DocType arm falls back to a Desk URL, and ~44% of accounts are
#: Website Users who cannot open Desk at all. Hence the explicit arm in
#: resolve_item().
LEAVE_APPLICATION = "Leave Application"

#: Where a pending leave is actually decided: the HR portal page, "Của nhóm" tab.
LEAVE_APPROVAL_URL = "/ec-hr/leave"


def build_approval_url(doctype, name):
    """Canonical /approval URL.

    Shared by Action Center feed and ecentric_workspace.api._notify_approver
    so the email and the homepage card always point at the same URL.
    """
    t = (doctype or "").lower().replace(" ", "_")
    return "/approval?id=" + _q(str(name or ""), safe="") + "&type=" + _q(t, safe="")


# ---- approval-engine link contract (Phase 1b.3) ----------------------------
#: The Approval Engine's request DocType, and the canonical Link field every
#: governed business form carries back to its engine request.
APPROVAL_REQUEST_DT = "EC Approval Request"
APPROVAL_LINK_FIELD = "approval_request"

#: SAFETY GATE (Phase 1b.3 generalized-scope review). ~31 DocTypes carry the
#: engine link, but the Action Center feed gates VISIBILITY through the ONE
#: canonical helper engine.permissions.can_view_request. A DocType may be
#: normalized to the approval route ONLY if its own form `_can_view` is >= that
#: helper (the feed must NEVER grant a broader view than the business form).
#:
#: Parity audit of all 26 form `_can_view` (2026-07-28):
#:   FULFILLER-pattern  (SM|requester|approver|fulfillment_owner|eligible_fulfiller)
#:     -> form >= canonical (form also scans Draft processes); feed <= form. SAFE.
#:     = AI Topup, Asset Request, Data Request, Document Request, Resignation,
#:       System Request.
#:   NO-FULFILLER pattern (SM|requester|approver only) -- 15 forms -- and
#:   SNAPSHOT pattern (SM|requester|snapshot-approver) -- 5 forms:
#:     canonical is BROADER (adds fulfillment_owner + eligible_fulfiller) ->
#:     EXCLUDED until their permission contract is aligned (delegate to / adopt
#:     the fulfiller pattern). Excluded DocTypes fall back to the generic
#:     referenced document (their pre-1b.3 behavior; no regression).
#: Adding a DocType here REQUIRES proving form >= can_view_request.
APPROVAL_NORMALIZE_ALLOWLIST = frozenset({
    "EC AI Topup Request",
    "EC Asset Request",
    "EC Data Request",
    "EC Document Request",
    "EC Resignation Request",
    "EC System Request",
})

#: cache: (doctype, fieldname) -> bool. DocType meta is static per process, so a
#: single get_meta() per DocType is enough (never one per ToDo row).
_META_FIELD_CACHE = {}


def _link_field(doctype, fieldname):
    dt = (doctype or "").strip()
    if not dt or not fieldname:
        return None
    ck = (dt, fieldname)
    if ck in _META_FIELD_CACHE:
        return _META_FIELD_CACHE[ck]
    f = None
    try:
        f = frappe.get_meta(dt).get_field(fieldname)
    except Exception:
        f = None
    _META_FIELD_CACHE[ck] = f
    return f


#: Fieldtypes that carry no queryable DB column. A (mis)configured title_field
#: pointing at one must never end up in a SQL SELECT.
_NO_COLUMN_FIELDTYPES = frozenset({
    "Section Break", "Column Break", "Tab Break", "Fold",
    "HTML", "Heading", "Button", "Table", "Table MultiSelect",
})

#: Attribute name for the request-scoped title-field cache on frappe.local.
_TITLE_FIELD_LOCAL_ATTR = "_ec_ac_title_fields"


def _title_field_cache():
    """Request-scoped cache (doctype -> validated title field or None).

    Lives on `frappe.local`, which the framework resets per request, so the
    title field is deduplicated only WITHIN a single feed request and is never
    retained across requests or for the process lifetime. `frappe.get_meta()`
    already provides framework-level meta cache + invalidation; this cache only
    avoids re-running get_title_field()/has_field() for the same DocType across
    the many rows of one feed.

    Degrades gracefully: outside a request context (background job started
    before request-local init, bench execute, tests) `frappe.local` may be
    absent or read-only. Caching is an optimisation, never a requirement, so we
    fall back to a throwaway dict -- raising here used to abort resolve_title
    and silently DROP every approval item from the feed."""
    local = getattr(frappe, "local", None)
    if local is None:
        return {}
    cache = getattr(local, _TITLE_FIELD_LOCAL_ATTR, None)
    if cache is None:
        cache = {}
        try:
            setattr(local, _TITLE_FIELD_LOCAL_ATTR, cache)
        except Exception:
            pass          # un-settable local -> per-call dict, still correct
    return cache


def _title_field(doctype):
    """The DocType's configured title field, validated to be a real, queryable
    column. Returns None when the DocType has no usable title field, in which
    case the caller falls back to `name`. Metadata-driven: never assumes a
    physical `title` column exists. Cached per DocType for one feed request."""
    dt = (doctype or "").strip()
    if not dt:
        return None
    cache = _title_field_cache()
    if dt in cache:
        return cache[dt]
    tf = None
    try:
        meta = frappe.get_meta(dt)
        cand = meta.get_title_field()            # configured title_field, or "name"
        if cand and cand != "name" and meta.has_field(cand):
            df = meta.get_field(cand)
            if df and not df.get("is_virtual") and df.fieldtype not in _NO_COLUMN_FIELDTYPES:
                tf = cand
    except Exception:
        tf = None
    cache[dt] = tf
    return tf


def resolve_title(doctype, name):
    """Human title for (doctype, name), resolved via DocType metadata:
      configured title_field (validated to physically exist) -> else `name`.
    Only ever SELECTs columns known to exist, so a DocType without a `title`
    column can never trigger MySQL 1054 (Unknown column). Falls back to the
    record `name` when the title field is empty or the record is missing."""
    dt = (doctype or "").strip()
    nm = (name or "").strip()
    if not dt or not nm:
        return nm
    tf = _title_field(dt)
    fields = ["name"] + ([tf] if tf else [])
    row = frappe.db.get_value(dt, nm, fields, as_dict=True) or {}
    return (row.get(tf) if tf else None) or row.get("name") or nm


def has_engine_approval_link(doctype):
    """True if `doctype` is an approval-governed business form: it declares a
    Link field `approval_request` whose options is `EC Approval Request`.

    METADATA-DRIVEN via Frappe get_meta -- never a hardcoded list of the ~28
    approval business DocTypes. Cached per DocType."""
    f = _link_field(doctype, APPROVAL_LINK_FIELD)
    return bool(f and getattr(f, "fieldtype", None) == "Link"
                and (getattr(f, "options", None) or "").strip() == APPROVAL_REQUEST_DT)


def has_field(doctype, fieldname):
    """True if `doctype` declares `fieldname` (metadata; cached)."""
    return _link_field(doctype, fieldname) is not None


def build_approval_center_url(route, business_name):
    """Canonical Approval Center form deep-link: ``<route>?id=<business_name>``.

    EC approval-center forms (AI Topup, purchase/SO-PO, asset, HR, ...) each live
    at their own governed route -- stored, leading-slash-validated, on
    ``EC Approval Type.route`` (e.g. ``/approvals/ai-topup``) -- and read
    ``?id=<business doc name>``. Canonical counterpart to
    :func:`build_approval_url` (the legacy ``/approval`` inbox for
    MSO/SO/PO/REC/GBS). Returns '' when the route is missing so the caller falls
    back instead of emitting a dead link."""
    r = (route or "").strip()
    if not r:
        return ""
    if not r.startswith("/"):
        r = "/" + r
    return r + "?id=" + _q(str(business_name or ""), safe="")


def apply_approval_normalization(item, request_name, route, business_name,
                                 title=None, stage="approval"):
    """Normalize `item` as a governed approval-FAMILY action with the canonical
    Approval Center URL. ONE place the source strings + URL are applied, for BOTH
    direct EC Approval Request references and linked business documents, and for
    BOTH lifecycle stages (Phase 1b.3.1):
      stage="approval"    -> pending approval decision ("PHÊ DUYỆT").
      stage="fulfillment" -> approval done, fulfillment still open ("THỰC HIỆN").
    Both keep source_type=approval (source_family) for backward compatibility;
    the additive `action_stage` discriminates them and drives the separate
    source_counts (approval vs fulfillment). Preserves the business reference
    fields already on `item` (reference_type/reference_name) for display/audit."""
    src = _FULFILLMENT_SRC if stage == "fulfillment" else _APPROVAL_SRC
    item["source_key"] = src["source_key"]
    item["source_type"] = src["source_key"]       # "approval" (source family) -- backward compat
    item["source_family"] = "approval"
    item["action_stage"] = stage                  # "approval" | "fulfillment"
    item["source_label"] = src["source_label"]
    item["action_label"] = src["action_label"]
    item["action_url"] = build_approval_center_url(route, business_name)
    item["source_name"] = request_name            # linked EC Approval Request
    item["approval_request"] = request_name        # explicit, for audit
    if title:
        item["title"] = title
    return item


def build_wtu_url(week_label):
    """Weekly Update form deep-link. UI reads URLSearchParams.get('week')."""
    return "/weekly-update?week=" + _q(str(week_label or ""), safe="")


def build_task_url(name):
    """Frappe Desk Task form ``/app/task/<name>``.

    Kept for the notification subsystem (``notification_center.resolvers`` /
    ``pm.api.notifications``), which delegates here for its email/card links.
    NOTE: requires Desk access. The Action Center feed uses
    :func:`build_pm_task_url` instead (portal SPA, permission-safe).
    """
    return "/app/task/" + _q(str(name or ""), safe="")


def build_pm_task_url(name):
    """Canonical PM SPA task-detail deep-link: ``/pm#task/<name>``.

    This is the Action Center's canonical PM Task destination. ``/pm`` is the
    portal SPA -- permission-safe for any internal website user, unlike the Desk
    form ``/app/task/<name>`` (which needs Desk access and is a permission-denied
    dead path for non-System users). The SPA router (``pm_app.html``
    ``pmApplyRoute``) recognises ``#task/<name>`` and runs
    ``go('work'); openTask(decodeURIComponent(name))`` -- opening the task detail
    with no document reload. The name occupies ONE hash segment (slash-encoded to
    %2F) so the router's ``hash.split('/')`` keeps it intact and
    ``decodeURIComponent`` restores it. Built server-side so the frontend never
    guesses a route from source_type.
    """
    return "/pm#task/" + _q(str(name or ""), safe="")


def build_desk_fallback_url(doctype, name):
    """Frappe Desk fallback for unknown DocTypes.

    DocType slug: lowercase, spaces -> dashes (also underscores -> dashes to
    match Frappe's website route slugging).
    """
    slug = (doctype or "").lower().replace(" ", "-").replace("_", "-")
    return "/app/" + _q(slug, safe="") + "/" + _q(str(name or ""), safe="")


_WTU_SRC = {
    "source_key": "weekly_report",
    "source_label": "BÁO CÁO TUẦN",
    "action_label": "Điền báo cáo",
}
_TASK_SRC = {
    "source_key": "task",
    "source_label": "CÔNG VIỆC",
    "action_label": "Xem công việc",
}
_APPROVAL_SRC = {
    "source_key": "approval",
    "source_label": "PHÊ DUYỆT",
    "action_label": "Phê duyệt",
}
#: fulfillment-stage display (Phase 1b.3.1). Same source_family (approval) + the
#: same canonical business-form URL, but a distinct label + action_stage so the
#: UI shows "thực hiện" (fulfil) rather than "phê duyệt" (approve).
_FULFILLMENT_SRC = {
    "source_key": "approval",
    "source_label": "THỰC HIỆN",
    "action_label": "Thực hiện",
}
_GENERIC_SRC = {
    "source_key": "generic",
    "source_label": "VIỆC",
    "action_label": "Mở",
}


#: how long one unmapped-DocType report is suppressed (seconds)
_UNMAPPED_TTL = 86400


def _note_unmapped_doctype(doctype):
    """Report ONCE A DAY that a DocType reached the Desk fallback.

    Why this exists: every producer inside this repo is caught by the source
    scan in tests/test_no_desk_urls.py, but ToDos also arrive from OTHER
    installed apps -- hrms filed the Attendance Request ToDos that reached
    production on 2026-08-21, and no amount of grepping this codebase could
    have found them. Source scanning cannot see another app; production can.

    Records the DocType NAME ONLY -- never the record name, the user or any
    field -- so this stays safe to read and cannot leak business data. Failure
    is swallowed: an observability aid must never break the feed it observes.
    """
    dt = (doctype or "").strip()
    if not dt:
        return
    try:
        cache = frappe.cache()
        key = "ec_ac_unmapped_dt:" + dt
        if cache.get_value(key):
            return
        cache.set_value(key, 1, expires_in_sec=_UNMAPPED_TTL)
        frappe.log_error(
            message=(
                "Action Center: ToDo reference_type %r has no portal route, so "
                "the reminder points at Frappe Desk (/app/...), which portal "
                "users cannot open.\n\n"
                "Fix: add %r to PORTAL_FALLBACK in "
                "ecentric_workspace/action_center/resolvers.py (and to "
                "EXTERNAL_TODO_DOCTYPES if another app owns it), then extend "
                "action_center/tests/test_no_desk_urls.py." % (dt, dt)),
            title="Action Center: unmapped ToDo DocType")
    except Exception:
        pass


def resolve_item(todo_row):
    """Build the canonical Action Center item from a tabToDo row.

    todo_row keys (from gbs_user_pending_todos SQL or equivalent):
      name, description, reference_type, reference_name, priority, modified
    Optional: date (ToDo.date / due date)
    """
    ref_type = (todo_row.get("reference_type") or "").strip()
    ref_name = (todo_row.get("reference_name") or "").strip()
    description = todo_row.get("description") or ""
    todo_name = todo_row.get("name") or ""
    priority = todo_row.get("priority") or "Medium"
    modified = todo_row.get("modified")
    due = todo_row.get("date") or todo_row.get("due_at") or ""

    title = ""
    subtitle = ""
    action_url = ""
    src = _GENERIC_SRC

    if ref_type == WTU and ref_name:
        src = _WTU_SRC
        wl = frappe.db.get_value(WTU, ref_name, "week_label") or ""
        title = ("Báo cáo tuần " + wl) if wl else "Báo cáo tuần"
        subtitle = ref_name
        action_url = build_wtu_url(wl)
    elif ref_type == TASK and ref_name:
        src = _TASK_SRC
        title = frappe.db.get_value(TASK, ref_name, "subject") or ref_name
        subtitle = ref_name
        # Canonical Action Center PM destination = the portal SPA task detail
        # (permission-safe), NOT the Desk form used by notifications.
        action_url = build_pm_task_url(ref_name)
    elif ref_type == LEAVE_APPLICATION and ref_name:
        src = _APPROVAL_SRC
        title = resolve_title(ref_type, ref_name)
        subtitle = ref_type + " · " + ref_name
        action_url = LEAVE_APPROVAL_URL
    elif ref_type in APPROVAL_DOCTYPES and ref_name:
        src = _APPROVAL_SRC
        title = resolve_title(ref_type, ref_name)
        subtitle = ref_type + " · " + ref_name
        action_url = build_approval_url(ref_type, ref_name)
    elif ref_type and ref_name and has_engine_approval_link(ref_type):
        # Engine-governed business document. Its canonical per-record URL is
        # applied later by the feed (apply_approval_normalization). If that
        # lookup is unavailable -- the type has no route configured yet, or the
        # engine link is missing -- send the user to the Approval Center HUB
        # instead of Desk: these forms exist precisely because portal users
        # cannot open /app.
        #
        # ONLY the URL changes. source_key/source_type stay GENERIC on purpose:
        # marking them "approval" here pushed them into the legacy approval
        # branch of _classified_feed, whose terminal check then DROPPED the item
        # from the feed entirely.
        src = _GENERIC_SRC
        title = ref_name
        subtitle = ref_type
        action_url = APPROVAL_HUB_ROUTE
    elif ref_type in PORTAL_FALLBACK and ref_name:
        # Governed portal home for sources that have a page but no per-record
        # deep link (Alert Center). Sending these to Desk produced a
        # permission-denied dead end for portal users.
        src = _GENERIC_SRC
        title = ref_name
        subtitle = ref_type
        action_url = PORTAL_FALLBACK[ref_type]
    elif ref_type and ref_name:
        # Unknown DocType with a reference -> Desk fallback (PO decision
        # 2026-08-21: keep the link rather than hide the item, so nothing is
        # silently dropped from someone's work list).
        #
        # The accompanying trade-off is that a portal user without Desk access
        # still hits a wall, so the unmapped type is REPORTED instead of passing
        # unnoticed -- see _note_unmapped_doctype.
        src = _GENERIC_SRC
        title = ref_name
        subtitle = ref_type
        action_url = build_desk_fallback_url(ref_type, ref_name)
        _note_unmapped_doctype(ref_type)
    elif "[XNGIO]" in (description or ""):
        # PM time-blocking "confirm your hours" reminder -> the week calendar (portal),
        # NOT the Desk ToDo form. Tag is set by pm.api.schedule._ensure_nudge_todo.
        src = _GENERIC_SRC
        title = "Xác nhận giờ đã làm"
        subtitle = ""
        action_url = "/pm#schedule"
    else:
        # Bare ToDo with no reference -> link to the ToDo itself in Desk.
        src = _GENERIC_SRC
        title = (description[:80] or todo_name) if description else todo_name
        subtitle = ""
        action_url = "/app/todo/" + _q(str(todo_name or ""), safe="")

    return {
        "todo_name": todo_name,
        "reference_type": ref_type,
        "reference_name": ref_name,
        "source_key": src["source_key"],
        "source_label": src["source_label"],
        "action_label": src["action_label"],
        "title": title,
        "subtitle": subtitle,
        "action_url": action_url,
        "priority": priority,
        "due_at": str(due) if due else "",
        "modified": str(modified) if modified else "",
        # ---- v1 additive canonical fields (2C.2 shared provider) ----------
        # Aliases + derived state; NOTHING above changed or removed, so the
        # existing homepage widget / any consumer of v0 keeps working.
        "source_type": src["source_key"],
        "source_id": (ref_type + "/" + ref_name) if (ref_type and ref_name) else todo_name,
        "status": todo_row.get("status") or "Open",
        # resolution is DERIVED: an item exists only while its governed source
        # keeps the ToDo open (engine/WTU/PM close it); never stored here.
        "resolution_state": "open",
        # bucket is filled by the API layer (needs "today"); default here so
        # the key always exists for consumers.
        "bucket": "undated",
    }


# ---- v1 pure helpers (no frappe import: unit-testable) -----------------------

BUCKETS = ("overdue", "today", "upcoming", "undated")


def bucket_for(due_at, today):
    """Classify a due datetime/date/ISO-string against `today` (a date).

    Contract (2C.2): a missing/unparseable due date is EXPLICITLY "undated"
    (hiển thị "Không hạn") -- never infer or fake a date.
    """
    if not due_at:
        return "undated"
    s = str(due_at).strip()
    if not s:
        return "undated"
    d = _parse_date(s)
    if d is None:
        return "undated"
    if d < today:
        return "overdue"
    if d == today:
        return "today"
    return "upcoming"


def _parse_date(s):
    """date part of 'YYYY-MM-DD[ HH:MM:SS]' -> datetime.date, else None."""
    import datetime
    part = s[:10]
    try:
        return datetime.date(int(part[0:4]), int(part[5:7]), int(part[8:10]))
    except (ValueError, IndexError):
        return None
