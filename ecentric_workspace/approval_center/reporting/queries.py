# Copyright (c) 2026, eCentric and contributors
"""Governed, parameterized query layer for Approval Center reporting.

The ONLY place that touches the DB for the dashboard. Every query ANDs the scope
predicate (scope.scope_predicate) and uses %(name)s parameters - never string-formatted
values. Callers pass a resolved scope + a validated filter dict.
"""
import re

import frappe

from ecentric_workspace.approval_center.reporting import scope as _scope

# Fetch union of (rows whose submission/creation is in the date range) and (all currently
# open rows), so period KPIs and current pending/SLA views can be computed from one result.
_BASE = """
    FROM `tabEC Approval Request` r
    LEFT JOIN `tabEC Approval Type` t ON t.name = r.approval_type
    LEFT JOIN `tabEC Approval Request Level` cl
           ON cl.approval_request = r.name AND cl.level_no = r.current_level
"""
_FIELDS = """
    r.name AS name, r.approval_type AS approval_type, t.approval_title AS type_title,
    t.category AS category, r.requested_by AS requested_by,
    r.requester_department AS requester_department, r.submitted_at AS submitted_at,
    r.creation AS creation, r.completed_at AS completed_at,
    r.approval_status AS approval_status, r.current_level AS current_level,
    cl.level_name AS current_level_name, cl.activated_at AS current_activated_at,
    cl.due_at AS due_at, cl.is_overdue AS is_overdue, cl.sla_policy AS sla_policy,
    r.reference_doctype AS reference_doctype, r.reference_name AS reference_name,
    t.route AS type_route
"""

_OPEN = "('Pending','Information Required')"


#: Tran so gia tri trong MOT menh de IN cua o loc nhieu gia tri. Danh sach lay tu
#: get_all_filters cung bi chan o 500 (all_list.DISTINCT_MAX) - day la lop chan thu hai.
IN_MAX = 500


def _non_date_filters(filters, params):
    """Build filter fragments (excluding date range) into a list; mutate params."""
    frag = []
    m = {
        "category": "t.category",
        "approval_type": "r.approval_type",
        "department": "r.requester_department",
        "requester": "r.requested_by",
        "status": "r.approval_status",
        "current_level": "r.current_level",
    }
    for key, col in m.items():
        val = (filters or {}).get(key)
        if val in (None, "", [], ()):
            continue
        pk = "f_" + key
        if isinstance(val, (list, tuple)):
            # Nhieu gia tri (o loc dang danh sach tick cua tab "Tat ca", 16/10/2026): IN voi
            # MOI gia tri mot tham so. Khong bao gio truyen ca list vao mot %(x)s - driver se
            # noi no thanh "('a','b')" sau dau "=", vua sai vua tuy driver.
            khoa = []
            for i, x in enumerate(list(val)[:IN_MAX]):
                k = "%s_%d" % (pk, i)
                params[k] = x
                khoa.append("%%(%s)s" % k)
            frag.append("%s IN (%s)" % (col, ", ".join(khoa)))
            continue
        params[pk] = val
        frag.append("%s = %%(%s)s" % (col, pk))
    # approver filter -> membership on the approver child
    approver = (filters or {}).get("approver")
    if approver:
        params["f_approver"] = approver
        frag.append("EXISTS (SELECT 1 FROM `tabEC Approval Request Approver` fa "
                    "WHERE fa.approval_request = r.name AND fa.approver = %(f_approver)s)")
    return frag


