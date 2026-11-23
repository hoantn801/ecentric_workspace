// Copyright (c) 2026, eCentric and contributors
// Form loi: 3 nut duyet (Manager) + ghi chu; xem clip minh chung. Diem phien do ERP cham lai sau khi duyet.
const HQ_API = "ecentric_workspace.host_qc.api.v1.";
const HQ_REVIEWS = [["Valid Violation", "Đúng lỗi", "btn-danger"], ["False Positive", "Báo nhầm", "btn-success"],
	["Need Review", "Cần xem lại", "btn-default"]];

frappe.ui.form.on("Host QC Violation", {
	refresh(frm) {
		hq_render_review(frm);
		hq_render_clip(frm);
	},
});

function hq_render_review(frm) {
	const $w = frm.fields_dict.review_html && frm.fields_dict.review_html.$wrapper;
	if (!$w) return;
	const can = frappe.user.has_role("Host QC Manager") || frappe.user.has_role("System Manager");
	const esc = frappe.utils.escape_html;
	const quote = esc(frm.doc.quote || "").replace(/«/g, "<mark>«").replace(/»/g, "»</mark>");
	$w.html(`<div class="small text-muted">${__("Câu nói")}:</div><div style="margin-bottom:8px">${quote || "-"}</div>
		${can ? `<textarea class="form-control hq-note" rows="2" placeholder="${__("Ghi chú duyệt (tuỳ chọn)")}"></textarea>
		<div style="margin-top:6px">${HQ_REVIEWS.map(([v, label, cls]) =>
			`<button class="btn btn-sm ${cls} hq-review" data-v="${v}" style="margin-right:6px">${__(label)}</button>`).join("")}</div>` : ""}`);
	$w.find(".hq-review").on("click", (ev) => hq_review(frm, $(ev.currentTarget).data("v"), $w.find(".hq-note").val()));
}

async function hq_review(frm, review, note) {
	try {
		const r = await frappe.call({ method: HQ_API + "review_violation", freeze: true,
			args: { violation_id: frm.doc.name, review, note: note || "" } });
		const env = r.message || {};
		if (!env.success) throw new Error(env.message);
		frappe.show_alert({ message: `${env.message} ${__("Điểm phiên")}: ${env.data.total_score} (${env.data.status_color})`, indicator: "green" });
		frm.reload_doc();
	} catch (e) {
		frappe.msgprint({ title: __("Không lưu được"), message: frappe.utils.escape_html(e.message || String(e)), indicator: "red" });
	}
}

function hq_render_clip(frm) {
	const $w = frm.fields_dict.clip_html && frm.fields_dict.clip_html.$wrapper;
	if (!$w) return;
	const src = frm.doc.clip_local_file || "";
	const web = frm.doc.clip_web_url || "";
	if (src) {
		$w.html(`<video controls preload="metadata" style="max-width:100%;max-height:360px" src="${encodeURI(src)}"></video>`);
	} else if (web) {
		$w.html(`<a href="${encodeURI(web)}" target="_blank" rel="noopener">${__("Mở clip trên SharePoint")}</a>`);
	} else {
		$w.html(`<span class="text-muted">${__("Chưa có clip")} (${frappe.utils.escape_html(frm.doc.clip_status || "none")})</span>`);
	}
}
