# Copyright (c) 2026, eCentric and contributors
"""Mot nguoi o NHIEU cap duyet -> bo cac cap TRUOC, giu cap CUOI (Hoan chot 09/09).

EC-HIRE-2026-00003: nguoi de nghi la hoan.tran, quan ly truc tiep la anh Lam, ma anh Lam
cung la CEO -> luong co ca "Direct Manager Review" (cap 2) lan "CEO Review" (cap 4) deu tro
ve mot nguoi.

Engine truoc do da bo cap SAU (`_auto_skip_duplicate_level`, chay luc kich hoat). Doi sang bo
cap TRUOC vi hai ly do: tham quyen cao nhat phai nam o CUOI (CEO chot sau khi HR review, khong
phai truoc), va so sach phai ghi CEO duyet o o "CEO Review" chu khong phai o "Direct Manager
Review". Quyet dinh chay luc DUNG LUONG nen thanh tien trinh hien dung ngay tu luc gui.

Bo test giu sau dieu, moi dieu la mot cach hong that:
  1. Trung nguoi -> bo cap truoc, GIU cap sau.
  2. Cap cuoi cua moi nguoi khong bao gio bi bo -> khong the bo sach ca luong.
  3. Cap con nguoi duyet KHAC khong trung -> khong duoc bo (Any-One/All deu an toan).
  4. Cap `mandatory` -> khong duoc bo.
  5. Ba cap cung mot nguoi -> chi con cap cuoi.
  6. `_activate_level` gap cap da Skipped thi di thang, khong dung ToDo/SLA.

ENGINE CO HAI LUAT TRUNG-NGUOI, KHONG PHAI MOT (ghi 16/09 chieu, sau su co thu hai)
----------------------------------------------------------------------------------
  * `_skip_earlier_duplicate_levels` - bo cap TRUOC, chay MOT LAN luc dung luong;
  * `_auto_skip_duplicate_level`     - bo cap SAU,  chay MOI LAN kich hoat mot cap.

Sang 16/09 chot ky-so chi duoc dat o luat THU NHAT. Chieu cung ngay, EC-PAYR-2026-00164 va
EC-PAYR-2026-00161 van bi bo cap 3 - boi luat THU HAI, luc kich hoat:
    activated_at == completed_at == 15:48:00.697624, khong ai bam gi.
O "Kiem soat" tren to mau eContract khong nhan duoc lenh; ERP di tiep va ban lenh ky cho CEO
luc 16:56; eContract nuot lenh; chan ky CEO chet voi nhan `provider_accepted_but_silent`.

Nen bo test nay giu THEM:
  7. Trung nguoi + CO ky so -> KHONG duoc goi `_auto_skip_duplicate_level`.
  8. Trung nguoi + KHONG ky so -> VAN goi (luat 09/09 giu nguyen).
  9. Doc cau hinh that bai -> KHONG GOP (fail-closed), o CA HAI luat.
 10. Khong trung nguoi -> KHONG duoc hoi ho so ky so (moi lan kich hoat cap deu chay qua
     day; hoi thua la mot truy van DB cho moi cap cua moi phieu).
 11. MOI duong dan toi hai luat do deu phai di qua `_luong_co_ky_so` - phep kiem quet ma,
     de lan sau them mot luat trung-nguoi nua thi no do ngay chu khong cho toi production.
"""
import ast
import copy
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "shared")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_TRANS = os.path.join(_root(), "approval_center", "shared", "workflow", "transitions.py")


def _ma_thuc_thi(node_or_name):
    """Chi con ma THUC THI: bo chu thich (ast.unparse tu bo) VA bo docstring.

    `ast.get_docstring()` tra ban da dedent nen `.replace()` tren chuoi unparse khong khop -
    16/09 phep kiem "khong duoc dung get_active_profile" do vi chinh cai loi giai thich VI SAO
    khong dung no, nam trong docstring. Cat thang node docstring khoi cay thi khong con cua so
    nao de loi van lot qua.
    """
    goc = (node_or_name if isinstance(node_or_name, ast.FunctionDef)
           else ast.parse(_func_source(node_or_name)).body[0])
    node = copy.deepcopy(goc)
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body = node.body[1:] or [ast.copy_location(ast.Pass(), node)]
    return ast.unparse(ast.fix_missing_locations(node))


