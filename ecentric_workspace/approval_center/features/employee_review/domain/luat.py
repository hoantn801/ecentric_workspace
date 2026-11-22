# Copyright (c) 2026, eCentric and contributors
"""Luat THUAN cua Danh gia nhan su (khong frappe) - Hoan chot 22-23/11/2026.

KET QUA THEO LOAI
  * Thu viec : Dat / Khong dat. "Gia han" CHI khi (a) chua tung gia han lan nao (Dieu 25 BLLD 2019:
               chi thu viec MOT lan cho mot cong viec) va (b) tong thoi gian thu viec hien tai con
               DUOI tran; ngay gia han moi khong duoc vuot tran. Tran doc tu cau hinh theo chuc danh /
               chuc vu, mac dinh 60 ngay (cao dang tro len). Dat -> chon thoi han HDLD dau tien.
  * Thuc tap : Dat / Khong dat / Gia han (khong phai HDLD - khong rang buoc tran).
  * Hop dong : Gia han (chon thoi han HD moi) / Khong gia han. Dieu 20: da co 2 HD xac dinh thoi han
               thi HD tiep theo PHAI la khong xac dinh thoi han.
NHAN XET CUA LM: ket qua + nhan xet BAT BUOC; an voi nhan vien toi khi CEO duyet (`xem_phan_lm`).
SAU CEO: chi tao DE XUAT cap nhat ho so (`de_xuat_ho_so`) - C&B xac nhan mot cham, khong tu ghi.
"""
import datetime as _dt

from ecentric_workspace.hr.hop_dong import domain as hd

DAT = "Đạt"
KHONG_DAT = "Không đạt"
GIA_HAN = "Gia hạn"
KHONG_GIA_HAN = "Không gia hạn"
KXD = "Không xác định thời hạn"
THOI_HAN = (("12 tháng", 12), ("24 tháng", 24), ("36 tháng", 36), (KXD, None))
TRAN_MAC_DINH = 60
NHAN_XET_TOI_THIEU = 10
DIEM_MIN, DIEM_MAX = 1, 5

#: Truong cua LM / ket qua: business_redactor bo khoi man hinh nguoi khong duoc xem.
LM_FIELDS = ("lm_danh_gia_json", "lm_ket_qua", "lm_gia_han_den", "lm_thoi_han_hd", "lm_nhan_xet",
             "lm_gui_luc", "lm_boi", "ket_qua", "ket_qua_luc", "ho_so_trang_thai",
             "ho_so_de_xuat_json", "ho_so_xac_nhan_boi", "ho_so_xac_nhan_luc")
#: Role duoc xem phan LM (ngoai nguoi duyet cap 2/3 + nguoi gui) - TRU khi chinh ho la doi tuong.
ROLE_XEM_LM = ("EC CnB", "HR", "HR Manager", "EC CEO", "System Manager")


class LoiDanhGia(ValueError):
    """Du lieu danh gia khong hop le - message viet cho nguoi dung."""


def so_ngay(tu, den):
    """So ngay tinh ca hai dau."""
    tu, den = hd.as_date(tu), hd.as_date(den)
    return (den - tu).days + 1 if tu and den else 0


def tran_thu_viec(nv, quy_tac, mac_dinh=None):
    """Tran ngay thu viec cua nhan vien: quy tac Chuc danh truoc, roi Chuc vu (grade), roi mac dinh."""
    nv = nv or {}
    rules = list(quy_tac or [])
    for kieu, truong in (("Chức danh", "designation"), ("Chức vụ", "grade")):
        val = (nv.get(truong) or "").strip()
        for r in rules:
            if (r.get("ap_dung") or "Chức danh") == kieu and val \
                    and (r.get("gia_tri") or "").strip() == val and int(r.get("tran_ngay") or 0) > 0:
                return int(r["tran_ngay"])
    return int(mac_dinh or TRAN_MAC_DINH)


