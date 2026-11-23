"""HR v2 (23/11/2026) - cac luat THUAN: bao truoc Dieu 35, HOF co dieu kien, ngay lam viec, han NSP.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hr_v2_luat_thuan.py
"""
import datetime as dt
import importlib.util
import pathlib

APP = pathlib.Path(__file__).resolve().parents[3]


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, APP / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


N = _load("approval_center/features/resignation/domain/notice.py", "hrv2_notice")
H = _load("approval_center/features/offer_request/domain/hof_rule.py", "hrv2_hof")
S = _load("approval_center/shared/sla_ngay_lam_viec.py", "hrv2_sla") if False else None
D = dt.date


def c(loai, tu, den=None, ktn=0):
    return {"loai_hop_dong": loai, "tu_ngay": tu, "den_ngay": den, "khong_thoi_han": ktn}


# ---------------------------------------------------------------- Dieu 35
def test_khong_thoi_han_45_ngay():
    r = N.tinh_bao_truoc([c("HĐLĐ lần 3", "2024-01-01", None, 1)], D(2026, 11, 23))
    assert r["so_ngay"] == 45 and r["ngay_som_nhat"] == D(2027, 1, 7) and r["can_bao_truoc"]


def test_12_den_36_thang_30_ngay():
    r = N.tinh_bao_truoc([c("HĐLĐ lần 1", "2026-01-01", "2026-12-31")], D(2026, 11, 23))
    assert r["so_ngay"] == 30 and r["ngay_som_nhat"] == D(2026, 12, 23)


def test_duoi_12_thang_3_ngay_lam_viec_bo_cuoi_tuan_va_le():
    # Thu Sau 20/11/2026 -> T2 23, T3 24 (le), T4 25, T5 26 => ngay LV thu 3 = 26/11
    r = N.tinh_bao_truoc([c("HĐLĐ lần 1", "2026-06-01", "2026-12-31")], D(2026, 11, 20),
                         ngay_le=[D(2026, 11, 24)])
    assert r["so_ngay"] == 3 and r["don_vi"] == "ngày làm việc" and r["ngay_som_nhat"] == D(2026, 11, 26)


def test_bien_12_thang_dung_moc():
    # 01/01 -> 31/12 = du 12 thang (30 ngay); 01/01 -> 30/12 = duoi 12 thang (3 ngay LV)
    assert N.tinh_bao_truoc([c("HĐLĐ lần 1", "2026-01-01", "2026-12-31")], D(2026, 5, 4))["so_ngay"] == 30
    assert N.tinh_bao_truoc([c("HĐLĐ lần 1", "2026-01-01", "2026-12-30")], D(2026, 5, 4))["so_ngay"] == 3


def test_thu_viec_va_thuc_tap_khong_bao_truoc():
    for loai in ("Thử việc", "Thực tập"):
        r = N.tinh_bao_truoc([c(loai, "2026-10-01", "2026-12-01")], D(2026, 11, 23))
        assert r["so_ngay"] == 0 and r["ngay_som_nhat"] == D(2026, 11, 23) and not r["can_bao_truoc"]


def test_hdld_thieu_ngay_ket_thuc_tinh_45_kem_ghi_chu():
    r = N.tinh_bao_truoc([c("HĐLĐ lần 1", "2026-01-01")], D(2026, 11, 23))
    assert r["so_ngay"] == 45 and "thieu_ngay_ket_thuc" in r["ghi_chu"]


def test_lay_hop_dong_hien_hanh_moi_nhat():
    rows = [c("Thử việc", "2026-01-01", "2026-02-28"), c("HĐLĐ lần 1", "2026-03-01", "2027-02-28")]
    r = N.tinh_bao_truoc(rows, D(2026, 11, 23))
    assert r["loai_hd"] == "HĐLĐ lần 1" and r["so_ngay"] == 30


def test_khong_co_hop_dong_hoac_loai_khac_khong_tinh():
    assert N.tinh_bao_truoc([], D(2026, 11, 23))["ngay_som_nhat"] is None
    r = N.tinh_bao_truoc([c("Hợp đồng dịch vụ", "2026-01-01", "2027-01-01")], D(2026, 11, 23))
    assert r["ngay_som_nhat"] is None and "loai_khong_ap_dung" in r["ghi_chu"]


def test_som_hon_han():
    r = N.tinh_bao_truoc([c("HĐLĐ lần 1", "2026-01-01", "2026-12-31")], D(2026, 11, 23))
    assert N.som_hon_han(D(2026, 12, 22), r) and not N.som_hon_han(D(2026, 12, 23), r)
    assert not N.som_hon_han(D(2026, 1, 1), {"ngay_som_nhat": None})


# ---------------------------------------------------------------- HOF co dieu kien
def test_hof_bo_khi_khong_vuot():
    assert H.bo_cap_hof(20000000, 20000000)[0] is True
    assert H.bo_cap_hof(15000000, 20000000)[0] is True


def test_hof_giu_khi_vuot_hoac_thieu_du_lieu():
    assert H.bo_cap_hof(20000001, 20000000)[0] is False
    assert H.bo_cap_hof(None, 20000000)[0] is False
    assert H.bo_cap_hof(15000000, None)[0] is False
    assert H.bo_cap_hof(15000000, 0)[0] is False
    assert H.bo_cap_hof("abc", 20000000)[0] is False
    assert "20.000.000" in H.bo_cap_hof(15000000, 20000000)[1]
