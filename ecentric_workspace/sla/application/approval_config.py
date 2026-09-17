# Copyright (c) 2026, eCentric and contributors
"""Han SLA DANG CHAY cua tung cap duyet / buoc xu ly - de hien len trang /sla.

DOC CAU HINH THAT, KHONG DOC LAI FIXTURE. `fixtures/approval_sla.json` la thu
ta MUON he thong cham; bang nay phai tra loi mot cau hoi khac han: "hom nay he
thong DANG cham theo con so nao". Hai thu do troi ra khoi nhau duoc - mot lan
sua tay tren Desk la du - va neu trang nay doc fixture thi no se mai mai noi
rang moi thu dung, ke ca khi khong.

VI SAO TRANG NAY MO CHO MOI NHAN VIEN. Diem SLA tru vao nguoi duyet, nen nguoi
duyet phai tra loi duoc "toi co bao lau" TRUOC khi bi cham tre, khong phai sau.
O day khong co du lieu ca nhan nao: ten quy trinh, so cap, so gio - het. Danh
sach NGUOI duyet khong nam trong bang nay.

BUOC CHUA CO HAN VAN PHAI HIEN RA. 3/60 buoc xu ly hom nay chua co ai nhan
trach nhiem (DATA_REQUEST, ASSET_REQUEST, BOOKING_REQUEST). Loc chung di se lam
bang nay trong nhu da xong; giu lai va danh dau "chua cau hinh" thi no la mot
viec phai lam, dung nhu no la - va nhung buoc do dang duoc LOAI TRU khoi diem,
khong phai duoc cham 100%.
"""
import frappe

AC_POLICY = "EC Approval SLA Policy"
AC_LEVEL = "EC Approval Level"
AC_PROCESS = "EC Approval Process"
AC_PARTICIPANT = "EC Approval Participant"

UNIT_BUSINESS = "giờ làm việc"
UNIT_CALENDAR = "giờ đồng hồ"

#: `level_no` gia cho dong "buoc xu ly": no khong phai mot cap duyet nen khong
#: co so cap that, nhung van can mot khoa sap xep de no luon nam CUOI mot quy
#: trinh - dung thu tu viec xay ra tren thuc te.
FULFILLMENT_LEVEL_NO = 99
FULFILLMENT_LABEL = "Bước xử lý (sau khi duyệt xong)"


def _policies():
    """(tra theo docname, tra theo policy_code) - HAI map RIENG.

    Phai tra ca hai khoa: `sla_policy` la truong Link nen no giu DOCNAME, va
    nhung ban ghi tao truoc khi co `autoname: field:policy_code` co docname la
    mot chuoi bam, khong bang ma.

    Nhung KHONG duoc gop hai loai khoa vao mot dict. Hom nay co the ton tai
    dong thoi: P1 voi docname bam va policy_code "X", va P2 voi docname "X".
    Gop chung lai thi tuy thu tu SQL tra ve, `out["X"]` co the la P1 - va moi
    cap duyet tro toi docname "X" se hien so gio cua mot chinh sach khac. Mot
    lan reindex la con so doi, khong ai giai thich duoc.
    """
    by_name, by_code = {}, {}
    rows = frappe.get_all(AC_POLICY, fields=[
        "name", "policy_code", "policy_name", "duration_hours",
        "reminder_before_hours", "use_business_hours", "active"],
        limit_page_length=0)
    for r in rows:
        info = {
            "policy_code": r.get("policy_code") or r["name"],
            "policy_name": r.get("policy_name"),
            "hours": r.get("duration_hours"),
            "reminder_hours": r.get("reminder_before_hours") or 0,
            "unit": UNIT_BUSINESS if r.get("use_business_hours") else UNIT_CALENDAR,
            "active": bool(r.get("active")),
        }
        by_name[r["name"]] = info
        if r.get("policy_code"):
            by_code.setdefault(r["policy_code"], info)
    return by_name, by_code


def _lookup(policies, key):
    """Docname truoc, ma sau - dung thu tu ma truong Link luu gia tri."""
    if not key:
        return None
    by_name, by_code = policies
    return by_name.get(key) or by_code.get(key)


def _active_processes():
    """Quy trinh dang chay. Mot quy trinh co nhieu phien ban; chi ban `Active`
    moi la cai dang cham diem ai do."""
    rows = frappe.get_all(AC_PROCESS, filters={"status": "Active"}, fields=[
        "name", "process_code", "title", "version_no", "fulfillment_sla_policy"],
        order_by="title asc, name asc", limit_page_length=0)
    return rows


