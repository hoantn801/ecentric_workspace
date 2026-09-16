# Copyright (c) 2026, eCentric and contributors
"""Nap cau hinh SLA cua tung buoc duyet tu `fixtures/approval_sla.json` vao he thong.

HAI BANG, MOT MA. Moi chinh sach duoc ghi vao ca hai noi duoi CUNG mot
`policy_code`:

  EC Approval SLA Policy   Approval Center doc de tinh `due_at` cho cap duyet.
                           Day la thu lam cho han hien ra tren phieu, tren
                           Action Center, tren bao cao.
  EC SLA Policy            Module SLA doc de cham diem nguoi duyet.

Chung phai la MOT con so. Neu hai ban cau hinh troi ra khoi nhau thi phieu bao
dung han con bang diem bao tre - va khi hai he thong noi hai dieu khac nhau ve
cung mot nguoi, ca hai deu mat gia tri.

SO HUU: chinh sach co ma bat dau bang `WH-`/`CH-` la do tep nay DUNG RA va do no
so huu - moi truong duoc dinh nghia lai day du moi lan chay. Chinh sach co ma
khac (vd `AI_TOPUP_MANAGER_3H`, do mot tinh nang tu dat) thi tep nay chi sua
DUNG BA CON SO: so gio, nhac truoc, va loai gio. Khong doi ten, khong bat/tat,
khong dong vao cac truong khac.

Ly do khong doi ten: ma va nhan cua mot tinh nang duoc chinh tinh nang do kiem
tra lai luc kich hoat (`validate_ai_topup_v1`). Doi so thi an toan; doi ten thi
bien bon chinh sach rieng biet thanh bon dong trung ten trong moi o chon.

CHAY LAI BAO NHIEU LAN CUNG MOT KET QUA. Moi lan chay deu doi chieu lai NOI DUNG
chinh sach chu khong chi doi chieu cai lien ket - neu khong, mot nguoi sua tay
`WH-8H-R4` thanh 80 gio se khong bao gio bi phat hien, va 23 buoc duyet im lang
chay theo mot cai han sai gap muoi lan.

CAP NHAT SAU NAY: sua so trong `fixtures/approval_sla.json`, deploy, roi goi
`ecentric_workspace.sla.controllers.api.reimport_approval_sla`. KHONG can viet
patch moi - patch chi la lan chay dau tien.
"""
import io
import json
import os

import frappe

from ecentric_workspace.sla.constants import DT_POLICY, DUE_BUSINESS_HOURS, DUE_CALENDAR_HOURS

AC_POLICY = "EC Approval SLA Policy"
AC_LEVEL = "EC Approval Level"
AC_PROCESS = "EC Approval Process"

UNIT_BUSINESS = "giờ làm việc"
UNIT_CALENDAR = "giờ đồng hồ"

OWNED_PREFIXES = ("WH-", "CH-")

# Lich lam viec chuan cua cong ty. Doi bang site_config neu bench khac dung lich khac.
DEFAULT_CALENDAR = "EC_STANDARD_9_18"
CALENDAR_CONF_KEY = "ec_sla_business_calendar"

_FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "fixtures", "approval_sla.json")


def load_rows(path=None):
    with io.open(path or _FIXTURE, encoding="utf-8") as f:
        return json.load(f)["rows"]


def _calendar():
    return frappe.conf.get(CALENDAR_CONF_KEY) or DEFAULT_CALENDAR


def policy_code_for(hours, reminder_hours, unit):
    """Ma chinh sach suy ra tu chinh con so, khong phai tu ten buoc.

    Nho vay hai buoc cung "4 gio lam viec, nhac truoc 2 gio" dung chung mot ban
    ghi - sua mot cho la sua ca hai. Neu dat ten theo buoc (`PAYMENT_L1_4H`) thi
    se co 60 ban ghi gan nhu giong het nhau, va lan sua thu hai chac chan bo sot
    mot cai.
    """
    prefix = "WH" if unit == UNIT_BUSINESS else "CH"
    h = int(hours) if float(hours) == int(hours) else hours
    return "%s-%sH-R%s" % (prefix, h, int(reminder_hours or 0))