def fetch_scoped_rows(scope, filters):
    """Rows in the date range OR currently open, within scope + non-date filters.
    Each row is tagged by the caller (service) for period/open membership."""
    params = {}
    where = ["1=1"]
    sp, sparams = _scope.scope_predicate(scope)
    where.append(sp)
    params.update(sparams)
    where.extend(_non_date_filters(filters, params))

    df = (filters or {}).get("date_from")
    dt = (filters or {}).get("date_to")
    if df and dt:
        params["date_from"] = df
        params["date_to"] = dt
        date_clause = ("(COALESCE(r.submitted_at, r.creation) BETWEEN %(date_from)s AND %(date_to)s "
                       "OR r.approval_status IN " + _OPEN + ")")
        where.append(date_clause)

    sql = "SELECT " + _FIELDS + _BASE + " WHERE " + " AND ".join(where) + " ORDER BY r.submitted_at DESC"
    return frappe.db.sql(sql, params, as_dict=True)


def fetch_rows_in_window(scope, filters, date_from, date_to):
    """Rows whose submission/creation falls strictly in [date_from, date_to] within scope +
    non-date filters (NO open-status union). Used for previous-period comparison and the
    volume/SLA time-series."""
    params = {"win_from": date_from, "win_to": date_to}
    where = ["1=1"]
    sp, sparams = _scope.scope_predicate(scope)
    where.append(sp)
    params.update(sparams)
    where.extend(_non_date_filters(filters, params))
    where.append("COALESCE(r.submitted_at, r.creation) BETWEEN %(win_from)s AND %(win_to)s")
    sql = "SELECT " + _FIELDS + _BASE + " WHERE " + " AND ".join(where) + " ORDER BY r.submitted_at ASC"
    return frappe.db.sql(sql, params, as_dict=True)


def fetch_levels_for_bottleneck(scope, filters, completed_from=None, completed_to=None):
    """Per-level rows for in-scope requests: completed durations + current pending, used
    to rank bottleneck levels. Skipped levels are excluded from duration by the caller.
    When completed_from/to are given, only levels COMPLETED in that window are returned
    (used for period-vs-previous bottleneck trend)."""
    params = {}
    where = ["1=1"]
    sp, sparams = _scope.scope_predicate(scope)
    where.append(sp)
    params.update(sparams)
    where.extend(_non_date_filters(filters, params))
    if completed_from and completed_to:
        params["lvl_from"] = completed_from
        params["lvl_to"] = completed_to
        where.append("rl.completed_at BETWEEN %(lvl_from)s AND %(lvl_to)s")
    sql = """
        SELECT rl.level_name AS level_name, rl.level_status AS level_status,
               rl.activated_at AS activated_at, rl.completed_at AS completed_at,
               r.approval_status AS approval_status, r.current_level AS current_level,
               rl.level_no AS level_no
        FROM `tabEC Approval Request Level` rl
        JOIN `tabEC Approval Request` r ON r.name = rl.approval_request
        LEFT JOIN `tabEC Approval Type` t ON t.name = r.approval_type
        WHERE %s
    """ % " AND ".join(where)
    return frappe.db.sql(sql, params, as_dict=True)


#: Tran so ma phieu nhet vao menh de IN cua o tim kiem. Khong phai tiet kiem tai nguyen -
#: mot menh de IN vai nghin phan tu la cach bien o tim kiem thanh don tan cong vao chinh DB.
SEARCH_REF_MAX = 500


