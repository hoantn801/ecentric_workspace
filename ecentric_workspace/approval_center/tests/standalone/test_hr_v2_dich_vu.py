"""HR v2 (23/11/2026) - dich vu Nghi viec / Clearance / Offer / NSP + process V2 tren frappe gia.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hr_v2_dich_vu.py
"""
import datetime as dt
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _hr_v2_fake as F   # noqa: E402
from _hr_v2_fake import W, put, user, Throw, PermErr   # noqa: E402

FEAT = "ecentric_workspace.approval_center.features."


@pytest.fixture(autouse=True)
def _clean():
    saved = dict(sys.modules)
    yield
    for k in list(sys.modules):
        if k not in saved:
            del sys.modules[k]
    sys.modules.update(saved)


def _boot(**k):
    fr = F.boot(**k)
    user("Administrator", ["System Manager"])
    return fr


# =============================================================== Nghi viec
def _emp(name, mail, reports_to=None, contracts=()):
    put("Employee", name, user_id=mail, employee_name=name, reports_to=reports_to, status="Active",
        company="EC", department="Ops")
    for i, cr in enumerate(contracts):
        put("EC Employee Contract", "%s-c%d" % (name, i), parent=name, parenttype="Employee",
            parentfield="ec_contracts", **cr)


def _resn(name="RESN-1", email="a@ec.vn", last="2026-12-31", status=None, req_by="a@ec.vn", **kw):
    d = put("EC Resignation Request", name, employee_email=email, personal_email="a@gmail.com",
            last_working_day=last, resignation_for="Myself", resignation_reason="Personal",
            request_title="t", requested_by=req_by, approval_request=None, **kw)
    if status:
        put("EC Approval Request", "AR-" + name, approval_status=status, requested_by=req_by)
        d.approval_request = "AR-" + name
    return d


def test_gui_don_tinh_ngay_som_nhat_va_danh_dau_xin_som():
    _boot(user="a@ec.vn")
    user("a@ec.vn")
    _emp("E1", "a@ec.vn", contracts=[{"loai_hop_dong": "HĐLĐ lần 1", "tu_ngay": "2026-01-01",
                                  "den_ngay": "2026-12-31", "khong_thoi_han": 0}])
    _resn(last="2026-12-01")
    svc = F.load(FEAT + "resignation.application.service")
    req = svc.submit("RESN-1")
    d = W.tables["EC Resignation Request"]["RESN-1"]
    assert str(d.earliest_valid_last_day) == "2026-12-23" and d.early_leave_requested == 1
    assert d.approval_request == req and W.submitted[0].atype == "RESIGNATION"
    assert any("sớm hơn hạn báo trước" in (a.comment or "") for a in W.actions)


def test_gui_don_khong_can_danh_gia_va_khong_xin_som():
    _boot(user="a@ec.vn")
    user("a@ec.vn")
    _emp("E1", "a@ec.vn", contracts=[{"loai_hop_dong": "Thử việc", "tu_ngay": "2026-11-01",
                                  "den_ngay": "2026-12-31"}])
    _resn(last="2026-11-25")
    svc = F.load(FEAT + "resignation.application.service")
    svc.submit("RESN-1")
    assert W.tables["EC Resignation Request"]["RESN-1"].early_leave_requested == 0


def test_chan_trung_don_dang_mo_va_don_da_duyet_chua_qua_ngay_cuoi():
    _boot(user="a@ec.vn")
    user("a@ec.vn")
    _emp("E1", "a@ec.vn")
    _resn("RESN-0", status="Pending")
    _resn("RESN-1")
    svc = F.load(FEAT + "resignation.application.service")
    with pytest.raises(Throw, match="RESN-0"):
        svc.submit("RESN-1")
    W.tables["EC Approval Request"]["AR-RESN-0"].approval_status = "Approved"
    with pytest.raises(Throw):
        svc.submit("RESN-1")
    W.tables["EC Resignation Request"]["RESN-0"].withdrawn_at = "2026-11-20"   # da rut -> duoc gui
    svc.submit("RESN-1")


def test_ngay_cuoi_qua_khu_bi_chan():
    _boot(user="a@ec.vn")
    user("a@ec.vn")
    _resn(last="2026-11-01")
    svc = F.load(FEAT + "resignation.application.service")
    with pytest.raises(Throw, match="quá khứ"):
        svc.submit("RESN-1")


