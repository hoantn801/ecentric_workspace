# Copyright (c) 2026, eCentric and contributors
"""Booking Request (form thu 28, 11/09 - Hoan brief).

Code THAT cua features/booking_request/application/service.py + reminders.py duoc nap bang
exec(compile) tren mot frappe gia ghi lai moi lenh - khong grep nguon, vi grep mu ngay sau
lan refactor dau tien.

Kiem:
  1. khoang_ngay_hop_le: tran = ngay hoat dong bat dau - 3; cua so RONG (yeu cau gap) thi noi
     tran toi chinh ngay bat dau va bat co `la_gap`, khong chan.
  2. claim: BAT BUOC ngay cam ket; chan ngay qua khu va ngay vuot tran; UPDATE co dieu kien
     (nguoi thu hai bi tu choi) va ngay ghi TRONG CUNG lenh.
  3. submit: loai "Chi dinh" phai co it nhat mot dong KOL; hai loai kia phai co so luong;
     brand moi phai khai nguoi Booking; brand co san thi CHEP nguoi phu trach tu Brand.
  4. on_final_approval: giao DICH DANH cho booking_owner; khong co thi ve ca nhom; khong ai
     ca thi log_error chu khong nem loi.
  5. complete: phai co ghi chu HOAC file.
  6. reminders: dung cua so D-3, moi phieu mot lan/ngay, kill switch.
  7. Dang ky: FULFILLMENT_DOCTYPES + _FULFILLMENT_HANDLERS + hooks scheduler + registry.
"""
import datetime as _dt
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.abspath(os.path.join(_HERE, "..", ".."))
_APP = os.path.abspath(os.path.join(_AC, ".."))
BUSINESS_DT = "EC Booking Request"
CHI_DINH = "KOL/KOC Chỉ định"
MIDDLE = "Middle KOL/KOC"


def _read(*p):
    with io.open(os.path.join(_AC, *p), encoding="utf-8") as fh:
        return fh.read()


