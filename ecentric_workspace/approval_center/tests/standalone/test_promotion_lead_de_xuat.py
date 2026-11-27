"""Promotion "huong 2" (27/11/2026, Hoan chot): Lead de xuat cho nguoi minh quan ly (cap duoi truc tiep +
gian tiep theo reports_to) nhung KHONG thay / KHONG nhap luong; nguoi duyet dau tien co quyen xem luong
dien luong khi duyet (salary_pending); chua dien thi engine chan Duyet.

Case that: phuong.nguyen (Lead, khong xem duoc luong) quan ly 6 nguoi; quan ly cua Phuong la Linh Ngo
(truong phong, xem duoc luong phong minh).

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_promotion_lead_de_xuat.py
"""
import ast
import json
import pathlib
import sys
import types

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_promotion_ho_so as base  # noqa: E402  (dung lai stub frappe cua bo test cu)

APP = base.APP.parent          # goc package ecentric_workspace
Obj, Doc, W, Perm, Throw = base.Obj, base.Doc, base.W, base.Perm, base.Throw

LEVELS = [Obj(level_no=1, level_name="Direct Manager Review", level_status="In Progress"),
          Obj(level_no=2, level_name="CnB Review", level_status="Pending"),
          Obj(level_no=3, level_name="HOF Review", level_status="Pending"),
          Obj(level_no=4, level_name="CEO Review", level_status="Pending")]


def _org():
    E = lambda name, user, rt, dept="ECO - EC", status="Active", nm=None: Doc(  # noqa: E731
        doctype="Employee", name=name, employee_name=nm or name, department=dept, designation="Staff",
        company="EC", user_id=user, status=status, reports_to=rt)
    W.emps.update({
        "E-CEO": E("E-CEO", "ceo@x", None, dept="BOD - EC"),
        "E-LINH": E("E-LINH", "linh@x", "E-CEO", nm="Linh Ngo"),
        "E-PHUONG": E("E-PHUONG", "phuong@x", "E-LINH", nm="Phuong Nguyen"),
        "E-X1": E("E-X1", "x1@x", "E-PHUONG", nm="X1"),
        "E-X2": E("E-X2", "x2@x", "E-PHUONG", nm="X2"),
        "E-Y": E("E-Y", "y@x", "E-X1", nm="Y gian tiep"),
        "E-GHOST": E("E-GHOST", "ghost@x", "E-PHUONG", status="Left", nm="Ghost"),
        "E-Z": E("E-Z", "z@x", "E-GHOST", nm="Z duoi nguoi da nghi"),
        "E-OUT": E("E-OUT", "out@x", "E-LINH", nm="Out nguoi ngoai"),
        "E-C1": E("E-C1", "c1@x", "E-C2", dept="Loop - EC"),
        "E-C2": E("E-C2", "c2@x", "E-C1", dept="Loop - EC"),
    })
    for e in list(W.emps.values()):
        if e.name.startswith("E-") and e.get("department") and not any(r.employee == e.name for r in W.ssa):
            W.ssa.append(Obj(name="SSA-" + e.name, employee=e.name, docstatus=1, from_date="2026-01-01",
                             base=10000000, salary_structure="ST", company="EC", department=e.department))
    eco = {r.name for r in W.ssa if W.emps.get(r.employee) and W.emps[r.employee].get("department") == "ECO - EC"}
    allssa = {r.name for r in W.ssa}
    W.perms.update({"linh@x": eco, "phuong@x": set(), "x1@x": set(), "cnb@x": allssa, "ceo@x": allssa,
                    "mid@x": set()})


