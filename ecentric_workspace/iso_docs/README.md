# Thư viện tài liệu ISO (`iso_docs`)

PO Hoàn chốt 04/10/2026 (mockup B rút gọn cho quản lý, D cho nhân viên). Thiết kế đầy đủ: doc
"Thư viện tài liệu ISO — kiểm kê & thiết kế". Đóng gói quy trình mới từ chat khác:
`NHIEU_LOP/iso/HUONG_DAN_DONG_GOI_QUY_TRINH.md`.

## Nguyên tắc

- Tài liệu = bản ghi **Quality Procedure** của ERPNext. **Không sửa DocType gốc**: chỉ Custom Field
  `ec_*` (fixtures), bảng con `EC Document Revision`, Workflow chuẩn của Frappe.
- Tên bản ghi = mã tài liệu (`QT-TCKT-03`), qua Property Setter `autoname = field:ec_doc_code`.
- Không xoá phiên bản cũ: mỗi lần ban hành là một dòng `EC Document Revision`; phiên bản trước chuyển
  "Hết hiệu lực" với ngày hiệu lực đến = ngày trước ngày hiệu lực mới.
- Biểu mẫu là tài liệu riêng (`BM-QT-TCKT-03-01`) trỏ về quy trình qua `ec_parent_doc`, **không** dùng
  cây `parent_quality_procedure` của ERPNext (cây tự chèn con vào bảng bước của cha).

## Luồng duyệt (Workflow "Tài liệu ISO", `workflow_spec.py`)

`Nháp → Chờ trưởng bộ phận → Chờ Ban ISO → Chờ Tổng giám đốc → Ban hành → (Chờ thu hồi → Hết hiệu lực)`

- Trưởng bộ phận = `Department.manager_email` của phòng chủ trì (service tự điền `ec_dept_head`).
  Không có role riêng: role Employee + điều kiện `doc.ec_dept_head == frappe.session.user`.
  Phòng chưa có trưởng BP thì Ban ISO bấm thay.
- Sửa **nhỏ** (X.Y+1) trên tài liệu đã có phiên bản: Ban ISO ban hành luôn, không qua TGĐ.
  Tài liệu mới và sửa **lớn** (X+1.0) luôn qua TGĐ.
- "Soạn phiên bản mới" đưa tài liệu về Nháp; phiên bản hiệu lực vẫn đọc được trong lúc soạn.

**Tên trạng thái trên site:** site đã có sẵn Workflow State "Nhap" và "Cho Truong bo phan" của luồng
khác. MariaDB coi "Nháp" = "Nhap" nên luồng ISO dùng lại tên cũ, và tài liệu lưu "Nhap". Code luôn so
trạng thái qua `domain.is_state` (bỏ dấu, không phân biệt hoa thường), **không** so bằng `==`.

## Thông báo lên trang chủ (spec PO 04/10)

Tích `ec_notify_home` (chỉ tài liệu toàn công ty) → khi chuyển sang Ban hành, `service.on_update` gọi
`home_today/announce_service.publish_from_source("Quality Procedure", mã, phiên bản, ...)`:
tiêu đề "Ban hành: <mã> <tên> (v<phiên bản>)", chuyên mục Chính sách, hiển thị "Ảnh + nội dung",
hiện từ ngày hiệu lực đến +6 ngày, link `/tai-lieu/<mã>` "Xem tài liệu →".
Một thông báo cho mỗi phiên bản; lỗi tạo thông báo **không chặn** ban hành (savepoint + Error Log).
Thu hồi tài liệu thì rút thông báo. Không đụng `ec_home_popup.js`, `home_today/service.py`, trang chủ.

## Thông báo người duyệt (06/10, `notify.py`)

Mỗi lần trạng thái đổi qua luồng duyệt, `service.on_update` xếp job `notify.state_changed`
(chạy sau commit, hàng `short`). Ai nhận do `domain.notify_plan` quyết định:

