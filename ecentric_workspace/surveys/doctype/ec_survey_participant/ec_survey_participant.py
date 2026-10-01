# Copyright (c) 2026, eCentric and contributors
"""EC Survey Participant - Ai đã nộp khảo sát nào + phần thưởng. Tách khỏi phiếu trả lời để khảo sát ẩn danh vẫn chống nộp trùng và trao quà được. name = khảo sát + băm email (chống trùng ở tầng khoá chính).

Khong co nghiep vu trong controller: DocType chi cap quyen System Manager, moi truy cap
cua nguoi dung di qua surveys/controllers/api.py -> application/* (kiem quyen o do)."""
from frappe.model.document import Document


class ECSurveyParticipant(Document):
    pass
