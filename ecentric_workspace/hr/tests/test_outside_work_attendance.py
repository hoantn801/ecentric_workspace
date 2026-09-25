# Copyright (c) 2026, eCentric and contributors
"""Ngay lam viec ben ngoai da duyet KHONG duoc tinh la thieu cong.

BOI CANH (25/09)
    `outside_work/application/service.py` ghi thang trong docstring:
    "No fulfillment, no attendance update (v1)". Va `_should_skip` cua bo nhac cham
    cong chi biet ba thu: ngay le, nghi phep da duyet, da cham cong. Ca ba script HR
    (`attendance_data`, `leave_data`, `today_state`) khong he nhac toi outside work.

    Hau qua doc duoc tren prod: don key live 28->30/09 cua mot ban, DU DA DUYET, van
    lam ban do bi nhac cham cong ca ba sang, bi dem ba ngay thieu cong cuoi thang, va
    bi keo diem SLA nhom 'Cham cong'. Cong ty duyet cho di, roi phat vi da di.

RANH GIOI CO Y GIU
    Ngay outside work duoc dem RIENG (`summary.outside`), KHONG gop vao `present`.
    Chuyen ngay do co tinh du cong hay khong la quyet dinh cua C&B, khong phai cua
    man hinh nay - doan sai thi sai vao luong. O day chi khang dinh mot dieu chac
    chan: do khong phai ngay thieu cong.
"""
import json
import os
import unittest


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


def _script(name):
    with open(os.path.join(_repo_root(), "fixtures", "server_script.json"),
              encoding="utf-8") as fh:
        rows = json.load(fh)
    hit = [r for r in rows if r.get("name") == name]
    assert len(hit) == 1, name
    return hit[0]["script"]


def _page(route):
    with open(os.path.join(_repo_root(), "fixtures", "web_page.json"),
              encoding="utf-8") as fh:
        rows = json.load(fh)
    hit = [r for r in rows if r.get("route") == route]
    assert len(hit) == 1, route
    return hit[0].get("main_section_html") or hit[0].get("main_section") or ""


class TestNhacChamCongBoQuaNgayDiNgoai(unittest.TestCase):

    def _src(self):
        with open(os.path.join(_repo_root(), "hr", "checkin_reminder.py"),
                  encoding="utf-8") as fh:
            return fh.read()

    def test_should_skip_biet_toi_outside_work(self):
        src = self._src()
        i = src.index("def _should_skip")
        self.assertIn("tabEC Outside Work Request", src[i:])

    def test_chi_tinh_don_DA_DUYET(self):
        # Don moi nop ma da mien cham cong thi ai cung co the tu mien cho minh.
        src = self._src()
        i = src.index("def _should_skip")
        self.assertIn("approval_status='Approved'", src[i:])

    def test_doc_trang_thai_tu_ban_ghi_engine(self):
        # STATE song o `EC Approval Request`; `EC Outside Work Request` chi la con
        # tro sang do. Doc trang thai tu ban ghi nghiep vu la doc nham cho.
        src = self._src()
        i = src.index("def _should_skip")
        self.assertIn("tabEC Approval Request", src[i:])


class TestManChamCongHieuOutsideWork(unittest.TestCase):

    def test_tra_ve_danh_sach_outside(self):
        s = _script("ec_hr_attendance_data")
        self.assertIn("'outside': outside", s)
        self.assertIn("approval_status='Approved'", s)

    def test_ngay_di_ngoai_khong_bi_dem_thieu_cong(self):
        s = _script("ec_hr_attendance_data")
        i = s.index("elif dcur < frappe.utils.nowdate():")
        khoi = s[i:i + 700]
        self.assertIn("if dcur not in off_by_day:", khoi)
        self.assertIn("sum_outside = sum_outside + 1", khoi)

    def test_khong_tu_quyet_la_du_cong(self):
        # Ranh gioi voi C&B: dem rieng, KHONG cong vao `present`.
        s = _script("ec_hr_attendance_data")
        i = s.index("elif off_by_day[dcur] == 'outside':")
        j = s.index("dcur = frappe.utils.add_days(dcur, 1)", i)
        nhanh = s[i:j]
        self.assertIn("sum_outside", nhanh)
        self.assertNotIn("sum_present", nhanh,
                         "ngay di ngoai KHONG duoc tu cong vao du cong - do la quyet dinh C&B")
        self.assertIn("'outside': sum_outside", s)

    def test_don_nghi_nhieu_ngay_khong_con_bi_dem_thieu_tu_ngay_thu_hai(self):
        # Ban cu so sanh `dcur not in [l['f'] for l in leaves]` - tuc chi doi chieu
        # NGAY BAT DAU cua don. Don nghi 3 ngay thi ngay 2 va 3 van bi dem thieu cong.
        # Cung dung mot khiem khuyet voi vu outside work, nen sua luon o day.
        s = _script("ec_hr_attendance_data")
        self.assertNotIn("[l2['f'] for l2 in leaves]", s)
        self.assertIn("off_by_day[dtmp] = 'leave'", s)