def _setup(env, user="phuong@x"):
    snap, svc = env()
    _org()
    fr = sys.modules["frappe"]
    fr.session.user = user
    W.levels = [Obj(x) for x in LEVELS]
    W.pending = {}            # (req, level) -> set(user)
    W.actions, W.submits = [], []
    W.biz_exists = set()
    old_get_all, old_get_value = fr.get_all, fr.db.get_value

    def get_all(dt, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None):
        if dt == "EC Approval Request Level":
            return [Obj(x) for x in W.levels]
        return old_get_all(dt, filters=filters, fields=fields, pluck=pluck, order_by=order_by,
                           limit_page_length=limit_page_length)
    fr.get_all = get_all

    def get_value(dt, name, fields=None, as_dict=False, for_update=False, **k):
        if dt in ("EC Promotion Request", "EC Approval Request"):
            row = W.req.get(name, {})
            if isinstance(fields, (list, tuple)):
                o = Obj({f: row.get(f) for f in fields})
                return o if as_dict else tuple(o.values())
            return row.get(fields)
        if dt == "Employee" and isinstance(name, dict) and isinstance(fields, (list, tuple)):
            e = next((e for e in W.emps.values() if e.user_id == name["user_id"]), None)
            return Obj({f: e.get(f) for f in fields}) if e else None
        return old_get_value(dt, name, fields, as_dict=as_dict, **k)
    fr.db.get_value = get_value

    def exists(dt, n=None):
        if dt == "Department":
            return True
        if dt == "EC Promotion Request":
            return n in W.biz_exists
        return (n in ("Engineer", "Senior Engineer")) if isinstance(n, str) else W.slip
    fr.db.exists = exists
    eng = sys.modules["ecentric_workspace.approval_center.shared.workflow.transitions"]
    eng.log_action = lambda *a, **k: W.actions.append((a, k))
    eng.submit = lambda *a, **k: W.submits.append((a, k)) or "APR-1"
    eng.resubmit = lambda *a, **k: W.actions.append(("resubmit", a, k))
    perm = types.ModuleType("perm")
    perm.is_actionable = lambda req, lvl, user=None, st=None: (
        st in ("Pending", "Information Required") and user in W.pending.get((req, lvl), set()))
    sys.modules["ecentric_workspace.approval_center.shared.workflow.permissions"] = perm
    sys.modules["ecentric_workspace.approval_center.shared.workflow"].permissions = perm
    return snap, svc, fr


def _draft(**kw):
    d = Doc(doctype="EC Promotion Request", name="P-9", request_title="T", requested_by="phuong@x",
            promoted_employee="E-X1", proposed_position="Senior Engineer", justification="gioi",
            effective_date_of_promotion="2026-12-01", current_position="Staff", department="ECO - EC",
            full_name="X1", approval_request=None)
    d.update(kw)
    return d


def _submitted(**kw):
    """Phieu Lead da gui, cho Linh o cap 1."""
    d = dict(doctype="EC Promotion Request", name="P-9", requested_by="phuong@x", promoted_employee="E-X1",
             proposed_position="Senior Engineer", effective_date_of_promotion="2026-12-01", full_name="X1",
             department="ECO - EC", current_position="Staff", justification="gioi",
             approval_request="APR-1", salary_pending=1, current_salary=None, proposed_salary=None,
             incentives=None, material_signature="old")
    d.update(kw)
    W.req["P-9"] = d
    W.req["APR-1"] = dict(name="APR-1", approval_status="Pending", current_level=1)
    W.pending[("APR-1", 1)] = {"linh@x"}
    W.biz_exists.add("P-9")
    return d


@pytest.fixture
def env():
    saved = dict(sys.modules)
    yield base.build
    for k in list(sys.modules):
        if k not in saved:
            del sys.modules[k]
    sys.modules.update(saved)


# ------------------------------------------------------------------ 1. pham vi de xuat
def test_lead_thay_cap_duoi_truc_tiep_va_gian_tiep_khong_thay_nguoi_ngoai(env):
    snap, svc, fr = _setup(env)
    rows = snap.candidates()
    names = {r.name for r in rows}
    assert names == {"E-X1", "E-X2", "E-Y", "E-Z"}       # Z: duoi nguoi da nghi van la cap duoi gian tiep
    assert "E-OUT" not in names and "E-PHUONG" not in names and "E-GHOST" not in names
    assert all(r["salary_visible"] == 0 for r in rows)    # Lead khong xem duoc luong ai


