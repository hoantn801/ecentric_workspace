# Copyright (c) 2026, eCentric and contributors
"""Shared Action feed + classification service (Phase 1a).

THE single internal service behind every Action Center consumer
(get_action_items today; get_reminder_summary + the full page later). No
consumer re-implements counting, classification, due derivation, terminal
filtering, ordering or pagination -- they all call build_feed().

Invariants:
  - tabToDo is the ONLY action index (no separate Action DocType/table).
  - Every field is DERIVED from governed source records each call.
  - Session scope: the caller passes the resolved user; the whitelisted API
    layer forbids a client-supplied user.

Classification policy (PO-locked 2026-07-24):
    resolved/terminal source          -> excluded
    due date before today             -> overdue
    due date == today                 -> act_now
    explicit ACTIVE source state       -> act_now   (source-specific)
    future due date                   -> upcoming
    undated and not explicitly active -> undated

Deterministic order: bucket priority, due_at asc (undated last), source
priority, stable creation/name tie-break. NEVER by modified.
"""
import base64
import json

import frappe

from ecentric_workspace.action_center.resolvers import resolve_item, bucket_for

WTU = "Weekly Team Update"
TASK = "Task"
EC_REQUEST = "EC Approval Request"
EC_LEVEL = "EC Approval Request Level"
EC_TYPE = "EC Approval Type"

FEED_BUCKETS = ("overdue", "act_now", "upcoming", "undated")
_BUCKET_RANK = {b: i for i, b in enumerate(FEED_BUCKETS)}
_SOURCE_PRIORITY = {"approval": 0, "task": 1, "weekly_report": 2, "generic": 3}
#: item source_type -> the canonical source_counts key exposed to consumers.
SOURCE_COUNT_KEY = {"approval": "approval", "task": "pm",
                    "weekly_report": "weekly_update", "generic": "generic_todo"}
#: Phase 1b.3.1: `fulfillment` is a SEPARATE count (approval-family, but NOT a
#: pending approval). Additive -- existing consumers that read source_counts.approval
#: keep working; the approval count no longer double-counts fulfillment actions.
SOURCE_COUNT_KEYS = ("approval", "pm", "weekly_update", "generic_todo", "fulfillment")
_APPROVAL_TERMINAL = frozenset({"Approved", "Rejected", "Cancelled"})
#: fulfillment_status values that keep a governed fulfillment action OPEN. Terminal
#: fulfillment = {"Completed", "Cancelled"}; "Not Started" = still in the approval
#: stage. Active = the action is live and belongs in the feed.
_FULFILLMENT_ACTIVE = frozenset({"Assigned", "In Progress"})
_WTU_TERMINAL = frozenset({"Submitted", "Reviewed"})

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
_SCAN_CAP = 500
#: default per-bucket preview size for the header reminder drawer.
PREVIEW_N = 4


# ---- pure helpers (no frappe): classification + ordering + cursor ----------
def classify(due_at, today, active, terminal):
    """Bucket for one item, or None if it must be EXCLUDED (resolved/terminal)."""
    if terminal:
        return None
    b = bucket_for(due_at, today)
    if b == "overdue":
        return "overdue"
    if b == "today":
        return "act_now"
    if b == "upcoming":
        return "upcoming"
    return "act_now" if active else "undated"


def _sort_key(item):
    due = item.get("due_at") or ""
    return (
        _BUCKET_RANK.get(item.get("bucket"), 99),
        due if due else "9999-99-99 99:99:99",
        _SOURCE_PRIORITY.get(item.get("source_type"), 9),
        str(item.get("_creation") or ""),
        str(item.get("todo_name") or ""),
    )


def order_items(items):
    return sorted(items, key=_sort_key)


def encode_cursor(offset):
    return base64.urlsafe_b64encode(json.dumps({"o": int(offset)}).encode()).decode()


def decode_cursor(cursor):
    if not cursor:
        return 0
    try:
        o = int(json.loads(base64.urlsafe_b64decode(cursor.encode()).decode()).get("o", 0))
        return o if o >= 0 else 0
    except Exception:
        return 0


