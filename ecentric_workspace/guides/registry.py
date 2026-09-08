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


def listed():
    """Danh sach bai de dung trang muc luc, sap theo tieu de."""
    out = []
    for slug, g in sorted(GUIDES.items(), key=lambda kv: kv[1]["title"]):
        item = dict(g)
        item["slug"] = slug
        item["route"] = route_of(slug)
        out.append(item)
    return out