def _search_clause(search, params, extra_refs=None):
    """O tim kiem cua trang "Tat ca yeu cau".

    `r.reference_name` (09/09/2026): nguoi dung cam MA PHIEU tren tay - tu thong bao
    Teams, tu email, tu cong ky so - roi go vao day va khong ra gi. Bang chi HIEN ma ho
    so duyet (EC-APR-...), con ma phieu (EC-PAYR-..., EC-PURR-...) thi khong o dau ca,
    nen Ctrl+F cua trinh duyet cung chiu. Hoan vap dung cai nay khi tra EC-PAYR-2026-00053
    (= EC-APR-2026-00166) va ket luan "khong tim thay phieu" trong khi no dang nam ngay
    truoc mat.

    Them mot ve OR, khong dung toi pham vi xem: dieu kien nay van duoc AND voi
    scope_predicate o `_list_where`, nen khong ai vi the ma thay them phieu cua nguoi khac.

    `extra_refs` (16/09): TIEU DE that cua phieu nam o DocType nghiep vu, khong o
    `EC Approval Request` - nen go dung ten phieu vao o tim kiem thi khong ra gi, trong khi
    do la CHINH CAI cot "Tieu de" dang hien tren man hinh. Tab "Tat ca" cua tung form BIET
    business_doctype cua no, nen tu tra ma phieu theo tieu de roi truyen vao day. Trang hub
    lien-form khong truyen gi -> hanh vi khong doi (tra tieu de qua 28 DocType moi lan go
    mot phim thi khong dang).
    """
    if not search and not extra_refs:
        return None
    ve = []
    if search:
        params["search"] = "%" + str(search).strip() + "%"
        ve.append("r.name LIKE %(search)s OR r.reference_name LIKE %(search)s "
                  "OR t.approval_title LIKE %(search)s "
                  "OR r.requested_by LIKE %(search)s OR r.requester_department LIKE %(search)s")
    if extra_refs:
        khoa = []
        for i, x in enumerate(list(extra_refs)[:SEARCH_REF_MAX]):
            k = "sref_%d" % i
            params[k] = x
            khoa.append("%%(%s)s" % k)
        if khoa:
            ve.append("r.reference_name IN (%s)" % ", ".join(khoa))
    return "(" + " OR ".join(ve) + ")"


def _fulfillment_refs(me=None):
    """Business records that are MINE to work on, across every form.

    'Chờ tôi xử lý' means: still unclaimed (fulfillment_status=Assigned) on a form I am an
    eligible fulfiller for, OR already claimed BY ME (In Progress + owner=me). Work claimed
    by someone else is deliberately excluded -- it is not mine to act on.

    16/09 - "DUYET XONG PHIEU KHONG BIEN MAT" (anh Lam bao).
    ---------------------------------------------------------------------------------
    Do duoc: anh Lam duyet cap cuoi EC-APR-2026-00265 luc 16:57:03.526; 51ms sau, phieu
    nghiep vu EC-PAYR-2026-00144 mang fulfillment_status='Assigned'. Tuc dong vua roi khoi
    ve (a) "cho toi duyet" thi rot NGAY vao ve (b) "viec fulfilment cua toi" cua CUNG mot
    hop - nguoi dung thay mot dong y nguyen va ket luan "bam duyet khong an gi".

    Vi sao no rot vao ve (b): ham nay hoi `is_eligible_fulfiller(me, code, dt)` ma KHONG
    truyen `business_name`. O dang do, ham con mot duong "co mot ToDo mo BAT KY tren LOAI
    phieu nay" - ma nguoi duyet thi gan nhu luc nao cung co ToDo mo tren Payment Request,
    vi do chinh la cach bo may giao viec duyet. Ket qua: MOI phieu chua ai nhan (23 phieu
    luc do) nam trong hop cua anh, va cai vua duyet nhap vao cung. Khi cac ToDo cua anh
    dong lai thi lan tai tiep theo chung bien mat - dung cai "refresh lai thi mat", va no
    that thuong vi phu thuoc ToDo nao con mo.

    Chinh docstring cua `is_eligible_fulfiller` da canh dung duong nay tu 01/09, va da siet
    cho `can_view_request`; cho nay bi bo sot.

    SUA: hoi `is_eligible_fulfiller_without_todo` - ham duoc viet ra dung de LOAI duong
    ToDo long leo do. "Viec cua toi" = toi la nguoi dang giu, hoac System Manager, hoac
    Fulfiller DUOC CAU HINH. Mot ToDo duyet khong bien mot nguoi thanh nguoi xu ly.

    KHONG dung toi pham vi xem: ham nay chi chon dong nao vao HOP nao. Pham vi van do
    `scope_predicate` AND vao cung truy van, va `scope._fulfil_types` dung mot duong khac
    (`fulfilled_approval_types`, fail-closed) nen khong he mo rong theo duong ToDo.

    fulfillment_status lives on each business DocType (not on EC Approval Request) so it
    cannot be joined; open fulfillment work is small, so we collect names per registered form
    and the caller filters the list by reference_name."""
    import frappe as _f
    names = []
    if not me:
        return names
    try:
        from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS
        defs = list(APPROVAL_DEFINITIONS.values())
    except Exception:
        return names
    try:
        from ecentric_workspace.approval_center.shared.workflow import permissions as _perm
    except Exception:
        _perm = None
    seen = set()
    for d in defs:
        dt = getattr(d, "business_doctype", None)
        code = getattr(d, "code", None)
        if not dt or dt in seen:
            continue
        seen.add(dt)
        try:
            if not _f.get_meta(dt).has_field("fulfillment_status"):
                continue
            # already mine
            names += _f.get_all(dt, filters={"fulfillment_status": "In Progress",
                                             "fulfillment_owner": me},
                                pluck="name", limit_page_length=0)
            # unclaimed, but only on forms I may actually fulfil.
            # FAIL-CLOSED: khong nap duoc module quyen thi KHONG cho gi vao hop. Truoc day
            # mac dinh la True va chi bi ha xuong khi goi duoc ham - tuc mot loi import se
            # do MOI phieu chua ai nhan vao hop cua MOI nguoi. Voi du lieu thanh toan thi
            # mac dinh phai la dong, khong phai mo.
            eligible = False
            if _perm is not None:
                try:
                    eligible = bool(_perm.is_eligible_fulfiller_without_todo(me, code))
                except Exception:
                    eligible = False
            if eligible:
                names += _f.get_all(dt, filters={"fulfillment_status": "Assigned"},
                                    pluck="name", limit_page_length=0)
        except Exception:
            continue
    return names