def _read_app(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


class _Throw(Exception):
    pass


class _Perm(_Throw):
    pass


def _getdate(v):
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


class _Doc(types.SimpleNamespace):
    def get(self, k, d=None):
        return getattr(self, k, d)


HOM_NAY = _dt.date(2026, 9, 11)


def _load(docs, brands=None, roles=("Employee",), user="book1@ec.vn", todos=None,
          fulfillers=("book1@ec.vn", "book2@ec.vn"), case=None):
    world = {"set_value": [], "sql": [], "assign": [], "notify": [], "log": [], "ensure_sole": [],
             "closed": [], "attached": [], "saved": [], "log_error": [], "inserted": [],
             "docs": docs, "brands": dict(brands or {}), "todos": set(todos or [])}
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=user)
    fk.PermissionError = _Perm
    fk.conf = {}
    fk.get_roles = lambda u=None: list(roles)
    # @frappe.whitelist(...) la mot decorator tra ve chinh ham - o day no khong lam gi,
    # nhung PHAI co, neu khong module that khong nap duoc.
    fk.whitelist = lambda *a, **k: (lambda f: f)
    fk.parse_json = lambda s: json.loads(s)
    fk.get_traceback = lambda: "tb"
    fk.log_error = lambda msg, title=None: world["log_error"].append((title, msg))
    fk.utils = types.SimpleNamespace(
        now_datetime=lambda: _dt.datetime(2026, 9, 11, 10, 0),
        formatdate=lambda d: "%02d-%02d-%d" % (_getdate(d).day, _getdate(d).month, _getdate(d).year),
        getdate=_getdate,
        today=lambda: str(HOM_NAY),
        add_days=lambda d, n: _getdate(d) + _dt.timedelta(days=n))

    def get_doc(dt, name=None):
        if dt == BUSINESS_DT:
            d = _Doc(**docs[name]); d.doctype = dt; d.name = name

            def save(ignore_permissions=False, _d=d):
                world["saved"].append(dict(vars(_d)))
                docs[name].update({k: v for k, v in vars(_d).items()
                                   if k not in ("save", "doctype")})
            d.save = save
            return d
        if dt == "EC Approval Process":
            return types.SimpleNamespace(name=name, participants=[
                types.SimpleNamespace(participant_purpose="Fulfiller", source_type="Role",
                                      role="EC Booking"),
                types.SimpleNamespace(participant_purpose="Approver",
                                      source_type="Requester Manager")])
        raise AssertionError("get_doc %s" % dt)
    fk.get_doc = get_doc

    def new_doc(dt):
        d = _Doc(doctype=dt, name=None)
        d.meta = types.SimpleNamespace(has_field=lambda f: True)

        def insert(ignore_permissions=False, _d=d):
            _d.name = getattr(_d, "brand", None) or "BRAND?"
            world["inserted"].append(dict(vars(_d)))
            world["brands"][_d.name] = {"ec_booking_owner": getattr(_d, "ec_booking_owner", None),
                                        "ec_account_owner": getattr(_d, "ec_account_owner", None)}
        d.insert = insert
        d.set = lambda k, v, _d=d: setattr(_d, k, v)
        return d
    fk.new_doc = new_doc

    def db_get_value(dt, name, field=None, as_dict=False, **k):
        if dt == "EC Approval Request":
            return "BOOKING_REQUEST-V1"
        if dt == BUSINESS_DT:
            return docs[name].get(field)
        if dt == "Employee":
            return types.SimpleNamespace(name="EMP-1", department="Service - EC",
                                         company="eCentric") if as_dict else "EMP-1"
        if dt == "Brand":
            row = world["brands"].get(name)
            if not row:
                return None
            # frappe tra ve `frappe._dict` (co .get) chu khong phai SimpleNamespace -
            # gia lap sai kieu o day thi ham that se no ngay khi len that.
            return _Doc(**row) if as_dict else row.get(field)
        raise AssertionError("get_value %s" % dt)

    def db_set_value(dt, name, field, value=None, update_modified=True):
        if isinstance(field, dict):
            docs[name].update(field); world["set_value"].append((name, dict(field)))
        else:
            docs[name][field] = value; world["set_value"].append((name, {field: value}))

    def db_sql(q, params=None):
        world["sql"].append((" ".join(q.split()), params))
        if q.strip().lower().startswith("update"):
            # Stub KHONG tu tra loi ho: dieu kien 'Assigned' phai nam trong SQL that, va ngay
            # cam ket phai di TRONG CUNG lenh - sai thu tu tham so la vo ngay o day.
            u, ngay, due, name = params
            cond = "fulfillment_status='Assigned'" in q
            if not cond or docs[name].get("fulfillment_status") == "Assigned":
                docs[name].update({"fulfillment_status": "In Progress", "fulfillment_owner": u,
                                   "fulfillment_expected_date": ngay, "fulfillment_due_at": due})
            return None
        name, u = params
        return [(1,)] if docs[name].get("fulfillment_owner") == u else []

    def db_exists(dt, f=None):
        if dt == "ToDo":
            return (f["reference_name"], f["allocated_to"]) in world["todos"]
        if dt == "Brand":
            return f in world["brands"]
        return False

    def get_all(dt, filters=None, fields=None, limit_page_length=None, **k):
        assert dt == BUSINESS_DT
        assert "fulfillment_expected_date" not in (filters or {}), \
            "loc ngay phai o Python, khong o SQL"
        out = []
        for n, d in docs.items():
            if d.get("fulfillment_status") not in filters["fulfillment_status"][1]:
                continue
            row = types.SimpleNamespace(name=n)
            for f in (fields or []):
                setattr(row, f, d.get(f) if f != "name" else n)
            out.append(row)
        return out

    fk.get_all = get_all
    fk.db = types.SimpleNamespace(get_value=db_get_value, set_value=db_set_value, sql=db_sql,
                                  exists=db_exists)

    def throw(msg, exc=_Throw):
        raise exc(msg)
    fk.throw = throw

    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
    eng.resolve_participants = lambda rows, requester: (
        [(u, "Role: EC Booking") for u in fulfillers]
        if any(r.participant_purpose == "Fulfiller" for r in rows) else [])
    eng.assign = lambda dt, name, users, desc=None, date=None, fulfillment=False: world["assign"].append(
        {"name": name, "users": list(users), "date": date, "fulfillment": fulfillment})
    eng.notify = lambda users, subject, dt, name: world["notify"].append((list(users), subject, name))
    eng.request_label = lambda dt, name: "BOOK " + name
    eng.is_active_process_fulfiller = lambda at, u: u in fulfillers
    eng.ensure_sole_todo = lambda dt, name, u, desc=None, date=None: world["ensure_sole"].append((name, u, date))
    eng.log_action = lambda ar, action, actor, **k: world["log"].append(
        (action, actor, k.get("new_status"), k.get("comment")))
    eng.close_fulfillment_todos = lambda dt, name: world["closed"].append(name)
    eng.submit = lambda dt, name, at, user, **k: "AR-" + name
    eng.resubmit = lambda ar, actor=None, restart=False: world["log"].append(
        ("Resubmitted", actor, None, "restart=%s" % restart))
    cs = types.ModuleType("ecentric_workspace.approval_center.shared.requests.command_service")
    cs.attach_extra_files = lambda doc, urls: world["attached"].append((doc.name, list(urls)))
    fu = types.ModuleType("frappe.utils")
    for k in ("now_datetime", "formatdate", "getdate", "add_days", "today"):
        setattr(fu, k, getattr(fk.utils, k))

    svc_mod = types.ModuleType(
        "ecentric_workspace.approval_center.features.booking_request.application.service")
    mods = {"frappe": fk, "frappe.utils": fu,
            "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
            "ecentric_workspace.approval_center.shared.requests.command_service": cs,
            "ecentric_workspace.approval_center.features.booking_request.application.service": svc_mod}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)

    def restore():
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    if case is not None:
        case.addCleanup(restore)
    try:
        exec(compile(_read("features", "booking_request", "application", "service.py"),
                     "service.py", "exec"), svc_mod.__dict__)
        rem = types.ModuleType("_reminders_under_test")
        exec(compile(_read("features", "booking_request", "application", "reminders.py"),
                     "reminders.py", "exec"), rem.__dict__)
    except Exception:
        restore()
        raise
    if case is None:
        restore()
    return svc_mod, rem, world, fk


