# Copyright (c) 2026, eCentric and contributors
"""E2E vong doi: cong ky tat -> duyet van di + GHI NO -> tra no (guard.py, ham THAT).

Va nua sau: validate_completion - cai cong duy nhat cho phep mot cap "yeu cau ky so"
dong lai. Moi phep kiem doc DB (gia lap), khong tin frappe.flags.

Nhung dieu giu:

  1. Cap yeu cau ky + cong MO + khong co chu ky da xac minh -> CHAN (PermissionError,
     ma "no_completion_marker") cho MOI vai tro - khong break-glass.
  2. Cong TAT -> duyet DI TIEP nhung mon no duoc ghi (signature_deferred=1 + comment +
     su kien SignatureDeferred); loai phieu khong dung ky so thi KHONG ghi gi.
  3. settle_signature_debt: bat buoc ly do; chi 'signed'/'waived'; goi lan hai la
     idempotent (khong ghi them, khong log them); khong co no thi tu choi.
  4. validate_completion tren goi Superseded -> chan (package_not_active); da co chan ky
     khac dong cap nay -> chan (level_already_completed_by); DSR da terminal -> chan
     (dsr_not_in_signed_state) - bam duyet hai lan khong dong cap hai lan.
  5. Happy path PHAI qua (fixture hop le) - de cac test chan o tren do vi DUNG ly do.

Su kien emit ra duoc doi chieu voi Select event_type trong DocType JSON that (bay: stub
nhan moi thu -> emit sai ten van xanh).
"""
import glob
import io
import json
import os
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
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class _Throw(Exception):
    pass


class _PermissionError(_Throw):
    pass


class _ValidationError(_Throw):
    pass


_STANDARD = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}


def _doctype_fields():
    out = {}
    for path in glob.glob(os.path.join(_ROOT, "*", "doctype", "*", "*.json")):
        try:
            doc = json.loads(io.open(path, encoding="utf-8").read())
        except ValueError:
            continue
        if doc.get("doctype") != "DocType" or not doc.get("name"):
            continue
        out[doc["name"]] = {f.get("fieldname") for f in doc.get("fields", [])
                            if f.get("fieldname")} | _STANDARD
    return out


_FIELDS = _doctype_fields()


def _event_types_declared():
    j = json.loads(_read("approval_center", "doctype", "ec_digital_signature_event",
                         "ec_digital_signature_event.json"))
    for f in j["fields"]:
        if f.get("fieldname") == "event_type":
            return set((f.get("options") or "").split("\n"))
    raise AssertionError("khong tim thay truong event_type")


_EVENT_TYPES = _event_types_declared()


class _FakeDB(object):
    """Bang du lieu (doctype, name) -> row. get_value doi chieu truong voi DocType JSON."""

    def __init__(self, tables):
        self.tables = tables            # {doctype: {name: dict}}
        self.writes = []

    def _row_by_filters(self, dt, filters):
        for name, row in self.tables.get(dt, {}).items():
            ok = True
            for k, v in filters.items():
                if isinstance(v, list):
                    op, val = v
                    if op == "in" and row.get(k) not in val:
                        ok = False
                    if op == "!=" and row.get(k) == val:
                        ok = False
                elif row.get(k) != v:
                    ok = False
            if ok:
                return name, row
        return None, None

    def _check(self, dt, fields):
        known = _FIELDS.get(dt)
        if known is None:
            return
        fl = [fields] if isinstance(fields, str) else list(fields or [])
        for f in fl:
            if f == "*":
                continue
            assert f in known, "truong %r khong co tren DocType %s" % (f, dt)

    def get_value(self, dt, name_or_filters, fields=None, as_dict=False, for_update=False,
                  order_by=None, **kw):
        self._check(dt, fields)
        if isinstance(name_or_filters, dict):
            name, row = self._row_by_filters(dt, name_or_filters)
        else:
            name, row = name_or_filters, self.tables.get(dt, {}).get(name_or_filters)
        if row is None:
            return None
        if isinstance(fields, str) or fields is None:
            f = fields or "name"
            return row.get(f, name if f == "name" else None)
        out = {x: (name if x == "name" and "name" not in row else row.get(x)) for x in fields}
        return _D(out) if as_dict else tuple(out.values())

    def set_value(self, dt, name, field, value=None):
        self.writes.append((dt, name, field, value))
        row = self.tables.setdefault(dt, {}).setdefault(name, {})
        if isinstance(field, dict):
            row.update(field)
        else:
            row[field] = value

    def exists(self, dt, filters):
        if isinstance(filters, dict):
            name, row = self._row_by_filters(dt, filters)
            return name
        return filters in self.tables.get(dt, {})

    def count(self, dt, filters=None):
        n = 0
        for _name, _row in self.tables.get(dt, {}).items():
            nm, _r = self._row_by_filters(dt, filters or {})
            if nm == _name:
                n += 1
        return n


