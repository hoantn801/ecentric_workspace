# Copyright (c) 2026, eCentric and contributors
"""Nut "Them tep" o buoc duyet (16/10/2026, Hoan): nguoi DANG giu phieu them tep, chi them khong
xoa, ghi lich su "Attachment Added"; Contract Review day RIENG tep moi len SharePoint.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_them_tep_buoc_duyet.py
"""
import importlib.util
import json
import pathlib
import sys
import types

import pytest

APP = pathlib.Path(__file__).resolve().parents[2].parent
CTR = "EC Contract Review Request"


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return self.get(k)


class Throw(Exception):
    pass


class W:
    pass


def _match(row, filters):
    for k, v in (filters or {}).items():
        if isinstance(v, list) and v and v[0] == "in":
            if row.get(k) not in v[1]:
                return False
        elif row.get(k) != v:
            return False
    return True


def _pkg(name):
    if name not in sys.modules or not isinstance(sys.modules[name], types.ModuleType):
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


def build(status="Pending", level=2, doctype="EC Leave", user="fin1@x", approvers=None,
          fulfillment=None, owner=None, roles=("Employee",), files=None):
    W.logged, W.locked, W.enqueued, W.set = [], [], [], []
    W.req = Obj(name="APR-1", approval_status=status, current_level=level)
    W.doc = Obj(doctype=doctype, name="DOC-1", approval_request="APR-1", requested_by="req@x",
                fulfillment_status=fulfillment, fulfillment_owner=owner)
    # (level_no, approver, status, source)
    W.approvers = list(approvers if approvers is not None else [
        (1, "lead@x", "Approved", "User"), (2, "fin1@x", "Pending", "User"),
        (2, "fin2@x", "Pending", "Role: EC Finance"), (3, "ceo@x", "Pending", "User")])
    W.roles = {"fin2@x": ["EC Finance"]}
    W.roles.setdefault(user, list(roles))
    W.files = [Obj(r) for r in (files if files is not None else [
        dict(name="F-OLD", file_url="/private/files/HopDong.docx", file_name="HopDong.docx",
             owner="req@x", is_private=1, is_folder=0, attached_to_doctype=doctype,
             attached_to_name="DOC-1"),
        dict(name="F-NEW", file_url="/private/files/Plan_Vinasoy.xlsx", file_name="Plan_Vinasoy.xlsx",
             owner="fin1@x", is_private=1, is_folder=0, attached_to_doctype=None, attached_to_name=None),
        dict(name="F-ALIEN", file_url="/private/files/Luong_ca_nhan.pdf", file_name="Luong_ca_nhan.pdf",
             owner="hr@x", is_private=1, is_folder=0, attached_to_doctype=None, attached_to_name=None),
    ])]

    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.PermissionError = type("PermissionError", (Exception,), {})
    fr.session = types.SimpleNamespace(user=user)

    def throw(m, exc=None):
        raise (exc or Throw)(m)
    fr.throw = throw
    fr.get_roles = lambda u=None: W.roles.get(u, [])

    def get_all(dt_, filters=None, fields=None, pluck=None, order_by=None, **k):
        if dt_ == "File":
            rows = [r for r in W.files if _match(r, filters)]
            return [r.get(pluck) for r in rows] if pluck else rows
        raise AssertionError("get_all %s" % dt_)
    fr.get_all = get_all
    fr.get_doc = lambda dt_, name=None: W.req if dt_ == "EC Approval Request" else W.doc

    def get_value(dt_, name, field=None, for_update=False, **k):
        if for_update:
            W.locked.append(name)
            return name
        if dt_ == "User":
            return {"fin1@x": "Thu Trinh"}.get(name)
        if dt_ == "EC Approval Request Level":
            return "Finance cấp 2"
        return None

    def set_value(dt_, name, values, *a, **k):
        W.set.append((dt_, name, dict(values)))
        for r in W.files:
            if r["name"] == name:
                r.update(values)
    fr.db = types.SimpleNamespace(get_value=get_value, set_value=set_value)
    fr.enqueue = lambda method, **kw: W.enqueued.append((method, kw))
    fr.log_error = lambda *a, **k: None
    fr.get_traceback = lambda: ""

    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")

    def actor_pending_row(req_name, level_no, actor):
        # Ban sao luat engine (_actor_pending_row + row_still_eligible): dong Pending o DUNG cap,
        # dong "Role: X" chi con hieu luc khi actor van giu X.
        for (lv, a, st, src) in W.approvers:
            if lv == level_no and a == actor and st == "Pending":
                if src.startswith("Role: ") and src[6:] not in W.roles.get(actor, []):
                    continue
                return "ROW-%s-%s" % (lv, a)
        return None
    eng._actor_pending_row = actor_pending_row
    eng.log_action = lambda req, action, actor, level_no=None, level_name=None, comment=None, **k: \
        W.logged.append(dict(req=req, action=action, actor=actor, level_no=level_no,
                             level_name=level_name, comment=comment))

    sp = types.ModuleType("ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror")
    sp.duoc_soi_guong = lambda dt_: dt_ == CTR

    for p in ("ecentric_workspace", "ecentric_workspace.approval_center",
              "ecentric_workspace.approval_center.shared",
              "ecentric_workspace.approval_center.shared.workflow",
              "ecentric_workspace.approval_center.shared.integrations"):
        _pkg(p)
    sys.modules["ecentric_workspace.approval_center.shared.workflow"].transitions = eng
    sys.modules["ecentric_workspace.approval_center.shared.workflow.transitions"] = eng
    sys.modules["ecentric_workspace.approval_center.shared.integrations"].sharepoint_mirror = sp
    sys.modules["ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror"] = sp
    sys.modules["frappe"] = fr
    spec = importlib.util.spec_from_file_location(
        "add_file_mod", APP / "approval_center/shared/requests/add_file.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, fr


DEF = types.SimpleNamespace(business_doctype="EC Leave")
DEF_CTR = types.SimpleNamespace(business_doctype=CTR)
NEW = "/private/files/Plan_Vinasoy.xlsx"


# ---- quyen ------------------------------------------------------------------------------
def test_nguoi_duyet_pending_o_cap_hien_tai_them_duoc_va_ghi_lich_su():
    m, _ = build()
    out = m.add(DEF, "DOC-1", NEW)
    assert out["file_name"] == "Plan_Vinasoy.xlsx" and out["level_no"] == 2
    f = [r for r in W.files if r["name"] == "F-NEW"][0]
    assert (f["attached_to_doctype"], f["attached_to_name"]) == ("EC Leave", "DOC-1")
    assert f["is_private"] == 1
    assert W.locked == ["APR-1"]
    assert len(W.logged) == 1
    row = W.logged[0]
    assert (row["req"], row["action"], row["actor"], row["level_no"]) == \
        ("APR-1", "Attachment Added", "fin1@x", 2)
    assert row["comment"] == "Thu Trinh đính kèm Plan_Vinasoy.xlsx ở cấp 2"
    assert m.capability("fin1@x", W.doc, W.req) == {
        "can_add_attachment": True, "add_attachment_request": "APR-1"}


@pytest.mark.parametrize("user", ["lead@x", "ceo@x", "req@x", "random@x"])
def test_nguoi_khong_giu_phieu_bi_chan(user):
    """Cap da duyet (lead), cap chua toi luot (ceo), nguoi gui, nguoi ngoai: khong."""
    m, fr = build(user=user, files=[dict(name="F-X", file_url=NEW, file_name="a.xlsx", owner=user,
                                          is_private=1, is_folder=0, attached_to_doctype=None,
                                          attached_to_name=None)])
    with pytest.raises(fr.PermissionError):
        m.add(DEF, "DOC-1", NEW)
    assert W.logged == [] and W.set == [] and W.enqueued == []
    assert m.capability(user, W.doc, W.req)["can_add_attachment"] is False


def test_dong_role_mat_role_thi_khong_con_giu_phieu():
    m, fr = build(user="fin2@x", roles=())
    W.roles["fin2@x"] = []
    with pytest.raises(fr.PermissionError):
        m.add(DEF, "DOC-1", NEW)
    assert m.capability("fin2@x", W.doc, W.req)["can_add_attachment"] is False


@pytest.mark.parametrize("status", ["Approved", "Rejected", "Cancelled", "Information Required"])
def test_phieu_khong_con_cho_duyet_bi_chan(status):
    m, fr = build(status=status)
    with pytest.raises(fr.PermissionError):
        m.add(DEF, "DOC-1", NEW)
    assert W.logged == []
    assert m.capability("fin1@x", W.doc, W.req) == m.NO_CAPABILITY


def test_buoc_xu_ly_chi_chu_viec():
    m, _ = build(status="Approved", level=None, fulfillment="In Progress", owner="fin1@x")
    out = m.add(DEF, "DOC-1", NEW)
    assert out["stage"] == "fulfillment" and out["level_no"] is None
    assert W.logged[0]["comment"] == "Thu Trinh đính kèm Plan_Vinasoy.xlsx ở bước xử lý"
    m, fr = build(status="Approved", level=None, fulfillment="In Progress", owner="other@x")
    with pytest.raises(fr.PermissionError):
        m.add(DEF, "DOC-1", NEW)
    m, fr = build(status="Approved", level=None, fulfillment="Completed", owner="fin1@x")
    with pytest.raises(fr.PermissionError):
        m.add(DEF, "DOC-1", NEW)


def test_phieu_chua_gui_bi_chan():
    m, fr = build()
    W.doc["approval_request"] = None
    with pytest.raises(Throw):
        m.add(DEF, "DOC-1", NEW)
    assert W.logged == []


# ---- tep ---------------------------------------------------------------------------------
def test_khong_cho_gan_tep_rieng_tu_cua_nguoi_khac():
    m, fr = build()
    with pytest.raises(fr.PermissionError):
        m.add(DEF, "DOC-1", "/private/files/Luong_ca_nhan.pdf")
    alien = [r for r in W.files if r["name"] == "F-ALIEN"][0]
    assert alien["attached_to_name"] is None
    assert W.logged == [] and W.set == []


def test_khong_cho_gan_lai_tep_da_thuoc_phieu_khac():
    m, fr = build(files=[dict(name="F-1", file_url=NEW, file_name="a.xlsx", owner="fin1@x",
                              is_private=1, is_folder=0, attached_to_doctype="EC Leave",
                              attached_to_name="DOC-OTHER")])
    with pytest.raises(fr.PermissionError):
        m.add(DEF, "DOC-1", NEW)
    assert W.set == []


@pytest.mark.parametrize("url", ["/files/Plan.xlsx", "https://evil/x.xlsx", "/private/files/../../etc/passwd", "", None])
def test_duong_dan_khong_hop_le_hoac_cong_khai(url):
    m, fr = build()
    with pytest.raises((Throw, fr.PermissionError)):
        m.add(DEF, "DOC-1", url)
    assert W.logged == [] and W.set == []


def test_tep_cong_khai_bi_chan_du_cung_ten_duong_dan_private():
    m, fr = build(files=[dict(name="F-1", file_url=NEW, file_name="a.xlsx", owner="fin1@x",
                              is_private=0, is_folder=0, attached_to_doctype=None,
                              attached_to_name=None)])
    with pytest.raises(fr.PermissionError):
        m.add(DEF, "DOC-1", NEW)


def test_duoi_tep_nguy_hiem_bi_chan():
    url = "/private/files/x.html"
    m, fr = build(files=[dict(name="F-1", file_url=url, file_name="x.html", owner="fin1@x",
                              is_private=1, is_folder=0, attached_to_doctype=None,
                              attached_to_name=None)])
    with pytest.raises(Throw):
        m.add(DEF, "DOC-1", url)
    assert W.set == [] and W.logged == []


def test_trung_ten_voi_dinh_kem_cu_thi_doi_ten():
    url = "/private/files/HopDong3ab1.docx"
    m, _ = build(files=[
        dict(name="F-OLD", file_url="/private/files/HopDong.docx", file_name="HopDong.docx",
             owner="req@x", is_private=1, is_folder=0, attached_to_doctype="EC Leave",
             attached_to_name="DOC-1"),
        dict(name="F-1", file_url=url, file_name="hopdong.DOCX", owner="fin1@x", is_private=1,
             is_folder=0, attached_to_doctype=None, attached_to_name=None)])
    out = m.add(DEF, "DOC-1", url)
    assert out["file_name"] == "hopdong (2).DOCX"
    assert [r for r in W.files if r["name"] == "F-1"][0]["file_name"] == "hopdong (2).DOCX"


# ---- SharePoint (Contract Review) ---------------------------------------------------------
def test_contract_review_day_rieng_tep_moi_len_sharepoint_sau_commit():
    m, _ = build(doctype=CTR)
    m.add(DEF_CTR, "DOC-1", NEW)
    assert len(W.enqueued) == 1
    method, kw = W.enqueued[0]
    assert method.endswith("sharepoint_mirror.dong_bo_mot_tep_nen")
    assert kw["file_url"] == NEW and kw["business_name"] == "DOC-1"
    assert kw["business_doctype"] == CTR
    assert kw["enqueue_after_commit"] is True
    # tuyet doi khong dong bo lai ca phieu (ghi de ban song tren SharePoint)
    assert "dong_bo_nen" not in method and "dong_bo_phieu" not in method


def test_form_khac_khong_dua_len_sharepoint():
    m, _ = build()
    m.add(DEF, "DOC-1", NEW)
    assert W.enqueued == []


# ---- sharepoint_mirror.dong_bo_mot_tep (module that, Graph gia) ----------------------------
def _mirror(files, links):
    calls = types.SimpleNamespace(tai_len=[], cap_quyen=[], ghi=[], log=[])
    fr = types.ModuleType("frappe")
    fr.get_all = lambda dt_, filters=None, fields=None, order_by=None, **k: \
        [Obj(r) for r in files if _match(r, filters)]
    fr.db = types.SimpleNamespace(
        get_value=lambda dt_, filters, field=None, **k: links.get((filters or {}).get("file_url")))
    fr.log_error = lambda *a, **k: calls.log.append(a)
    fr.get_traceback = lambda: ""
    fu = types.ModuleType("frappe.utils")
    fu.now_datetime = lambda: None
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = fu
    wr = types.ModuleType("ecentric_workspace.weekly_report.sharepoint")
    wr.safe_filename = lambda n: (n or "").replace(":", "_")
    wr.get_app_token = lambda: "TOKEN"
    wr.GRAPH, wr.SITE_ID = "https://graph", "site"
    _pkg("ecentric_workspace")
    _pkg("ecentric_workspace.weekly_report").sharepoint = wr
    sys.modules["ecentric_workspace.weekly_report.sharepoint"] = wr
    spec = importlib.util.spec_from_file_location(
        "sp_mirror_mod", APP / "approval_center/shared/integrations/sharepoint_mirror.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.tai_len = lambda dt_, url, name, biz, token=None: calls.tai_len.append(url) or {
        "item_id": "IT-" + name, "web_url": "w", "last_modified": None}
    mod.cap_quyen = lambda item, emails, token=None: calls.cap_quyen.append((item, list(emails))) or {
        "da_cap": list(emails), "link": "L"}
    mod.ghi_lien_ket = lambda dt_, url, biz, kq, da_cap=None, share_url=None: calls.ghi.append(url)
    mod.nguoi_trong_luong = lambda dt_, biz: ["req@x", "fin1@x", "fin2@x"]
    return mod, calls


_CTR_FILES = [
    dict(file_url="/private/files/HopDong.docx", file_name="HopDong.docx",
         attached_to_doctype=CTR, attached_to_name="DOC-1"),
    dict(file_url=NEW, file_name="Plan_Vinasoy.xlsx", attached_to_doctype=CTR,
         attached_to_name="DOC-1"),
]


def test_mirror_chi_tai_dung_tep_moi_va_cap_quyen_ca_luong():
    mod, c = _mirror(_CTR_FILES, {"/private/files/HopDong.docx": "ITEM-OLD"})
    out = mod.dong_bo_mot_tep(CTR, "DOC-1", NEW)
    assert out == {"xong": ["Plan_Vinasoy.xlsx"]}
    assert c.tai_len == [NEW]                       # KHONG dung toi HopDong.docx (ban song)
    assert c.cap_quyen == [("IT-Plan_Vinasoy.xlsx", ["req@x", "fin1@x", "fin2@x"])]
    assert c.ghi == [NEW]


def test_mirror_tep_da_co_tren_sharepoint_thi_khong_tai_lai():
    mod, c = _mirror(_CTR_FILES, {NEW: "ITEM-NEW"})
    assert "bo_qua" in mod.dong_bo_mot_tep(CTR, "DOC-1", NEW)
    assert c.tai_len == [] and c.cap_quyen == []


def test_mirror_trung_ten_tep_khac_thi_khong_ghi_de():
    files = [dict(file_url="/private/files/HopDong.docx", file_name="HopDong.docx",
                  attached_to_doctype=CTR, attached_to_name="DOC-1"),
             dict(file_url="/private/files/HopDong9f.docx", file_name="hopdong.docx",
                  attached_to_doctype=CTR, attached_to_name="DOC-1")]
    mod, c = _mirror(files, {})
    assert "bo_qua" in mod.dong_bo_mot_tep(CTR, "DOC-1", "/private/files/HopDong9f.docx")
    assert c.tai_len == []
    assert c.log, "trung ten phai ghi log de quan tri biet"


def test_mirror_loai_phieu_ngoai_danh_sach_va_tep_khong_thuoc_phieu():
    mod, c = _mirror(_CTR_FILES, {})
    assert "bo_qua" in mod.dong_bo_mot_tep("EC Leave", "DOC-1", NEW)
    assert "bo_qua" in mod.dong_bo_mot_tep(CTR, "DOC-2", NEW)
    assert c.tai_len == []


def test_mirror_nen_nuot_loi():
    mod, c = _mirror(_CTR_FILES, {})

    def hong(*a, **k):
        raise RuntimeError("graph down")
    mod.tai_len = hong
    assert mod.dong_bo_mot_tep_nen(CTR, "DOC-1", NEW) is None
    assert c.log


# ---- noi day: DocType, endpoint, capabilities, hooks ---------------------------------------
def test_action_khai_bao_trong_select_cua_doctype():
    d = json.loads((APP / "approval_center/doctype/ec_approval_action/ec_approval_action.json")
                   .read_text(encoding="utf-8"))
    opts = [f for f in d["fields"] if f["fieldname"] == "action"][0]["options"].split("\n")
    m, _ = build()
    assert m.ACTION in opts


def test_endpoint_post_va_capabilities_noi_day():
    src = (APP / "approval_center/reporting/actions.py").read_text(encoding="utf-8")
    i = src.index("def add_attachment(request_name, file_url)")
    assert '@frappe.whitelist(methods=["POST"])' in src[i - 60:i]
    assert "_resolve(request_name)" in src[i:i + 300]
    for p in ("approval_center/shared/requests/capabilities.py",
              "approval_center/features/ai_topup/controllers/api.py"):
        s = (APP / p).read_text(encoding="utf-8")
        assert '"can_add_attachment"' in s and '"add_attachment_request"' in s, p
    hooks = (APP / "hooks.py").read_text(encoding="utf-8")
    assert 'web_include_js.append("ec_addfile.bundle.js")' in hooks
    assert 'web_include_css.append("ec_addfile.bundle.css")' in hooks
    js = (APP / "public/js/ec_addfile.bundle.js").read_text(encoding="utf-8")
    m, _ = build()
    for ext in m.BLOCKED_EXT:
        assert '"%s"' % ext in js, "danh sach duoi cam cua JS lech server: %s" % ext
