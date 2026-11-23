// Copyright (c) 2026, eCentric and contributors
// "Bang huong dan" Host QC: chi doc cho moi role Host QC; nut "Chinh" (mo form Host QC Rule) chi Manager thay.
// Du lieu tu api.v1.guide - khong tinh toan gi o day.
const HQ_API = "ecentric_workspace.host_qc.api.v1.";

frappe.pages["host-qc-guide"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Bảng hướng dẫn Host QC"), single_column: true });
	const $body = $('<div class="hq-guide" style="padding:8px 0"></div>').appendTo(page.body);
	page.set_secondary_action(__("Tải lại"), () => load(), "refresh");
	load();

	async function load() {
		$body.html(`<div class="text-muted" style="padding:24px">${__("Đang tải…")}</div>`);
		try {
			const r = await frappe.call({ method: HQ_API + "guide", type: "GET" });
			const env = r.message || {};
			if (!env.success) throw new Error(env.message || __("Không tải được bảng hướng dẫn."));
			render(env.data);
		} catch (e) {
			$body.html(`<div class="text-danger" style="padding:24px">${frappe.utils.escape_html(e.message || String(e))}</div>`);
			frappe.show_alert({ message: __("Không tải được bảng hướng dẫn"), indicator: "red" });
		}
	}

	function render(d) {
		const esc = frappe.utils.escape_html;
		const groups = d.groups || {};
		const head = `<p class="text-muted">${__("Phiên bản luật")}: <b>${esc(d.version || "-")}</b> · ${__("Trừ điểm")}:
			Minor ${esc(String(d.deduction?.Minor ?? ""))} / Major ${esc(String(d.deduction?.Major ?? ""))} /
			Critical ${esc(String(d.deduction?.Critical ?? ""))}</p>`;
		const rows = (d.rows || []).map((r) => {
			const g = groups[r.group];
			const params = (r.params || []).map((p) =>
				`<div><code>${esc(p.key)}</code> = <b>${esc(String(p.value ?? ""))}</b> ${esc(p.unit || "")}
				<span class="text-muted">${esc(p.description || "")}</span></div>`).join("");
			const edit = d.can_edit
				? `<a class="btn btn-xs btn-default" href="/app/host-qc-rule/${encodeURIComponent(r.code)}">${__("Chỉnh")}</a>` : "";
			const tags = [r.enabled ? "" : `<span class="indicator-pill gray">${__("Tắt")}</span>`,
				r.severity ? `<span class="indicator-pill orange">${esc(r.severity)}</span>` : "",
				r.default_review ? `<span class="indicator-pill blue">${esc(r.default_review)}</span>` : "",
				r.count_after_valid ? `<span class="indicator-pill purple">${__("Chỉ tính khi duyệt Valid")}</span>` : "",
				r.experimental ? `<span class="indicator-pill yellow">${__("Thử nghiệm")}</span>` : ""].join(" ");
			return `<tr>
				<td><b>${esc(r.code)}</b><div class="text-muted small">${esc(g ? `${g.name} (${g.max})` : __("Chung"))}</div></td>
				<td><b>${esc(r.title || "")}</b> ${tags}<div class="small">${esc(r.how || "")}</div></td>
				<td class="small">${params}</td>
				<td class="small">${esc(r.default_text || "")}</td>
				<td class="small">${esc(r.tune_tip || "")}</td>
				<td>${edit}</td></tr>`;
		}).join("");
		$body.html(`${head}<div class="table-responsive"><table class="table table-bordered table-sm">
			<thead><tr><th>${__("Mã")}</th><th>${__("Lỗi / cách phát hiện")}</th><th>${__("Ngưỡng đang dùng")}</th>
			<th>${__("Mặc định")}</th><th>${__("Mẹo chỉnh")}</th><th></th></tr></thead>
			<tbody>${rows || `<tr><td colspan="6" class="text-muted">${__("Chưa có luật.")}</td></tr>`}</tbody></table></div>`);
	}
};
