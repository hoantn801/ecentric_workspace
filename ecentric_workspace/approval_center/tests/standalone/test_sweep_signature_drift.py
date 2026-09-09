# Copyright (c) 2026, eCentric and contributors
"""Soi lech chu ky 2 luot/ngay (Hoan chot 09/09: "co cach nao no tu dong check lech khong").

Boi canh. EC-PAYR-2026-00051 treo o "HOF Review" trong khi tai lieu ben SCTS da ky du - HOF
va CEO ky thang tren cong, khong bam gi tren ERP. Loai su co nay VO HINH voi trang van hanh
(no chi liet ke CHAN KY bi ket, ma o day chua bao gio co chan ky nao). `soi_lech_scts.ps1`
tra loi duoc, nhung phai co nguoi nho chay no.

Kiem o day:
  1. CHI bao dong `actionable_now`. Chu ky cua mot cap CHUA toi luot khong phai viec gi.
  2. KHONG BAO GIO tu dong sync - cong viec chay nen khong duoc tu cong nhan mot chu ky.
  3. Khong doc duoc trang thai ben nha cung cap thi VAN bao (bang mot cau noi ro), khong im.
  4. Kill switch ec_esign_scheduler_disabled; hong cau hinh = TAT (fail-safe).
  5. Goi `_audit_drift` (khong hang rao quyen) chu khong ban co `assert_system_manager`.
  6. Khong co System Manager nao dang bat -> ghi log, khong nuot.
  7. hooks.py dat dung hai moc 08:30 / 14:30.
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.abspath(os.path.join(_HERE, "..", ".."))
_APP = os.path.abspath(os.path.join(_AC, ".."))
_TASKS = ("platform", "esign", "tasks.py")
_SVC = ("platform", "esign", "service.py")


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _fn(name, rel):
    return next(n for n in ast.parse(_read(*rel)).body
                if isinstance(n, ast.FunctionDef) and n.name == name)


def _than_ham(name, rel):
    """Ma nguon cua ham, DA BO docstring."""
    node = _fn(name, rel)
    body = [n for n in node.body
            if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str))]
    return "\n".join(ast.unparse(n) for n in body)


def _load(drift=(), unreadable=(), sms=("sm@ec.vn",), conf=None, no_audit=None):
    """Nap HAI ham that (`sweep_provider_signature_drift` + `_system_managers`) tren frappe gia."""
    the_gioi = {"notify": [], "log_error": [], "audit_goi": [], "sync_goi": []}
    fk = types.ModuleType("frappe")
    fk.conf = dict(conf or {})
    fk._ = lambda s: s
    fk.get_traceback = lambda: "tb"
    fk.log_error = lambda msg, title=None: the_gioi["log_error"].append((title, msg))

    # `nghi@ec.vn` CO role System Manager nhung tai khoan DA TAT.
    bang_user = dict({u: 1 for u in sms}, **{"nghi@ec.vn": 0})

    def get_all(dt, filters=None, pluck=None, **k):
        if dt == "Has Role":
            return ["Administrator", "sm@ec.vn", "nghi@ec.vn"]
        if dt == "User":
            # Ban gia KHONG duoc tu loc theo `enabled`: no phai lam dung nhung gi ham that
            # YEU CAU. Ban dau no tra thang danh sach "dang bat" bat ke filters - tuc no tu
            # thuc thi cai luat dang can kiem, va bo `enabled: 1` khoi code van xanh.
            ten = (filters or {}).get("name", [None, []])[1]
            rows = [u for u in ten if u in bang_user]
            if (filters or {}).get("enabled") is not None:
                rows = [u for u in rows if bang_user[u] == filters["enabled"]]
            return rows
        raise AssertionError("get_all %s" % dt)
    fk.get_all = get_all

    svc = types.ModuleType("ecentric_workspace.platform.esign.service")

    def _audit_drift(limit=200):
        the_gioi["audit_goi"].append(limit)
        if no_audit:
            raise RuntimeError(no_audit)
        return {"checked": 3, "requests_seen": 3,
                "drift": list(drift), "unreadable": list(unreadable)}
    svc._audit_drift = _audit_drift

    def _chan(*a, **k):
        the_gioi["sync_goi"].append((a, k))
        raise AssertionError("cong viec dinh ky KHONG duoc tu dong dong bo chu ky")
    svc.sync_signatures_from_provider = _chan
    svc.audit_provider_signature_drift = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("phai goi _audit_drift, khong goi ban co hang rao quyen"))

    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
    eng.notify = lambda users, subject, dt, name: the_gioi["notify"].append(
        (sorted(users), subject, dt, name))

    ns = {"frappe": fk, "_": fk._}
    src = _read(*_TASKS)
    nodes = [_fn("_disabled", _TASKS), _fn("_system_managers", _TASKS),
             _fn("sweep_provider_signature_drift", _TASKS)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "tasks.py", "exec"), ns)

    import sys
    luu = {k: sys.modules.get(k) for k in
           ("ecentric_workspace.platform.esign.service",
            "ecentric_workspace.approval_center.shared.workflow.transitions")}
    sys.modules["ecentric_workspace.platform.esign.service"] = svc
    sys.modules["ecentric_workspace.approval_center.shared.workflow.transitions"] = eng
    return ns, the_gioi, luu


def _tra_lai(luu):
    import sys
    for k, v in luu.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def _dong(approver="hof@ec.vn", actionable=True, **o):
    d = {"business_doctype": "EC Payment Request", "business_name": "EC-PAYR-2026-00051",
         "approval_request": "EC-APR-1", "current_level": 4, "approver": approver,
         "signatures": 1, "completed_legs": 0, "surplus": 1, "actionable_now": actionable}
    d.update(o)
    return d


class TestSoiLechDinhKy(unittest.TestCase):
    def _chay(self, **k):
        ns, w, luu = _load(**k)
        self.addCleanup(_tra_lai, luu)
        return ns["sweep_provider_signature_drift"](), w

    def test_bao_dong_can_xu_ly_kem_link_dung_phieu(self):
        n, w = self._chay(drift=[_dong()])
        self.assertEqual(n, 1)
        users, subject, dt, name = w["notify"][0]
        self.assertEqual(users, ["sm@ec.vn"])
        self.assertEqual((dt, name), ("EC Payment Request", "EC-PAYR-2026-00051"))
        self.assertIn("hof@ec.vn", subject)
        self.assertIn("SCTS", subject)

    def test_KHONG_bao_chu_ky_cua_cap_chua_toi_luot(self):
        """Ho ky truoc cho mot cap chua toi luot - de yen, no se dung khi toi luot. Bao ca
        hai thi danh sach dai ra vi nhung dong khong lam gi duoc, va lan sau khong ai doc."""
        n, w = self._chay(drift=[_dong(actionable=False)])
        self.assertEqual(n, 0)
        self.assertEqual(w["notify"], [])

    def test_loc_dung_dong_trong_mot_me_lan_lon(self):
        n, w = self._chay(drift=[_dong(actionable=False),
                                 _dong(approver="ceo@ec.vn", business_name="PR-9"),
                                 _dong(actionable=False, approver="x@ec.vn")])
        self.assertEqual(n, 1)
        self.assertEqual([x[3] for x in w["notify"]], ["PR-9"])

    def test_KHONG_BAO_GIO_tu_dong_dong_bo(self):
        """Dong bo la hanh dong CONG NHAN mot chu ky: no dong mot cap duyet va day phieu di
        tiep. Mot cong viec chay nen khong duoc tu quyet dieu do (y Hoan). Ban gia cua
        `sync_signatures_from_provider` no ngay neu bi cham toi."""
        self._chay(drift=[_dong(), _dong(approver="ceo@ec.vn")])
        # (khong nem AssertionError la du, nhung noi thanh loi cho ro)
        _ns, w, luu = _load(drift=[_dong()])
        self.addCleanup(_tra_lai, luu)
        self.assertEqual(w["sync_goi"], [])

    def test_khong_doc_duoc_thi_VAN_bao_chu_khong_im(self):
        """"Hoi duoc va sach" KHAC "khong hoi duoc". Im lang khi khong doc duoc la dung cai
        loi im lang da lam mat hai dem cua thang 8."""
        n, w = self._chay(unreadable=[{"business_name": "PR-7", "error": "timeout"}])
        self.assertEqual(n, 0)                      # khong co dong nao BAO cho nguoi
        self.assertTrue(any("KHONG hoi duoc" in m for _t, m in w["log_error"]))
        self.assertTrue(any("PR-7" in m for _t, m in w["log_error"]))

    def test_sach_thi_KHONG_lam_phien_ai(self):
        n, w = self._chay()
        self.assertEqual((n, w["notify"], w["log_error"]), (0, [], []))

    def test_kill_switch_va_hong_cau_hinh_deu_TAT(self):
        n, w = self._chay(conf={"ec_esign_scheduler_disabled": 1}, drift=[_dong()])
        self.assertEqual((n, w["notify"], w["audit_goi"]), (0, [], []))
        # hong cau hinh -> fail-safe la TAT, khong phai BAT
        n2, w2 = self._chay(conf={"ec_esign_scheduler_disabled": "khong-phai-so"},
                            drift=[_dong()])
        self.assertEqual((n2, w2["audit_goi"]), (0, []))

    def test_audit_no_thi_ghi_log_chu_khong_giet_scheduler(self):
        n, w = self._chay(no_audit="SCTS sap", drift=[_dong()])
        self.assertEqual((n, w["notify"]), (0, []))
        self.assertTrue(any("sweep_provider_signature_drift" in (t or "")
                            for t, _m in w["log_error"]))

    def test_khong_co_System_Manager_nao_thi_GHI_LOG_chu_khong_nuot(self):
        """Hom nay chi co MOT System Manager dang bat. Neu tai khoan do bi tat thi canh bao
        se roi vao hu khong - phai con lai mot dau vet o Error Log."""
        n, w = self._chay(drift=[_dong()], sms=())
        self.assertEqual((n, w["notify"]), (0, []))
        self.assertTrue(any("KHONG co System Manager" in m for _t, m in w["log_error"]))

    def test_loai_Administrator_ra_khoi_nguoi_nhan(self):
        """Administrator khong phai mot nguoi; thong bao gui vao do khong ai doc."""
        ns, _w, luu = _load(sms=("sm@ec.vn", "Administrator"))
        self.addCleanup(_tra_lai, luu)
        self.assertEqual(ns["_system_managers"](), ["sm@ec.vn"])

    def test_bo_qua_tai_khoan_DA_TAT_du_van_con_role(self):
        """Nguoi nghi viec thuong bi TAT tai khoan chu role khong ai go. Gui canh bao vao
        mot tai khoan da tat la gui vao hu khong - va con nguy hon: no lam `_system_managers`
        tra ve khac rong, nen duong "khong co ai de bao" khong bao gio chay, tuc mat luon
        dong Error Log dang le phai co."""
        ns, _w, luu = _load(sms=("sm@ec.vn",))
        self.addCleanup(_tra_lai, luu)
        self.assertEqual(ns["_system_managers"](), ["sm@ec.vn"])   # nghi@ec.vn bi loai

    def test_moi_System_Manager_deu_bi_TAT_thi_coi_nhu_khong_co_ai(self):
        ns, w, luu = _load(drift=[_dong()], sms=())
        self.addCleanup(_tra_lai, luu)
        self.assertEqual(ns["_system_managers"](), [])
        self.assertEqual(ns["sweep_provider_signature_drift"](), 0)
        self.assertTrue(any("KHONG co System Manager" in m for _t, m in w["log_error"]))


class TestGoiDungCuaVaoVaLichChay(unittest.TestCase):
    def test_goi_ban_KHONG_hang_rao_quyen(self):
        """`audit_provider_signature_drift` co `assert_system_manager`, ma cong viec dinh ky
        khong co nguoi nao dang bam: no chay duoi Administrator. De no di qua duoc hang rao
        do la dang dua vao viec "Administrator tinh co duoc cap moi role" - doi mot cai la
        cong viec chet IM LANG (no bat Exception roi ghi log, khong ai doc)."""
        src = _than_ham("sweep_provider_signature_drift", _TASKS)
        self.assertIn("_audit_drift()", src)
        self.assertNotIn("audit_provider_signature_drift", src)

    def test_ban_co_hang_rao_VAN_con_hang_rao(self):
        """Tach loi ra khong duoc lam mat hang rao o duong API."""
        pub = ast.unparse(_fn("audit_provider_signature_drift", _SVC))
        self.assertIn("assert_system_manager()", pub)
        self.assertIn("_audit_drift(limit)", pub)
        # Kiem tren THAN HAM, khong ke docstring: docstring CO Y nhac
        # `assert_system_manager` de noi vi sao KHONG dat no o day. Kiem ca ham thi phep do
        # bat nham chinh phan giai thich - va cach "sua" de test xanh se la xoa mat loi giai
        # thich do. (Da dinh loi nay 2 lan sang nay voi `allowed_signing_users` va
        # `coalesce`.)
        self.assertNotIn("assert_system_manager", _than_ham("_audit_drift", _SVC))

    def test_hooks_dat_dung_hai_moc_gio_dia_phuong(self):
        """System Settings.time_zone = Asia/Ho_Chi_Minh (da doi chieu tren prod 09/09) nen
        Frappe chay cron theo gio VN - KHONG duoc quy ra UTC."""
        src = _read("hooks.py")
        ns = {"__name__": "hooks"}
        body = "".join(l for l in src.splitlines(True)
                       if not l.lstrip().startswith(("from .", "import .")))
        exec(compile(body, "hooks.py", "exec"), ns)
        cron = ns["scheduler_events"]["cron"]
        M = "ecentric_workspace.platform.esign.tasks.sweep_provider_signature_drift"
        for moc in ("30 8 * * *", "30 14 * * *"):
            self.assertIn(M, cron.get(moc, []), moc)
        chay = [k for k, v in cron.items() if M in v]
        self.assertEqual(len(chay), 2, "dung HAI luot/ngay, khong hon: %s" % chay)


if __name__ == "__main__":
    unittest.main()
