# ============================================================================
# BAN SAO DOI CHIEU - KHONG PHAI CODE CHAY.
#
# Day la ban sao y het cua Server Script `ec_pnl_data` dang chay tren
# team.ecentric.vn (Server Script, script_type = API, api_method =
# 'ec_pnl_data'). Frappe KHONG import file nay; no nam trong repo chi de repo
# khong bi mu ve logic dang chay.
#
# Sua that = sua Server Script tren live qua REST, roi cap nhat lai file nay
# trong cung mot commit. Cu phap tuan theo RestrictedPython cua Server Script
# (khong import, khong dunder, khong tuple-unpack trong vong lap).
# ============================================================================

# ec_pnl_data - API doc-only cho Dashboard PnL (giai doan 1: DOANH THU)
# Server Script, script_type = API, api_method = 'ec_pnl_data'
#
# CHI DOC. Khong ghi, khong sua bat ky chung tu SO/PO/GBS nao.
#
# Nguon doanh thu: Sales Order so EC (ca 2 kenh Direct + GBS doi ung).
#   - Dung net_total (KHONG dung grand_total): tinh den 2026-08-09 chi 1/198 phieu
#     co thue > 0 vi form moi gan dong VAT that tu 2026-08-07. Lay grand_total se
#     lam thang 8 vot len gia tao so voi thang truoc.
#   - Loai han phieu Rejected va phieu docstatus = 2 (cancelled).
#   - 3 lop theo DO TIN CAY, gia tri luon 100% (khong nhan he so):
#       Approved = da duyet (tin cay 90%)
#       Pending* = dang xu ly (50%)
#       Draft    = khai bao   (30%)
#
# Lat cat dich vu: gom theo Item.item_group cua BANG ITEM MASTER, khong lay
# item_group snapshot tren dong SO - snapshot bi lech (REV_MKT_DAYLYLIVE nam o
# ca 2 nhom). Chi tiet cap 2 la item_code.
#
# QUYEN XEM (siet lai 2026-08-10 theo yeu cau cua Hoan):
#   Chi cho vao khi thoa MOT trong ba dieu kien:
#     1. co role 'System Manager'
#     2. co ban ghi 'EC Viewer Permission' voi scope = 'all'
#     3. Employee.department = 'Management - EC'
#   Ban dau con dieu kien thu 4 la "co nhan su truc thuoc" (reports_to tro ve
#   minh). Da BO: dieu kien do bat trung ca truong nhom cap duoi phong ban
#   (Project Lead, Senior Project Lead, Analytics Engineer, Merchandise &
#   Content Lead) chu khong chi cap quan ly phong -> 13 nguoi thay vi 8.
#   KHONG loc bang tu khoa designation (quy tac A14); ranh gioi duy nhat co
#   that trong du lieu la phong ban 'Management - EC'. Doctype 'Global Role'
#   (ceo/hof) KHONG ton tai tren site nay - chi nam trong runbook trong _archive.
#   Mo them cho ai = them ban ghi EC Viewer Permission scope='all', khong sua code.
#
# Params (form_dict, tat ca optional):
#   date_from, date_to : YYYY-MM-DD. Mac dinh = khoang co du lieu.
#   granularity        : day | week | month  (mac dinh month)
#   date_basis         : txn | delivery  (mac dinh txn)
#       txn      = transaction_date = ngay chung tu. Tren GBS SO no trung ngay
#                  BAT DAU ky dich vu o 263/308 phieu.
#       delivery = delivery_date = ngay giao. Trung ngay KET THUC ky dich vu o
#                  280/308 phieu.
#       Ca 175 phieu dang tinh deu co du ca 2 ngay; 63 phieu roi khac thang.
#   channel            : all | Direct | GBS  (mac dinh all)
#   brand, team        : loc them theo ec_brand / ec_team
#   debug_as_user      : chi System Manager, de xem thu goc nhin cua nguoi khac

MGMT_DEPT = "Management - EC"
DEPT_SUFFIX = " - EC"
DEPT_ALIAS = {"Operation & Data & System": "Operation, Data & System"}
CONFIDENCE = {"approved": 90, "pending": 50, "draft": 30}

notes = []

# ---------------------------------------------------------------- viewer scope
session_user = frappe.session.user or ""

is_sysmgr = False
if session_user and session_user != "Guest":
    sm_rows = frappe.db.sql("""
        SELECT name FROM `tabHas Role`
        WHERE parent = %s AND parenttype = 'User' AND role = 'System Manager' LIMIT 1
    """, (session_user,))
    if sm_rows:
        is_sysmgr = True

