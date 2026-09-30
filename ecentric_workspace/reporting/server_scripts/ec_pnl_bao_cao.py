# ============================================================================
# BAN SAO DOI CHIEU - KHONG PHAI CODE CHAY.
#
# Day la ban sao y het cua Server Script `ec_pnl_bao_cao` dang chay tren
# team.ecentric.vn (script_type = API, api_method = 'ec_pnl_bao_cao').
# Frappe KHONG import file nay; no nam trong repo chi de repo khong bi mu ve logic
# dang chay. Sua that = sua Server Script tren live qua REST roi cap nhat lai file
# nay trong CUNG mot commit. Cu phap tuan theo RestrictedPython (khong import,
# khong dunder, khong tuple-unpack trong vong lap, khong ten bat dau bang gach duoi).
#
# Nguon so cho /pnl-dashboard (5 tab, 29/09/2026): doanh thu theo brand x nhom dich vu,
# gia von / chi phi van hanh theo nhom, luong theo chuc danh / phong ban / khach hang me
# (EC PnL Luong Lich Su, khong co ten nguoi), chi phi cho duyet, dong tien.
# Quyen: xem = FULL_ROLES hoac quyen doanh thu; chi phi (cost) chi FULL_ROLES, nguoc lai cost = null.
#
# DocType custom di kem (tao truc tiep tren live qua REST, khong co trong repo):
#   EC Dong Tien Nhap Tay: thang Date | loai Select (So du dau nam / Thu tu khach hang /
#   Thu ho brand (chi ho hoan lai) / Thu khac (lai tien gui, hoan coc...)) | so_tien Currency |
#   khach_hang_me Link Customer | ghi_chu. Quyen: System Manager + EC Finance ghi; FULL_ROLES doc.
# ============================================================================
# ec_pnl_bao_cao - API doc-only cho tab moi cua Dashboard PnL (29/09/2026, Hoan duyet thiet ke)
# Server Script, script_type = API, api_method = 'ec_pnl_bao_cao'
#
# CHI DOC. Moi cau SQL la SELECT. Tra ve MA TRAN THANG cho ca nam de trang tu cong theo
# pham vi (toan cong ty / khach hang me / sub-brand) ma khong phai goi lai:
#   rev[brand][nhom][12]        doanh thu (Sales Order so EC + so P&L lich su), CHUA gom phi van hanh
#                               gian hang tinh tu NMV (trang lay tu ec_pnl_phi_ql cho thang > HIST_END)
#   cogs[nhom][12], opex[nhom][12]   gia von / chi phi van hanh toan cong ty
#   luong_kh[khach hang me][12], fte_kh[...]   luong nhan su dich vu theo khach hang me
#   tt_kh[khach hang me][12]    chi phi thue ngoai truc tiep (DNTT loai TT_*) co gan brand
#   so_gv_kh / so_cp_kh         gia von / chi phi van hanh theo brand trong SO P&L (thang <= HIST_CUT)
#   dept                        so nguoi / luong / chi phi hoat dong theo phong ban ERP
#   cash                        tien chi theo ngay UNC, tien thu + so du dau ky do Finance nhap
#
# QUYEN:
#   Xem (doanh thu): System Manager | EC Viewer Permission scope=all | phong Management - EC |
#                    role EC CEO / EC HOF / EC CnB / EC Payroll Viewer All.
#   Chi phi + luong (moi so chi phi): CHI System Manager + 4 role tren (giong ec_pnl_chi_phi, pham vi 'all').
#   Nguoi chi xem duoc doanh thu: cac khoi chi phi tra ve null.
#   Luong chi tiet theo chuc danh / phong ban: cung nhom tren. KHONG co ten nhan su o bat ky dau.
#
# Params: year (YYYY, mac dinh nam hien tai), debug_as_user (chi System Manager).

HIST_CUT = "2026-08"
HIST_END = "2026-08-31"
LUONG_DOT = "LUONG_PB_V2_20260929"
MGMT_DEPT = "Management - EC"
FULL_ROLES = ("System Manager", "EC CEO", "EC HOF", "EC CnB", "EC Payroll Viewer All")
LIVE_STATUS = ("Approved", "Pending", "Information Required")
CTY_KEY = "(chi phí chung)"
KHAC_KH = "(khác)"

REV_GROUPS = ["STORE", "KOL", "LIVE", "VIDEO", "MEDIA", "FFM", "QL", "GBS", "KHAC"]
COGS_GROUPS = ["C_LUONG", "C_KOL", "C_LIVE", "C_VIDEO", "C_MEDIA", "C_FFM", "C_KHAC"]
OPEX_GROUPS = ["O_NS", "O_NSK", "O_VP", "O_TOOL", "O_HR", "O_EVENT", "O_PRO", "O_KHAC", "O_SO"]

