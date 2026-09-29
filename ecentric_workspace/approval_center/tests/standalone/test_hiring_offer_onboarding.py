"""Chuoi tuyen dung Hiring -> Offer -> New Staff Preparation -> chao mung ngay onboard (28/09/2026).

Hoan chot 28/09:
  * Hiring duyet xong -> buoc "HR tuyen dung" (Role EC Recruiter), nut "Tao Offer" tren phieu;
  * Offer: Line manager -> HR & CnB -> HOF -> CEO; vi tri/LM chep tu Hiring, luong kin;
  * Offer duyet xong -> TU TAO New Staff Preparation (o nen), cac ben chuan bi SONG SONG;
  * Ngay onboard: popup trang chu tu 08:30, thiep Teams 10:00.
Chay CODE THAT cua cac service tren frappe + engine gia (khong can bench):
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hiring_offer_onboarding.py
"""
import copy
import datetime as _dt
import importlib.util
import json
import os
import re
import sys
import types

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_FEAT = os.path.join(_ROOT, "approval_center", "features")
REC, HR2, LM, CEO, SM = "rec@x", "rec2@x", "lm@x", "ceo@x", "admin@x"


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return dict.get(self, k)

    def __setattr__(self, k, v):
        self[k] = v


class Err(Exception):
    pass


class PermErr(Err):
    pass


class World:
    def __init__(self):
        self.t = {}
        self.saved = None
        self.roles = {REC: {"EC Recruiter"}, HR2: {"EC Recruiter"}, SM: {"System Manager"}}
        self.users = {u: Obj(enabled=1, user_type="System User") for u in (REC, HR2, LM, CEO, SM)}
        self.calls = []
        self.conf = {}
        self.now = _dt.datetime(2026, 10, 1, 9, 0)
        self.seq = 0
        self.fulfillers = [REC, HR2]
        self.fail_submit_for = set()

    def tbl(self, dt):
        return self.t.setdefault(dt, {})

    def add(self, dt, **row):
        self.seq += 1
        row.setdefault("name", "%s-%03d" % (dt.split()[-1][:4].upper(), self.seq))
        self.tbl(dt)[row["name"]] = Obj(row)
        return row["name"]

    def commit(self):
        self.saved = copy.deepcopy(self.t)

    def rollback(self):
        if self.saved is not None:
            self.t = copy.deepcopy(self.saved)


def _match(r, f):
    for k, v in (f or {}).items():
        if isinstance(v, (list, tuple)):
            op, val = v[0], v[1]
            if op == "in" and r.get(k) not in val:
                return False
            if op == "!=" and r.get(k) == val:
                return False
        elif r.get(k) != v:
            return False
    return True