def test_rut_don_dang_duyet_huy_phieu_duyet():
    _boot(user="a@ec.vn")
    user("a@ec.vn")
    user("lm@x")
    _resn(status="Pending")
    put("EC Approval Request Approver", "x1", approval_request="AR-RESN-1", approver="lm@x")
    svc = F.load(FEAT + "resignation.application.service")
    out = svc.withdraw("RESN-1", "đổi ý", actor="a@ec.vn")
    assert out["withdrawn"] and W.cancelled[0][0] == "AR-RESN-1"
    d = W.tables["EC Resignation Request"]["RESN-1"]
    assert d.withdrawn_by == "a@ec.vn" and d.withdrawal_reason == "đổi ý"
    assert any(n[0] == "notify" and "lm@x" in n[1] for n in W.notes if isinstance(n, tuple))
    with pytest.raises(PermErr):                                  # rut lan 2
        svc.withdraw("RESN-1", "x", actor="a@ec.vn")


def test_rut_don_sau_khi_duyet_xoa_ngay_nghi_va_huy_clearance():
    _boot(user="a@ec.vn")
    user("a@ec.vn")
    _emp("E1", "a@ec.vn")
    W.tables["Employee"]["E1"].update(relieving_date="2026-12-31", resignation_letter_date="2026-11-20")
    _resn(status="Approved")
    put("EC Clearance Request", "CLR-1", resignation_request="RESN-1", approval_request="AR-C")
    put("EC Approval Request", "AR-C", approval_status="Pending")
    svc = F.load(FEAT + "resignation.application.service")
    out = svc.withdraw("RESN-1", "ở lại", actor="a@ec.vn")
    assert W.tables["Employee"]["E1"].relieving_date is None
    assert ("AR-C", "a@ec.vn") == W.cancelled[0][:2]
    assert W.tables["EC Approval Request"]["AR-RESN-1"].approval_status == "Approved"   # khong doi
    assert any("da huy clearance" in s for s in out["steps"])


def test_rut_don_bi_chan_khi_toi_ngay_cuoi_hoac_nguoi_khac():
    _boot(user="a@ec.vn")
    user("a@ec.vn")
    user("other@x")
    _resn(status="Pending", last="2026-11-23")
    svc = F.load(FEAT + "resignation.application.service")
    with pytest.raises(PermErr, match="ngày làm việc cuối"):
        svc.withdraw("RESN-1", "x", actor="a@ec.vn")
    W.tables["EC Resignation Request"]["RESN-1"].last_working_day = "2026-12-31"
    with pytest.raises(PermErr):
        svc.withdraw("RESN-1", "x", actor="other@x")
    with pytest.raises(Throw):
        svc.withdraw("RESN-1", "  ", actor="a@ec.vn")


def test_khao_sat_nghi_viec_goi_ham_module_khao_sat_neu_co():
    _boot(user="a@ec.vn")
    user("a@ec.vn")
    _resn(status="Approved", last="2026-11-27")
    svc = F.load(FEAT + "resignation.application.service")
    doc = W.tables["EC Resignation Request"]["RESN-1"]
    assert svc.giao_khao_sat_nghi_viec(doc) == "chua co module"        # chua co -> bo qua, khong nem
    calls = []
    W.attrs[svc.SURVEY_FN] = lambda *a: calls.append(a) or {"ok": True, "assignment": "S-1"}
    assert svc.giao_khao_sat_nghi_viec(doc) == "da giao"
    u, ma, han, ctx, roles = calls[0]
    assert u == "a@ec.vn" and ma == "NGHI_VIEC" and han == 4 and ctx["khoa"] == "RESN-1"
    W.attrs[svc.SURVEY_FN] = lambda *a: {"ok": False, "ly_do": "chua_co_mau"}
    assert svc.giao_khao_sat_nghi_viec(doc) == "khong giao (chua_co_mau)"
    assert "HR" in roles and "EC CnB" in roles


def test_an_danh_gia_khao_sat_voi_lm_ca_don_cu():
    _boot(user="lm@x")
    user("lm@x")
    user("cnb@x", ["EC CnB"])
    red = F.load(FEAT + "resignation.application.redact")
    biz = {"requested_by": "a@ec.vn", "employee_email": "a@ec.vn", "workplace_environment_rating": "1",
           "final_message": "secret", "benefit_policy_rating": "2"}
    out = red.redact(dict(biz))
    assert out["final_message"] is None and out["workplace_environment_rating"] is None and out["survey_hidden"]
    sys.modules["frappe"].session.user = "cnb@x"
    assert red.redact(dict(biz))["final_message"] == "secret"
    sys.modules["frappe"].session.user = "a@ec.vn"
    assert red.redact(dict(biz))["final_message"] == "secret"


