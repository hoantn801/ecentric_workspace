# Copyright (c) 2026, eCentric and contributors
"""BOT 4 / vong 3 - ma tran vong doi tra-lai / gui-lai / clone / revision.

Dao cac to hop trang thai HIEM giua {approval_status} x {trang thai chan ky} va chung
minh ba lo hong bang MA THAT (state.py, package.py, transitions.py, capabilities.py),
khong grep chuoi mo ta.

Ba phat hien co RANG (mutation-proof):

  H1 (nang) - `request_information` la DUA con chua duoc va cua BOT D:
      approve/reject/cancel deu doc lai approval_status DUOI ROW LOCK (for_update) sau
      khi vet 31/08. request_information KHONG khoa, KHONG doc lai -> mot reject/cancel/
      approve-ve-terminal chen giua doc-cu va ghi cua no se bi GHI DE nguoc ve
      "Information Required": phieu da Rejected/Cancelled/Approved song lai. Test doc AST
      tung ham va khang dinh dung ba ham kia CO khoa, con request_information THIEU.

  H2 (vua, tiem an) - `package.create_revision` bo sot chan ky DANG BAY:
      bo loc Superseded cua no khong co "Signed" (nam trong state.DSR_LIVE) lan
      "Verification Mismatch" (non-terminal). Mot chu ky DA THU nhung chua Approval
      Completed, hoac mot chan dang doi soat, bi de LAI song tren goi vua Superseded.
      Va Signed->Superseded thau chi khong phai canh hop le -> create_revision khong the
      vo hieu mot chan Signed ke ca neu them vao bo loc. (create_revision hien la MA CHET
      trong prod: on_request_reopened tu 31/08 tu choi thay vi tao ban moi, nen day la lo
      hong tiem an + chi con duong test goi toi.)

  H3 (nang) - NGO CUT cua o "Information Required x tai lieu ky doi/khong doc duoc":
      khi cap duyet DUY NHAT cua cap da bam "Yeu cau bo sung" (dong approver -> trang thai
      "Information Requested", KHONG con Pending), roi noi dung ky thanh changed/unreadable:
      * resubmit NEM loi, chi duong "Tu choi roi Tao phieu moi";
      * nhung reject() doi mot dong Pending -> cap duyet do KHONG reject duoc;
      * requester KHONG cancel duoc trong trang thai IR (capabilities: requester chi cancel
        khi status=="Pending" va chua co quyet dinh).
      => loi thoat DUY NHAT la System Manager cancel. Huong dan tren man hinh (Tu choi) la
      NGO CUT trong dung topology pho bien nhat. Test dung capabilities.py THAT.

Chay: python3 -m unittest ...test_e2e3_lifecycle_matrix  (khong can bench/frappe that).
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
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
    with io.open(os.path.join(_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _funcdef(src, name):
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError("khong thay ham %r" % name)


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


# --------------------------------------------------------------------------- #
# load state.py THAT (thuan tuy, khong frappe)
# --------------------------------------------------------------------------- #
def _load_state():
    mod = types.ModuleType("state")
    exec(compile(_read("platform", "esign", "state.py"), "state.py", "exec"), mod.__dict__)
    return mod


_STATE = _load_state()


# =========================================================================== #
# H2 - create_revision bo sot chan ky dang bay (Signed / Verification Mismatch)
# =========================================================================== #
class TestCreateRevisionMissesLiveLegs(unittest.TestCase):
    """Doc bo loc Superseded THAT trong create_revision (package.py) qua AST."""

    def setUp(self):
        src = _read("platform", "esign", "package.py")
        fn = _funcdef(src, "create_revision")
        # tim List[str] chua "Queued" trong than ham = bo trang thai duoc Superseded
        supersede = None
        for node in ast.walk(fn):
            if isinstance(node, ast.List):
                vals = [e.value for e in node.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if "Queued" in vals and "Prepared" in vals:
                    supersede = vals
                    break
        self.assertIsNotNone(supersede,
                             "khong doc duoc bo trang thai Superseded cua create_revision")
        self.supersede = supersede

    def test_bo_loc_khong_co_signed_va_verification_mismatch(self):
        # Day la RANG cua phat hien: chan ky DA THU (Signed) va dang DOI SOAT
        # (Verification Mismatch) khong bi vo hieu khi tao phien ban moi.
        self.assertNotIn("Signed", self.supersede,
                         "create_revision KHONG superseded chan Signed (DSR_LIVE) - chu ky "
                         "da thu nhung chua hoan tat bi de lai song tren goi da Superseded")
        self.assertNotIn("Verification Mismatch", self.supersede,
                         "chan dang doi soat cung bi bo sot")

    def test_signed_thau_chi_khong_the_superseded(self):
        # Ke ca muon them Signed vao bo loc cung khong duoc: state machine khong co canh do.
        self.assertNotIn("Superseded", _STATE.DSR_TRANSITIONS["Signed"],
                         "Signed->Superseded khong hop le -> create_revision khong the vo "
                         "hieu mot chu ky da thu chi bang cach them vao bo loc")

    def test_moi_trang_thai_trong_bo_loc_deu_co_canh_superseded(self):
        # Guard cho vet MR->Superseded 31/08: neu ai bo canh, create_revision se NEM
        # InvalidTransition dung luc dang bay -> chu trinh sendback chet.
        for s in self.supersede:
            self.assertIn("Superseded", _STATE.DSR_TRANSITIONS.get(s, ()),
                          "create_revision superseded %r nhung state machine khong cho "
                          "%r->Superseded (se crash)" % (s, s))
        # Manual Review PHAI nam trong ca hai (chinh la lo hong da va)
        self.assertIn("Manual Review", self.supersede)
        self.assertIn("Superseded", _STATE.DSR_TRANSITIONS["Manual Review"])

    def test_liet_ke_chan_song_bi_bo_sot(self):
        nonterminal = [s for s in _STATE.DSR_STATES if s not in _STATE.DSR_TERMINAL]
        missed_live = [s for s in _STATE.DSR_LIVE if s not in self.supersede]
        self.assertEqual(missed_live, ["Signed"],
                         "DSR_LIVE bi create_revision bo sot phai dung la ['Signed']; "
                         "neu doi, xem lai phat hien H2")
        # Verification Mismatch la non-terminal & khong live nhung van bi bo -> orphan
        self.assertIn("Verification Mismatch",
                      [s for s in nonterminal if s not in self.supersede])


# =========================================================================== #
# H1 - request_information la dua con chua khoa cua BOT D (race downgrade)
# =========================================================================== #
class TestRequestInformationUnhardenedRace(unittest.TestCase):
    """approve/reject/cancel deu re-read status duoi for_update; request_information thi khong."""

    def setUp(self):
        self.src = _read("approval_center", "shared", "workflow", "transitions.py")

    def _profile(self, name):
        seg = ast.get_source_segment(self.src, _funcdef(self.src, name))
        return ("for_update=True" in seg,
                'req.approval_status = frappe.db.get_value' in seg)

    def test_ba_ham_ghi_terminal_deu_da_khoa_va_doc_lai(self):
        # Sentinel chong hoi quy: neu ai go khoa khoi approve/reject/cancel, test do.
        for fn in ("approve", "reject", "cancel"):
            lock, reread = self._profile(fn)
            self.assertTrue(lock, "%s phai lay row lock for_update (vet BOT D)" % fn)
            self.assertTrue(reread, "%s phai doc lai approval_status sau khi khoa" % fn)

    def test_request_information_CO_khoa_va_doc_lai(self):
        """DA VA 01/09 (H1). Truoc do request_information la ham DUY NHAT trong bon ham
        quyet dinh khong khoa hang va khong doc lai trang thai - dua voi reject/cancel/
        approve-ve-terminal thi no hoi sinh mot phieu da ket thuc ve "Information Required".
        """
        lock, reread = self._profile("request_information")
        self.assertTrue(lock, "request_information phai khoa hang truoc khi ghi")
        self.assertTrue(reread, "phai doc lai approval_status SAU khoa roi guard lan hai")

    def test_request_information_ghi_approval_status_information_required(self):
        # Xac nhan chinh no CO ghi approval_status=Information Required (nen race co hau qua).
        seg = ast.get_source_segment(self.src, _funcdef(self.src, "request_information"))
        self.assertIn('"approval_status": "Information Required"', seg)


# =========================================================================== #
# H3 - ngo cut IR x (changed/unreadable) voi cap duyet DUY NHAT
#      dung capabilities.py THAT
# =========================================================================== #
def _load_capabilities(roles, pending_row_exists, has_decision):
    """Nap capabilities.py that voi frappe + permissions gia lap."""
    recorder = {}

    def get_roles(user=None):
        return list(roles)

    class _DB(object):
        @staticmethod
        def exists(dt, filters):
            if dt == "EC Approval Request Approver":
                # _pending_row hoi status=Pending; _has_decision khong dung exists nay
                return pending_row_exists
            if dt == "EC Approval Action":
                return has_decision
            return False

        @staticmethod
        def get_value(dt, filters, field=None, **kw):
            # chi duoc goi cho admin_approve level_status; tra In Progress
            return "In Progress"

    frappe_mod = types.ModuleType("frappe")
    frappe_mod.db = _DB
    frappe_mod.get_roles = get_roles
    frappe_mod.session = types.SimpleNamespace(user="x")

    perms_mod = types.ModuleType(
        "ecentric_workspace.approval_center.shared.workflow.permissions")
    perms_mod.can_view_request = lambda *a, **kw: True
    perms_mod.is_eligible_fulfiller = lambda *a, **kw: False

    saved = {}
    for k, v in (("frappe", frappe_mod),
                 ("ecentric_workspace.approval_center.shared.workflow.permissions", perms_mod)):
        saved[k] = sys.modules.get(k)
        sys.modules[k] = v
    env = {}
    try:
        exec(compile(_read("approval_center", "shared", "requests", "capabilities.py"),
                     "capabilities.py", "exec"), env)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return env


def _biz(user, requested_by):
    return types.SimpleNamespace(doctype="EC Payment Request", requested_by=requested_by,
                                 approval_type="PAYR", fulfillment_status=None,
                                 fulfillment_owner=None)


def _ar(status, level=1):
    return _D({"name": "AR-1", "approval_status": status, "current_level": level,
               "information_requested_from_level": level, "requested_by": "req@x",
               "approval_type": "PAYR"})


class TestInformationRequiredDeadEnd(unittest.TestCase):
    """O ma tran: Information Required x noi dung ky doi, cap duyet duy nhat."""

    def test_requester_khong_cancel_duoc_trong_IR(self):
        env = _load_capabilities(roles=[], pending_row_exists=False, has_decision=True)
        caps = env["derive"]("req@x", _biz("req@x", "req@x"), _ar("Information Required"))
        self.assertFalse(caps["can_cancel"],
                         "requester khong duoc cancel khi status=IR (chi cancel khi Pending "
                         "va chua co quyet dinh) - nen khong tu thoat ngo cut duoc")
        self.assertTrue(caps["can_resubmit"], "chi con nut Gui lai - ma no se nem loi")

    def test_cap_duyet_duy_nhat_khong_reject_duoc_sau_khi_yeu_cau_bo_sung(self):
        # approver da bam "Yeu cau bo sung" -> dong cua ho la "Information Requested",
        # KHONG con Pending -> _pending_row = None -> can_reject False.
        env = _load_capabilities(roles=[], pending_row_exists=False, has_decision=True)
        caps = env["derive"]("appr@x", _biz("appr@x", "req@x"), _ar("Information Required"))
        self.assertFalse(caps["can_reject"],
                         "cap duyet da yeu cau bo sung khong con dong Pending -> reject() se "
                         "nem 'not a pending approver'. Huong dan 'Tu choi' la ngo cut.")
        self.assertFalse(caps["can_request_information"])

    def test_chi_system_manager_thoat_duoc_bang_cancel(self):
        env = _load_capabilities(roles=["System Manager"], pending_row_exists=False,
                                 has_decision=True)
        caps = env["derive"]("sm@x", _biz("sm@x", "req@x"), _ar("Information Required"))
        self.assertTrue(caps["can_cancel"],
                        "loi thoat DUY NHAT khoi ngo cut la System Manager cancel (open_request)")

    def test_pending_status_thi_requester_van_cancel_duoc(self):
        # doi chieu: o Pending chua co quyet dinh, requester cancel duoc (khong ngo cut).
        env = _load_capabilities(roles=[], pending_row_exists=False, has_decision=False)
        caps = env["derive"]("req@x", _biz("req@x", "req@x"), _ar("Pending"))
        self.assertTrue(caps["can_cancel"])


# =========================================================================== #
# Ma tran hanh dong theo approval_status (chup tu code THAT)
# =========================================================================== #
class TestActionMatrixByStatus(unittest.TestCase):
    """Trich hang so cong tac tu code that de chot ma tran clone/resubmit."""

    def test_clone_chi_tu_rejected_hoac_cancelled(self):
        src = _read("approval_center", "shared", "requests", "command_service.py")
        mod = ast.parse(src)
        cloneable = None
        for n in ast.walk(mod):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id == "_CLONEABLE":
                        cloneable = tuple(e.value for e in n.value.elts)
        self.assertEqual(cloneable, ("Rejected", "Cancelled"),
                         "clone chi tu trang thai da ket thuc; Approved KHONG clone duoc "
                         "(phai tao phieu moi tu dau) - la lua chon thiet ke, ghi nhan.")

    def test_resubmit_chi_tu_information_required(self):
        src = _read("approval_center", "shared", "workflow", "transitions.py")
        seg = ast.get_source_segment(src, _funcdef(src, "resubmit"))
        self.assertIn('"Information Required"', seg)
        self.assertIn("Only an Information Required request can be resubmitted", seg)

    def test_clone_khong_chep_tep_he_thong_signed_review(self):
        src = _read("approval_center", "shared", "requests", "command_service.py")
        mod = ast.parse(src)
        prefixes = None
        for n in ast.walk(mod):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id == "_SYSTEM_FILE_PREFIXES":
                        prefixes = tuple(e.value for e in n.value.elts)
        self.assertEqual(prefixes, ("SIGNED-", "REVIEW-"),
                         "clone phai loai ban DA KY (SIGNED-) va ban doi chieu (REVIEW-) de "
                         "khong mang chu ky cu sang phieu moi")


if __name__ == "__main__":
    unittest.main()
