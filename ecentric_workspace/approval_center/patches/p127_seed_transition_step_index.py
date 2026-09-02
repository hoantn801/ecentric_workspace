# Copyright (c) 2026, eCentric and contributors
"""Danh so vi tri buoc cho cac canh chuyen eContract, va them `-10`, `-11`.

CHUP TAY TU CONG 02/09/2026, mot tai lieu duy nhat, bam tuan tu qua tung buoc
(`07ab9b5d-153d-4e5f-a287-232f8ea877ea`, mau "De nghi thanh toan, De nghi mua hang, De nghi
tam ung (5 chu ky)" - cung mau voi phieu that):

    Trinh ky  -> transitionId "-2"   WfFunctionRunSignedOther / ky-tham-gia
    duyet 1   -> transitionId "-9"   WfFunctionRunSignedOther / ky-tham-gia
    duyet 2   -> transitionId "-10"  WfFunctionRunSignedOther / ky-tham-gia
    duyet 3   -> transitionId "-11"  WfFunctionRunSignedOther / ky-tham-gia
    Ky chinh  -> signToken=1, hsmId=null  => ky bang OfficeSignTool tren may nguoi ky

VI SAO PHAI SUA. Cau hinh cu gan DUNG MOT id `-9` cho moi buoc duyet, nen buoc 3 va 4 luon
bi tra 400 "Duong chuyen khong hop le hoac khong khop trang thai". Sau 400 he lui ve pool,
va pool chi ky duoc khi nguoi minh gui TINH CO dung la nguoi eContract dang cho:

    02/09 03:24  DSR-00026  400 -> pool -> chi Lien KY DUOC (trung nguoi)
    02/09 03:25  DSR-00027  400 -> pool -> chi Phuong KHONG (trat) -> 20 phut -> Manual Review

Hai buoc dau chay tot bao lau nay khong phai may man - `-2` va `-9` dung that. Tu buoc 3 tro
di he dang song bang xo so, va hom nay no trat.

transitionId chay theo THU TU BUOC trong quy trinh: khong theo nguoi (cung mot nguoi dung
buoc 2 o tai lieu nay, cap 4 o tai lieu khac), va khong theo cap duyet cua ERP. Nen khoa la
`step_index` = SO CHU KY DA CO tren tai lieu truoc buoc do, dem tu chinh nha cung cap.

KHONG seed canh nao chua chup duoc. `-12` la "Tu choi" - so duyet va so tu choi xen ke nhau,
nen bat cu co che "thu tuan tu id cho toi khi duoc" nao cung co ngay tu tu choi mot phieu chi
tien that. Chi gui id da chup va biet chac ten.

Idempotent: khop dong theo (parent, action, transition_id) roi cap nhat tai cho.
"""
import frappe

PROFILE_CODE = "PAYMENT-REQUEST-SCTS-UAT"
CHILD = "EC Digital Signature Profile Transition"
_NOTE = "Chup tuan tu tu cong eContract 02/09/2026. Khong sua neu khong co ban chup moi."

# step_index = so chu ky da co truoc buoc nay.
BUOC = [
    {"step_index": 0, "transition_id": -2, "transition_name": "Trinh ky", "stage": "requester"},
    {"step_index": 1, "transition_id": -9, "transition_name": "Phe duyet", "stage": "approval"},
    {"step_index": 2, "transition_id": -10, "transition_name": "Phe duyet", "stage": "approval"},
    {"step_index": 3, "transition_id": -11, "transition_name": "Phe duyet", "stage": "approval"},
]


def execute():
    # Truong la `profile_code`, KHONG phai `code`. Ban dau viet {"code": ...} - Frappe loc
    # theo mot truong khong ton tai thi NEM DataError chu khong tra None, nen patch se chet
    # ngay tu dong dau chu khong "bo qua em dep" nhu chu thich cu tuong. Bat duoc trong lan
    # do thu tren site that truoc khi deploy, khong phai bang doc code.
    name = frappe.db.get_value("EC Digital Signature Profile", PROFILE_CODE, "name") \
        or frappe.db.get_value("EC Digital Signature Profile",
                               {"profile_code": PROFILE_CODE}, "name")
    if not name:
        print("[WARN] khong tim thay ho so %s - bo qua" % PROFILE_CODE)
        return
    doc = frappe.get_doc("EC Digital Signature Profile", name)
    theo_id = {}
    for r in (doc.get("transitions") or []):
        if r.action == "Sign" and r.transition_id is not None:
            theo_id.setdefault(int(r.transition_id), r)

    them = capnhat = 0
    for b in BUOC:
        r = theo_id.get(b["transition_id"])
        if r is None:
            r = doc.append("transitions", {"action": "Sign"})
            them += 1
        else:
            capnhat += 1
        r.transition_id = b["transition_id"]
        r.transition_name = b["transition_name"]
        r.process_action = "WfFunctionRunSignedOther"
        r.sign_type = "ky-tham-gia"
        r.stage = b["stage"]
        r.step_index = b["step_index"]
        r.terminal = 0
        r.notes = _NOTE

    doc.save(ignore_permissions=True)
    print("[OK] %s: them %d, cap nhat %d canh chuyen" % (PROFILE_CODE, them, capnhat))

    # VERIFY - doc lai tu DB, khong tin doc trong bo nho.
    lai = frappe.get_doc("EC Digital Signature Profile", name)
    co = {int(r.transition_id): r.step_index
          for r in (lai.get("transitions") or [])
          if r.action == "Sign" and r.transition_id is not None}
    loi = 0
    for b in BUOC:
        thuc = co.get(b["transition_id"])
        dung = thuc is not None and int(thuc) == b["step_index"]
        print("%s  %-4s buoc %s" % ("[OK]  " if dung else "[ERR] ",
                                    b["transition_id"], b["step_index"]))
        loi += 0 if dung else 1
    if loi:
        frappe.throw("p127: %d canh chuyen khong ghi duoc" % loi)