if is_sysmgr and frappe.form_dict and frappe.form_dict.get("debug_as_user"):
    session_user = frappe.form_dict.get("debug_as_user")
    notes = notes + ["Dang xem duoi goc nhin cua " + str(session_user)]
    sm2 = frappe.db.sql("""
        SELECT name FROM `tabHas Role`
        WHERE parent = %s AND parenttype = 'User' AND role = 'System Manager' LIMIT 1
    """, (session_user,))
    is_sysmgr = True if sm2 else False

scope_mode = ""
viewer_dept = ""
viewer_team = ""
emp_key = ""

if session_user and session_user != "Guest":
    emp_rows = frappe.db.sql("""
        SELECT name, department FROM `tabEmployee`
        WHERE user_id = %s AND status = 'Active' LIMIT 1
    """, (session_user,), as_dict=True)
    if emp_rows:
        emp_key = emp_rows[0].get("name") or ""
        viewer_dept = emp_rows[0].get("department") or ""

if viewer_dept:
    plain = viewer_dept
    if plain[-len(DEPT_SUFFIX):] == DEPT_SUFFIX:
        plain = plain[:-len(DEPT_SUFFIX)]
    viewer_team = DEPT_ALIAS.get(plain) or plain

if is_sysmgr:
    scope_mode = "admin"
else:
    if session_user and frappe.db.exists("EC Viewer Permission", session_user):
        vp = frappe.get_doc("EC Viewer Permission", session_user)
        if vp.scope == "all":
            scope_mode = "admin"
    if not scope_mode and viewer_dept == MGMT_DEPT:
        scope_mode = "management"

if not scope_mode:
    frappe.response["message"] = {
        "ok": False,
        "error": "no_permission",
        "message": "Ban khong co quyen xem bao cao PnL. Chi CEO / HOF / Manager moi duoc xem.",
        "scope": {"user": session_user, "mode": "", "department": viewer_dept},
    }