def _load_guard(tables, profiles=(), profile_levels=(), approver_levels=(),
                sm_ok=True, flags=None):
    import sys

    rec = {"events": [], "logs": []}
    db = _FakeDB(tables)

    def get_all(dt, filters=None, fields=None, limit_page_length=None, order_by=None,
                distinct=False, pluck=None, **kw):
        if dt == "EC Digital Signature Profile":
            return [_D(p) for p in profiles]
        if dt == "EC Approval Request Approver":
            rows = [_D(a) for a in approver_levels]
            if order_by and "desc" in order_by:
                rows.sort(key=lambda r: r["level_no"], reverse=True)
            return rows[:limit_page_length] if limit_page_length else rows
        return []

    frappe_mod = types.ModuleType("frappe")
    frappe_mod.db = db
    frappe_mod.get_all = get_all
    frappe_mod._ = lambda s: s
    frappe_mod._dict = _D
    frappe_mod.session = types.SimpleNamespace(user="admin.sm@ec.vn")
    frappe_mod.flags = flags or types.SimpleNamespace()
    frappe_mod.PermissionError = _PermissionError
    frappe_mod.ValidationError = _ValidationError
    frappe_mod.log_error = lambda *a, **kw: rec["logs"].append(("error_log", a))
    frappe_mod.get_traceback = lambda: "tb"

    def _throw(msg, exc=None):
        raise (exc or _Throw)(msg)

    frappe_mod.throw = _throw

    # profile-level exists() cho chinh sach "Selected Approval Levels"
    _orig_exists = db.exists

    def exists(dt, filters):
        if dt == "EC Digital Signature Profile Level":
            for pl in profile_levels:
                if all(pl.get(k) == v for k, v in filters.items()):
                    return "PLVL-1"
            return None
        return _orig_exists(dt, filters)

    db.exists = exists

    utils_mod = types.ModuleType("frappe.utils")
    utils_mod.now_datetime = lambda: "2026-09-01 11:00:00"
    frappe_mod.utils = utils_mod

    events_mod = types.ModuleType("events")

    def emit(event_type, **kwargs):
        assert event_type in _EVENT_TYPES, \
            "su kien %r chua khai bao trong DocType Event" % event_type
        rec["events"].append((event_type, kwargs))

    events_mod.emit = emit

    perms_mod = types.ModuleType("permissions")

    def assert_system_manager():
        rec["logs"].append(("sm_check",))
        if not sm_ok:
            raise _PermissionError("Can quyen System Manager")

    perms_mod.assert_system_manager = assert_system_manager

    engine_mod = types.ModuleType("transitions")
    engine_mod.log_action = lambda *a, **kw: rec["logs"].append(("log_action", a, kw))
    wf_pkg = types.ModuleType("ecentric_workspace.approval_center.shared.workflow")
    wf_pkg.transitions = engine_mod

    esign_pkg = types.ModuleType("ecentric_workspace.platform.esign")
    esign_pkg.events = events_mod
    esign_pkg.permissions = perms_mod

    mods = {
        "frappe": frappe_mod,
        "frappe.utils": utils_mod,
        "ecentric_workspace.platform.esign": esign_pkg,
        "ecentric_workspace.platform.esign.events": events_mod,
        "ecentric_workspace.platform.esign.permissions": perms_mod,
        "ecentric_workspace.approval_center.shared.workflow": wf_pkg,
        "ecentric_workspace.approval_center.shared.workflow.transitions": engine_mod,
    }
    saved = {k: sys.modules.get(k) for k in mods}
    for k, v in mods.items():
        sys.modules[k] = v
    env = {}
    try:
        exec(compile(_read("platform", "esign", "guard.py"), "guard.py", "exec"), env)
        return env, db, rec, (saved, sys)
    except Exception:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        raise


class _Ctx(object):
    def __init__(self, *a, **kw):
        self._a, self._kw = a, kw

    def __enter__(self):
        self.env, self.db, self.rec, (self._saved, self._sys) = _load_guard(*self._a, **self._kw)
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                self._sys.modules.pop(k, None)
            else:
                self._sys.modules[k] = v
        return False


