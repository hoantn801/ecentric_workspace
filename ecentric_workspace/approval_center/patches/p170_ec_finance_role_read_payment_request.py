# Copyright (c) 2026, eCentric and contributors
"""Cap quyen DOC tren `EC Payment Request` cho ROLE `EC Finance` (09/09, Hoan chot).

PHAN BU cho p167, KHONG thay the no
-----------------------------------
`p167_backfill_fulfiller_file_read` (chat khac, cung ngay) da vá dung goc: cap DocShare cho
Fulfiller duoc cau hinh, ngay luc dung luong + cap bu cho phieu dang mo. Patch nay khong dung
den co che do va khong lam no thua.

Nhung DocShare cap theo tung NGUOI, va chinh p167 ghi ro han che do trong
`grant_read_to_snapshot_approvers`: "ai duoc them vao Role Fulfiller SAU khi phieu da gui thi
khong co dong chia se cua phieu do". Cong them: cap bu chi cham phieu CON MO
(Pending / Information Required) - phieu da Approved/Rejected/Cancelled khong duoc cap.

Hai lo con lai sau p167, ca hai deu thuoc ve phong Finance:
  1. Phieu chi DA XONG - ke toan tra cuu lai khoan da tra thi van 403 tren tep dinh kem.
  2. Nguoi MOI vao phong Finance - khong co quyen tren moi phieu da gui truoc do, tru khi co
     ai nho chay lai patch. Hoan chot 09/09: "khi cap thi ai vao nhom do duoc quyen xem,
     don gian vay ma?" - tuc la khong chap nhan mot viec tay lap lai.

Cap quyen doc cho chinh Role la cach dong ca hai lo bang MOT dong cau hinh: Fulfiller cua
De nghi thanh toan von DA la Role `EC Finance` (p149, buoc 6 "Finance xu ly UNC"), nen hai
thu doc cung MOT danh sach - them nguoi vao role la xem duoc ngay, bo ra la mat ngay.

Trieu chung do duoc tren production 09/09
-----------------------------------------
Chi Dan (Ke toan) mo /approvals/all-requests thay 32 phieu chi, mo phieu ra thay du noi
dung VA thay ca danh sach ten tep dinh kem - nhung bam vao tep thi 403. Do duoc:
  * 32/32 ho so co tep, 122 tep RIENG TU (di qua cong quyen);
  * chi duoc DocShare tren dung 1 ho so;
  * `EC Payment Request` chi co MOT dong DocPerm: System Manager.
Nghia la tren loai phieu nay khong role nao doc duoc; moi quyen doc chay qua DocShare.

Vi sao lo hong xuat hien
------------------------
`d914f2d1` mo danh sach cho NGUOI XU LY (Fulfiller duoc cau hinh) - dung, vi
`can_view_request` va `is_eligible_fulfiller` da coi ho la nguoi duoc xem tu truoc. Nhung
cong file cua Frappe doc DocShare/DocPerm, KHONG doc luat cua app. DocShare thi chi duoc
cap cho nguoi duyet (luc dung luong + p163) va nguoi DA NHAN VIEC (co ToDo). Nguoi xu ly
chua nhan viec khong co gi ca. Day dung la loi CEO Lam gap 08/09, doi chan: lan do la
NGUOI DUYET, lan nay la NGUOI XU LY.

Vi sao cap theo ROLE chu khong theo tung nguoi (Hoan chot 09/09)
---------------------------------------------------------------
DocShare cap theo NGUOI: moi nguoi moi vao phong Finance lai phai chay lai mot patch cap
bu, va khong ai nho de chay. Fulfiller cua De nghi thanh toan von DA duoc cau hinh la
Role `EC Finance` (p149, buoc 6 "Finance xu ly UNC" - ca phong, ai ranh nhan). Cap quyen
doc cho chinh role do thi hai thu doc cung MOT danh sach: them nguoi vao role la ho xem
duoc ngay, bo ra la mat ngay, khong con buoc thu cong nao o giua.

KHONG noi rong pham vi: nhom duoc cap dung bang nhom ma `scope_predicate` (fulfil_types)
va `can_view_request` da cho xem toan bo phieu chi tu truoc do.

Chi cap READ
------------
`write` KHONG can: duong ghi cua buoc fulfillment di bang SQL truc tiep / ignore_permissions
(xem features/payment_request/application/service.py :: claim_fulfillment), va file UNC
duoc tai len khong kem doctype/docname dung vi nhan vien thuong khong co DocPerm chuan.
`export`/`report` KHONG cap: khong bay san mot duong keo ca bang ra ngoai.
`create`/`delete`/`submit`/`cancel`/`amend` KHONG cap.

TAC DUNG PHU - DOC TRUOC KHI MIGRATE
------------------------------------
`frappe.permissions.add_permission()` goi `setup_custom_perms()`, lan dau se CHEP moi dong
DocPerm chuan cua DocType sang `Custom DocPerm`; tu do Frappe doc quyen cua DocType nay o
`Custom DocPerm` va BO QUA cac dong chuan (frappe/model/meta.py). Cu the o day: dong
System Manager trong `ec_payment_request.json` tro thanh VO HIEU tren production.

Hau qua phai nho: sau patch nay, sua muc `permissions` trong ec_payment_request.json se
KHONG con tac dung tren site nay. Muon doi quyen thi doi qua Custom DocPerm (hoac
`reset_perms` roi lam lai). Day la cai gia da biet truoc cua viec cap role qua API duoc
ho tro - giong het p045 da chap nhan cho Sales Order / Purchase Order.

Rollback
--------
    bench --site team.ecentric.vn execute frappe.permissions.reset_perms --args "['EC Payment Request']"
Xoa moi dong Custom DocPerm cua DocType -> khoi phuc dong System Manager chuan VA go bo
quyen doc cua EC Finance (tuc la tra lai dung lo hong 403 o tren).

KHONG BAO GIO nem loi: patch chay trong migrate, mot exception lam chet ca lan deploy (p116).
Idempotent: chay lai khong doi gi them.
"""
import frappe
from frappe.permissions import add_permission, update_permission_property

ROLE = "EC Finance"
DOCTYPE = "EC Payment Request"

# CHI doc. Xem muc "Chi cap READ" o docstring truoc khi them bat ky quyen nao vao day.
GRANTS = ("read",)


def execute():
    try:
        if not frappe.db.exists("Role", ROLE):
            frappe.log_error("Role %s chua co tren site -> bo qua" % ROLE, "p170 finance role read")
            return
        if not frappe.db.exists("DocType", DOCTYPE):
            frappe.log_error("DocType %s chua co -> bo qua" % DOCTYPE, "p170 finance role read")
            return

        add_permission(DOCTYPE, ROLE, 0)
        for ptype in GRANTS:
            update_permission_property(DOCTYPE, ROLE, 0, ptype, 1, validate=False)
        frappe.clear_cache(doctype=DOCTYPE)
        frappe.log_error("da cap %s tren %s cho Role '%s'" % ("/".join(GRANTS), DOCTYPE, ROLE),
                         "p170 finance role read")
    except Exception:
        # Thieu quyen doc thi nguoi dung van mo duoc ho so trong app, chi vuong tep dinh kem.
        # Khong dang de danh doi ca lan deploy.
        frappe.log_error(frappe.get_traceback(), "p169 finance read THAT BAI")
