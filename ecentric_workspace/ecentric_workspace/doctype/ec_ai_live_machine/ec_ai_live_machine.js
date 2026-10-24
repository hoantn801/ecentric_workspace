// Copyright (c) 2026, eCentric and contributors
// Nut cap token may phat: goi API, hien token 1 lan de dan vao app eCentric AI Live tren may do.
frappe.ui.form.on("EC AI Live Machine", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Tạo token mới"), () => {
			frappe.confirm(__("Token cũ của máy này sẽ ngừng dùng được. Tạo token mới?"), async () => {
				try {
					const r = await frappe.call({
						method: "ecentric_workspace.ai_live.api.register_machine",
						args: { code: frm.doc.machine_code, new_token: 1 },
						freeze: true,
					});
					const m = r.message || {};
					if (!m.success) { frappe.msgprint(m.message || __("Không tạo được token.")); return; }
					const d = new frappe.ui.Dialog({
						title: __("Token máy {0}", [frm.doc.machine_code]),
						fields: [
							{ fieldtype: "HTML", options: `<p>${__("Dán token này vào app eCentric AI Live trên máy, mục Cài đặt chung. Token chỉ hiện một lần.")}</p>` },
							{ fieldname: "token", fieldtype: "Data", label: __("Token"), read_only: 1, default: m.data.token },
						],
						primary_action_label: __("Đóng"),
						primary_action() { d.hide(); frm.reload_doc(); },
					});
					d.show();
				} catch (e) {
					frappe.show_alert({ message: __("Lỗi mạng, thử lại."), indicator: "red" });
				}
			});
		});
	},
});
