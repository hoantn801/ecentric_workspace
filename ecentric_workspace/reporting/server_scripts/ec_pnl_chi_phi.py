# ============================================================================
# BAN SAO DOI CHIEU - KHONG PHAI CODE CHAY.
#
# Day la ban sao y het cua Server Script `ec_pnl_chi_phi` dang chay tren
# team.ecentric.vn (script_type = API, api_method = 'ec_pnl_chi_phi', module Core).
# Frappe KHONG import file nay; no nam trong repo chi de repo khong bi mu ve logic
# dang chay. Sua that = sua Server Script tren live qua REST roi cap nhat lai file
# nay trong CUNG mot commit. Cu phap tuan theo RestrictedPython (khong import,
# khong dunder, khong tuple-unpack trong vong lap, khong ten bat dau bang gach duoi).
#
# HAI DocType custom di kem (tao truc tiep tren live qua REST, khong co trong repo):
#
# 1) EC Nhan Su Brand  (module Custom, autoname hash, allow_import, title_field employee_name)
#    employee Link Employee (reqd) | employee_name/department fetch tu employee (read_only)
#    brand Link Brand (reqd) | ty_trong Percent (reqd) | tu_thang/den_thang Data 'YYYY-MM'
#    ghi_chu Small Text.  Quyen: System Manager + EC CnB ghi; EC CEO/HOF/Payroll Viewer All doc.
#    Mau import: C:\dev\EC_Nhan_Su_Brand_import_template.xlsx
#
# 2) EC Loai Chi Phi   (module Custom, autoname field:ma, title_field ten, allow_import)
#    ma Data (reqd, unique) | ten Data (reqd) | thu_tu Int | goi_y Small Text | disabled Check
#    nhom Select: Truc tiep khach hang / Van hanh cong ty / Luong & nhan su / Khong tinh vao chi phi
#    tinh_vao_chi_phi Check (bo tick = KHONG cong vao chi phi ky do)
#    can_brand Check (bat = form DNTT hien them o Brand)
#    Quyen: System Manager + EC Finance + EC CnB ghi; role All chi doc (form can doc de do danh muc).
#    27 dong seed 09/09/2026 - Finance them/sua truc tiep, khong can deploy.
# ============================================================================

# ec_pnl_chi_phi - API doc-only cho Dashboard PnL (giai doan 2: CHI PHI & LUONG UOC TINH)
# Server Script, script_type = API, api_method = 'ec_pnl_chi_phi'
#
# CHI DOC. Khong ghi, khong sua bat ky ban ghi nao. Toan bo cau SQL la SELECT.
#
# NGUYEN TAC BAO MAT (theo yeu cau cua Hoan 2026-09-07):
#   - Luong lay ESTIMATE tu ho so nhan su (Employee.ctc + phu cap), KHONG phu thuoc phieu luong.
#     Phieu luong / Additional Salary chi dung lam cot "thuc te (tham khao)" o muc TONG.
#   - API KHONG BAO GIO tra luong cua tung nguoi. Chi tra tong theo thang x phong ban x loai.
#   - Ten nguoi chi xuat hien o kich ban brand (ai bi anh huong) kem % phan bo, khong kem tien.
#   - Nguoi xem pham vi PHONG BAN (manager) chi thay phong ban cua minh; so tien tong hop
#     co it hon K_MIN nguoi thi an di (chong suy ra luong ca nhan).
#
# QUYEN XEM (hep hon quyen xem doanh thu):
#   Toan cong ty  : Administrator / System Manager / EC CEO / EC HOF / EC CnB / EC Payroll Viewer All
#   Theo phong ban: (a) la manager_email cua Department, hoac
#                   (b) co role EC Payroll Viewer Dept -> phong ban cua chinh minh (Employee.department)
#                   Phong 'Management - EC' (luong CEO/HOF/manager) KHONG BAO GIO mo theo pham vi phong ban,
#                   ke ca khi manager dang ngoi trong phong do (quy tac cua Hoan 2026-08-09).
#   Nguoi khac    : tu choi (error = no_permission). Xem doanh thu KHONG dong nghia xem chi phi.
#
# CONG THUC UOC TINH 1 THANG cho 1 nhan su (ti le ngay lam viec trong thang neu vao/nghi giua thang):
#   luong co ban   = Employee.ctc
#   phu cap        = ec_allow_lunch + ec_allow_coffee + ec_allow_computer
#   BH phan cong ty= [min(ctc, 46.800.000) x 20,5% (BHXH 17,5% + BHYT 3%) + min(ctc, 106.200.000) x 1% (BHTN)]
#                    chi khi ec_dong_bhxh = 1. Tran 46,8tr = 20 x luong co so 2,34tr; tran 106,2tr = 20 x luong toi thieu vung I.
#   luong du an    = Additional Salary component 'Luong du an' cua chinh nguoi do: thang HR da nhap thi lay dung so,
#                    thang chua nhap thi lay theo THANG GAN NHAT co du lieu cua nguoi do (danh dau proj_est) -
#                    day la khoan tra hang thang cho ~43/48 nhan su chinh thuc (07/2026: 279tr = 1/4 quy luong),
#                    bo ra thi quy luong thap hon that ~25% (Hoan phat hien 08/09).
#   thuong & khac  = cac Additional Salary Earning khac (KPI, incentive, ho tro...) - CHI thang da nhap, khong keo sang thang khac.
#   tong           = luong co ban + phu cap + BH phan cong ty + luong du an + thuong & khac
#   Chua gom: kinh phi cong doan 2%, chi phi tuyen dung, dao tao.
#
# Params (form_dict, tat ca optional):
#   date_from, date_to : YYYY-MM-DD -> danh sach thang [tu, den]. Mac dinh: 01/01 nam nay -> cuoi thang nay.
#   action             : overview (mac dinh) | scenario
#   brands             : (scenario) danh sach brand, phan cach dau phay, vd LOF-VN,FES-VN
#   debug_as_user      : chi System Manager, de xem thu goc nhin cua nguoi khac

FULL_ROLES = ("System Manager", "EC CEO", "EC HOF", "EC CnB", "EC Payroll Viewer All")
DEPT_ROLE = "EC Payroll Viewer Dept"
MGMT_DEPT = "Management - EC"
DEPT_SUFFIX = " - EC"
K_MIN = 3
BHXH_CAP = 46800000.0
BHTN_CAP = 106200000.0
RATE_CAPPED = 0.205
RATE_BHTN = 0.01
MAX_MONTHS = 24
LIVE_STATUS = ("Approved", "Pending", "Information Required")
PROJ_COMP = "Luong du an"
# Cac form chua co truong loai chi phi thi suy ra tu ban chat form. Chi dat cho hai loai
# CHAC CHAN; con lai de "Chua phan loai" cho Finance gan tay, khong doan bua.
DEFAULT_CAT = {"EC AI Topup Request": "VH_SOFTWARE", "EC Affiliate Bonus Request": "TT_AFF"}
UNCLASSIFIED = "(Chua phan loai)"
GROUP_ORDER = ("Truc tiep khach hang", "Van hanh cong ty", "Luong & nhan su",
               "Khong tinh vao chi phi", UNCLASSIFIED)

notes = []
fd = frappe.form_dict or {}

# ---------------------------------------------------------------- viewer scope
session_user = frappe.session.user or ""