def make_frappe(w):
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.PermissionError = PermErr
    fr.session = types.SimpleNamespace(user=REC)

    class Flags(dict):
        def __getattr__(self, k):
            return self.get(k)

        def __setattr__(self, k, v):
            self[k] = v
    fr.flags = Flags()
    fr.conf = w.conf
    fr.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))

    def throw(msg, exc=None):
        raise (exc or Err)(msg)
    fr.throw = throw
    fr.get_roles = lambda u=None: sorted(w.roles.get(u or fr.session.user, ()))
    fr.parse_json = lambda s: json.loads(s) if isinstance(s, str) else s
    fr.log_error = lambda title=None, message=None, **k: w.calls.append(("log", title, message))
    fr.get_traceback = lambda: "tb"
    fr.enqueue = lambda method, **k: w.calls.append(("enqueue", method, k))

    class Doc(Obj):
        def is_new(self):
            return not self.get("_saved")

        def set(self, k, v):
            self[k] = v

        def get(self, k, d=None):
            return dict.get(self, k, d)

        def as_dict(self):
            return dict(self)

        def save(self, ignore_permissions=False):
            dt = self["doctype"]
            if not self.get("name"):
                w.seq += 1
                self["name"] = "%s-%03d" % ({"EC New Staff Preparation": "NSP", "EC Offer Request": "OFFR"}.get(dt, "DOC"), w.seq)
            ctl = w.controllers.get(dt)
            if ctl:
                ctl(self)
            self["_saved"] = 1
            w.tbl(dt)[self["name"]] = Obj({k: v for k, v in self.items()})
            return self
        insert = save

    def get_doc(dt, name=None):
        if isinstance(dt, dict):
            d = Doc(dt)
            return d
        row = w.tbl(dt).get(name)
        if row is None:
            raise Err("khong co %s %s" % (dt, name))
        d = Doc(copy.deepcopy(dict(row)))
        d["doctype"] = dt
        d["_saved"] = 1
        return d
    fr.get_doc = get_doc
    fr.new_doc = lambda dt: Doc(doctype=dt)

    def get_all(dt, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None, **k):
        rows = [r for r in w.tbl(dt).values() if _match(r, filters)]
        if pluck:
            return [r.get(pluck) for r in rows]
        if fields:
            return [Obj({f: r.get(f) for f in fields}) for r in rows]
        return [Obj(r) for r in rows]
    fr.get_all = get_all

    def get_value(dt, name, field=None, as_dict=False, for_update=False, **k):
        if dt == "User":
            u = w.users.get(name)
            if u is None:
                return None
            if isinstance(field, (list, tuple)):
                return Obj({f: u.get(f) for f in field})
            return u.get(field)
        if isinstance(name, dict):
            hit = [r for r in w.tbl(dt).values() if _match(r, name)]
            row = hit[0] if hit else None
        else:
            row = w.tbl(dt).get(name)
        if row is None:
            return None
        if isinstance(field, (list, tuple)):
            return Obj({f: row.get(f) for f in field})
        return row.get(field)

    def set_value(dt, name, f, v=None, update_modified=True):
        w.tbl(dt)[name].update(f if isinstance(f, dict) else {f: v})

    def exists(dt, name=None):
        if isinstance(name, dict):
            return any(_match(r, name) for r in w.tbl(dt).values())
        if dt == "DocType":
            return True
        return name in w.tbl(dt)

    def sql(q, args=()):
        m = re.match(r"\s*update `tab([^`]+)` set fulfillment_owner=%s, fulfillment_status='In Progress'\s+where name=%s and fulfillment_status='Assigned'", q)
        if m:
            row = w.tbl(m.group(1)).get(args[1])
            if row and row.get("fulfillment_status") == "Assigned":
                row.update(fulfillment_owner=args[0], fulfillment_status="In Progress")
            return []
        m = re.match(r"\s*select 1 from `tab([^`]+)` where name=%s and fulfillment_owner=%s", q)
        if m:
            row = w.tbl(m.group(1)).get(args[0])
            return [(1,)] if row and row.get("fulfillment_owner") == args[1] else []
        raise AssertionError("sql khong mong doi: " + q)

    fr.db = types.SimpleNamespace(get_value=get_value, set_value=set_value, exists=exists, sql=sql,
                                  commit=w.commit, rollback=w.rollback)
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: w.now
    utils.nowdate = lambda: w.now.date().isoformat()
    utils.getdate = lambda v: v if isinstance(v, _dt.date) and not isinstance(v, _dt.datetime) else _dt.date.fromisoformat(str(v)[:10])
    fr.utils = utils
    return fr


def make_engine(w, fr):
    e = types.ModuleType("engine")

    def submit(dt, name, atype, requester):
        if name in w.fail_submit_for:
            raise Err("Nhom Operation chua co ai")
        ar = w.add("EC Approval Request", reference_doctype=dt, reference_name=name, approval_type=atype,
                   requested_by=requester, approval_status="Pending", current_level=1)
        w.calls.append(("submit", dt, name, requester))
        return ar
    e.submit = submit
    e.resubmit = lambda req, actor=None, restart=False: w.calls.append(("resubmit", req, restart))
    e.notify = lambda users, subj, dt, name: w.calls.append(("notify", tuple(sorted(users)), subj, name))
    e.assign = lambda dt, name, users, desc=None, date=None, fulfillment=False: w.calls.append(("assign", name, tuple(users), fulfillment))
    e.resolve_participants = lambda parts, requester, context=None: [(u, "Role: EC Recruiter") for u in w.fulfillers] if parts else []
    e.resolve_sla = lambda *a, **k: None
    e.ensure_sole_todo = lambda dt, name, user, desc=None, date=None: w.calls.append(("sole_todo", name, user))
    e.log_action = lambda req, action, actor, level_no=None, comment=None, **k: w.calls.append(("log_action", req, action, actor, comment))
    e.close_fulfillment_todos = lambda dt, name, keep_user=None: w.calls.append(("close_ff", name))
    e.is_active_process_fulfiller = lambda atype, user=None: "EC Recruiter" in w.roles.get(user, ())
    e.request_label = lambda dt, name, atype=None: name
    return e