def test_thong_tin_hop_dong_chi_cho_nguoi_duoc_phep():
    _boot(user="x@x")
    user("x@x")
    _emp("E1", "a@ec.vn", contracts=[{"loai_hop_dong": "HĐLĐ lần 1", "tu_ngay": "2026-01-01",
                                  "den_ngay": "2026-12-31"}])
    svc = F.load(FEAT + "resignation.application.service")
    assert svc.notice_info("a@ec.vn")["known"] is False and svc.notice_info("a@ec.vn").get("hidden")
    sys.modules["frappe"].session.user = "a@ec.vn"
    assert svc.notice_info("a@ec.vn")["earliest"] == "2026-12-23"


# =============================================================== khong co Tu choi
def test_khong_co_tu_choi_o_may_chu_va_capabilities():
    _boot()
    for m in ("query_service",):
        sys.modules["ecentric_workspace.approval_center.shared.requests." + m] = type(sys)("q")
    sys.modules["ecentric_workspace.approval_center.shared.requests.query_service"].detail = lambda *a: {}
    perms = type(sys)("perms")
    perms.can_view_request = lambda *a, **k: True
    sys.modules["ecentric_workspace.approval_center.shared.workflow.permissions"] = perms
    cs = F.load("ecentric_workspace.approval_center.shared.requests.command_service")

    class D:
        allow_reject = False
        business_doctype = "EC Resignation Request"
    with pytest.raises(PermErr, match="Từ chối"):
        cs.reject(D(), "RESN-1", "x")
    caps = F.load("ecentric_workspace.approval_center.shared.requests.capabilities")
    reg = type(sys)("reg")
    reg.get_definition = lambda code: D() if code == "RESIGNATION" else type("O", (), {"allow_reject": True})()
    sys.modules["ecentric_workspace.approval_center.shared.registry"] = reg
    assert caps._type_allows_reject({"approval_type": "RESIGNATION"}) is False
    assert caps._type_allows_reject({"approval_type": "OFFER_REQUEST"}) is True
    assert caps._type_allows_reject(None) is True


def test_dinh_nghia_nghi_viec_tat_tu_choi():
    import ast
    src = (F.ROOT / "ecentric_workspace/approval_center/features/resignation/domain/definition.py").read_text()
    assert "allow_reject=False" in src and "business_redactor" in src and "resignation_block" in src
    ast.parse(src)


# =============================================================== Clearance
def test_nguoi_gui_clearance_khong_bao_gio_la_nguoi_nghi():
    _boot()
    user("a@ec.vn", ["EC CnB"])            # nguoi nghi lai thuoc CnB
    user("cnb2@x", ["EC CnB"])
    svc = F.load(FEAT + "clearance_request.application.service")
    assert svc.nguoi_gui_clearance("a@ec.vn") == "cnb2@x"
    res = F.Doc(approval_request="AR-R", requested_by="a@ec.vn")
    put("EC Approval Request Approver", "r1", approval_request="AR-R", status="Approved",
        approver="hr@x", source="Role: HR", level_no=2)
    user("hr@x", ["HR"])
    assert svc.nguoi_gui_clearance("a@ec.vn", res) == "hr@x"           # nguoi duyet cap CnB/HR uu tien
    W.role_users = {}
    assert svc.nguoi_gui_clearance("a@ec.vn", F.Doc(requested_by="a@ec.vn")) == "Administrator"


def _clr_world():
    user("a@ec.vn")
    user("lm@x")
    user("cnb@x", ["EC CnB"])
    _emp("E1", "a@ec.vn", reports_to="EM")
    _emp("EM", "lm@x")
    put("EC Approval Process", "CLEARANCE_REQUEST-V2", approval_type="CLEARANCE_REQUEST", status="Active")


def test_tao_clearance_tu_don_da_duyet_dat_han_ngay_cuoi():
    _boot()
    _clr_world()
    _resn(status="Approved", last="2026-12-31")
    sla = type(sys)("sla")
    hans = []
    sla.dat_han_cap = lambda req, lvl, han: hans.append((req, lvl, str(han)))
    sys.modules["ecentric_workspace.approval_center.shared.sla_ngay_lam_viec"] = sla
    svc = F.load(FEAT + "clearance_request.application.service")
    name = svc.create_from_resignation("RESN-1")
    c = W.tables["EC Clearance Request"][name]
    assert c.requested_by == "cnb@x" and c.employee_email == "a@ec.vn" and c.line_manager == "lm@x"
    assert c.clearance_source == "Resignation" and c.opened_early == 0
    assert hans and hans[0][1:] == (1, "2026-12-31")
    assert svc.create_from_resignation("RESN-1") == name and len(W.submitted) == 1   # idempotent