def lua_chon(review_type, dong, rows, tran=TRAN_MAC_DINH, da_gia_han=False):
    """Lua chon hop le cho LM (va CEO xem lai). Dung CHUNG cho man hinh va kiem o server.

    -> {"ket_qua": [{value, enabled, ly_do}], "thoi_han": [{value, enabled, ly_do}],
        "can_thoi_han_khi": [ket qua can chon thoi han], "gia_han_toi_da": "YYYY-MM-DD"|None,
        "can_ngay_gia_han": bool, "ghi_chu": [cau giai thich]}"""
    dong = dong or {}
    tu, den = hd.as_date(dong.get("tu_ngay")), hd.as_date(dong.get("den_ngay"))
    ghi_chu = []
    so_xdth = hd.so_hd_xac_dinh_thoi_han(rows)
    chi_kxd = so_xdth >= 2
    thoi_han = []
    for label, _m in THOI_HAN:
        ok = (label == KXD) or not chi_kxd
        thoi_han.append({"value": label, "enabled": ok,
                         "ly_do": "" if ok else "Đã có %d HĐ xác định thời hạn (Điều 20)" % so_xdth})
    out = {"ket_qua": [], "thoi_han": thoi_han, "can_thoi_han_khi": [], "gia_han_toi_da": None,
           "can_ngay_gia_han": False, "ghi_chu": ghi_chu, "tran": None}
    if review_type == hd.DG_THU_VIEC:
        out["tran"] = tran
        dai = so_ngay(tu, den)
        ly_do = ""
        if da_gia_han:
            ly_do = "Đã gia hạn thử việc một lần (Điều 25: thử việc chỉ một lần)"
        elif not tu or not den:
            ly_do = "Thiếu ngày bắt đầu / kết thúc thử việc"
        elif dai >= tran:
            ly_do = "Thời gian thử việc %d ngày đã chạm trần %d ngày (Điều 25)" % (dai, tran)
        out["ket_qua"] = [{"value": DAT, "enabled": True, "ly_do": ""},
                          {"value": KHONG_DAT, "enabled": True, "ly_do": ""},
                          {"value": GIA_HAN, "enabled": not ly_do, "ly_do": ly_do}]
        if not ly_do:
            out["gia_han_toi_da"] = str(tu + _dt.timedelta(days=tran - 1))
            out["can_ngay_gia_han"] = True
        out["can_thoi_han_khi"] = [DAT]
        ghi_chu.append("Trần thử việc của vị trí: %d ngày." % tran)
    elif review_type == hd.DG_THUC_TAP:
        out["ket_qua"] = [{"value": v, "enabled": True, "ly_do": ""} for v in (DAT, KHONG_DAT, GIA_HAN)]
        out["can_ngay_gia_han"] = True
    elif review_type == hd.DG_HOP_DONG:
        out["ket_qua"] = [{"value": GIA_HAN, "enabled": True, "ly_do": ""},
                          {"value": KHONG_GIA_HAN, "enabled": True, "ly_do": ""}]
        out["can_thoi_han_khi"] = [GIA_HAN]
        if chi_kxd:
            ghi_chu.append("Đã có %d HĐ xác định thời hạn (Điều 20): lần này chỉ được ký không xác "
                           "định thời hạn hoặc không gia hạn." % so_xdth)
    return out


def _tim(opts, value):
    return next((o for o in opts if o["value"] == value), None)


def kiem_danh_gia_lm(review_type, payload, chon, den_ngay, tieu_chi=()):
    """Kiem phan LM. Tra ve dict sach de ghi; sai -> LoiDanhGia."""
    p = payload or {}
    kq = (p.get("lm_ket_qua") or "").strip()
    opt = _tim(chon["ket_qua"], kq)
    if not opt:
        raise LoiDanhGia("Vui lòng chọn kết quả đánh giá.")
    if not opt["enabled"]:
        raise LoiDanhGia("Không chọn được “%s”: %s." % (kq, opt["ly_do"]))
    nx = (p.get("lm_nhan_xet") or "").strip()
    if len(nx) < NHAN_XET_TOI_THIEU:
        raise LoiDanhGia("Nhận xét của quản lý là bắt buộc (ít nhất %d ký tự)." % NHAN_XET_TOI_THIEU)
    clean = {"lm_ket_qua": kq, "lm_nhan_xet": nx[:5000], "lm_gia_han_den": None, "lm_thoi_han_hd": None,
             "lm_danh_gia_json": diem_hop_le(p.get("lm_diem"), tieu_chi, bat_buoc=False)}
    if kq == GIA_HAN and chon.get("can_ngay_gia_han"):
        moi = hd.as_date(p.get("lm_gia_han_den"))
        den = hd.as_date(den_ngay)
        if not moi:
            raise LoiDanhGia("Vui lòng chọn ngày gia hạn đến.")
        if den and moi <= den:
            raise LoiDanhGia("Ngày gia hạn phải sau ngày kết thúc hiện tại.")
        tran = hd.as_date(chon.get("gia_han_toi_da"))
        if tran and moi > tran:
            raise LoiDanhGia("Ngày gia hạn vượt trần thử việc (chậm nhất %s - Điều 25)."
                             % tran.strftime("%d/%m/%Y"))
        clean["lm_gia_han_den"] = str(moi)
    if kq in chon.get("can_thoi_han_khi", ()):
        th = (p.get("lm_thoi_han_hd") or "").strip()
        o = _tim(chon["thoi_han"], th)
        if not o:
            raise LoiDanhGia("Vui lòng chọn thời hạn hợp đồng mới.")
        if not o["enabled"]:
            raise LoiDanhGia("Không chọn được “%s”: %s." % (th, o["ly_do"]))
        clean["lm_thoi_han_hd"] = th
    return clean


