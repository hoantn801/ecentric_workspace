# Copyright (c) 2026, eCentric and contributors
"""Tra cuu cho form hop dong KOL/KOC: SO doanh thu, doanh thu da cam ket, mau hop dong.

SO doanh thu EC (chot 11/11/2026):
  * SO Direct cua EC: chon thang.
  * SO tu GBS: nguoi dung chon theo ma GBS SO, nhung luu SO DOI UNG (`Sales Order` co
    `ec_channel='GBS'`, `ec_gbs_so_ref=<GBS SO>`) - do moi la doanh thu EC. SO doi ung do cron
    `ec_gbs_counterpart_reconcile` tao, CHI khi GBS SO co dong phi EC; chua co thi bao ro ly do.
  * Mac dinh chi hien SO cua minh hoac cung phong ban (team); EC Finance / SM thay het.
"""
import frappe

from ecentric_workspace.approval_center.features.contract_review.domain import kol

CR_DT = "EC Contract Review Request"
TEMPLATE_DT = "EC Contract Template"
FINANCE_ROLES = {"EC Finance", "System Manager"}
SO_LIMIT = 30


def is_finance(user):
    return bool(set(frappe.get_roles(user)) & FINANCE_ROLES)


def team_users(user):
    """Nguoi cung phong ban voi `user` (ke ca chinh ho)."""
    dept = frappe.db.get_value("Employee", {"user_id": user}, "department")
    if not dept:
        return {user}
    rows = frappe.get_all("Employee", filters={"department": dept, "user_id": ["is", "set"]},
                          pluck="user_id", limit_page_length=0)
    return set(rows) | {user}


def so_label(row):
    ref = row.get("ec_gbs_so_ref")
    return "%s (GBS %s)" % (row["name"], ref) if ref else row["name"]


SO_FIELDS = ["name", "ec_channel", "ec_brand", "ec_gbs_so_ref", "net_total", "transaction_date",
             "owner", "workflow_state", "docstatus"]
SO_CHANNELS = ("Direct", "GBS")


def _team_gbs_sos(team):
    """GBS SO do nguoi trong team tao - SO doi ung cua chung la SO cua team."""
    return frappe.get_all("GBS Sales Order", filters={"owner": ["in", list(team)]}, pluck="name",
                          order_by="creation desc", limit_page_length=2000, ignore_permissions=True)


def search_sales_orders(user, query=None):
    filters = {"docstatus": ["<", 2], "ec_channel": ["in", list(SO_CHANNELS)]}
    or_filters = None
    q = (query or "").strip()[:60]
    if q:
        like = "%%%s%%" % q
        or_filters = [["name", "like", like], ["ec_gbs_so_ref", "like", like],
                      ["ec_brand", "like", like]]

    def fetch(extra):
        return frappe.get_all("Sales Order", filters=dict(filters, **extra), or_filters=or_filters,
                              fields=SO_FIELDS, order_by="transaction_date desc",
                              limit_page_length=SO_LIMIT, ignore_permissions=True)

    if is_finance(user):
        rows = fetch({})
    else:
        # Loc team NGAY TRONG truy van (khong lay 300 SO moi nhat roi loc sau - SO cu cua team
        # se bi mat). Hai nhom: SO team tao, va SO doi ung cua GBS SO team tao.
        team = team_users(user)
        rows = fetch({"owner": ["in", list(team)]})
        gbs = _team_gbs_sos(team)
        if gbs:
            seen = {r.name for r in rows}
            rows += [r for r in fetch({"ec_gbs_so_ref": ["in", gbs]}) if r.name not in seen]
        rows.sort(key=lambda r: str(r.get("transaction_date") or ""), reverse=True)
    return [{"value": r.name, "label": so_label(r), "brand": r.get("ec_brand") or "",
             "revenue": float(r.get("net_total") or 0), "channel": r.get("ec_channel"),
             "date": str(r.get("transaction_date") or ""), "state": r.get("workflow_state") or ""}
            for r in rows[:SO_LIMIT]]


