# Copyright (c) 2026, eCentric and contributors
"""Khoi "Tai lieu & Ky so" tai tep bang endpoint goc cua Frappe -> nhan vien thuong bi 403.

03/09 chi Hien (Employee, Customer, PM Member) tao phieu cua phong minh, bam "+ Tai tai lieu"
va thay "1 tep loi". Tai hien lai bang chinh phien cua chi:

    POST /api/method/upload_file  (kem doctype=EC Payment Request, docname=...)
    -> 403 PermissionError
       "User hien.nguyen does not have doctype access via role permission
        for document EC Payment Request"

`upload_file` la endpoint CUA FRAPPE va kiem quyen bang DocPerm CHUAN tren DocType. He nay
co y KHONG cap DocPerm chuan cho cac DocType yeu cau - do bang du lieu: ca 8 DocType yeu cau
kiem tra deu chi co MOT dong DocPerm cho System Manager, khong dong nao cho Employee/All -
vi moi duong ghi deu di qua app method co guard. Nen gui kem doctype/docname la tu chuoc lay
mot phep kiem quyen ma kien truc nay co tinh khong dung.

Hau qua: KHONG nhan vien nao thiet lap duoc tai lieu ky so, tuc khong ai gui duoc phieu chi
tien can ky. Hoan khong bao gio thay vi System Manager duoc bo qua moi kiem tra - va cho toi
hom nay chi co Hoan thu.

Loi giai da co san trong repo: 13 form khac tai len KHONG kem doctype/docname (tep rieng tu,
chua thuoc ho so nao) roi gan vao phieu bang app method. Chu thich o main_section.html dong
467 viet nguyen van ly do. Khoi ky so viet sau nen bo sot.

Sua:
  * `document_setup.attach_uploaded_file` - gan tep vao phieu SAU khi tu kiem quyen, dung LAI
    hai cong da co (`_assert_setup_editable` + `_assert_can_classify` khi dang lap ho so;
    `_can_add_supporting` khi dang bi tra lai). Chi gan tep dang MO COI - tep da thuoc ho so
    khac thi tu choi, de mot `file_url` tuy y khong the keo tep cua phieu nguoi khac sang.
  * `esign.api.attach_uploaded_file` (POST, whitelisted).
  * `document_signing_section.html` bo doctype/docname, goi endpoint tren.

CHUA sua trong patch nay: 5 o "tep hoan tat" khac cung gui doctype/docname (system_request,
document_request, data_request, resignation, va trang MSO cu). Cung mot lop loi, nhung nguoi
xu ly cac form do hien chi la Hoan va Dong (hai nguoi duy nhat co quyen) nen chua ai gap; moi
cai la mot trang rieng = mot patch rieng, gom vao mot dot co chu dich.

Patch moi vi p130 da chay - patch chay MOT LAN.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