# ---- governed source lookups (batched; only the user's own queued docs) ----
def _approval_state(names):
    out = {}
    if not names:
        return out
    reqs = frappe.get_all(
        EC_REQUEST, filters={"reference_name": ["in", list(names)]},
        fields=["name", "reference_name", "approval_status"],
        ignore_permissions=True) or []
    by_ref = {}
    for r in reqs:
        by_ref.setdefault(r["reference_name"], []).append(r)
    for ref in names:
        rows = by_ref.get(ref) or []
        active_req = [r for r in rows if r["approval_status"] not in _APPROVAL_TERMINAL]
        if not active_req:
            out[ref] = (True, False, "")
            continue
        req = active_req[0]
        lv = frappe.get_all(
            EC_LEVEL,
            filters={"approval_request": req["name"], "level_status": "In Progress"},
            fields=["due_at"], limit=1, ignore_permissions=True) or []
        due = str(lv[0]["due_at"]) if (lv and lv[0].get("due_at")) else ""
        out[ref] = (False, bool(lv), due)
    return out


def _task_state(names):
    out = {}
    if not names:
        return out
    from ecentric_workspace.pm import permissions as pmperm
    rows = frappe.get_all(
        TASK, filters={"name": ["in", list(names)]},
        fields=["name", "workflow_state", "status", "exp_end_date"],
        ignore_permissions=True) or []
    seen = set()
    for t in rows:
        seen.add(t["name"])
        terminal = pmperm.is_task_terminal(t)
        active = (t.get("workflow_state") == "In Progress")
        due = str(t.get("exp_end_date")) if t.get("exp_end_date") else ""
        out[t["name"]] = (terminal, active, due)
    for ref in names:
        if ref not in seen:
            out[ref] = (True, False, "")
    return out


def _wtu_state(names):
    out = {}
    if not names:
        return out
    rows = frappe.get_all(
        WTU, filters={"name": ["in", list(names)]},
        fields=["name", "status"], ignore_permissions=True) or []
    st = {r["name"]: r.get("status") for r in rows}
    for ref in names:
        s = st.get(ref)
        out[ref] = (s in _WTU_TERMINAL if s is not None else True, False, "")
    return out


