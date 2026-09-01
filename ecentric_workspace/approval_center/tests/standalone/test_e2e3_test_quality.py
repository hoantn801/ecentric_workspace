# Copyright (c) 2026, eCentric and contributors
"""Cong QC cho CHINH BO TEST: khoa lai nhung bat bien ma 648 test hien co KHONG canh.

Vi sao co file nay (audit BOT 10 vong 3, 01/09/2026). Chay dot bien tren 30 diem sua o
transitions.py / esign / command_service: 21 bi bat, 9 SONG SOT. Song sot nghia la co the
XOA hoan toan doan code do ma ca 648 test van bao OK. Danh sach song sot deu cung mot ho:
cac chot kiem quyen va chot bat buoc ly do - thu khong bao gio duoc test vi "hien nhien
dung", cho den ngay ai do don dep no di.

Cu the, nhung dot bien KHONG bi bat:
  * approve()              bo `_signature_guard(...)`   -> dong cap can chu ky ma khong ky
  * reject()               bo `if not row: throw`        -> nguoi la tu choi duoc phieu
  * request_information()  bo `if not row: throw`        -> nguoi la tra lai duoc phieu
  * reject/cancel/request_information  bo bat buoc ly do
  * cancel_fulfillment()   bo `_assert_can_cancel`       -> ai cung huy giao viec duoc
  * _evaluate()            bo `if decision != "approved": return` -> dong cap khi CHUA du duyet

NAY LA CHOT SENTINEL, KHONG PHAI TEST HANH VI. No doc CAY CU PHAP (ast) cua ham that, nen
mot chu thich nhac ten ham khong lam no xanh, va no khong cat than ham theo do dai co dinh.
Nhung no van chi chung minh "loi goi con do", khong chung minh "loi goi lam dung viec".

  => Viec dung phai lam: viet test HANH VI cho tung dong o tren (goi ham that voi frappe gia
     lap, nhu test_e2e2_engine_guard_races.py dang lam) roi XOA bot sentinel tuong ung.
     Sentinel chi de vung mu khong tiep tuc rong ra trong luc cho.

Chay:
  python3 -m unittest discover -s ecentric_workspace/approval_center/tests/standalone \
      -p 'test_*.py'
"""
import ast
import io
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    """Goc goi `ecentric_workspace/` - do len chu khong ghep so bac thu muc co dinh."""
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()


def _read(*parts):
    path = os.path.join(_ROOT, *parts)
    if not os.path.isfile(path):
        raise AssertionError("khong doc duoc %s - duong dan da doi, sentinel dang mu" % path)
    return io.open(path, encoding="utf-8").read()


def _funcdef(src, name):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError("khong tim thay ham %s - da doi ten hoac da bi xoa" % name)


def _calls_in(node):
    """Ten moi loi goi THUC SU nam trong than ham (theo cay cu phap, khong grep chu).

    Chi dem loi goi o cap ham nay - mot loi goi nam trong mot `def` long ben trong ma khong
    ai goi thi KHONG duoc tinh. Da vap dung bay do: chuyen row-lock vao mot helper khong bao
    gio goi van giu nguyen moi chu, va phep kiem bang chuoi van xanh.
    """
    inner = {n for sub in ast.iter_child_nodes(node)
             for n in ast.walk(sub)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    skip = set()
    for fn in inner:
        for n in ast.walk(fn):
            skip.add(id(n))
    out = []
    for n in ast.walk(node):
        if id(n) in skip or not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute):
            out.append(f.attr)
        elif isinstance(f, ast.Name):
            out.append(f.id)
    return out


def _raises_on_falsy(node, called_name):
    """Than ham CO chan `if not <ket qua cua called_name(...)>` roi throw.

    Bat dung hinh dang cua chot: gan ket qua ra bien, kiem tra bien do rong, va nem loi.
    Doi `if False:` hay xoa dong `throw` deu lam phep kiem nay do.
    """
    targets = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            f = n.value.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if nm == called_name:
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        targets.add(t.id)
    if not targets:
        return False
    for n in ast.walk(node):
        if not isinstance(n, ast.If):
            continue
        test = n.test
        if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
                and isinstance(test.operand, ast.Name) and test.operand.id in targets):
            continue
        if any(c in ("throw", "PermissionError", "ValidationError")
               for c in _calls_in_stmt(n.body)):
            return True
    return False