def roles_of(user):
    out = []
    if not user or user == "Guest":
        return out
    rr = frappe.db.sql("""
        SELECT role FROM `tabHas Role` WHERE parent = %s AND parenttype = 'User'
    """, (user,))
    for r in rr:
        out = out + [r[0]]
    return out


def short_dept(d):
    d = d or ""
    if d[-len(DEPT_SUFFIX):] == DEPT_SUFFIX:
        return d[:-len(DEPT_SUFFIX)]
    return d


roles = roles_of(session_user)
is_sysmgr = (session_user == "Administrator") or ("System Manager" in roles)

if is_sysmgr and fd.get("debug_as_user"):
    session_user = fd.get("debug_as_user")
    roles = roles_of(session_user)
    is_sysmgr = (session_user == "Administrator") or ("System Manager" in roles)
    notes = notes + ["Dang xem duoi goc nhin cua " + str(session_user)]

matched_roles = []
for r in roles:
    if r in FULL_ROLES:
        matched_roles = matched_roles + [r]
if session_user == "Administrator":
    matched_roles = matched_roles + ["Administrator"]

scope_mode = ""
scope_depts = []
viewer_dept = ""
if session_user and session_user != "Guest":
    emp_rows = frappe.db.sql("""
        SELECT name, department FROM `tabEmployee`
        WHERE user_id = %s AND status = 'Active' LIMIT 1
    """, (session_user,), as_dict=True)
    if emp_rows:
        viewer_dept = emp_rows[0].get("department") or ""

if matched_roles:
    scope_mode = "all"
elif session_user and session_user != "Guest":
    mg = frappe.db.sql("""
        SELECT name FROM `tabDepartment`
        WHERE manager_email = %s AND ifnull(disabled, 0) = 0 AND ifnull(is_group, 0) = 0
    """, (session_user,))
    for r in mg:
        # Phong Management (luong CEO / HOF / cac manager) KHONG BAO GIO mo theo pham vi phong ban
        if r[0] not in scope_depts and r[0] != MGMT_DEPT:
            scope_depts = scope_depts + [r[0]]
    if DEPT_ROLE in roles and viewer_dept and viewer_dept != MGMT_DEPT and viewer_dept not in scope_depts:
        scope_depts = scope_depts + [viewer_dept]
    if scope_depts:
        scope_mode = "dept"

if not scope_mode:
    frappe.response["message"] = {
        "ok": False,
        "error": "no_permission",
        "message": "Ban khong co quyen xem chi phi / quy luong. Chi CEO, HOF, C&B va quan ly phong ban (pham vi phong minh) moi duoc xem.",
        "scope": {"user": session_user, "mode": "", "departments": []},
    }