def test_loi_tao_clearance_ghi_len_don():
    _boot()
    _clr_world()
    _resn(status="Pending")
    svc = F.load(FEAT + "clearance_request.application.service")
    assert svc.create_from_resignation("RESN-1") is None
    assert "chưa được duyệt xong" in W.tables["EC Resignation Request"]["RESN-1"].clearance_error


def test_mo_som_khi_lm_da_duyet_va_con_5_ngay_lam_viec():
    _boot(today="2026-11-23")
    _clr_world()
    _resn(status="Pending", last="2026-11-30")          # T2 23 -> T2 30: 5 ngay LV
    put("EC Approval Request Level", "L1", approval_request="AR-RESN-1", level_no=1, level_status="Approved")
    _resn("RESN-2", email="b@ec.vn", status="Pending", last="2026-12-31")   # con xa -> khong mo
    put("EC Approval Request Level", "L2", approval_request="AR-RESN-2", level_no=1, level_status="Approved")
    sla = type(sys)("sla")
    sla.dat_han_cap = lambda *a: None
    sla.ngay_le = lambda: set()
    from ecentric_workspace.approval_center.shared import sla_ngay_lam_viec as real
    sla.dem_ngay_lam_viec = real.dem_ngay_lam_viec
    sys.modules["ecentric_workspace.approval_center.shared.sla_ngay_lam_viec"] = sla
    svc = F.load(FEAT + "clearance_request.application.service")
    ket = svc.quet_hang_ngay()
    assert len(ket["mo_som"]) == 1 and not ket["tao_bu"]
    (c,) = W.tables["EC Clearance Request"].values()
    assert c.resignation_request == "RESN-1" and c.opened_early == 1


def test_quet_khong_lam_gi_khi_chua_co_process_active():
    _boot()
    svc = F.load(FEAT + "clearance_request.application.service")
    assert "skipped" in svc.quet_hang_ngay()


def test_tao_bu_dry_run_khong_ghi_va_chan_doan():
    _boot()
    _clr_world()
    _resn(status="Approved", last="2026-10-01")          # da qua ngay cuoi
    put("EC Approval Action", "x", approval_request="AR-RESN-1", action="Commented", actor="Administrator",
        comment="ho so ...", seq=1)
    svc = F.load(FEAT + "clearance_request.application.service")
    rep = svc.tao_bu(dry_run=1)
    (it,) = rep["items"]
    assert it["name"] == "RESN-1" and it["da_qua_ngay_cuoi"] and "handler sau duyet chua tung chay" in it["ly_do"][0]
    assert not W.tables.get("EC Clearance Request")
    rep = svc.tao_bu(dry_run=0)                          # khong include_past -> van bo qua
    assert "bo qua" in rep["items"][0]["hanh_dong"] and not W.tables.get("EC Clearance Request")
    sla = type(sys)("sla")
    sla.dat_han_cap = lambda *a: None
    sys.modules["ecentric_workspace.approval_center.shared.sla_ngay_lam_viec"] = sla
    rep = svc.tao_bu(dry_run=0, include_past=1)
    assert "da tao" in rep["items"][0]["hanh_dong"]


def test_tao_clearance_cho_module_khac_idempotent():
    _boot(user="hr@x")
    user("hr@x", ["EC CnB"])
    _clr_world()
    sla = type(sys)("sla")
    sla.dat_han_cap = lambda *a: None
    sys.modules["ecentric_workspace.approval_center.shared.sla_ngay_lam_viec"] = sla
    svc = F.load(FEAT + "clearance_request.application.service")
    n1 = svc.tao_clearance("E1", "Sa thải - quyết định KL-1", "2026-12-15", tham_chieu="KL-1")
    c = W.tables["EC Clearance Request"][n1]
    assert c.clearance_source == "Discipline" and c.requested_by == "hr@x" and c.employee_email == "a@ec.vn"
    assert svc.tao_clearance("E1", "x", "2026-12-15") == n1
    with pytest.raises(Throw):
        svc.tao_clearance("NOPE", "x", "2026-12-15")