def _calls_in_stmt(body):
    out = []
    for st in body:
        for n in ast.walk(st):
            if isinstance(n, ast.Call):
                f = n.func
                out.append(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return out


def _mandatory_text_guard(node, argname):
    """Than ham CO chan `if not (<argname> or "").strip(): throw`.

    Doi hinh dang chinh xac cua chot chu khong doi mot chuoi thong bao - thong bao la thu
    duoc phep sua loi chinh ta, con chot thi khong duoc phep bien mat.
    """
    for n in ast.walk(node):
        if not isinstance(n, ast.If):
            continue
        test = n.test
        if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)):
            continue
        names = {x.id for x in ast.walk(test.operand) if isinstance(x, ast.Name)}
        strips = [x for x in ast.walk(test.operand)
                  if isinstance(x, ast.Attribute) and x.attr == "strip"]
        if argname in names and strips and "throw" in _calls_in_stmt(n.body):
            return True
    return False


_TRANSITIONS = ("approval_center", "shared", "workflow", "transitions.py")
_COMMAND_SERVICE = ("approval_center", "shared", "requests", "command_service.py")


class TestDecisionFunctionsKeepTheirAuthorityChecks(unittest.TestCase):
    """Chot kiem quyen tren 4 ham quyet dinh. Xoa bat ky dong nao duoi day, 648 test cu
    van xanh - da do bang dot bien 01/09."""

    def setUp(self):
        self.src = _read(*_TRANSITIONS)

    def test_approve_van_goi_signature_guard(self):
        """Bat bien S2A: cap can chu ky chi dong duoc qua duong chu ky da xac thuc.

        Dot bien M3: xoa dong `_signature_guard(req, req.current_level, actor)` khoi approve()
        -> 648/648 van xanh. Test duy nhat cham toi ten nay lai la test THAY no bang lambda
        rong (test_e2e2_engine_guard_races.py:243), tuc khong ai canh viec no bi go han.
        """
        node = _funcdef(self.src, "approve")
        self.assertIn("_signature_guard", _calls_in(node),
                      "approve() khong con goi _signature_guard -> duyet duoc cap bat buoc "
                      "ky ma khong co chu ky nao")

    def test_ba_ham_deu_chan_nguoi_khong_phai_nguoi_duyet_dang_cho(self):
        """Dot bien M25/M26/M27: doi `if not row:` thanh `if False:`.

        approve() bi bat (nho mot test race), reject() va request_information() SONG SOT -
        nghia la hai duong ghi trang thai phieu dang khong co test kiem quyen nao.
        """
        for fn in ("approve", "reject", "request_information"):
            node = _funcdef(self.src, fn)
            self.assertTrue(
                _raises_on_falsy(node, "_actor_pending_row"),
                "%s() khong con chan 'khong phai nguoi duyet dang cho' -> nguoi ngoai "
                "ghi duoc quyet dinh len phieu" % fn)

    def test_cancel_fulfillment_van_kiem_tra_tham_quyen(self):
        """Dot bien M9: xoa `_assert_can_cancel(actor)` -> khong test nao do.

        Khong mot file test nao trong ca cay tests/ nhac den `_assert_can_cancel` hay
        `cancel_fulfillment` (da grep 01/09).
        """
        node = _funcdef(self.src, "cancel_fulfillment")
        self.assertIn("_assert_can_cancel", _calls_in(node),
                      "cancel_fulfillment() khong con kiem tham quyen -> ai cung huy "
                      "giao viec cua nguoi khac duoc")


