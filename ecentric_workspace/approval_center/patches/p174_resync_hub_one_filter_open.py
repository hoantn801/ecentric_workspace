# Copyright (c) 2026, eCentric and contributors
"""Hub: mo mot o loc thi dong o dang mo truoc do - 10/09, Hoan.

Trieu chung: bam lan luot bon o loc "Nhom / Loai yeu cau / Phong ban / Trang thai" thi CA BON
panel cung mo, chong len bang ben duoi - nhin nhu giao dien vo.

DA DO TREN PRODUCTION truoc khi sua (khong suy doan):
    bam o 1 -> mo 1 | bam o 2 -> mo 2 | bam ca 4 -> mo 4 | bam ra ngoai -> mo 0
    position cua .ec-cb-panel = absolute  (nen no KHONG day bo cuc; hang loc van thang hang:
    do lai sau p173 ra moi o top=0 h=44, nhan top=0 h=14, o nhap top=16 h=28)

Goc nam o `public/js/ec_formkit.bundle.js` (asset dung chung toan site):
    btn.onclick = function(e){ e.stopPropagation(); panel.hidden ? open() : close(); };
    document.addEventListener("click", function(e){ if(!wrap.contains(e.target)) close(); });
Moi o CO san bo dong-khi-bam-ra-ngoai o tang document. Nhung nut cua no goi stopPropagation(),
nen cu bam KHONG BAO GIO toi duoc document -> bo dong cua nhung o kia khong chay. Bam ra cho
trong (khong trung nut nao) thi dong het - dung nhu do duoc.

KHONG sua bundle: no dung chung cho 27 form + cac trang legacy, sua o do la doi hanh vi cua
nhung trang khac ma khong ai ngo. Ban va nam TRONG trang hub, nghe o PHA BAT (capture, chay
tu tren xuong TRUOC khi handler cua nut kip chan) va gioi han trong `#ec-apl-root .fgrid`.

Da thu lai tren chinh production sau khi tiem ban va:
    bam Nhom -> [Nhom] | bam Loai yeu cau -> [Loai yeu cau] | bam Phong ban -> [Phong ban]
    bam Trang thai -> [Trang thai]        (mo cai moi, dong cai cu)
    bam lai chinh no -> dong han; chieu cao .fgrid khong doi (44.0)

Landmark = dieu PHAI CO tren ban song.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARKS = ("function dongOLocKhac", "dongOLocKhac();", ".ec-cb-panel")


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p174 all_requests sync=%s" % action, "p174 resync")
    if action == "refused":
        frappe.log_error(
            "p174: upsert TU CHOI GHI (khoa chong troi). Trang KHONG duoc cap nhat - doc "
            "live_sha trong ket qua roi them vao SUPERSEDES_SHA256.", "p174 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        # Khong nem loi: mot exception o day lam chet CA LAN MIGRATE (bai hoc p116). Nhung
        # phai ghi ro, vi deploy se bao sach du trang chua duoc cap nhat.
        frappe.log_error("p174: trang all-requests thieu dau moc %s" % missing,
                         "p174 KHONG toi noi")