class TestLichHienChuOutsideWork(unittest.TestCase):

    def test_lich_co_nhan_va_mau_rieng(self):
        s = _page("ec-hr/attendance")
        self.assertIn("cls:'outside', label:'Outside work'", s)
        self.assertIn(".ha-day.outside{background:var(--sky)}", s)
        self.assertIn("--sky:#e0f2fe", s)

    def test_co_trong_chu_thich(self):
        s = _page("ec-hr/attendance")
        i = s.index('class="ha-legend"')
        self.assertIn("Outside work", s[i:i + 900])

    def test_xep_sau_ngay_le_nhung_truoc_moi_nhanh_thieu(self):
        # Ngay le / cuoi tuan von khong phai ngay lam viec nen phai thang; nhung
        # outside work PHAI chan duoc moi duong dan toi 'Thieu'.
        s = _page("ec-hr/attendance")
        i_hol = s.index("cls: hol.wo ? 'weekend' : 'holiday'")
        i_out = s.index("cls:'outside'")
        i_missing = s.index("label:'Thiếu'")
        self.assertLess(i_hol, i_out)
        self.assertLess(i_out, i_missing)

    def test_bam_vao_ngay_thi_mo_duoc_don(self):
        s = _page("ec-hr/attendance")
        self.assertIn("/approvals/outside-work?id=", s)


class TestMotCuaBaoVang(unittest.TestCase):

    def test_trang_nghi_phep_co_loi_sang_outside_work(self):
        s = _page("ec-hr/leave")
        self.assertIn('href="/approvals/outside-work"', s)
        self.assertIn("Làm việc bên ngoài", s)

    def test_khong_gop_engine(self):
        # Gop cua vao thi duoc; gop engine thi KHONG. Nghi phep an vao quy phep va
        # bang luong (Leave Application + Leave Ledger); outside work la don phe
        # duyet co nhieu cap va co SLA. Nhet outside work thanh mot loai Leave
        # Application se lam ban so quy phep - no khong tru phep.
        s = _page("ec-hr/leave")
        self.assertNotIn("Outside Work Request", _script("ec_hr_leave_apply"))
        self.assertIn("/approvals/outside-work", s)


class TestCuaSoLichCuaNhom(unittest.TestCase):
    """Trang cham cong co HAI bo dung lich, khong dung chung code.

    Lich chinh dung `classify()`. Cua so "Lịch công · <ten>" mo tu o chon nguoi
    trong nhom (`ec-attm-*`) co chuoi if/else RIENG va chu thich RIENG.

    Ban vá outside work dau tien chi sua lich chinh, nen trong cua so nay ngay
    24/09 cua ban Bao van roi xuong nhanh cuoi: co check-in luc 11:09 -> "Trễ".
    Hai bo dung song song la ly do mot sua khong bao gio du."""

    def _src(self):
        return _page("ec-hr/attendance")

    def test_modal_biet_outside_work(self):
        s = self._src()
        self.assertIn("var outDays={}", s)
        self.assertIn('cls="c-out";tag="Outside work"', s)

    def test_outside_chan_duoc_nhan_Tre(self):
        # Nguoi da duoc duyet lam viec ben ngoai thi moc 10:00 khong con y nghia.
        s = self._src()
        i_out = s.index('cls="c-out";tag="Outside work"')
        i_late = s.index('tag="Trễ";tm=ciByDay[ds];')
        self.assertLess(i_out, i_late, "nhanh outside phai dung TRUOC nhanh Thieu/Tre")

    def test_modal_co_chu_thich_rieng(self):
        s = self._src()
        i = s.index("Thiếu/Vắng")
        self.assertIn("Outside work", s[max(0, i - 400):i])

    def test_ca_hai_lich_deu_co_nhan(self):
        # Chot lai ca hai bo dung trong mot ca test, de lan sau ai them lich thu ba
        # thi cung phai nghi toi cho nay.
        s = self._src()
        self.assertEqual(s.count("Outside work") >= 3, True,
                         "lich chinh + cua so nhom + chu thich deu phai co nhan")