def diem_hop_le(diem, tieu_chi, bat_buoc=True):
    """{"<so thu tu tieu chi>": {"diem": 1..5, "nhan_xet": "..."}} -> JSON-able dict da kiem."""
    diem = diem if isinstance(diem, dict) else {}
    out = {}
    for i, tc in enumerate(tieu_chi or ()):
        k = str(i)
        cell = diem.get(k) if isinstance(diem.get(k), dict) else {}
        raw = cell.get("diem")
        if raw in (None, ""):
            if bat_buoc:
                raise LoiDanhGia("Vui lòng chấm điểm tiêu chí “%s”." % (tc.get("tieu_chi") or k))
            continue
        try:
            n = int(raw)
        except (TypeError, ValueError):
            raise LoiDanhGia("Điểm tiêu chí “%s” không hợp lệ." % (tc.get("tieu_chi") or k))
        if not DIEM_MIN <= n <= DIEM_MAX:
            raise LoiDanhGia("Điểm phải từ %d đến %d." % (DIEM_MIN, DIEM_MAX))
        out[k] = {"diem": n, "nhan_xet": str(cell.get("nhan_xet") or "").strip()[:1000]}
    return out


def de_xuat_ho_so(review_type, ket_qua, dong, rows, thoi_han=None, gia_han_den=None):
    """De xuat cap nhat ho so sau khi CEO duyet. KHONG ghi gi - C&B xac nhan moi ghi.

    -> {"kieu": "them_dong"|"sua_den_ngay"|"khong", "dong_moi": {...}|None,
        "sua": {"dong", "den_ngay"}|None, "employment_type": str|None, "ghi_chu": str}"""
    dong = dong or {}
    den = hd.as_date(dong.get("den_ngay"))
    out = {"kieu": "khong", "dong_moi": None, "sua": None, "employment_type": None, "ghi_chu": ""}
    if ket_qua in (KHONG_DAT, KHONG_GIA_HAN):
        out["ghi_chu"] = ("Kết quả “%s”: không đổi hồ sơ. C&B làm thủ tục chấm dứt (thông báo, "
                          "quyết định, Clearance) theo quy trình nghỉ việc." % ket_qua)
        return out
    if ket_qua == GIA_HAN and review_type in (hd.DG_THU_VIEC, hd.DG_THUC_TAP):
        out.update(kieu="sua_den_ngay", sua={"dong": dong.get("name"), "den_ngay": str(gia_han_den)},
                   ghi_chu="Gia hạn %s đến %s trên chính dòng hợp đồng hiện hành."
                   % (review_type.lower(), gia_han_den))
        return out
    if not den:
        out["ghi_chu"] = "Dòng hợp đồng hiện hành thiếu ngày kết thúc - C&B nhập tay."
        return out
    tu_moi = den + _dt.timedelta(days=1)
    if review_type == hd.DG_THUC_TAP and ket_qua == DAT:
        out.update(kieu="them_dong", employment_type=hd.ET_PROBATION, dong_moi={
            "loai_hop_dong": hd.THU_VIEC, "tu_ngay": str(tu_moi),
            "den_ngay": str(hd.ket_thuc_sau_thang(tu_moi, hd.THANG_THU_VIEC_GOI_Y)),
            "khong_thoi_han": 0}, ghi_chu="Thực tập đạt: gợi ý chuyển thử việc 2 tháng - C&B sửa ngày nếu khác.")
        return out
    if (review_type == hd.DG_THU_VIEC and ket_qua == DAT) or \
            (review_type == hd.DG_HOP_DONG and ket_qua == GIA_HAN):
        thang = dict(THOI_HAN).get(thoi_han)
        moi = {"loai_hop_dong": hd.hdld_tiep_theo(rows), "tu_ngay": str(tu_moi),
               "den_ngay": str(hd.ket_thuc_sau_thang(tu_moi, thang)) if thang else None,
               "khong_thoi_han": 0 if thang else 1}
        out.update(kieu="them_dong", dong_moi=moi,
                   employment_type=hd.ET_FULLTIME if review_type == hd.DG_THU_VIEC else None,
                   ghi_chu="Thêm %s (%s) từ %s." % (moi["loai_hop_dong"], thoi_han or KXD, tu_moi))
    return out


def xem_phan_lm(viewer, subject, approved, viewer_roles=(), approver_tu_cap_2=False,
                la_nguoi_gui=False):
    """Nguoi xem co thay phan LM / ket qua khong.

    Doi tuong (nhan vien duoc danh gia) KHONG thay cho toi khi phieu Approved - ke ca khi ho
    giu role HR / EC CnB (tu xem nhan xet ve chinh minh truoc khi CEO chot la dung cai ma
    quyet dinh "an voi NV" muon chan)."""
    if not viewer or viewer == "Guest":
        return False
    if viewer == subject:
        return bool(approved)
    return bool(approved or approver_tu_cap_2 or la_nguoi_gui
                or set(viewer_roles or ()) & set(ROLE_XEM_LM))