# =============================================================== Offer / NSP
def _offer_world(salary=15000000, suggested=20000000, hof_mandatory=0):
    put("EC Hiring Request", "HR-1", suggested_salary=suggested, employment_type="Full-time")
    put("EC Approval Process", "OFFER_REQUEST-V2", approval_type="OFFER_REQUEST", status="Active")
    from ecentric_workspace.approval_center.features.offer_request.infrastructure.setup_v2 import HOF_LEVEL_NAME
    put("EC Approval Level", "LV3", approval_process="OFFER_REQUEST-V2", level_name=HOF_LEVEL_NAME,
        level_no=3, mandatory=hof_mandatory)
    return F.Doc(hiring_request="HR-1", offered_salary=salary)


def test_hof_bo_cap_qua_skip_level_nos():
    _boot()
    svc = F.load(FEAT + "offer_request.application.service")
    doc = _offer_world()
    assert svc.hof_decision(doc)[0] == 3
    doc.offered_salary = 25000000
    assert svc.hof_decision(doc)[0] is None


def test_hof_khong_bo_khi_process_v1_bat_buoc():
    _boot()
    svc = F.load(FEAT + "offer_request.application.service")
    doc = _offer_world(hof_mandatory=1)
    lvl, note = svc.hof_decision(doc)
    assert lvl is None and "giữ nguyên" in note


def test_ung_vien_tu_choi_huy_nsp_dang_mo():
    _boot(user="ta@x")
    user("ta@x")
    user("p1@x")
    put("EC Offer Request", "OF-1", requested_by="ta@x", approval_request="AR-O", line_manager="lm@x",
        new_staff_preparation="NSP-1")
    put("EC Approval Request", "AR-O", approval_status="Approved")
    put("EC New Staff Preparation", "NSP-1", approval_request="AR-N", offer_request="OF-1")
    put("EC Approval Request", "AR-N", approval_status="Pending")
    put("EC Approval Request Approver", "a1", approval_request="AR-N", approver="p1@x")
    svc = F.load(FEAT + "offer_request.application.service")
    out = svc.mark_candidate_status("OF-1", "Declined", "nhận nơi khác", actor="ta@x")
    assert W.cancelled == [("AR-N", "ta@x", "Ứng viên từ chối offer: nhận nơi khác")]
    assert W.tables["EC Offer Request"]["OF-1"].candidate_status == "Declined"
    assert W.tables["EC Approval Request"]["AR-O"].approval_status == "Approved"
    assert "da huy NSP" in out["new_staff_preparation"]
    with pytest.raises(Throw):
        svc.mark_candidate_status("OF-1", "Declined", "x", actor="ta@x")


def test_nguoi_ngoai_khong_ghi_nhan_tu_choi():
    _boot(user="x@x")
    user("x@x")
    put("EC Offer Request", "OF-1", requested_by="ta@x", approval_request="AR-O")
    put("EC Approval Request", "AR-O", approval_status="Approved")
    svc = F.load(FEAT + "offer_request.application.service")
    with pytest.raises(PermErr):
        svc.mark_candidate_status("OF-1", "Declined", "x", actor="x@x")


def test_nsp_khong_tao_khi_ung_vien_da_tu_choi():
    _boot()
    put("EC Offer Request", "OF-1", requested_by="ta@x", approval_request="AR-O", candidate_status="Declined")
    put("EC Approval Request", "AR-O", approval_status="Approved")
    svc = F.load(FEAT + "new_staff_preparation.application.service")
    with pytest.raises(Throw, match="Declined"):
        svc._create_and_submit("OF-1")


def test_han_nsp_truoc_onboard_1_ngay_lv_toi_thieu_2():
    _boot()
    svc = F.load(FEAT + "new_staff_preparation.application.service")
    D = dt.date
    assert svc.han_chuan_bi(D(2026, 12, 7), D(2026, 11, 23)) == D(2026, 12, 4)    # T2 -> T6 truoc
    assert svc.han_chuan_bi(D(2026, 11, 24), D(2026, 11, 23)) == D(2026, 11, 25)  # toi thieu 2 ngay LV
    assert svc.han_chuan_bi(None, D(2026, 11, 27)) == D(2026, 12, 1)


