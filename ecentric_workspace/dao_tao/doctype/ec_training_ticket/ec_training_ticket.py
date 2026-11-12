# Copyright (c) 2026, eCentric and contributors
"""EC Training Ticket - Vé quay số tuần (tối đa 3 vé / người / tuần, tính chung quiz + thực hành)

Khong co nghiep vu trong controller: DocType chi cap quyen System Manager, moi truy cap cua
nguoi dung di qua dao_tao/controllers/api.py -> application/* (kiem quyen o access.py)."""
from frappe.model.document import Document


class ECTrainingTicket(Document):
    pass