ITEM_GRP = {
    "REV_KOL_CMS": "KOL", "REV_KOL_MGMT": "KOL", "REV_TAP_MCN": "KOL", "REV_MKT_AFFILIATE": "KOL",
    "REV_MKT_BOOKING": "KOL", "GBS_MKT_ECBOOKING": "KOL", "GBS_PVH_VHTTLK": "KOL", "GBS_PVH_KOL": "KOL",
    "REV_MKT_DAYLYLIVE": "LIVE", "REV_MKT_LIVESTREAM": "LIVE", "GBS_MKT_LIVESTREAM": "LIVE",
    "REV_MKT_SHORTVIDEO": "VIDEO", "GBS_MKT_VIDEO": "VIDEO", "GBS_MKT_THIETKE": "VIDEO",
    "REV_MKT_MEDIA": "MEDIA", "GBS_PVH_FBADS_VH": "MEDIA", "GBS_PVH_VHPAIDADS": "MEDIA",
    "REV_FFM_FEE": "FFM", "GBS_PVC": "FFM", "GBS_BM_PVH": "FFM",
    "REV_QL_TT": "QL", "REV_MKT_PACKAGES": "QL", "GBS_PVH_EC_VHGH": "QL", "GBS_PVH_TMDT": "QL",
    "PHI_GIAN_HANG": "STORE",
}
HIST_NHOM = {"STORE": "STORE", "KOL": "KOL", "LIVE": "LIVE", "VIDEO": "VIDEO", "TOPUP": "MEDIA",
             "FFM": "FFM", "QL": "QL", "KHAC": "KHAC"}
HIST_COGS = {"Booking KOL / TAP-MCN / AFF": "C_KOL", "Livestream (host, kỹ thuật, AI)": "C_LIVE",
             "Short video": "C_VIDEO", "Media / top up": "C_MEDIA", "Fulfillment": "C_FFM",
             "Giá vốn khác": "C_KHAC"}
CAT_GRP = {
    "TT_KOL": "C_KOL", "TT_AFF": "C_KOL", "TT_LIVE": "C_LIVE", "TT_CONTENT": "C_VIDEO", "TT_ADS": "C_MEDIA",
    "TT_LOGISTICS": "C_FFM", "TT_OUTSOURCE": "C_KHAC", "TT_SAMPLE": "C_KHAC",
    "LG_NGOAI_KHOI": "O_NSK", "VH_OFFICE": "O_VP", "VH_TELECOM": "O_VP", "VH_SOFTWARE": "O_TOOL",
    "VH_ASSET": "O_TOOL", "VH_HR": "O_HR", "VH_EVENT": "O_EVENT", "VH_SUPPLIES": "O_EVENT",
    "VH_PROFESSIONAL": "O_PRO", "VH_TAX": "O_PRO", "VH_BANK": "O_PRO", "VH_MARKETING": "O_KHAC",
    "VH_TRAVEL": "O_KHAC", "VH_OTHER": "O_KHAC",
}
CASH_GRP = {"TT": "Chi nhà cung cấp dịch vụ (KOL, livestream, media…)", "VH": "Chi vận hành văn phòng, công cụ",
            "LG_TRONG_KHOI": "Chi lương, thưởng (qua ĐNTT)", "LG": "Chi nhân sự khác (ngoài bảng lương)", "KT_CHIHO": "Chi hộ brand", "KT_TAMUNG": "Tạm ứng",
            "KT_KYQUY": "Ký quỹ, đặt cọc", "KT_TRANO": "Trả nợ gốc vay", "": "Chi khác (chưa phân loại)"}