# ---------------------------------------------------------------------------- #
# fixtures
# ---------------------------------------------------------------------------- #
def _profile_row(gates_open=True):
    return {"EC Digital Signature Provider Settings": {
        "SET-1": {"provider": "SCTS", "environment": "UAT",
                  "integration_enabled": 1,
                  "allow_signing": 1 if gates_open else 0,
                  "allow_production_signing": 0}},
            "EC Digital Signature Profile": {
        "PROF-1": {"approver_signature_policy": "All Approval Levels",
                   "requester_signature_required": 1,
                   "requester_role_title": None}}}


def _req(name="AR-1", level=2):
    return _D({"name": name, "current_level": level, "approval_status": "Pending",
               "reference_doctype": "EC Payment Request",
               "reference_name": "EC-PAYR-2026-00001", "approval_type": "PAYMENT_REQUEST"})


def _happy_tables(pkg_status="Active", other_completed=False, dsr_status="Signed"):
    t = _profile_row()
    t["EC Digital Signature Request"] = {
        "DSR-1": {"approval_request": "AR-1", "request_level": "RL-2",
                  "approver_row": "ROW-2", "approver": "sep@ec.vn", "action": "Sign",
                  "status": dsr_status, "package": "PKG-1", "package_version": 3,
                  "package_hash": "h" * 64, "verified_at": "2026-09-01 10:59:00"}}
    if other_completed:
        t["EC Digital Signature Request"]["DSR-0"] = {
            "approval_request": "AR-1", "request_level": "RL-2",
            "status": "Approval Completed", "action": "Sign"}
    t["EC Approval Request Level"] = {
        "RL-2": {"level_no": 2, "approval_request": "AR-1", "level_status": "Active"}}
    t["EC Approval Request Approver"] = {
        "ROW-2": {"approver": "sep@ec.vn", "level_no": 2, "status": "Pending",
                  "approval_request": "AR-1"}}
    t["EC Digital Signature Package"] = {
        "PKG-1": {"approval_request": "AR-1", "business_doctype": "EC Payment Request",
                  "business_name": "EC-PAYR-2026-00001", "status": pkg_status,
                  "package_version": 3, "package_hash": "h" * 64}}
    return t


_PROFILES = ({"name": "PROF-1", "provider": "SCTS", "environment": "UAT"},)
_APPROVERS = ({"level_no": 1}, {"level_no": 2})


class TestSignRequiredLevelFailsClosed(unittest.TestCase):
    def test_cong_mo_ma_khong_co_chu_ky_thi_chan_moi_vai_tro(self):
        with _Ctx(_happy_tables(), profiles=_PROFILES, approver_levels=_APPROVERS,
                  flags=types.SimpleNamespace()) as c:      # KHONG co call marker
            with self.assertRaises(_PermissionError) as ctx:
                c.env["assert_level_completable"](_req(), 2, "sep@ec.vn")
            self.assertIn("no_completion_marker", str(ctx.exception))
            self.assertIn("Duyệt & Ký", str(ctx.exception))
            # va TUYET DOI khong duoc ghi no trong truong hop nay (cong dang MO)
            debt = [w for w in c.db.writes if isinstance(w[2], dict)
                    and "signature_deferred" in w[2]]
            self.assertEqual(debt, [])

    def test_happy_path_du_chung_cu_thi_qua(self):
        flags = types.SimpleNamespace()
        setattr(flags, "ec_esign_completion_dsr", "DSR-1")
        with _Ctx(_happy_tables(), profiles=_PROFILES, approver_levels=_APPROVERS,
                  flags=flags) as c:
            self.assertTrue(c.env["validate_completion"]("DSR-1", _req(), 2, "sep@ec.vn"))

    def test_goi_superseded_thi_chan(self):
        with _Ctx(_happy_tables(pkg_status="Superseded"), profiles=_PROFILES,
                  approver_levels=_APPROVERS) as c:
            with self.assertRaises(_PermissionError) as ctx:
                c.env["validate_completion"]("DSR-1", _req(), 2, "sep@ec.vn")
            self.assertIn("package_not_active:Superseded", str(ctx.exception))

    def test_cap_da_co_chan_ky_khac_dong_thi_chan(self):
        with _Ctx(_happy_tables(other_completed=True), profiles=_PROFILES,
                  approver_levels=_APPROVERS) as c:
            with self.assertRaises(_PermissionError) as ctx:
                c.env["validate_completion"]("DSR-1", _req(), 2, "sep@ec.vn")
            self.assertIn("level_already_completed_by", str(ctx.exception))

    def test_dsr_da_terminal_thi_khong_dong_lan_hai(self):
        with _Ctx(_happy_tables(dsr_status="Approval Completed"), profiles=_PROFILES,
                  approver_levels=_APPROVERS) as c:
            with self.assertRaises(_PermissionError) as ctx:
                c.env["validate_completion"]("DSR-1", _req(), 2, "sep@ec.vn")
            self.assertIn("dsr_not_in_signed_state", str(ctx.exception))