def test_truong_phong_thay_ca_nguoi_xem_duoc_luong_co_co(env):
    snap, svc, fr = _setup(env, user="linh@x")
    rows = {r.name: r for r in snap.candidates()}
    assert {"E-PHUONG", "E-X1", "E-Y", "E-OUT"} <= set(rows) and "E-LINH" not in rows
    assert rows["E-OUT"]["salary_visible"] == 1 and rows["E-X1"]["salary_visible"] == 1


def test_reports_to_vong_lap_khong_treo(env):
    snap, svc, fr = _setup(env)
    assert snap.subordinates("E-C1") == {"E-C2"}
    assert snap.subordinates(None) == set()


def test_server_chan_nhan_su_ngoai_pham_vi_khi_chon_luu_gui(env):
    snap, svc, fr = _setup(env)
    with pytest.raises(Perm):
        snap.snapshot("E-OUT")                                  # endpoint chon nhan su
    with pytest.raises(Perm):
        svc.prepare_draft(_draft(promoted_employee="E-OUT"))    # luu nhap (draft_preparer)
    with pytest.raises(Perm):
        svc.prepare_draft(_draft(promoted_employee="E-GHOST"))  # da nghi
    with pytest.raises(Perm):
        svc.prepare_draft(_draft(promoted_employee="E-PHUONG"))  # chinh minh
    W.req["P-9"] = dict(_draft(promoted_employee="E-OUT"))
    with pytest.raises(Perm):
        svc.submit("P-9")                                       # gui
    assert not W.submits


def test_snapshot_cap_duoi_khong_tra_luong_tham_khao(env):
    snap, svc, fr = _setup(env)
    x = snap.snapshot("E-X1")
    assert x["salary_visible"] == 0 and x["base_salary"] is None and x["salary_from"] is None
    fr.session.user = "linh@x"
    assert snap.snapshot("E-X1")["base_salary"] == 10000000


# ------------------------------------------------------------------ 2. gui khong luong
def test_luu_nhap_bo_luong_client_gui(env):
    snap, svc, fr = _setup(env)
    d = _draft(name=None, current_salary=99, proposed_salary=100, incentives="xe")
    svc.prepare_draft(d)
    assert d.current_salary is None and d.proposed_salary is None and d.incentives is None


def test_luu_lai_khi_bi_tra_giu_luong_nguoi_duyet_da_dien(env):
    snap, svc, fr = _setup(env)
    _submitted(current_salary=30000000, proposed_salary=36000000, incentives="thuong", salary_pending=0)
    d = _draft(approval_request="APR-1", current_salary=1, proposed_salary=2, incentives="hack")
    svc.prepare_draft(d)
    assert (d.current_salary, d.proposed_salary, d.incentives) == (30000000, 36000000, "thuong")


def test_lead_gui_duoc_khong_luong_server_xoa_luong_va_dat_co(env):
    snap, svc, fr = _setup(env)
    W.req["P-9"] = dict(_draft(current_salary=50000000, proposed_salary=60000000, incentives="x"))
    assert svc.submit("P-9") == "APR-1"
    saved = [d for dt, d in W.saved if dt == "EC Promotion Request"][-1]
    assert saved["salary_pending"] == 1
    assert saved["current_salary"] is None and saved["proposed_salary"] is None and saved["incentives"] is None
    assert saved["salary_reviewer"] == "linh@x"                     # cap 1 = Linh, KHONG bi bo
    (args, kw), = W.submits
    assert kw["skip_level_nos"] is None


def test_nguoi_xem_duoc_luong_tu_lap_nhu_cu(env):
    snap, svc, fr = _setup(env, user="linh@x")
    W.req["P-9"] = dict(_draft(requested_by="linh@x"))
    with pytest.raises(Throw):
        svc.submit("P-9")                                          # thieu luong -> chan nhu cu
    W.req["P-9"] = dict(_draft(requested_by="linh@x", current_salary=30000000, proposed_salary=36000000))
    svc.submit("P-9")
    saved = [d for dt, d in W.saved if dt == "EC Promotion Request"][-1]
    assert saved["salary_pending"] == 0 and saved["proposed_salary"] == 36000000
    d = _draft(requested_by="linh@x", current_salary=1, proposed_salary=2)
    svc.prepare_draft(d)
    assert d.current_salary == 1                                   # nguoi co quyen: khong bo luong


