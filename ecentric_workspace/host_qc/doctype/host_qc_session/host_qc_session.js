// Copyright (c) 2026, eCentric and contributors
// Form phien QC: o "Mic" cua host lay tu "Micro tren may" cua may da chon (ERP kiem lai khi luu).
const HQ_API = "ecentric_workspace.host_qc.api.v1.";

frappe.ui.form.on("Host QC Session", {
	refresh(frm) { hq_load_mics(frm); },
	machine(frm) { hq_load_mics(frm); },
});

async function hq_load_mics(frm) {
	const grid = frm.fields_dict.hosts && frm.fields_dict.hosts.grid;
	if (!grid) return;
	let names = [];
	if (frm.doc.machine) {
		try {
			const r = await frappe.call({ method: HQ_API + "machine_mics", type: "GET", args: { machine_id: frm.doc.machine } });
			const env = r.message || {};
			if (!env.success) throw new Error(env.message);
			names = (env.data || []).map((m) => m.device_name);
		} catch (e) {
			frappe.show_alert({ message: __("Không tải được mic của máy: ") + (e.message || ""), indicator: "orange" });
		}
	}
	(frm.doc.hosts || []).forEach((h) => { if (h.mic_device && !names.includes(h.mic_device)) names.push(h.mic_device); });
	grid.update_docfield_property("mic_device", "options", [""].concat(names));
	grid.refresh();
}
