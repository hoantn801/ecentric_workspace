// Copyright (c) 2026, eCentric and contributors
// Phien live: nut mo trang Phien live / Lich live tren /ai-live (18/11: trang da tach khoi /ai-video tu 25/10).
frappe.ui.form.on("EC AI Live Session", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Mở chi tiết phiên"), () => window.open("/ai-live#/live/" + encodeURIComponent(frm.doc.name), "_blank"));
		}
		frm.add_custom_button(__("Lịch live (kéo thả)"), () => window.open("/ai-live#/schedule", "_blank"));
	},
});