class TestReasonIsAlwaysMandatory(unittest.TestCase):
    """Ba hanh dong dong phieu deu BAT BUOC ly do. Ca ba chot deu xoa duoc ma khong test
    nao do (dot bien M4/M6/M7). Mot phieu bi tu choi/huy ma khong ai biet vi sao la thu
    khong duoc phep ton tai trong ho so duyet chi."""

    def setUp(self):
        self.src = _read(*_TRANSITIONS)

    def test_reject_bat_buoc_ly_do(self):
        self.assertTrue(_mandatory_text_guard(_funcdef(self.src, "reject"), "comment"),
                        "reject() khong con bat buoc ly do tu choi")

    def test_cancel_bat_buoc_ly_do(self):
        self.assertTrue(_mandatory_text_guard(_funcdef(self.src, "cancel"), "reason"),
                        "cancel() khong con bat buoc ly do huy")

    def test_request_information_bat_buoc_noi_can_bo_sung_gi(self):
        self.assertTrue(
            _mandatory_text_guard(_funcdef(self.src, "request_information"), "comment"),
            "request_information() khong con bat buoc noi ro can bo sung gi - nguoi de "
            "nghi nhan phieu tra lai trong khong biet phai sua gi")


class TestLevelNeverClosesWithoutADecision(unittest.TestCase):
    def test_evaluate_van_dung_lai_khi_chua_ket_luan_approved(self):
        """Dot bien M30: doi `if decision != "approved": return` thanh `if False: return`
        -> 648/648 van xanh, tuc mot cap Any-One/N-of-M co the dong khi MOI CO MOT nguoi
        bam duyet trong so nhieu nguoi bat buoc.
        """
        node = _funcdef(_read(*_TRANSITIONS), "_evaluate")
        found = False
        for n in ast.walk(node):
            if not isinstance(n, ast.If):
                continue
            cmp_ = n.test
            if (isinstance(cmp_, ast.Compare) and isinstance(cmp_.left, ast.Name)
                    and cmp_.left.id == "decision"
                    and any(isinstance(o, ast.NotEq) for o in cmp_.ops)
                    and any(isinstance(c, ast.Constant) and c.value == "approved"
                            for c in cmp_.comparators)
                    and any(isinstance(s, ast.Return) for s in n.body)):
                found = True
        self.assertTrue(found,
                        "_evaluate() khong con dung lai khi decide_level chua ket luan "
                        "'approved' -> dong cap khi chua du so nguoi duyet")


class TestCloneCannotForkALiveRequest(unittest.TestCase):
    def test_chi_clone_tu_trang_thai_da_ket_thuc(self):
        """`_CLONEABLE` chi duoc chua trang thai DA KET THUC. Them "Pending"/"Approved" vao
        day la tao ra hai ho so cung song tren cung mot viec."""
        src = _read(*_COMMAND_SERVICE)
        tree = ast.parse(src)
        values = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "_CLONEABLE" for t in node.targets):
                values = {c.value for c in ast.walk(node.value)
                          if isinstance(c, ast.Constant)}
        self.assertIsNotNone(values, "khong tim thay _CLONEABLE trong command_service.py")
        self.assertEqual(values, {"Rejected", "Cancelled"},
                         "_CLONEABLE da doi: chi duoc clone tu trang thai da ket thuc")


class TestNoStandaloneTestIsSilentlySkipped(unittest.TestCase):
    """Mot test bi @skip/@expectedFailure trong bo nay se KHONG lam suite do, va dong
    ket qua chi hien mot chu 's' giua hang tram dau cham - khong ai thay. Vong 3 dem duoc
    0 cai; khoa lai con so 0 do."""

    def test_khong_co_skip_hay_expected_failure(self):
        here = os.path.dirname(os.path.abspath(__file__))
        offenders = []
        files = 0
        for fn in sorted(os.listdir(here)):
            if not (fn.startswith("test_") and fn.endswith(".py")):
                continue
            files += 1
            tree = ast.parse(io.open(os.path.join(here, fn), encoding="utf-8").read())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    continue
                for d in node.decorator_list:
                    txt = ast.dump(d)
                    if "skip" in txt.lower() or "expectedFailure" in txt:
                        offenders.append("%s::%s" % (fn, node.name))
        self.assertGreater(files, 40,
                           "chi thay %d file test - cach quet hong, khong phai bo test gon "
                           "lai" % files)
        self.assertEqual(offenders, [],
                         "test bi tat am tham (skip/xfail): %s" % ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