def _load(path, name, mods):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def env():
    w = World()
    w.controllers = {}
    fr = make_frappe(w)
    eng = make_engine(w, fr)
    keep = {k: v for k, v in sys.modules.items() if k == "frappe" or k.startswith("frappe.") or k.startswith("ecentric_workspace")}
    for k in list(sys.modules):
        if k == "frappe" or k.startswith("frappe.") or k.startswith("ecentric_workspace"):
            del sys.modules[k]
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = fr.utils
    pk = ["ecentric_workspace", "ecentric_workspace.approval_center", "ecentric_workspace.approval_center.shared",
          "ecentric_workspace.approval_center.shared.workflow", "ecentric_workspace.approval_center.shared.requests",
          "ecentric_workspace.approval_center.features"]
    for p in pk:
        sys.modules[p] = types.ModuleType(p)
    sys.modules["ecentric_workspace.approval_center.shared.workflow"].transitions = eng
    sys.modules["ecentric_workspace.approval_center.shared.workflow.transitions"] = eng
    cmd = types.ModuleType("cmd")
    cmd.attach_extra_files = lambda doc, urls: w.calls.append(("attach", doc["name"], tuple(urls or ())))
    sys.modules["ecentric_workspace.approval_center.shared.requests.command_service"] = cmd
    mods = {}
    for feat in ("hiring_request", "offer_request", "new_staff_preparation"):
        for p in ("ecentric_workspace.approval_center.features.%s" % feat,
                  "ecentric_workspace.approval_center.features.%s.application" % feat):
            sys.modules[p] = types.ModuleType(p)
    mods["hiring"] = _load(os.path.join(_FEAT, "hiring_request", "application", "service.py"),
                           "ecentric_workspace.approval_center.features.hiring_request.application.service", mods)
    sys.modules["ecentric_workspace.approval_center.features.hiring_request.application"].service = mods["hiring"]
    mods["offer"] = _load(os.path.join(_FEAT, "offer_request", "application", "service.py"),
                          "ecentric_workspace.approval_center.features.offer_request.application.service", mods)
    mods["nsp"] = _load(os.path.join(_FEAT, "new_staff_preparation", "application", "service.py"),
                        "ecentric_workspace.approval_center.features.new_staff_preparation.application.service", mods)
    mods["welcome"] = _load(os.path.join(_FEAT, "new_staff_preparation", "application", "welcome.py"),
                            "ecentric_workspace.approval_center.features.new_staff_preparation.application.welcome", mods)
    w.fr, w.eng, w.m = fr, eng, mods
    yield w
    for k in list(sys.modules):
        if k == "frappe" or k.startswith("frappe.") or k.startswith("ecentric_workspace"):
            del sys.modules[k]
    sys.modules.update(keep)


def _hiring(w, status="Approved", ff="Assigned", owner=None, vac=2):
    ar = w.add("EC Approval Request", approval_status=status, approval_process="HIRING_REQUEST-V1")
    h = w.add("EC Hiring Request", request_title="Hiring - Data Intern", position="Data Intern",
              employment_type="Intern", line_manager=LM, department="Operation - EC", company="EC",
              number_of_vacancy=vac, approval_request=ar, requested_by="mgr@x",
              fulfillment_status=ff, fulfillment_owner=owner)
    w.tbl("EC Approval Process")["HIRING_REQUEST-V1"] = Obj(name="HIRING_REQUEST-V1", participants=[
        Obj(participant_purpose="Fulfiller", source_type="Role", role="EC Recruiter")], fulfillment_sla_policy=None)
    w.tbl("EC Approval Request")[ar]["approval_process"] = "HIRING_REQUEST-V1"
    return h


# ============================== HIRING: buoc HR tuyen dung ==============================
def test_hiring_duyet_xong_vao_hang_doi_ec_recruiter(env):
    w = env
    h = _hiring(w, ff=None)
    w.m["hiring"].on_final_approval(h)
    assert w.tbl("EC Hiring Request")[h]["fulfillment_status"] == "Assigned"
    assert ("assign", h, (REC, HR2), True) in w.calls
    assert any(c[0] == "notify" and "mgr@x" in c[1] and REC in c[1] for c in w.calls)