def so_allowed(user, name):
    """Kiem lai tren server SO nguoi dung gui len (khong tin bo chon tren trang).
    Tra (row, loi): row la SO hop le; loi la thong bao neu khong dung duoc."""
    row = frappe.db.get_value("Sales Order", name, SO_FIELDS, as_dict=True) if name else None
    if not row or row.docstatus == 2:
        return None, "SO %s không tồn tại hoặc đã huỷ." % name
    if row.ec_channel not in SO_CHANNELS:
        return None, "SO %s không phải SO doanh thu EC (Direct / đối ứng GBS)." % name
    if is_finance(user):
        return row, None
    team = team_users(user)
    if row.owner in team:
        return row, None
    if row.ec_gbs_so_ref and frappe.db.get_value("GBS Sales Order", row.ec_gbs_so_ref, "owner") in team:
        return row, None
    return None, "SO %s không thuộc phòng ban của bạn. Nhờ Kế toán nếu cần dùng SO này." % name


def gbs_without_counterpart(user, query):
    """GBS SO khop tu khoa nhung CHUA co SO doi ung - de form bao ly do thay vi im lang.
    Nguoi khong phai ke toan chi thay GBS SO cua team minh."""
    q = (query or "").strip()[:60]
    if not q:
        return []
    flt = [["name", "like", "%%%s%%" % q]]
    if not is_finance(user):
        flt.append(["owner", "in", list(team_users(user))])
    gbs = frappe.get_all("GBS Sales Order", filters=flt,
                         fields=["name", "owner"], limit_page_length=10, ignore_permissions=True)
    have = set(frappe.get_all("Sales Order", filters={"ec_gbs_so_ref": ["in", [g.name for g in gbs] or [""]],
                                                      "docstatus": ["<", 2]},
                              pluck="ec_gbs_so_ref", ignore_permissions=True))
    return [{"gbs": g.name,
             "reason": "GBS SO này chưa có dòng phí EC nên chưa có SO đối ứng (doanh thu EC). "
                       "Thêm dòng phí EC trên GBS SO, đợi tối đa 15 phút rồi chọn lại."}
            for g in gbs if g.name not in have]


def committed_on_so(sales_order, exclude=None):
    """Tong gia tri hop dong KOL/KOC da gui tren SO (tru phieu bi tu choi / huy / nhap)."""
    total = 0.0
    rows = frappe.get_all(CR_DT, filters={"sales_order": sales_order,
                                          "contract_type": kol.KOL_CONTRACT_TYPE,
                                          "approval_request": ["is", "set"]},
                          fields=["name", "contract_value", "approval_request"],
                          limit_page_length=0, ignore_permissions=True)
    for r in rows:
        if exclude and r.name == exclude:
            continue
        status = frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status")
        if status not in ("Rejected", "Cancelled"):
            total += float(r.contract_value or 0)
    return total


def brand_code(brand):
    if not brand:
        return ""
    return frappe.db.get_value("Brand", brand, "ec_brand_code") or ""


def list_templates(kind=None):
    filters = {"is_active": 1}
    if kind:
        filters["kind"] = kind
    return frappe.get_all(TEMPLATE_DT, filters=filters,
                          fields=["name", "kind", "creator_type", "service_type", "has_advance",
                                  "version", "unknown_placeholders"],
                          order_by="template_name asc", limit_page_length=200)


def pick_template(kind, creator_type, service_type, has_advance):
    """Mau khop nhat: dung loai creator; dich vu dung hon 'Tất cả'; co/khong coc dung hon."""
    best, best_score = None, -1
    for t in list_templates(kind):
        if t.creator_type != creator_type:
            continue
        if t.service_type not in ("Tất cả", service_type):
            continue
        score = (2 if t.service_type == service_type else 0) + (1 if bool(t.has_advance) == bool(has_advance) else 0)
        if score > best_score:
            best, best_score = t.name, score
    return best
