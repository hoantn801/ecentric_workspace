# Quản lý tài sản & thiết bị (`tai_san`)

Khảo sát + plan 26/11/2026 (doc "Quản lý tài sản & thiết bị — khảo sát và kế hoạch"). PO Hoàn duyệt
hướng giao diện ghép: trang chính theo phương án A, tab Linh kiện theo B, màn điện thoại theo C
(mockup "Quản lý tài sản – Bản chốt (A + B + C)").

## Nguyên tắc

- Thiết bị = bản ghi **Asset gốc của ERPNext** (54 máy đã có trên site). **Không** tạo DocType tài sản
  thứ hai, **không** sửa DocType gốc: chỉ Custom Field `ec_*` (fixtures) và bảng con `EC Asset Spec`.
- Linh kiện **có sẵn** trong máy (CPU, RAM hàn, SSD theo máy) → bảng `ec_spec` (EC Asset Spec), không giá.
- Linh kiện **mua thêm** (RAM, SSD, card…) → một Asset riêng, trỏ về máy mẹ qua `custom_installed_on`.
- Khấu hao **quản trị**: đường thẳng, tròn tháng, từ `ec_depreciation_start` (trống = ngày đưa vào dùng),
  số tháng `ec_useful_life_months` (trống = `Asset Category.ec_default_life_months`). Không submit Asset,
  không sinh Journal Entry — chuyển sang khấu hao gốc ERPNext khi Finance đưa sổ lên ERP.
- Tài sản dưới 30 triệu là công cụ dụng cụ (TT45/2013): phân bổ tối đa 36 tháng.

## Field có sẵn trên site — KHÔNG thuộc app (nợ)

Tạo tay khoảng 08/2026, không nằm trong fixtures. Code đọc qua hằng số trong `constants.py`, không
đổi tên (đổi = migrate dữ liệu 54 máy):

| Field | Ý nghĩa |
| --- | --- |
| `custom_asset_` | Trạng thái vận hành thật (nhãn "Asset Status"). p001 nối thêm `Pending Check`, `Broken` |
| `custom_asset_tag` | Tag dán trên máy, mẫu `EC` + 9 số (`EC202400001`, linh kiện `EC202400006-1`) |
| `custom_serie_number` | Serial |
| `custom_installed_on` / `custom_installed_date` | Linh kiện đang lắp trong máy nào, từ ngày nào |

Bench mới dựng từ app sẽ **không** có các field này → p001 bỏ qua bước trạng thái. Khi làm đợt 1 nên
đưa 5 field này vào fixtures (cần export đúng định nghĩa từ site trước).

## Trạng thái (9)

`Available` Sẵn sàng · `Reserved` Đã giữ chỗ · `In Use` Đang dùng · `Pending Check` Chờ kiểm tra ·
`Broken` Hỏng chờ xử lý · `Under Repair` Đang sửa · `Lost` Mất · `Disposed` Thanh lý · `Retired` Ngừng dùng.
Tình trạng (`ec_condition`: Tốt / Hỏng một phần / Hỏng toàn bộ) là trường riêng.

## Đợt 0 (nhánh `feat/tai-san-dot0`)

- `patches/p001_setup.py`: 16 Custom Field, nối 2 trạng thái, role `EC Asset Manager`, mặc định theo loại
  (chỉ điền ô trống). Idempotent, lỗi một bước → Error Log, không chặn migrate.
- `domain.audit_assets`: rà soát dữ liệu sổ (người giữ đã nghỉ, Sẵn sàng còn người giữ, serial trùng /
  thiếu, tag sai mẫu, ngày dùng trước ngày mua, giá linh kiện bất thường, linh kiện lệch trạng thái máy mẹ).
  Dùng lại cho cảnh báo ở đợt 1.

Test: `python -m unittest ecentric_workspace.tai_san.tests.test_tai_san`

## Đợt 1–3 (nhánh `feat/tai-san-dot1`)

| Phần | File |
| --- | --- |
| Vòng đời (bảng chuyển trạng thái duy nhất) | `lifecycle.py` |
| Khấu hao quản trị | `depreciation.py` |
| Số liệu Tổng quan (hàm thuần) | `reports.py` |
| Truy cập dữ liệu (nơi duy nhất gọi `frappe.db`) | `repository.py` |
| Quyền | `access.py` (Ctx: manage / see_cost / finance / overview, phạm vi phòng ban) |
| Lệnh vận hành | `service.py` (transition, nhân viên xác nhận / báo hỏng, sửa thông tin) |
| Sửa chữa | `repair_service.py` (máy tạm, ngưỡng duyệt chi phí) |
| Linh kiện, cấu hình gốc, nhập thiết bị | `component_service.py` |
| Nối luồng phê duyệt | `flows.py` (NSP, Asset Request → hoàn tất fulfillment, Clearance, Báo hỏng/mất) |
| Kiểm kê | `count_service.py` |
| Tác vụ nền | `jobs.py` — 00:40 thu hồi theo ngày làm việc cuối, 01:10 ngày 1 chốt tháng |
| Đọc cho trang | `views.py` |
| API | `controllers/api.py` (hợp đồng: `API.md`) |
| Trang | `pages/*` + `public/tai_san/*` |
| Menu | `nav.py` + `shell/nav.py` (ngữ cảnh `tai_san`, nhóm "Tài sản & thiết bị" ở khu Công ty) |

DocType mới: `EC Asset Event` (nhật ký, chỉ thêm), `EC Asset Repair`, `EC Asset Monthly`,
`EC Asset Count` + `EC Asset Count Item`. Field mới: `Asset.ec_reserved_for`, `Asset.ec_end_date`.

**Ranh giới với Approval Center:** chỉ ĐỌC phiếu (NSP, Asset Request, Clearance, Báo hỏng/mất) và
link sang. Ngoại lệ duy nhất có ghi: cấp phát theo Asset Request gọi
`asset_request.application.service.claim_fulfillment / complete_fulfillment` (API của chính
feature đó) — lỗi phía phiếu không chặn việc cấp máy, trả cảnh báo. **Không** duyệt thay nhóm
Operation của Clearance.

**Thao tác ghi Asset** dùng `frappe.db.set_value` (không `doc.save()`): Asset đang Draft, validate
gốc của ERPNext kiểm khấu hao / tài khoản kế toán mà module không dùng. `create_asset` thì phải
`insert()` một Asset thật (is_existing_asset=1) — **cần thử trên site trước khi Ops dùng**.

Test: `python -m unittest ecentric_workspace.tai_san.tests.test_tai_san ecentric_workspace.tai_san.tests.test_dot1 ecentric_workspace.tai_san.tests.test_pages`

## Chưa chốt (mặc định đang theo đề xuất trong plan)

36 tháng / 24 tháng linh kiện · có bước "Chờ kiểm tra" khi thu hồi · role riêng `EC Asset Manager` ·
menu ở khu Công ty · ngưỡng 3.000.000 ₫ sửa chữa phải tạo phiếu duyệt (đợt 2).
