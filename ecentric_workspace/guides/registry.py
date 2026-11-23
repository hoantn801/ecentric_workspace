# Copyright (c) 2026, eCentric and contributors
"""MOT cho duy nhat khai bao cac bai huong dan su dung.

Vi sao co file nay thay vi hardcode o ba noi. Moi bai huong dan phai xuat hien o
BA cho: trang muc luc /huong-dan, menu ben trai, va (buoc sau) icon "?" tren the
cua Approval Center + tren chinh trang form. Ba ban sao se lech ngay lan sua thu
hai - kieu lech im lang: menu tro toi bai da doi ten, the tro toi route khong con.

`approval_types` la cau noi giua BAI VIET va FORM: mot bai co the phuc vu nhieu
form (DNMH va DNTT dung chung mot bai vi chung la MOT quy trinh). Trang danh muc
va cac form doc chinh cho nay de biet co huong dan hay khong - khong ai doan.
"""

#: Nhom tren trang muc luc. Bai khong khai "group" thuoc GROUP_DEFAULT. Thu tu = thu tu tuple;
#: trong mot nhom: "order" (mac dinh 100) roi tieu de.
GROUP_DEFAULT = "Hướng dẫn chung"
GROUP_HR = "Quy trình nhân sự"
GROUP_ORDER = (GROUP_DEFAULT, GROUP_HR)


