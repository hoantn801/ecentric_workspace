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

    def test_buoc_lead_do_cap_tren_ky_chu_khong_phai_nhan_su(self):
        # Luong moi buoc mot la LEAD. Neu HR cung bam duoc buoc nay thi mot nguoi ky
        # ca hai cua -> hai chu ky chi con la mot.
        don = [_don("HR-LAP-2026-00041", "phuong.nguyen@ecentric.vn", "lead")]
        self.assertEqual(_chay("linh.ngo@ecentric.vn", False, don),
                         ["HR-LAP-2026-00041"])
        self.assertEqual(_chay("huong.pham@ecentric.vn", True, don), [])

    def test_cap_tren_gian_tiep_cung_ky_duoc_buoc_lead(self):
        # Lead nghi/ban thi don khong duoc ket: cap cao hon van go duoc.
        don = [_don("HR-LAP-2026-00041", "phuong.nguyen@ecentric.vn", "lead")]
        self.assertEqual(_chay(CEO, True, don), ["HR-LAP-2026-00041"])

    def test_khong_co_vai_tro_hr_thi_khong_thay_don_buoc_nhan_su(self):
        # Quan ly truc tiep cua Phuong. Backend se nem 'Don nay cho Nhan su duyet
        # truoc', nen KHONG duoc hien nut -- nut bam vao bao loi con te hon khong nut.
        don = [_don("HR-LAP-2026-00041", "phuong.nguyen@ecentric.vn", "hr")]
        self.assertEqual(_chay("linh.ngo@ecentric.vn", False, don), [])

    def test_buoc_ceo_la_di_san_van_co_duong_ve_dich(self):
        # Tu 24/09 khong sinh them don nao o buoc nay. Nhung don lo nop truoc do
        # phai ve duoc dich, nen mo cho CA CEO va Nhan su - khong de cho mot nguoi.
        don = [_don("HR-LAP-2026-00041", "phuong.nguyen@ecentric.vn", "ceo")]
        self.assertEqual(_chay(CEO, True, don), ["HR-LAP-2026-00041"])
        self.assertEqual(_chay("huong.pham@ecentric.vn", True, don),
                         ["HR-LAP-2026-00041"])
        self.assertEqual(_chay("linh.ngo@ecentric.vn", False, don), [])

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

    def test_duyet_buoc_mot_bao_dung_la_con_cho_nguoi_ke_tiep(self):
        # Luong moi: lead ky xong thi con Nhan su. Trang phai noi ro con mot chu ky
        # nua, neu khong nguoi duyet tuong xong roi va khong ai nhac buoc sau.
        src = self._trang()
        self.assertIn("chuyển Nhân sự ký bước cuối", src)
        self.assertNotIn("chuyển CEO ký bước cuối", src)

    def test_hang_cho_duyet_noi_ro_buoc_may(self):
        src = self._trang()
        self.assertIn("Bước 1/2", src)
        self.assertIn("Bước 2/2", src)


class TestLuongLeadRoiNhanSu(unittest.TestCase):
    """Luong moi (24/09, Hoan chot): LEAD -> NHAN SU -> xong, CC cho CEO.

    Truoc do la HR -> CEO, bo qua lead hoan toan: quan ly truc tiep khong he biet
    nguoi cua minh nghi, con don thi doi chu ky cua nguoi ban nhat cong ty."""

    def test_don_hieu_hi_sinh_ra_o_buoc_lead(self):
        src = _script("ec_hr_leave_apply")
        i = src.index("if lt in TWO_STEP:")
        khoi = src[i:i + 500]
        self.assertIn("stage = 'lead'", khoi)
        self.assertIn("order by lft desc limit 1", khoi,
                      "lead phai doc theo cay de tu nhay qua ca 'lead tu nop don'")

    def test_nguoi_dung_dau_cong_ty_nop_don_thi_khong_ket(self):
        # Khong con ai o tren -> giao thang Nhan su. Tha mot chu ky con hon mot don
        # khong ai bam duoc (dung cai bay da lam 3 don nam im).
        src = _script("ec_hr_leave_apply")
        i = src.index("if lt in TWO_STEP:")
        self.assertIn("if not appr:", src[i:i + 900])

    def test_buoc_nhan_su_la_buoc_cuoi_khong_con_chuyen_CEO(self):
        src = _script("ec_hr_leave_decide")
        i = src.index("elif stage == 'hr':")
        khoi = src[i:i + 420]
        self.assertIn("la.submit()", khoi)
        self.assertNotIn("'stage': 'ceo'", khoi)

    def test_hr_khong_ky_duoc_buoc_lead(self):
        src = _script("ec_hr_leave_decide")
        i = src.index("if stage == 'lead':")
        dieu_kien = src[i:i + 160]
        self.assertIn("mgr_user", dieu_kien)
        self.assertIn("is_ancestor_mgr", dieu_kien)
        self.assertNotIn("is_hr", dieu_kien)

    def test_CEO_duoc_CC_khi_don_xong(self):
        src = _script("ec_hr_leave_decide")
        self.assertIn("ec-lv-cc-ceo-v1", src)
        i = src.index("ec-lv-cc-ceo-v1")
        khoi = src[i:i + 900]
        self.assertIn("'for_user': CEO_USER", khoi)
        # Chi bao o chuong. Tao ToDo cho CEO la bien nguoi vua duoc go khoi duong
        # duyet thanh nguoi co them mot hang cho trong danh sach viec.
        self.assertNotIn("'doctype': 'ToDo'", khoi)

    def test_nhac_viec_di_theo_nguoi_duyet_ke_tiep(self):
        src = _script("ec_hr_leave_decide")
        self.assertIn("'allocated_to': nxt_user", src)
        self.assertNotIn("'allocated_to': CEO_USER", src)


class TestPatchDuaDonVeBuocLead(unittest.TestCase):
    """3 don lo nop theo luong cu dang dung o buoc 'hr'. De nguyen thi Nhan su ky
    mot chu la xong - quan ly van khong duoc hoi lan nao."""

    def _src(self):
        path = os.path.join(_repo_root(), "hr", "patches",
                            "p001_leave_two_step_back_to_lead.py")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_da_dang_ky_trong_patches_txt(self):
        with open(os.path.join(_repo_root(), "patches.txt"), encoding="utf-8") as fh:
            self.assertIn("hr.patches.p001_leave_two_step_back_to_lead", fh.read())

    def test_chi_dung_toi_don_chua_xu_ly(self):
        src = self._src()
        self.assertIn('"docstatus": 0', src)
        self.assertIn('"status": "Open"', src)
        self.assertIn('"ec_approval_stage": "hr"', src)

    def test_doi_ca_nguoi_duyet_va_nhac_viec(self):
        # Doi moi mot truong stage thi don im lang nam trong 'Viec can lam' cua
        # nguoi khong con trach nhiem - dung kieu hong vua phai sua.
        src = self._src()
        self.assertIn('"leave_approver": lead', src)
        self.assertIn("_chuyen_todo", src)

    def test_khong_tim_duoc_lead_thi_de_nguyen(self):
        src = self._src()
        i = src.index("if not lead:")
        self.assertIn("continue", src[i:i + 320])

    def test_khong_bao_gio_nem_loi(self):
        # Patch chay trong migrate: nem loi la chan ca lan deploy.
        self.assertIn("except Exception:", self._src())
