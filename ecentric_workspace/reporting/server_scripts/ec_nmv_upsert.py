# ============================================================================
# BAN SAO DOI CHIEU - KHONG PHAI CODE CHAY.
#
# Ban sao y het cua Server Script `ec_nmv_upsert` dang chay tren team.ecentric.vn
# (script_type = API, api_method = 'ec_nmv_upsert'). Frappe KHONG import file nay.
# Sua that = sua Server Script tren live qua REST roi cap nhat lai file nay trong
# CUNG mot commit. Cu phap tuan theo RestrictedPython.
#
# DocType di kem `EC NMV Ngay` co trong fixtures (hooks.py), schema theo repo.
# Du lieu NMV thi KHONG phai fixture - do PowerBI day vao hang ngay.
#   brand Link Brand (reqd) | platform Select (reqd) | ngay Date (reqd)
#   nmv Currency (reqd) | nguon Select | ghi_chu Small Text
#   autoname format:NMV-{brand}-{platform}-{ngay}
#   Quyen: System Manager + EC Finance ghi; EC CEO/HOF/CnB doc.
# Truong di kem tren Brand: `ec_phi_ql_pct` (Percent) - muc % thu tren NMV,
# va `ec_fabric_code` (Data) - ma brand ben Fabric, dung lam bang anh xa.
# ============================================================================

# ec_nmv_upsert - API nap NMV theo brand theo NGAY (nguon PowerBI / Omisell).
# Server Script, script_type = API, api_method = 'ec_nmv_upsert'
#
# Vao:  form_dict['rows'] = chuoi JSON, danh sach {brand, platform, ngay, nmv, nguon, ghi_chu}
#         brand    bat buoc. Nhan TEN brand (vd LOF-VN), hoac ma la khai san trong
#                  Brand.ec_fabric_code / Brand.ec_brand_code - xem ANH XA ben duoi.
#         platform bat buoc: Shopee | Lazada | TikTok | Other | Tat ca san.
#                  Khong phan biet hoa thuong, va nhan vai bi danh quen thuoc
#                  ('TikTok Shop', 'khac', 'all').
#         ngay     bat buoc, dang YYYY-MM-DD
#         nmv      bat buoc, so tien VND trong ngay CUA RIENG SAN DO
#         nguon    tuy chon, mac dinh PowerBI
# Ra:   {ok, tao_moi, cap_nhat, bo_qua, loi[...]}
#
# Idempotent: ten ban ghi la NMV-<brand>-<platform>-<ngay> nen chay lai cung mot file chi
# ghi de, khong bao gio de ra hai dong cho cung mot brand + san + ngay.
#
# CHONG CONG DOI: mot brand trong mot ngay hoac khai theo TUNG SAN, hoac khai mot dong
# 'Tat ca san' - KHONG duoc ca hai. Tron lai thi tong NMV cua ngay do gap doi ma khong ai
# nhin ra. API tu choi dong thu hai va noi ro dang vuong dong nao.
#
# ANH XA MA BRAND (11/09/2026): ma brand ben Fabric/PowerBI khong trung ten brand o day,
# va bang anh xa KHONG duoc nam trong notebook - them mot brand la phai sua code, khong ai
# nho. Bang anh xa song tren chinh ban ghi Brand:
#     Brand.ec_fabric_code   ma ben Fabric, nhieu ma thi ngan cach bang dau phay
#     Brand.ec_brand_code    ma cu cua eCentric, dung luon lam alias cho tien
# Thu tu tra: ten brand (khong phan biet hoa thuong) -> ec_fabric_code -> ec_brand_code.
# Khong tra duoc thi BAO LOI kem ma da gui, KHONG doan bua.
#
# Goi voi danh_muc=1 (khong kem rows) de LAY VE danh sach ma dang chap nhan - dung de ben
# Fabric tu doi chieu truoc khi day, khong ghi gi.
#
# QUYEN: Administrator / System Manager / EC Finance. Nguoi khac bi tu choi.
# KHONG dung cho doanh thu: so nay chi de DOI CHIEU phi quan ly gian hang
# (NMV x Brand.ec_phi_ql_pct) voi so thuc thu o ma REV_QL_TT tren Sales Order.
# Cong ca hai vao doanh thu la dem hai lan.

MAX_ROWS = 2000
PLATFORMS = ("Shopee", "Lazada", "TikTok", "Other", "Tat ca san")
PLAT_ALL = "Tat ca san"
PLAT_ALIAS = {"shopee": "Shopee", "lazada": "Lazada",
              "tiktok": "TikTok", "tiktok shop": "TikTok", "tiktokshop": "TikTok",
              "tiktok-shop": "TikTok", "tik tok": "TikTok",
              "other": "Other", "khac": "Other", "orther": "Other",
              "tat ca san": PLAT_ALL, "tatcasan": PLAT_ALL, "all": PLAT_ALL,
              "tat ca": PLAT_ALL, "total": PLAT_ALL}