def _func_source(name):
    src = io.open(_TRANS, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError("khong thay ham %s" % name)


class _DB(object):
    def __init__(self, levels, approvers):
        self.levels = [dict(l) for l in levels]
        self.approvers = [dict(a) for a in approvers]
        self.writes = []

    def set_value(self, dt, name, values, *a, **k):
        self.writes.append((dt, name, dict(values) if isinstance(values, dict) else values))
        pool = self.levels if dt.endswith("Level") else self.approvers
        for row in pool:
            if row.get("name") == name and isinstance(values, dict):
                row.update(values)


class _Req(object):
    """Gia mot Document cua Frappe: co THUOC TINH va co ca `.get()`.

    Ban gia cu la `SimpleNamespace(name="REQ-1")` - khong co `.get()`, khong co
    `reference_doctype`. Tu 16/09 ham that hoi hai thu do de biet luong co ky so khong, nen
    ban gia thieu se nem AttributeError roi bi khoi `except` nuot mat -> ham tra ve som va
    MOI phep kiem o duoi xanh gia (khong gop thi dung la "khong bo cap nao"). Dung hinh dang
    that thi phep do moi noi that.
    """

    def __init__(self, approval_type="HIRING_REQUEST"):
        self.name = "REQ-1"
        self.reference_doctype = "EC Hiring Request"
        self._d = {"name": self.name, "approval_type": approval_type,
                   "reference_doctype": self.reference_doctype}

    def get(self, k, default=None):
        return self._d.get(k, default)


def _run_skip(levels, approvers, co_ky_so=False, guard_loi=False):
    import sys
    db = _DB(levels, approvers)
    frappe = types.ModuleType("frappe")
    frappe.db = db
    frappe.log_error = lambda *a, **k: None
    frappe.get_traceback = lambda: "TB"

    def get_all(dt, filters=None, fields=None, order_by=None, **kw):
        if dt.endswith("Level"):
            return sorted((dict(r) for r in db.levels), key=lambda r: r["level_no"])
        return [dict(r) for r in db.approvers]

    frappe.get_all = get_all
    logs = []
    ns = {
        "frappe": frappe,
        "now_datetime": lambda: "NOW",
        "log_action": lambda *a, **k: logs.append((a, k)),
        "_": lambda s: s,
    }
    # Ban gia cua tang ky so. `get_enabled_profile` tra ten ho so khi luong CO ky so.
    guard_mod = types.ModuleType("ecentric_workspace.platform.esign.guard")

    def _profile(ref_dt, atype):
        if guard_loi:
            raise RuntimeError("khong doc duoc cau hinh")
        return "EC-DSPROF-1" if co_ky_so else None

    guard_mod.get_enabled_profile = _profile
    esign_pkg = types.ModuleType("ecentric_workspace.platform.esign")
    esign_pkg.guard = guard_mod
    root = types.ModuleType("ecentric_workspace")
    plat = types.ModuleType("ecentric_workspace.platform")
    root.platform = plat
    plat.esign = esign_pkg
    gia = {"ecentric_workspace": root, "ecentric_workspace.platform": plat,
           "ecentric_workspace.platform.esign": esign_pkg,
           "ecentric_workspace.platform.esign.guard": guard_mod}
    saved = {k: sys.modules.get(k) for k in gia}
    sys.modules.update(gia)
    try:
        # Chot ky-so nam o ham DUNG CHUNG `_luong_co_ky_so` (dung chung voi luat bo-cap-SAU),
        # nen phai nap ca hai - va nap ban THAT, khong gia, de phep kiem noi ve ma that.
        exec(compile(_func_source("_luong_co_ky_so"), "<kyso>", "exec"), ns)
        exec(compile(_func_source("_skip_earlier_duplicate_levels"), "<skip>", "exec"), ns)
        ns["_skip_earlier_duplicate_levels"](_Req())
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return db, logs


def _lv(no, name=None, mandatory=0):
    return {"name": "RL-%d" % no, "level_no": no,
            "level_name": name or ("L%d" % no), "mandatory": mandatory,
            "level_status": "Pending"}


def _ap(no, user):
    return {"name": "AP-%d-%s" % (no, user), "level_no": no, "approver": user,
            "status": "Pending"}


def _status(db):
    return {l["level_no"]: l["level_status"] for l in db.levels}


class TestBoCapTruocGiuCapSau(unittest.TestCase):
    def test_ca_hire_00003_bo_cap_2_giu_cap_4(self):
        db, logs = _run_skip(
            [_lv(1, "Da gui"), _lv(2, "Direct Manager"), _lv(3, "HR"), _lv(4, "CEO")],
            [_ap(1, "hoan@x"), _ap(2, "lam@x"), _ap(3, "hr@x"), _ap(4, "lam@x")])
        self.assertEqual(_status(db)[2], "Skipped", "cap Direct Manager phai bi bo")
        self.assertEqual(_status(db)[4], "Pending", "cap CEO phai GIU")
        self.assertEqual(_status(db)[3], "Pending", "cap HR khong lien quan, phai giu")
        self.assertTrue(logs, "phai ghi audit cho tung nguoi bi bo")

    def test_cap_cuoi_cua_moi_nguoi_khong_bao_gio_bi_bo(self):
        db, _l = _run_skip([_lv(1), _lv(2)], [_ap(1, "a@x"), _ap(2, "a@x")])
        self.assertEqual(_status(db)[2], "Pending",
                         "bo ca hai thi khong con ai duyet - khong duoc phep")

    def test_ba_cap_cung_mot_nguoi_chi_con_cap_cuoi(self):
        db, _l = _run_skip([_lv(1), _lv(2), _lv(3)],
                           [_ap(1, "a@x"), _ap(2, "a@x"), _ap(3, "a@x")])
        self.assertEqual(_status(db), {1: "Skipped", 2: "Skipped", 3: "Pending"})


class TestKhongDuocBoNham(unittest.TestCase):
    def test_con_nguoi_duyet_khac_khong_trung_thi_giu_ca_cap(self):
        """Cap 2 co lam@x (trung cap 4) VA hr@x (khong trung) -> hr@x van phai bam."""
        db, _l = _run_skip([_lv(1), _lv(2), _lv(4)],
                           [_ap(1, "req@x"), _ap(2, "lam@x"), _ap(2, "hr@x"), _ap(4, "lam@x")])
        self.assertEqual(_status(db)[2], "Pending")

    def test_cap_mandatory_VAN_bo_khi_trung_nguoi(self):
        """10/09: HIRING_REQUEST-V1 co CA BA cap mandatory=1 -> chot mandatory lam luat thanh
        vo dung. `mandatory` chan viec BO HAN mot cap theo dieu kien nghiep vu (bo that, khong
        ai xem); o day khong ai mat quyen xem xet - van dung nguoi do duyet, chi gop mot lan.
        `_auto_skip_duplicate_level` cung chua bao gio kiem mandatory."""
        db, _l = _run_skip([_lv(1, mandatory=1), _lv(2, mandatory=1), _lv(3, mandatory=1)],
                           [_ap(1, "lam@x"), _ap(2, "tuan@x"), _ap(3, "lam@x")])
        self.assertEqual(_status(db)[1], "Skipped", "cap 1 trung anh Lam -> phai bo")
        self.assertEqual(_status(db)[2], "Pending", "cap HR nguoi khac -> giu")
        self.assertEqual(_status(db)[3], "Pending", "cap CEO la lan cuoi -> giu")

    def test_LUONG_CO_KY_SO_thi_KHONG_GOP(self):
        """SU CO EC-PAYR-2026-00149 (16/09).

        Chi Lien (Finance) gui phieu; truong bo phan cua chi la chi Phuong, ma chi Phuong
        cung la HOF o cap 3. Luat gop bo cap 1 - va lam chuoi duyet 4 buoc cua ERP lech khoi
        chuoi 5 o ky cua eContract. Do duoc, nguyen van:

            next handler not named: no_eligible_recipient:1_de_xuat_0_duoc_nhan

        eContract tra loi khong ai nhan duoc buoc ke tiep, vi buoc ke tiep CUA NO van la
        "Truong bo phan" - cai o ERP vua bo. Lenh ky roi ve pool 7 truong phong, truot nguoi,
        `not_enough_signatures:have=1/need=2` lap 11 lan, roi Manual Review.
        """
        db, logs = _run_skip([_lv(1, "Direct Manager"), _lv(2, "Finance"), _lv(3, "HOF")],
                             [_ap(1, "phuong@x"), _ap(2, "lien@x"), _ap(3, "phuong@x")],
                             co_ky_so=True)
        self.assertEqual(_status(db), {1: "Pending", 2: "Pending", 3: "Pending"},
                         "luong co ky so thi KHONG duoc bo cap nao")
        self.assertEqual(logs, [], "khong ghi so vi khong bo gi")

    def test_KHONG_ky_so_thi_van_gop_nhu_cu(self):
        """Luat 09/09 van dung khi khong co to giay nao dong cung so o ky."""
        db, _logs = _run_skip([_lv(1, "Direct Manager"), _lv(2, "Finance"), _lv(3, "HOF")],
                              [_ap(1, "phuong@x"), _ap(2, "lien@x"), _ap(3, "phuong@x")],
                              co_ky_so=False)
        self.assertEqual(_status(db)[1], "Skipped")
        self.assertEqual(_status(db)[3], "Pending")

    def test_khong_doc_duoc_cau_hinh_thi_KHONG_GOP(self):
        """Doan nham huong nay: nguoi ta ky hai lan cho mot cau hoi - kho chiu, thay ngay,
        sua duoc. Doan nham huong kia: chuoi chu ky vo trong im lang."""
        db, _logs = _run_skip([_lv(1), _lv(2)], [_ap(1, "a@x"), _ap(2, "a@x")],
                              guard_loi=True)
        self.assertEqual(_status(db), {1: "Pending", 2: "Pending"})

    def test_hoi_ho_so_theo_CAU_HINH_khong_theo_cong_dang_mo(self):
        """`get_active_profile` phu thuoc cac cong thuc thi (integration/signing/bulk...).
        Dung ban do thi tat mot cai gate se AM THAM doi ca cau truc luong duyet."""
        # BO CHU THICH TRUOC KHI GREP. Chu thich cua chinh ban sua nay co nhac
        # `get_active_profile` de giai thich VI SAO khong dung no - de nguyen thi phep kiem
        # khop voi loi van cua chinh no, va cach "sua cho xanh" se la xoa mat loi giai thich.
        # `ast.unparse` bo sach comment, chi con ma THUC THI.
        ma = _ma_thuc_thi("_luong_co_ky_so")
        self.assertIn("get_enabled_profile", ma)
        self.assertNotIn("get_active_profile", ma)
        # Va khong ham nao khac trong file duoc tu di hoi bang duong rieng.
        cay_all = ast.parse(io.open(_TRANS, encoding="utf-8").read())
        for node in cay_all.body:
            if isinstance(node, ast.FunctionDef):
                self.assertNotIn("get_active_profile", _ma_thuc_thi(node),
                                 "%s dung get_active_profile - phai hoi CAU HINH" % node.name)

    def test_khong_trung_ai_thi_khong_dong_gi(self):
        db, logs = _run_skip([_lv(1), _lv(2)], [_ap(1, "a@x"), _ap(2, "b@x")])
        self.assertEqual(_status(db), {1: "Pending", 2: "Pending"})
        self.assertEqual(db.writes, [])
        self.assertEqual(logs, [])

    def test_mot_cap_duy_nhat_thi_khong_dong_gi(self):
        db, _l = _run_skip([_lv(1)], [_ap(1, "a@x")])
        self.assertEqual(db.writes, [])


class TestKichHoatBoQuaCapDaSkipped(unittest.TestCase):
    """`_activate_level` phai di thang qua cap da Skipped - khong ToDo, khong SLA."""

    def _run_activate(self, skipped):
        called = {"advance": [], "past_guard": False}
        ns = {
            "_is_level_skipped": lambda rn, no: skipped,
            "_advance_past_level": lambda req, no: called["advance"].append(no),
        }

        def _rl_for(rn, no):
            called["past_guard"] = True
            raise RuntimeError("DUNG-SAU-CHAN")

        ns["_rl_for"] = _rl_for
        exec(compile(_func_source("_activate_level"), "<act>", "exec"), ns)
        # cac ham phu khac chi duoc goi SAU chan; neu chan chay dung thi khong cham toi
        ns["_all_level_approvers_already_approved"] = lambda rn, no: False
        try:
            ns["_activate_level"](types.SimpleNamespace(name="REQ-1"), 2)
        except RuntimeError as exc:
            if "DUNG-SAU-CHAN" not in str(exc):
                raise
        return called

    def test_cap_skipped_thi_di_thang_khong_cham_phan_con_lai(self):
        c = self._run_activate(True)
        self.assertEqual(c["advance"], [2])
        self.assertFalse(c["past_guard"], "khong duoc chay tiep vao than ham")

    def test_cap_binh_thuong_thi_chay_tiep_nhu_cu(self):
        c = self._run_activate(False)
        self.assertEqual(c["advance"], [])
        self.assertTrue(c["past_guard"], "cap khong bi bo thi phai kich hoat binh thuong")


def _moi_truong_ky_so(co_ky_so, guard_loi, dem):
    """Ban gia tang ky so + bo nho dem so lan bi hoi. Tra ve (dict modules, guard_mod)."""
    guard_mod = types.ModuleType("ecentric_workspace.platform.esign.guard")

    def _profile(ref_dt, atype):
        dem["hoi_ky_so"] += 1
        if guard_loi:
            raise RuntimeError("khong doc duoc cau hinh")
        return "EC-DSPROF-1" if co_ky_so else None

    guard_mod.get_enabled_profile = _profile
    esign_pkg = types.ModuleType("ecentric_workspace.platform.esign")
    esign_pkg.guard = guard_mod
    root = types.ModuleType("ecentric_workspace")
    plat = types.ModuleType("ecentric_workspace.platform")
    root.platform = plat
    plat.esign = esign_pkg
    return {"ecentric_workspace": root, "ecentric_workspace.platform": plat,
            "ecentric_workspace.platform.esign": esign_pkg,
            "ecentric_workspace.platform.esign.guard": guard_mod}


def _run_activate_trung_nguoi(trung=True, co_ky_so=False, guard_loi=False):
    """Chay THAT `_activate_level` + `_luong_co_ky_so` voi cac ham xung quanh la ban gia."""
    import sys
    dem = {"hoi_ky_so": 0}
    goi = {"auto_skip": [], "toi_than_ham": False}
    frappe = types.ModuleType("frappe")
    frappe.log_error = lambda *a, **k: None
    frappe.get_traceback = lambda: "TB"

    def _rl_for(rn, no):
        goi["toi_than_ham"] = True
        raise RuntimeError("DUNG-SAU-CHAN")

    ns = {
        "frappe": frappe,
        "_is_level_skipped": lambda rn, no: False,
        "_advance_past_level": lambda req, no: None,
        "_all_level_approvers_already_approved": lambda rn, no: trung,
        "_auto_skip_duplicate_level": lambda req, no: goi["auto_skip"].append(no),
        "_rl_for": _rl_for,
    }
    gia = _moi_truong_ky_so(co_ky_so, guard_loi, dem)
    saved = {k: sys.modules.get(k) for k in gia}
    sys.modules.update(gia)
    try:
        exec(compile(_func_source("_luong_co_ky_so"), "<kyso>", "exec"), ns)
        exec(compile(_func_source("_activate_level"), "<act>", "exec"), ns)
        try:
            ns["_activate_level"](_Req(approval_type="PAYMENT_REQUEST"), 3)
        except RuntimeError as exc:
            if "DUNG-SAU-CHAN" not in str(exc):
                raise
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    goi["hoi_ky_so"] = dem["hoi_ky_so"]
    return goi


class TestBoCapSauKhongApKhiCoKySo(unittest.TestCase):
    """Luat THU HAI - `_auto_skip_duplicate_level`, chay luc kich hoat cap.

    SU CO EC-PAYR-2026-00164 (16/09 chieu). Chi Phuong duyet cap 1 luc 15:47:49, chi Lien
    duyet cap 2 luc 15:48:00, cap 3 (HOF - CUNG chi Phuong) vua kich hoat la bi bo ngay.
    """

    def test_trung_nguoi_va_CO_ky_so_thi_KHONG_bo_cap(self):
        c = _run_activate_trung_nguoi(trung=True, co_ky_so=True)
        self.assertEqual(c["auto_skip"], [], "luong co ky so thi KHONG duoc bo cap sau")
        self.assertTrue(c["toi_than_ham"], "phai kich hoat cap binh thuong de chi Phuong ky")

    def test_trung_nguoi_va_KHONG_ky_so_thi_VAN_bo_nhu_cu(self):
        """Luat 09/09 giu nguyen cho luong khong co to giay nao dong cung so o ky."""
        c = _run_activate_trung_nguoi(trung=True, co_ky_so=False)
        self.assertEqual(c["auto_skip"], [3])
        self.assertFalse(c["toi_than_ham"], "da bo cap thi khong kich hoat")

    def test_doc_cau_hinh_that_bai_thi_KHONG_bo_cap(self):
        c = _run_activate_trung_nguoi(trung=True, guard_loi=True)
        self.assertEqual(c["auto_skip"], [],
                         "khong doc duoc ho so -> fail-closed, khong duoc bo")
        self.assertTrue(c["toi_than_ham"])

    def test_khong_trung_nguoi_thi_KHONG_HOI_ho_so_ky_so(self):
        """`_activate_level` chay MOI lan kich hoat MOT cap cua MOI phieu. Hoi ho so ky so
        khi khong co gi de bo la mot truy van DB thua tren duong nong."""
        c = _run_activate_trung_nguoi(trung=False)
        self.assertEqual(c["hoi_ky_so"], 0)
        self.assertEqual(c["auto_skip"], [])
        self.assertTrue(c["toi_than_ham"])

    def test_co_trung_nguoi_thi_CO_hoi_dung_mot_lan(self):
        c = _run_activate_trung_nguoi(trung=True, co_ky_so=True)
        self.assertEqual(c["hoi_ky_so"], 1)


class TestFailClosedCuaHamDungChung(unittest.TestCase):
    def test_luong_co_ky_so_tra_True_khi_khong_doc_duoc(self):
        """Doan nham huong "coi nhu co ky so": nguoi ta ky hai lan cho mot cau hoi - kho
        chiu, thay ngay, sua duoc. Doan nham huong kia: mot o ky khong bao gio nhan duoc
        lenh, va phieu chet o buoc SAU do voi mot cai nhan khong chi ra nguyen nhan."""
        import sys
        dem = {"hoi_ky_so": 0}
        frappe = types.ModuleType("frappe")
        ghi = []
        frappe.log_error = lambda *a, **k: ghi.append(a)
        frappe.get_traceback = lambda: "TB"
        ns = {"frappe": frappe}
        gia = _moi_truong_ky_so(False, True, dem)
        saved = {k: sys.modules.get(k) for k in gia}
        sys.modules.update(gia)
        try:
            exec(compile(_func_source("_luong_co_ky_so"), "<kyso>", "exec"), ns)
            ket = ns["_luong_co_ky_so"](_Req(), "phep-kiem")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        self.assertIs(ket, True)
        self.assertTrue(ghi, "that bai phai duoc ghi so, khong duoc nuot im")

    def test_hai_luat_deu_di_qua_ham_dung_chung(self):
        """Phep kiem QUET MA: moi ham co dong toi mot trong hai luat trung-nguoi deu phai
        hoi `_luong_co_ky_so`. Them luat thu ba ma quen chot thi phep nay do ngay.

        Sang 16/09 chot dat o mot ham; docstring cua chinh ham do co nhac ten ham kia va no
        van bi de nguyen. Mot phep kiem quet duong dan bat duoc dieu do, mot phep kiem chi
        nhin mot ham thi khong.
        """
        src = io.open(_TRANS, encoding="utf-8").read()
        tree = ast.parse(src)
        ten_luat = {"_skip_earlier_duplicate_levels", "_auto_skip_duplicate_level"}

        def _goi_trong(node):
            return {n.func.id for n in ast.walk(node)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}

        ham = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for ten in ten_luat:
            self.assertIn(ten, ham, "luat %s bien mat - doi ten thi sua ca phep kiem" % ten)

        # Luat nao TU chot thi moi nguoi goi no deu an toan; luat nao khong tu chot thi
        # TUNG nguoi goi phai chot. Hai kieu deu dung, mien la khong co duong nao lot.
        tu_chot = {t for t in ten_luat if "_luong_co_ky_so" in _goi_trong(ham[t])}
        can_nguoi_goi_chot = ten_luat - tu_chot
        thieu = []
        for ten, node in ham.items():
            if ten in ten_luat:
                continue
            goi = _goi_trong(node)
            if (goi & can_nguoi_goi_chot) and "_luong_co_ky_so" not in goi:
                thieu.append(ten)
        self.assertEqual(sorted(thieu), [],
                         "cac ham nay goi mot luat trung-nguoi KHONG tu chot (%s) ma cung "
                         "khong tu hoi ho so ky so: %s"
                         % (sorted(can_nguoi_goi_chot), sorted(thieu)))
        # Va phai con it nhat mot trong hai duong duoc chot - de phep kiem khong xanh vi
        # ca hai luat cung bien mat khoi file.
        self.assertTrue(
            any("_luong_co_ky_so" in _goi_trong(n) for n in ham.values()),
            "khong ham nao trong transitions.py hoi `_luong_co_ky_so` nua")


class TestDungLuongCoGoi(unittest.TestCase):
    def test_build_snapshot_co_goi_ham_nay(self):
        """Ham dung ma khong ai goi thi vo nghia - va phai goi TRUOC khi cap quyen doc."""
        src = io.open(_TRANS, encoding="utf-8").read()
        tree = ast.parse(src)
        bs = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "build_snapshot"]
        self.assertTrue(bs)
        goi = [n.func.id for n in ast.walk(bs[0])
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertIn("_skip_earlier_duplicate_levels", goi)


if __name__ == "__main__":
    unittest.main(verbosity=2)