def _bk(**over):
    d = {"name": "BK-1", "approval_request": "AR-1", "requested_by": "acc@ec.vn",
         "request_title": "Booking KOC T10 - BRANDX",
         "brand": "BRANDX", "brand_is_new": 0, "brand_display_name": "BRANDX",
         "booking_owner": "book1@ec.vn", "account_owner": "acc@ec.vn",
         "booking_type": CHI_DINH, "kol_count": 0, "expected_budget": 5000000,
         "campaign_start_date": "2026-10-01", "campaign_end_date": None,
         "brand_brief": "brief", "kol_list": [{"kol_name": "A"}],
         "fulfillment_status": "Assigned", "fulfillment_owner": None,
         "fulfillment_expected_date": None, "booking_reminded_on": None,
         "completed_attachment": None, "fulfillment_summary": None,
         "employee": None, "department": None, "company": None,
         "submitted_at": None, "material_signature": None, "cc_to": None}
    d.update(over)
    return d


class TestKhoangNgay(unittest.TestCase):
    def setUp(self):
        self.svc, self.rem, self.world, self.fk = _load({"BK-1": _bk()}, case=self)

    def test_tran_la_ngay_bat_dau_tru_ba(self):
        som, muon, gap = self.svc.khoang_ngay_hop_le("2026-10-01")
        self.assertEqual(som, HOM_NAY)
        self.assertEqual(muon, _dt.date(2026, 9, 28))
        self.assertFalse(gap)

    def test_yeu_cau_gap_thi_noi_tran_chu_KHONG_chan(self):
        """Hoat dong bat dau trong vong 3 ngay: cua so D-3 rong. Chan thi ban Booking khong
        nhan viec duoc va se quay lai nhan tin tay - dung cai luong form nay sinh ra de bo."""
        som, muon, gap = self.svc.khoang_ngay_hop_le("2026-09-12")
        self.assertTrue(gap)
        self.assertEqual(muon, _dt.date(2026, 9, 12))   # chinh ngay bat dau
        self.assertEqual(som, HOM_NAY)

    def test_khong_co_ngay_bat_dau_thi_khong_bia_tran(self):
        som, muon, gap = self.svc.khoang_ngay_hop_le(None)
        self.assertEqual(som, HOM_NAY)
        self.assertIsNone(muon)
        self.assertFalse(gap)

    def test_khoi_doc_them_cho_man_hinh_lay_dung_khoang_do(self):
        """Man hinh KHONG duoc tu tru 3 ngay: luat chi duoc song mot noi."""
        block = self.svc.booking_block(_Doc(**_bk()))["booking"]
        self.assertEqual(block["ngay_muon_nhat"], "2026-09-28")
        self.assertEqual(block["dem_truoc_hoat_dong"], 3)
        self.assertEqual(block["la_gap"], 0)