# ---- approval-engine link normalization (Phase 1b.3) -----------------------
def _engine_link_state(rows, user):
    """Metadata-driven approval normalization for engine-governed business
    documents AND direct EC Approval Request references.

    Returns a map key=(reference_type, reference_name) -> dict:
      found     linked EC Approval Request resolved (else generic fallback)
      terminal  request in a terminal approval_status (-> excluded)
      active    current level is In Progress (actionable)
      due       current In-Progress level SLA due_at (or '')  -> drives bucket
      route     EC Approval Type.route for the canonical Approval Center URL
      request   linked EC Approval Request name
      biz_name  business doc name used for `?id=`
      visible   user is requester / a pending approver / the fulfiller

    Chain: business doc --approval_request--> EC Approval Request
    --approval_type--> EC Approval Type.route. Detection is Frappe-meta driven
    (resolvers.has_engine_approval_link), never a hardcoded DocType list.
    Every lookup is BATCHED (one get_all per DocType / engine table); bounded by
    len(rows) (<= _SCAN_CAP)."""
    from ecentric_workspace.action_center import resolvers as R
    from ecentric_workspace.approval_center.engine import permissions as acperm

    biz_by_dt = {}                     # engine-linked business DocType -> {names}
    req_of = {}                        # (rt,rn) -> linked request name
    for r in rows:
        rt = (r.get("reference_type") or "").strip()
        rn = (r.get("reference_name") or "").strip()
        if not rt or not rn:
            continue
        if rt == R.APPROVAL_REQUEST_DT:
            req_of[(rt, rn)] = rn                        # direct; gated by reference_doctype below
        elif R.has_engine_approval_link(rt) and rt in R.APPROVAL_NORMALIZE_ALLOWLIST:
            # metadata-detected AND permission-aligned (form >= canonical helper).
            biz_by_dt.setdefault(rt, set()).add(rn)
        # metadata-detected but NOT allow-listed -> skip: the feed must not use a
        # broader permission than the form; item falls back to generic.

    # linked business doc -> request name (+ governed fulfillment fields), batched.
    ful_by_biz = {}                    # (biz_dt,biz_name) -> {owner,status,due}
    for dt, names in biz_by_dt.items():
        extra = [f for f in ("fulfillment_owner", "fulfillment_status", "fulfillment_due_at")
                 if R.has_field(dt, f)]
        docs = frappe.get_all(dt, filters={"name": ["in", list(names)]},
                              fields=["name", "approval_request"] + extra,
                              ignore_permissions=True) or []
        for d in docs:
            req_of[(dt, d["name"])] = (d.get("approval_request") or "").strip()
            ful_by_biz[(dt, d["name"])] = _ful_fields(d)

    out = {}
    req_names = sorted({v for v in req_of.values() if v})
    if not req_names:
        for k in req_of:
            out[k] = {"found": False}
        return out

    reqs = frappe.get_all(
        EC_REQUEST, filters={"name": ["in", req_names]},
        fields=["name", "approval_status", "current_level", "approval_type",
                "requested_by", "reference_doctype", "reference_name"],
        ignore_permissions=True) or []
    req_index = {r["name"]: r for r in reqs}

    type_names = sorted({(r.get("approval_type") or "") for r in reqs if r.get("approval_type")})
    type_route = {}
    if type_names:
        for t in frappe.get_all(EC_TYPE, filters={"name": ["in", type_names]},
                                fields=["name", "route"], ignore_permissions=True) or []:
            type_route[t["name"]] = (t.get("route") or "").strip()

    level_map = {}                     # request -> {level_no: (level_status, due_at)}
    for lv in frappe.get_all(EC_LEVEL, filters={"approval_request": ["in", req_names]},
                             fields=["approval_request", "level_no", "level_status", "due_at"],
                             ignore_permissions=True) or []:
        level_map.setdefault(lv["approval_request"], {})[lv.get("level_no")] = (
            lv.get("level_status") or "", str(lv.get("due_at")) if lv.get("due_at") else "")

    # Resolve the business document per key. For direct EC Approval Request refs
    # this REVERSE-resolves via reference_doctype/reference_name BEFORE any stage
    # selection; a failed reverse resolution (missing / not allow-listed) yields a
    # generic fallback -- never an inferred fulfillment or a reused approval SLA.
    biz_of_key = {}                    # key -> (biz_dt, biz_name) or None
    direct_need = {}                   # dt -> {names} needing a reverse fulfillment fetch
    for key, reqname in req_of.items():
        req = req_index.get(reqname) if reqname else None
        if not req:
            biz_of_key[key] = None
            continue
        if key[0] == R.APPROVAL_REQUEST_DT:
            bdt = (req.get("reference_doctype") or "").strip()
            bnm = (req.get("reference_name") or "").strip()
            if not bdt or not bnm or bdt not in R.APPROVAL_NORMALIZE_ALLOWLIST:
                biz_of_key[key] = None           # reverse resolution failed / not aligned
                continue
            biz_of_key[key] = (bdt, bnm)
            if (bdt, bnm) not in ful_by_biz:
                direct_need.setdefault(bdt, set()).add(bnm)
        else:
            biz_of_key[key] = (key[0], key[1])

    for dt, names in direct_need.items():
        extra = [f for f in ("fulfillment_owner", "fulfillment_status", "fulfillment_due_at")
                 if R.has_field(dt, f)]
        if not extra:
            continue
        for d in frappe.get_all(dt, filters={"name": ["in", list(names)]},
                                fields=["name"] + extra, ignore_permissions=True) or []:
            ful_by_biz[(dt, d["name"])] = _ful_fields(d)

    for key, reqname in req_of.items():
        req = req_index.get(reqname) if reqname else None
        if not req:
            out[key] = {"found": False}          # missing/invalid link -> fallback
            continue
        biz_pair = biz_of_key.get(key)
        if biz_pair is None:
            out[key] = {"found": False}          # reverse resolution failed -> generic
            continue
        biz_dt, biz = biz_pair
        appr_status = req.get("approval_status")
        route = type_route.get(req.get("approval_type"), "")
        atype = req.get("approval_type")
        ful = ful_by_biz.get((biz_dt, biz), {})
        ful_status = ful.get("status", "")

        # ---- STAGE selection (Phase 1b.3.1, tightened gate) ----------------
        # Approval-decision terminal != overall-action terminal, BUT fulfillment
        # is permitted ONLY for an APPROVED request whose governed fulfillment is
        # active AND that has an OPEN fulfillment ToDo for THIS user. Rejected /
        # Cancelled requests can NEVER enter fulfillment even with stale
        # Assigned/In Progress fields; a terminal/missing fulfillment status or a
        # missing Open ToDo excludes the item (both sides must agree).
        # Resolve the governed Open fulfillment ToDo ONCE (for Approved + active
        # candidates) -- it gates the stage AND supplies the due-fallback date.
        ftodo = (_open_fulfillment_todo(biz_dt, biz, user)
                 if (appr_status == "Approved" and ful_status in _FULFILLMENT_ACTIVE)
                 else None)
        if appr_status not in _APPROVAL_TERMINAL:
            # APPROVAL stage: due from the CURRENT actionable level SLA only.
            cur = req.get("current_level") or 0
            ls, lvl_due = level_map.get(reqname, {}).get(cur, ("", ""))
            visible = acperm.can_view_request(
                reqname, user, business_doctype=biz_dt,
                requested_by=req.get("requested_by"),
                fulfillment_owner=ful.get("owner", ""), approval_type=atype)
            out[key] = {"found": True, "stage": "approval", "terminal": False,
                        "active": (ls == "In Progress"),
                        "due": lvl_due if ls == "In Progress" else "",
                        "route": route, "request": reqname, "biz_name": biz,
                        "visible": visible}
        elif (ftodo is not None
              and acperm.is_eligible_fulfiller_without_todo(
                  user, approval_type=atype, fulfillment_owner=ful.get("owner", ""))):
            # FULFILLMENT stage requires TWO INDEPENDENT signals (Phase 1b.3.1):
            #   ENTITLEMENT  = is_eligible_fulfiller_without_todo -- fulfillment
            #                  owner / configured Fulfiller participant / SM, with
            #                  the ToDo path DELIBERATELY EXCLUDED; AND
            #   ACTION EXISTS = ftodo -- a record-scoped Open fulfillment ToDo for
            #                  THIS user (the engine's per-record assignment).
            # The SAME ToDo row can never establish both, so an Open ToDo alone
            # never grants permission or exposes the business URL. A requester/
            # approver who can merely VIEW never gets it. Due precedence =
            # fulfillment_due_at -> the SAME governed Open ToDo's date -> undated.
            # NEVER the approval-level SLA.
            todo_date = str(ftodo.get("date")) if ftodo.get("date") else ""
            out[key] = {"found": True, "stage": "fulfillment", "terminal": False,
                        "active": True, "due": (ful.get("due", "") or todo_date),
                        "route": route, "request": reqname, "biz_name": biz,
                        "visible": True}
        else:
            # Rejected/Cancelled, OR Approved without an active+open fulfillment
            # -> excluded (terminal). No approval-level SLA is ever reused here.
            out[key] = {"found": True, "stage": "approval", "terminal": True,
                        "active": False, "due": "", "route": route,
                        "request": reqname, "biz_name": biz, "visible": False}
    return out