def _list_where(scope, filters, search, params):
    where = ["1=1"]
    sp, sparams = _scope.scope_predicate(scope)
    where.append(sp)
    params.update(sparams)
    where.extend(_non_date_filters(filters, params))
    df = (filters or {}).get("date_from")
    dt = (filters or {}).get("date_to")
    if df and dt:
        params["date_from"] = df
        params["date_to"] = dt
        where.append("COALESCE(r.submitted_at, r.creation) BETWEEN %(date_from)s AND %(date_to)s")
    sc = _search_clause(search, params, (filters or {}).get("_search_refs"))
    if sc:
        where.append(sc)
    box = (filters or {}).get("box")
    me = (filters or {}).get("_me")
    if box == "sent" and me:
        params["_me_sent"] = me
        where.append("r.requested_by = %(_me_sent)s")
    elif box == "received" and me:
        params["_me_recv"] = me
        where.append("EXISTS (SELECT 1 FROM `tabEC Approval Request Approver` va "
                     "WHERE va.approval_request = r.name AND va.approver = %(_me_recv)s)")
    elif box == "fulfil":
        where.append(_my_todo_clause(me, params))
    bz = _biz_clause(filters, params)
    if bz:
        where.append(bz)
    return " AND ".join(where)


# --------------------------------------------------------------------------------------
# Loc / sap xep theo truong cua DocType NGHIEP VU (tab "Tat ca" cua tung form, 16/10/2026).
#
# Tieu de, so tien, brand... nam o DocType nghiep vu, khong o `EC Approval Request`. Tab
# "Tat ca" cua MOT form biet dung DocType nghiep vu cua no, nen all_list dung san mot dac ta
# `_biz` (KHOA NOI BO, gach duoi: `_parse_filters` khong bao gio chep no tu client - cung
# loai voi `_search_refs`, `_me`). Trang hub lien-form khong dat `_biz` -> hanh vi khong doi.
#
# Dinh danh (ten DocType, ten truong) KHONG the di bang tham so SQL, nen bi chan hai lop:
# all_list chi dua vao nhung gi definition khai VA meta co that; o day kiem lai bang regex
# truoc khi dat vao dau backtick. Gia tri luon la %(tham_so)s.
# --------------------------------------------------------------------------------------