def test_chon_ho_so_ghi_dong_thu_viec_mot_lan():
    _boot(user="cnb@x")
    user("cnb@x", ["EC CnB"])
    put("EC Hiring Request", "HR-1", employment_type="Full-time")
    put("EC New Staff Preparation", "NSP-1", approval_request="AR-N", hiring_request="HR-1",
        onboard_date="2026-12-01", probation_end_date="2027-01-31", offer_request="OF-1")
    put("EC Approval Request", "AR-N", approval_status="Pending")
    emp = put("Employee", "HR-EMP-9", employee_name="New", status="Active", ec_contracts=[])
    svc = F.load(FEAT + "new_staff_preparation.application.service")
    out = svc.pick_employee("NSP-1", "HR-EMP-9", actor="cnb@x")
    rows = emp["ec_contracts"]
    assert len(rows) == 1 and rows[0]["loai_hop_dong"] == "Thử việc"
    assert str(rows[0]["tu_ngay"]) == "2026-12-01" and str(rows[0]["den_ngay"]) == "2027-01-31"
    assert W.tables["EC New Staff Preparation"]["NSP-1"].new_employee == "HR-EMP-9"
    svc.pick_employee("NSP-1", "HR-EMP-9", actor="cnb@x")
    assert len(emp["ec_contracts"]) == 1 and "da co dong" in W.tables["EC New Staff Preparation"]["NSP-1"].contract_row_note


def test_chon_ho_so_chi_nhom_hr():
    _boot(user="op@x")
    user("op@x", ["EC Ops System"])
    put("EC New Staff Preparation", "NSP-1", approval_request="AR-N")
    put("EC Approval Request", "AR-N", approval_status="Pending")
    put("Employee", "E9", employee_name="x", status="Active")
    svc = F.load(FEAT + "new_staff_preparation.application.service")
    with pytest.raises(PermErr):
        svc.pick_employee("NSP-1", "E9", actor="op@x")
    put("EC Approval Request Approver", "g", approval_request="AR-N", approver="op@x", participant_group="HR")
    assert svc.may_pick_employee(W.tables["EC New Staff Preparation"]["NSP-1"], "op@x")


# =============================================================== process V2
def test_upsert_khong_ghi_de_active_va_swap_mot_giao_dich():
    _boot(user="Administrator")
    ps = F.load("ecentric_workspace.approval_center.shared.process_seed")
    put("EC Approval Process", "X-V1", approval_type="X", status="Active")
    put("EC Approval Process", "X-V2", approval_type="X", status="Active")
    assert ps.upsert_process({"code": "X-V2", "title": "t", "approval_type": "X", "levels": []}) == "SKIP_ACTIVE"
    W.tables["EC Approval Process"]["X-V2"].status = "Draft"
    put("EC Approval Level", "LV", approval_process="X-V2", level_no=1, level_name="a",
        approval_mode="Any One")
    put("EC Approval Participant", "P", parent="LV", parenttype="EC Approval Level",
        participant_purpose="Approver", source_type="Role", role="EC CEO")
    rep = ps.swap_active("X", "X-V2", dry_run=True, expect_levels=1)
    assert rep["result"] == "BLOCKED" and W.tables["EC Approval Process"]["X-V1"].status == "Active"
    user("ceo@x", ["EC CEO"])
    rep = ps.swap_active("X", "X-V2", dry_run=True, expect_levels=1)
    assert rep["result"] == "DRY_RUN_OK" and W.tables["EC Approval Process"]["X-V2"].status == "Draft"
    rep = ps.swap_active("X", "X-V2", dry_run=False, expect_levels=1)
    assert rep["result"] == "SWAPPED"
    assert W.tables["EC Approval Process"]["X-V1"].status == "Retired"
    assert W.tables["EC Approval Process"]["X-V2"].status == "Active"
    assert ps.swap_active("X", "X-V2", dry_run=False)["result"] == "ALREADY_ACTIVE"


def test_swap_bi_chan_boi_dieu_kien_them():
    _boot(user="Administrator")
    ps = F.load("ecentric_workspace.approval_center.shared.process_seed")
    put("EC Approval Process", "X-V2", approval_type="X", status="Draft")
    put("EC Approval Level", "LV", approval_process="X-V2", level_no=1, level_name="a", approval_mode="Any One")
    put("EC Approval Participant", "P", parent="LV", parenttype="EC Approval Level",
        participant_purpose="Approver", source_type="User", user="Administrator")
    rep = ps.swap_active("X", "X-V2", dry_run=False, extra_blockers=["Hàng đợi còn 2 đơn"])
    assert rep["result"] == "BLOCKED" and W.tables["EC Approval Process"]["X-V2"].status == "Draft"


def test_kich_hoat_nghi_viec_v2_chan_khi_hang_doi_cu_con_viec():
    _boot(user="Administrator")
    put("EC Resignation Request", "OLD", fulfillment_status="In Progress")
    st = F.load(FEAT + "resignation.infrastructure.setup_v2")
    rep = st.activate_resignation_v2(dry_run=0, apply=1)
    assert rep["old_queue_open"] == 1 and rep["result"] == "BLOCKED"
    assert any("Hàng đợi" in b for b in rep["blockers"])