class TestNhanViec(unittest.TestCase):
    def _w(self, **over):
        docs = {"BK-1": _bk(**over)}
        self.svc, self.rem, self.world, self.fk = _load(docs, case=self)
        return docs

    def test_khong_khai_ngay_thi_khong_nhan_duoc(self):
        self._w()
        with self.assertRaises(_Throw):
            self.svc.claim_fulfillment("BK-1", user="book1@ec.vn", expected_date=None)

    def test_ngay_qua_khu_bi_chan(self):
        self._w()
        with self.assertRaises(_Throw):
            self.svc.claim_fulfillment("BK-1", user="book1@ec.vn", expected_date="2026-09-01")

    def test_ngay_vuot_tran_bi_chan(self):
        self._w()
        with self.assertRaises(_Throw):
            self.svc.claim_fulfillment("BK-1", user="book1@ec.vn", expected_date="2026-09-29")

    def test_dung_tran_thi_nhan_duoc(self):
        docs = self._w()
        r = self.svc.claim_fulfillment("BK-1", user="book1@ec.vn", expected_date="2026-09-28")
        self.assertEqual(r["owner"], "book1@ec.vn")
        self.assertEqual(docs["BK-1"]["fulfillment_status"], "In Progress")
        self.assertEqual(str(docs["BK-1"]["fulfillment_expected_date"]), "2026-09-28")

    def test_ngay_ghi_TRONG_CUNG_lenh_voi_viec_nhan(self):
        """Khong bao gio duoc ton tai khoanh khac 'da nhan ma chua co han'."""
        self._w()
        self.svc.claim_fulfillment("BK-1", user="book1@ec.vn", expected_date="2026-09-20")
        up = [q for q, p in self.world["sql"] if q.lower().startswith("update")]
        self.assertTrue(up, "phai co lenh UPDATE")
        self.assertIn("fulfillment_expected_date=%s", up[0])
        self.assertIn("fulfillment_owner=%s", up[0])
        self.assertIn("fulfillment_status='Assigned'", up[0], "UPDATE phai co dieu kien")

    def test_nguoi_thu_hai_bi_tu_choi(self):
        docs = self._w(fulfillment_status="In Progress", fulfillment_owner="book1@ec.vn")
        with self.assertRaises(_Throw):
            self.svc.claim_fulfillment("BK-1", user="book2@ec.vn", expected_date="2026-09-20")
        self.assertEqual(docs["BK-1"]["fulfillment_owner"], "book1@ec.vn")

    def test_nguoi_ngoai_nhom_khong_nhan_duoc(self):
        self._w()
        with self.assertRaises(_Perm):
            self.svc.claim_fulfillment("BK-1", user="ngoai@ec.vn", expected_date="2026-09-20")

    def test_han_xu_ly_la_17h_ngay_cam_ket(self):
        self._w()
        self.assertEqual(self.svc.han_xu_ly("2026-09-20"), "2026-09-20 17:00:00")
        self.assertIsNone(self.svc.han_xu_ly(None))


