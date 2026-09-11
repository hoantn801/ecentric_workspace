# ============================================================================
# BAN SAO DOI CHIEU - KHONG PHAI CODE CHAY.
#
# Day la ban sao y het cua Server Script `ec_pnl_phi_ql` dang chay tren
# team.ecentric.vn (Server Script, script_type = API, api_method =
# 'ec_pnl_phi_ql'). Frappe KHONG import file nay; no nam trong repo chi de repo
# khong bi mu ve logic dang chay.
#
# Sua that = sua Server Script tren live qua REST, roi cap nhat lai file nay
# trong cung mot commit. Cu phap tuan theo RestrictedPython cua Server Script
# (khong import, khong dunder, khong tuple-unpack trong vong lap).
# ============================================================================

# ec_pnl_phi_ql - API doc-only: phi quan ly gian hang UOC TINH tu NMV
# Server Script, script_type = API, api_method = 'ec_pnl_phi_ql'
#
# CHI DOC. Khong ghi, khong tao chung tu.
#
# VI SAO CO SCRIPT NAY (11/09/2026, Hoan chot):
#   Ke toan xac nhan REV_QL_TT KHONG phai phi quan ly gian hang - do la phi
#   quan ly/van hanh cong tren tung goi dich vu (booking 10%, affiliate 9%,
#   livestream 72% - ty le khac nhau tung phieu nen khong the la % tren NMV).
#   Ra soat toan bo Sales Order: chi 15 ma item tung duoc dung, KHONG ma nao la
#   phi theo % NMV. Nghia la khoan nay chua duoc ghi nhan o bat ky dau trong ERP.
#   Uoc tinh thang 9: 1,88 - 2,48 ty, lon hon ca tong doanh thu thang 8
#   (1.549.122.965d). Nen PnL phai hien no, nhung hien TACH RIENG va ghi ro la
#   SO TINH RA, khong duoc tron vao doanh thu co chung tu.
#
# Params (form_dict, tat ca optional):
#   date_from, date_to : YYYY-MM-DD. Mac dinh = thang hien tai.
#   brand              : loc mot brand
#
# CACH TINH:
#   bien doi  = NMV x pct. Dong phi ghi ro SAN thang dong "Tat ca san".
#   co dinh   = fix_thang chia deu theo SO NGAY TRONG THANG, cong theo tung ngay
#               nam trong ky -> ky le thang van ra dung ty le.
#   muc san   = min_thang cung chia theo ngay. Neu (bien doi + co dinh) thap hon
#               muc san thi bu cho du. Vi du Pin Ha Noi 6% nhung khong duoi 50tr:
#               NMV ~200tr/thang thi 6% = 12tr, thu 50tr. Tu moc NMV 833.333.333
#               /thang tro len thi 6% vuot san va thu theo %.
#   Tach THUC TE va KE HOACH theo `loai_so` cua EC NMV Ngay - KHONG cong chung.

MGMT_DEPT = "Management - EC"
MAX_NGAY = 400
PLAT_ALL = "Tat ca san"

notes = []

# ---------------------------------------------------------------- quyen xem
session_user = frappe.session.user or ""
is_sysmgr = False
if session_user and session_user != "Guest":
    sm_rows = frappe.db.sql("""
        SELECT name FROM `tabHas Role`
        WHERE parent = %s AND parenttype = 'User' AND role = 'System Manager' LIMIT 1
    """, (session_user,))
    if sm_rows:
        is_sysmgr = True

viewer_dept = ""
if session_user and session_user != "Guest":
    emp_rows = frappe.db.sql("""
        SELECT department FROM `tabEmployee`
        WHERE user_id = %s AND status = 'Active' LIMIT 1
    """, (session_user,), as_dict=True)
    if emp_rows:
        viewer_dept = emp_rows[0].get("department") or ""

scope_mode = ""
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
        "message": "Ban khong co quyen xem bao cao PnL.",
        "scope": {"user": session_user, "mode": "", "department": viewer_dept},
    }