def _ful_fields(doc):
    """Normalize a business doc's governed fulfillment fields."""
    return {
        "owner": (doc.get("fulfillment_owner") or "").strip(),
        "status": (doc.get("fulfillment_status") or "").strip(),
        "due": str(doc.get("fulfillment_due_at")) if doc.get("fulfillment_due_at") else "",
    }


def _open_fulfillment_todo(biz_dt, biz_name, user):
    """Return THIS user's governed Open fulfillment ToDo on THIS business document
    as {"name", "date"}, or None. The business fulfillment_status and this ToDo
    must AGREE; None -> the item is excluded (never inferred from the status field
    alone). The returned `date` is the authoritative ToDo.date the fulfillment due
    fallback uses (fulfillment_due_at -> THIS ToDo.date -> undated) -- never a
    different ToDo's date and never the approval-level SLA."""
    if not biz_dt or not biz_name:
        return None
    rows = frappe.get_all(
        "ToDo", filters={"reference_type": biz_dt, "reference_name": biz_name,
                         "allocated_to": user, "status": "Open"},
        fields=["name", "date"], limit=1, ignore_permissions=True) or []
    return rows[0] if rows else None


# ---- the shared feed -------------------------------------------------------
def _load_open_todos(user):
    return frappe.db.sql(
        "SELECT name, description, reference_type, reference_name, "
        "       priority, modified, creation, date, status "
        "FROM `tabToDo` "
        "WHERE allocated_to=%s AND status=%s "
        "ORDER BY creation ASC, name ASC LIMIT %s",
        (user, "Open", _SCAN_CAP), as_dict=True) or []


