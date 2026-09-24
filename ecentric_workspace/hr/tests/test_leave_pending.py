# Copyright (c) 2026, eCentric and contributors
"""Ai duoc thay nut Duyet tren man nghi phep (ec_hr_leave_data -> 'pending').

VI SAO CO FILE NAY
    24/09: don nghi cuoi cua mot ban nam im tu 04/09, don nghi hieu cua ban khac
    nam im tu 26/08. Khong ai lam sai ca -- chi la KHONG AI CO NUT de bam.
    `ec_hr_leave_apply` gan nguoi duyet bang cau "lay MOT HR Manager bat ky", va
    nguoi roi vao la mot nhan su LA trong cay to chuc (lft/rgt lien nhau, khong ai
    bao cao len). Ban cu cua 'Cho duyet' chi lay don cua nguoi nam trong nhanh DUOI
    minh -> danh sach cua ho vinh vien rong. Quyen thi co (ec_hr_leave_decide cho
    phep HR duyet buoc 'hr'), chi giao dien la khong moi.

TEST NAY CHAY TREN CHINH VAN BAN SCRIPT TRONG FIXTURE
    Khong chep lai logic ra day roi kiem ban sao -- lam vay thi ban sao dung con
    prod van hong. Ta doc script that tu server_script.json, exec no voi mot frappe
    gia, roi soi `frappe.response`. Script doi gi thi test vo hieu ngay lap tuc.
"""
import json
import os
import types
import unittest


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


def _script(name):
    path = os.path.join(_repo_root(), "fixtures", "server_script.json")
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    hit = [r for r in rows if r.get("name") == name]
    assert len(hit) == 1, name + " phai co dung mot ban ghi trong fixtures"
    return hit[0]["script"]


CEO = "lam.nguyen@ecentric.vn"

# Mot lat cat cay to chuc rut gon, lay dung hinh dang da gay ra su co tren prod.
#   Lam (CEO)      7 - 190   <- to tien cua tat ca
#     Linh          8 -  53
#       Phuong     23 -  40  <- nguoi nop don cuoi
#     Tuan        124 - 135
#       Huong     129 - 130  <- LA: khong ai bao cao len, nhung lai giu vai tro HR
#   Hoan           54 -  75  <- nhanh khac han
PEOPLE = {
    "lam.nguyen@ecentric.vn": ("HR-EMP-00026", 7, 190),
    "linh.ngo@ecentric.vn": ("HR-EMP-00010", 8, 53),
    "phuong.nguyen@ecentric.vn": ("HR-EMP-00030", 23, 40),
    "tuan.ly@ecentric.vn": ("HR-EMP-00011", 124, 135),
    "huong.pham@ecentric.vn": ("HR-EMP-00022", 129, 130),
    "hoan.tran@ecentric.vn": ("HR-EMP-00002", 54, 75),
}

# (name, employee, employee_name, leave_type, from, to, days, note, stage,
#  lft, rgt, user_id nguoi nop, user_id quan ly truc tiep)
def _don(name, nguoi_nop, stage, loai="Marriage Leave"):
    empn, lft, rgt = PEOPLE[nguoi_nop]
    quan_ly = {"phuong.nguyen@ecentric.vn": "linh.ngo@ecentric.vn",
               "huong.pham@ecentric.vn": "tuan.ly@ecentric.vn",
               "linh.ngo@ecentric.vn": CEO,
               "tuan.ly@ecentric.vn": CEO,
               "hoan.tran@ecentric.vn": CEO,
               CEO: ""}.get(nguoi_nop, "")
    return (name, empn, nguoi_nop.split("@")[0], loai, "2026-09-25", "2026-09-25",
            1, "", stage, lft, rgt, nguoi_nop, quan_ly)


class _Stub(object):
    """frappe gia, chi du cho ec_hr_leave_data chay."""

    def __init__(self, user, vai_tro_hr, don):
        self.session = types.SimpleNamespace(user=user)
        self.response = {}
        self._user = user
        self._hr = vai_tro_hr
        self._don = don
        self.db = types.SimpleNamespace(get_value=self._get_value, sql=self._sql)
        self.utils = types.SimpleNamespace(nowdate=lambda: "2026-09-24")

    def throw(self, msg):
        raise AssertionError("script nem loi: " + str(msg))

    def _get_value(self, doctype, filters, fields, as_dict=False):
        empn, lft, rgt = PEOPLE[self._user]
        out = {"name": empn, "employee_name": self._user, "department": "X",
               "reports_to": "", "company": "eCentric", "lft": lft, "rgt": rgt}
        return types.SimpleNamespace(**out)

    def _sql(self, query, params=None):
        q = " ".join(query.split())
        if "left join `tabEmployee` m on m.name=e.reports_to" in q:
            return list(self._don)
        if "tabHas Role" in q:
            return [("HR Manager",)] if self._hr else []
        if "tabLeave Type" in q:
            return []
        if "tabLeave Ledger Entry" in q:
            return [(0,)]
        return []


def _chay(user, vai_tro_hr, don):
    fr = _Stub(user, vai_tro_hr, don)
    exec(compile(_script("ec_hr_leave_data"), "ec_hr_leave_data", "exec"),
         {"frappe": fr})
    return [p["name"] for p in fr.response["message"]["pending"]]