def _processes_with_fulfiller(names):
    """(tap quy trinh co NGUOI xu ly sau duyet, doc duoc hay khong).

    Khong co Fulfiller thi "buoc xu ly" la mot o trong tren so do, khong phai
    mot nghia vu chua cau hinh - va dem chung vao se bien 3 viec phai lam thanh
    24 dong nhieu.

    TRA VE CA CO HONG, khong chi tra tap rong. Neu truy van nay hong ma ta im
    lang tra rong thi ba dong "buoc xu ly" bien mat, `chua_cau_hinh` tut ve 0,
    va trang bao "57/57 buoc da co han" - dung ba dong dang con thieu chu lai
    la ba dong khong hien ra. Do la kieu hong nguy hiem nhat cua bang nay: no
    lam chu quy trinh yen tam.
    """
    if not names:
        return set(), True
    try:
        # Loc `parent` trong Python chu khong dua vao filters: day la bang con,
        # va cach goi DUY NHAT da chay duoc tren ban song (policy_import.verify,
        # 16/09) la bo loc phang khong kem tham so `parent`. Danh sach nay co
        # vai chuc dong, khong dang doi mot lan gay nua.
        rows = frappe.get_all(AC_PARTICIPANT, filters={
            "parenttype": AC_PROCESS, "participant_purpose": "Fulfiller"},
            pluck="parent", limit_page_length=0)
        return set(rows) & set(names), True
    except Exception:
        frappe.log_error(title="sla.approval_config._processes_with_fulfiller",
                         message=frappe.get_traceback())
        return set(), False


def _row(proc, level_no, step_label, policy_key, policies):
    info = _lookup(policies, policy_key)
    return {
        "process_code": proc.get("process_code") or proc["name"],
        "title": proc.get("title") or proc.get("process_code") or proc["name"],
        "level_no": level_no,
        "step": step_label,
        "policy_code": (info or {}).get("policy_code") or policy_key or None,
        "hours": (info or {}).get("hours"),
        "unit": (info or {}).get("unit"),
        "reminder_hours": (info or {}).get("reminder_hours"),
        # `configured` khong phai "co lien ket khong" ma "co con so khong".
        # Mot lien ket tro toi mot chinh sach 0 gio la chua cau hinh, du cot
        # `sla_policy` nhin thi day.
        "configured": bool(info and info.get("hours")),
        # Chinh sach bi TAT van co con so, nen no khac "chua cau hinh". Hien
        # rieng thay vi giau: trang nay hua doc "cau hinh dang chay", ma mot
        # chinh sach da tat thi khong con chac la thu dang chay.
        "active": None if info is None else bool(info.get("active")),
    }


def approval_steps():
    """Bang cau hinh: moi cap duyet mot dong, moi buoc xu ly mot dong."""
    procs = _active_processes()
    by_name = {p["name"]: p for p in procs}
    levels = []
    if by_name:
        levels = frappe.get_all(AC_LEVEL, filters={
            "approval_process": ("in", list(by_name))}, fields=[
            "approval_process", "level_no", "level_name", "sla_policy",
            "approval_mode"], order_by="level_no asc", limit_page_length=0)
    policies = _policies()
    fulfillers, fulfiller_ok = _processes_with_fulfiller(list(by_name))

    rows = []
    for lv in levels:
        proc = by_name.get(lv["approval_process"])
        if not proc:
            continue
        label = "Cấp %s%s" % (lv.get("level_no"),
                              " — %s" % lv["level_name"] if lv.get("level_name") else "")
        r = _row(proc, lv.get("level_no") or 0, label, lv.get("sla_policy"), policies)
        r["approval_mode"] = lv.get("approval_mode")
        rows.append(r)
    for p in procs:
        if p["name"] not in fulfillers:
            continue
        rows.append(_row(p, FULFILLMENT_LEVEL_NO, FULFILLMENT_LABEL,
                         p.get("fulfillment_sla_policy"), policies))

    # Sap theo MA quy trinh, khong theo ten: hai quy trinh khac nhau co the
    # trung ten, va sap theo ten se dat chung canh nhau de UI gop lam mot.
    rows.sort(key=lambda r: (r["process_code"] or "", r["level_no"]))
    missing = [r for r in rows if not r["configured"]]
    off = [r for r in rows if r["configured"] and r["active"] is False]
    return {
        "rows": rows,
        "tong": len(rows),
        "da_cau_hinh": len(rows) - len(missing),
        "chua_cau_hinh": len(missing),
        "da_tat": len(off),
        # UI phai noi duoc "bang nay dang THIEU dong" thay vi ve mot bang trong
        # nhu da du.
        "fulfiller_loi": not fulfiller_ok,
    }
