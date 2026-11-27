// Copyright (c) 2026, eCentric and contributors
// ec_ts_ops.js -- cac hop thoai THAO TAC dung chung (chi giao dien, goi API; server quyet dinh):
// chuyen trang thai, bao hong / gui sua, dong phieu sua, cap phat, nhap thiet bi.
// Moi ham tra Promise(ket qua | null khi huy). Can ec_ts_core.js nap truoc.
(function () {
  "use strict";
  if (window.ECTsOps) return;
  var T = window.ECTs, esc = T.esc;
  var NEED_EMP = { reserve: 1, assign: 1, transfer: 1 };
  var COND_OPTS = [["Good", "Tốt"], ["Partially Damaged", "Hỏng một phần"], ["Fully Damaged", "Hỏng toàn bộ"]];

  function condSelect(name, val) {
    return '<select class="ts-sel" name="' + name + '">' + COND_OPTS.map(function (c) {
      return '<option value="' + c[0] + '"' + (c[0] === val ? " selected" : "") + ">" + c[1] + "</option>";
    }).join("") + "</select>";
  }

  // Mot thao tac tu danh sach `actions` cua asset_detail.
  function transition(asset, action, label) {
    var needEmp = NEED_EMP[action];
    var p = needEmp ? T.pickEmployee(label + ": chọn nhân viên") : Promise.resolve("");
    return p.then(function (emp) {
      if (needEmp && !emp) return null;
      return new Promise(function (resolve) {
        var danger = action === "dispose" || action === "lost";
        T.modal(label + " · " + (asset.tag || asset.name),
          '<p class="ts-muted">' + T.assetLine(asset) + "</p>" +
          (action === "check_pass" || action === "check_fail" || action === "repair_done" ? '<label class="ts-lbl">Tình trạng' + condSelect("condition", action === "check_fail" ? "Fully Damaged" : "Good") + "</label>" : "") +
          '<label class="ts-lbl">Ghi chú<textarea class="ts-ta" name="note" maxlength="1000"></textarea></label>' +
          (action === "dispose" ? '<div class="ts-warn">Thanh lý là ghi giảm tài sản: dừng khấu hao từ tháng sau, không hoàn tác trên trang.</div>' : ""),
          '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ' + (danger ? "ts-danger" : "ts-primary") + '" data-ok>' + esc(label) + "</button>",
          function (el, close) {
            el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
            el.querySelector("[data-ok]").addEventListener("click", function (ev) {
              var btn = ev.currentTarget, cond = el.querySelector('[name="condition"]');
              T.busy(btn, true);
              T.post("transition", { asset: asset.name, action: action, employee: emp || "",
                note: el.querySelector('[name="note"]').value, condition: cond ? cond.value : "" })
                .then(function (r) { close(); T.toast("Đã " + label.toLowerCase() + "."); resolve(r); },
                  function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
            });
          });
      });
    });
  }

  // Bao hong / gui sua (open_repair). parts: danh sach bo phan goi y (tu specs).
  function openRepair(asset, parts, damageRequest) {
    return new Promise(function (resolve) {
      var partBtns = (parts && parts.length ? parts : ["Màn hình", "Bàn phím", "Pin", "RAM", "Ổ cứng", "Bản lề", "Cổng sạc"]).map(function (p) {
        return '<button type="button" class="ts-chip" data-part="' + esc(p) + '" aria-pressed="false">' + esc(p) + "</button>";
      }).join("");
      var today = new Date().toISOString().slice(0, 10);
      T.modal("Báo hỏng / gửi sửa · " + (asset.tag || asset.name),
        '<p class="ts-muted">' + T.assetLine(asset) + "</p>" +
        '<div><div class="ts-lbl" style="margin-bottom:6px">Mức hỏng</div><div class="ts-chips" data-lv>' +
        '<button type="button" class="ts-chip on" data-v="Partial">Hỏng một phần</button><button type="button" class="ts-chip" data-v="Full">Hỏng toàn bộ</button></div></div>' +
        '<div><div class="ts-lbl" style="margin-bottom:6px">Bộ phận hỏng</div><div class="ts-chips" data-parts>' + partBtns + "</div></div>" +
        '<div><div class="ts-lbl" style="margin-bottom:6px">Hướng xử lý</div><div class="ts-chips" data-mode>' +
        '<button type="button" class="ts-chip" data-v="Internal">Sửa nội bộ</button><button type="button" class="ts-chip on" data-v="Warranty">Gửi bảo hành</button><button type="button" class="ts-chip" data-v="External">Gửi sửa bên ngoài</button></div></div>' +
        '<div class="ts-form"><label class="ts-lbl">Nơi sửa<input class="ts-in" name="vendor" maxlength="140"></label>' +
        '<label class="ts-lbl">Chi phí dự kiến (₫)<input class="ts-in" name="expected_cost" inputmode="numeric" placeholder="0"></label>' +
        '<label class="ts-lbl">Ngày gửi<input class="ts-in" type="date" name="sent_date" value="' + today + '"></label>' +
        '<label class="ts-lbl">Dự kiến nhận lại<input class="ts-in" type="date" name="expected_return"></label>' +
        '<label class="ts-lbl ts-full">Mô tả<textarea class="ts-ta" name="description" maxlength="1000"></textarea></label></div>' +
        (asset.holder ? '<div class="ts-infobox"><label class="ts-ck"><input type="checkbox" data-loan> Cấp máy tạm cho người đang dùng (' + esc(asset.holder_name || asset.holder) + ")</label><div data-loanpick hidden></div></div>" : "") +
        '<div class="ts-note">Chi phí dự kiến trên ngưỡng duyệt thì phải tạo phiếu Báo hỏng / mất để duyệt chi phí trước khi gửi sửa.</div>',
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Tạo phiếu sửa chữa</button>',
        function (el, close) {
          var loanPick = null;
          function single(sel) {
            el.querySelector(sel).addEventListener("click", function (e) {
              var b = e.target.closest(".ts-chip"); if (!b) return;
              T.qsa(el.querySelector(sel), ".ts-chip").forEach(function (x) { x.classList.toggle("on", x === b); });
            });
          }
          single("[data-lv]"); single("[data-mode]");
          el.querySelector("[data-parts]").addEventListener("click", function (e) {
            var b = e.target.closest(".ts-chip"); if (!b) return;
            b.classList.toggle("on"); b.setAttribute("aria-pressed", b.classList.contains("on"));
          });
          var loan = el.querySelector("[data-loan]");
          if (loan) loan.addEventListener("change", function () {
            var host = el.querySelector("[data-loanpick]");
            host.hidden = !loan.checked;
            if (loan.checked && !loanPick) {
              host.innerHTML = T.skel(2);
              T.pickList("available").then(function (rows) {
                loanPick = T.picker(host, rows.filter(function (r) { return r.name !== asset.name && r.status === "Available"; }),
                  { label: function (r) { return (r.tag || r.name) + " · " + (r.asset_name || ""); }, sub: function (r) { return r.specs; } });
              }, function (e2) { host.innerHTML = T.errBox(e2); });
            }
          });
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget;
            var data = {
              damage_level: el.querySelector("[data-lv] .on").getAttribute("data-v"),
              repair_mode: el.querySelector("[data-mode] .on").getAttribute("data-v"),
              damaged_parts: T.qsa(el, "[data-parts] .on").map(function (b) { return b.getAttribute("data-part"); }),
              vendor: el.querySelector('[name="vendor"]').value, sent_date: el.querySelector('[name="sent_date"]').value,
              expected_return: el.querySelector('[name="expected_return"]').value,
              expected_cost: String(el.querySelector('[name="expected_cost"]').value || "").replace(/[^\d]/g, ""),
              description: el.querySelector('[name="description"]').value,
              loaner_asset: loan && loan.checked && loanPick ? loanPick.value() : "", damage_request: damageRequest || ""
            };
            T.busy(btn, true);
            T.post("open_repair", { asset: asset.name, data: data }).then(function (r) {
              if (r && r.need_approval) {
                T.busy(btn, false);
                el.querySelector(".ts-mb").insertAdjacentHTML("beforeend", '<div class="ts-warn">Chi phí dự kiến vượt ' + T.fmtMoney(r.threshold) +
                  ': cần tạo phiếu <a href="' + esc(r.route) + '" target="_blank" rel="noopener">Báo hỏng / mất</a> để duyệt trước.</div>');
                return;
              }
              close(); T.toast("Đã tạo phiếu sửa chữa."); resolve(r);
            }, function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
          });
        }, true);
    });
  }

  function closeRepair(rep) {
    return new Promise(function (resolve) {
      var today = new Date().toISOString().slice(0, 10);
      T.modal("Nhận lại sau sửa · " + (rep.tag || rep.asset),
        '<p class="ts-muted">' + esc(rep.asset_name || "") + " · " + esc(rep.mode_label || "") + (rep.vendor ? " · " + esc(rep.vendor) : "") + "</p>" +
        '<div><div class="ts-lbl" style="margin-bottom:6px">Kết quả</div><div class="ts-chips" data-res><button type="button" class="ts-chip on" data-v="Fixed">Sửa được</button><button type="button" class="ts-chip" data-v="Unfixable">Không sửa được</button></div></div>' +
        '<div class="ts-form"><label class="ts-lbl">Chi phí thật (₫)<input class="ts-in" name="actual_cost" inputmode="numeric" placeholder="0"></label>' +
        '<label class="ts-lbl">Ngày nhận lại<input class="ts-in" type="date" name="returned_date" value="' + today + '"></label>' +
        '<label class="ts-lbl">Sau khi nhận<select class="ts-sel" name="return_to"><option value="holder">Trả người đang dùng</option><option value="stock">Về kho (Sẵn sàng)</option></select></label>' +
        '<label class="ts-lbl">Tình trạng' + condSelect("condition", "Good") + "</label>" +
        '<label class="ts-lbl ts-full">Ghi chú<textarea class="ts-ta" name="note" maxlength="1000"></textarea></label></div>' +
        (rep.loaner_asset ? '<div class="ts-note">Máy tạm ' + esc(rep.loaner_asset) + " sẽ tự thu về khi trả máy cho người dùng.</div>" : ""),
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Đóng phiếu</button>',
        function (el, close) {
          el.querySelector("[data-res]").addEventListener("click", function (e) {
            var b = e.target.closest(".ts-chip"); if (!b) return;
            T.qsa(el.querySelector("[data-res]"), ".ts-chip").forEach(function (x) { x.classList.toggle("on", x === b); });
          });
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget;
            T.busy(btn, true);
            T.post("close_repair", { repair: rep.name, data: {
              result: el.querySelector("[data-res] .on").getAttribute("data-v"),
              actual_cost: String(el.querySelector('[name="actual_cost"]').value || "").replace(/[^\d]/g, ""),
              returned_date: el.querySelector('[name="returned_date"]').value,
              return_to: el.querySelector('[name="return_to"]').value, condition: el.querySelector('[name="condition"]').value,
              note: el.querySelector('[name="note"]').value } })
              .then(function (r) { close(); T.toast("Đã đóng phiếu sửa."); resolve(r); },
                function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
          });
        });
    });
  }

  // Cap phat / giu cho tu the "Cho cap phat". card: {source, source_type, employee, employee_name, need, has_employee}
  function allocate(card, checklist) {
    return new Promise(function (resolve) {
      var noEmp = card && card.source_type === "EC New Staff Preparation" && !card.has_employee;
      T.modal("Cấp phát thiết bị" + (card && card.employee_name ? " · " + card.employee_name : ""),
        (card ? '<div class="ts-infobox">' + esc(card.source_label || "") + " " + (card.route ? '<a href="' + esc(card.route) + '" target="_blank" rel="noopener">' + esc(card.source) + "</a>" : "") +
          (card.need ? "<br><span class=\"ts-muted\">Nhu cầu: " + esc(card.need) + "</span>" : "") + (card.due ? "<br><span class=\"ts-muted\">Hạn: " + T.fmtDate(card.due) + "</span>" : "") + "</div>" : "") +
        (card && card.employee ? "" : '<div><div class="ts-lbl" style="margin-bottom:6px">Nhân viên nhận</div><div data-emp>' + (noEmp ? '<div class="ts-warn">Nhân sự mới chưa có hồ sơ nhân viên: chỉ giữ chỗ được, cấp phát khi HR tạo hồ sơ.</div>' : T.skel(2)) + "</div></div>") +
        '<div><div class="ts-lbl" style="margin-bottom:6px">Chọn máy Sẵn sàng</div><div data-asset>' + T.skel(4) + "</div></div>" +
        '<div><div class="ts-lbl" style="margin-bottom:6px">Checklist bàn giao</div>' + T.checklistHtml(checklist, "hand") + "</div>" +
        '<label class="ts-lbl">Ghi chú<textarea class="ts-ta" name="note" maxlength="1000"></textarea></label>' +
        '<div class="ts-note">Sau khi cấp phát, nhân viên nhận thông báo và bấm "Tôi đã nhận đủ" trong Tài sản của tôi.</div>',
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-wash" data-reserve>Giữ chỗ</button>' +
        (noEmp ? "" : '<button type="button" class="ts-btn ts-primary" data-ok>Cấp phát</button>'),
        function (el, close) {
          var assetPick = null, empPick = null;
          T.pickList("available").then(function (rows) {
            assetPick = T.picker(el.querySelector("[data-asset]"), rows, { placeholder: "Tag, tên máy, cấu hình…",
              label: function (r) { return (r.tag || r.name) + " · " + (r.asset_name || ""); },
              sub: function (r) { return r.specs || r.category; }, text: function (r) { return [r.tag, r.asset_name, r.specs, r.category].join(" "); },
              right: function (r) { return T.pill(r.status) + (r.condition && r.condition !== "Good" ? " " + T.condPill(r.condition) : ""); },
              selected: card && card.reserved_asset });
          }, function (e) { el.querySelector("[data-asset]").innerHTML = T.errBox(e); });
          if (!(card && card.employee) && !noEmp) {
            T.pickList("employees").then(function (rows) {
              empPick = T.picker(el.querySelector("[data-emp]"), rows, { placeholder: "Tên nhân viên…", label: function (r) { return r.label; }, sub: function (r) { return r.department; } });
            }, function (e) { el.querySelector("[data-emp]").innerHTML = T.errBox(e); });
          }
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          function send(reserve, btn) {
            var asset = assetPick && assetPick.value();
            if (!asset) { T.toast("Chọn một máy.", true); return; }
            var emp = (card && card.employee) || (empPick && empPick.value()) || "";
            var note = el.querySelector('[name="note"]').value;
            T.busy(btn, true);
            var call = noEmp ? T.post("reserve_for_nsp", { asset: asset, nsp: card.source, note: note }) :
              T.post("allocate", { asset: asset, employee: emp, source_type: card ? card.source_type : "", source_name: card ? card.source : "",
                checklist: T.checklistValue(el, "hand"), note: note, reserve_only: reserve ? 1 : 0 });
            call.then(function (r) {
              close();
              if (r && r.fulfillment && !r.fulfillment.ok) T.toast(r.fulfillment.message || "Đã cấp máy, cần hoàn tất phiếu Asset Request tay.", true);
              else T.toast(reserve ? "Đã giữ chỗ." : "Đã cấp phát.");
              resolve(r);
            }, function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
          }
          el.querySelector("[data-reserve]").addEventListener("click", function (ev) { send(true, ev.currentTarget); });
          var ok = el.querySelector("[data-ok]");
          if (ok) ok.addEventListener("click", function (ev) { send(false, ev.currentTarget); });
        }, true);
    });
  }

  // ------------------------------------------------- mau thiet bi (danh muc) --
  // Mau = Item tai san goc ERPNext; them moi qua create_model (chan trung ten, hoi khi giong ten).
  function modelForm(name) {
    return new Promise(function (resolve) {
      T.modal("Thêm mẫu thiết bị",
        '<div class="ts-form"><label class="ts-lbl ts-full">Tên mẫu *<input class="ts-in" name="item_name" maxlength="140" placeholder="Vd: Dell Latitude 5420" value="' + esc(name || "") + '"></label>' +
        '<label class="ts-lbl ts-full">Loại thiết bị *<select class="ts-sel" name="asset_category"><option value="">Đang tải…</option></select></label></div>' +
        '<div class="ts-note">Ghi đủ hãng + dòng máy, không ghi cấu hình riêng của từng máy (cấu hình nhập ở bước sau). Loại quyết định thời gian khấu hao mặc định.</div>',
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Thêm</button>',
        function (el, close) {
          var sel = el.querySelector('[name="asset_category"]');
          T.pickList("categories").then(function (rows) {
            sel.innerHTML = '<option value="">Chọn loại…</option>' + rows.map(function (r) {
              return '<option value="' + esc(r.name) + '">' + esc(r.label) + (r.component ? " (linh kiện)" : "") + "</option>";
            }).join("");
          }, function (e) { sel.innerHTML = '<option value="">' + esc(T.msg(e)) + "</option>"; });
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget, data = { item_name: el.querySelector('[name="item_name"]').value.trim(), asset_category: sel.value };
            if (!data.item_name) { T.toast("Nhập tên mẫu.", true); return; }
            if (!data.asset_category) { T.toast("Chọn loại thiết bị.", true); return; }
            T.busy(btn, true);
            T.catalogCreate("create_model", data, "mẫu này").then(function (r) {
              T.busy(btn, false);
              if (!r) return;
              T.pickList("items", null, true);
              close(); T.toast("Đã có mẫu " + r.label + "."); resolve(r);
            }, function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
          });
        });
    });
  }

  // O chon mau thiet bi (dropdown + Them mau moi). -> Promise(handle {value(), row()})
  function modelPick(host, selected, onPick) {
    host.innerHTML = T.skel(1);
    return T.pickList("items").then(function (rows) {
      return T.catalogPick(host, { rows: rows.slice(), selected: selected || null, placeholder: "Chọn mẫu thiết bị…",
        label: function (r) { return r.label || r.name; }, sub: function (r) { return r.category; },
        addLabel: "Thêm mẫu mới", onAdd: modelForm, onPick: onPick });
    }, function (e) { host.innerHTML = T.errBox(e); return null; });
  }

  // Doi mau cho mot thiet bi (sap lai may nhap ten lech). Loai di theo mau (server).
  function changeModel(asset) {
    return new Promise(function (resolve) {
      var pick = null;
      T.modal("Đổi mẫu · " + (asset.tag || asset.name),
        '<div class="ts-lbl">Mẫu thiết bị<div data-mp></div></div>' +
        '<label class="ts-ck"><input type="checkbox" data-rename checked> Đặt tên hiển thị theo tên mẫu (hiện: ' + esc(asset.asset_name || "—") + ")</label>" +
        '<div class="ts-note">Loại thiết bị đổi theo mẫu. Có ghi vào Lịch sử của máy.</div>',
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Lưu</button>',
        function (el, close) {
          modelPick(el.querySelector("[data-mp]"), asset.model).then(function (h) { pick = h; });
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget, k = pick && pick.value(), r = pick && pick.row();
            if (!k) { T.toast("Chọn mẫu.", true); return; }
            var data = { item_code: k };
            if (el.querySelector("[data-rename]").checked && r) data.asset_name = r.label || k;
            T.busy(btn, true);
            T.post("update_info", { asset: asset.name, data: JSON.stringify(data) }).then(function (res) { close(); T.toast("Đã đổi mẫu."); resolve(res || true); },
              function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
          });
        });
    });
  }

  // Nhap thiet bi moi (create_asset).
  // can: d.can cua trang (server). Khau hao / tien thue chi Finance dat - nguoi khac de theo loai.
  function createAsset(can) {
    var fin = !!(can && can.finance);
    return new Promise(function (resolve) {
      var today = new Date().toISOString().slice(0, 10);
      T.modal("Nhập thiết bị",
        '<div class="ts-form"><div class="ts-lbl ts-full">Mẫu thiết bị *<div data-item></div>' +
        '<span class="ts-note" style="font-weight:400">Chọn từ danh mục để cùng một dòng máy luôn một tên. Chưa có thì bấm Thêm mẫu mới.</span></div>' +
        '<label class="ts-lbl ts-full">Tên hiển thị<input class="ts-in" name="asset_name" maxlength="140" placeholder="Trống = theo tên mẫu"></label>' +
        '<label class="ts-lbl">Tag dán trên máy<input class="ts-in" name="tag" placeholder="EC202600001"></label>' +
        '<label class="ts-lbl">Serial<input class="ts-in" name="serial"></label>' +
        '<label class="ts-lbl">Ngày mua<input class="ts-in" type="date" name="purchase_date" value="' + today + '"></label>' +
        '<label class="ts-lbl">Ngày đưa vào dùng<input class="ts-in" type="date" name="available_for_use_date" value="' + today + '"></label>' +
        '<label class="ts-lbl">Nguyên giá (₫)<input class="ts-in" name="net_purchase_amount" inputmode="numeric" required></label>' +
        (fin ? '<label class="ts-lbl">Khấu hao (tháng, trống = theo loại)<input class="ts-in" name="useful_life_months" inputmode="numeric"></label>' : "") +
        '<label class="ts-lbl">Bảo hành đến<input class="ts-in" type="date" name="warranty_until"></label>' +
        '<label class="ts-lbl">Sở hữu<select class="ts-sel" name="ownership"><option value="Owned">Công ty sở hữu</option><option value="Rented">Đi thuê</option><option value="Personal">Máy cá nhân (phụ cấp)</option></select></label>' +
        (fin ? '<label class="ts-lbl" data-rent hidden>Tiền thuê / phụ cấp tháng (₫)<input class="ts-in" name="monthly_rent" inputmode="numeric"></label>' : "") + "</div>" +
        '<div><div class="ts-lbl" style="margin-bottom:6px">Cấu hình gốc</div><div data-specs class="ts-form"></div></div>',
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Nhập kho</button>',
        function (el, close) {
          var itemPick = null;
          var specHost = el.querySelector("[data-specs]");
          function specRows(parts) {
            specHost.innerHTML = parts.map(function (p) {
              return '<label class="ts-lbl">' + esc(p) + '<input class="ts-in" data-part="' + esc(p) + '" maxlength="140"></label>';
            }).join("");
          }
          specRows(["CPU", "RAM", "Ổ cứng", "Màn hình"]);
          modelPick(el.querySelector("[data-item]"), null, function (k, r) {
            var c = String((r && r.category) || "").toUpperCase();
            specRows(c === "PC" ? ["CPU", "Mainboard", "RAM", "SSD", "GPU", "PSU"] : c === "MONITOR" ? ["Kích thước", "Độ phân giải", "Cổng kết nối"] :
              c === "PRINTER" ? ["Loại máy", "Kết nối"] : ["CPU", "RAM", "Ổ cứng", "Màn hình"]);
          }).then(function (h) { itemPick = h; });
          var own = el.querySelector('[name="ownership"]');
          own.addEventListener("change", function () { var r = el.querySelector("[data-rent]"); if (r) r.hidden = own.value === "Owned"; });
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget;
            function v(n) { var f = el.querySelector('[name="' + n + '"]'); return f ? f.value : ""; }
            var data = { item_code: itemPick ? itemPick.value() : "", asset_name: v("asset_name"), tag: v("tag"), serial: v("serial"),
              purchase_date: v("purchase_date"), available_for_use_date: v("available_for_use_date"),
              net_purchase_amount: String(v("net_purchase_amount")).replace(/[^\d]/g, ""), useful_life_months: v("useful_life_months"),
              warranty_until: v("warranty_until"), ownership: own.value, monthly_rent: String(v("monthly_rent")).replace(/[^\d]/g, ""),
              specs: T.qsa(specHost, "[data-part]").filter(function (i) { return i.value.trim(); }).map(function (i) {
                return { part_type: i.getAttribute("data-part"), spec: i.value.trim(), qty: 1 }; }) };
            if (!data.item_code) { T.toast("Chọn mẫu thiết bị.", true); return; }
            T.busy(btn, true);
            T.post("create_asset", { data: data }).then(function (r) { close(); T.toast("Đã nhập kho."); resolve(r); },
              function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
          });
        }, true);
    });
  }

  window.ECTsOps = { changeModel: changeModel, modelPick: modelPick, transition: transition, openRepair: openRepair, closeRepair: closeRepair, allocate: allocate, createAsset: createAsset, condSelect: condSelect };
})();