class TestLeavePendingVisibility(unittest.TestCase):

    def test_hr_la_trong_cay_van_thay_don_buoc_nhan_su(self):
        # Day CHINH LA ca da hong tren prod: chi Huong giu vai tro HR nhung khong
        # ai bao cao len chi, nen ban cu khong bao gio hien nut cho chi.
        don = [_don("HR-LAP-2026-00041", "phuong.nguyen@ecentric.vn", "hr")]
        self.assertEqual(_chay("huong.pham@ecentric.vn", True, don),
                         ["HR-LAP-2026-00041"])

    def test_khong_co_vai_tro_hr_thi_khong_thay_don_buoc_nhan_su(self):
        # Quan ly truc tiep cua Phuong. Backend se nem 'Don nay cho Nhan su duyet
        # truoc', nen KHONG duoc hien nut -- nut bam vao bao loi con te hon khong nut.
        don = [_don("HR-LAP-2026-00041", "phuong.nguyen@ecentric.vn", "hr")]
        self.assertEqual(_chay("linh.ngo@ecentric.vn", False, don), [])

    def test_buoc_ceo_chi_ceo_chot(self):
        don = [_don("HR-LAP-2026-00041", "phuong.nguyen@ecentric.vn", "ceo")]
        self.assertEqual(_chay(CEO, True, don), ["HR-LAP-2026-00041"])
        self.assertEqual(_chay("huong.pham@ecentric.vn", True, don), [])

    def test_don_cua_chinh_ceo_thi_nhan_su_chot_buoc_cuoi(self):
        # Neu khong co nhanh nay thi don hieu/hi cua CEO ket cung: buoc cuoi bat
        # buoc CEO ky, ma chot 'khong ai tu duyet don minh' lai chan chinh CEO.
        don = [_don("HR-LAP-2026-00050", CEO, "ceo")]
        self.assertEqual(_chay("huong.pham@ecentric.vn", True, don),
                         ["HR-LAP-2026-00050"])
        self.assertEqual(_chay(CEO, True, don), [])

    def test_khong_ai_tu_duyet_don_cua_chinh_minh(self):
        don = [_don("HR-LAP-2026-00060", "huong.pham@ecentric.vn", "hr")]
        self.assertEqual(_chay("huong.pham@ecentric.vn", True, don), [])

    def test_phep_thuong_van_do_quan_ly_truc_tiep_duyet(self):
        # CO Y khong mo phep thuong cho HR du backend cho phep: mo ra thi 'Cho duyet'
        # cua HR se chua moi don phep nam cua ca cong ty, cai can xu ly chim trong
        # cai khong can.
        don = [_don("HR-LAP-2026-00070", "phuong.nguyen@ecentric.vn", "",
                    loai="Annual Leave")]
        self.assertEqual(_chay("linh.ngo@ecentric.vn", False, don),
                         ["HR-LAP-2026-00070"])
        self.assertEqual(_chay("huong.pham@ecentric.vn", True, don), [])

    def test_khong_thay_don_cua_nhanh_khac(self):
        don = [_don("HR-LAP-2026-00070", "phuong.nguyen@ecentric.vn", "",
                    loai="Annual Leave")]
        self.assertEqual(_chay("hoan.tran@ecentric.vn", False, don), [])

    def test_pending_mang_theo_stage_de_giao_dien_noi_duoc_buoc_nao(self):
        don = [_don("HR-LAP-2026-00041", "phuong.nguyen@ecentric.vn", "hr")]
        fr = _Stub("huong.pham@ecentric.vn", True, don)
        exec(compile(_script("ec_hr_leave_data"), "x", "exec"), {"frappe": fr})
        self.assertEqual(fr.response["message"]["pending"][0]["stage"], "hr")


class TestDecideVaDataKhopNhau(unittest.TestCase):
    """Hai script phai noi cung mot thu. Lech nhau la sinh ra nut bam vao bao loi,
    hoac don co quyen duyet ma khong ai nhin thay -- dung hai kieu hong vua gap."""

    def test_cung_mot_dinh_nghia_CEO(self):
        data = _script("ec_hr_leave_data")
        decide = _script("ec_hr_leave_decide")
        moc = "CEO_USER = '" + CEO + "'"
        self.assertIn(moc, data)
        self.assertIn(moc, decide)

    def test_data_khong_con_loc_thuan_theo_cay(self):
        data = _script("ec_hr_leave_data")
        self.assertIn("ec-lv-pending-v2", data)
        self.assertIn("is_hr", data)


class TestManNghiPhepNoiDungBuoc(unittest.TestCase):
    """Giao dien phai noi that ve chuyen gi vua xay ra.

    `ec_hr_leave_decide` tra ve status 'Open' cho buoc Nhan su -- vi don CHUA xong,
    no chi chuyen sang CEO. Ban cu cua trang doc "khong phai Approved" thanh
    "Da tu choi", nen nguoi vua DUYET lai nhin thay bao da TU CHOI."""

    def _trang(self):
        path = os.path.join(_repo_root(), "fixtures", "web_page.json")
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
        hit = [r for r in rows if r.get("route") == "ec-hr/leave"]
        self.assertEqual(len(hit), 1)
        return hit[0].get("main_section_html") or hit[0].get("main_section") or ""

    def test_khong_con_bao_tu_choi_khi_vua_duyet(self):
        src = self._trang()
        self.assertNotIn("m.status==='Approved'?'Đã duyệt ✓':'Đã từ chối'", src)
        self.assertIn("ec-lv-toast-v2", src)

    def test_buoc_nhan_su_bao_dung_la_con_cho_CEO(self):
        src = self._trang()
        self.assertIn("chuyển CEO ký bước cuối", src)

    def test_hang_cho_duyet_noi_ro_buoc_may(self):
        src = self._trang()
        self.assertIn("Bước 1/2", src)
        self.assertIn("Bước 2/2", src)