class TestGui(unittest.TestCase):
    def _w(self, docs_over=None, brands=None):
        docs = {"BK-1": _bk(approval_request=None, **(docs_over or {}))}
        self.svc, self.rem, self.world, self.fk = _load(
            docs, brands=brands or {"BRANDX": {"ec_booking_owner": "book9@ec.vn",
                                               "ec_account_owner": "acc9@ec.vn"}},
            user="acc@ec.vn", case=self)
        return docs

    def test_chi_dinh_khong_co_dong_KOL_nao_thi_bi_chan(self):
        self._w({"kol_list": []})
        with self.assertRaises(_Throw):
            self.svc.submit("BK-1")

    def test_chi_dinh_dong_KOL_chi_co_khoang_trang_cung_bi_chan(self):
        """Mot dong rong khong phai la mot KOL - neu khong bo qua duoc thi form nay vo nghia."""
        self._w({"kol_list": [{"kol_name": "   "}]})
        with self.assertRaises(_Throw):
            self.svc.submit("BK-1")

    def test_middle_thieu_so_luong_thi_bi_chan(self):
        self._w({"booking_type": MIDDLE, "kol_count": 0, "kol_list": []})
        with self.assertRaises(_Throw):
            self.svc.submit("BK-1")

    def test_brand_co_san_thi_CHEP_nguoi_phu_trach_tu_Brand(self):
        """Chep xuong phieu chu khong tra cuu moi lan: brand doi nguoi ve sau thi phieu cu
        van giu dung nguoi chiu trach nhiem luc do."""
        docs = self._w({"booking_owner": None, "account_owner": None})
        self.svc.submit("BK-1")
        self.assertEqual(docs["BK-1"]["booking_owner"], "book9@ec.vn")
        self.assertEqual(docs["BK-1"]["account_owner"], "acc9@ec.vn")

    def test_brand_moi_khong_khai_nguoi_booking_thi_bi_chan(self):
        self._w({"brand": "BRANDMOI", "brand_is_new": 1, "booking_owner": None},
                brands={})
        with self.assertRaises(_Throw):
            self.svc.submit("BK-1")

    def test_brand_moi_duoc_TAO_kem_nguoi_phu_trach_va_co_chua_chuan_hoa(self):
        docs = self._w({"brand": "BRANDMOI", "brand_is_new": 1, "brand_display_name": "BRANDMOI",
                        "booking_owner": "book2@ec.vn", "account_owner": None}, brands={})
        self.svc.submit("BK-1")
        self.assertEqual(len(self.world["inserted"]), 1, "phai tao dung MOT ban ghi Brand")
        b = self.world["inserted"][0]
        self.assertEqual(b["ec_booking_owner"], "book2@ec.vn")
        self.assertEqual(b["ec_account_owner"], "acc@ec.vn", "Account phu trach = chinh nguoi gui")
        self.assertEqual(b["ec_can_chuan_hoa"], 1, "ten do nguoi dung go -> phai danh dau")
        self.assertEqual(b["ec_brand_source"], "External")

    def test_brand_moi_trung_ten_ban_da_co_thi_KHONG_tao_ban_thu_hai(self):
        self._w({"brand": "BRANDX", "brand_is_new": 1, "booking_owner": "book2@ec.vn"})
        self.svc.submit("BK-1")
        self.assertEqual(self.world["inserted"], [])

    def test_ngan_sach_khong_duong_thi_bi_chan(self):
        self._w({"expected_budget": 0})
        with self.assertRaises(_Throw):
            self.svc.submit("BK-1")

    def test_ngay_ket_thuc_truoc_ngay_bat_dau_thi_bi_chan(self):
        self._w({"campaign_end_date": "2026-09-20"})
        with self.assertRaises(_Throw):
            self.svc.submit("BK-1")

    def test_gui_hai_lan_thi_lan_hai_bi_chan(self):
        docs = self._w()
        self.svc.submit("BK-1")
        docs["BK-1"]["approval_request"] = "AR-BK-1"
        with self.assertRaises(_Throw):
            self.svc.submit("BK-1")


