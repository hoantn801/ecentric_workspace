# API module tài sản (`tai_san/controllers/api.py`)

Prefix: `ecentric_workspace.tai_san.controllers.api.` · gọi qua `window.ecApi.get/post` (xem
`public/dao_tao/ec_dt_core.js` hàm `whenApi`/`call`). Mọi hàm trả envelope
`{success, message, data}`; `success=false` → hiện `message` (tiếng Việt) bằng toast.
Không có quyền (`AccessDenied`) → `data = {denied: true}`: trang Tổng quan / Danh sách chuyển sang
`/tai-san/cua-toi`. Chi phí sửa chữa (`expected_cost`, `actual_cost`) và vấn đề dữ liệu lộ giá chỉ trả
cho role xem chi phí; nhật ký không ghi giá trị tiền.
Tham số dict/list gửi JSON (POST) hoặc chuỗi JSON (GET `filters`).

Mọi response đọc có `can`: `{manage, see_cost, finance, overview, employee}` → ẩn/hiện nút.
**Không có `see_cost` thì KHÔNG có trường tiền** (gross, nbv, accumulated, monthly, finance,
cost_12m, depreciation, info) — trang phải chịu được thiếu.

Trạng thái lưu tiếng Anh, nhãn trong `status_labels` / `status_label`:
`Available Sẵn sàng · Reserved Đã giữ chỗ · In Use Đang dùng · Pending Check Chờ kiểm tra ·
Broken Hỏng chờ xử lý · Under Repair Đang sửa · Lost Mất · Disposed Thanh lý · Retired Ngừng dùng`.
Chấm màu pill (DESIGN.md, nền xám): Available #10b981 · In Use #2C3DA6 · Reserved #9ca3af (viền) ·
Pending Check #d97706 viền · Broken #dc2626 · Under Repair #d97706 · Lost #6b7280 · Disposed #d1d5db · Retired #9ca3af.
Tình trạng `condition`: Good Tốt · Partially Damaged Hỏng một phần · Fully Damaged Hỏng toàn bộ.

## Dòng thiết bị (`row`) — dùng chung
`name, tag, asset_name, category, status, status_label, condition, serial, holder, holder_name,
holder_left (bool: người giữ đã nghỉ), department, purchase_date, warranty_until, ownership,
installed_on, components (số linh kiện lắp thêm), reserved_for` + khi see_cost:
`gross, nbv, accumulated, monthly, months_done, life`.

## GET
| hàm | tham số | data |
|---|---|---|
| `dashboard` | month (YYYY-MM), department, category | `kpis{total, by_status{status:n}, in_use, available, reserved, pending_check, broken_or_repair, lost, components_installed}`, `by_category[{category, counts{status:n}, total}]`, `by_department[{department, count, nbv?}]`, `age[{bucket, count}]`, `month`, `status_labels`, `filters{departments, categories}`, `finance?{gross, accumulated, nbv, month, month_cost{depreciation, repair, rent, total}}`, `cost_12m?[{month, depreciation, repair, rent}]`, `todo{returns[{source, route, employee, employee_name, department, last_working_day, days_left, assets[{name,tag,asset_name}]}], holder_left[{asset,tag,asset_name,employee,employee_name}], allocations[{source, source_type, source_label, route, employee, employee_name, department, need, due, reserved_asset?, has_employee?}], repairs[repair_row], warranty[{asset,tag,asset_name,days_left,warranty_until}], fully_depreciated?[{asset,tag,asset_name}], idle[{asset,tag,asset_name,idle_days}]}` |
| `list_assets` | filters JSON `{q, status, category, department, holder, issues_only, include_components, page}` | `rows[row + issues[nhãn]]`, `total, page, page_size(50), status_labels, categories, departments` |
| `asset_detail` | name | `asset(row)`, `specs[{name, part_type, spec, qty, note}]`, `spec_template[bộ phận gợi ý]`, `components[row]`, `parent(row\|null)`, `events[{type, label, time, actor, from_status, to_status, from_employee, to_employee, ref_doctype, ref_name, ref_route, related_asset, note, checklist, acknowledged_at}]`, `repairs[repair_row]`, `actions[{action,label}]` (chỉ khi manage), `is_component_category`, see_cost: `depreciation{gross, salvage, life, start, end, monthly, months_done, accumulated, nbv, this_month, fully_depreciated, curve[[YYYY-MM, nbv]], components_total}`, `info{ec_ownership, ec_monthly_rent, ec_supplier, ec_invoice, ec_useful_life_months, ec_depreciation_start, ec_salvage_value, available_for_use_date, location, item_code}` |
| `my_assets` | – | `assets[row + pending_ack(bool), count_confirmed("ok"\|"wrong"\|null), specs[], components[{name,tag,asset_name}]]`, `employee`, `no_employee?`, `damage_levels[Partial, Full, Lost]`, `count{name,title,started_on}\|null` (đợt kiểm kê đang mở), `request_route` (/approvals/asset-request) |
| `board` | – | `allocate[như todo.allocations]`, `reserved[row]`, `returns[{…như todo.returns, assets[row], all_returned}]`, `checks[row]` (Chờ kiểm tra), `broken[row]`, `repairs[repair_row]`, `damage_requests[{source, route, title, incident_type, incident_date, asset_code, asset?, tag?, estimated_cost}]`, `handover_checklist[]`, `return_checklist[]`, `repair_threshold` |
| `repairs` | status? | `rows[repair_row]`, `cost_by_month?{YYYY-MM: tổng}`, `repeat{asset: số lần}`, `status_labels`, `mode_labels` |
| `pickers` | kind = `employees`\|`items`\|`available`\|`components`, category? | employees `[{name,label,department}]` · items `[{name,label,category}]` · available/components `[row + specs(chuỗi)]` |
| `audit` | – | `rows[row + issues[]]`, `total` |
| `count_summary` | name? | `count{name,title,status,started_on}\|null`, `rows[{asset, tag, asset_name, expected_holder, expected_holder_name, expected_status, result, result_label, actual_holder, actual_holder_name, self_confirmed, note, counted_at}]`, `done, total, mismatch, result_labels, can` |