def test_hiring_khong_ai_giu_role_thi_bao_loi_co_tieng(env):
    w = env
    w.fulfillers = []
    h = _hiring(w, ff=None)
    w.m["hiring"].on_final_approval(h)
    assert w.tbl("EC Hiring Request")[h]["fulfillment_status"] == "Assigned"
    assert any(c[0] == "log" and "EC Recruiter" in (c[1] or "") for c in w.calls)


def test_hiring_nhan_viec_cong_rong_va_khong_cuop(env):
    w = env
    h = _hiring(w)
    w.fr.session.user = "outsider@x"
    with pytest.raises(Err):
        w.m["hiring"].claim_fulfillment(h)
    w.fr.session.user = REC
    w.m["hiring"].claim_fulfillment(h)            # khong ToDo nhung la EC Recruiter -> duoc
    row = w.tbl("EC Hiring Request")[h]
    assert (row["fulfillment_status"], row["fulfillment_owner"]) == ("In Progress", REC)
    assert w.m["hiring"].claim_fulfillment(h)["idempotent"]
    w.fr.session.user = HR2
    with pytest.raises(Err):
        w.m["hiring"].claim_fulfillment(h)        # nguoi khac dang giu


def test_hiring_hoan_tat_bat_buoc_ghi_chu_va_chi_chu_viec(env):
    w = env
    h = _hiring(w, ff="In Progress", owner=REC)
    w.fr.session.user = HR2
    with pytest.raises(Err):
        w.m["hiring"].complete_fulfillment(h, payload=json.dumps({"fulfillment_summary": "x"}))
    w.fr.session.user = REC
    with pytest.raises(Err):
        w.m["hiring"].complete_fulfillment(h, payload=json.dumps({"fulfillment_summary": "  "}))
    w.m["hiring"].complete_fulfillment(h, payload=json.dumps({"fulfillment_summary": "Du 2/2",
                                                              "_attachments": ["/private/files/a.pdf"]}))
    row = w.tbl("EC Hiring Request")[h]
    assert (row["fulfillment_status"], row["completed_by"], row["fulfillment_summary"]) == ("Completed", REC, "Du 2/2")
    assert ("attach", h, ("/private/files/a.pdf",)) in w.calls
    assert ("close_ff", h) in w.calls
    with pytest.raises(Err):
        w.m["hiring"].complete_fulfillment(h, payload=json.dumps({"fulfillment_summary": "lan 2"}))


@pytest.mark.parametrize("status,ff,user,ok", [
    ("Approved", "Assigned", REC, True), ("Approved", "In Progress", HR2, True),
    ("Approved", "Completed", REC, False), ("Pending", None, REC, False),
    ("Pending", "Assigned", REC, False),     # du lieu lech: phieu chua duyet thi KHONG, du co hang doi
    ("Approved", "Assigned", "outsider@x", False), ("Approved", "Assigned", SM, True)])
def test_ai_duoc_tao_offer(env, status, ff, user, ok):
    w = env
    h = _hiring(w, status=status, ff=ff)
    assert bool(w.m["hiring"].can_create_offer(h, user)) is ok


def test_danh_sach_offer_khong_lo_luong_va_an_nhap_nguoi_khac(env):
    w = env
    h = _hiring(w)
    a1 = w.add("EC Approval Request", approval_status="Approved")
    w.add("EC Offer Request", name="OF-1", hiring_request=h, candidate_name="A", onboard_date="2026-10-05",
          approval_request=a1, requested_by=REC, compensation="20tr")
    w.add("EC Offer Request", name="OF-2", hiring_request=h, candidate_name="B", requested_by=HR2,
          compensation="9tr")                      # nhap cua nguoi khac
    w.add("EC Offer Request", name="OF-3", hiring_request=h, candidate_name="C", requested_by=REC)
    rows = w.m["hiring"].offers_of(h, REC)
    assert [r["name"] for r in rows] == ["OF-1", "OF-3"]
    assert all("compensation" not in r for r in rows)
    blk = w.m["hiring"].hiring_block(Obj(name=h, number_of_vacancy=2), None)
    assert blk["offered"] == 1 and blk["vacancy"] == 2 and blk["offer_route"].endswith(h)