# Chi phi van hanh theo SO P&L (sheet 'expensive' cua file P&L Finance), da gom theo nhom - chi dung cho thang <= HIST_CUT.
# Khong co dong luong (luong khoi chung lay tu bang luong); phan chenh con lai vao O_SO.
EXP_HIST = {
    "2025-01": {"O_EVENT": 61848626, "O_HR": 2008333, "O_KHAC": 9332312, "O_PRO": 2239200, "O_TOOL": 19590687, "O_VP": 62892297},
    "2025-02": {"O_EVENT": 3730856, "O_HR": 2008333, "O_KHAC": 30995290, "O_PRO": 320400, "O_TOOL": 23346685, "O_VP": 61015170},
    "2025-03": {"O_EVENT": 9197000, "O_HR": 4544565, "O_KHAC": 31538644, "O_PRO": 211200, "O_TOOL": 12961738, "O_VP": 95224610},
    "2025-04": {"O_EVENT": 4923889, "O_HR": 2008333, "O_KHAC": 22510206, "O_PRO": 194400, "O_TOOL": 40696373, "O_VP": 88111435},
    "2025-05": {"O_EVENT": 8991889, "O_HR": 17340560, "O_KHAC": 11465505, "O_PRO": 202800, "O_TOOL": 38816651, "O_VP": 101563115},
    "2025-06": {"O_EVENT": 5944555, "O_HR": 26746260, "O_KHAC": 20133858, "O_PRO": 244800, "O_TOOL": 39807485, "O_VP": 93881428},
    "2025-07": {"O_EVENT": 13096065, "O_HR": 4390000, "O_KHAC": 12591574, "O_PRO": 1419600, "O_TOOL": 39995354, "O_VP": 85691140},
    "2025-08": {"O_EVENT": 6386930, "O_HR": 4390000, "O_KHAC": 21189806, "O_PRO": 367200, "O_TOOL": 52814288, "O_VP": 90386960},
    "2025-09": {"O_EVENT": 64757809, "O_HR": 4390000, "O_KHAC": 39525693, "O_PRO": 337200, "O_TOOL": 40276594, "O_VP": 86436846},
    "2025-10": {"O_EVENT": 42520647, "O_HR": 6287963, "O_KHAC": 24968521, "O_PRO": 289600, "O_TOOL": 45527433, "O_VP": 91850555},
    "2025-11": {"O_EVENT": 15720146, "O_KHAC": 22139800, "O_PRO": 458800, "O_TOOL": 49632747, "O_VP": 161662128},
    "2025-12": {"O_EVENT": 15484192, "O_KHAC": 52904870, "O_PRO": 333405141, "O_TOOL": 58520854, "O_VP": 165746020},
    "2026-01": {"O_EVENT": 144600282, "O_KHAC": 51540898, "O_PRO": 533200, "O_TOOL": 57616024, "O_VP": 159729955},
    "2026-02": {"O_EVENT": 7253861, "O_KHAC": 39592074, "O_PRO": 563300, "O_TOOL": 68640421, "O_VP": 152371500},
    "2026-03": {"O_EVENT": 42521845, "O_KHAC": 4012058, "O_PRO": 429600, "O_TOOL": 68811925, "O_VP": 162059915},
    "2026-04": {"O_EVENT": 13718731, "O_KHAC": 51053927, "O_PRO": 639600, "O_TOOL": 96272273, "O_VP": 162056241},
    "2026-05": {"O_EVENT": 32503017, "O_KHAC": 26811119, "O_PRO": 569600, "O_TOOL": 64668590, "O_VP": 167816959},
    "2026-06": {"O_EVENT": 282119718, "O_KHAC": 85498160, "O_PRO": 600400, "O_TOOL": 70976659, "O_VP": 193260608},
    "2026-07": {"O_EVENT": 129640135, "O_KHAC": 59893679, "O_PRO": 530400, "O_TOOL": 64828597, "O_VP": 210245758},
    "2026-08": {"O_EVENT": 94003607, "O_KHAC": 31557304, "O_PRO": 630500, "O_TOOL": 65828597, "O_VP": 186473041},
}
# Ma chuc danh trong file luong -> ten vi tri (Designation) tren ERP.
ROLE_NAME = {
    "COMMERCIAL": "Commercial Executive",
    "KOL/KOC": "Affiliate Management Executive",
    "MER": "Campaign & Merchandise Executive",
    "DES": "Design Executive",
    "MERDIA ONSITE": "Digital Marketing Executive",
    "MERDIA OFFSITE": "Digital Marketing Executive",
    "Digital Marketing": "Digital Marketing Executive",
    "HOST_IH": "Livestream Host",
    "HOST": "Livestream Host",
    "PRODUCTION": "Production",
    "PRODUCTION LEAD": "Production Manager",
    "CONTENT": "Content Creator",
    "PBI": "Analytics Engineer",
    "DATA & SYSTEM": "Data & System",
    "AI": "AI & Digital Solutions Developer",
    "SA": "Sale Admin",
    "VA": "Business Development Executive",
    "GA": "General Accounting Executive",
    "TA": "TA",
    "HR": "HR",
    "OPS": "Operation & System Executive",
    "OPS & SYSTEM MANAGER": "Operation, System & Data Manager",
    "SERVICE LEAD": "Service Lead",
    "SERVICE PROJECT LEAD": "Service Lead",
    "PROJECT LEAD": "Project Lead",
    "KAM": "Key Account Manager",
    "KAM_AI": "AI Livestream Key Account Manager",
    "LABOR": "Labor",
    "ECOM LEAD": "E-commerce Lead",
    "CS": "CS/CX (chưa có trên ERP)"
}

HIST_BRAND_FIX = {"Định phí BBT tháng 11": "BBT-VN"}
EXTRA_CLIENT = {"CM Foods": "CM Foods", "Masan": "Masan", "Fonterra": "Fonterra", "MCN": "ECENTRIC"}

notes = []
session_user = frappe.session.user or ""
fd = frappe.form_dict or {}