`repair_row`: `name, asset, tag, asset_name, status, status_label, damage_level (Partial|Full),
damaged_parts, mode, mode_label, vendor, sent_date, expected_return, returned_date,
expected_cost?, actual_cost?, result, loaner_asset, overdue(bool)`.

## POST
| hàm | tham số | ghi chú |
|---|---|---|
| `transition` | asset, action, employee?, note?, checklist?(list/dict), condition? | action ∈ `actions` của asset_detail: reserve, unreserve, assign, transfer, return, check_pass, check_fail, break, repair_start, repair_done, repair_fail, lost, found, dispose (chỉ finance), retire |
| `allocate` | asset, employee?, source_type?, source_name?, checklist?, note?, reserve_only? | Cấp phát / giữ chỗ từ thẻ "Chờ cấp phát". source_type = `EC New Staff Preparation` \| `EC Asset Request`. Với Asset Request trả thêm `fulfillment{ok, message?}` (hiện cảnh báo nếu ok=false) |
| `reserve_for_nsp` | asset, nsp, note? | giữ chỗ khi nhân sự mới chưa có hồ sơ |
| `return_for_clearance` | asset, clearance, checklist?, note? | → Chờ kiểm tra |
| `check` | asset, passed(1/0), checklist?, note?, condition? | Chờ kiểm tra → Sẵn sàng / Hỏng |
| `acknowledge` | asset | nhân viên "Tôi đã nhận đủ" |
| `report_damage` | asset, level(Partial\|Full\|Lost), parts?(list), description? | nhân viên báo hỏng |
| `open_repair` | asset, data{damage_level, damaged_parts(list), description, repair_mode(Internal\|Warranty\|External), vendor, sent_date, expected_return, expected_cost, loaner_asset, damage_request?, note} | nếu trả `{need_approval:true, threshold, route}` → báo cần tạo phiếu Báo hỏng/mất để duyệt chi phí (link route) |
| `close_repair` | repair, data{result(Fixed\|Unfixable), actual_cost, returned_date, return_to("holder"\|"stock"), condition, note} | |
| `cancel_repair` | repair, note? | |
| `handle_damage_request` | request, asset, action("repair"\|"lost"), data? | |
| `install_component` | component, parent | |
| `remove_component` | component, to_status?("Broken") | |
| `save_specs` | asset, rows[{part_type, spec, qty, note}] | thay toàn bộ bảng cấu hình gốc |
| `create_asset` | data{item_code (mẫu thiết bị), asset_name? (trống = tên mẫu), purchase_date, net_purchase_amount, available_for_use_date?, tag?, serial?, ownership?, monthly_rent?, warranty_until?, supplier?, useful_life_months?, specs?[]} | "+ Nhập thiết bị" |
| `update_info` | asset, data{…, item_code?} | trường tiền / khấu hao chỉ finance; `item_code` = đổi mẫu (người quản lý), loại đi theo mẫu |
| `open_count` | title? | |
| `confirm_count` | asset, ok(1/0), note? | nhân viên tự xác nhận trong "Tài sản của tôi" |
| `mark_count` | asset, result(OK\|Wrong Holder\|Wrong Status\|Not Found\|Damaged), actual_holder?, note? | |
| `close_count` | – | |

