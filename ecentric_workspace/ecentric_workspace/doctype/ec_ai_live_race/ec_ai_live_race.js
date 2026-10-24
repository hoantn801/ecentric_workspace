// Copyright (c) 2026, eCentric and contributors
// EC AI Live Race: ket qua do app chot - chi sua trang thai trao giai + ghi chu. Nut mo trang Dua vit tren /ai-video.
frappe.ui.form.on("EC AI Live Race", {
	refresh(frm) {
		frm.add_custom_button(__("Mở trang Đua vịt"), () => {
			window.open("/ai-video#/races?live=" + encodeURIComponent(frm.doc.live || ""), "_blank");
		});
		if (frm.doc.live) {
			frm.add_custom_button(__("Giải thưởng của phiên"), () => {
				window.open("/ai-video#/live/" + encodeURIComponent(frm.doc.live) + "/giai", "_blank");
			});
		}
	},
});