def _is_ours(code):
    return bool(code) and code.startswith(OWNED_PREFIXES)


# --------------------------------------------------------------------------- #
# Ghi chinh sach
# --------------------------------------------------------------------------- #
# Nhung truong duoc phep cham vao khi CAP NHAT mot chinh sach KHONG phai cua bo
# nap (vd `AI_TOPUP_MANAGER_3H`). Chi con so - khong ten, khong trang thai.
_AC_NUMBER_KEYS = ("duration_hours", "reminder_before_hours",
                   "use_business_hours", "business_calendar")
_SLA_NUMBER_KEYS = ("due_rule", "duration_hours", "business_calendar")


def _ac_fields(hours, reminder_hours, unit):
    """Bo truong DAY DU cho EC Approval SLA Policy.

    Luon day du, ke ca voi ma cua tinh nang khac. Phan biet "chi sua con so" la
    viec cua luc CAP NHAT (`_AC_NUMBER_KEYS`), khong phai luc TAO MOI: `policy_name`
    la truong bat buoc, va tra ve mot bo thieu no se lam `insert` nem
    MandatoryError - da xay ra that tren ban chay ngay 16/09 voi ca bon dong
    AI Topup.
    """
    business = unit == UNIT_BUSINESS
    return {
        "duration_hours": int(hours),
        "reminder_before_hours": int(reminder_hours or 0),
        "use_business_hours": 1 if business else 0,
        "business_calendar": _calendar() if business else None,
        "policy_name": "%s giờ %s (nhắc trước %s giờ)"
                       % (int(hours), "làm việc" if business else "đồng hồ",
                          int(reminder_hours or 0)),
        "active": 1,
        "holiday_list": None,
    }


def _sla_fields(hours, reminder_hours, unit, name_hint=None):
    business = unit == UNIT_BUSINESS
    return {
        "due_rule": DUE_BUSINESS_HOURS if business else DUE_CALENDAR_HOURS,
        "duration_hours": float(hours),
        "business_calendar": _calendar() if business else None,
        # Khi phai tao ban sao cho mot ma cua tinh nang khac, LAY LAI dung nhan
        # cua ban goc thay vi tu dat ten. Hai ban ghi cung ma ma khac ten se lam
        # nguoi doc tuong day la hai chinh sach.
        "policy_name": name_hint or ("%s giờ %s" % (int(hours),
                                     "làm việc" if business else "đồng hồ")),
        "active": 1,
        # Dinh nghia LAI day du moi truong anh huong toi phep tinh han. Bo trong
        # mot truong nghia la de nguyen gia tri cu - va mot `offset_days=2` ai do
        # go nham se lam diem SLA lech hai ngay so voi han tren phieu, mai mai.
        "grace_minutes": 0,
        "offset_days": 0,
        "fixed_time": None,
        "holiday_list": None,
        "description": "Nạp từ fixtures/approval_sla.json. Dùng chung mã với "
                       "EC Approval SLA Policy để hạn trên phiếu và điểm SLA "
                       "luôn là một con số.",
    }


def _differs(doc, want):
    return [k for k, v in want.items() if (doc.get(k) or None) != (v or None)]


