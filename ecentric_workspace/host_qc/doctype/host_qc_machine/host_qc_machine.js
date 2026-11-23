// Copyright (c) 2026, eCentric and contributors
// Form may studio: nut "Tao token moi" (Manager) - token chi hien 1 lan; danh dau mic lau khong thay.
const HQ_API = "ecentric_workspace.host_qc.api.v1.";

frappe.ui.form.on("Host QC Machine", {
	refresh(frm) {
		if (!frm.is_new() && (frappe.user.has_role("Host QC Manager") || frappe.user.has_role("System Manager"))) {
			frm.add_custom_button(__("Tạo token mới"), () => hq_issue_token(frm));
		}
		if (!frm.is_new()) hq_show_stale_mics(frm);
	},
});

function hq_issue_token(frm) {
	frappe.confirm(__("Token cũ của máy sẽ hết hiệu lực ngay. Tạo token mới?"), async () => {
		try {
			const r = await frappe.call({ method: HQ_API + "issue_machine_token", args: { machine_id: frm.doc.machine_id },
				freeze: true, freeze_message: __("Đang tạo token…") });
			const env = r.message || {};
			if (!env.success) throw new Error(env.message);
			const full = `${env.data.machine_id}.${env.data.token}`;
			const d = new frappe.ui.Dialog({
				title: __("Token máy {0}", [env.data.machine_id]),
				fields: [{ fieldtype: "HTML", fieldname: "info" }, { fieldtype: "Code", fieldname: "token", read_only: 1 }],
				primary_action_label: __("Sao chép"),
				primary_action: () => frappe.utils.copy_to_clipboard(full),
			});
			d.fields_dict.info.$wrapper.html(`<p class="text-danger">${frappe.utils.escape_html(env.message || "")}</p>`);
			d.set_value("token", full);
			d.show();
			frm.reload_doc();
		} catch (e) {
			frappe.msgprint({ title: __("Không tạo được token"), message: frappe.utils.escape_html(e.message || String(e)), indicator: "red" });
		}
	});
}

async function hq_show_stale_mics(frm) {
	try {
		const r = await frappe.call({ method: HQ_API + "machine_mics", type: "GET", args: { machine_id: frm.doc.name } });
		const stale = ((r.message || {}).data || []).filter((m) => m.stale);
		if (stale.length) {
			frm.set_intro(__("Mic không thấy gần đây: ") + stale.map((m) =>
				`${frappe.utils.escape_html(m.device_name)} (${__("không thấy từ")} ${m.last_seen})`).join(", "), "orange");
		}
	} catch (e) {
		frappe.show_alert({ message: __("Không tải được danh sách mic"), indicator: "orange" });
	}
}