def roles_of(u):
    out = []
    for r in frappe.db.sql("""SELECT role FROM `tabHas Role` WHERE parent = %s AND parenttype = 'User'""", (u,)):
        out = out + [r[0]]
    return out


roles = roles_of(session_user) if session_user and session_user != "Guest" else []
if "System Manager" in roles and fd.get("debug_as_user"):
    session_user = fd.get("debug_as_user")
    roles = roles_of(session_user)
    notes = notes + ["Dang xem duoi goc nhin cua " + str(session_user)]

can_cost = session_user == "Administrator"
for r in roles:
    if r in FULL_ROLES:
        can_cost = True
can_view = can_cost
viewer_dept = ""
if session_user and session_user != "Guest":
    er = frappe.db.sql("""SELECT department FROM `tabEmployee` WHERE user_id = %s AND status = 'Active' LIMIT 1""",
                       (session_user,), as_dict=True)
    if er:
        viewer_dept = er[0].get("department") or ""
if not can_view and session_user and frappe.db.exists("EC Viewer Permission", session_user):
    if frappe.db.get_value("EC Viewer Permission", session_user, "scope") == "all":
        can_view = True
if not can_view and viewer_dept == MGMT_DEPT:
    can_view = True

if not can_view:
    frappe.response["message"] = {"ok": False, "error": "no_permission",
                                  "message": "Ban khong co quyen xem bao cao PnL.",
                                  "scope": {"user": session_user, "can_cost": False}}
