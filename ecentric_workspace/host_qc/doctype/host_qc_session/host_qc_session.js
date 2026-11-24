// Copyright (c) 2026, eCentric and contributors
// Form phien QC: o "Mic" cua host lay tu "Micro tren may" cua may da chon - hoac cua may dang khai phong live
// neu chua chon may (ERP kiem lai khi luu).
const HQ_API = "ecentric_workspace.host_qc.api.v1.";

frappe.ui.form.on("Host QC Session", {
	refresh(frm) { hq_load_mics(frm); },
	machine(frm) { hq_load_mics(frm); },
	live_room(frm) { hq_load_mics(frm); },
});

async function hq_load_mics(frm) {
	const grid = frm.fields_dict.hosts && frm.fields_dict.hosts.grid;
	if (!grid) return;
	let names = [];
	if (frm.doc.machine || frm.doc.live_room) {
		try {
			const r = await frappe.call({ method: HQ_API + "machine_mics", type: "GET",
				args: { machine_id: frm.doc.machine || "", room_id: frm.doc.live_room || "" } });
			const env = r.message || {};
			if (!env.success) throw new Error(env.message);
			names = (env.data || []).map((m) => m.device_name);
		} catch (e) {
			frappe.show_alert({ message: __("Không tải được mic của máy: ") + (e.message || ""), indicator: "orange" });
		}
	}
	if (frm.doc.no_schedule) {
		frm.set_intro(__("Live chưa có lịch: OBS phát khi ERP chưa có lịch cho phòng này."), "orange");
	}
	(frm.doc.hosts || []).forEach((h) => { if (h.mic_device && !names.includes(h.mic_device)) names.push(h.mic_device); });
	grid.update_docfield_property("mic_device", "options", [""].concat(names));
	grid.refresh();
}