def test_seed_role_tuy_chon_bo_khi_khong_co_nguoi():
    _boot(user="Administrator")
    ps = F.load("ecentric_workspace.approval_center.shared.process_seed")
    user("c@x", ["EC CnB"])
    rep = ps.new_report(True)
    keep = ps.check_entries("CnB/HR", ["role:EC CnB", "role:HR"], rep, optional=("role:HR",))
    assert keep == ["role:EC CnB"] and rep["warnings"] and not rep["errors"]
    keep = ps.check_entries("CEO", ["role:EC CEO"], rep)
    assert keep == [] and rep["errors"]


def _seed_roles():
    for r, u in (("EC CnB", "cnb@x"), ("EC HOF", "hof@x"), ("EC Ops System", "ops@x"), ("EC CEO", "ceo@x"),
                 ("EC CnB Payroll", "pay@x")):
        user(u, [r])
    user("tuan.ly@ecentric.vn")


def test_setup_clearance_v2_tao_draft_co_ceo_theo_doi_va_khong_ghi_de_active():
    _boot(user="Administrator")
    _seed_roles()
    put("EC Approval Type", "CLEARANCE_REQUEST")
    st = F.load(FEAT + "clearance_request.infrastructure.setup_v2")
    rep = st.setup_clearance_request_v2(dry_run=1)
    assert rep["result"].startswith("DRY_RUN_OK") and "CLEARANCE_REQUEST-V2" not in W.tables.get("EC Approval Process", {})
    rep = st.setup_clearance_request_v2(apply=1)
    p = W.tables["EC Approval Process"]["CLEARANCE_REQUEST-V2"]
    assert p.status == "Draft" and rep["result"].startswith("APPLIED")
    assert [r["participant_purpose"] for r in p.participants] == ["Notify"] and p.participants[0]["role"] == "EC CEO"
    (lvl,) = [l for l in W.tables["EC Approval Level"].values() if l.approval_process == "CLEARANCE_REQUEST-V2"]
    labels = [r["group_label"] for r in lvl.participants]
    assert lvl.approval_mode == "Each Group" and labels == ["Line Manager", "HR", "HOF", "Operation"]
    assert lvl.participants[0]["source_type"] == "Reference Employee Manager"
    p.status = "Active"
    assert st.setup_clearance_request_v2(apply=1)["result"].startswith("ALREADY_ACTIVE")


def test_setup_offer_v2_cap_hof_khong_bat_buoc_va_sla():
    _boot(user="Administrator")
    _seed_roles()
    put("EC Approval Type", "OFFER_REQUEST")
    sla = F.load("ecentric_workspace.approval_center.shared.sla_ngay_lam_viec")
    sla.ensure_policy = lambda days, rep=None: "HR_%d_NGAY_LV" % days
    st = F.load(FEAT + "offer_request.infrastructure.setup_v2")
    rep = st.setup_offer_request_v2(apply=1)
    assert any("HR" in w for w in rep["warnings"])                 # role HR chua co nguoi -> bo, canh bao
    lv = sorted([l for l in W.tables["EC Approval Level"].values() if l.approval_process == "OFFER_REQUEST-V2"],
                key=lambda l: l.level_no)
    assert [l.level_no for l in lv] == [1, 2, 3, 4] and [l.mandatory for l in lv] == [1, 1, 0, 1]
    assert lv[2].level_name == st.HOF_LEVEL_NAME and all(l.sla_policy == "HR_1_NGAY_LV" for l in lv)
    assert [r["role"] for r in lv[1].participants] == ["EC CnB"]


def test_setup_nghi_viec_v2_ba_cap_sla_2_ngay():
    _boot(user="Administrator")
    _seed_roles()
    user("hrr@x", ["HR"])
    put("EC Approval Type", "RESIGNATION")
    sla = F.load("ecentric_workspace.approval_center.shared.sla_ngay_lam_viec")
    sla.ensure_policy = lambda days, rep=None: "HR_%d_NGAY_LV" % days
    st = F.load(FEAT + "resignation.infrastructure.setup_v2")
    st.setup_resignation_v2(apply=1)
    lv = sorted([l for l in W.tables["EC Approval Level"].values() if l.approval_process == "RESIGNATION-V2"],
                key=lambda l: l.level_no)
    assert [l.level_name for l in lv] == list(st.LEVEL_NAMES)
    assert {r["role"] for r in lv[1].participants} == {"EC CnB", "HR"} and lv[2].participants[0]["role"] == "EC CEO"
    assert all(l.sla_policy == "HR_2_NGAY_LV" for l in lv)
    assert not [r for r in W.tables["EC Approval Process"]["RESIGNATION-V2"].participants
                if r["participant_purpose"] == "Fulfiller"]