class TestGiaoViecSauKhiDuyet(unittest.TestCase):
    def _w(self, **over):
        docs = {"BK-1": _bk(fulfillment_status="Not Started", **over)}
        self.svc, self.rem, self.world, self.fk = _load(docs, case=self)
        return docs

    def test_giao_DICH_DANH_cho_booking_owner(self):
        docs = self._w(booking_owner="book9@ec.vn")
        self.svc.on_final_approval("BK-1")
        self.assertEqual(docs["BK-1"]["fulfillment_status"], "Assigned")
        self.assertEqual([a["users"] for a in self.world["assign"]], [["book9@ec.vn"]])
        self.assertTrue(self.world["assign"][0]["fulfillment"])

    def test_chua_gan_nguoi_thi_ve_CA_NHOM(self):
        self._w(booking_owner=None)
        self.svc.on_final_approval("BK-1")
        self.assertEqual(self.world["assign"][0]["users"], ["book1@ec.vn", "book2@ec.vn"])

    def test_khong_ai_ca_thi_ghi_log_chu_khong_nem_loi(self):
        docs = {"BK-1": _bk(fulfillment_status="Not Started", booking_owner=None)}
        self.svc, self.rem, self.world, self.fk = _load(docs, fulfillers=(), case=self)
        self.svc.on_final_approval("BK-1")          # khong duoc nem loi
        self.assertEqual(self.world["assign"], [])
        self.assertEqual(docs["BK-1"]["fulfillment_status"], "Assigned")
        self.assertTrue(any("booking_request.on_final_approval" in (t or "")
                            for t, _m in self.world["log_error"]))

    def test_chua_ai_nhan_thi_KHONG_bia_han(self):
        docs = self._w(booking_owner="book9@ec.vn")
        self.svc.on_final_approval("BK-1")
        self.assertIsNone(docs["BK-1"]["fulfillment_due_at"])
        self.assertIsNone(docs["BK-1"]["fulfillment_owner"])


class TestHoanTat(unittest.TestCase):
    def _w(self, **over):
        docs = {"BK-1": _bk(fulfillment_status="In Progress",
                            fulfillment_owner="book1@ec.vn", **over)}
        self.svc, self.rem, self.world, self.fk = _load(docs, case=self)
        return docs

    def test_khong_ghi_chu_va_khong_file_thi_bi_chan(self):
        self._w()
        with self.assertRaises(_Throw):
            self.svc.complete_fulfillment("BK-1", user="book1@ec.vn", payload={})

    def test_chi_ghi_chu_thoi_van_hoan_tat_duoc(self):
        """Ket qua booking co the la mot danh sach go thang - khong bat buoc file nhu phieu chi."""
        docs = self._w()
        self.svc.complete_fulfillment("BK-1", user="book1@ec.vn",
                                      payload={"fulfillment_summary": "5 KOC da chot"})
        self.assertEqual(docs["BK-1"]["fulfillment_status"], "Completed")
        self.assertEqual(self.world["closed"], ["BK-1"])

    def test_file_khong_hop_le_bi_chan(self):
        self._w()
        with self.assertRaises(_Throw):
            self.svc.complete_fulfillment("BK-1", user="book1@ec.vn",
                                          payload={"completed_attachment": "http://ngoai/x.pdf"})

    def test_nguoi_khac_khong_hoan_tat_duoc(self):
        self._w()
        with self.assertRaises(_Perm):
            self.svc.complete_fulfillment("BK-1", user="book2@ec.vn",
                                          payload={"fulfillment_summary": "x"})


