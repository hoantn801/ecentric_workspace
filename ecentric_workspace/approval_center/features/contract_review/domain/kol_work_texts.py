# Copyright (c) 2026, eCentric and contributors
"""Doan van mo ta cong viec trong HDDV/BBNT - chep NGUYEN VAN tu tool Google Sheet cu.

buildWorkTexts_ -> work_texts, buildAdvanceServiceTexts_ -> advance_texts (Apps Script
2026.10.05-PERFORMANCE-V5.0.3). Day la cau chu Ke toan / phap che da duyet va da ky voi ~300
creator: muon sua cau chu thi sua o day VA bao Ke toan, khong sua rieng mot ben.
"""
from ecentric_workspace.approval_center.features.contract_review.domain.kol_texts import (
    HYBRID, VIDEO, _d, quantity_text)

_MIN_PRODUCT = "- Số lượng sản phẩm tối thiểu của Bên A được giới thiệu: 01 sản phẩm."
_MIN_LABEL = "- Số lượng sản phẩm tối thiểu của bên A được giới thiệu: "


def _object(service_phrase, platform_name):
    return ("Theo các điều khoản và điều kiện của Hợp đồng này, Bên A yêu cầu và Bên B đồng ý cung "
            "cấp dịch vụ %s trên nền tảng %s theo chỉ định, yêu cầu của Bên A, cụ thể như sau:"
            % (service_phrase, platform_name))


def _live(brand, channel_url, dates, quantity, duration, custom, shopee):
    platform = "Shopee" if shopee else "TikTok"
    date_lines = ", ".join(_d(d) for d in dates)
    lines = ["- Số lượng: " + quantity_text(quantity, "LIVESTREAM") + ".",
             "- Các phiên livestream dự kiến diễn ra vào: " + date_lines + ".",
             ("- Thời lượng mỗi phiên: " + duration + ".") if duration
             else "- Thời lượng mỗi phiên: theo booking được duyệt.",
             _MIN_PRODUCT]
    if custom:
        lines.append("- Yêu cầu bổ sung: " + custom)
    prefix = ("Bên B sẽ phát video trực tiếp (livestream) nhằm giới thiệu, quảng bá sản phẩm " + brand
              + " và gắn link mua hàng (Affiliate) trên nền tảng " + platform + ", cụ thể là kênh "
              + platform + " của Bên B: ")
    tiktok_short = "Tik Tok" if not shopee else "Shopee"
    return {
        "titleShort": "Livestream Shopee" if shopee else "Livestream",
        "serviceDisplay": "Livestream Shopee" if shopee else "Livestream",
        "serviceAction": "phát trực tiếp (livestream)",
        "objectParagraph": _object("livestream", platform),
        # Tool cu: ban Shopee KHONG co gach dau dong o dau doan, ban TikTok co.
        "workParagraph": (prefix if shopee else "- " + prefix) + channel_url,
        "workPrefix": "- " + prefix,
        "detailParagraph": "\n".join(lines),
        "durationLabel": "- Thời lượng mỗi phiên: ",
        "durationDisplay": duration or "theo booking được duyệt",
        "minProductLabel": _MIN_LABEL,
        "minProductDisplay": "01 sản phẩm",
        "resultUsageClause": "- Bên A được quyền sử dụng kết quả buổi phát trực tiếp để phục vụ cho các "
                             "chiến dịch truyền thông và quảng cáo trong phạm vi Hợp đồng này;",
        "productInfoClause": "- Cung cấp hoặc chuẩn bị đầy đủ thông tin về sản phẩm được giới thiệu "
                             "trong buổi phát trực tiếp.",
        "bbntWorkDescription": "Quảng bá sản phẩm " + brand + " thông qua phát trực tiếp trên nền tảng "
                               + platform + " tại " + channel_url + ".",
        "bbntWorkDescriptionShort": "Quảng bá sản phẩm " + brand + " thông qua phát trực tiếp trên nền "
                                    "tảng " + tiktok_short + ".",
        "bbntPaymentDescription": "Dịch vụ Livestream quảng bá sản phẩm " + brand + " trên nền tảng "
                                  + platform + ".",
        "quantityHeader": "Số lượng buổi live thực tế",
    }


