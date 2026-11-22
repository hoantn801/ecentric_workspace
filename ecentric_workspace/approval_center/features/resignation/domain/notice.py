# Copyright (c) 2026, eCentric and contributors
"""Ngay lam viec cuoi SOM NHAT hop le khi NLD don phuong nghi viec (Dieu 35 BLLD 2019) - ham THUAN.

Khoan 1 Dieu 35: NLD co quyen don phuong cham dut HDLD, chi can bao truoc:
  a) it nhat 45 ngay - HD khong xac dinh thoi han;
  b) it nhat 30 ngay - HD xac dinh thoi han tu 12 den 36 thang;
  c) it nhat 03 ngay lam viec - HD xac dinh thoi han duoi 12 thang.
Thu viec (Dieu 27): moi ben huy thoa thuan thu viec khong can bao truoc.

Nguon: dong HD dang hieu luc trong Employee.ec_contracts (EC Employee Contract: loai_hop_dong,
tu_ngay, den_ngay, khong_thoi_han). Gia dinh da tu quyet (ghi o day de C&B / phap che soat):
  * "Thuc tap" khong phai HDLD -> khong ap thoi han bao truoc (nhu thu viec).
  * HDLD (lan n) KHONG co den_ngay va KHONG tick khong_thoi_han -> tinh nhu khong thoi han (45 ngay,
    muc chat nhat) va ghi chu "thieu ngay ket thuc" de C&B bo sung.
  * "Hop dong dich vu" / "Khac" / khong co dong nao -> khong tinh duoc (C&B kiem tay).
  * Thoi han HD tinh theo thang lich tu tu_ngay den den_ngay (lam tron theo ngay: >= 12 thang
    khi den_ngay >= tu_ngay + 12 thang - 1 ngay).
Khong cham DB: ben goi truyen danh sach dong HD + tap ngay le."""
import datetime as _dt

THU_VIEC = "Thử việc"
THUC_TAP = "Thực tập"
HDLD_PREFIX = "HĐLĐ"


def _d(v):
    if v is None or v == "":
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    import calendar
    return _dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def hop_dong_hien_hanh(contracts, ngay):
    """Dong HD phu `ngay` (tu_ngay <= ngay, va den_ngay >= ngay hoac khong co den_ngay); nhieu dong
    thi lay dong tu_ngay MOI NHAT. Khong co dong phu -> dong co tu_ngay moi nhat <= ngay (HD da het
    han nhung chua nhap HD moi - van dung lam can cu, kem ghi chu)."""
    ngay = _d(ngay)
    rows = [r for r in (contracts or []) if _d(r.get("tu_ngay")) and _d(r.get("tu_ngay")) <= ngay]
    phu = [r for r in rows if not _d(r.get("den_ngay")) or _d(r.get("den_ngay")) >= ngay]
    pick = phu or rows
    if not pick:
        return None, False
    pick = sorted(pick, key=lambda r: _d(r.get("tu_ngay")))[-1]
    return pick, bool(phu)


def _cong_ngay_lam_viec(tu, n, le):
    d = tu
    while n > 0:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5 and d not in le:
            n -= 1
    return d


def tinh_bao_truoc(contracts, ngay_bao, ngay_le=()):
    """-> dict {loai_hd, so_ngay, don_vi ("ngày"|"ngày làm việc"|None), ngay_som_nhat (date|None),
    can_bao_truoc (bool), quy_tac (chuoi hien cho nguoi duyet), ghi_chu (list)}."""
    ngay_bao = _d(ngay_bao)
    le = set(_d(x) for x in (ngay_le or ()))
    row, con_hieu_luc = hop_dong_hien_hanh(contracts, ngay_bao)
    out = {"loai_hd": None, "so_ngay": None, "don_vi": None, "ngay_som_nhat": None,
           "can_bao_truoc": True, "quy_tac": None, "ghi_chu": []}
    if not row:
        out["quy_tac"] = "Chưa có dòng hợp đồng trên hồ sơ - C&B kiểm thời hạn báo trước"
        out["ghi_chu"].append("thieu_hop_dong")
        return out
    loai = (row.get("loai_hop_dong") or "").strip()
    out["loai_hd"] = loai
    if not con_hieu_luc:
        out["ghi_chu"].append("hop_dong_da_het_han")
    if loai in (THU_VIEC, THUC_TAP):
        out.update(so_ngay=0, don_vi="ngày", ngay_som_nhat=ngay_bao, can_bao_truoc=False,
                   quy_tac="%s: không cần báo trước (Điều 27 BLLĐ 2019)" % loai)
        return out
    if not loai.startswith(HDLD_PREFIX):
        out["quy_tac"] = "Loại hợp đồng \"%s\" không thuộc Điều 35 - C&B kiểm" % (loai or "—")
        out["ghi_chu"].append("loai_khong_ap_dung")
        return out
    tu, den = _d(row.get("tu_ngay")), _d(row.get("den_ngay"))
    if row.get("khong_thoi_han") or not den:
        if not row.get("khong_thoi_han"):
            out["ghi_chu"].append("thieu_ngay_ket_thuc")
        out.update(so_ngay=45, don_vi="ngày", ngay_som_nhat=ngay_bao + _dt.timedelta(days=45),
                   quy_tac="HĐ không xác định thời hạn: báo trước ít nhất 45 ngày (Điều 35.1.a)")
        return out
    if den >= _add_months(tu, 12) - _dt.timedelta(days=1):
        out.update(so_ngay=30, don_vi="ngày", ngay_som_nhat=ngay_bao + _dt.timedelta(days=30),
                   quy_tac="HĐ xác định thời hạn 12–36 tháng: báo trước ít nhất 30 ngày (Điều 35.1.b)")
        return out
    out.update(so_ngay=3, don_vi="ngày làm việc", ngay_som_nhat=_cong_ngay_lam_viec(ngay_bao, 3, le),
               quy_tac="HĐ xác định thời hạn dưới 12 tháng: báo trước ít nhất 3 ngày làm việc (Điều 35.1.c)")
    return out


def som_hon_han(ngay_cuoi, ket_qua):
    """True khi NLD chon ngay lam viec cuoi TRUOC ngay som nhat hop le."""
    nsn = ket_qua and ket_qua.get("ngay_som_nhat")
    return bool(nsn and _d(ngay_cuoi) and _d(ngay_cuoi) < nsn)
