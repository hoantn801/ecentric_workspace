# Copyright (c) 2026, eCentric and contributors
"""EC Web Push Subscription: mot ban ghi cho MOI trinh duyet/thiet bi da cap quyen.

Mot nguoi co the co nhieu ban ghi (laptop + dien thoai + PWA tren man hinh chinh) va
do la dung - web push gan voi TRINH DUYET chu khong gan voi tai khoan.

KHONG co quyen cho role "All": trong ban ghi nay co `auth` + `p256dh`, la khoa ma hoa
cua rieng endpoint do. Moi thao tac cua nguoi dung di qua API da whitelist
(notification_center.api.webpush_*), o do luon ep `user = frappe.session.user`.
"""
import hashlib

import frappe
from frappe.model.document import Document


def endpoint_hash(endpoint):
    return hashlib.sha256((endpoint or "").encode("utf-8")).hexdigest()[:32]


class ECWebPushSubscription(Document):
    def validate(self):
        # Chuan hoa: endpoint la khoa dinh danh that su, nen cat khoang trang.
        self.endpoint = (self.endpoint or "").strip()