_BIZ_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_BIZ_DT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,139}$")

#: Sap xep (16/10/2026, loc tren header cot): all_list dich {"col","dir"} cua client thanh
#: mot dac ta NOI BO `_sort` = {"key", "dir", ...}. Chi ba loai khoa duoc dung ORDER BY:
#:   submitted  - ngay gui (mac dinh, DESC)
#:   status     - trang thai phieu, theo THU TU NHAN TIENG VIET do all_list dua vao (`order`)
#:   biz        - mot truong cua DocType nghiep vu (`field`, da kiem o all_list + regex o day)
#: Khoa / chieu la -> mac dinh moi -> cu. Khong co manh ORDER BY nao do client viet.
SORT_KINDS = ("submitted", "status", "biz")
SORT_DIRS = ("asc", "desc")
_NGAY = "COALESCE(r.submitted_at, r.creation)"
_MAC_DINH = _NGAY + " DESC"


def _biz_ident(dt, field=None):
    if not (isinstance(dt, str) and _BIZ_DT_RE.match(dt)):
        raise ValueError("biz doctype khong hop le: %r" % (dt,))
    if field is not None and not (isinstance(field, str) and _BIZ_FIELD_RE.match(field)):
        raise ValueError("biz field khong hop le: %r" % (field,))
    return "`tab%s`" % dt, ("`%s`" % field if field else None)


def _biz_clause(filters, params):
    """EXISTS tren DocType nghiep vu cho cac dieu kien `_biz` (bang / thuoc / so tien tu - den).

    `eq`  = ((field, gia_tri), ...)        - mot gia tri (dang cu)
    `in`  = ((field, (gt1, gt2, ...)), ...) - nhieu gia tri (o tick tren header cot)
    Tra None khi khong co dieu kien nao. Duoc AND vao `where` cung scope_predicate - day la
    LOC THU HEP, khong bao gio noi rong pham vi."""
    biz = (filters or {}).get("_biz") or {}
    dt = biz.get("doctype")
    if not dt:
        return None
    conds = []
    bang, _ = _biz_ident(dt)
    for i, (field, val) in enumerate(biz.get("eq") or ()):
        _, cot = _biz_ident(dt, field)
        k = "bz_eq%d" % i
        params[k] = val
        conds.append("b.%s = %%(%s)s" % (cot, k))
    for i, (field, vals) in enumerate(biz.get("in") or ()):
        _, cot = _biz_ident(dt, field)
        khoa = []
        for j, val in enumerate(list(vals or ())[:IN_MAX]):
            k = "bz_in%d_%d" % (i, j)
            params[k] = val
            khoa.append("%%(%s)s" % k)
        if khoa:
            conds.append("b.%s IN (%s)" % (cot, ", ".join(khoa)))
    amt = biz.get("amount_field")
    for key, op in (("amount_min", ">="), ("amount_max", "<=")):
        val = biz.get(key)
        if val is None or not amt:
            continue
        _, cot = _biz_ident(dt, amt)
        params["bz_" + key] = val
        conds.append("b.%s %s %%(bz_%s)s" % (cot, op, key))
    if not conds:
        return None
    params["bz_dt"] = dt
    return ("EXISTS (SELECT 1 FROM " + bang + " b WHERE b.name = r.reference_name "
            "AND r.reference_doctype = %(bz_dt)s AND " + " AND ".join(conds) + ")")