| Chuyển sang | Ai nhận | Link |
|---|---|---|
| Chờ trưởng bộ phận | `ec_dept_head` (trống thì Ban ISO) | `/tai-lieu/quan-ly?loc=cho-toi&ma=` |
| Chờ Ban ISO | mọi user role Ban ISO | như trên |
| Chờ Tổng giám đốc, Chờ thu hồi | role TGĐ duyệt tài liệu | như trên |
| Nháp (bị trả lại từ bước chờ) | người soạn, kèm ý kiến | `/tai-lieu/soan?ma=` |
| Ban hành | người soạn | `/tai-lieu/<mã>` |

Không báo chính người bấm. Nhập file cũ (`force_published`) không qua `on_update` nên không báo ai.
Tắt hẳn: `site_config` `ec_iso_notify_disabled = 1`. Qua `notification_center.publish_notification_event`
(chuông ERP + Teams theo ma trận của notification_center), dedupe theo (tài liệu, trạng thái, lần lưu).

## Quyền

- Ban ISO / TGĐ duyệt tài liệu / System Manager: mọi tài liệu.
- Nhân viên (hồ sơ Employee Active): tài liệu đã có phiên bản hiệu lực, chưa hết hiệu lực, toàn công ty
  hoặc phòng mình nằm trong phạm vi (phòng cha gồm phòng con).
- Người soạn + trưởng BP của tài liệu: luôn thấy; ghi được đúng bước của mình (Nháp / Chờ trưởng BP).
- Desk User trước đây toàn quyền trên Quality Procedure → nay chỉ đọc (patch p001).

## Lớp code

`constants → domain (thuần) → workflow_spec (thuần) → errors → repository (chỉ chỗ này chạm DB)
→ service → events (doc_events) / permissions (hooks)`. Patch `p001_setup` dựng field, role,
Property Setter, Custom DocPerm, Workflow; chạy lại bao nhiêu lần cũng được.

Test (không cần bench): `python -m unittest ecentric_workspace.iso_docs.tests.test_iso_docs`

## Đã làm / còn lại

- [x] Bước 2: nền dữ liệu, luồng duyệt, quyền, lịch sử ban hành, thông báo trang chủ (05/10/2026).
- [x] Chạy thử trên site 05/10: đủ luồng lớn, sửa nhỏ, thu hồi, thông báo trang chủ; sửa lỗi tên trạng thái bỏ dấu.
- [x] Trang `/tai-lieu` (thư viện: theo phòng ban / theo việc cần làm / hệ thống ISO, tìm không dấu),
  `/tai-lieu/<mã>` (sơ đồ mermaid to, chọn vai trò thì tô sáng bước + "Việc của …", biểu mẫu, phiên
  bản cũ `?ban=X.Y`), `/tai-lieu/quan-ly` (Chờ tôi duyệt / Đến hạn rà soát / theo phòng, bấm bước duyệt,
  "Nhập gói") - 05/10/2026. Lớp: `library.py`, `manage.py`, `package.py`, `view.py` (thuần), `api.py`.
- [ ] Nhắc rà soát định kỳ (cron + kill switch), "Báo nội dung sai / lỗi thời", EC Read Receipt.
- [x] Nhập tài liệu cũ từ SharePoint: `legacy.py` + `api.import_legacy` (Ban ISO). Không đi lại luồng duyệt,
  ghi lịch sử phiên bản theo bảng "Lịch sử thay đổi" của file Word, đặt thẳng "Ban hành", nhãn "Bản cũ" trên trang.
  Không ghi đè, chạy lại an toàn, không thông báo trang chủ.
- [ ] AI: sơ đồ mermaid / tóm tắt / eC Mate hỏi đáp qua `platform.ai`.
- [ ] Gán người cho role **Ban ISO** và **TGĐ duyệt tài liệu** trên site (chưa biết thành viên Ban ISO).