def _upsert(doctype, code, fields, update_keys, report, created_key, updated_key):
    """Tao hoac cap nhat mot chinh sach. Tim bang `policy_code` o CA HAI bang.

    `fields` luon DAY DU (de `insert` khong thieu truong bat buoc); `update_keys`
    la tap con duoc phep ghi de khi ban ghi DA TON TAI. Tach hai viec nay ra la
    co y: han che pham vi sua chi co nghia voi mot ban ghi da co chu, con voi mot
    ban ghi moi thi han che pham vi chi tao ra mot ban ghi khong hop le.

    Khong dung `frappe.db.exists(doctype, code)`: do la tim theo DOCNAME. Voi
    ban ghi duoc tao truoc khi co `autoname: field:policy_code`, docname la hash
    va khong bang policy_code - tim kieu do se truot, roi `insert` dam vao khoa
    duy nhat va nem DuplicateEntryError giua mot patch.
    """
    name = frappe.db.get_value(doctype, {"policy_code": code}, "name")
    if name:
        want = {k: v for k, v in fields.items() if k in update_keys}
        doc = frappe.get_doc(doctype, name)
        changed = _differs(doc, want)
        if changed:
            doc.update(want)
            doc.save(ignore_permissions=True)
            report[updated_key].append("%s (%s)" % (code, ",".join(sorted(changed))))
        return name
    doc = frappe.new_doc(doctype)
    doc.policy_code = code
    doc.update(fields)
    doc.insert(ignore_permissions=True)
    report[created_key].append(code)
    return doc.name


def _write_policy(code, hours, reminder_hours, unit, report):
    owned = _is_ours(code)
    ac = _ac_fields(hours, reminder_hours, unit)
    _upsert(AC_POLICY, code, ac,
            set(ac) if owned else set(_AC_NUMBER_KEYS),
            report, "ac_policy_created", "ac_policy_updated")
    # Ban sao ben SLA lay lai nhan cua ban goc khi ma khong phai cua bo nap.
    hint = None if owned else frappe.db.get_value(AC_POLICY, {"policy_code": code},
                                                  "policy_name")
    sla = _sla_fields(hours, reminder_hours, unit, name_hint=hint)
    _upsert(DT_POLICY, code, sla,
            set(sla) if owned else set(_SLA_NUMBER_KEYS),
            report, "sla_policy_created", "sla_policy_updated")


# --------------------------------------------------------------------------- #
# Gan vao cap duyet / buoc xu ly
# --------------------------------------------------------------------------- #
def _resolve_process(process_code):
    """`PAYMENT_REQUEST` -> docname cua EC Approval Process dang chay.

    Doi chieu trong Python chu khong bang `like`: trong SQL LIKE thi `_` la mot
    ky tu dai dien, ma gan het ma quy trinh o day deu co `_`. `AI_TOPUP-V%` se
    khop ca `AIxTOPUPxV1`. Hom nay khong co ban ghi nao nhu vay, nhung mot bo nap
    cau hinh khong nen dua vao dieu do.
    """
    rows = frappe.get_all(AC_PROCESS, fields=["name", "version_no", "status"],
                          limit_page_length=0)
    mine = [r for r in rows
            if r["name"].rsplit("-V", 1)[0] == process_code and "-V" in r["name"]]
    if not mine:
        return None
    active = [r for r in mine if (r.get("status") or "") == "Active"]
    pool = active or mine
    # Sap theo (version_no, name) de ket qua on dinh khi hai ban cung phien ban -
    # neu khong, lan chay hom nay va lan chay tuan sau co the chon hai ban khac
    # nhau va khong ai giai thich duoc tai sao han doi.
    pool.sort(key=lambda r: (-(r.get("version_no") or 0), r["name"]))
    if len(pool) > 1:
        return pool[0]["name"], [r["name"] for r in pool]
    return pool[0]["name"]


def _resolve_process_name(process_code, report, key):
    res = _resolve_process(process_code)
    if res is None:
        report["missing"].append("%s (không thấy quy trình)" % key)
        return None
    if isinstance(res, tuple):
        name, pool = res
        report["ambiguous_process"].append("%s -> chọn %s trong %s" % (key, name, pool))
        return name
    return res


