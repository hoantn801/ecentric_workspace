# Copyright (c) 2026, eCentric and contributors
"""Mau khao sat ca nhan TAM (Hoan gui cau hoi sau - 22/11/2026).

3 cau cho moi moc thu viec / thuc tap + 1 mau khao sat nghi viec, danh dau `mau_tam = 1`.
HR sua cau hoi trong trinh soan (/khao-sat/soan) - nguoi giu role trong `quan_ly_roles` quan ly
duoc mau. Cau co id trong `lm_hidden_items` thuoc nhom "chi HR · C&B" (ve quan ly, moi truong):
quan ly truc tiep KHONG thay cau tra loi.

CHI TAO KHI CHUA CO mau cung `ma_mau` - khong bao gio ghi de cau hoi HR da sua.
"""
import json

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.domain import schema


def _opt(*labels):
    return [{"id": "o%d" % i, "label": lb} for i, lb in enumerate(labels, 1)]


def _scale(qid, title):
    return {"id": qid, "kind": "question", "type": "scale", "required": True, "title": title,
            "scale_min": 1, "scale_max": 5, "min_label": "Rất thấp", "max_label": "Rất cao"}


def _para(qid, title, required=False):
    return {"id": qid, "kind": "question", "type": "paragraph", "required": required,
            "title": title}


def _single(qid, title, *labels):
    return {"id": qid, "kind": "question", "type": "single", "required": True, "title": title,
            "options": _opt(*labels)}


def _moc(ma, ten, loai, so, items, hidden):
    return {"ma_mau": ma, "title": "Khảo sát %s - mốc %s%s" % (loai, so, ten),
            "description": ("Khảo sát định kỳ trong thời gian %s. Câu trả lời giúp công ty hỗ trợ "
                            "bạn tốt hơn. Câu đánh dấu \"chỉ HR\" quản lý trực tiếp không xem được."
                            % loai),
            "items": items, "hidden": hidden, "managers": C.MANAGER_ROLES_MOC}


def templates():
    tv, tt = "thử việc", "thực tập"
    out = []
    for loai, ma, ngay in ((tv, "KS_THU_VIEC", (7, 30, 45)), (tt, "KS_THUC_TAP", (30, 60, 75))):
        out.append(_moc("%s_1" % ma, " (ngày %d)" % ngay[0], loai, 1, [
            _scale("q1", "Bạn đã được hướng dẫn công việc và công cụ làm việc đầy đủ chưa?"),
            _single("q2", "Khối lượng công việc so với kỳ vọng của bạn", "Ít hơn", "Phù hợp", "Nhiều hơn"),
            _para("q3", "Điều bạn muốn chia sẻ riêng với HR (về quản lý, môi trường làm việc) - chỉ HR xem"),
        ], ["q3"]))
        out.append(_moc("%s_2" % ma, " (ngày %d)" % ngay[1], loai, 2, [
            _scale("q1", "Mục tiêu / KPI %s của bạn rõ ràng ở mức nào?" % loai),
            _para("q2", "Khó khăn lớn nhất của bạn trong công việc hiện tại là gì?"),
            _scale("q3", "Mức độ hỗ trợ bạn nhận được từ quản lý trực tiếp - chỉ HR xem"),
        ], ["q3"]))
        out.append(_moc("%s_3" % ma, " (trước khi đánh giá)", loai, 3, [
            _scale("q1", "Bạn tự tin hoàn thành mục tiêu %s ở mức nào?" % loai),
            _para("q2", "Bạn cần thêm đào tạo / hỗ trợ gì?"),
            _single("q3", "Bạn có muốn tiếp tục gắn bó sau %s không? - chỉ HR xem" % loai,
                    "Có", "Đang cân nhắc", "Không"),
        ], ["q3"]))
    out.append({"ma_mau": "NGHI_VIEC", "title": "Khảo sát nghỉ việc",
                "description": "Không bắt buộc. Chỉ HR xem câu trả lời - quản lý trực tiếp không xem.",
                "items": [
                    _single("q1", "Lý do chính bạn quyết định nghỉ việc", "Thu nhập / phúc lợi",
                            "Cơ hội phát triển", "Quản lý / đồng nghiệp", "Khối lượng công việc",
                            "Lý do cá nhân / gia đình", "Khác"),
                    _scale("q2", "Mức độ hài lòng chung của bạn khi làm việc tại công ty"),
                    _para("q3", "Góp ý để công ty tốt hơn"),
                ], "hidden": ["q1", "q2", "q3"], "managers": ("HR",)})
    return out


def dam_bao_mau_tam(repo):
    """Tao mau con thieu. Tra ve danh sach ma_mau vua tao."""
    made = []
    now = repo.now()
    for t in templates():
        if repo.survey_by_ma_mau(t["ma_mau"]):
            continue
        form = schema.normalize({"v": 1, "items": t["items"]})
        repo.insert_survey({
            "title": t["title"], "description": t["description"], "status": C.STATUS_OPEN,
            "published_at": now, "anonymous": 0, "allow_edit": 0, "show_progress": 1,
            "notify_on_publish": 0, "audience_mode": C.AUDIENCE_CUSTOM,
            "reward_mode": C.REWARD_NONE, "form_json": json.dumps(form, ensure_ascii=False),
            "survey_kind": C.KIND_PERSONAL, "ma_mau": t["ma_mau"], "mau_tam": 1,
            "quan_ly_roles": "\n".join(t["managers"]),
            "lm_hidden_items": json.dumps(t["hidden"]),
            "confirmation_message": "Cảm ơn bạn đã trả lời khảo sát!"})
        made.append(t["ma_mau"])
    return made
