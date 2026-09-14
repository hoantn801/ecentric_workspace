# Copyright (c) 2026, eCentric and contributors
"""Noi mot tep trong Frappe voi ban song cua no tren SharePoint.

KHONG dat cac truong nay thanh Custom Field tren DocType `File`: File la bang dung chung cho
MOI dinh kem trong he thong, them cot vao do la doi hinh dang du lieu cua ca nhung module
khong lien quan. Mot bang rieng thi pham vi ro rang va xoa di cung khong anh huong ai."""
from frappe.model.document import Document


class ECSharePointFileLink(Document):
    pass