def _video(brand, channel_url, dates, quantity, duration, custom):
    date_lines = ", ".join(_d(d) for d in dates)
    lines = ["- Số lượng: " + quantity_text(quantity, VIDEO) + ".",
             "- Thời gian đăng tải dự kiến: " + date_lines + ".",
             ("- Thời lượng video: " + duration + "/video.") if duration
             else "- Thời lượng video: theo brief được Bên A duyệt.",
             _MIN_PRODUCT]
    if custom:
        lines.append("- Yêu cầu bổ sung: " + custom)
    prefix = ("- Bên B sẽ đăng tải video nhằm giới thiệu, quảng bá sản phẩm " + brand
              + " trên nền tảng TikTok, cụ thể là kênh TikTok của Bên B: ")
    return {
        "titleShort": "video", "serviceDisplay": "Video", "serviceAction": "đăng tải video",
        "objectParagraph": _object("đăng tải video", "TikTok"),
        "workParagraph": prefix + channel_url, "workPrefix": prefix,
        "detailParagraph": "\n".join(lines),
        "durationLabel": "- Thời lượng video tối thiểu: ",
        "durationDisplay": duration or "theo brief được Bên A duyệt",
        "minProductLabel": _MIN_LABEL, "minProductDisplay": "01 sản phẩm",
        "resultUsageClause": "- Bên A được quyền sử dụng kết quả video do Bên B thực hiện để phục vụ cho các "
                             "chiến dịch truyền thông và quảng cáo trong phạm vi Hợp đồng này kể từ ngày "
                             "Bên B bàn giao sản phẩm cho Bên A;",
        "productInfoClause": "- Cung cấp hoặc chuẩn bị đầy đủ thông tin về sản phẩm được giới thiệu trong video.",
        "bbntWorkDescription": "Quảng bá sản phẩm " + brand + " thông qua đăng tải video trên nền tảng "
                               "TikTok tại " + channel_url + ".",
        "bbntWorkDescriptionShort": "Quảng bá sản phẩm " + brand + " thông qua đăng tải video trên nền "
                                    "tảng Tik Tok.",
        "bbntPaymentDescription": "Dịch vụ đăng tải video quảng bá sản phẩm " + brand + " trên nền tảng TikTok.",
        "quantityHeader": "Số lượng video thực tế",
    }


def _hybrid(brand, channel_url, dates, duration, custom):
    date_lines = ", ".join(_d(d) for d in dates)
    prefix = ("- Bên B sẽ livestream và/hoặc đăng tải video nhằm giới thiệu, quảng bá sản phẩm " + brand
              + " trên kênh TikTok ")
    return {
        "titleShort": "Livestream và video", "serviceDisplay": "Livestream và Video",
        "serviceAction": "livestream và đăng tải video",
        "objectParagraph": _object("livestream và đăng tải video", "TikTok"),
        "workParagraph": prefix + channel_url + ".", "workPrefix": prefix,
        "detailParagraph": custom or ("- Thời gian thực hiện dự kiến: " + date_lines
                                      + ((". Thời lượng: " + duration + ".") if duration else ".")),
        "durationLabel": "- Thời lượng thực hiện: ",
        "durationDisplay": duration or "theo booking được duyệt",
        "minProductLabel": _MIN_LABEL, "minProductDisplay": "01 sản phẩm",
        "resultUsageClause": "- Bên A được quyền sử dụng kết quả công việc do Bên B thực hiện để phục vụ cho "
                             "các chiến dịch truyền thông và quảng cáo trong phạm vi Hợp đồng này;",
        "productInfoClause": "- Cung cấp hoặc chuẩn bị đầy đủ thông tin về sản phẩm được giới thiệu trong "
                             "livestream/video.",
        "bbntWorkDescription": "Quảng bá sản phẩm " + brand + " thông qua livestream và/hoặc video trên nền "
                               "tảng TikTok tại " + channel_url + ".",
        "bbntWorkDescriptionShort": "Quảng bá sản phẩm " + brand + " thông qua livestream và/hoặc video trên "
                                    "nền tảng Tik Tok.",
        "bbntPaymentDescription": "Dịch vụ livestream và video quảng bá sản phẩm " + brand + " trên nền tảng TikTok.",
        "quantityHeader": "Khối lượng thực tế",
    }