def _order_by(filters, params=None):
    """ORDER BY tu dac ta `_sort` (xem SORT_KINDS). Khong co / la -> y nhu truoc day.

    `params` chi can cho sap theo trang thai (thu tu nhan di bang tham so). Thieu `params`
    thi sap trang thai roi ve thu tu cot tho - khong bao gio noi gia tri vao chuoi SQL."""
    s = (filters or {}).get("_sort")
    if not isinstance(s, dict):
        return _MAC_DINH
    key, huong = s.get("key"), s.get("dir")
    if key not in SORT_KINDS or huong not in SORT_DIRS:
        return _MAC_DINH
    H = huong.upper()
    if key == "submitted":
        return _MAC_DINH if huong == "desc" else _NGAY + " ASC, r.name ASC"
    if key == "status":
        order = [x for x in (s.get("order") or ()) if isinstance(x, str)][:20]
        if not order or params is None:
            return "r.approval_status %s, %s DESC, r.name DESC" % (H, _NGAY)
        khoa = []
        for i, x in enumerate(order):
            k = "so_st%d" % i
            params[k] = x
            khoa.append("%%(%s)s" % k)
        return "FIELD(r.approval_status, %s) %s, %s DESC, r.name DESC" % (
            ", ".join(khoa), H, _NGAY)
    # key == "biz"
    biz = (filters or {}).get("_biz") or {}
    dt, field = biz.get("doctype"), s.get("field")
    if not (dt and field):
        return _MAC_DINH
    bang, cot = _biz_ident(dt, field)
    gt = "(SELECT b.%s FROM %s b WHERE b.name = r.reference_name)" % (cot, bang)
    # Phieu khong co gia tri luon xuong CUOI, ca hai chieu: dua 20 dong "trong" len dau
    # bang "tang dan" la giau mat thu nguoi ta dang tim. Truong chu: chuoi rong cung la trong.
    # Truong so / ngay: chi NULL (0 la mot so tien that; so '' voi ngay la canh bao cua DB).
    trong = ("(%s IS NULL OR %s = '')" % (gt, gt)) if s.get("text") else ("%s IS NULL" % gt)
    return "%s, %s %s, %s DESC, r.name DESC" % (trong, gt, H, _NGAY)


def awaiting_my_decision_sql(param_name):
    """Hồ sơ ĐANG chờ chính người này bấm duyệt.

    Dùng đúng định nghĩa của engine (transitions._level_pending_approvers): dòng approver ở
    ĐÚNG cấp hiện tại và còn status='Pending'. Không dùng "là approver bất kỳ" — như vậy sẽ
    kéo cả hồ sơ mình đã duyệt xong hoặc còn ở cấp người khác."""
    return ("(r.approval_status IN " + _OPEN + " AND EXISTS ("
            "SELECT 1 FROM `tabEC Approval Request Approver` va "
            "WHERE va.approval_request = r.name AND va.approver = %(" + param_name + ")s "
            "AND va.level_no = r.current_level AND va.status = 'Pending'))")


def _my_todo_clause(me, params):
    """Tab 'Chờ tôi xử lý' = MỌI việc đang chờ tôi ra tay.

    Trước đây tab này chỉ có phần Operation nhận xử lý SAU khi duyệt xong, nên hồ sơ đang chờ
    chính mình bấm duyệt lại không xuất hiện — đúng thứ người dùng vào tab này để tìm.
    Nay là hợp của hai vế: (a) chờ tôi duyệt, (b) việc fulfilment của tôi."""
    parts = []
    if me:
        params["_me_todo"] = me
        parts.append(awaiting_my_decision_sql("_me_todo"))
    refs = _fulfillment_refs(me)
    if refs:
        keys = []
        for i, nm in enumerate(refs):
            k = "_ff%d" % i
            params[k] = nm
            keys.append("%%(%s)s" % k)
        parts.append("r.reference_name IN (" + ", ".join(keys) + ")")
    if not parts:
        return "1=0"
    return "(" + " OR ".join(parts) + ")"