#: slug -> mo ta bai. `route` suy ra tu slug, khong khai lai (mot su that).
GUIDES = {
    "dnmh-dntt": {
        "title": "Đề nghị mua hàng → Đề nghị thanh toán",
        "short": "DNMH → DNTT",
        "summary": "Từ 4 vòng duyệt–ký còn 2 vòng: duyệt và ký số gộp làm một, "
                   "chữ ký trên DNTT ký gộp cả DNMH, Finance xử lý UNC ngay trên hệ.",
        "approval_types": ["PURCHASE_REQUEST", "PAYMENT_REQUEST"],
        "updated": "2026-09-08",
        "audience": "Người đề nghị · Cấp duyệt · Finance",
    },
    "chot-cong-thang": {
        "title": "Chốt công tháng và phân bổ công việc",
        "short": "Chốt công & phân bổ công việc",
        "summary": "Đầu mỗi tháng: kiểm tra công, giải trình, chốt công và nộp tỷ trọng brand. "
                   "Hạn ngày 2 — nhân viên 12:00, leader / trưởng phòng 15:00.",
        # Bai cua Nhan su, khong gan voi form nao o Approval Center -> khong co icon "?".
        "approval_types": [],
        "updated": "2026-10-01",
        "audience": "Mọi nhân viên · Leader · Trưởng phòng",
    },
    # 23/11/2026 - 8 bai "Quy trinh nhan su" (brief HR Agent F, Hoan chot 22-23/11). Bai
    # nhan-su la trang tong quan (luat chung: phieu rieng tu, nguoi theo doi, khong tu duyet,
    # muc Gap) + loi vao tu menu khu Nhan su (shell/nav.py RAIL_LAYOUTS["hr"]).
    # approval_types: chi khai ma DA CO tren site. Form moi (Phe duyet dot xuat, Danh gia
    # nhan su, Ky luat) chua co ma -> them ma vao bai tuong ung khi tich hop form.
    # Tich hop 23/11 (nhanh feat/hr-quy-trinh-nhan-su): da them ADHOC_APPROVAL,
    # EMPLOYEE_REVIEW, DISCIPLINE_DECISION - ma do seed / activation cua chinh nhanh nay tao.
    'nhan-su': {
        "title": 'Quy trình nhân sự trên ERP — tổng quan',
        "short": 'Quy trình nhân sự',
        "summary": 'Bảy quy trình nhân sự mới trên ERP và các luật chung: phiếu riêng tư, người theo dõi, không tự duyệt, mức Gấp, hạn tính theo ngày làm việc.',
        "approval_types": [],
        "updated": '2026-11-23',
        "audience": 'Mọi nhân viên · Line Manager · CnB/HR · CEO',
        "group": GROUP_HR,
        "order": 0,
    },
    'gan-phieu-duyet': {
        "title": 'Gắn phiếu duyệt vào ô đính kèm',
        "short": 'Gắn phiếu duyệt',
        "summary": 'Dùng một phiếu đã duyệt làm chứng từ cho phiếu khác: tìm, gắn, xem trạng thái sống — không chụp màn hình, không chép nội dung.',
        "approval_types": [],
        "updated": '2026-11-23',
        "audience": 'Người gửi phiếu · Người duyệt',
        "group": GROUP_HR,
        "order": 1,
    },
    'phe-duyet-dot-xuat': {
        "title": 'Phê duyệt đột xuất gửi CEO',
        "short": 'Phê duyệt đột xuất',
        "summary": 'Xin CEO duyệt một việc ngoài quy trình bằng phiếu riêng tư trên ERP thay cho email; có mức Gấp báo ngay.',
        "approval_types": ['ADHOC_APPROVAL'],
        "updated": '2026-11-23',
        "audience": 'Mọi nhân viên · CEO',
        "group": GROUP_HR,
        "order": 2,
    },
    'offer-new-staff': {
        "title": 'Offer → New Staff Preparation',
        "short": 'Offer → New Staff',
        "summary": 'Từ thư mời nhận việc tới chuẩn bị ngày đầu đi làm: Line Manager → CnB/HR → (HOF) → CEO, rồi 4 nhóm chuẩn bị song song.',
        "approval_types": ['OFFER_REQUEST', 'NEW_STAFF_PREPARATION'],
        "updated": '2026-11-23',
        "audience": 'TA · Line Manager · CnB/HR · HOF · Operation · CEO',
        "group": GROUP_HR,
        "order": 3,
    },
    'nghi-viec-clearance': {
        "title": 'Nghỉ việc → Clearance',
        "short": 'Nghỉ việc → Clearance',
        "summary": 'Gửi đơn nghỉ việc với ngày cuối hợp lệ, Line Manager → CnB/HR → CEO, rồi bàn giao song song (Clearance) và khảo sát nghỉ việc.',
        "approval_types": ['RESIGNATION', 'CLEARANCE_REQUEST'],
        "updated": '2026-11-23',
        "audience": 'Mọi nhân viên · Line Manager · CnB/HR · Fin · Operation · CEO',
        "group": GROUP_HR,
        "order": 4,
    },
    'danh-gia-nhan-su': {
        "title": 'Đánh giá nhân sự (thử việc · thực tập · hợp đồng)',
        "short": 'Đánh giá nhân sự',
        "summary": 'Một form cho đánh giá cuối thử việc, cuối thực tập và trước khi hết hợp đồng: hệ thống tự tạo nháp, tự gửi đúng ngày; nhân viên → Line Manager → CEO.',
        "approval_types": ['EMPLOYEE_REVIEW'],
        "updated": '2026-11-23',
        "audience": 'Nhân viên · Line Manager · C&B · CEO',
        "group": GROUP_HR,
        "order": 5,
    },
    'khao-sat-nhan-su': {
        "title": 'Khảo sát thử việc, thực tập và nghỉ việc',
        "short": 'Khảo sát nhân sự',
        "summary": 'Khảo sát tự giao theo mốc cho người thử việc, thực tập và khảo sát khi nghỉ việc: ai trả lời, ai xem, hạn bao lâu.',
        "approval_types": [],
        "updated": '2026-11-23',
        "audience": 'Nhân viên mới · Thực tập sinh · Người nghỉ việc · HR · Line Manager',
        "group": GROUP_HR,
        "order": 6,
    },
    'ky-luat': {
        "title": 'Kỷ luật: thẻ vàng, thẻ đỏ, thẻ đen',
        "short": 'Kỷ luật',
        "summary": 'Thẻ vàng là nhắc nhở nội bộ; thẻ đỏ / đen là kỷ luật theo Bộ luật Lao động, đi 4 bước: hồ sơ → thông báo họp → họp → CEO ký quyết định.',
        "approval_types": ['DISCIPLINE_DECISION'],
        "updated": '2026-11-23',
        "audience": 'Nhân viên · Line Manager · HR/CnB · CEO',
        "group": GROUP_HR,
        "order": 7,
    },
}

ROUTE_PREFIX = "/huong-dan"



def route_of(slug):
    return "%s/%s" % (ROUTE_PREFIX, slug)


def guide_for_approval_type(approval_type):
    """Bai huong dan cua mot loai yeu cau, hoac None. Dung cho icon "?" tren the."""
    if not approval_type:
        return None
    for slug, g in GUIDES.items():
        if approval_type in g.get("approval_types", ()):
            out = dict(g)
            out["slug"] = slug
            out["route"] = route_of(slug)
            return out
    return None


def group_of(g):
    return g.get("group") or GROUP_DEFAULT


def _sort_key(kv):
    g = kv[1]
    grp = group_of(g)
    rank = GROUP_ORDER.index(grp) if grp in GROUP_ORDER else len(GROUP_ORDER)
    return (rank, grp, g.get("order", 100), g["title"])


def listed():
    """Danh sach bai de dung trang muc luc: theo nhom (GROUP_ORDER), roi "order", roi tieu de."""
    out = []
    for slug, g in sorted(GUIDES.items(), key=_sort_key):
        item = dict(g)
        item["slug"] = slug
        item["route"] = route_of(slug)
        item["group"] = group_of(g)
        out.append(item)
    return out