def work_texts(kind, brand, channel_url, dates, quantity, duration, custom, shopee):
    duration, custom = (duration or "").strip(), (custom or "").strip()
    if shopee:
        return _live(brand, channel_url, dates, quantity, duration, custom, True)
    if kind == VIDEO:
        return _video(brand, channel_url, dates, quantity, duration, custom)
    if kind == HYBRID:
        return _hybrid(brand, channel_url, dates, duration, custom)
    return _live(brand, channel_url, dates, quantity, duration, custom, False)


_AFFILIATE = ("Trong suốt thời gian livestream, Bên B có trách nhiệm gắn đúng đường dẫn mua hàng (Affiliate) "
              "do Bên A cung cấp và giới thiệu tối thiểu 01 sản phẩm của Bên A theo nội dung, kịch bản hoặc "
              "hướng dẫn đã được Bên A phê duyệt.")


def advance_texts(kind, brand, channel_url, dates, quantity, duration, custom):
    """Cac dong cua mau HDDV CO COC. Dong rong -> xoa ca doan khi dien (xem CONDITIONAL_LINES)."""
    q = int(quantity or 1)
    count = "%02d" % q if q < 10 else str(q)
    all_dates = ", ".join(_d(d) for d in dates)
    dur = (duration or "").strip() or "theo booking được Hai Bên thống nhất"
    base = {"customDetailLine": (custom or "").strip(), "packageQuantity": count + " gói",
            "videoDateLine": "", "videoChannelLine": "", "videoDurationLine": "",
            "liveSummaryLine": "", "liveDateLine": "", "liveDurationLine": "", "affiliateClause": ""}
    if kind == VIDEO:
        base.update({
            "subtitle": "(V/v: Cung cấp dịch vụ booking video)",
            "workParagraph": "Bên B sẽ đăng tải video nhằm giới thiệu, quảng bá sản phẩm " + brand
                             + " trên nền tảng TikTok theo yêu cầu của Bên A.",
            "detailIntro": "Đăng tải " + count + " video giới thiệu sản phẩm. Chi tiết:",
            "videoDateLine": "Ngày đăng tải: " + all_dates + " (dự kiến)",
            "videoChannelLine": "Link kênh đăng tải: " + channel_url,
            "videoDurationLine": "Thời lượng tối thiểu của video: " + dur})
    elif kind == HYBRID:
        base.update({
            "subtitle": "(V/v: Cung cấp dịch vụ booking video và livestream)",
            "workParagraph": "Bên B sẽ đăng tải video và phát trực tiếp (livestream) nhằm giới thiệu, quảng bá "
                             "sản phẩm " + brand + " của Bên A trên nền tảng TikTok.",
            "detailIntro": "Đăng tải video giới thiệu sản phẩm và thực hiện phiên Livestream. Chi tiết:",
            "videoDateLine": "Ngày đăng tải video: " + _d(dates[0]) + " (dự kiến)",
            "videoChannelLine": "Link kênh đăng tải: " + channel_url,
            "videoDurationLine": "Thời lượng tối thiểu của video: " + dur,
            "liveSummaryLine": "Thực hiện phiên Livestream. Chi tiết:",
            "liveDateLine": "Ngày thực hiện: " + _d(dates[-1]),
            "liveDurationLine": "Thời lượng tối thiểu của phiên livestream: " + dur + ".",
            "affiliateClause": _AFFILIATE})
    else:
        base.update({
            "subtitle": "(V/v: Cung cấp dịch vụ booking livestream)",
            "workParagraph": "Bên B sẽ phát trực tiếp (livestream) nhằm giới thiệu, quảng bá sản phẩm " + brand
                             + " của Bên A và gắn link mua hàng (Affiliate) trên nền tảng TikTok, cụ thể là kênh "
                             "TikTok của Bên B: " + channel_url,
            "detailIntro": "Thực hiện " + count + " phiên Livestream. Chi tiết:",
            "liveDateLine": "Ngày thực hiện: " + all_dates,
            "liveDurationLine": "Thời lượng tối thiểu của mỗi phiên livestream: " + dur + ".",
            "affiliateClause": _AFFILIATE})
    return base