# ============================== OFFER ==============================
def _offer_draft(w, h, user=REC, **kw):
    d = w.fr.new_doc("EC Offer Request")
    d.update(dict(hiring_request=h, requested_by=user, candidate_name="Nguyen Van A",
                  onboard_date="2026-10-10", probation_end_date="2027-01-10", mobile_phone="0900",
                  compensation="15.000.000 VND", resume="/private/files/cv.pdf"), **kw)
    return d


def test_prepare_draft_chep_ban_chup_tu_hiring_khong_nhan_tu_client(env):
    w = env
    h = _hiring(w)
    d = _offer_draft(w, h, position="Gia", line_manager="hacker@x", department="X")
    w.m["offer"].prepare_draft(d)
    assert (d["position"], d["line_manager"], d["department"], d["employment_type"]) == \
        ("Data Intern", LM, "Operation - EC", "Intern")


def test_prepare_draft_chan_nguoi_ngoai_va_thieu_hiring(env):
    w = env
    h = _hiring(w)
    with pytest.raises(Err):
        w.m["offer"].prepare_draft(_offer_draft(w, h, user="outsider@x"))
    with pytest.raises(Err) as e:
        w.m["offer"].prepare_draft(_offer_draft(w, None))
    assert "Tạo Offer" in str(e.value)            # chi duong: mo tu Hiring, khong phai "khong co quyen"
    closed = _hiring(w, ff="Completed")
    with pytest.raises(Err):
        w.m["offer"].prepare_draft(_offer_draft(w, closed))


def _saved_offer(w, h, **kw):
    d = _offer_draft(w, h, **kw)
    w.m["offer"].prepare_draft(d)
    d.save()
    return d["name"]


def test_gui_offer_tu_nhan_hiring_va_goi_engine(env):
    w = env
    h = _hiring(w)
    o = _saved_offer(w, h)
    ar = w.m["offer"].submit(o)
    row = w.tbl("EC Offer Request")[o]
    assert row["approval_request"] == ar and row["material_signature"]
    assert row["request_title"] == "Offer - Nguyen Van A - Data Intern - Operation - EC"
    assert ("submit", "EC Offer Request", o, REC) in w.calls
    hr = w.tbl("EC Hiring Request")[h]
    assert (hr["fulfillment_status"], hr["fulfillment_owner"]) == ("In Progress", REC)   # tu nhan


@pytest.mark.parametrize("kw,msg", [
    (dict(probation_end_date="2026-09-01"), "thử việc"),
    (dict(compensation=""), "bắt buộc"),
    (dict(resume=None), "bắt buộc")])
def test_gui_offer_kiem_du_lieu(env, kw, msg):
    w = env
    h = _hiring(w)
    o = _saved_offer(w, h, **kw)
    with pytest.raises(Err) as e:
        w.m["offer"].submit(o)
    assert msg in str(e.value)
    assert not any(c[0] == "submit" for c in w.calls)


def test_gui_offer_chan_line_manager_khong_hoat_dong(env):
    w = env
    h = _hiring(w)
    w.users[LM].enabled = 0
    o = _saved_offer(w, h)
    with pytest.raises(Err) as e:
        w.m["offer"].submit(o)
    assert "Line manager" in str(e.value)


def test_offer_duyet_xong_tao_nsp_o_nen_sau_commit(env):
    w = env
    h = _hiring(w)
    o = _saved_offer(w, h)
    w.m["offer"].submit(o)
    w.m["offer"].on_final_approval(o)
    enq = [c for c in w.calls if c[0] == "enqueue"]
    assert enq and enq[0][1].endswith("new_staff_preparation.application.service.create_from_offer")
    assert enq[0][2]["enqueue_after_commit"] is True and enq[0][2]["offer_name"] == o
    note = [c for c in w.calls if c[0] == "notify" and "Offer đã được duyệt" in c[2]]
    assert note and set(note[0][1]) == {REC, LM}
    assert not any(c[0] == "notify" and "15.000.000" in str(c) for c in w.calls)   # luong khong vao thong bao


# ============================== NEW STAFF PREPARATION ==============================
def _approved_offer(w):
    h = _hiring(w)
    o = _saved_offer(w, h)
    ar = w.m["offer"].submit(o)
    w.tbl("EC Approval Request")[ar]["approval_status"] = "Approved"
    return o


