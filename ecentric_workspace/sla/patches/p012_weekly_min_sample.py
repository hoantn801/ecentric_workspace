# Copyright (c) 2026, eCentric and contributors
"""Ha nguong mau cua nhom Bao cao tuan: 3 tuan -> 1 tuan.

VI SAO. Nguong 3 duoc dat khi chua co du lieu that. Chay len ban song moi thay
no sai o cho nay: mot thang chi co 4-5 tuan, nen doi du 3 tuan nghia la ca
cong ty nhin mot cot TRONG trong hai phan ba dau thang. Con nguoi doc thi hieu
dau "—" thanh "khong co du lieu", trong khi that ra ho DA bi tinh diem roi -
mot nguoi khong nop bao cao tuan W38 dang la 71.4% chinh vi no.

Nguong khong giau duoc hinh phat, no chi giau LY DO. Do la kieu te nhat: nguoi
ta thay diem tut ma khong thay tai sao.

Chu so huu chot 21/09: ha xuong 1.

DANH DOI, noi ro de sau nay khong ai ngac nhien: voi 1 tuan thi ti le nhom chi
co hai gia tri, 0% hoac 100%. Do dung la thu ma nguong sinh ra de chan. Chap
nhan vi doi voi nhom nay, mot con so nhay con hon mot o trong bi doc nham.

`GROUP_MIN_SAMPLE` trong `constants.py` moi la thu `scoring.aggregate` doc de
cham diem. Ban ghi `EC SLA Obligation Type` duoi day chi phuc vu HIEN THI (tab
"Cach tinh SLA" doc no qua endpoint `effective_dates`). Phai doi CA HAI, neu
khong trang se noi "toi thieu 3 tuan" trong khi he thong cham theo 1 - va mot
trang giai thich sai ve cach cham diem con te hon khong co trang nao.

FAIL-SAFE: moi loi bi nuot va ghi Error Log. Mot patch hong chan CA lan deploy,
va viec nay khong quan trong den muc do.
"""
import frappe

TITLE = "p012 ha nguong mau Bao cao tuan 3 -> 1"

TYPE_CODE = "WEEKLY_REPORT"
NEW_MIN = 1


def execute():
    try:
        from ecentric_workspace.sla.constants import DT_TYPE
        name = frappe.db.get_value(DT_TYPE, {"type_code": TYPE_CODE}, "name")
        if not name:
            frappe.log_error(title=TITLE,
                             message="khong thay ban ghi %s - bo qua" % TYPE_CODE)
            return
        cur = frappe.db.get_value(DT_TYPE, name, "min_sample")
        if int(cur or 0) == NEW_MIN:
            frappe.log_error(title=TITLE, message="da la %s - khong doi" % NEW_MIN)
            return
        frappe.db.set_value(DT_TYPE, name, "min_sample", NEW_MIN,
                            update_modified=False)
        frappe.log_error(title=TITLE,
                         message="min_sample %s -> %s tren %s" % (cur, NEW_MIN, name))
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())