WRITE_ROLES = ("System Manager", "EC Finance")

user = frappe.session.user or ""
allowed = 0
if user == "Administrator":
    allowed = 1
if not allowed and user and user != "Guest":
    rr = frappe.db.sql("""
        SELECT role FROM `tabHas Role` WHERE parent = %s AND parenttype = 'User'
    """, (user,))
    for row in rr:
        if row[0] in WRITE_ROLES:
            allowed = 1

if not allowed:
    frappe.response["message"] = {"ok": False, "error": "no_permission",
                                  "message": "Chi System Manager hoac EC Finance duoc nap NMV."}
else:
    fd = frappe.form_dict or {}

    # --- che do chi doc: tra ve danh muc ma dang chap nhan, khong ghi gi ---
    if fd.get("danh_muc"):
        dm = []
        for b in frappe.get_all("Brand", limit_page_length=0, order_by="name asc",
                                fields=["name", "ec_brand_code", "ec_fabric_code",
                                        "ec_status", "ec_phi_ql_pct"]):
            ma = []
            if b.get("ec_fabric_code"):
                for k in (b["ec_fabric_code"] or "").split(","):
                    if (k or "").strip():
                        ma = ma + [k.strip()]
            if b.get("ec_brand_code") and b["ec_brand_code"] != b["name"]:
                ma = ma + [b["ec_brand_code"]]
            dm = dm + [{"brand": b["name"], "ma_chap_nhan": ma,
                        "trang_thai": b.get("ec_status") or "",
                        "phi_pct": frappe.utils.flt(b.get("ec_phi_ql_pct"))}]
        frappe.response["message"] = {"ok": True, "danh_muc": dm,
                                      "platform": list(PLATFORMS),
                                      "ghi_chu": ("Gui 'brand' bang ten brand hoac mot trong "
                                                  "ma_chap_nhan. Thieu ma thi dien vao o 'Ma "
                                                  "brand ben Fabric / PowerBI' cua ban ghi Brand.")}
    else:
        raw = fd.get("rows")
        data = []
        parse_err = ""
        if not raw:
            parse_err = "Thieu tham so 'rows'."
        else:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except Exception as exc:
                parse_err = "rows khong phai JSON hop le: " + str(exc)[:120]

        if parse_err:
            frappe.response["message"] = {"ok": False, "error": "bad_input", "message": parse_err}
        elif len(data) > MAX_ROWS:
            frappe.response["message"] = {"ok": False, "error": "too_many",
                                          "message": "Toi da %d dong moi lan goi, dang gui %d."
                                                     % (MAX_ROWS, len(data))}
        else:
            # ten chuan -> chinh no ; ten thuong hoa va moi ma la -> ten chuan
            ten_chuan = {}
            alias = {}
            for b in frappe.get_all("Brand", limit_page_length=0,
                                    fields=["name", "ec_brand_code", "ec_fabric_code"]):
                ten = b["name"]
                ten_chuan[ten] = 1
                alias[ten.strip().lower()] = ten
            for b in frappe.get_all("Brand", limit_page_length=0,
                                    fields=["name", "ec_brand_code", "ec_fabric_code"]):
                ten = b["name"]
                ma_la = []
                if b.get("ec_fabric_code"):
                    for k in (b["ec_fabric_code"] or "").split(","):
                        ma_la = ma_la + [k]
                if b.get("ec_brand_code"):
                    ma_la = ma_la + [b["ec_brand_code"]]
                for k in ma_la:
                    kk = (k or "").strip().lower()
                    # ten chuan luon thang: khong cho mot ma la che ten cua brand khac
                    if kk and kk not in alias:
                        alias[kk] = ten

            seen_all = {}
            seen_plat = {}
            n_map = 0
            n_new = 0
            n_upd = 0
            n_skip = 0
            errs = []
            idx = 0
            for r in data:
                idx = idx + 1
                brand = (r.get("brand") or "").strip()
                plat = (r.get("platform") or "").strip()
                ngay = (r.get("ngay") or "").strip()[:10]
                nguon = (r.get("nguon") or "PowerBI").strip()
                ghi_chu = (r.get("ghi_chu") or "").strip()
                if not brand or not ngay:
                    n_skip = n_skip + 1
                    errs = errs + ["dong %d: thieu brand hoac ngay" % idx]
                    continue
                if brand not in ten_chuan:
                    goc = brand
                    brand = alias.get(brand.strip().lower()) or ""
                    if not brand:
                        n_skip = n_skip + 1
                        errs = errs + ["dong %d: khong tra duoc brand '%s'. Mo ban ghi Brand tuong "
                                       "ung tren ERP va dien ma nay vao o 'Ma brand ben Fabric / "
                                       "PowerBI' (ec_fabric_code), roi day lai." % (idx, goc)]
                        continue
                    n_map = n_map + 1
                if plat not in PLATFORMS:
                    plat = PLAT_ALIAS.get(plat.strip().lower()) or ""
                    if not plat:
                        n_skip = n_skip + 1
                        errs = errs + ["dong %d: platform '%s' khong hop le, phai la mot trong %s"
                                       % (idx, (r.get("platform") or ""), ", ".join(PLATFORMS))]
                        continue
                try:
                    nmv = frappe.utils.flt(r.get("nmv"))
                except Exception:
                    nmv = -1.0
                if nmv < 0:
                    n_skip = n_skip + 1
                    errs = errs + ["dong %d: nmv khong hop le" % idx]
                    continue
                # BAT BUOC dung YYYY-MM-DD. Khong de getdate() tu doan: PowerBI hay xuat
                # dd/mm/yyyy, va getdate('01/07/2026') tra ve 2026-01-07 - lech thang ma
                # khong bao loi. Do 10/09/2026 bang test, dung im lang la sai het du lieu.
                ok_fmt = 1
                if len(ngay) != 10:
                    ok_fmt = 0
                elif ngay[4] != "-" or ngay[7] != "-":
                    ok_fmt = 0
                elif not ngay[0:4].isdigit() or not ngay[5:7].isdigit() or not ngay[8:10].isdigit():
                    ok_fmt = 0
                d = None
                if ok_fmt:
                    try:
                        d = frappe.utils.getdate(ngay)
                    except Exception:
                        d = None
                if not d or str(d) != ngay:
                    n_skip = n_skip + 1
                    errs = errs + ["dong %d: ngay '%s' phai dung dang YYYY-MM-DD (vd 2026-07-01)"
                                   % (idx, ngay)]
                    continue
                # Chong cong doi: khong cho vua 'Tat ca san' vua tung san cho cung brand+ngay.
                bd = brand + "|" + ngay
                clash = ""
                if plat == PLAT_ALL:
                    if bd in seen_plat:
                        clash = "trong chinh lan gui nay"
                    elif frappe.get_all("EC NMV Ngay", limit_page_length=1, fields=["name"],
                                        filters={"brand": brand, "ngay": ngay,
                                                 "platform": ["!=", PLAT_ALL]}):
                        clash = "da co tren he thong"
                    if clash:
                        n_skip = n_skip + 1
                        errs = errs + ["dong %d: %s %s da khai theo TUNG SAN (%s), khong nhan them "
                                       "dong 'Tat ca san' - se cong doi"
                                       % (idx, brand, ngay, clash)]
                        continue
                    seen_all[bd] = 1
                else:
                    if bd in seen_all:
                        clash = "trong chinh lan gui nay"
                    elif frappe.get_all("EC NMV Ngay", limit_page_length=1, fields=["name"],
                                        filters={"brand": brand, "ngay": ngay,
                                                 "platform": PLAT_ALL}):
                        clash = "da co tren he thong"
                    if clash:
                        n_skip = n_skip + 1
                        errs = errs + ["dong %d: %s %s da co dong 'Tat ca san' (%s), khong nhan "
                                       "them dong theo san - se cong doi"
                                       % (idx, brand, ngay, clash)]
                        continue
                    seen_plat[bd] = 1
                key = "NMV-" + brand + "-" + plat + "-" + ngay
                try:
                    if frappe.db.exists("EC NMV Ngay", key):
                        frappe.db.set_value("EC NMV Ngay", key, {"nmv": nmv, "nguon": nguon,
                                                                 "ghi_chu": ghi_chu})
                        n_upd = n_upd + 1
                    else:
                        doc = frappe.get_doc({"doctype": "EC NMV Ngay", "brand": brand,
                                              "platform": plat, "ngay": ngay, "nmv": nmv,
                                              "nguon": nguon, "ghi_chu": ghi_chu})
                        doc.insert()
                        n_new = n_new + 1
                except Exception as exc2:
                    n_skip = n_skip + 1
                    errs = errs + ["dong %d (%s): %s" % (idx, key, str(exc2)[:120])]

            frappe.response["message"] = {"ok": True, "tao_moi": n_new, "cap_nhat": n_upd,
                                          "bo_qua": n_skip, "loi": errs[:20],
                                          "qua_anh_xa": n_map, "tong_gui": len(data)}
