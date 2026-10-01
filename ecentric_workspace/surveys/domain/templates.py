# Copyright (c) 2026, eCentric and contributors
"""Mau khoi dau cho nut "Tạo khảo sát" - de dot khao sat hang thang khong phai go lai tu dau.
Moi mau la (key, nhan, mo ta, form, cai dat). id trong form chi can duy nhat trong mau;
schema.normalize se giu nguyen."""


def _opt(*labels):
    return [{"id": "o%d" % i, "label": lb} for i, lb in enumerate(labels, 1)]


TEMPLATES = [
    {
        "key": "blank",
        "label": "Khảo sát trống",
        "description": "Bắt đầu từ một trang trắng.",
        "title": "Khảo sát không tên",
        "form": {"v": 1, "items": [
            {"id": "q1", "kind": "question", "type": "single", "title": "Câu hỏi không tên",
             "options": _opt("Lựa chọn 1")},
        ]},
        "settings": {},
    },
    {
        "key": "monthly_pulse",
        "label": "Nhịp đập tháng (eNPS)",
        "description": "Mức độ hài lòng, NPS 0–10 và góp ý - dùng cho đợt khảo sát hằng tháng.",
        "title": "Khảo sát nhịp đập tháng",
        "form": {"v": 1, "items": [
            {"id": "q1", "kind": "question", "type": "scale", "required": True,
             "title": "Bạn sẵn sàng giới thiệu eCentric là nơi đáng làm việc cho bạn bè ở mức nào?",
             "scale_min": 0, "scale_max": 10, "min_label": "Không bao giờ", "max_label": "Chắc chắn"},
            {"id": "q2", "kind": "question", "type": "grid_single", "required": True,
             "title": "Tháng này bạn thấy thế nào về...",
             "rows": [{"id": "r1", "label": "Khối lượng công việc"},
                      {"id": "r2", "label": "Sự hỗ trợ từ quản lý"},
                      {"id": "r3", "label": "Phối hợp giữa các phòng"},
                      {"id": "r4", "label": "Công cụ / hệ thống làm việc"}],
             "cols": [{"id": "c1", "label": "Chưa tốt"}, {"id": "c2", "label": "Bình thường"},
                      {"id": "c3", "label": "Tốt"}, {"id": "c4", "label": "Rất tốt"}],
             "require_each_row": True},
            {"id": "q3", "kind": "question", "type": "paragraph",
             "title": "Điều bạn muốn công ty cải thiện ngay trong tháng tới?"},
        ]},
        "settings": {"anonymous": 1, "reward_mode": "wheel"},
    },
    {
        "key": "event_signup",
        "label": "Đăng ký sự kiện",
        "description": "Xác nhận tham gia, chọn suất ăn, size áo, ghi chú.",
        "title": "Đăng ký tham gia sự kiện",
        "form": {"v": 1, "items": [
            {"id": "q1", "kind": "question", "type": "single", "required": True, "branch": True,
             "title": "Bạn có tham gia không?",
             "options": [{"id": "o1", "label": "Có, mình tham gia", "goto": "s_yes"},
                         {"id": "o2", "label": "Không tham gia được", "goto": "s_no"}]},
            # Cau bat buoc cua nguoi THAM GIA phai nam o phan rieng: de chung phan voi cau re
            # nhanh thi nguoi "Khong tham gia" cung bi bat chon suat an.
            {"id": "s_yes", "kind": "section", "title": "Thông tin tham gia", "next": "__submit__"},
            {"id": "q2", "kind": "question", "type": "dropdown", "required": True,
             "title": "Suất ăn", "options": _opt("Thường", "Chay")},
            {"id": "q3", "kind": "question", "type": "single", "title": "Size áo",
             "options": _opt("S", "M", "L", "XL", "XXL")},
            {"id": "s_no", "kind": "section", "title": "Góp ý thêm", "next": "__submit__"},
            {"id": "q4", "kind": "question", "type": "paragraph", "title": "Ghi chú cho ban tổ chức"},
        ]},
        "settings": {},
    },
    {
        "key": "quiz",
        "label": "Bài kiểm tra",
        "description": "Câu hỏi có đáp án và điểm - kiểm tra sau đào tạo, quy trình mới.",
        "title": "Bài kiểm tra sau đào tạo",
        "form": {"v": 1, "items": [
            {"id": "q1", "kind": "question", "type": "single", "required": True, "points": 1,
             "title": "Câu hỏi 1", "options": _opt("Đáp án A", "Đáp án B", "Đáp án C"),
             "correct": ["o1"]},
            {"id": "q2", "kind": "question", "type": "multi", "required": True, "points": 2,
             "title": "Câu hỏi 2 (chọn tất cả đáp án đúng)",
             "options": _opt("Đáp án A", "Đáp án B", "Đáp án C"), "correct": ["o1", "o3"]},
        ]},
        "settings": {"is_quiz": 1, "show_score": 1},
    },
]


def get(key):
    for t in TEMPLATES:
        if t["key"] == key:
            return t
    return TEMPLATES[0]


def catalog():
    return [{"key": t["key"], "label": t["label"], "description": t["description"]}
            for t in TEMPLATES]