else:
    today = frappe.utils.getdate(frappe.utils.today())
    cur_month = str(today)[:7]
    year = str(fd.get("year") or str(today.year)).strip()[:4]
    if not year.isdigit():
        year = str(today.year)
    months = []
    for i in range(12):
        mm = str(i + 1)
        if len(mm) < 2:
            mm = "0" + mm
        months = months + [year + "-" + mm]
    midx = {}
    for i in range(12):
        midx[months[i]] = i
    msrc = []
    for m in months:
        if m <= HIST_CUT:
            msrc = msrc + ["so"]
        elif m <= cur_month:
            msrc = msrc + ["erp"]
        else:
            msrc = msrc + ["est"]

    def z():
        return [0.0] * 12

    def addm(store, key, i, v):
        if key not in store:
            store[key] = z()
        store[key][i] = store[key][i] + v

    # ------------------------------------------------------------ brand / khach hang me
    bmeta = {}
    for r in frappe.db.sql("""SELECT name, ifnull(ec_brand_name, '') AS nm, ifnull(ec_parent_client, '') AS pc,
                                     ifnull(ec_status, 'Active') AS st FROM `tabBrand`""", as_dict=True):
        bmeta[r.get("name")] = {"label": r.get("nm") or r.get("name"), "client": r.get("pc") or "",
                                "active": 1 if (r.get("st") or "Active") == "Active" else 0}

    def brand_key(b):
        b = (b or "").strip()
        return HIST_BRAND_FIX.get(b) or b or "(chưa gán brand)"

    def client_of(b):
        if b in bmeta and bmeta[b]["client"]:
            return bmeta[b]["client"]
        if b in EXTRA_CLIENT:
            return EXTRA_CLIENT[b]
        return KHAC_KH

    # ------------------------------------------------------------ doanh thu: Sales Order
    ecol = "(CASE WHEN so.transaction_date <= '2026-08-31' OR so.delivery_date <= '2026-08-31' THEN ifnull(so.delivery_date, so.transaction_date) ELSE so.transaction_date END)"
    dfrom = year + "-01-01"
    dto = year + "-12-31"
    so_rows = frappe.db.sql("""
        SELECT so.name, ifnull(so.ec_brand, '') AS brand, ifnull(so.net_total, 0) AS net,
               date_format(""" + ecol + """, '%%Y-%%m') AS ky, ifnull(so.workflow_state, '') AS st,
               date_format(so.transaction_date, '%%Y-%%m') AS tky, left(ifnull(so.ec_mso_month, ''), 7) AS mso
        FROM `tabSales Order` so
        WHERE so.docstatus < 2 AND ((""" + ecol + """ >= %(df)s AND """ + ecol + """ <= %(dt)s)
              OR (left(ifnull(so.ec_mso_month, ''), 7) >= %(ym0)s AND left(ifnull(so.ec_mso_month, ''), 7) <= %(ym1)s))
    """, {"df": dfrom, "dt": dto, "ym0": year + "-01", "ym1": year + "-12"}, as_dict=True)
    so_ok = {}
    for r in so_rows:
        st = r.get("st") or ""
        if st == "Approved" or st[:7] == "Pending" or st == "Draft":
            so_ok[r.get("name")] = r
    it_rows = frappe.db.sql("""
        SELECT soi.parent, soi.item_code, ifnull(soi.amount, 0) AS amt, ifnull(it.item_group, '') AS ig
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        LEFT JOIN `tabItem` it ON it.name = soi.item_code
        WHERE so.docstatus < 2 AND ((""" + ecol + """ >= %(df)s AND """ + ecol + """ <= %(dt)s)
              OR (left(ifnull(so.ec_mso_month, ''), 7) >= %(ym0)s AND left(ifnull(so.ec_mso_month, ''), 7) <= %(ym1)s))
    """, {"df": dfrom, "dt": dto, "ym0": year + "-01", "ym1": year + "-12"}, as_dict=True)
    so_items = {}
    for r in it_rows:
        if r.get("parent") in so_ok:
            so_items[r.get("parent")] = (so_items.get(r.get("parent")) or []) + [r]
    rev = {}

    def rev_add(b, g, i, v):
        if b not in rev:
            rev[b] = {}
        addm(rev[b], g, i, v)

    # Ghi nhan doanh thu SO: thang <= HIST_CUT giu luat cu (SO vao thang ecol, da khop so P&L bang dong ADJ).
    # Thang sau HIST_CUT: ghi theo THANG DICH VU cua SO (ec_mso_month); SO khong co thi theo ngay SO.
    # SO co thang dich vu <= HIST_CUT (vd hop dong quy 07-09 gan thang 07, chu ky 26/08-25/09 gan thang 08)
    # bo di vi so P&L da tinh -> khong don ca hop dong vao thang dang chay.
    def so_shares(r):
        ky = r.get("ky") or ""
        if ky <= HIST_CUT:
            if ky in midx:
                return [[midx[ky], 1.0]]
            return []
        mm = r.get("mso") or r.get("tky") or ""
        if mm <= HIST_CUT or mm not in midx:
            return []
        return [[midx[mm], 1.0]]

    for name in so_ok:
        r = so_ok[name]
        shares = so_shares(r)
        if not shares:
            continue
        b = brand_key(r.get("brand"))
        net0 = frappe.utils.flt(r.get("net"))
        for sh in shares:
            i = sh[0]
            net = net0 * sh[1]
            its = so_items.get(name) or []
            tot_it = 0.0
            for x in its:
                tot_it = tot_it + frappe.utils.flt(x.get("amt"))
            if not its or not tot_it:
                rev_add(b, "KHAC", i, net)
                continue
            for x in its:
                code = x.get("item_code") or ""
                g = ITEM_GRP.get(code)
                if not g:
                    ig = x.get("ig") or ""
                    if ig.find("vận chuyển") >= 0 or ig.find("kho bãi") >= 0:
                        g = "FFM"
                    elif code[:4] == "GBS_" or code[:4] == "REV_" or ig[:3] == "GBS":
                        g = "GBS"
                    else:
                        g = "KHAC"
                rev_add(b, g, i, net * frappe.utils.flt(x.get("amt")) / tot_it)

    # ------------------------------------------------------------ so P&L lich su
    hrows = []
    if months[0] <= HIST_CUT:
        hrows = frappe.db.sql("""
            SELECT date_format(thang, '%%Y-%%m') AS ky, loai, ifnull(brand, '') AS brand, ifnull(nhom, '') AS nhom,
                   ifnull(dich_vu, '') AS dv, ifnull(khoan_muc, '') AS km, ifnull(ma_erp, '') AS ma,
                   SUM(ifnull(so_tien, 0)) AS amt
            FROM `tabEC PnL Lich Su`
            WHERE thang >= %(df)s AND thang <= %(dt)s
            GROUP BY date_format(thang, '%%Y-%%m'), loai, ifnull(brand, ''), ifnull(nhom, ''), ifnull(dich_vu, ''),
                     ifnull(khoan_muc, ''), ifnull(ma_erp, '')
        """, {"df": dfrom, "dt": HIST_END if dto > HIST_END else dto}, as_dict=True)
    so_gv_kh = {}
    so_cp_kh = {}
    adj_rows = []
    cogs = {}
    opex = {}
    book_sal = z()
    for h in hrows:
        i = midx.get(h.get("ky"))
        if i is None:
            continue
        amt = frappe.utils.flt(h.get("amt"))
        loai = h.get("loai") or ""
        if h.get("ma") == "BRAND_ALLOC":
            kh = client_of(brand_key(h.get("brand")))
            if loai == "Giá vốn":
                addm(so_gv_kh, kh, i, amt)
            else:
                addm(so_cp_kh, kh, i, amt)
            continue
        if loai == "Doanh thu" and h.get("ma") == "ADJ":
            adj_rows = adj_rows + [[brand_key(h.get("brand")), h.get("nhom") or "", i, amt]]
            continue
        if loai == "Doanh thu":
            nh = h.get("nhom") or ""
            g = HIST_NHOM.get(nh)
            if not g:
                dv = (h.get("dv") or "").lower()
                if dv.find("kol") >= 0:
                    g = "KOL"
                elif dv.find("live") >= 0:
                    g = "LIVE"
                elif dv.find("media") >= 0:
                    g = "MEDIA"
                elif dv.find("video") >= 0:
                    g = "VIDEO"
                elif dv.find("package") >= 0:
                    g = "QL"
                else:
                    g = "GBS"
            rev_add(brand_key(h.get("brand")), g, i, amt)
            continue
        nh = h.get("nhom") or ""
        km = h.get("km") or ""
        if loai == "Giá vốn":
            if nh == "Lương & phụ cấp theo chức danh" or km in ("MERDIA ONSITE", "MERDIA OFFSITE"):
                book_sal[i] = book_sal[i] + amt
                continue
            addm(cogs, HIST_COGS.get(nh) or "C_KHAC", i, amt)
        else:
            addm(opex, "O_SO", i, amt)

    # Dong ADJ ("ERP cao hon so - dieu chinh ve so P&L"): khong de thanh dong doanh thu am rieng, ma tru
    # ty le vao cac nhom doanh thu cua chinh brand do trong thang (tru phi gian hang), de tong van bang so.
    for a in adj_rows:
        b = a[0]
        i = a[2]
        g = HIST_NHOM.get(a[1])
        if g and g != "KHAC":
            rev_add(b, g, i, a[3])
            continue
        base = 0.0
        for gg in (rev.get(b) or {}):
            if gg != "STORE" and rev[b][gg][i] > 0:
                base = base + rev[b][gg][i]
        if base <= 0:
            rev_add(b, "KHAC", i, a[3])
            continue
        for gg in list((rev.get(b) or {}).keys()):
            if gg != "STORE" and rev[b][gg][i] > 0:
                rev[b][gg][i] = rev[b][gg][i] + a[3] * rev[b][gg][i] / base

    # ------------------------------------------------------------ luong (bang luong lich su + TB 3 thang)
    luong_kh = {}
    fte_kh = {}
    sal_role = {}
    sal_role_c = {}
    sal_role_o = {}
    sal_dept = {}
    fte_dept = {}
    sal_tag = [""] * 12
    tb3_from = []
    lrows = frappe.db.sql("""
        SELECT date_format(thang, '%%Y-%%m') AS ky, ifnull(chuc_danh, '') AS cd, ifnull(khach_hang_me, '') AS kh,
               ifnull(phong_ban, '') AS pb, SUM(ifnull(fte, 0)) AS fte, SUM(ifnull(tong, 0)) AS tong
        FROM `tabEC PnL Luong Lich Su` WHERE dot_nap = %(dot)s
        GROUP BY date_format(thang, '%%Y-%%m'), ifnull(chuc_danh, ''), ifnull(khach_hang_me, ''), ifnull(phong_ban, '')
    """, {"dot": LUONG_DOT}, as_dict=True) if frappe.db.exists("DocType", "EC PnL Luong Lich Su") else []
    by_m = {}
    for r in lrows:
        by_m[r.get("ky")] = (by_m.get(r.get("ky")) or []) + [r]
    actual = sorted(by_m.keys())
    tb3_from = actual[-3:]
    last_actual = actual[-1] if actual else ""
    sal_total = z()
    for i in range(12):
        m = months[i]
        src = []
        fac = 1.0
        if m in by_m:
            src = by_m[m]
            sal_tag[i] = "that"
        elif actual and m > last_actual:
            for k in tb3_from:
                src = src + by_m[k]
            fac = 1.0 / len(tb3_from)
            sal_tag[i] = "tb3"
        for r in src:
            t = frappe.utils.flt(r.get("tong")) * fac
            f = frappe.utils.flt(r.get("fte")) * fac
            kh = r.get("kh") or CTY_KEY
            sal_total[i] = sal_total[i] + t
            if kh == CTY_KEY:
                addm(opex, "O_NS", i, t)
                addm(sal_role_o, ROLE_NAME.get(r.get("cd") or "") or r.get("cd") or "(khong ro)", i, t)
            else:
                addm(cogs, "C_LUONG", i, t)
                addm(luong_kh, kh, i, t)
                addm(sal_role_c, ROLE_NAME.get(r.get("cd") or "") or r.get("cd") or "(khong ro)", i, t)
            addm(fte_kh, kh, i, f)
            addm(sal_role, ROLE_NAME.get(r.get("cd") or "") or r.get("cd") or "(khong ro)", i, t)
            addm(sal_dept, r.get("pb") or "(chua ro)", i, t)
            addm(fte_dept, r.get("pb") or "(chua ro)", i, f)
    # thang <= HIST_CUT co luong that: luong so (book_sal) da bo o tren; phan chenh (luong that - luong so trong
    # gia von) tru vao chi phi van hanh theo so -> tong chi phi van bang so P&L.
    for i in range(12):
        if msrc[i] == "so" and sal_tag[i] == "that":
            nct = (cogs.get("C_LUONG") or z())[i] + (opex.get("O_NS") or z())[i]
            addm(opex, "O_SO", i, -(nct - book_sal[i]))
        elif msrc[i] == "so" and book_sal[i]:
            addm(cogs, "C_LUONG", i, book_sal[i])

    # ------------------------------------------------------------ DNTT / thuong / affiliate (ERP)
    ky_ok = frappe.db.sql("""SELECT name FROM `tabCustom Field` WHERE dt = 'EC Payment Request' AND fieldname = 'ec_ky_chi_phi' LIMIT 1""")
    pr_date = "ifnull(d.ec_ky_chi_phi, ifnull(d.payment_date, d.creation))" if ky_ok else "ifnull(d.payment_date, d.creation)"
    pr_amt = "ifnull(d.payment_amount, 0) / (1 + CAST(ifnull(nullif(d.ec_vat_pct, ''), '0') AS DECIMAL(10,4)) / 100)"
    specs = [
        ["EC Payment Request", pr_amt, pr_date, "ifnull(d.ec_loai_chi_phi, '')", "ifnull(d.ec_brand, '')"],
        ["EC Special Bonus Request", "ifnull(d.total_bonus, 0)", "d.creation", "'SB'", "''"],
        ["EC Affiliate Bonus Request", "CASE WHEN ifnull(d.total_amount, 0) > 0 THEN d.total_amount ELSE ifnull(d.budget, 0) END",
         "ifnull(d.service_month, d.creation)", "'TT_AFF'", "''"],
    ]
    tt_kh = {}
    tt_nobrand = z()
    opex_dept = {}
    pending = []
    for sp in specs:
        if not frappe.db.exists("DocType", sp[0]):
            continue
        rows = frappe.db.sql("""
            SELECT d.name, ifnull(d.request_title, d.name) AS title, ifnull(d.department, '') AS dept,
                   """ + sp[1] + """ AS amt, date_format(""" + sp[2] + """, '%%Y-%%m') AS ky,
                   ifnull(a.approval_status, '') AS st, """ + sp[3] + """ AS cat, """ + sp[4] + """ AS brand
            FROM `tab""" + sp[0] + """` d
            LEFT JOIN `tabEC Approval Request` a ON a.name = d.approval_request
            WHERE d.docstatus < 2 AND """ + sp[2] + """ >= %(df)s AND """ + sp[2] + """ <= %(dt)s
        """, {"df": dfrom, "dt": dto + " 23:59:59"}, as_dict=True)
        for r in rows:
            st = r.get("st") or ""
            if st not in LIVE_STATUS:
                continue
            i = midx.get(r.get("ky"))
            if i is None:
                continue
            cat = r.get("cat") or ""
            if cat == "SB":
                g = "O_NSK"
            else:
                g = CAT_GRP.get(cat)
            if not g:
                if cat[:3] == "KT_" or cat == "LG_TRONG_KHOI":
                    continue
                g = "O_KHAC"
            amt = frappe.utils.flt(r.get("amt"))
            if st != "Approved":
                if len(pending) < 400:
                    b = (r.get("brand") or "").strip()
                    pending = pending + [{"name": r.get("name"), "title": r.get("title"), "amount": amt,
                                          "month": r.get("ky"), "status": st, "group": g, "dept": r.get("dept"),
                                          "brand": (bmeta.get(b) or {}).get("label") or b}]
                continue
            if g[:2] == "C_":
                addm(cogs, g, i, amt)
                b = (r.get("brand") or "").strip()
                if b:
                    addm(tt_kh, client_of(b), i, amt)
                else:
                    tt_nobrand[i] = tt_nobrand[i] + amt
            else:
                addm(opex, g, i, amt)
            addm(opex_dept, r.get("dept") or "(chua ro)", i, amt)

    # Thang <= HIST_CUT: tach chi phi van hanh theo nhom tu so P&L (EXP_HIST). Tong giu nguyen bang so;
    # phan con lai (chu yeu chenh luong so <-> bang luong) nam o O_SO.
    for i in range(12):
        eh = EXP_HIST.get(months[i])
        if msrc[i] != "so" or not eh:
            continue
        tong = 0.0
        for g in opex:
            tong = tong + opex[g][i]
        ns = (opex.get("O_NS") or z())[i]
        for g in list(opex.keys()):
            if g != "O_NS":
                opex[g][i] = 0.0
        da = 0.0
        for g in eh:
            addm(opex, g, i, frappe.utils.flt(eh[g]))
            da = da + frappe.utils.flt(eh[g])
        addm(opex, "O_SO", i, tong - ns - da)

    # ------------------------------------------------------------ dong tien
    cash_chi = {}
    unc = frappe.db.sql("""
        SELECT date_format(d.fulfillment_unc_date, '%%Y-%%m') AS ky, ifnull(d.ec_loai_chi_phi, '') AS cat,
               SUM(ifnull(d.payment_amount, 0)) AS amt
        FROM `tabEC Payment Request` d
        WHERE d.docstatus < 2 AND d.fulfillment_unc_date >= %(df)s AND d.fulfillment_unc_date <= %(dt)s
        GROUP BY date_format(d.fulfillment_unc_date, '%%Y-%%m'), ifnull(d.ec_loai_chi_phi, '')
    """, {"df": dfrom, "dt": dto}, as_dict=True)
    chi_from = ""
    for r in unc:
        i = midx.get(r.get("ky"))
        if i is None:
            continue
        cat = r.get("cat") or ""
        key = CASH_GRP.get(cat) or CASH_GRP.get(cat[:2]) or CASH_GRP[""]
        addm(cash_chi, key, i, frappe.utils.flt(r.get("amt")))
        if not chi_from or r.get("ky") < chi_from:
            chi_from = r.get("ky")
    cash_thu = {}
    so_du = None
    if frappe.db.exists("DocType", "EC Dong Tien Nhap Tay"):
        for r in frappe.db.sql("""
            SELECT date_format(thang, '%%Y-%%m') AS ky, loai, SUM(ifnull(so_tien, 0)) AS amt
            FROM `tabEC Dong Tien Nhap Tay` WHERE thang >= %(df)s AND thang <= %(dt)s
            GROUP BY date_format(thang, '%%Y-%%m'), loai
        """, {"df": dfrom, "dt": dto}, as_dict=True):
            i = midx.get(r.get("ky"))
            if i is None:
                continue
            if r.get("loai") == "Số dư đầu năm":
                so_du = frappe.utils.flt(r.get("amt"))
            else:
                addm(cash_thu, r.get("loai") or "Thu khác", i, frappe.utils.flt(r.get("amt")))

    # ------------------------------------------------------------ brand meta tra ve
    used = {}
    for b in rev:
        used[b] = 1
    for b in bmeta:
        if bmeta[b]["active"] or bmeta[b]["client"]:
            used[b] = 1
    brands_out = {}
    for b in used:
        mt = bmeta.get(b) or {}
        brands_out[b] = {"label": mt.get("label") or b, "client": client_of(b), "active": mt.get("active", 1)}
    clients = {}
    for b in brands_out:
        c = brands_out[b]["client"]
        clients[c] = (clients.get(c) or []) + [b]
    for c in list(luong_kh.keys()) + list(so_gv_kh.keys()) + list(tt_kh.keys()):
        if c not in clients:
            clients[c] = []

    def rnd(store):
        out = {}
        for k in store:
            out[k] = [round(v) for v in store[k]]
        return out

    def rnd2(store):
        out = {}
        for k in store:
            out[k] = [round(v, 2) for v in store[k]]
        return out

    rev_out = {}
    for b in rev:
        rev_out[b] = rnd(rev[b])
    cost_block = None
    if can_cost:
        cost_block = {
            "cogs": rnd(cogs), "opex": rnd(opex), "luong_kh": rnd(luong_kh), "tt_kh": rnd(tt_kh),
            "tt_nobrand": [round(v) for v in tt_nobrand], "so_gv_kh": rnd(so_gv_kh), "so_cp_kh": rnd(so_cp_kh),
            "sal_role": rnd(sal_role), "sal_role_c": rnd(sal_role_c), "sal_role_o": rnd(sal_role_o), "sal_dept": rnd(sal_dept), "sal_total": [round(v) for v in sal_total],
            "opex_dept": rnd(opex_dept), "pending": sorted(pending, key=lambda x: x["amount"], reverse=True),
            "cash": {"chi": rnd(cash_chi), "thu": rnd(cash_thu), "so_du_dau_nam": so_du, "chi_tu_thang": chi_from},
        }
    else:
        notes = notes + ["Ban chi xem duoc doanh thu. Chi phi, luong va loi nhuan chi nhom CEO / HOF / C&B xem duoc."]
    frappe.response["message"] = {
        "ok": True,
        "scope": {"user": session_user, "can_cost": can_cost, "dept": viewer_dept},
        "year": year, "months": months, "src": msrc, "hist_cut": HIST_CUT, "cur_month": cur_month,
        "sal_tag": sal_tag, "sal_tb3_from": tb3_from, "sal_last_actual": last_actual,
        "brands": brands_out, "clients": clients,
        "rev": rev_out,
        "fte_kh": rnd2(fte_kh), "fte_dept": rnd2(fte_dept),
        "cost": cost_block,
        "meta": {"notes": notes, "generated_at": str(frappe.utils.now_datetime())},
    }