else:
    fd = frappe.form_dict or {}
    hom_nay = frappe.utils.today()
    date_from = (fd.get("date_from") or "").strip() or (str(hom_nay)[0:7] + "-01")
    date_to = (fd.get("date_to") or "").strip() or str(frappe.utils.get_last_day(hom_nay))
    f_brand = (fd.get("brand") or "").strip()

    if str(date_from) > str(date_to):
        tam = date_from
        date_from = date_to
        date_to = tam
        notes = notes + ["date_from lon hon date_to nen da doi cho hai gia tri."]

    so_ngay = frappe.utils.date_diff(date_to, date_from) + 1
    if so_ngay > MAX_NGAY:
        date_to = str(frappe.utils.add_days(date_from, MAX_NGAY - 1))
        so_ngay = MAX_NGAY
        notes = notes + ["Ky qua dai, da cat con " + str(MAX_NGAY) + " ngay."]

    # ------------------------------------------------------ bang muc phi
    phi_rows = frappe.db.sql("""
        SELECT name, brand, platform, pct, fix_thang, min_thang, tu_ngay, den_ngay
        FROM `tabEC Phi Quan Ly Brand`
        WHERE ifnull(tu_ngay, '1900-01-01') <= %s
          AND (den_ngay IS NULL OR den_ngay = '' OR den_ngay >= %s)
        ORDER BY brand, platform, tu_ngay
    """, (date_to, date_from), as_dict=True)

    phi = []
    for r in phi_rows:
        if f_brand and (r.get("brand") or "") != f_brand:
            continue
        phi = phi + [{
            "name": r.get("name") or "",
            "brand": r.get("brand") or "",
            "platform": r.get("platform") or PLAT_ALL,
            "pct": float(r.get("pct") or 0),
            "fix": float(r.get("fix_thang") or 0),
            "min": float(r.get("min_thang") or 0),
            "tu": str(r.get("tu_ngay") or "1900-01-01"),
            "den": str(r.get("den_ngay") or ""),
        }]

    def hop_le(dong, ngay):
        if dong["tu"] > ngay:
            return 0
        if dong["den"] and dong["den"] < ngay:
            return 0
        return 1

    def tim_dong(ten_brand, san, ngay):
        khop_san = None
        khop_all = None
        for d in phi:
            if d["brand"] != ten_brand:
                continue
            if not hop_le(d, ngay):
                continue
            if d["platform"] == san:
                khop_san = d
            elif d["platform"] == PLAT_ALL:
                khop_all = d
        if khop_san:
            return khop_san
        return khop_all

    # ------------------------------------------------------ NMV trong ky
    nmv_where = "ngay >= %s AND ngay <= %s"
    nmv_args = (date_from, date_to)
    if f_brand:
        nmv_where = nmv_where + " AND brand = %s"
        nmv_args = (date_from, date_to, f_brand)

    nmv_rows = frappe.db.sql("""
        SELECT brand, platform, ngay, nmv, loai_so
        FROM `tabEC NMV Ngay`
        WHERE """ + nmv_where + """
        ORDER BY ngay, brand, platform
    """, nmv_args, as_dict=True)

    # ------------------------------------------------------ cong don
    acc = {}          # ten dong phi -> so lieu
    ngay_map = {}     # ngay -> {thuc, ke_hoach}
    thieu = {}        # brand|san khong co muc phi -> nmv
    tong_nmv_thuc = 0.0
    tong_nmv_kh = 0.0

    def bao_dam(ten, dong):
        if ten not in acc:
            acc[ten] = {
                "brand": dong["brand"], "platform": dong["platform"],
                "pct": dong["pct"], "fix_thang": dong["fix"], "min_thang": dong["min"],
                "nmv_thuc": 0.0, "nmv_kh": 0.0,
                "bien_thuc": 0.0, "bien_kh": 0.0,
                "co_dinh": 0.0, "san": 0.0,
            }

    def bao_dam_ngay(ng):
        if ng not in ngay_map:
            ngay_map[ng] = {"ngay": ng, "thuc": 0.0, "ke_hoach": 0.0}

    for r in nmv_rows:
        ten_brand = r.get("brand") or ""
        san = r.get("platform") or ""
        ngay = str(r.get("ngay") or "")
        gia_tri = float(r.get("nmv") or 0)
        la_thuc = 1
        if (r.get("loai_so") or "Thuc te") != "Thuc te":
            la_thuc = 0

        if la_thuc:
            tong_nmv_thuc = tong_nmv_thuc + gia_tri
        else:
            tong_nmv_kh = tong_nmv_kh + gia_tri

        dong = tim_dong(ten_brand, san, ngay)
        if not dong:
            khoa = ten_brand + " | " + san
            if khoa not in thieu:
                thieu[khoa] = {"brand": ten_brand, "platform": san, "nmv": 0.0, "so_dong": 0}
            thieu[khoa]["nmv"] = thieu[khoa]["nmv"] + gia_tri
            thieu[khoa]["so_dong"] = thieu[khoa]["so_dong"] + 1
            continue

        bao_dam(dong["name"], dong)
        tien = gia_tri * dong["pct"] / 100.0
        bao_dam_ngay(ngay)
        if la_thuc:
            acc[dong["name"]]["nmv_thuc"] = acc[dong["name"]]["nmv_thuc"] + gia_tri
            acc[dong["name"]]["bien_thuc"] = acc[dong["name"]]["bien_thuc"] + tien
            ngay_map[ngay]["thuc"] = ngay_map[ngay]["thuc"] + tien
        else:
            acc[dong["name"]]["nmv_kh"] = acc[dong["name"]]["nmv_kh"] + gia_tri
            acc[dong["name"]]["bien_kh"] = acc[dong["name"]]["bien_kh"] + tien
            ngay_map[ngay]["ke_hoach"] = ngay_map[ngay]["ke_hoach"] + tien

    # ------------------------------------------ phi co dinh + muc san theo ngay
    ngay_chay = date_from
    i = 0
    while i < so_ngay:
        ngay_chay = str(frappe.utils.add_days(date_from, i))
        cuoi_thang = str(frappe.utils.get_last_day(ngay_chay))
        ngay_trong_thang = int(cuoi_thang[8:10])
        for d in phi:
            if not hop_le(d, ngay_chay):
                continue
            if d["fix"] == 0 and d["min"] == 0:
                continue
            bao_dam(d["name"], d)
            if d["fix"]:
                phan = d["fix"] / float(ngay_trong_thang)
                acc[d["name"]]["co_dinh"] = acc[d["name"]]["co_dinh"] + phan
                bao_dam_ngay(ngay_chay)
                ngay_map[ngay_chay]["thuc"] = ngay_map[ngay_chay]["thuc"] + phan
            if d["min"]:
                acc[d["name"]]["san"] = acc[d["name"]]["san"] + d["min"] / float(ngay_trong_thang)
        i = i + 1

    # ------------------------------------------------------ gop theo brand
    theo_brand = {}
    tong = {"nmv_thuc": 0.0, "nmv_kh": 0.0, "bien_thuc": 0.0, "bien_kh": 0.0,
            "co_dinh": 0.0, "bu_san": 0.0, "tong_thuc": 0.0, "tong_kh": 0.0}

    for ten in acc:
        a = acc[ten]
        goc = a["bien_thuc"] + a["bien_kh"] + a["co_dinh"]
        bu = 0.0
        if a["san"] > goc:
            bu = a["san"] - goc
        b = a["brand"]
        if b not in theo_brand:
            theo_brand[b] = {"brand": b, "nmv_thuc": 0.0, "nmv_kh": 0.0,
                             "bien_thuc": 0.0, "bien_kh": 0.0, "co_dinh": 0.0,
                             "bu_san": 0.0, "tong": 0.0, "dong": []}
        t = theo_brand[b]
        t["nmv_thuc"] = t["nmv_thuc"] + a["nmv_thuc"]
        t["nmv_kh"] = t["nmv_kh"] + a["nmv_kh"]
        t["bien_thuc"] = t["bien_thuc"] + a["bien_thuc"]
        t["bien_kh"] = t["bien_kh"] + a["bien_kh"]
        t["co_dinh"] = t["co_dinh"] + a["co_dinh"]
        t["bu_san"] = t["bu_san"] + bu
        t["dong"] = t["dong"] + [{
            "platform": a["platform"], "pct": a["pct"],
            "fix_thang": a["fix_thang"], "min_thang": a["min_thang"],
            "nmv_thuc": round(a["nmv_thuc"]), "nmv_kh": round(a["nmv_kh"]),
            "bien_thuc": round(a["bien_thuc"]), "bien_kh": round(a["bien_kh"]),
            "co_dinh": round(a["co_dinh"]), "bu_san": round(bu),
        }]

    ds_brand = []
    for b in theo_brand:
        t = theo_brand[b]
        t["tong"] = t["bien_thuc"] + t["bien_kh"] + t["co_dinh"] + t["bu_san"]
        tong["nmv_thuc"] = tong["nmv_thuc"] + t["nmv_thuc"]
        tong["nmv_kh"] = tong["nmv_kh"] + t["nmv_kh"]
        tong["bien_thuc"] = tong["bien_thuc"] + t["bien_thuc"]
        tong["bien_kh"] = tong["bien_kh"] + t["bien_kh"]
        tong["co_dinh"] = tong["co_dinh"] + t["co_dinh"]
        tong["bu_san"] = tong["bu_san"] + t["bu_san"]
        ds_brand = ds_brand + [{
            "brand": t["brand"],
            "nmv_thuc": round(t["nmv_thuc"]), "nmv_kh": round(t["nmv_kh"]),
            "bien_thuc": round(t["bien_thuc"]), "bien_kh": round(t["bien_kh"]),
            "co_dinh": round(t["co_dinh"]), "bu_san": round(t["bu_san"]),
            "tong": round(t["tong"]), "dong": t["dong"],
        }]
    ds_brand = sorted(ds_brand, key=lambda x: x["tong"], reverse=True)

    tong["tong_thuc"] = tong["bien_thuc"] + tong["co_dinh"] + tong["bu_san"]
    tong["tong_kh"] = tong["bien_kh"]

    # bu muc san rai deu ra cac ngay de bieu do khop voi tong
    if tong["bu_san"] and so_ngay:
        moi_ngay = tong["bu_san"] / float(so_ngay)
        j = 0
        while j < so_ngay:
            ng = str(frappe.utils.add_days(date_from, j))
            bao_dam_ngay(ng)
            ngay_map[ng]["thuc"] = ngay_map[ng]["thuc"] + moi_ngay
            j = j + 1

    ds_ngay = []
    for ng in sorted(ngay_map):
        ds_ngay = ds_ngay + [{
            "ngay": ng,
            "thuc": round(ngay_map[ng]["thuc"]),
            "ke_hoach": round(ngay_map[ng]["ke_hoach"]),
        }]

    ds_thieu = []
    for k in thieu:
        ds_thieu = ds_thieu + [{
            "brand": thieu[k]["brand"], "platform": thieu[k]["platform"],
            "nmv": round(thieu[k]["nmv"]), "so_dong": thieu[k]["so_dong"],
        }]
    ds_thieu = sorted(ds_thieu, key=lambda x: x["nmv"], reverse=True)

    if ds_thieu:
        notes = notes + [
            "Co " + str(len(ds_thieu)) + " cap brand/san co NMV nhung CHUA co muc phi - "
            "phan NMV do khong sinh dong phi nao. Them dong trong EC Phi Quan Ly Brand."
        ]
    if str(date_from)[0:7] != str(date_to)[0:7] or str(date_from)[8:10] != "01":
        notes = notes + [
            "Ky khong phai tron mot thang duong lich: phi co dinh va muc thu toi thieu "
            "duoc chia theo so ngay, nen con so la phan tuong ung cua ky chu khong phai "
            "ca thang."
        ]

    frappe.response["message"] = {
        "ok": True,
        "scope": {"user": session_user, "mode": scope_mode, "department": viewer_dept},
        "meta": {
            "date_from": date_from, "date_to": date_to, "so_ngay": so_ngay,
            "brand": f_brand,
            "nguon": "EC NMV Ngay x EC Phi Quan Ly Brand",
            "canh_bao_chinh": "SO TINH RA tu NMV, KHONG phai doanh thu co chung tu. "
                              "Khong duoc cong vao doanh thu Sales Order.",
            "generated_at": str(frappe.utils.now()),
            "notes": notes,
        },
        "tong": {
            "nmv_thuc": round(tong["nmv_thuc"]), "nmv_kh": round(tong["nmv_kh"]),
            "bien_thuc": round(tong["bien_thuc"]), "bien_kh": round(tong["bien_kh"]),
            "co_dinh": round(tong["co_dinh"]), "bu_san": round(tong["bu_san"]),
            "tong_thuc": round(tong["tong_thuc"]), "tong_kh": round(tong["tong_kh"]),
            "tong_ca_ky": round(tong["tong_thuc"] + tong["tong_kh"]),
        },
        "theo_brand": ds_brand,
        "theo_ngay": ds_ngay,
        "thieu_muc_phi": ds_thieu,
    }
