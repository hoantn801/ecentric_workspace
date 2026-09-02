# Copyright (c) 2026, eCentric and contributors
"""Them canh KY CHINH: buoc 4, transitionId -4, WfFunctionRunSignedA, ky-chinh, terminal.

CHUP TAY TU CONG 03/09/2026 00:2x, cung tai lieu `07ab9b5d-...` da chup bon buoc dau (p127):

    Ky chinh -> transitionId "-4", transitionName "Phe duyet",
                processAction "WfFunctionRunSignedA", signType "ky-chinh", toUsers []

`toUsers` RONG: sau Ky chinh khong con ai - day la buoc cuoi, nen `terminal=1`. Code
`plan_handover` da xu ly: khong co nguoi ke tiep + terminal -> gui transition voi toUsers [].

SUA MOT KET LUAN SAI cua dem 02/09: toi noi chu ky `ky-chinh` co `signToken=1`/`hsmId=null`
nen "phai ky bang OfficeSignTool tai may, ERP khong ky thay duoc". Sai. Do la trang thai khi
nguoi do CHUA GAN CHUNG THU SO tren cong. Hoan gan xong, bam Phe duyet buoc Ky chinh tren
cong -> ky duoc tu may chu binh thuong, khong can tool. Anh Lam chi can gan chung thu.

KHONG ghi de p127. Patch chay MOT LAN; them canh moi = patch moi. Idempotent theo
(action, transition_id).
"""
import frappe

PROFILE_CODE = "PAYMENT-REQUEST-SCTS-UAT"
_NOTE = "Chup tu cong eContract 03/09/2026 (buoc Ky chinh). Khong sua neu khong co ban chup moi."

CANH = {"step_index": 4, "transition_id": -4, "transition_name": "Phe duyet",
        "process_action": "WfFunctionRunSignedA", "sign_type": "ky-chinh",
        "stage": "approval", "terminal": 1}


def execute():
    name = frappe.db.get_value("EC Digital Signature Profile", PROFILE_CODE, "name") \
        or frappe.db.get_value("EC Digital Signature Profile",
                               {"profile_code": PROFILE_CODE}, "name")
    if not name:
        print("[WARN] khong tim thay ho so %s - bo qua" % PROFILE_CODE)
        return
    doc = frappe.get_doc("EC Digital Signature Profile", name)
    row = None
    for r in (doc.get("transitions") or []):
        if r.action == "Sign" and r.transition_id is not None \
                and int(r.transition_id) == CANH["transition_id"]:
            row = r
            break
    if row is None:
        row = doc.append("transitions", {"action": "Sign"})
        print("[OK] them canh -4")
    else:
        print("[OK] cap nhat canh -4")
    for k, v in CANH.items():
        setattr(row, k, v)
    row.notes = _NOTE
    doc.save(ignore_permissions=True)

    # VERIFY - doc lai tu DB.
    lai = frappe.get_doc("EC Digital Signature Profile", name)
    ok = False
    for r in (lai.get("transitions") or []):
        if r.action == "Sign" and r.transition_id is not None and int(r.transition_id) == -4:
            ok = (int(r.step_index or -1) == 4 and r.process_action == "WfFunctionRunSignedA"
                  and r.sign_type == "ky-chinh" and int(r.terminal or 0) == 1)
    print("[OK]  -4 buoc 4 ky-chinh terminal" if ok else "[ERR] canh -4 khong ghi dung")
    if not ok:
        frappe.throw("p128: canh Ky chinh khong ghi duoc")