def test_khong_tao_tay_nsp(env):
    w = env
    with pytest.raises(Err):
        w.m["nsp"].prepare_draft(w.fr.new_doc("EC New Staff Preparation"))


def test_tao_tu_offer_chep_du_khong_co_luong_va_idempotent(env):
    w = env
    o = _approved_offer(w)
    n = w.m["nsp"].create_from_offer(o)
    nsp = w.tbl("EC New Staff Preparation")[n]
    assert nsp["offer_request"] == o and nsp["requested_by"] == REC
    assert nsp["candidate_name"] == "Nguyen Van A" and nsp["onboard_date"] == "2026-10-10"
    assert "compensation" not in nsp and "resume" not in nsp
    assert nsp["approval_request"] and nsp["request_title"].startswith("New Staff Preparation - Nguyen Van A")
    assert w.tbl("EC Offer Request")[o]["new_staff_preparation"] == n
    so_nsp = len(w.tbl("EC New Staff Preparation"))
    assert w.m["nsp"].create_from_offer(o) == n                     # chay lai: khong tao them
    assert len(w.tbl("EC New Staff Preparation")) == so_nsp
    assert len([c for c in w.calls if c[0] == "submit" and c[1] == "EC New Staff Preparation"]) == 1


def test_tao_nsp_hong_thi_rollback_ghi_loi_bao_hr(env):
    w = env
    o = _approved_offer(w)
    w.commit()
    orig = w.eng.submit

    def hong(dt, name, atype, requester):
        if dt == "EC New Staff Preparation":
            raise Err("Nhom Operation chua co ai")
        return orig(dt, name, atype, requester)
    w.eng.submit = hong
    assert w.m["nsp"].create_from_offer(o) is None
    assert not w.tbl("EC New Staff Preparation")                        # rollback het
    assert not w.tbl("EC Offer Request")[o].get("new_staff_preparation")
    assert any(c[0] == "log" and o in (c[1] or "") for c in w.calls)
    assert any(c[0] == "notify" and c[1] == (REC,) and "Tạo lại" in c[2] for c in w.calls)
    with pytest.raises(Err):
        w.m["nsp"].create_from_offer(o, raise_errors=True)


def test_offer_chua_duyet_khong_tao_nsp(env):
    w = env
    h = _hiring(w)
    o = _saved_offer(w, h)
    w.m["offer"].submit(o)
    with pytest.raises(Err):
        w.m["nsp"].create_from_offer(o, raise_errors=True)


def _nsp(w):
    o = _approved_offer(w)
    return w.m["nsp"].create_from_offer(o)


def test_sua_loi_gioi_thieu_va_ngay_onboard(env):
    w = env
    n = _nsp(w)
    w.fr.session.user = "outsider@x"
    with pytest.raises(PermErr):
        w.m["nsp"].update_welcome(n, welcome_intro="hi")
    w.fr.session.user = HR2                                               # EC Recruiter khac
    assert w.m["nsp"].update_welcome(n, welcome_intro="Em chao ca nha")["changed"]
    w.tbl("EC New Staff Preparation")[n]["welcome_teams_sent_at"] = "x"
    w.m["nsp"].update_welcome(n, onboard_date="2026-10-20")
    row = w.tbl("EC New Staff Preparation")[n]
    assert row["onboard_date"] == "2026-10-20" and row["welcome_teams_sent_at"] is None
    assert any(c[0] == "notify" and "Đổi ngày onboard" in c[2] for c in w.calls)
    with pytest.raises(Err):
        w.m["nsp"].update_welcome(n, onboard_date="2026-09-01")         # qua khu
    assert not w.m["nsp"].update_welcome(n, welcome_intro="Em chao ca nha")["changed"]


def test_checklist_nhom(env):
    w = env
    n = _nsp(w)
    ar = w.tbl("EC New Staff Preparation")[n]["approval_request"]
    for g, u, st in (("HOF", "hof@x", "Approved"), ("CnB", "c1@x", "Skipped"), ("CnB", "c2@x", "Approved"),
                     ("Operation", "op@x", "Pending")):
        w.add("EC Approval Request Approver", approval_request=ar, participant_group=g, approver=u,
              status=st, decided_at="t", comment=None, creation=str(w.seq))
    blk = w.m["nsp"].nsp_block(w.fr.get_doc("EC New Staff Preparation", n),
                               Obj(name=ar, approval_status="Pending"))
    g = {x["group"]: x for x in blk["groups"]}
    assert g["HOF"]["done"] and g["CnB"]["done"] and g["CnB"]["by"] == "c2@x"
    assert not g["Operation"]["done"] and g["CnB"]["members"] == ["c1@x", "c2@x"]