def _classified_feed(user):
    """THE one classification + ordering pass. Loads the user's Open ToDos
    (bounded by _SCAN_CAP), resolves, derives governed due dates, terminal-
    filters, classifies and deterministically orders. Returns
    (ordered_items, counts, source_counts). Every consumer -- flat pagination
    (build_feed), per-bucket previews (bucket_previews) and per-bucket
    pagination (bucket_page) -- reuses THIS; no separate source queries, no
    duplicated classifier, no unbounded fetch."""
    today = frappe.utils.getdate()
    rows = _load_open_todos(user)

    from ecentric_workspace.action_center import resolvers as R
    from ecentric_workspace.action_center.resolvers import APPROVAL_DOCTYPES
    # Engine-link normalization runs BEFORE bucket classification + source_counts
    # so approval-governed business docs (direct or linked) are counted/classified
    # as approvals, not generic ToDos.
    engine_map = _engine_link_state(rows, user)
    approval_names, task_names, wtu_names = set(), set(), set()
    for r in rows:
        rt = (r.get("reference_type") or "").strip()
        rn = (r.get("reference_name") or "").strip()
        if not rn:
            continue
        if (rt, rn) in engine_map:
            continue                                  # handled by the engine adapter
        if rt in APPROVAL_DOCTYPES:
            approval_names.add(rn)
        elif rt == TASK:
            task_names.add(rn)
        elif rt == WTU:
            wtu_names.add(rn)
    appr = _approval_state(approval_names)
    tsk = _task_state(task_names)
    wtu = _wtu_state(wtu_names)

    items = []
    counts = {b: 0 for b in FEED_BUCKETS}
    source_counts = {k: 0 for k in SOURCE_COUNT_KEYS}
    for r in rows:
        try:
            it = resolve_item(r)
        except Exception as e:
            # Do NOT blanket-swallow a genuine DB operational fault (missing
            # column/table, lost connection): re-raise so it surfaces loudly
            # instead of silently dropping every affected row. Ordinary per-row
            # resolution errors are still caught so one bad ToDo cannot sink the
            # whole feed. (getattr fallback keeps this import-safe even if the
            # request-local db is not yet bound.)
            _oe = getattr(getattr(frappe, "db", None), "OperationalError", None)
            if _oe is not None and isinstance(e, _oe):
                raise
            frappe.log_error(frappe.get_traceback(),
                             "action_center.feed resolve failed " + str(r.get("name")))
            continue
        rt = it.get("reference_type")
        rn = it.get("reference_name")
        terminal = active = False
        # PRECEDENCE 1: governed approval (direct EC Approval Request OR a business
        # doc linked via approval_request). The SAME normalized adapter for both.
        el = engine_map.get((rt, rn))
        if el is not None:
            if el.get("found"):
                if el["terminal"]:
                    continue                          # terminal -> excluded (policy unchanged)
                stage = el.get("stage", "approval")
                if el["visible"] and el["route"]:
                    # stage-aware normalize -> canonical Approval Center route.
                    R.apply_approval_normalization(
                        it, el["request"], el["route"], el["biz_name"], stage=stage)
                    active = el["active"]
                    # el["due"] is already the governed value: for fulfillment it
                    # is fulfillment_due_at -> the governed Open ToDo's date; for
                    # approval it is the current level SLA. Never a row-derived or
                    # approval-SLA leak.
                    it["due_at"] = el["due"] or ""
                    terminal = False
                elif stage == "fulfillment":
                    # fulfillment action but user is NOT owner/eligible fulfiller
                    # -> NO item (a viewer must not receive a fulfillment action).
                    continue
                # else: approval stage not visible / no route -> keep resolve_item's
                # generic referenced-document fallback (source stays generic).
            # else: missing/invalid link -> generic referenced-document fallback.
        else:
            # PRECEDENCE 2..4: legacy /approval, PM Task, Weekly Update.
            st = it.get("source_type")
            if st == "approval" and rn in appr:
                terminal, active, due = appr[rn]
                if due and not it.get("due_at"):
                    it["due_at"] = due
            elif st == "task" and rn in tsk:
                terminal, active, due = tsk[rn]
                if due and not it.get("due_at"):
                    it["due_at"] = due
            elif st == "weekly_report" and rn in wtu:
                terminal, active, _ = wtu[rn]
        bucket = classify(it.get("due_at"), today, active, terminal)
        if bucket is None:
            continue
        it["bucket"] = bucket
        it["active"] = bool(active)
        it["resolution_state"] = "open"
        it["_creation"] = str(r.get("creation") or "")
        items.append(it)
        counts[bucket] += 1
        # Fulfillment-stage actions are approval-FAMILY but NOT pending approvals:
        # count them separately so source_counts.approval stays accurate.
        if it.get("action_stage") == "fulfillment":
            sk = "fulfillment"
        else:
            sk = SOURCE_COUNT_KEY.get(it.get("source_type"), "generic_todo")
        source_counts[sk] += 1

    return order_items(items), counts, source_counts