### Bản quyền phần mềm (đợt 4)
| Hàm | Tham số | Ghi chú |
|---|---|---|
| `licenses` (GET) | filters{stage: due\|expired\|perpetual, category, product, status, q} | `rows[]` (có `product`), `groups[]` (gộp theo phần mềm), `summary{total,due,expired,seats,used,monthly_cost?}`; tiền chỉ cho role xem chi phí |
| `license_detail` (GET) | name | `license`, `seats[]`, `history[]`, `renewals[]`, `suggested_expiry` |
| `create_license` | data{product (bắt buộc), license_type?, billing_cycle, seats, start_date, expiry_date, owner_employee, department, account, key_location, cost_per_cycle, …} | người quản lý tài sản |
| `update_license` | name, data | tên / hãng / nhóm theo `product` (không sửa riêng); `cost_per_cycle` chỉ finance; `expiry_date` = sửa nhập nhầm (gia hạn dùng `renew_license`) |
| `renew_license` | name, new_expiry, cost?, note? | hạn mới phải sau hạn cũ và sau hôm nay |
| `cancel_license` | name, note? | thu hết chỗ |
| `assign_license` / `revoke_license_seat` | name, employee, note? / seat, note? | không vượt số chỗ, không trùng người, nhân viên phải Active |
`dashboard.licenses{summary, todo}`, `my_assets.licenses[]` (không có tiền), `board.returns[].licenses[]`.

### Danh mục (27/11/2026)
Tạo trả về một trong ba: `{product|item, row}` đã tạo · `{exact: row}` đã có đúng tên (bỏ dấu / hoa thường / khoảng trắng) - không tạo · `{similar: [row+score]}` tên gần giống - gọi lại với `force=1` nếu chắc là khác.

| Hàm | Tham số | Ghi chú |
|---|---|---|
| `products` (GET) | – | danh mục phần mềm `rows[{name,label,vendor,category,license_type,billing_cycle,disabled,licenses}]` |
| `create_product` | data{product_name, vendor?, category?, license_type?, billing_cycle?}, force? | người quản lý tài sản |
| `update_product` | name, data{product_name?, vendor?, category?, license_type?, billing_cycle?, disabled?, note?} | đổi tên / hãng / nhóm cập nhật luôn mọi bản quyền của phần mềm |
| `merge_product` | source, target | bản quyền của source chuyển sang target; source ngừng dùng (không xoá) |
| `create_model` | data{item_name, asset_category}, force? | mẫu thiết bị = Item tài sản (is_fixed_asset); mã `EC-<TÊN>`, nhóm hàng / ĐVT chép từ Item cùng loại |
| `pickers` (GET) | kind = `categories` | loại thiết bị (Asset Category) cho form Thêm mẫu |

### Chi phí nhiều tiền tệ (27/11/2026)
- `create_license` / `update_license` nhận `currency` (VND, USD, EUR, SGD), `cost_fc` (số ngoại tệ), `exchange_rate` (₫ / 1 đơn vị) và `cost_per_cycle` (₫).
  - Ngoại tệ mà `cost_per_cycle` để trống: hệ thống tính `cost_fc × exchange_rate`.
  - `cost_per_cycle` luôn là ₫, dùng để cộng chi phí tháng.
- Ai sửa chi phí: người quản lý tài sản + Finance / HOF, bất cứ lúc nào. Mỗi lần sửa ghi nhật ký; `license_detail.logs` trả nhật ký cho hai vai này.
- `renew_license` nhận thêm `currency`, `cost_fc`, `exchange_rate`. Để trống thì giữ chi phí cũ.
- `licenses` trả thêm:
  - `currencies`;
  - `rates` (tỷ giá gợi ý = Currency Exchange mới nhất → VND; chỉ người quản lý / Finance thấy).
