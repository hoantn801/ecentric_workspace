# Copyright (c) 2026, eCentric and contributors
"""Moc khao sat thu viec / thuc tap - THUAN (khong frappe).

Luat (Hoan chot 22-23/11/2026):
  * thu viec: ngay 7 / 30 / 45; thuc tap: ngay 30 / 60 / 75 - tinh tu `tu_ngay` cua dong hop
    dong Thu viec / Thuc tap tren ho so;
  * moc roi vao ngay nghi (T7/CN/le) thi doi sang ngay lam viec KE TIEP;
  * moc CUOI phai TRUOC ngay he thong tao nhap phieu "Danh gia nhan su" (D-21) - de ket qua
    khao sat kip dinh vao phieu. Moc cuoi roi vao / sau ngay do thi keo ve 2 ngay lam viec
    truoc ngay tao nhap (thiet ke v2 22/11: "moc 3 = 2 ngay lam viec truoc ngay tao nhap");
  * moc giua (khong phai moc cuoi) roi vao / sau ngay tao nhap thi BO (thu viec qua ngan);
  * moc nao khong con sau moc truoc no thi bo (khong giao hai khao sat cung mot ngay).

Giao MOT moc moi lan: chi moc i ma moc_i <= hom nay < moc_{i+1} (moc cuoi: < ngay tao nhap,
hoac 7 ngay neu khong biet ngay tao nhap). Job bi tat vai ngay / lan deploy dau tien KHONG
ban ca ba khao sat cung luc cho mot nguoi - chi moc dang mo.
"""
import datetime as _dt

from ecentric_workspace.hr.hop_dong import domain as hd

MOC = {
    hd.THU_VIEC: ((7, "KS_THU_VIEC_1"), (30, "KS_THU_VIEC_2"), (45, "KS_THU_VIEC_3")),
    hd.THUC_TAP: ((30, "KS_THUC_TAP_1"), (60, "KS_THUC_TAP_2"), (75, "KS_THUC_TAP_3")),
}
#: So ngay lam viec truoc ngay tao nhap ma moc cuoi bi keo ve.
LUI_MOC_CUOI_NGAY_LV = 2
#: Cua so giao moc cuoi khi khong biet ngay tao nhap (dong hop dong thieu den_ngay).
CUA_SO_MAC_DINH = 7


def cac_moc(loai_hop_dong, tu_ngay, ngay_nhap=None, ngay_le=()):
    """[(thu_tu 1..3, ma_mau, ngay_moc)] da ap moi luat o docstring module."""
    spec = MOC.get(loai_hop_dong)
    tu = hd.as_date(tu_ngay)
    if not spec or not tu:
        return []
    ngay_nhap = hd.as_date(ngay_nhap)
    out = []
    last = len(spec)
    for i, (off, ma) in enumerate(spec, 1):
        d = hd.tien_toi_ngay_lam_viec(tu + _dt.timedelta(days=off), ngay_le)
        if ngay_nhap and d >= ngay_nhap:
            if i != last:
                continue
            d = hd.lui_ngay_lam_viec(ngay_nhap, LUI_MOC_CUOI_NGAY_LV, ngay_le)
        if d <= tu or (out and d <= out[-1][2]):
            continue
        out.append((i, ma, d))
    return out


def moc_can_giao(moc, hom_nay, ngay_nhap=None):
    """Moc DANG MO hom nay (tuple cua cac_moc) hoac None."""
    hom_nay = hd.as_date(hom_nay)
    ngay_nhap = hd.as_date(ngay_nhap)
    for k, m in enumerate(moc):
        if m[2] > hom_nay:
            return None
        if k + 1 < len(moc):
            het = moc[k + 1][2]
        else:
            het = ngay_nhap or (m[2] + _dt.timedelta(days=CUA_SO_MAC_DINH))
        if hom_nay < het:
            return m
    return None
