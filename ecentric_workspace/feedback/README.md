# Góp ý công ty (`/gop-y`)

Nhân viên gửi góp ý, đề xuất, phản ánh, câu hỏi cho Ban Giám đốc và theo dõi được góp ý của mình đã xử lý tới đâu.
Thay mục "Góp ý BGD (sắp ra mắt)" trong nhóm Tài nguyên. PO Hoàn chốt 04/10/2026, thiết kế = mockup Bản 1.

## Trang

| Route | Ai | Nội dung |
|---|---|---|
| `/gop-y` | nhân viên | 3 tab: Gửi góp ý · Của tôi (`?tab=cua-toi`) · Bảng chung (`?tab=bang-chung`, `&sap-xep=`, `&loc=`) |
| `/gop-y/<mã>` | người gửi | luồng trao đổi, tiến độ 3 bước, nhắn thêm, "Chưa ổn" (mở lại 1 lần). Người xử lý mở link này → chuyển sang hộp xử lý |
| `/gop-y/xu-ly` | Management + System Manager | hộp xử lý: lọc (cần xử lý / quá hạn / sắp hết hạn / đã đóng), trả lời, đổi trạng thái, ghi chú nội bộ, bảng chung, chuyển chủ đề, trùng / spam |
| `/gop-y/tong-quan` | Management + System Manager | số liệu tháng, theo chủ đề, chủ đề nóng (AI), góp ý quá hạn |

Thư mục www không được có gạch ngang → `www/gop_y/` + 4 `website_route_rules`. Mọi trang `no_cache = 1`.

## Luật (PO chốt 04/10/2026)

- **Ẩn danh**: tuỳ người gửi. Người xử lý và BGD thấy "Ẩn danh". Danh tính ở `EC Feedback Identity`,
  chỉ System Manager đọc được, mỗi lần mở bản ghi Frappe ghi View Log (`track_views`).
  Không báo người gửi khi danh tính bị mở, không ghi vào luồng.
- **Người xử lý** = nhân viên Active thuộc phòng `Management - EC` (cả phòng con). Không chia theo chủ đề.
- **Trạng thái**: Mới → Đang xem → Đã trả lời / Đã làm / Không làm. "Đã trả lời" và "Không làm"
  bắt buộc có lời nhắn. Người gửi được chuông (`feedback_update`) mỗi lần đổi trạng thái / có trả lời.
- **Hạn phản hồi đầu**: 5 ngày làm việc (lịch `EC_STANDARD_9_18` + Holiday List mặc định của công ty).
  Chỉ trả lời hoặc trạng thái kết quả mới dừng đồng hồ; "Đang xem" thì không. Chưa tính KPI.
  Nhắc khi còn ≤ 1 ngày làm việc; quá hạn báo cả nhóm Management. Mở lại = hạn mới.
- **Bảng chung**: mặc định riêng tư. Người xử lý "Đưa lên" kèm tiêu đề + trả lời công khai viết lại
  (nội dung gốc không bao giờ lên bảng). Mọi nhân viên "+1"; không ai thấy ai đã bấm.
- **Popup trang chủ**: góp ý "Đã làm" đang trên bảng chung → popup 7 ngày (`home_today.announce_service`).
- **Chống spam**: 5 góp ý / người / ngày (tính cả ẩn danh).
- **Bản tin tháng**: 08:45 ngày 1, chuông + Teams cho nhóm Management; AI gom chủ đề nóng qua `platform/ai`
  (chỉ gửi tiêu đề + nội dung + số +1). BGD bấm "Tóm tắt ngay" tối đa 3 lần / ngày.

## Ẩn danh — chỗ dễ lộ và cách chặn

| Đường lộ | Chặn |
|---|---|
| `owner` / `modified_by` Frappe tự ghi vào mọi bản ghi (cả File, bảng con) | ghi thay người gửi trong `repository.as_system()` + `scrub_owner()` |
| realtime `list_update` mang `frappe.session.user` | ghi dưới SYSTEM_USER; DocType `read_only` |
| `from_user` / owner của Notification Log | job thông báo chạy dưới `Administrator` (`notify._boot`) |
| `EC Read Receipt` (HR Manager đọc được) | không dùng cho góp ý; "chưa đọc" là cột trong bảng danh tính |
| giờ phút gửi + ai đang online | góp ý ẩn danh chỉ hiện ngày |
| nội dung tự lộ | cảnh báo trên form; bảng chung chỉ hiện nội dung viết lại |

## Lớp

`constants` → `domain` (thuần) → `repository` (chỗ DUY NHẤT chạm DB) → `service` (nhân viên) /
`handler_service` (người xử lý) / `notify` (job thông báo + nhắc hạn) / `digest` (bản tin tháng) →
`api.py` (whitelist, user lấy từ phiên, trả `{success, message, data}`) và `www/gop_y/*.py`.

Mọi DocType chỉ System Manager có quyền (không có đường `/app`, `/api/resource` cho nhân viên);
mọi quyền kiểm ở service. Tệp đính kèm private, tải qua `api.download`.

## Test

    python -m unittest ecentric_workspace.feedback.tests.test_feedback

Chạy thật domain / service / handler_service / notify / digest trên repo giả và render 4 trang bằng jinja2.
Lớp `TestAnonymity` kiểm cả context lẫn HTML người xử lý nhận: email / họ tên người gửi ẩn danh không xuất hiện.

**Không kiểm được ngoài bench** (phải thử trên site sau deploy): `as_system()` khôi phục đúng phiên,
owner của Notification Log, tải tệp private, phân quyền DocType.