# ------------------------------------------------------------------ 3. duyet: dien luong
def test_nguoi_duyet_co_quyen_phai_dien_truoc_khi_duyet(env):
    snap, svc, fr = _setup(env)
    biz = _submitted()
    req = Obj(name="APR-1", current_level=1, approval_status="Pending")
    msg = svc.approval_input_message(Obj(biz), req, "linh@x")
    assert msg and "Vui lòng điền" in msg
    assert svc.approval_input_message(Obj(biz, salary_pending=0), req, "linh@x") == ""


def test_nguoi_duyet_khong_quyen_o_cap_trung_gian_duyet_binh_thuong(env):
    snap, svc, fr = _setup(env)
    biz = _submitted()
    W.levels[0]["level_status"] = "Skipped"
    W.levels[1]["level_status"] = "Approved"
    W.levels[2]["level_status"] = "In Progress"
    assert svc.approval_input_message(Obj(biz), Obj(name="APR-1", current_level=3), "mid@x") == ""


def test_cap_cnb_va_cap_cuoi_bat_buoc_co_luong(env):
    snap, svc, fr = _setup(env)
    biz = _submitted()
    W.levels[0]["level_status"] = "Skipped"
    assert "bắt buộc" in svc.approval_input_message(Obj(biz), Obj(name="APR-1", current_level=2), "mid@x")
    assert "Vui lòng điền" in svc.approval_input_message(Obj(biz), Obj(name="APR-1", current_level=2), "cnb@x")
    assert "bắt buộc" in svc.approval_input_message(Obj(biz), Obj(name="APR-1", current_level=4), "mid@x")
    W.levels[3]["level_status"] = "Skipped"                      # CEO bo -> HOF thanh cap cuoi
    assert "bắt buộc" in svc.approval_input_message(Obj(biz), Obj(name="APR-1", current_level=3), "mid@x")


def test_dien_luong_quyen_va_ghi_vet_khong_so_tien(env):
    snap, svc, fr = _setup(env)
    _submitted()
    for who in ("phuong@x", "cnb@x"):                         # Lead / nguoi khong phai approver cap hien tai
        fr.session.user = who
        with pytest.raises(Perm):
            svc.fill_salary("P-9", "30.000.000", "36.000.000")
    W.pending[("APR-1", 1)] = {"linh@x", "mid@x"}
    fr.session.user = "mid@x"                                 # approver nhung khong xem duoc luong
    with pytest.raises(Perm):
        svc.fill_salary("P-9", "30.000.000", "36.000.000")
    fr.session.user = "linh@x"
    with pytest.raises(Throw):
        svc.fill_salary("P-9", "0", "36.000.000")
    with pytest.raises(Throw):
        svc.fill_salary("P-9", "30.000.000", "-1")
    assert svc.fill_salary("P-9", "30.000.000", 36000000, incentives=" thuong Tet ") == {"saved": True}
    row = W.req["P-9"]
    assert row["current_salary"] == 30000000 and row["proposed_salary"] == 36000000
    assert row["salary_pending"] == 0 and row["salary_filled_by"] == "linh@x" and row["incentives"] == "thuong Tet"
    assert row["material_signature"] != "old"
    (args, kw), = W.actions
    assert args[0] == "APR-1" and args[1] == "Commented" and args[2] == "linh@x"
    text = json.dumps([args, kw], ensure_ascii=False)
    assert "30" not in text.replace("APR-1", "") and "36" not in text     # khong ghi so tien vao nhat ky
    assert svc.approval_input_message(Obj(row), Obj(name="APR-1", current_level=1), "linh@x") == ""