def _clean(items):
    out = []
    for it in items:
        it = dict(it)
        it.pop("_creation", None)
        out.append(it)
    return out


def build_feed(user, cursor=None, limit=DEFAULT_LIMIT):
    """Flat, deterministically ordered, paginated feed (badge + 'Xem tất cả'
    consumers). Reuses _classified_feed."""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    offset = decode_cursor(cursor)
    items, counts, source_counts = _classified_feed(user)
    total = len(items)
    page = _clean(items[offset:offset + limit])
    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total else None
    return {
        "items": page,
        "counts": counts,
        "source_counts": source_counts,
        "total": total,
        "returned": len(page),
        "next_cursor": next_cursor,
        "generated_at": str(frappe.utils.now_datetime()),
    }


def bucket_previews(user, preview_n=PREVIEW_N):
    """PER-BUCKET previews: the FIRST `preview_n` items of EACH bucket from
    the ONE classified+ordered feed BEFORE any global pagination. A high-
    priority bucket can never starve a later one (fixes overdue eating the
    whole limit while upcoming has a count but no payload). No separate source
    queries; bounded scan."""
    preview_n = max(1, min(int(preview_n or PREVIEW_N), MAX_LIMIT))
    items, counts, source_counts = _classified_feed(user)
    bucket_items = {b: [] for b in FEED_BUCKETS}
    for it in items:
        b = it.get("bucket")
        if b in bucket_items and len(bucket_items[b]) < preview_n:
            bucket_items[b].append(it)
    bucket_items = {b: _clean(v) for b, v in bucket_items.items()}
    bucket_has_more = {b: counts.get(b, 0) > len(bucket_items[b]) for b in FEED_BUCKETS}
    return {
        "total": len(items),
        "counts": counts,
        "source_counts": source_counts,
        "bucket_items": bucket_items,
        "bucket_has_more": bucket_has_more,
        "preview_n": preview_n,
        "generated_at": str(frappe.utils.now_datetime()),
    }


def bucket_page(user, bucket, cursor=None, limit=DEFAULT_LIMIT):
    """Governed per-bucket pagination ('Xem thêm N việc'): items of ONE bucket,
    deterministically ordered, paged by cursor. Reuses _classified_feed
    (bounded scan; NEVER an unbounded ToDo fetch)."""
    if bucket not in FEED_BUCKETS:
        return {"bucket": bucket, "items": [], "count": 0, "returned": 0, "next_cursor": None}
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    offset = decode_cursor(cursor)
    items, counts, _ = _classified_feed(user)
    rows = [it for it in items if it.get("bucket") == bucket]
    total = len(rows)
    page = _clean(rows[offset:offset + limit])
    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total else None
    return {
        "bucket": bucket,
        "items": page,
        "count": total,
        "returned": len(page),
        "next_cursor": next_cursor,
    }