def _shared_by_others(code, level_name=None, process_name=None):
    """Ma chinh sach nay con cho nao khac dang tro toi khong - ca cap duyet LAN
    buoc xu ly. Chi dem cap duyet la thieu mot nua: mot ma dung chung giua mot
    cap duyet va mot buoc xu ly van la dung chung."""
    lv = frappe.db.count(AC_LEVEL, {"sla_policy": code, "name": ("!=", level_name or "")})
    pr = frappe.db.count(AC_PROCESS, {"fulfillment_sla_policy": code,
                                      "name": ("!=", process_name or "")})
    return (lv + pr) > 0


def _apply_one(row, process, report):
    code = policy_code_for(row["hours"], row["reminder_hours"], row["unit"])
    ful = bool(row.get("fulfillment"))

    if ful:
        holder, field, current = process, "fulfillment_sla_policy", frappe.db.get_value(
            AC_PROCESS, process, "fulfillment_sla_policy")
        doctype = AC_PROCESS
    else:
        lv = frappe.db.get_value(AC_LEVEL,
                                 {"approval_process": process, "level_no": row["level_no"]},
                                 ["name", "sla_policy"], as_dict=True)
        if not lv:
            report["missing"].append("%s (không thấy cấp duyệt)" % row["key"])
            return
        holder, field, current = lv["name"], "sla_policy", lv.get("sla_policy")
        doctype = AC_LEVEL

    if current and current != code:
        # Da co chinh sach RIENG. Giu ma, chi sua so - tru khi ma do dang duoc
        # dung chung: sua no se doi han cua mot buoc khong lien quan.
        shared = _shared_by_others(current,
                                   level_name=None if ful else holder,
                                   process_name=holder if ful else None)
        if shared:
            report["kept_shared"].append("%s giữ %s (dùng chung, không sửa)"
                                         % (row["key"], current))
            return
        _write_policy(current, row["hours"], row["reminder_hours"], row["unit"], report)
        report["kept_own"].append("%s giữ mã %s" % (row["key"], current))
        return

    # Doi chieu NOI DUNG truoc, roi moi den lien ket. Lam nguoc lai thi mot khi
    # lien ket dung, khong ai kiem con so ben trong nua.
    _write_policy(code, row["hours"], row["reminder_hours"], row["unit"], report)
    if current == code:
        report["unchanged"].append(row["key"])
        return
    frappe.db.set_value(doctype, holder, field, code)
    report[("fulfillment_set" if ful else "level_set")].append("%s = %s" % (row["key"], code))


# --------------------------------------------------------------------------- #
# Diem vao
# --------------------------------------------------------------------------- #
_BUCKETS = ("ac_policy_created", "ac_policy_updated", "sla_policy_created",
            "sla_policy_updated", "level_set", "fulfillment_set", "unchanged",
            "kept_own", "kept_shared", "ambiguous_process", "missing", "failed")


def _new_report():
    return {k: [] for k in _BUCKETS}


def apply(rows=None, path=None):
    """Nap cau hinh. Tra ve bao cao chi tiet. Chay lai duoc.

    MOI DONG MOT DIEM LUU. Khong co no thi mot dong hong se keo theo: giao dich
    bi huy bo, moi dong sau do cung hong, va den luot `frappe.log_error` cung nem
    loi vi giao dich da chet - tuc la ca ban deploy do, dung o cho ma tep nay
    hua la khong bao gio lam do.
    """
    rows = rows if rows is not None else load_rows(path)
    report = _new_report()
    for row in rows:
        key = row.get("key")
        sp = "sla_cfg"
        try:
            frappe.db.savepoint(sp)
        except Exception:
            sp = None
        try:
            process = _resolve_process_name(row["process_code"], report, key)
            if process:
                _apply_one(row, process, report)
        except Exception:
            if sp:
                try:
                    frappe.db.rollback(save_point=sp)
                except Exception:
                    pass
            report["failed"].append(key)
            try:
                frappe.log_error(title="sla.policy_import %s" % key,
                                 message=frappe.get_traceback())
            except Exception:
                pass
    return report


