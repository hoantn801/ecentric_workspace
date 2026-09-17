# Copyright (c) 2026, eCentric and contributors
"""Mot dong trang thai cua ho so duyet dan toi nghia vu SLA nao. Thuan - khong
import frappe.

Tach ra khoi `hooks.py` de kiem duoc bang python3 tran. Day la nhom DUY NHAT ma
du lieu vao khong phai cua module SLA: no den tu `EC Approval Request Level` va
`EC Approval Request Approver`, hai bang do Approval Center so huu va co the doi
ma khong ai bao truoc. Mot bang quyet dinh viet ro, co test, la cho de doi chieu
khi dieu do xay ra.

BA KHAI NIEM DE LAN NHAU, phai tach bach:

  * `level_status`    cap duyet da xong chua (In Progress / Approved / Rejected)
  * `approver_status` NGUOI NAY da bam gi chua (Pending / Approved / Rejected /
                      Information Requested / Skipped)
  * nghia vu SLA      nguoi nay co PHAN HOI trong han khong

Nghia vu do PHAN HOI, khong do DONG Y. Nguoi bam "Tu choi" dung han la dung han;
nguoi bam "Yeu cau bo sung" dung han cung la dung han. Cham theo ket qua duyet
se bien SLA thanh ap luc phai duyet, va do la cach nhanh nhat de bien mot he do
luong thanh mot he gay hai.
"""

ACT_OPEN = "open"          # con no - qua han ma chua bam thi thanh Missed
ACT_CLOSE = "close"        # da phan hoi - so moc bam voi han
ACT_EXCLUDE = "exclude"    # co ban ghi, khong cham diem, co ly do nhin thay duoc
ACT_MISSED = "missed"      # khong phan hoi va da qua han
ACT_SKIP = "skip"          # khong tao ban ghi nao

#: Nhung gi tinh la DA PHAN HOI. "Skipped" khong nam o day: no la thu he thong
#: lam voi nguoi ta, khong phai thu nguoi ta lam.
RESPONDED = ("Approved", "Rejected", "Information Requested")

REASON_ANY_ONE = "Người khác trong cùng cấp đã xử lý (Any-One)"
REASON_OVERRIDE = "Ban Giám đốc ép duyệt cấp này trước hạn"
REASON_LEVEL_SKIPPED = "Cấp duyệt bị bỏ qua (trùng người duyệt)"


def attempt_no(restart_count):
    """Lan thu may ho so nay chay lai tu dau.

    Mot ho so bi tra ve roi `Restarted` se di lai tu cap 1, va nhung nguoi da
    duyet o lan truoc phai duyet lai. Do la mot nghia vu MOI, khong phai nghia
    vu cu mo lai: neu dung chung khoa chong trung thi lan thu hai se khong tao
    duoc ban ghi nao, va ca vong duyet thu hai bien mat khoi bang diem.

    `Resubmitted` (gui lai, tiep tu cap dang do) KHONG tang so lan: cap do van
    la cap do, nguoi do van no dung chu ky do - dong ho chi tam dung roi chay
    tiep.
    """
    try:
        n = int(restart_count or 0)
    except (TypeError, ValueError):
        n = 0
    return (n if n > 0 else 0) + 1


def override_outcome(due_at, at, cmp_fn=None):
    """Ban Giam doc ep duyet mot cap -> nguoi duyet cua cap do bi cham the nao.

    Chu so huu chot 17/09: THEO HAN.

      * ep duyet khi DA qua han  -> van tinh la khong phan hoi (Missed). Nguoi
        do da tre truoc khi co lenh ep, va mot lan ep duyet khong duoc phep xoa
        vet do - neu khong thi ai tre cung chi can nho ep duyet mot cai la sach.
      * ep duyet khi CHUA toi han -> loai tru. Sau lenh ep ho khong con nut nao
        de bam; giu ho chiu mot cai han khong con cach nao dap ung khong con la
        do hanh vi nua.

    Khong co han (`due_at is None`) thi khong the tre -> loai tru.
    """
    if due_at is None or at is None:
        return ACT_EXCLUDE, REASON_OVERRIDE
    late = cmp_fn(due_at, at) if cmp_fn else (at > due_at)
    return (ACT_MISSED, None) if late else (ACT_EXCLUDE, REASON_OVERRIDE)


def reconcile_decision(level_status, approver_status, decided_at):
    """Doi chieu nguoc: mot dong (cap duyet, nguoi duyet) DANG o trang thai nay
    thi nghia vu SLA cua no le ra phai o dau.

    Dung cho duong CHAY BU - khi mot loi goi hook bi mat (may chu restart giua
    giao dich, module SLA chua migrate, loi mang). Duong nay khong thay the
    hook: no chi vao nhung cho hook da truot.

    CO Y KHONG NGHIEM HON DUONG HOOK. Mot nguoi `Skipped` o day luon duoc loai
    tru, ke ca khi cap dong sau han - trong khi duong hook cua lenh ep duyet lai
    cham theo han. Ly do: hai duong phai ra CUNG mot ket qua cho cung mot su
    viec, neu khong thi diem cua mot nguoi phu thuoc vao viec hom do co su co
    ha tang hay khong. Duong chay bu khong biet chac vi sao mot nguoi bi
    `Skipped` (Any-One hay bi ep duyet), nen no chon nhanh KHONG cham diem -
    tha bo sot mot vet tre con hon tao ra mot vet tre khong co that.
    """
    # CAP BI BO QUA THANG MOI THU KHAC, ke ca khi mot dong nguoi duyet con ghi
    # "Approved" tu mot vong truoc. Cap do khong phat sinh nghia vu cho ai, nen
    # dong ghi kia khong duoc bien thanh mot diem cong mien phi. Thu tu nay la
    # co y - dat sau nhanh RESPONDED thi mot cap bi bo qua van cho diem.
    if level_status == "Skipped":
        return ACT_SKIP, None, REASON_LEVEL_SKIPPED
    if approver_status in RESPONDED:
        return ACT_CLOSE, decided_at, None
    if approver_status == "Skipped":
        return ACT_EXCLUDE, None, REASON_ANY_ONE
    if approver_status == "Pending":
        if level_status in ("Approved", "Rejected"):
            # Cap da dong ma nguoi nay chua bam -> Any-One, nguoi khac da xu ly.
            return ACT_EXCLUDE, None, REASON_ANY_ONE
        # Cap con dang chay -> con no. Qua han hay chua la viec cua `scoring`,
        # khong phai cua ham nay: cham o day se dong bang mot trang thai ma le
        # ra phai duoc tinh lai moi lan doc.
        return ACT_OPEN, None, None
    # Mot chuoi khong nam trong bang tren. Khong doan - khong tao ban ghi, de
    # duong chay bu bao ra.
    return ACT_SKIP, None, "trạng thái người duyệt không rõ: %s" % (approver_status,)