# =============================================================== 24/11: NSP -> ho so nhan vien
def test_chon_ho_so_offer_thieu_ngay_thu_viec_dung_mac_dinh_d25_va_dien_ho_so():
    _boot(user="cnb@x")
    user("cnb@x", ["EC CnB"])
    put("EC Hiring Request", "HR-1", employment_type="Full-time")
    put("EC New Staff Preparation", "NSP-1", approval_request="AR-N", hiring_request="HR-1",
        onboard_date="2026-12-01", probation_end_date=None, offer_request="OF-1")
    put("EC Approval Request", "AR-N", approval_status="Pending")
    emp = put("Employee", "HR-EMP-9", employee_name="New", status="Active", ec_contracts=[],
              date_of_joining=None, final_confirmation_date=None)
    svc = F.load(FEAT + "new_staff_preparation.application.service")
    svc.pick_employee("NSP-1", "HR-EMP-9", actor="cnb@x")
    rows = emp["ec_contracts"]
    assert len(rows) == 1 and str(rows[0]["den_ngay"]) == "2027-01-29"          # 60 ngay ke ca ngay dau
    assert "Đ25" in (rows[0]["ghi_chu"] or "")
    e = W.tables["Employee"]["HR-EMP-9"]
    assert str(e.date_of_joining) == "2026-12-01" and str(e.final_confirmation_date) == "2027-01-29"


def test_dien_ho_so_khong_ghi_de_ngay_da_co():
    _boot(user="cnb@x")
    user("cnb@x", ["EC CnB"])
    put("EC Hiring Request", "HR-1", employment_type="Full-time")
    put("EC New Staff Preparation", "NSP-1", approval_request="AR-N", hiring_request="HR-1",
        onboard_date="2026-12-01", probation_end_date="2027-01-31", offer_request="OF-1")
    put("EC Approval Request", "AR-N", approval_status="Pending")
    put("Employee", "HR-EMP-9", employee_name="New", status="Active", ec_contracts=[],
        date_of_joining="2026-11-30", final_confirmation_date="2027-02-15")
    svc = F.load(FEAT + "new_staff_preparation.application.service")
    out = svc.pick_employee("NSP-1", "HR-EMP-9", actor="cnb@x")
    e = W.tables["Employee"]["HR-EMP-9"]
    assert str(e.date_of_joining) == "2026-11-30" and str(e.final_confirmation_date) == "2027-02-15"
    assert "giu nguyen" in out["contract"]


def test_thuc_tap_khong_tu_dat_ngay_khi_offer_thieu():
    _boot(user="cnb@x")
    user("cnb@x", ["EC CnB"])
    put("EC Hiring Request", "HR-1", employment_type="Intern")
    put("EC New Staff Preparation", "NSP-1", approval_request="AR-N", hiring_request="HR-1",
        onboard_date="2026-12-01", probation_end_date=None, offer_request="OF-1")
    put("EC Approval Request", "AR-N", approval_status="Pending")
    emp = put("Employee", "HR-EMP-9", employee_name="New", status="Active", ec_contracts=[],
              date_of_joining=None, final_confirmation_date=None)
    svc = F.load(FEAT + "new_staff_preparation.application.service")
    svc.pick_employee("NSP-1", "HR-EMP-9", actor="cnb@x")
    assert emp["ec_contracts"] == []
    assert W.tables["Employee"]["HR-EMP-9"].final_confirmation_date is None


def test_nsp_duyet_xong_dam_bao_ho_so_da_gan():
    _boot()
    put("EC Hiring Request", "HR-1", employment_type="Full-time")
    put("EC New Staff Preparation", "NSP-1", approval_request="AR-N", hiring_request="HR-1",
        onboard_date="2026-12-01", probation_end_date="2027-01-31", offer_request="OF-1",
        new_employee="HR-EMP-9", line_manager=None, requested_by="ta@x")
    put("EC Approval Request", "AR-N", approval_status="Approved")
    emp = put("Employee", "HR-EMP-9", employee_name="New", status="Active", ec_contracts=[],
              date_of_joining=None, final_confirmation_date=None)
    svc = F.load(FEAT + "new_staff_preparation.application.service")
    svc.on_final_approval("NSP-1")
    svc.on_final_approval("NSP-1")
    assert len(emp["ec_contracts"]) == 1
    assert str(W.tables["Employee"]["HR-EMP-9"].final_confirmation_date) == "2027-01-31"