def test_dien_luong_khi_phieu_khong_pending_bi_chan(env):
    snap, svc, fr = _setup(env, user="linh@x")
    _submitted()
    W.req["APR-1"]["approval_status"] = "Information Required"
    with pytest.raises(Perm):
        svc.fill_salary("P-9", "30.000.000", "36.000.000")


def test_khoi_chi_tiet_chi_co_co_khong_co_so(env):
    snap, svc, fr = _setup(env, user="linh@x")
    biz = _submitted()
    req = Obj(name="APR-1", approval_status="Pending", current_level=1)
    x = svc.promotion_block(Obj(biz), req)["salary_input"]
    assert x == {"pending": True, "can_fill": True, "required": True}
    fr.session.user = "phuong@x"
    assert svc.promotion_block(Obj(biz), req)["salary_input"] == {"pending": True, "can_fill": False, "required": False}


# ------------------------------------------------------------------ 5. khong lo luong cho Lead
def test_lead_khong_thay_luong_sau_khi_nguoi_duyet_dien(env):
    snap, svc, fr = _setup(env)
    biz = _submitted(current_salary=30000000, proposed_salary=36000000, incentives="t", salary_pending=0)
    b = dict(biz)
    svc.redact_business(b)
    assert b["current_salary"] is None and b["proposed_salary"] is None and b["incentives"] is None
    assert b["salary_hidden"] == 1
    fr.session.user = "linh@x"
    b = dict(biz)
    svc.redact_business(b)
    assert b["proposed_salary"] == 36000000


def test_resubmit_lead_doi_noi_dung_thi_bat_dien_lai(env):
    snap, svc, fr = _setup(env)
    _submitted(current_salary=30000000, proposed_salary=36000000, salary_pending=0, material_signature="old")
    svc.resubmit("P-9", actor="phuong@x")
    assert W.req["P-9"]["salary_pending"] == 1
    assert W.req["P-9"]["current_salary"] == 30000000           # gia tri cu giu de dien san


def test_duyet_thay_bo_qua_dien_luong_thi_bao_cnb(env):
    snap, svc, fr = _setup(env)
    _submitted(salary_pending=1, proposed_position="Staff")
    svc.apply_to_employee("P-9")
    assert "chưa có lương" in W.req["P-9"]["apply_result"]


# ------------------------------------------------------------------ engine + duyet nhanh (boc ham)
def _fn(path, name, glb):
    src = (APP / path).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), glb)
    return glb[name]


def test_engine_approve_chan_bang_cau_cua_module(env, monkeypatch):
    calls = []
    reg = types.ModuleType("reg")
    reg.BUSINESS_DOCTYPE_DEFINITIONS = {
        "EC Promotion Request": Obj(approval_input_check=lambda b, r, a: calls.append(a) or ("Vui lòng điền" if a == "linh@x" else ""))}
    monkeypatch.setitem(sys.modules, "ecentric_workspace.approval_center.shared.registry", reg)
    fr = types.SimpleNamespace(get_doc=lambda dt, n: Obj(name=n), throw=lambda m: (_ for _ in ()).throw(Throw(m)))
    guard = _fn("approval_center/shared/workflow/transitions.py", "_approval_input_guard", {"frappe": fr})
    req = Obj(reference_doctype="EC Promotion Request", reference_name="P-9")
    with pytest.raises(Throw):
        guard(req, "linh@x")
    guard(req, "mid@x")
    guard(Obj(reference_doctype="EC Payment Request", reference_name="X"), "linh@x")   # loai khac: khong anh huong
    assert calls == ["linh@x", "mid@x"]
    src = (APP / "approval_center/shared/workflow/transitions.py").read_text(encoding="utf-8")
    body = src[src.index("def approve(request_name"):src.index("def reject(request_name")]
    assert body.index("_approval_input_guard(req, actor)") < body.index('{"status": "Approved"')