class TestNhacHan(unittest.TestCase):
    def _w(self, docs):
        self.svc, self.rem, self.world, self.fk = _load(docs, case=self)
        return docs

    def test_chi_nhac_trong_cua_so_D_tru_3(self):
        docs = self._w({
            "BK-1": _bk(name="BK-1", fulfillment_status="In Progress",
                        fulfillment_owner="book1@ec.vn", fulfillment_expected_date="2026-09-14"),
            "BK-2": _bk(name="BK-2", fulfillment_status="In Progress",
                        fulfillment_owner="book1@ec.vn", fulfillment_expected_date="2026-09-15"),
        })
        self.assertEqual(self.rem.due_candidates(HOM_NAY), ["BK-1"])

    def test_qua_han_van_nhac(self):
        self._w({"BK-1": _bk(fulfillment_status="In Progress", fulfillment_owner="book1@ec.vn",
                             fulfillment_expected_date="2026-09-01")})
        self.assertEqual(self.rem.due_candidates(HOM_NAY), ["BK-1"])

    def test_chua_khai_ngay_thi_khong_nhac(self):
        """Chua ai nhan viec thi chua co cam ket nao - nhac theo mot moc khong ai dat ra chi
        la tieng on."""
        self._w({"BK-1": _bk(fulfillment_status="Assigned", fulfillment_expected_date=None)})
        self.assertEqual(self.rem.due_candidates(HOM_NAY), [])

    def test_da_nhac_hom_nay_thi_thoi(self):
        self._w({"BK-1": _bk(fulfillment_status="In Progress", fulfillment_owner="book1@ec.vn",
                             fulfillment_expected_date="2026-09-12",
                             booking_reminded_on=str(HOM_NAY))})
        self.assertEqual(self.rem.due_candidates(HOM_NAY), [])

    def test_nhac_hom_qua_thi_hom_nay_van_nhac(self):
        self._w({"BK-1": _bk(fulfillment_status="In Progress", fulfillment_owner="book1@ec.vn",
                             fulfillment_expected_date="2026-09-12",
                             booking_reminded_on="2026-09-10")})
        self.assertEqual(self.rem.due_candidates(HOM_NAY), ["BK-1"])

    def test_In_Progress_nhac_dung_nguoi_da_nhan(self):
        self._w({"BK-1": _bk(fulfillment_status="In Progress", fulfillment_owner="book9@ec.vn",
                             fulfillment_expected_date="2026-09-12")})
        n = self.rem.remind_booking_due(HOM_NAY)
        self.assertEqual(n, 1)
        self.assertEqual(self.world["notify"][0][0], ["book9@ec.vn"])

    def test_Assigned_thi_nhac_ca_nhom(self):
        self._w({"BK-1": _bk(fulfillment_status="Assigned", fulfillment_owner=None,
                             fulfillment_expected_date="2026-09-12")})
        self.rem.remind_booking_due(HOM_NAY)
        self.assertEqual(self.world["notify"][0][0], ["book1@ec.vn", "book2@ec.vn"])

    def test_danh_dau_da_nhac_KHONG_dung_toi_modified(self):
        """Nhac viec la viec cua may - khong duoc lam phieu trong nhu vua co nguoi sua."""
        self._w({"BK-1": _bk(fulfillment_status="In Progress", fulfillment_owner="book1@ec.vn",
                             fulfillment_expected_date="2026-09-12")})
        self.rem.remind_booking_due(HOM_NAY)
        self.assertIn(("BK-1", {"booking_reminded_on": HOM_NAY}), self.world["set_value"])

    def test_kill_switch(self):
        self._w({"BK-1": _bk(fulfillment_status="In Progress", fulfillment_owner="book1@ec.vn",
                             fulfillment_expected_date="2026-09-12")})
        self.fk.conf["ec_booking_reminder_disabled"] = 1
        self.assertEqual(self.rem.remind_booking_due(HOM_NAY), 0)
        self.assertEqual(self.world["notify"], [])

    def test_mot_phieu_loi_khong_chan_phieu_khac(self):
        docs = self._w({
            "BK-BAD": _bk(name="BK-BAD", fulfillment_status="In Progress",
                          fulfillment_owner="book1@ec.vn", fulfillment_expected_date="2026-09-12"),
            "BK-OK": _bk(name="BK-OK", fulfillment_status="In Progress",
                         fulfillment_owner="book1@ec.vn", fulfillment_expected_date="2026-09-12"),
        })
        goc = self.fk.get_doc

        def no_voi_mot_phieu(dt, name=None):
            if name == "BK-BAD":
                raise RuntimeError("hong")
            return goc(dt, name)
        self.fk.get_doc = no_voi_mot_phieu
        self.assertEqual(self.rem.remind_booking_due(HOM_NAY), 1)
        self.assertTrue(any("BK-BAD" in (t or "") for t, _m in self.world["log_error"]))