else:
    # ------------------------------------------------------------ params
    fd = frappe.form_dict or {}
    granularity = (fd.get("granularity") or "month").lower().strip()
    if granularity not in ("day", "week", "month"):
        granularity = "month"
    basis = (fd.get("date_basis") or "txn").lower().strip()
    if basis not in ("txn", "delivery"):
        basis = "txn"
    # danh sach trang, KHONG ghep chuoi tu input nguoi dung vao SQL
    dcol = "so.delivery_date" if basis == "delivery" else "so.transaction_date"
    dfield = "delivery_date" if basis == "delivery" else "transaction_date"
    channel = (fd.get("channel") or "all").strip()
    f_brand = (fd.get("brand") or "").strip()
    f_team = (fd.get("team") or "").strip()

    bound = frappe.db.sql("""
        SELECT MIN(""" + dfield + """) AS dmin, MAX(""" + dfield + """) AS dmax
        FROM `tabSales Order`
        WHERE docstatus < 2 AND ifnull(workflow_state, '') <> 'Rejected'
    """, as_dict=True)
    dmin = str(bound[0].get("dmin") or "2026-01-01") if bound else "2026-01-01"
    dmax = str(bound[0].get("dmax") or frappe.utils.today()) if bound else frappe.utils.today()
    date_from = (fd.get("date_from") or "").strip() or dmin
    date_to = (fd.get("date_to") or "").strip() or dmax

    where_extra = ""
    args = {"df": date_from, "dt": date_to}
    if channel in ("Direct", "GBS"):
        where_extra = where_extra + " AND ifnull(so.ec_channel, '') = %(ch)s "
        args["ch"] = channel
    if f_brand:
        where_extra = where_extra + " AND ifnull(so.ec_brand, '') = %(br)s "
        args["br"] = f_brand
    if f_team:
        where_extra = where_extra + " AND ifnull(so.ec_team, '') = %(tm)s "
        args["tm"] = f_team

    # ------------------------------------------------------------ header rows
    so_rows = frappe.db.sql("""
        SELECT so.name, so.transaction_date, so.delivery_date,
               so.workflow_state, so.docstatus,
               so.ec_channel, so.ec_brand, so.ec_team, so.customer,
               so.net_total, so.total_taxes_and_charges, so.grand_total,
               so.ec_gbs_so_ref, so.ec_in_out_budget
        FROM `tabSales Order` so
        WHERE so.docstatus < 2
          AND """ + dcol + """ >= %(df)s AND """ + dcol + """ <= %(dt)s
    """ + where_extra + """
        ORDER BY """ + dcol + """ ASC
    """, args, as_dict=True)

    item_rows = frappe.db.sql("""
        SELECT soi.parent, soi.item_code, soi.amount,
               it.item_group AS master_group, it.item_name AS master_name
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        LEFT JOIN `tabItem` it ON it.name = soi.item_code
        WHERE so.docstatus < 2
          AND """ + dcol + """ >= %(df)s AND """ + dcol + """ <= %(dt)s
    """ + where_extra, args, as_dict=True)

    # ------------------------------------------------------------ classify
    layer_of = {}
    rejected_amt = 0.0
    rejected_cnt = 0
    other_states = {}
    for r in so_rows:
        st = (r.get("workflow_state") or "").strip()
        lay = ""
        if st == "Approved":
            lay = "approved"
        elif st[:7] == "Pending":
            lay = "pending"
        elif st == "Draft":
            lay = "draft"
        elif st == "Rejected":
            lay = "rejected"
            rejected_amt = rejected_amt + (r.get("net_total") or 0)
            rejected_cnt = rejected_cnt + 1
        else:
            lay = "other"
            other_states[st] = (other_states.get(st) or 0) + 1
        layer_of[r.get("name")] = lay
    if other_states:
        notes = notes + ["Co workflow_state la khong nhan dien duoc, da xep vao nhom khac: "
                         + str(other_states)]

    live_rows = [r for r in so_rows if layer_of.get(r.get("name")) in ("approved", "pending", "draft")]

    def blank():
        return {"approved": 0.0, "pending": 0.0, "draft": 0.0,
                "approved_cnt": 0, "pending_cnt": 0, "draft_cnt": 0}

    def bump(acc, lay, amt):
        acc[lay] = (acc.get(lay) or 0) + (amt or 0)
        acc[lay + "_cnt"] = (acc.get(lay + "_cnt") or 0) + 1
        return acc

    def finish(acc, key, label):
        tot = acc["approved"] + acc["pending"] + acc["draft"]
        return {"key": key, "label": label, "approved": acc["approved"],
                "pending": acc["pending"], "draft": acc["draft"], "total": tot,
                "approved_cnt": acc["approved_cnt"], "pending_cnt": acc["pending_cnt"],
                "draft_cnt": acc["draft_cnt"],
                "count": acc["approved_cnt"] + acc["pending_cnt"] + acc["draft_cnt"]}

    def bucket_of(dval, gran):
        d = frappe.utils.getdate(dval)
        if not d:
            return "?"
        if gran == "day":
            return str(d)
        if gran == "month":
            return str(d)[:7]
        iso = d.isocalendar()
        wk = str(iso[1])
        if iso[1] < 10:
            wk = "0" + wk
        return str(iso[0]) + "-W" + wk

    # ------------------------------------------------------------ totals
    totals = blank()
    for r in live_rows:
        totals = bump(totals, layer_of.get(r.get("name")), r.get("net_total"))
    totals_out = finish(totals, "all", "Toan cong ty")

    # ------------------------------------------------------------ time series
    ser = {}
    for r in live_rows:
        b = bucket_of(r.get(dfield), granularity)
        if b not in ser:
            ser[b] = blank()
        ser[b] = bump(ser[b], layer_of.get(r.get("name")), r.get("net_total"))
    series = []
    for b in sorted(ser.keys()):
        series = series + [finish(ser[b], b, b)]

    # ------------------------------------------------------------ dimensions
    def group_rows(rows, field, fallback_label, lmap):
        acc = {}
        for r in rows:
            k = (r.get(field) or "").strip() or fallback_label
            if k not in acc:
                acc[k] = blank()
            acc[k] = bump(acc[k], lmap.get(r.get("name")), r.get("net_total"))
        out = []
        for k in acc:
            out = out + [finish(acc[k], k, k)]
        return sorted(out, key=lambda x: x["total"], reverse=True)

    by_brand = group_rows(live_rows, "ec_brand", "(chua gan brand)", layer_of)
    by_team = group_rows(live_rows, "ec_team", "(chua gan phong ban)", layer_of)
    by_channel = group_rows(live_rows, "ec_channel", "(chua gan kenh)", layer_of)

    # ------------------------------------------------------------ services
    svc = {}
    item_acc = {}
    item_meta = {}
    for r in item_rows:
        lay = layer_of.get(r.get("parent"))
        if lay not in ("approved", "pending", "draft"):
            continue
        grp = (r.get("master_group") or "").strip() or "(chua phan nhom)"
        code = (r.get("item_code") or "").strip() or "(khong ro)"
        if grp not in svc:
            svc[grp] = blank()
        svc[grp] = bump(svc[grp], lay, r.get("amount"))
        ik = grp + "||" + code
        if ik not in item_acc:
            item_acc[ik] = blank()
            item_meta[ik] = {"group": grp, "code": code,
                             "name": (r.get("master_name") or code)}
        item_acc[ik] = bump(item_acc[ik], lay, r.get("amount"))

    items_by_group = {}
    for ik in item_acc:
        meta = item_meta[ik]
        row = finish(item_acc[ik], meta["code"], meta["name"])
        row["item_code"] = meta["code"]
        g = meta["group"]
        items_by_group[g] = (items_by_group.get(g) or []) + [row]

    by_service = []
    for g in svc:
        kids = sorted(items_by_group.get(g) or [], key=lambda x: x["total"], reverse=True)
        row = finish(svc[g], g, g)
        row["items"] = kids
        by_service = by_service + [row]
    by_service = sorted(by_service, key=lambda x: x["total"], reverse=True)

    flat_items = []
    for ik in item_acc:
        meta = item_meta[ik]
        row = finish(item_acc[ik], meta["code"], meta["name"])
        row["item_code"] = meta["code"]
        row["group"] = meta["group"]
        flat_items = flat_items + [row]
    flat_items = sorted(flat_items, key=lambda x: x["total"], reverse=True)

    # ------------------------------------------------------------ reconcile
    hdr_sum = 0.0
    for r in live_rows:
        hdr_sum = hdr_sum + (r.get("net_total") or 0)
    line_sum = 0.0
    for r in item_rows:
        if layer_of.get(r.get("parent")) in ("approved", "pending", "draft"):
            line_sum = line_sum + (r.get("amount") or 0)
    taxed = 0
    for r in live_rows:
        if (r.get("total_taxes_and_charges") or 0) > 0:
            taxed = taxed + 1

    # ------------------------------------------------------------ table view
    top_so = []
    ranked = sorted(live_rows, key=lambda x: (x.get("net_total") or 0), reverse=True)
    for r in ranked[:25]:
        top_so = top_so + [{
            "name": r.get("name"),
            "date": str(r.get(dfield) or ""),
            "txn_date": str(r.get("transaction_date") or ""),
            "delivery_date": str(r.get("delivery_date") or ""),
            "brand": r.get("ec_brand") or "",
            "team": r.get("ec_team") or "",
            "channel": r.get("ec_channel") or "",
            "customer": r.get("customer") or "",
            "state": r.get("workflow_state") or "",
            "layer": layer_of.get(r.get("name")),
            "net_total": r.get("net_total") or 0,
            "gbs_ref": r.get("ec_gbs_so_ref") or "",
        }]

    # dong chi tiet, dung cho drill-down khi bam vao mot dich vu
    hdr_by_name = {}
    for r in live_rows:
        hdr_by_name[r.get("name")] = r
    lines = []
    for r in item_rows:
        lay = layer_of.get(r.get("parent"))
        if lay not in ("approved", "pending", "draft"):
            continue
        h = hdr_by_name.get(r.get("parent")) or {}
        lines = lines + [{
            "so": r.get("parent"),
            "item_code": (r.get("item_code") or ""),
            "item_name": (r.get("master_name") or r.get("item_code") or ""),
            "group": (r.get("master_group") or "(chua phan nhom)"),
            "amount": r.get("amount") or 0,
            "date": str(h.get(dfield) or ""),
            "txn_date": str(h.get("transaction_date") or ""),
            "delivery_date": str(h.get("delivery_date") or ""),
            "brand": h.get("ec_brand") or "",
            "team": h.get("ec_team") or "",
            "channel": h.get("ec_channel") or "",
            "state": h.get("workflow_state") or "",
            "layer": lay,
        }]
    lines = sorted(lines, key=lambda x: x["amount"], reverse=True)

    brand_opts = sorted([b["key"] for b in by_brand])
    team_opts = sorted([t["key"] for t in by_team])

    frappe.response["message"] = {
        "ok": True,
        "scope": {"user": session_user, "mode": scope_mode,
                  "department": viewer_dept, "team": viewer_team,
                  "can_view_revenue": True,
                  "cost_scope": "all" if scope_mode in ("admin", "management") else viewer_team},
        "meta": {"date_from": date_from, "date_to": date_to,
                 "data_from": dmin, "data_to": dmax,
                 "granularity": granularity, "channel": channel,
                 "date_basis": basis,
                 "date_basis_label": ("Ngay giao" if basis == "delivery"
                                      else "Ngay chung tu"),
                 "brand": f_brand, "team": f_team,
                 "generated_at": str(frappe.utils.now_datetime()),
                 "measure": "net_total (truoc thue)",
                 "confidence": CONFIDENCE,
                 "notes": notes},
        "totals": totals_out,
        "excluded": {"rejected_amount": rejected_amt, "rejected_count": rejected_cnt},
        "series": series,
        "by_brand": by_brand,
        "by_team": by_team,
        "by_channel": by_channel,
        "by_service": by_service,
        "items": flat_items,
        "lines": lines,
        "top_so": top_so,
        "recon": {"header_net_total": hdr_sum, "line_amount": line_sum,
                  "delta": hdr_sum - line_sum, "so_count": len(live_rows),
                  "line_count": len(item_rows), "so_with_tax": taxed},
        "options": {"brands": brand_opts, "teams": team_opts},
    }
