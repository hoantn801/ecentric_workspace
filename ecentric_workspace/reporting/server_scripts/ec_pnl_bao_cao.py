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
EXP_LABELS = [
    "Chi phí thuê văn phòng, điện, nước sinh hoạt, giữ xe nhân viên",
    "Chi phí gửi chứng từ, bưu phẩm văn phòng",
    "Chi phí internet,phone, đường truyền, truyền hình cáp của các văn phòng làm việc",
    "Chi phí văn phòng phẩm, nhu yếu phẩm văn phòng, nước uống văn phòng",
    "Chi phí mua sắm Tools, thiết bị thay thế máy móc",
    "Chi phí tiếp khách của BOD, mua quà tặng khách, chi tham gia sự kiện để mở rộng kinh doanh, networking và tìm kiếm Khách hàng",
    "Chi phí tiệc công ty",
    "Chi phí di chuyển (Grab, taxi..)",
    "Chi phí ngân hàng",
    "Chi phí tuyển dụng",
    "Chi phí thuế, lệ phí",
    "Chi phí khác",
    "Chi phí phúc lợi khác nhân viên (khám sức khỏe, bảo hiểm sức khỏe…)",
    "Tên miền",
    "Chi phí công tác (vé máy bay, khách sạn, di chuyển…)",
    "Chi phí tranning",
    "Chi phí quảng cáo",
    "Chi phí vận hành khác",
    "Chi phí sữa chữa văn phòng, thiết bị..",
    "Chi phí mua sắm mới bàn ghế văn phòng",
    "Chi phí chữ ký số, phần mềm phục vụ báo cáo nhà nước",
    "Chi phí tổ chức các hoạt động teambuilding",
]
# [nhom, chi so trong EXP_LABELS, so tien] theo thang. Khong co dong luong va khong co ghi chu (ghi chu so co ten nguoi).
EXP_LINES = {
    "2025-01": [["O_VP", 0, 50527966], ["O_VP", 1, 1530409], ["O_VP", 2, 9632904], ["O_VP", 3, 1201018], ["O_TOOL", 4, 18924020], ["O_EVENT", 5, 22884895], ["O_EVENT", 6, 36663731], ["O_KHAC", 7, 3436526], ["O_PRO", 8, 239200], ["O_HR", 9, 2008333], ["O_PRO", 10, 2000000], ["O_KHAC", 11, 5895786], ["O_EVENT", 12, 2300000], ["O_TOOL", 13, 666667]],
    "2025-02": [["O_VP", 0, 48555966], ["O_VP", 1, 1004169], ["O_VP", 2, 10217449], ["O_VP", 3, 1237586], ["O_TOOL", 4, 22680018], ["O_EVENT", 5, 1430856], ["O_KHAC", 14, 18005579], ["O_KHAC", 7, 2000000], ["O_PRO", 8, 320400], ["O_HR", 9, 2008333], ["O_KHAC", 11, 10989711], ["O_EVENT", 12, 2300000], ["O_TOOL", 13, 666667]],
    "2025-03": [["O_VP", 0, 82422198], ["O_VP", 1, 303241], ["O_VP", 2, 9967140], ["O_VP", 3, 2532031], ["O_TOOL", 4, 12295071], ["O_EVENT", 5, 6897000], ["O_KHAC", 14, 15935939], ["O_KHAC", 7, 2706919], ["O_PRO", 8, 211200], ["O_HR", 9, 2008333], ["O_KHAC", 11, 12895786], ["O_HR", 15, 2536232], ["O_EVENT", 12, 2300000], ["O_TOOL", 13, 666667]],
    "2025-04": [["O_VP", 0, 73951254], ["O_VP", 1, 631284], ["O_VP", 2, 12441312], ["O_VP", 3, 1087585], ["O_TOOL", 4, 40029706], ["O_EVENT", 5, 2453889], ["O_KHAC", 14, 10471444], ["O_KHAC", 7, 4971192], ["O_PRO", 8, 194400], ["O_HR", 9, 2008333], ["O_KHAC", 11, 7067570], ["O_EVENT", 12, 2470000], ["O_TOOL", 13, 666667]],
    "2025-05": [["O_VP", 0, 78733090], ["O_VP", 1, 716653], ["O_VP", 2, 12440767], ["O_VP", 3, 9672605], ["O_TOOL", 4, 38149984], ["O_EVENT", 5, 6521889], ["O_KHAC", 7, 4829460], ["O_PRO", 8, 202800], ["O_HR", 9, 6398337], ["O_KHAC", 11, 6636045], ["O_HR", 15, 10942223], ["O_EVENT", 12, 2470000], ["O_TOOL", 13, 666667]],
    "2025-06": [["O_VP", 0, 76196110], ["O_VP", 1, 2937443], ["O_VP", 2, 12828741], ["O_VP", 3, 1919134], ["O_TOOL", 4, 39140818], ["O_EVENT", 5, 2094000], ["O_KHAC", 14, 8910703], ["O_KHAC", 7, 3115741], ["O_PRO", 8, 244800], ["O_HR", 9, 4390000], ["O_KHAC", 11, 8107414], ["O_HR", 15, 22356260], ["O_EVENT", 12, 3850555], ["O_TOOL", 13, 666667]],
    "2025-07": [["O_VP", 0, 75784550], ["O_VP", 1, 1029355], ["O_VP", 2, 6296130], ["O_VP", 3, 2581105], ["O_TOOL", 4, 39328687], ["O_EVENT", 5, 2133750], ["O_KHAC", 7, 6588679], ["O_PRO", 8, 1419600], ["O_HR", 9, 4390000], ["O_KHAC", 11, 6002895], ["O_EVENT", 12, 10962315], ["O_TOOL", 13, 666667]],
    "2025-08": [["O_VP", 0, 74875468], ["O_VP", 1, 1663707], ["O_VP", 2, 6301789], ["O_VP", 3, 7545996], ["O_KHAC", 16, 9002271], ["O_TOOL", 4, 52147621], ["O_EVENT", 5, 2922930], ["O_KHAC", 14, 5570860], ["O_PRO", 8, 367200], ["O_HR", 9, 4390000], ["O_KHAC", 11, 6616675], ["O_EVENT", 12, 3464000], ["O_TOOL", 13, 666667]],
    "2025-09": [["O_VP", 0, 75149432], ["O_VP", 1, 407588], ["O_VP", 2, 6299363], ["O_VP", 3, 4580463], ["O_TOOL", 4, 39609927], ["O_EVENT", 5, 46801759], ["O_EVENT", 6, 14600050], ["O_KHAC", 7, 6988836], ["O_PRO", 8, 337200], ["O_KHAC", 17, 17600000], ["O_HR", 9, 4390000], ["O_KHAC", 11, 14936857], ["O_EVENT", 12, 3356000], ["O_TOOL", 13, 666667]],
    "2025-10": [["O_VP", 0, 75173926], ["O_VP", 1, 818597], ["O_VP", 2, 6295902], ["O_VP", 3, 9562130], ["O_TOOL", 4, 44860766], ["O_EVENT", 5, 9758147], ["O_EVENT", 6, 342500], ["O_KHAC", 7, 5743922], ["O_PRO", 8, 289600], ["O_HR", 9, 4390000], ["O_KHAC", 11, 19224599], ["O_HR", 15, 1897963], ["O_EVENT", 12, 32420000], ["O_TOOL", 13, 666667]],
    "2025-11": [["O_VP", 0, 135019014], ["O_VP", 1, 2064815], ["O_VP", 2, 6292404], ["O_VP", 3, 7940833], ["O_TOOL", 4, 48966080], ["O_EVENT", 5, 6528331], ["O_KHAC", 14, 1439074], ["O_KHAC", 7, 8067902], ["O_PRO", 8, 458800], ["O_KHAC", 11, 12632824], ["O_EVENT", 12, 9191815], ["O_TOOL", 13, 666667], ["O_VP", 18, 10345062]],
    "2025-12": [["O_VP", 0, 133928792], ["O_VP", 1, 2089403], ["O_VP", 2, 11707173], ["O_VP", 3, 7975590], ["O_TOOL", 4, 57854187], ["O_EVENT", 5, 9375000], ["O_KHAC", 14, 1879000], ["O_KHAC", 7, 4123727], ["O_PRO", 8, 415600], ["O_PRO", 10, 332989541], ["O_KHAC", 11, 46902143], ["O_EVENT", 12, 6109192], ["O_TOOL", 13, 666667], ["O_VP", 18, 10045062]],
    "2026-01": [["O_VP", 0, 134197008], ["O_VP", 1, 3038854], ["O_VP", 2, 9524951], ["O_VP", 3, 3324080], ["O_TOOL", 4, 56949357], ["O_EVENT", 5, 79546721], ["O_EVENT", 6, 58233561], ["O_KHAC", 14, 6957863], ["O_KHAC", 7, 7106755], ["O_PRO", 8, 533200], ["O_KHAC", 11, 37476280], ["O_EVENT", 12, 6820000], ["O_TOOL", 13, 666667], ["O_VP", 18, 9645062]],
    "2026-02": [["O_VP", 0, 132941512], ["O_VP", 1, 435556], ["O_VP", 2, 9349370], ["O_TOOL", 4, 67973754], ["O_EVENT", 5, 1458500], ["O_KHAC", 14, 2739000], ["O_KHAC", 7, 3594600], ["O_PRO", 8, 563300], ["O_KHAC", 11, 33258474], ["O_EVENT", 12, 5795361], ["O_TOOL", 13, 666667], ["O_VP", 18, 9645062]],
    "2026-03": [["O_VP", 0, 130990846], ["O_VP", 1, 1729796], ["O_VP", 2, 9163655], ["O_VP", 3, 10530556], ["O_TOOL", 4, 68145258], ["O_EVENT", 5, 11368900], ["O_KHAC", 7, 4012058], ["O_PRO", 8, 429600], ["O_EVENT", 12, 31152945], ["O_TOOL", 13, 666667], ["O_VP", 18, 9645062]],
    "2026-04": [["O_VP", 0, 137681760], ["O_VP", 1, 1271247], ["O_VP", 2, 9166228], ["O_VP", 3, 4291944], ["O_TOOL", 19, 19930560], ["O_TOOL", 4, 75415787], ["O_EVENT", 5, 5616096], ["O_KHAC", 14, 11024962], ["O_KHAC", 7, 5271296], ["O_PRO", 8, 639600], ["O_TOOL", 20, 259259], ["O_KHAC", 11, 34757669], ["O_EVENT", 12, 8102635], ["O_TOOL", 13, 666667], ["O_VP", 18, 9645062]],
    "2026-05": [["O_VP", 0, 145338780], ["O_VP", 1, 1468111], ["O_VP", 2, 8644006], ["O_VP", 3, 2721000], ["O_TOOL", 4, 64001923], ["O_EVENT", 5, 15430385], ["O_KHAC", 7, 5366667], ["O_PRO", 8, 569600], ["O_KHAC", 11, 21444452], ["O_EVENT", 12, 17072632], ["O_TOOL", 13, 666667], ["O_VP", 18, 9645062]],
    "2026-06": [["O_VP", 0, 166784386], ["O_VP", 1, 1339103], ["O_VP", 2, 11238724], ["O_VP", 3, 4253333], ["O_TOOL", 4, 70309992], ["O_EVENT", 5, 9232977], ["O_KHAC", 7, 6770370], ["O_PRO", 8, 600400], ["O_KHAC", 11, 78727790], ["O_EVENT", 21, 263060667], ["O_EVENT", 12, 9826074], ["O_TOOL", 13, 666667], ["O_VP", 18, 9645062]],
    "2026-07": [["O_VP", 0, 178143516], ["O_VP", 1, 605590], ["O_VP", 2, 5883590], ["O_VP", 3, 15968000], ["O_TOOL", 4, 64161930], ["O_EVENT", 5, 120489542], ["O_KHAC", 7, 5231441], ["O_PRO", 8, 530400], ["O_KHAC", 11, 54662238], ["O_EVENT", 12, 9150593], ["O_TOOL", 13, 666667], ["O_VP", 18, 9645062]],
    "2026-08": [["O_VP", 0, 166944138], ["O_VP", 1, 2315127], ["O_VP", 2, 5340936], ["O_VP", 3, 2227778], ["O_TOOL", 4, 65161930], ["O_EVENT", 5, 87200000], ["O_KHAC", 14, 14636934], ["O_KHAC", 7, 9920370], ["O_PRO", 8, 630500], ["O_KHAC", 11, 7000000], ["O_EVENT", 12, 6803607], ["O_TOOL", 13, 666667], ["O_VP", 18, 9645062]],
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
    opex_items = []
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
                if msrc[i] != "so" and len(opex_items) < 3000:
                    # Nhan su khac (thuong, ngoai bang luong): khong dua tieu de vi co the co ten nguoi.
                    ttl = r.get("title") or r.get("name")
                    if g == "O_NSK":
                        ttl = "Chi nhân sự (ẩn nội dung)"
                    opex_items = opex_items + [{"i": i, "g": g, "title": ttl, "amount": amt, "name": r.get("name"),
                                                "dept": r.get("dept") or "", "src": "erp"}]
            addm(opex_dept, r.get("dept") or "(chua ro)", i, amt)

    # Thang <= HIST_CUT: tach chi phi van hanh theo nhom tu so P&L (EXP_LINES). Tong giu nguyen bang so;
    # phan con lai (chu yeu chenh luong so <-> bang luong) nam o O_SO.
    for i in range(12):
        el = EXP_LINES.get(months[i])
        if msrc[i] != "so" or not el:
            continue
        eh = {}
        for x in el:
            eh[x[0]] = (eh.get(x[0]) or 0) + x[2]
            opex_items = opex_items + [{"i": i, "g": x[0], "title": EXP_LABELS[x[1]], "amount": x[2], "src": "so"}]
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
            "opex_dept": rnd(opex_dept), "opex_items": opex_items, "pending": sorted(pending, key=lambda x: x["amount"], reverse=True),
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