def test_duyet_nhanh_coi_la_needs_input(env):
    fr = types.SimpleNamespace(session=types.SimpleNamespace(user="linh@x"), log_error=lambda *a: None,
                               get_traceback=lambda: "")
    glb = {"frappe": fr, "_": lambda s: s, "_controller": lambda d: None, "inspect": __import__("inspect")}
    needs = _fn("approval_center/shared/requests/quick_approve.py", "_needs_input", glb)
    d = Obj(code="PROMOTION_REQUEST", approval_input_check=lambda b, r, u: "Vui lòng điền" if u == "linh@x" else "")
    assert needs(d, {}, "Direct Manager Review", Obj(), Obj(name="APR-1"), "linh@x") == (True, "Vui lòng điền")
    assert needs(d, {}, "Direct Manager Review", Obj(), Obj(name="APR-1"), "mid@x") == (False, "")
    boom = Obj(code="X", approval_input_check=lambda b, r, u: 1 / 0)
    assert needs(boom, {}, "L", Obj(), Obj(), "a")[0] is True          # loi -> khong cho duyet nhanh
    src = (APP / "approval_center/shared/requests/quick_approve.py").read_text(encoding="utf-8")
    assert src.count("need, why = _needs_input(definition, caps,") == 2 and src.count("req_doc, user)") == 2


# ------------------------------------------------------------------ khai bao + cac duong ra khac
def test_khai_bao_dinh_nghia_va_doctype():
    df = (APP / "approval_center/features/promotion/domain/definition.py").read_text(encoding="utf-8")
    assert 'draft_preparer=ServiceMethod(_BASE, "prepare_draft")' in df
    assert 'approval_input_check=ServiceMethod(_BASE, "approval_input_message")' in df
    tree = ast.parse(df)
    tuples = [ast.literal_eval(n) for n in ast.walk(tree) if isinstance(n, ast.Tuple)
              and all(isinstance(e, ast.Constant) for e in n.elts) and "name" in [e.value for e in n.elts]]
    for t in tuples:                                 # danh sach / tab "Cho toi duyet": khong cot luong
        assert not {"current_salary", "proposed_salary", "incentives"} & set(t)
    assert "salary" not in df[df.index("quick_summary="):df.index("quick_comment_required")]
    js = json.loads((APP / "approval_center/doctype/ec_promotion_request/ec_promotion_request.json").read_text(encoding="utf-8"))
    f = {x["fieldname"]: x for x in js["fields"]}
    for k in ("current_salary", "proposed_salary", "incentives"):
        assert f[k].get("permlevel") == 1, k            # REST /api/resource: nguoi duoc share doc khong doc duoc
    assert f["salary_pending"]["fieldtype"] == "Check" and f["salary_filled_by"]["options"] == "User"
    lvl1 = [p for p in js["permissions"] if p.get("permlevel") == 1]
    assert lvl1 == [{"role": "System Manager", "permlevel": 1, "read": 1, "write": 1}]
    assert set(js["field_order"]) == set(f)


def test_thong_bao_va_xuat_khong_doc_truong_luong():
    tr = (APP / "approval_center/shared/workflow/transitions.py").read_text(encoding="utf-8")
    amt = tr[tr.index("_AMOUNT_FIELDS = ("):tr.index(")", tr.index("_AMOUNT_FIELDS = ("))]
    assert "salary" not in amt and "incentive" not in amt
    pa = (APP / "notification_center/providers/power_automate.py").read_text(encoding="utf-8")
    amt = pa[pa.index("_AMOUNT_FIELDS = ("):pa.index(")", pa.index("_AMOUNT_FIELDS = ("))]
    assert "salary" not in amt
    bs = (APP / "approval_center/reporting/business_summary.py").read_text(encoding="utf-8")
    assert "EC Promotion Request" not in bs[bs.index("AMOUNT_FIELDS = {"):bs.index("}", bs.index("AMOUNT_FIELDS = {"))]


def test_endpoint_dien_luong_post_va_khong_nhan_actor():
    api = (APP / "approval_center/features/promotion/controllers/api.py").read_text(encoding="utf-8")
    i = api.index("def fill_salary(")
    assert '@frappe.whitelist(methods=["POST"])' in api[i - 60:i]
    assert "actor" not in api[i:i + 200] and "user" not in api[i:api.index(":", i)]
