# Copyright (c) 2026, eCentric and contributors
"""Nhat ky AI dien ho. CHI GHI MOT LAN - khong sua, khong ai tu tao qua giao dien.

`write`/`create` = 0 cho moi role: bang nay vua la HAN MUC theo ngay (`used_today` dem hang
o day) vua la du lieu DO cua giai doan 3. Mot bang ma nguoi dung sua duoc thi khong dung
duoc cho ca hai viec. Server ghi bang `ignore_permissions=True`.

Hai truong duoc phep cap nhat sau khi tao, va chi qua service:
  - `handed_off_at`  : linh vat ban giao sang form, DUNG MOT LAN
  - `business_doc` / `fields_edited_after` : sau khi nguoi dung luu nhap
"""
import frappe
from frappe import _
from frappe.model.document import Document


class ECAIFormfillLog(Document):
    def on_update(self):
        """Chan sua noi dung da ghi. Cho phep dung mot so truong 'sau khi dien' vi chung
        duoc dat sau, khong phai sua lai lich su."""
        if self.is_new():
            return
        mutable = {"handed_off_at", "business_doc", "fields_edited_after", "modified",
                   "modified_by"}
        before = self.get_doc_before_save()
        if not before:
            return
        changed = {f.fieldname for f in self.meta.fields
                   if self.get(f.fieldname) != before.get(f.fieldname)}
        illegal = changed - mutable
        if illegal:
            frappe.throw(_("Nhật ký AI điền hộ chỉ ghi một lần; không sửa được: %s")
                         % ", ".join(sorted(illegal)))
