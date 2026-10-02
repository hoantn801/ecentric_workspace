# surveys — Khảo sát nội bộ (/khao-sat)

PO Hoàn yêu cầu 01/10/2026. Mockup đã duyệt: `C:\dev\khao-sat\v2_quay_so\khao_sat_mockup_v2.html` (v2.1, phương án màu **A · Thẻ màu**).

## Cấu trúc
`domain/` (tính toán thuần, test không cần bench) → `infrastructure/` (mọi truy vấn DB) →
`application/` (dịch vụ, kiểm quyền ở `access.py`) → `controllers/api.py` (nơi DUY NHẤT có `@frappe.whitelist`).
Trang: `pages/{hub,fill,manage,builder}` + asset `public/surveys/` (đổi asset → `python -m ecentric_workspace.surveys.pages.assets --stamp`).

## Phần thưởng (PO chốt 01/10/2026)
| Kiểu | Cách chạy | Quyết định PO |
|---|---|---|
| Vòng quay chia đợt | Nộp xong quay ngay. K phần quà → K đợt liền nhau trên số người dự kiến, mỗi đợt giấu 1 lượt trúng (`EC Survey.wheel_plan`, không bao giờ gửi trình duyệt). | Ít người hơn dự kiến → quà đợt chưa tới **không trao** ("B") |
| Số may mắn | Nộp xong tự chọn 1 số trong 1..N, không trùng (khoá dòng khảo sát), bảng số công khai. Tới giờ hẹn máy rút trong CẢ dải, giải nhỏ trước. | Số không ai giữ → **quà để lại** ("A") |
| Đua về đích | Ai nộp phiếu cũng có xe. Thứ tự về đích quyết ở server lúc tới giờ. | Mọi người nộp đều có xe |

Trước khi quay, trang không cho biết "bạn là lượt thứ mấy / đợt này còn quà không" — biết thì canh được lúc quay (review 01/10). Khảo sát ẩn danh: bảng số và làn đua không ghi tên (trừ người về đầu / chính mình).

## Quay theo giờ hẹn (số may mắn, đua về đích) — `application/draw_service.py`
* **T-5 phút:** chuông ERP + web push cho toàn bộ đối tượng, realtime `ec_survey_draw`; popup trang chủ tự mở.
* **T:** job `draw_service.tick` (cron mỗi phút trong `hooks.py`) chốt kết quả dưới khoá, chạy lại không đổi. Người quản lý có nút "Quay ngay" ở tab Kết quả.
* **Cả ngày:** popup giữ kết quả. Đổi giờ quay sau khi đã báo → báo lại theo giờ mới.
* Tắt khẩn cấp: site_config `ec_survey_draw_disabled: 1`.

## Popup trang chủ — `application/draw_feed.py` (API khai báo cho `home_today`)
`for_user(user)` → `draws` (hôm nay, từ T-5: countdown → live 3 phút → done), `upcoming` ("Lượt quay tiếp theo", 30 ngày, kèm tình trạng của người xem), `timers` (để popup hẹn giờ tự mở).
`any_soon()` cho Jinja trang chủ (cache 5 phút). `one(user, name)` cho popup hỏi trong lúc chờ chốt (chưa chốt thì trả ngay, không tính đối tượng).
Hiệu ứng: `public/surveys/ec_survey_draw.js` (`ECSvyDraw.mount/unmount`), nạp qua `ec_home_popup.bundle.js`.

## Thông báo (02/10/2026)
- Phát hành: chuông ERP + web push (`announcement`, Teams KHOÁ).
- "Nhắc người chưa làm": chuông ERP + web push + **Teams** (`announcement_urgent`, qua Power Automate). Khoá chống trùng `survey|remind|<ks>|<user>|<ngày>|teams` → mỗi người tối đa một DM Teams / khảo sát / ngày.
- Thẻ khảo sát ở `/khao-sat` và dòng "Lượt quay tiếp theo" trong popup trang chủ có hộp quà: trỏ chuột / chạm để xem danh sách quà (`prizes` = tên + số lượng).