# ============================== CHAO MUNG NGAY ONBOARD ==============================
def _onboard_today(w, **kw):
    n = _nsp(w)
    w.tbl("EC New Staff Preparation")[n].update(onboard_date=w.now.date().isoformat(), **kw)
    return n


def test_popup_chi_tu_0830_va_chi_phieu_con_song(env):
    w = env
    n = _onboard_today(w, welcome_intro="Em la A")
    dead = _onboard_today(w)
    w.tbl("EC Approval Request")[w.tbl("EC New Staff Preparation")[dead]["approval_request"]]["approval_status"] = "Cancelled"
    w.now = _dt.datetime(2026, 10, 1, 8, 29)
    assert w.m["welcome"].welcome_today() == {"rows": []}
    w.now = _dt.datetime(2026, 10, 1, 8, 30)
    rows = w.m["welcome"].welcome_today()["rows"]
    assert [r["name"] for r in rows] == [n]
    assert rows[0]["welcome_intro"] == "Em la A" and "compensation" not in rows[0]
    w.fr.session.user = "Guest"
    assert w.m["welcome"].welcome_today() == {"rows": []}
    w.fr.session.user = REC
    w.conf["ec_onboard_welcome_disabled"] = 1
    assert w.m["welcome"].welcome_today() == {"rows": []}


def test_teams_10h_gui_mot_lan_va_ghi_ket_qua(env):
    w = env
    n = _onboard_today(w, welcome_intro="Em la A")
    posted = []
    w.m["welcome"]._post = lambda url, data: posted.append((url, data)) or (202, "")
    assert w.m["welcome"].send_welcome_teams()["skipped"] == "no_webhook"
    assert any(c[0] == "log" and "webhook" in (c[1] or "") for c in w.calls) and not posted
    w.conf["ec_onboard_welcome_webhook_url"] = "https://example.invalid/hook"
    assert w.m["welcome"].send_welcome_teams()["sent"] == 1
    card = posted[0][1]["attachments"][0]["content"]
    txt = json.dumps(card, ensure_ascii=False)
    assert "NGUYEN VAN A" in txt and "Em la A" in txt and "Data Intern" in txt
    row = w.tbl("EC New Staff Preparation")[n]
    assert row["welcome_teams_sent_at"] and row["welcome_teams_result"].startswith("OK")
    assert w.m["welcome"].send_welcome_teams() == {"sent": 0}           # khong gui lan 2
    assert len(posted) == 1


def test_teams_loi_http_khong_danh_dau_da_gui(env):
    w = env
    n = _onboard_today(w)
    w.conf["ec_onboard_welcome_webhook_url"] = "https://example.invalid/hook"
    w.m["welcome"]._post = lambda url, data: (400, "bad card")
    assert w.m["welcome"].send_welcome_teams()["sent"] == 0
    row = w.tbl("EC New Staff Preparation")[n]
    assert row["welcome_teams_sent_at"] is None and "400" in row["welcome_teams_result"]
    assert any(c[0] == "log" and "HTTP 400" in (c[1] or "") for c in w.calls)   # co Error Log
    # 10:15 chay lai: chi gui bu phieu loi, gui xong thi thoi
    w.m["welcome"]._post = lambda url, data: (202, "")
    assert w.m["welcome"].send_welcome_teams()["sent"] == 1
    assert w.m["welcome"].send_welcome_teams() == {"sent": 0}
    w.conf["ec_onboard_welcome_disabled"] = 1
    assert w.m["welcome"].send_welcome_teams() == {"skipped": "disabled"}


def test_thiep_khong_co_loi_gioi_thieu_van_hop_le(env):
    w = env
    card = w.m["welcome"].build_card({"candidate_name": "b", "position": "P", "department": "D",
                                      "welcome_intro": ""})
    body = card["attachments"][0]["content"]["body"]
    assert card["type"] == "message" and card["attachments"][0]["contentType"].endswith("adaptive")
    assert "Đôi lời giới thiệu" not in json.dumps(body, ensure_ascii=False)