def verify(rows=None, path=None):
    """Doi chieu he thong voi tep cau hinh - CHI DOC, khong ghi gi.

    Ton tai vi `apply()` chay trong mot patch, va mot patch fail-safe luon ket
    thuc xanh du 65/65 dong hong. Neu khong co duong doc lai doc lap thi "deploy
    xanh" va "cau hinh dung" la hai dieu khac nhau ma khong ai phan biet duoc.
    """
    rows = rows if rows is not None else load_rows(path)
    out = {"ok": [], "sai_han": [], "chua_gan": [], "khong_thay": [],
           "quy_trinh_thieu_buoc_xu_ly": []}
    for row in rows:
        key = row["key"]
        want_h, want_r = int(row["hours"]), int(row["reminder_hours"] or 0)
        try:
            res = _resolve_process(row["process_code"])
            process = res[0] if isinstance(res, tuple) else res
            if not process:
                out["khong_thay"].append(key)
                continue
            if row.get("fulfillment"):
                current = frappe.db.get_value(AC_PROCESS, process, "fulfillment_sla_policy")
            else:
                current = frappe.db.get_value(
                    AC_LEVEL, {"approval_process": process, "level_no": row["level_no"]},
                    "sla_policy")
            if not current:
                out["chua_gan"].append(key)
                continue
            pol = frappe.db.get_value(AC_POLICY, {"policy_code": current},
                                      ["duration_hours", "reminder_before_hours",
                                       "use_business_hours", "active"], as_dict=True)
            sla = frappe.db.get_value(DT_POLICY, {"policy_code": current},
                                      ["duration_hours", "active"], as_dict=True)
            bad = []
            if not pol:
                bad.append("thiếu EC Approval SLA Policy")
            else:
                if int(pol.duration_hours or 0) != want_h:
                    bad.append("giờ trên phiếu=%s (cần %s)" % (pol.duration_hours, want_h))
                if int(pol.reminder_before_hours or 0) != want_r:
                    bad.append("nhắc trước=%s (cần %s)" % (pol.reminder_before_hours, want_r))
                if not pol.active:
                    bad.append("chính sách đang tắt")
            if not sla:
                bad.append("thiếu EC SLA Policy (điểm SLA sẽ không chấm được)")
            elif abs(float(sla.duration_hours or 0) - want_h) > 0.001:
                bad.append("giờ chấm điểm=%s (cần %s)" % (sla.duration_hours, want_h))
            out["sai_han" if bad else "ok"].append(
                key if not bad else "%s: %s" % (key, "; ".join(bad)))
        except Exception:
            out["khong_thay"].append("%s (lỗi tra cứu)" % key)

    # Quy trinh CO buoc xu ly that nhung chua co han. `apply()` duyet theo DONG
    # nen mot quy trinh vang mat khoi tep cau hinh khong bao gio hien ra o do -
    # mot dong bi bo quen trong Excel se im lang mai mai.
    #
    # "Co buoc xu ly" = co nguoi tham gia voi vai tro Fulfiller. Khong dung "quy
    # trinh nao khong co fulfillment_sla_policy": phan lon quy trinh KHONG he co
    # buoc xu ly, va dem ca chung se ra 24 dong canh bao trong khi chi 3 dong la
    # that - mot bang canh bao toan nhieu thi khong ai doc nua.
    try:
        with_ful = {r["parent"] for r in frappe.get_all(
            "EC Approval Participant", parent=AC_PROCESS, limit_page_length=0,
            filters={"parenttype": AC_PROCESS, "participant_purpose": "Fulfiller"},
            fields=["parent"])}
        for name in sorted(with_ful):
            if not frappe.db.get_value(AC_PROCESS, name, "fulfillment_sla_policy"):
                out["quy_trinh_thieu_buoc_xu_ly"].append(name.rsplit("-V", 1)[0])
    except Exception:
        out["quy_trinh_thieu_buoc_xu_ly"].append("(không tra cứu được)")
    return out


def summarize(report):
    return "; ".join("%s=%d" % (k, len(v)) for k, v in sorted(report.items()) if v)