class TestGateOffRecordsDebt(unittest.TestCase):
    def _tables(self):
        t = _profile_row(gates_open=False)
        t["EC Approval Request Level"] = {
            "RL-2": {"level_no": 2, "approval_request": "AR-1"}}
        return t

    def test_cong_tat_thi_di_tiep_va_ghi_no(self):
        with _Ctx(self._tables(), profiles=_PROFILES, approver_levels=_APPROVERS) as c:
            c.env["assert_level_completable"](_req(), 2, "sep@ec.vn")   # KHONG throw
            debt = [w for w in c.db.writes if isinstance(w[2], dict)
                    and w[2].get("signature_deferred") == 1]
            self.assertEqual(len(debt), 1, "phai ghi no chu ky khi cong tat")
            self.assertEqual([e[0] for e in c.rec["events"]], ["SignatureDeferred"])
            self.assertTrue(any(x[0] == "log_action" for x in c.rec["logs"]),
                            "mon no phai hien trong lich su phieu")

    def test_loai_khong_dung_ky_so_thi_khong_ghi_gi(self):
        with _Ctx({"EC Approval Request Level": {}}, profiles=(),
                  approver_levels=_APPROVERS) as c:
            c.env["assert_level_completable"](_req(), 2, "sep@ec.vn")
            self.assertEqual(c.db.writes, [])
            self.assertEqual(c.rec["events"], [])


class TestSettleSignatureDebt(unittest.TestCase):
    def _tables(self, settled=None, deferred=1):
        return {"EC Approval Request Level": {
            "RL-2": {"approval_request": "AR-1", "level_no": 2,
                     "signature_deferred": deferred,
                     "signature_settled_at": settled,
                     "signature_deferred_by": "sep@ec.vn"}}}

    def test_khong_ly_do_thi_chan(self):
        with _Ctx(self._tables()) as c:
            with self.assertRaises(_ValidationError):
                c.env["settle_signature_debt"]("RL-2", "signed", "   ")
            self.assertEqual(c.db.writes, [], "tu choi phai xay ra TRUOC khi ghi")

    def test_cach_xu_ly_la_phai_hop_le(self):
        with _Ctx(self._tables()) as c:
            with self.assertRaises(_ValidationError):
                c.env["settle_signature_debt"]("RL-2", "auto_sign", "ly do")

    def test_tra_no_ghi_nhan_va_de_lai_vet(self):
        with _Ctx(self._tables()) as c:
            out = c.env["settle_signature_debt"]("RL-2", "waived", "nguoi duyet da nghi viec")
            self.assertEqual(out, {"ok": True, "resolution": "waived"})
            self.assertTrue(any(w[2] == "signature_settled_at" for w in c.db.writes))
            self.assertEqual([e[0] for e in c.rec["events"]], ["SignatureDebtSettled"])
            logs = [x for x in c.rec["logs"] if x[0] == "log_action"]
            self.assertEqual(len(logs), 1)
            self.assertIn("nguoi duyet da nghi viec", str(logs[0]))

    def test_tra_no_hai_lan_la_idempotent(self):
        with _Ctx(self._tables()) as c:
            c.env["settle_signature_debt"]("RL-2", "signed", "da ky lai tren portal")
            n_writes, n_logs = len(c.db.writes), len(c.rec["logs"])
            out2 = c.env["settle_signature_debt"]("RL-2", "signed", "da ky lai tren portal")
            self.assertEqual(out2, {"ok": True, "already": True})
            self.assertEqual(len(c.db.writes), n_writes, "lan hai khong duoc ghi them")
            self.assertEqual(len([x for x in c.rec["logs"] if x[0] == "log_action"]), 1,
                             "lan hai khong duoc log them - lich su phieu khong phinh ra")

    def test_khong_co_no_thi_tu_choi(self):
        with _Ctx(self._tables(deferred=0)) as c:
            with self.assertRaises(_Throw) as ctx:
                c.env["settle_signature_debt"]("RL-2", "signed", "ly do")
            self.assertIn("không có nợ", str(ctx.exception))

    def test_khong_phai_system_manager_thi_dung_ngay_cua(self):
        with _Ctx(self._tables(), sm_ok=False) as c:
            with self.assertRaises(_PermissionError):
                c.env["settle_signature_debt"]("RL-2", "signed", "ly do")
            self.assertEqual(c.db.writes, [])


if __name__ == "__main__":
    unittest.main()
