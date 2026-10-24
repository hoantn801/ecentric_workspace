// Copyright (c) 2026, eCentric and contributors
// Phien live: nut mo trang Phien live / Lich live tren /ai-video (sua lich nhanh bang keo tha).
frappe.ui.form.on("EC AI Live Session", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Mở chi tiết phiên"), () => window.open("/ai-video#/live/" + encodeURIComponent(frm.doc.name), "_blank"));
		}
		frm.add_custom_button(__("Lịch live (kéo thả)"), () => window.open("/ai-video#/schedule", "_blank"));
	},
});