class TestDangKy(unittest.TestCase):
    """Nhung cho phai KHAI thi form moi chay - quen mot cho la form im lang khong hoat dong."""

    def test_engine_biet_doctype_nay_co_buoc_xu_ly(self):
        src = _read("shared", "workflow", "transitions.py")
        i = src.index("FULFILLMENT_DOCTYPES")
        self.assertIn(BUSINESS_DT, src[i:i + 700])

    def test_engine_goi_on_final_approval_cua_booking(self):
        src = _read("shared", "workflow", "transitions.py")
        i = src.index("_FULFILLMENT_HANDLERS")
        self.assertIn("features.booking_request.application.service.on_final_approval",
                      src[i:i + 1800])

    def test_registry_co_dinh_nghia(self):
        src = _read("shared", "registry.py")
        self.assertIn("BOOKING_REQUEST_DEFINITION", src)
        self.assertIn("features.booking_request.domain.definition", src)

    def test_hooks_dang_ky_job_nhac_han(self):
        src = _read_app("hooks.py")
        self.assertIn("features.booking_request.application.reminders.remind_booking_due", src)

    def test_patches_txt_khai_ba_patch(self):
        src = _read_app("patches.txt")
        for p in ("p177_create_ec_booking_role", "p178_seed_booking_request_approval_type",
                  "p179_create_booking_request_page"):
            self.assertIn(p, src, p)

    def test_brand_co_bon_truong_moi_va_DEU_duoc_khai_fixture(self):
        """Thieu khai trong hooks.py thi bench dung tu app nay se co Brand khong co cac truong
        do - va viec giao cho dung nguoi Booking se im lang khong bao gio chay."""
        cf = json.loads(_read_app("fixtures", "custom_field.json"))
        ten = {x.get("fieldname") for x in cf if x.get("dt") == "Brand"}
        hooks = _read_app("hooks.py")
        for f in ("ec_booking_owner", "ec_account_owner", "ec_brand_source", "ec_can_chuan_hoa"):
            self.assertIn(f, ten, "thieu trong fixtures: " + f)
            self.assertIn('"Brand-%s"' % f, hooks, "thieu khai trong hooks.py: " + f)

    def test_doctype_khoa_ban_chup_ca_phong_ban(self):
        src = _read("doctype", "ec_booking_request", "ec_booking_request.py")
        self.assertIn("_snapshot_lock", src)
        i = src.index("_KHOA_SAU_KHI_GUI")
        self.assertIn('"department"', src[i:i + 300])


if __name__ == "__main__":
    unittest.main(verbosity=2)