def fetch_requests_page(scope, filters, start, page_length, search=None):
    """One governed, scoped, paginated page of requests across all forms (all statuses)."""
    params = {}
    where = _list_where(scope, filters, search, params)
    params["_start"] = int(start)
    params["_len"] = int(page_length)
    sql = ("SELECT " + _FIELDS + _BASE + " WHERE " + where +
           " ORDER BY " + _order_by(filters, params) + " LIMIT %(_start)s, %(_len)s")
    return frappe.db.sql(sql, params, as_dict=True)


def count_requests(scope, filters, search=None):
    params = {}
    where = _list_where(scope, filters, search, params)
    row = frappe.db.sql("SELECT COUNT(*) AS c FROM `tabEC Approval Request` r "
                        "LEFT JOIN `tabEC Approval Type` t ON t.name = r.approval_type "
                        "WHERE " + where, params, as_dict=True)
    return row[0]["c"] if row else 0


def is_visible(scope, request_name):
    """True iff `request_name` falls within the caller's scope. Used to gate the timeline
    drawer without any DocPerm dependency."""
    sp, params = _scope.scope_predicate(scope)
    params["vis_name"] = request_name
    row = frappe.db.sql("SELECT 1 FROM `tabEC Approval Request` r WHERE " + sp +
                        " AND r.name = %(vis_name)s LIMIT 1", params)
    return bool(row)


def distinct_filter_values(scope):
    """Scoped distinct values for filter dropdowns (types, categories, departments)."""
    sp, params = _scope.scope_predicate(scope)
    types = frappe.db.sql(
        "SELECT DISTINCT r.approval_type AS v, t.approval_title AS label "
        "FROM `tabEC Approval Request` r LEFT JOIN `tabEC Approval Type` t ON t.name=r.approval_type "
        "WHERE " + sp + " AND r.approval_type IS NOT NULL ORDER BY t.approval_title", params, as_dict=True)
    cats = frappe.db.sql(
        "SELECT DISTINCT t.category AS v FROM `tabEC Approval Request` r "
        "LEFT JOIN `tabEC Approval Type` t ON t.name=r.approval_type "
        "WHERE " + sp + " AND t.category IS NOT NULL ORDER BY t.category", params, as_dict=True)
    depts = frappe.db.sql(
        "SELECT DISTINCT r.requester_department AS v FROM `tabEC Approval Request` r "
        "WHERE " + sp + " AND r.requester_department IS NOT NULL ORDER BY r.requester_department",
        params, as_dict=True)
    return {"types": types, "categories": [c["v"] for c in cats], "departments": [d["v"] for d in depts]}


def fetch_my_drafts(me):
    """Ban nhap CUA TOI o moi loai yeu cau da dang ky (05/09, Hoan): phieu "Luu nhap" xong bien
    mat - khong co EC Approval Request nen khong nam trong bat ky tab nao. Ban nhap = ban ghi
    nghiep vu docstatus 0, owner = toi, CHUA co approval_request. Doctype khong co cot
    approval_request thi bo qua (khong doan)."""
    from ecentric_workspace.approval_center.shared.registry import BUSINESS_DOCTYPE_DEFINITIONS
    out = []
    for dt, definition in BUSINESS_DOCTYPE_DEFINITIONS.items():
        if not frappe.db.table_exists(dt) or not frappe.db.has_column(dt, "approval_request"):
            continue
        filters = {"owner": me, "docstatus": 0, "approval_request": ["is", "not set"]}
        if frappe.db.has_column(dt, "status"):
            filters["status"] = ["not in", ["Cancelled", "Rejected"]]
        for r in frappe.get_all(dt, filters=filters, fields=["name", "modified", "creation"],
                                order_by="modified desc", limit_page_length=50):
            out.append({"doctype": dt, "name": r.name, "approval_type": definition.code,
                        "modified": r.modified, "creation": r.creation})
    out.sort(key=lambda r: r["modified"] or "", reverse=True)
    return out
