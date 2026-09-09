# Copyright (c) 2026, eCentric and contributors
"""Phong ban gui sang nha cung cap: lay theo PHIEU, khong phai mot hang so.

VAN DE (do that 09/09/2026). `EC Digital Signature Profile.department_id` la MOT gia
tri co dinh ("cntt"), duoc gan cho MOI tai lieu ERP day sang SCTS. Nen mot phieu do
ban Uyen (phong Service) tao lai hien tren cong SCTS thuoc phong "Data & System".
Voi mot he chi co mot luong ky thi day chi la sai nhan; nhung neu ben SCTS dung
departmentId de phan quyen xem hay dinh tuyen duyet thi moi phieu deu dang nam sai
phong - nguoi dung khong thay, nguoi khong lien quan lai thay.

CACH LAM. Phong ban cua phieu (`department` tren chinh business doc - la BAN CHUP
luc gui duyet, khong doi duoc sau do) -> tra ma phong ban SCTS o Custom Field
`custom_scts_department_id` tren DocType `Department`.

!! GIA TRI DIEN VAO CUSTOM FIELD LA TRUONG `id` CUA CAY PHONG BAN eCONTRACT,
   KHONG PHAI TRUONG `code`. Hai cai KHAC NHAU: phong "Data & System" co
   id='cntt' nhung code='CNTT 1'. Ngay 09/09/2026 dien nham cot `code` (SER,
   FINANCE, HR...) -> AddDocument tra HTTP 500 -> ba goi ket o 'Provider
   Creating'. Vi 'cntt' - gia tri duy nhat dang chay dung luc do - trong giong
   mot "ma" viet thuong nen khong ai nghi no la mot id. Dau hieu nhan biet:
   id cua cac phong khac deu la GUID. Neu gia tri dien vao trong nhu mot ma
   viet hoa ngan gon thi gan nhu chac chan la dang lay nham cot.
   Lay bang cach GET cay phong ban cua eContract va doc cot `id`.

BA QUYET DINH DANG CHU Y:

1. **Ma nam tren chinh ban ghi Department, khong phai mot bang anh xa rieng.**
   Mot khai niem = mot cho. Them phong ban moi thi dien ma vao ngay tai do, khong
   ai phai nho con mot bang thu hai o dau nua. `Department` la DocType cua ERPNext
   nen dung Custom Field - dung quy uoc "KHONG dung DocType native, mo rong bang
   Custom Field".

2. **Chua dien ma thi LUI VE gia tri cua Profile, khong chan.** Mot phieu ky khong
   duoc vi thieu mot dong cau hinh la cai gia qua dat cho viec hien dung ten phong.
   Nen ham nay khong bao gio nem loi. Doi lai, no KHONG im lang: moi lan phai lui
   ve deu ghi mot dong log de con biet ma dien not.

3. **Gia tri THAT SU gui di duoc luu lai tren goi** (`department_id_sent`, xem
   tasks.py). Ly do: buoc doi soat trong service.py so dinh danh do SCTS tra ve voi
   ho so - truoc day so voi Profile. Neu gio gui gia tri dong ma van so voi Profile
   thi moi goi cua phong khac deu bi tu choi doi soat ("identity_mismatch"). Phai so
   voi cai DA GUI, khong phai cai mac dinh.
"""
import frappe

#: Custom Field tren DocType `Department` (khai trong hooks.py fixtures).
DEPT_FIELD = "custom_scts_department_id"


def department_of_business(business_doctype, business_name):
    """Phong ban ghi tren phieu, hoac None. Doctype nao khong co cot `department`
    (khong phai form nao cung co) thi tra None - khong phai loi."""
    if not (business_doctype and business_name):
        return None
    try:
        if not frappe.db.has_column(business_doctype, "department"):
            return None
    except Exception:
        return None
    return frappe.db.get_value(business_doctype, business_name, "department")


def scts_code_of_department(department):
    """Ma phong ban SCTS cua mot Department, hoac None neu chua dien / chua co field."""
    if not department:
        return None
    try:
        if not frappe.db.has_column("Department", DEPT_FIELD):
            return None
    except Exception:
        return None
    return (frappe.db.get_value("Department", department, DEPT_FIELD) or "").strip() or None


def resolve_department_id(business_doctype, business_name, fallback=None, package=None):
    """Ma phong ban gui sang nha cung cap cho MOT phieu cu the.

    Thu tu: ma SCTS cua phong ban tren phieu -> `fallback` (thuong la
    Profile.department_id) -> None. Khong bao gio nem loi.
    """
    dept = department_of_business(business_doctype, business_name)
    code = scts_code_of_department(dept)
    if code:
        return code
    # Khong ghi log khi phieu KHONG co phong ban (nhieu form nhu vay) - chi ghi khi
    # co phong ban that ma chua ai dien ma cho no. Do moi la viec con thieu.
    if dept:
        frappe.log_error(
            "esign: phong ban '%s' chua co %s -> lui ve '%s' (%s %s%s)"
            % (dept, DEPT_FIELD, fallback, business_doctype, business_name,
               ", goi %s" % package if package else ""),
            "esign department fallback")
    return fallback


def resolve_for_package(pkg, profile_department_id):
    """Ma phong ban GUI DI cho mot goi. Tra (ma, co_phai_lan_dau).

    GHI MOT LAN, roi giu nguyen. Day khong phai toi uu - day la tinh dung.
    `create_document` co the chay lai (thu lai sau loi tam thoi, hoac nhanh doi soat
    goi lai). Neu moi lan chay deu giai lai phong ban thi chi can ai do sua ma phong
    ban giua hai lan la gia tri gui lan 2 khac lan 1; va buoc doi soat sau do se so
    voi mot con so ma SCTS chua bao gio nhan -> tu choi doi soat. Cai da gui la su
    that lich su, khong phai mot phep tinh lam lai duoc.

    Ghi mot lan cung la ly do khong lo Error Log: chi lan DAU chua co ma moi ghi
    log nhac dien, khong ghi lai o moi lan thu.
    """
    sent = pkg.get("department_id_sent") if hasattr(pkg, "get") else None
    if sent:
        return sent, False
    code = resolve_department_id(pkg.get("business_doctype"), pkg.get("business_name"),
                                 fallback=profile_department_id, package=pkg.get("name"))
    return code, bool(code)