else:
    # ------------------------------------------------------------ params
    today = frappe.utils.getdate(frappe.utils.today())
    cur_month = str(today)[:7]
    d_from = None
    d_to = None
    try:
        d_from = frappe.utils.getdate((fd.get("date_from") or "").strip() or (str(today.year) + "-01-01"))
        d_to = frappe.utils.getdate((fd.get("date_to") or "").strip() or str(frappe.utils.get_last_day(today)))
    except Exception:
        notes = notes + ["Ngay loc khong hop le, dung mac dinh"]
    if not d_from:
        d_from = frappe.utils.getdate(str(today.year) + "-01-01")
    if not d_to:
        d_to = frappe.utils.get_last_day(today)
    if d_to < d_from:
        d_to = d_from
    months = []
    mcur = frappe.utils.get_first_day(d_from)
    mend = frappe.utils.get_first_day(d_to)
    while mcur <= mend and len(months) < MAX_MONTHS:
        months = months + [str(mcur)[:7]]
        mcur = frappe.utils.add_months(mcur, 1)
    if mcur <= mend:
        notes = notes + ["Chi tinh toi da " + str(MAX_MONTHS) + " thang, da cat bot cuoi ky"]
    month_kind = {}
    for m in months:
        if m < cur_month:
            month_kind[m] = "past"
        elif m == cur_month:
            month_kind[m] = "current"
        else:
            month_kind[m] = "future"

    action = (fd.get("action") or "overview").strip().lower()
    # cua so thang cho cac bien dong "sap toi": tu dau ky loc toi 12 thang sau cuoi ky
    win_lo = months[0]
    win_hi = str(frappe.utils.add_months(frappe.utils.getdate(months[-1] + "-01"), 12))[:7]

    def in_window(m):
        if not m:
            return True
        return m >= win_lo and m <= win_hi

    def in_scope(dept):
        if scope_mode == "all":
            return True
        return (dept or "") in scope_depts

    def hide_amount(n):
        # pham vi phong ban: an so tien khi it hon K_MIN nguoi
        if scope_mode == "all":
            return False
        return n < K_MIN

    # ------------------------------------------------------------ departments
    dept_rows = frappe.db.sql("""
        SELECT name, department_code FROM `tabDepartment`
        WHERE ifnull(disabled, 0) = 0 AND ifnull(is_group, 0) = 0
        ORDER BY name
    """, as_dict=True)
    depts = []
    for r in dept_rows:
        if in_scope(r.get("name")):
            depts = depts + [{"key": r.get("name"), "short": short_dept(r.get("name")),
                              "code": r.get("department_code") or ""}]
    dept_keys = []
    for d in depts:
        dept_keys = dept_keys + [d["key"]]

    # ------------------------------------------------------------ roster
    emp_all = frappe.db.sql("""
        SELECT name, employee_name, ifnull(department, '') AS department,
               ifnull(employment_type, '') AS employment_type, status,
               date_of_joining, relieving_date,
               ifnull(ctc, 0) AS ctc,
               ifnull(ec_allow_lunch, 0) + ifnull(ec_allow_coffee, 0) + ifnull(ec_allow_computer, 0) AS allow_sum,
               ifnull(ec_dong_bhxh, 0) AS dong_bhxh, ifnull(user_id, '') AS user_id
        FROM `tabEmployee`
        WHERE status IN ('Active', 'Left')
    """, as_dict=True)

    n_inactive = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabEmployee` WHERE status = 'Inactive'
    """)
    n_inactive = n_inactive[0][0] if n_inactive else 0
    if n_inactive:
        notes = notes + [str(n_inactive) + " ho so Inactive khong co ngay nghi viec -> khong dua vao uoc tinh thang nao"]

    # ---- luong du an + thuong theo TUNG NGUOI tu Additional Salary: chi dung noi bo de cong tong,
    #      KHONG bao gio dua ra ngoai theo nguoi.
    add_rows = frappe.db.sql("""
        SELECT employee, salary_component AS comp, ifnull(type, '') AS ctype,
               date_format(payroll_date, '%Y-%m') AS ky, ifnull(amount, 0) AS amt
        FROM `tabAdditional Salary`
        WHERE docstatus = 1 AND ifnull(disabled, 0) = 0
    """, as_dict=True)
    proj_emp = {}
    bonus_emp = {}
    proj_months_all = []
    for r in add_rows:
        if (r.get("ctype") or "") == "Deduction":
            continue
        ek = r.get("employee") or ""
        ky = r.get("ky") or ""
        amt = frappe.utils.flt(r.get("amt"))
        if not ek or not ky:
            continue
        if (r.get("comp") or "") == PROJ_COMP:
            if ek not in proj_emp:
                proj_emp[ek] = {}
            proj_emp[ek][ky] = frappe.utils.flt(proj_emp[ek].get(ky)) + amt
            if ky not in proj_months_all:
                proj_months_all = proj_months_all + [ky]
        else:
            if ek not in bonus_emp:
                bonus_emp[ek] = {}
            bonus_emp[ek][ky] = frappe.utils.flt(bonus_emp[ek].get(ky)) + amt
    proj_months_all = sorted(proj_months_all)
    latest_proj_month = proj_months_all[-1] if proj_months_all else ""

    def proj_for(ek, m):
        # luong du an cua 1 nguoi cho thang m: dung so neu thang do HR da nhap,
        # neu chua thi lay thang gan nhat co du lieu (uu tien thang truoc do) -> carried = 1
        d = proj_emp.get(ek)
        if not d:
            return {"amt": 0.0, "carried": 0}
        if m in d:
            return {"amt": frappe.utils.flt(d.get(m)), "carried": 0}
        keys = sorted(d.keys())
        pick = ""
        for k in keys:
            if k <= m:
                pick = k
        if not pick:
            pick = keys[0]
        return {"amt": frappe.utils.flt(d.get(pick)), "carried": 1}

    def latest_proj(ek):
        d = proj_emp.get(ek)
        if not d:
            return 0.0
        keys = sorted(d.keys())
        return frappe.utils.flt(d.get(keys[-1]))

    def month_cost(e):
        # chi phi 1 thang tron cua 1 nhan su theo cong thuc o dau file (luong du an = thang gan nhat co du lieu)
        ctc = frappe.utils.flt(e.get("ctc"))
        allow = frappe.utils.flt(e.get("allow_sum"))
        bh = 0.0
        if frappe.utils.cint(e.get("dong_bhxh")) and ctc > 0:
            bh = min(ctc, BHXH_CAP) * RATE_CAPPED + min(ctc, BHTN_CAP) * RATE_BHTN
        proj = latest_proj(e.get("name"))
        return {"base": ctc, "allow": allow, "bh": bh, "proj": proj, "fixed": ctc + allow + bh,
                "total": ctc + allow + bh + proj}

    def type_key(t):
        if t == "Full-time":
            return "ft"
        if t == "Intern":
            return "intern"
        if t == "Probation":
            return "prob"
        return "other"

    def blank_month(m):
        return {"month": m, "kind": month_kind.get(m) or "", "headcount": 0, "fte": 0.0,
                "ft": 0, "intern": 0, "prob": 0, "other": 0, "no_ctc": 0,
                "joiners": 0, "leavers": 0,
                "base": 0.0, "allow": 0.0, "bh": 0.0, "fixed": 0.0,
                "proj": 0.0, "proj_est": 0.0, "n_proj": 0, "bonus": 0.0, "total": 0.0}

    def add_month(acc, e, m, frac, at_end, is_join, is_leave):
        mc = month_cost(e)
        acc["fte"] = acc["fte"] + frac
        acc["base"] = acc["base"] + mc["base"] * frac
        acc["allow"] = acc["allow"] + mc["allow"] * frac
        acc["bh"] = acc["bh"] + mc["bh"] * frac
        acc["fixed"] = acc["fixed"] + mc["fixed"] * frac
        pf = proj_for(e.get("name"), m)
        proj_amt = pf["amt"] if not pf["carried"] else pf["amt"] * frac
        acc["proj"] = acc["proj"] + proj_amt
        if pf["carried"]:
            acc["proj_est"] = acc["proj_est"] + proj_amt
        if proj_amt > 0:
            acc["n_proj"] = acc["n_proj"] + 1
        bonus_amt = frappe.utils.flt((bonus_emp.get(e.get("name")) or {}).get(m))
        acc["bonus"] = acc["bonus"] + bonus_amt
        acc["total"] = acc["total"] + mc["fixed"] * frac + proj_amt + bonus_amt
        if at_end:
            acc["headcount"] = acc["headcount"] + 1
            tk = type_key(e.get("employment_type"))
            acc[tk] = acc[tk] + 1
            if frappe.utils.flt(e.get("ctc")) <= 0:
                acc["no_ctc"] = acc["no_ctc"] + 1
        if is_join:
            acc["joiners"] = acc["joiners"] + 1
        if is_leave:
            acc["leavers"] = acc["leavers"] + 1
        return acc

    pay_dept = {}
    pay_company = {}
    for dk in dept_keys:
        pay_dept[dk] = {}
    for m in months:
        pay_company[m] = blank_month(m)
        for dk in dept_keys:
            pay_dept[dk][m] = blank_month(m)

    n_unknown_dept = 0
    for e in emp_all:
        doj = frappe.utils.getdate(e.get("date_of_joining")) if e.get("date_of_joining") else None
        rel = frappe.utils.getdate(e.get("relieving_date")) if e.get("relieving_date") else None
        if not doj:
            continue
        if e.get("status") == "Left" and not rel:
            continue
        dept = e.get("department") or ""
        for m in months:
            ms = frappe.utils.getdate(m + "-01")
            me = frappe.utils.get_last_day(ms)
            nd = me.day
            start = doj if doj > ms else ms
            end = me
            if rel and rel < me:
                end = rel
            if start > end:
                continue
            days = frappe.utils.date_diff(end, start) + 1
            frac = frappe.utils.flt(days) / frappe.utils.flt(nd)
            if frac > 1:
                frac = 1.0
            at_end = (end == me)
            is_join = (doj >= ms and doj <= me)
            is_leave = (rel is not None and rel >= ms and rel <= me)
            pay_company[m] = add_month(pay_company[m], e, m, frac, at_end, is_join, is_leave)
            if dept in pay_dept:
                pay_dept[dept][m] = add_month(pay_dept[dept][m], e, m, frac, at_end, is_join, is_leave)
            elif scope_mode == "all" and dept == "":
                n_unknown_dept = n_unknown_dept + 1
    if n_unknown_dept:
        notes = notes + ["Co nhan su Active chua gan phong ban - chi nam trong tong cong ty"]

    payroll_by_dept = {}
    for dk in dept_keys:
        lst = []
        for m in months:
            lst = lst + [pay_dept[dk][m]]
        payroll_by_dept[dk] = lst
    payroll_company = []
    if scope_mode == "all":
        for m in months:
            payroll_company = payroll_company + [pay_company[m]]

    # ------------------------------------------------------------ headcount hien tai (as of today)
    hc_dept = {}
    hc_company = {"total": 0, "ft": 0, "intern": 0, "prob": 0, "other": 0, "no_ctc": 0, "bhxh": 0}
    for dk in dept_keys:
        hc_dept[dk] = {"dept": dk, "short": short_dept(dk), "total": 0, "ft": 0, "intern": 0,
                       "prob": 0, "other": 0, "no_ctc": 0, "bhxh": 0}
    for e in emp_all:
        if e.get("status") != "Active":
            continue
        rel = frappe.utils.getdate(e.get("relieving_date")) if e.get("relieving_date") else None
        if rel and rel < today:
            continue
        tk = type_key(e.get("employment_type"))
        dept = e.get("department") or ""
        targets = [hc_company]
        if dept in hc_dept:
            targets = targets + [hc_dept[dept]]
        for t in targets:
            t["total"] = t["total"] + 1
            t[tk] = t[tk] + 1
            if frappe.utils.flt(e.get("ctc")) <= 0:
                t["no_ctc"] = t["no_ctc"] + 1
            if frappe.utils.cint(e.get("dong_bhxh")):
                t["bhxh"] = t["bhxh"] + 1
    headcount_by_dept = []
    for dk in dept_keys:
        h = hc_dept[dk]
        h["intern_pct"] = round(100.0 * h["intern"] / h["total"], 1) if h["total"] else 0.0
        h["prob_pct"] = round(100.0 * h["prob"] / h["total"], 1) if h["total"] else 0.0
        headcount_by_dept = headcount_by_dept + [h]
    hc_company["intern_pct"] = round(100.0 * hc_company["intern"] / hc_company["total"], 1) if hc_company["total"] else 0.0
    hc_company["prob_pct"] = round(100.0 * hc_company["prob"] / hc_company["total"], 1) if hc_company["total"] else 0.0

    # ------------------------------------------------------------ khoan bien dong da ghi nhan (Additional Salary, tong)
    var_rows = frappe.db.sql("""
        SELECT date_format(payroll_date, '%Y-%m') AS ky, ifnull(department, '') AS dept,
               salary_component AS comp, COUNT(*) AS n, SUM(ifnull(amount, 0)) AS amt
        FROM `tabAdditional Salary`
        WHERE docstatus = 1
        GROUP BY ky, dept, comp
    """, as_dict=True)
    var_dept = {}
    var_company = {}
    for r in var_rows:
        m = r.get("ky") or ""
        if m not in month_kind:
            continue
        dept = r.get("dept") or ""
        comp = r.get("comp") or "Khac"
        amt = frappe.utils.flt(r.get("amt"))
        n = frappe.utils.cint(r.get("n"))
        for key in ["company", dept]:
            if key == "company":
                if scope_mode != "all":
                    continue
                store = var_company
            else:
                if dept not in pay_dept:
                    continue
                if dept not in var_dept:
                    var_dept[dept] = {}
                store = var_dept[dept]
            if m not in store:
                store[m] = {"month": m, "total": 0.0, "n": 0, "components": {}}
            store[m]["total"] = store[m]["total"] + amt
            store[m]["n"] = store[m]["n"] + n
            store[m]["components"][comp] = frappe.utils.flt(store[m]["components"].get(comp)) + amt

    def store_to_list(store):
        out = []
        for m in sorted(store.keys()):
            out = out + [store[m]]
        return out

    variable_by_dept = {}
    for dk in var_dept:
        variable_by_dept[dk] = store_to_list(var_dept[dk])
    variable_company = store_to_list(var_company) if scope_mode == "all" else []

    # ------------------------------------------------------------ thuc te theo phieu luong (chi tong, tham khao)
    slip_rows = frappe.db.sql("""
        SELECT date_format(start_date, '%Y-%m') AS ky, ifnull(department, '') AS dept,
               COUNT(*) AS n, SUM(ifnull(gross_pay, 0)) AS gross, SUM(CASE WHEN docstatus = 1 THEN 1 ELSE 0 END) AS n_sub
        FROM `tabSalary Slip`
        WHERE docstatus < 2
        GROUP BY ky, dept
    """, as_dict=True)
    act_dept = {}
    act_company = {}
    for r in slip_rows:
        m = r.get("ky") or ""
        if m not in month_kind:
            continue
        dept = r.get("dept") or ""
        row = {"month": m, "n": frappe.utils.cint(r.get("n")), "n_submitted": frappe.utils.cint(r.get("n_sub")),
               "gross": frappe.utils.flt(r.get("gross"))}
        if scope_mode == "all":
            if m not in act_company:
                act_company[m] = {"month": m, "n": 0, "n_submitted": 0, "gross": 0.0}
            act_company[m]["n"] = act_company[m]["n"] + row["n"]
            act_company[m]["n_submitted"] = act_company[m]["n_submitted"] + row["n_submitted"]
            act_company[m]["gross"] = act_company[m]["gross"] + row["gross"]
        if dept in pay_dept:
            if dept not in act_dept:
                act_dept[dept] = {}
            act_dept[dept][m] = row
    actual_by_dept = {}
    for dk in act_dept:
        actual_by_dept[dk] = store_to_list(act_dept[dk])
    actual_company = store_to_list(act_company) if scope_mode == "all" else []

    # ------------------------------------------------------------ chi phi khac tu Approval Center (da duyet / dang cho)
    # Moi loai: (doctype, cot tien, cot ngay quy ky, nhan)
    cost_specs = [
        ("EC Payment Request", "ifnull(d.payment_amount, 0)", "ifnull(d.payment_date, d.creation)", "Payment Request", "ifnull(d.request_title, d.name)"),
        ("EC AI Topup Request", "CASE WHEN ifnull(d.approved_amount, 0) > 0 THEN d.approved_amount ELSE ifnull(d.requested_amount, 0) END",
         "ifnull(d.subscription_start_date, d.creation)", "AI Topup", "ifnull(d.request_title, d.name)"),
        ("EC Purchase Request", "ifnull(d.payment_amount, 0)", "ifnull(d.estimated_purchase_date, d.creation)", "Purchase Request", "ifnull(d.request_title, d.name)"),
        ("EC Special Bonus Request", "ifnull(d.total_bonus, 0)", "d.creation", "Special Bonus", "ifnull(d.request_title, d.name)"),
        ("EC Affiliate Bonus Request", "CASE WHEN ifnull(d.total_amount, 0) > 0 THEN d.total_amount ELSE ifnull(d.budget, 0) END",
         "ifnull(d.service_month, d.creation)", "Affiliate Bonus", "ifnull(d.request_title, d.name)"),
    ]
    # Danh muc loai chi phi (DocType EC Loai Chi Phi, tao 09/09). `tinh_vao_chi_phi = 0`
    # nghia la khoan do KHONG phai chi phi cua ky: luong da tinh o khoi luong, tam ung,
    # chi ho brand, ky quy, tra no goc. Chung van duoc liet ke rieng de doi chieu dong tien.
    cat_map = {}
    if frappe.db.exists("DocType", "EC Loai Chi Phi"):
        cat_rows = frappe.db.sql("""
            SELECT name, ifnull(ten, name) AS ten, ifnull(nhom, '') AS nhom,
                   ifnull(tinh_vao_chi_phi, 1) AS tinh, ifnull(can_brand, 0) AS can_brand
            FROM `tabEC Loai Chi Phi`
        """, as_dict=True)
        for r in cat_rows:
            cat_map[r.get("name")] = {"ten": r.get("ten"), "nhom": r.get("nhom") or UNCLASSIFIED,
                                      "tinh": frappe.utils.cint(r.get("tinh")),
                                      "can_brand": frappe.utils.cint(r.get("can_brand"))}
    # frappe.db.has_column KHONG co trong sandbox Server Script -> hoi thang bang Custom Field.
    cf_rows = frappe.db.sql("""
        SELECT name FROM `tabCustom Field`
        WHERE dt = 'EC Payment Request' AND fieldname = 'ec_loai_chi_phi' LIMIT 1
    """)
    has_cat_field = True if cf_rows else False

    oc_month = {}
    oc_dept = {}
    oc_items = []
    oc_types = []
    oc_group = {}
    oc_cat = {}
    oc_brand = {}
    n_unclassified = 0
    amt_unclassified = 0.0
    amt_skip_payroll = 0.0
    amt_skip_noncost = 0.0
    for spec in cost_specs:
        dt_name = spec[0]
        if not frappe.db.exists("DocType", dt_name):
            continue
        oc_types = oc_types + [spec[3]]
        cat_cols = ", '' AS cat, '' AS brand"
        if dt_name == "EC Payment Request" and has_cat_field:
            cat_cols = ", ifnull(d.ec_loai_chi_phi, '') AS cat, ifnull(d.ec_brand, '') AS brand"
        crow = frappe.db.sql("""
            SELECT d.name AS name, """ + spec[4] + """ AS title, ifnull(d.department, '') AS dept,
                   """ + spec[1] + """ AS amt, date_format(""" + spec[2] + """, '%Y-%m') AS ky,
                   ifnull(a.approval_status, '') AS st""" + cat_cols + """
            FROM `tab""" + dt_name + """` d
            LEFT JOIN `tabEC Approval Request` a ON a.name = d.approval_request
            WHERE d.docstatus < 2
        """, as_dict=True)
        for r in crow:
            st = r.get("st") or ""
            if st not in LIVE_STATUS:
                continue
            m = r.get("ky") or ""
            if m not in month_kind:
                continue
            dept = r.get("dept") or ""
            if not in_scope(dept):
                continue
            amt = frappe.utils.flt(r.get("amt"))
            bucket = "approved" if st == "Approved" else "pending"
            code = (r.get("cat") or "").strip() or DEFAULT_CAT.get(dt_name) or ""
            info = cat_map.get(code)
            cat_ten = info["ten"] if info else UNCLASSIFIED
            cat_nhom = info["nhom"] if info else UNCLASSIFIED
            counts = 1 if (info is None or info["tinh"]) else 0
            if info is None:
                n_unclassified = n_unclassified + 1
                if st == "Approved":
                    amt_unclassified = amt_unclassified + amt
            elif not info["tinh"] and st == "Approved":
                if cat_nhom == "Luong & nhan su":
                    amt_skip_payroll = amt_skip_payroll + amt
                else:
                    amt_skip_noncost = amt_skip_noncost + amt
            gkey = cat_nhom
            if gkey not in oc_group:
                oc_group[gkey] = {"group": gkey, "approved": 0.0, "pending": 0.0, "n": 0,
                                  "counts": counts}
            oc_group[gkey]["approved"] = oc_group[gkey]["approved"] + (amt if st == "Approved" else 0)
            oc_group[gkey]["pending"] = oc_group[gkey]["pending"] + (0 if st == "Approved" else amt)
            oc_group[gkey]["n"] = oc_group[gkey]["n"] + 1
            ckey = cat_ten
            if ckey not in oc_cat:
                oc_cat[ckey] = {"category": ckey, "code": code, "group": cat_nhom,
                                "counts": counts, "approved": 0.0, "pending": 0.0, "n": 0}
            oc_cat[ckey]["approved"] = oc_cat[ckey]["approved"] + (amt if st == "Approved" else 0)
            oc_cat[ckey]["pending"] = oc_cat[ckey]["pending"] + (0 if st == "Approved" else amt)
            oc_cat[ckey]["n"] = oc_cat[ckey]["n"] + 1
            bname = (r.get("brand") or "").strip()
            if bname and counts:
                if bname not in oc_brand:
                    oc_brand[bname] = {"brand": bname, "approved": 0.0, "pending": 0.0, "n": 0}
                oc_brand[bname]["approved"] = oc_brand[bname]["approved"] + (amt if st == "Approved" else 0)
                oc_brand[bname]["pending"] = oc_brand[bname]["pending"] + (0 if st == "Approved" else amt)
                oc_brand[bname]["n"] = oc_brand[bname]["n"] + 1
            if not counts:
                # Khoan khong phai chi phi cua ky: van giu trong `items` de doi chieu dong tien,
                # nhung KHONG cong vao tong thang / tong phong ban.
                oc_items = oc_items + [{"name": r.get("name"), "doctype": dt_name, "type": spec[3],
                                        "title": r.get("title") or r.get("name"), "dept": dept,
                                        "short": short_dept(dept), "month": m, "amount": amt,
                                        "status": st, "category": cat_ten, "group": cat_nhom,
                                        "brand": bname, "counts": 0}]
                continue
            if m not in oc_month:
                oc_month[m] = {"month": m, "approved": 0.0, "pending": 0.0, "n_approved": 0, "n_pending": 0, "types": {}}
            oc_month[m][bucket] = oc_month[m][bucket] + amt
            oc_month[m]["n_" + bucket] = oc_month[m]["n_" + bucket] + 1
            tkey = spec[3]
            if tkey not in oc_month[m]["types"]:
                oc_month[m]["types"][tkey] = {"approved": 0.0, "pending": 0.0}
            oc_month[m]["types"][tkey][bucket] = oc_month[m]["types"][tkey][bucket] + amt
            if dept not in oc_dept:
                oc_dept[dept] = {"dept": dept, "short": short_dept(dept), "approved": 0.0, "pending": 0.0, "n": 0}
            oc_dept[dept][bucket] = oc_dept[dept][bucket] + amt
            oc_dept[dept]["n"] = oc_dept[dept]["n"] + 1
            oc_items = oc_items + [{"name": r.get("name"), "doctype": dt_name, "type": tkey,
                                    "title": r.get("title") or r.get("name"), "dept": dept,
                                    "short": short_dept(dept), "month": m, "amount": amt,
                                    "status": st, "category": cat_ten, "group": cat_nhom,
                                    "brand": bname, "counts": 1}]
    group_list = []
    for g in GROUP_ORDER:
        if g in oc_group:
            group_list = group_list + [oc_group[g]]
    for g in oc_group:
        if g not in GROUP_ORDER:
            group_list = group_list + [oc_group[g]]
    other_costs = {
        "types": oc_types,
        "by_month": store_to_list(oc_month),
        "by_dept": sorted(list(oc_dept.values()), key=lambda x: x["approved"], reverse=True),
        "by_group": group_list,
        "by_category": sorted(list(oc_cat.values()), key=lambda x: x["approved"], reverse=True),
        "by_brand": sorted(list(oc_brand.values()), key=lambda x: x["approved"], reverse=True),
        "items": sorted(oc_items, key=lambda x: x["month"], reverse=True)[:200],
        "unclassified": {"n": n_unclassified, "amount": amt_unclassified,
                         "has_field": True if has_cat_field else False,
                         "n_categories": len(cat_map)},
        "excluded": {"payroll": amt_skip_payroll, "noncost": amt_skip_noncost},
        "note": "Chi gom yeu cau co trang thai Approved (da duyet) hoac Pending / Information Required (dang cho). Rejected / Cancelled bi loai. Thang quy ky: Payment Request = payment_date, AI Topup = subscription_start_date, Purchase = estimated_purchase_date, Affiliate = service_month, Special Bonus = ngay tao. Khoan thuoc nhom 'Luong & nhan su' da co trong khoi luong va nhom 'Khong tinh vao chi phi' (tam ung, chi ho brand, ky quy, tra no goc) KHONG duoc cong vao tong - chung nam rieng o `excluded`.",
    }

    # ------------------------------------------------------------ tuyen dung / bien dong nhan su sap toi (Approval Center + HRMS)
    hiring_items = []
    hiring_dept = {}
    if frappe.db.exists("DocType", "EC Hiring Request"):
        hr_rows = frappe.db.sql("""
            SELECT d.name, d.request_title, ifnull(d.department, '') AS dept, d.position,
                   ifnull(d.number_of_vacancy, 0) AS n, ifnull(d.employment_type, '') AS etype,
                   ifnull(d.suggested_salary, 0) AS sal, ifnull(a.approval_status, '') AS st,
                   date_format(ifnull(d.submitted_at, d.creation), '%Y-%m') AS ky
            FROM `tabEC Hiring Request` d
            LEFT JOIN `tabEC Approval Request` a ON a.name = d.approval_request
            WHERE d.docstatus < 2
        """, as_dict=True)
        for r in hr_rows:
            st = r.get("st") or ""
            if st not in LIVE_STATUS:
                continue
            dept = r.get("dept") or ""
            if not in_scope(dept):
                continue
            n = frappe.utils.cint(r.get("n")) or 1
            hiring_items = hiring_items + [{"name": r.get("name"), "title": r.get("request_title") or r.get("name"),
                                            "dept": dept, "short": short_dept(dept), "position": r.get("position") or "",
                                            "n": n, "type": r.get("etype") or "", "status": st, "month": r.get("ky") or ""}]
            if dept not in hiring_dept:
                hiring_dept[dept] = {"dept": dept, "short": short_dept(dept), "n_approved": 0, "n_pending": 0,
                                     "cost_approved": 0.0, "cost_pending": 0.0, "requests": 0}
            hd = hiring_dept[dept]
            hd["requests"] = hd["requests"] + 1
            if st == "Approved":
                hd["n_approved"] = hd["n_approved"] + n
                hd["cost_approved"] = hd["cost_approved"] + frappe.utils.flt(r.get("sal")) * n
            else:
                hd["n_pending"] = hd["n_pending"] + n
                hd["cost_pending"] = hd["cost_pending"] + frappe.utils.flt(r.get("sal")) * n

    resign_dept = {}
    if frappe.db.exists("DocType", "EC Resignation Request"):
        rs_rows = frappe.db.sql("""
            SELECT ifnull(d.department, '') AS dept, d.last_working_day AS lwd, ifnull(a.approval_status, '') AS st,
                   ifnull(e.ctc, 0) AS ctc
            FROM `tabEC Resignation Request` d
            LEFT JOIN `tabEC Approval Request` a ON a.name = d.approval_request
            LEFT JOIN `tabEmployee` e ON e.name = d.employee
            WHERE d.docstatus < 2
        """, as_dict=True)
        for r in rs_rows:
            st = r.get("st") or ""
            if st not in LIVE_STATUS:
                continue
            dept = r.get("dept") or ""
            if not in_scope(dept):
                continue
            m = str(r.get("lwd") or "")[:7]
            if not in_window(m):
                continue
            key = dept + "|" + m
            if key not in resign_dept:
                resign_dept[key] = {"dept": dept, "short": short_dept(dept), "month": m, "n": 0, "n_pending": 0, "ctc_sum": 0.0}
            if st == "Approved":
                resign_dept[key]["n"] = resign_dept[key]["n"] + 1
            else:
                resign_dept[key]["n_pending"] = resign_dept[key]["n_pending"] + 1
            resign_dept[key]["ctc_sum"] = resign_dept[key]["ctc_sum"] + frappe.utils.flt(r.get("ctc"))
    resignations = []
    for key in sorted(resign_dept.keys()):
        row = resign_dept[key]
        if hide_amount(row["n"] + row["n_pending"]):
            row["ctc_sum"] = None
            row["amount_hidden"] = True
        resignations = resignations + [row]

    promo_dept = {}
    if frappe.db.exists("DocType", "EC Promotion Request"):
        pm_rows = frappe.db.sql("""
            SELECT ifnull(d.department, '') AS dept, d.effective_date_of_promotion AS eff,
                   ifnull(d.proposed_salary, 0) - ifnull(d.current_salary, 0) AS delta,
                   ifnull(a.approval_status, '') AS st
            FROM `tabEC Promotion Request` d
            LEFT JOIN `tabEC Approval Request` a ON a.name = d.approval_request
            WHERE d.docstatus < 2
        """, as_dict=True)
        for r in pm_rows:
            st = r.get("st") or ""
            if st not in LIVE_STATUS:
                continue
            dept = r.get("dept") or ""
            if not in_scope(dept):
                continue
            m = str(r.get("eff") or "")[:7]
            if not in_window(m):
                continue
            key = dept + "|" + m
            if key not in promo_dept:
                promo_dept[key] = {"dept": dept, "short": short_dept(dept), "month": m, "n": 0, "n_pending": 0, "delta_month": 0.0}
            if st == "Approved":
                promo_dept[key]["n"] = promo_dept[key]["n"] + 1
            else:
                promo_dept[key]["n_pending"] = promo_dept[key]["n_pending"] + 1
            promo_dept[key]["delta_month"] = promo_dept[key]["delta_month"] + frappe.utils.flt(r.get("delta"))
    promotions = []
    for key in sorted(promo_dept.keys()):
        row = promo_dept[key]
        if hide_amount(row["n"] + row["n_pending"]):
            row["delta_month"] = None
            row["amount_hidden"] = True
        promotions = promotions + [row]

    moves = []
    if frappe.db.exists("DocType", "EC Lateral Move Request"):
        mv_rows = frappe.db.sql("""
            SELECT ifnull(d.department, '') AS dept, ifnull(d.new_department, '') AS new_dept,
                   d.start_date AS sd, ifnull(a.approval_status, '') AS st
            FROM `tabEC Lateral Move Request` d
            LEFT JOIN `tabEC Approval Request` a ON a.name = d.approval_request
            WHERE d.docstatus < 2
        """, as_dict=True)
        mv_acc = {}
        for r in mv_rows:
            st = r.get("st") or ""
            if st not in LIVE_STATUS:
                continue
            dept = r.get("dept") or ""
            ndept = r.get("new_dept") or ""
            if not (in_scope(dept) or in_scope(ndept)):
                continue
            m = str(r.get("sd") or "")[:7]
            if not in_window(m):
                continue
            key = dept + "|" + ndept + "|" + m + "|" + st
            if key not in mv_acc:
                mv_acc[key] = {"from": dept, "from_short": short_dept(dept), "to": ndept, "to_short": short_dept(ndept),
                               "month": m, "status": st, "n": 0}
            mv_acc[key]["n"] = mv_acc[key]["n"] + 1
        for key in sorted(mv_acc.keys()):
            moves = moves + [mv_acc[key]]

    staffing = []
    sp_rows = frappe.db.sql("""
        SELECT p.name, ifnull(p.department, '') AS dept, p.from_date, p.to_date, ifnull(p.total_estimated_budget, 0) AS budget,
               c.designation, ifnull(c.vacancies, 0) AS vacancies, ifnull(c.number_of_positions, 0) AS positions,
               ifnull(c.current_count, 0) AS current_count, ifnull(c.total_estimated_cost, 0) AS est_cost
        FROM `tabStaffing Plan` p
        LEFT JOIN `tabStaffing Plan Detail` c ON c.parent = p.name
        WHERE p.docstatus < 2
    """, as_dict=True)
    for r in sp_rows:
        dept = r.get("dept") or ""
        if not in_scope(dept):
            continue
        staffing = staffing + [{"name": r.get("name"), "dept": dept, "short": short_dept(dept),
                                "from": str(r.get("from_date") or ""), "to": str(r.get("to_date") or ""),
                                "designation": r.get("designation") or "", "vacancies": frappe.utils.cint(r.get("vacancies")),
                                "positions": frappe.utils.cint(r.get("positions")), "current_count": frappe.utils.cint(r.get("current_count")),
                                "est_cost": frappe.utils.flt(r.get("est_cost")), "budget": frappe.utils.flt(r.get("budget"))}]

    openings = []
    jo_rows = frappe.db.sql("""
        SELECT name, job_title, ifnull(department, '') AS dept, ifnull(designation, '') AS designation,
               ifnull(status, '') AS status, ifnull(planned_vacancies, 0) AS planned, ifnull(vacancies, 0) AS vacancies,
               ifnull(employment_type, '') AS etype, closes_on
        FROM `tabJob Opening`
    """, as_dict=True)
    ja_rows = frappe.db.sql("""
        SELECT ifnull(job_title, '') AS opening, ifnull(status, '') AS status, COUNT(*) AS n
        FROM `tabJob Applicant`
        GROUP BY opening, status
    """, as_dict=True)
    ja_map = {}
    for r in ja_rows:
        op = r.get("opening") or ""
        if op not in ja_map:
            ja_map[op] = {}
        ja_map[op][r.get("status") or "?"] = frappe.utils.cint(r.get("n"))
    for r in jo_rows:
        dept = r.get("dept") or ""
        if not in_scope(dept):
            continue
        apps = ja_map.get(r.get("name")) or {}
        n_apps = 0
        for k in apps:
            n_apps = n_apps + apps[k]
        n_acc = frappe.utils.cint(apps.get("Accepted"))
        openings = openings + [{"name": r.get("name"), "title": r.get("job_title") or r.get("name"), "dept": dept,
                                "short": short_dept(dept), "designation": r.get("designation") or "",
                                "status": r.get("status") or "", "planned": frappe.utils.cint(r.get("planned")),
                                "vacancies": frappe.utils.cint(r.get("vacancies")), "type": r.get("etype") or "",
                                "closes_on": str(r.get("closes_on") or ""), "applicants": apps, "n_applicants": n_apps,
                                "accepted": n_acc,
                                "conv_pct": round(100.0 * n_acc / n_apps, 1) if n_apps else None}]

    hiring = {
        "requests": sorted(hiring_items, key=lambda x: x["month"], reverse=True),
        "by_dept": sorted(list(hiring_dept.values()), key=lambda x: x["n_approved"] + x["n_pending"], reverse=True),
        "resignations": resignations,
        "promotions": promotions,
        "moves": moves,
        "staffing_plan": staffing,
        "job_openings": openings,
        "window": {"from": win_lo, "to": win_hi},
        "note": "Nguon: EC Hiring Request (vi tri xin tuyen), EC Resignation Request (nghi viec), EC Promotion Request (tang luong / thang chuc), EC Lateral Move Request (chuyen phong), Staffing Plan + Job Opening/Applicant cua HRMS. Chi tinh yeu cau Approved hoac dang cho, co ngay hieu luc trong cua so tu dau ky loc toi 12 thang sau cuoi ky.",
    }

    # ------------------------------------------------------------ phan bo brand tung nguoi (EC Nhan Su Brand) + kich ban
    has_alloc = True if frappe.db.exists("DocType", "EC Nhan Su Brand") else False
    alloc_rows = []
    if has_alloc:
        alloc_rows = frappe.db.sql("""
            SELECT employee, ifnull(brand, '') AS brand, ifnull(ty_trong, 0) AS pct,
                   ifnull(tu_thang, '') AS tu_thang, ifnull(den_thang, '') AS den_thang
            FROM `tabEC Nhan Su Brand`
            WHERE ifnull(brand, '') <> '' AND ifnull(ty_trong, 0) > 0
        """, as_dict=True)
    emp_map = {}
    for e in emp_all:
        if e.get("status") == "Active":
            emp_map[e.get("name")] = e

    # alloc theo nguoi: chi lay dong dang hieu luc cho THANG HIEN TAI
    alloc_by_emp = {}
    for r in alloc_rows:
        tm = (r.get("tu_thang") or "")[:7]
        dm = (r.get("den_thang") or "")[:7]
        if tm and tm > cur_month:
            continue
        if dm and dm < cur_month:
            continue
        ek = r.get("employee")
        if ek not in emp_map:
            continue
        if ek not in alloc_by_emp:
            alloc_by_emp[ek] = {}
        b = r.get("brand")
        alloc_by_emp[ek][b] = frappe.utils.flt(alloc_by_emp[ek].get(b)) + frappe.utils.flt(r.get("pct"))

    brand_acc = {}
    n_over = 0
    for ek in alloc_by_emp:
        e = emp_map[ek]
        dept = e.get("department") or ""
        tot_pct = 0.0
        for b in alloc_by_emp[ek]:
            tot_pct = tot_pct + alloc_by_emp[ek][b]
        if tot_pct > 100.5:
            n_over = n_over + 1
        if not in_scope(dept):
            continue
        mc = month_cost(e)
        for b in alloc_by_emp[ek]:
            pct = alloc_by_emp[ek][b]
            if b not in brand_acc:
                brand_acc[b] = {"brand": b, "n": 0, "fte": 0.0, "cost_month": 0.0, "depts": {}}
            brand_acc[b]["n"] = brand_acc[b]["n"] + 1
            brand_acc[b]["fte"] = brand_acc[b]["fte"] + pct / 100.0
            brand_acc[b]["cost_month"] = brand_acc[b]["cost_month"] + mc["total"] * pct / 100.0
            brand_acc[b]["depts"][short_dept(dept)] = frappe.utils.cint(brand_acc[b]["depts"].get(short_dept(dept))) + 1
    if n_over:
        notes = notes + [str(n_over) + " nhan su co tong ty trong brand > 100% - can HR sua lai"]
    brand_list = []
    for b in brand_acc:
        row = brand_acc[b]
        row["fte"] = round(row["fte"], 2)
        if hide_amount(row["n"]):
            row["cost_month"] = None
            row["amount_hidden"] = True
        brand_list = brand_list + [row]
    brand_list = sorted(brand_list, key=lambda x: x["fte"], reverse=True)

    n_alloc_scope = 0
    n_active_scope = 0
    for ek in emp_map:
        if in_scope(emp_map[ek].get("department") or ""):
            n_active_scope = n_active_scope + 1
            if ek in alloc_by_emp:
                n_alloc_scope = n_alloc_scope + 1

    # goi y nguoi <-> brand tu du lieu co san (chi doc): MSO.kam, EC Marketplace Shop.kam_owner
    hints = []
    if frappe.db.exists("DocType", "MSO"):
        mso_rows = frappe.db.sql("""
            SELECT ifnull(kam, '') AS kam, ifnull(brand, '') AS brand, COUNT(*) AS n
            FROM `tabMSO` WHERE ifnull(kam, '') <> '' AND ifnull(brand, '') <> ''
            GROUP BY kam, brand
        """, as_dict=True)
        for r in mso_rows:
            hints = hints + [{"user": r.get("kam"), "brand": r.get("brand"), "source": "MSO.kam", "n": frappe.utils.cint(r.get("n"))}]
    if frappe.db.exists("DocType", "EC Marketplace Shop"):
        shop_rows = frappe.db.sql("""
            SELECT ifnull(kam_owner, '') AS kam, ifnull(brand, '') AS brand, COUNT(*) AS n
            FROM `tabEC Marketplace Shop` WHERE ifnull(kam_owner, '') <> '' AND ifnull(brand, '') <> ''
            GROUP BY kam, brand
        """, as_dict=True)
        for r in shop_rows:
            hints = hints + [{"user": r.get("kam"), "brand": r.get("brand"), "source": "Marketplace Shop.kam_owner", "n": frappe.utils.cint(r.get("n"))}]
    user_name = {}
    for e in emp_all:
        if e.get("user_id"):
            user_name[e.get("user_id")] = {"name": e.get("employee_name"), "dept": e.get("department") or ""}
    hint_out = []
    for h in hints:
        un = user_name.get(h["user"]) or {}
        if not in_scope(un.get("dept") or ""):
            continue
        h["employee_name"] = un.get("name") or h["user"]
        h["short"] = short_dept(un.get("dept") or "")
        hint_out = hint_out + [h]

    brand_opts = []
    bo_rows = frappe.db.sql("""
        SELECT ifnull(ec_brand, '') AS b, COUNT(*) AS n FROM `tabSales Order`
        WHERE docstatus < 2 AND ifnull(workflow_state, '') <> 'Rejected' AND ifnull(ec_brand, '') <> ''
        GROUP BY b ORDER BY n DESC
    """, as_dict=True)
    for r in bo_rows:
        brand_opts = brand_opts + [r.get("b")]
    for b in brand_acc:
        if b not in brand_opts:
            brand_opts = brand_opts + [b]

    brands = {
        "has_table": has_alloc,
        "coverage": {"allocated": n_alloc_scope, "active": n_active_scope},
        "list": brand_list,
        "hints": hint_out,
        "options": brand_opts,
        "note": "Ty trong theo brand cua tung nguoi lay tu DocType 'EC Nhan Su Brand' (HR nhap / import). Chi phi theo brand = tong (chi phi thang uoc tinh x ty trong). Khi chua khai bao thi kich ban chi co phan doanh thu.",
    }

    # ------------------------------------------------------------ kich ban ngung brand
    scenario = None
    if action == "scenario":
        sel = []
        for b in (fd.get("brands") or "").split(","):
            b = b.strip()
            if b and b not in sel:
                sel = sel + [b]
        people = []
        sc_dept = {}
        n_all = 0
        fte_all = 0.0
        cost_all = 0.0
        for ek in alloc_by_emp:
            e = emp_map[ek]
            dept = e.get("department") or ""
            if not in_scope(dept):
                continue
            pct_sel = 0.0
            pct_other = 0.0
            hit = []
            for b in alloc_by_emp[ek]:
                if b in sel:
                    pct_sel = pct_sel + alloc_by_emp[ek][b]
                    hit = hit + [b + " " + str(int(round(alloc_by_emp[ek][b]))) + "%"]
                else:
                    pct_other = pct_other + alloc_by_emp[ek][b]
            if pct_sel <= 0:
                continue
            mc = month_cost(e)
            n_all = n_all + 1
            fte_all = fte_all + pct_sel / 100.0
            cost_all = cost_all + mc["total"] * pct_sel / 100.0
            people = people + [{"employee_name": e.get("employee_name"), "dept": dept, "short": short_dept(dept),
                                "type": e.get("employment_type") or "", "pct_selected": round(pct_sel, 1),
                                "pct_other": round(pct_other, 1), "brands": hit}]
            if dept not in sc_dept:
                sc_dept[dept] = {"dept": dept, "short": short_dept(dept), "n": 0, "fte": 0.0, "cost_month": 0.0}
            sc_dept[dept]["n"] = sc_dept[dept]["n"] + 1
            sc_dept[dept]["fte"] = sc_dept[dept]["fte"] + pct_sel / 100.0
            sc_dept[dept]["cost_month"] = sc_dept[dept]["cost_month"] + mc["total"] * pct_sel / 100.0
        by_dept = []
        for dk in sorted(sc_dept.keys()):
            row = sc_dept[dk]
            row["fte"] = round(row["fte"], 2)
            if hide_amount(row["n"]):
                row["cost_month"] = None
                row["amount_hidden"] = True
            by_dept = by_dept + [row]
        hidden_all = hide_amount(n_all)
        scenario = {
            "brands": sel,
            "people": sorted(people, key=lambda x: x["pct_selected"], reverse=True),
            "n": n_all,
            "fte": round(fte_all, 2),
            "cost_month": None if hidden_all else cost_all,
            "amount_hidden": hidden_all,
            "by_dept": by_dept,
            "note": "Nguoi anh huong = co ty trong > 0 o brand da chon (hieu luc thang hien tai). Chi phi/thang = tong (chi phi thang uoc tinh, gom luong du an thang gan nhat, x ty trong da chon). Doanh thu mat lay tu API doanh thu (by_brand) tren cung khoang ngay.",
        }

    # ------------------------------------------------------------ dau ra
    payload = {
        "ok": True,
        "scope": {
            "user": session_user,
            "mode": scope_mode,
            "departments": dept_keys,
            "roles": matched_roles,
            "can_view_company": scope_mode == "all",
            "k_min": K_MIN,
        },
        "params": {"date_from": str(d_from), "date_to": str(d_to), "months": months,
                   "month_kind": month_kind, "current_month": cur_month, "action": action},
        "depts": depts,
        "payroll": {"by_dept": payroll_by_dept, "company": payroll_company,
                    "proj_months": proj_months_all, "proj_latest_month": latest_proj_month,
                    "note": "total = base + allow + bh (fixed) + proj (luong du an: dung so o thang HR da nhap, thang khac lay theo thang gan nhat co du lieu cua tung nguoi -> phan do nam trong proj_est) + bonus (thuong & khac, chi thang da nhap)"},
        "variable": {"by_dept": variable_by_dept, "company": variable_company,
                     "note": "Khoan bien dong da ghi nhan qua Additional Salary (luong du an, thuong KPI, incentive, ho tro khac). Chi co o thang HR da nhap."},
        "actual": {"by_dept": actual_by_dept, "company": actual_company,
                   "note": "Tong gross theo phieu luong (docstatus < 2) - chi de tham khao / doi chieu, khong dung de tinh."},
        "headcount": {"as_of": str(today), "by_dept": headcount_by_dept,
                      "company": hc_company if scope_mode == "all" else None},
        "other_costs": other_costs,
        "hiring": hiring,
        "brands": brands,
        "scenario": scenario,
        "meta": {
            "notes": notes,
            "formula": "tong/thang = ctc + (phu cap com + ca phe + may tinh) + BH cong ty [min(ctc,46,8tr) x 20,5% + min(ctc,106,2tr) x 1%, chi khi dong BHXH] + luong du an (Additional Salary, thang gan nhat co du lieu) + thuong & khac (chi thang da nhap); nhan ti le ngay lam viec trong thang neu vao/nghi giua thang",
            "generated_at": str(frappe.utils.now_datetime()),
        },
    }
    frappe.response["message"] = payload
