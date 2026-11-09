# Trung tâm Dữ liệu (`/du-lieu`) — đợt 1

Mọi team gửi yêu cầu dữ liệu (Power BI, crawl, xử lý dữ liệu…) **thẳng cho team Data** và theo dõi tới đâu;
team Data nhận việc, điều phối, đổi hạn có lý do; người gửi nghiệm thu. Đồng bộ **hai chiều với /pm**.
PO Hoàn chốt 09/11/2026 (spec + mockup `mockup_trung_tam_du_lieu.html`). Đợt 2 (Data availability, đề xuất crawl,
kế hoạch DA, độ tươi, thư viện báo cáo) và đợt 3 (sửa + duyệt quy tắc, chuyển phiếu Data Request cũ) cắm vào
cùng mô hình — xem cuối file.

## Trang

| Route | Ai | Nội dung |
|---|---|---|
| `/du-lieu` | mọi nhân viên | KPI · lọc (tìm, loại, team, đang mở/tất cả/đã xong, chỉ của tôi) · **Danh sách \| Gantt** (`?xem=gantt`) · `+ Tạo yêu cầu` · popup chi tiết giữa màn hình (`?ma=DR-2026-0001`) |
| `/du-lieu/dieu-phoi` | team Data + System Manager | kanban: Chờ tiếp nhận (vị trí hàng đợi, nút **Nhận**) · Đang xử lý (+ chờ nghiệm thu) · Tạm dừng – chờ người gửi (**Tiếp tục**) · Xong 7 ngày |
| `/du-lieu/quy-tac` | team Data + người duyệt quy tắc | bảng quy tắc đang áp dụng (chỉ đọc ở đợt 1) + lịch sử phiên bản |
| `/du-lieu/san-co` | mọi nhân viên | **Data availability** (đợt 2): KPI độ phủ, ma trận, độ tươi, “Cần bổ sung”, đề xuất data cần crawl; `?xem=thu-vien` Thư viện báo cáo — xem mục “Đợt 2” cuối file |

Thư mục www không được có gạch ngang → `www/du_lieu/` + 4 `website_route_rules` (hooks.py, nối cuối file).
Mọi trang `no_cache = 1`. Trạng thái đầu vẽ sẵn ở server (KPI, bảng đã sắp và đã lọc "Đang mở", kanban) — không chớp.
Asset `public/js/ec_data_hub.bundle.js` + `public/css/ec_data_hub.bundle.css` **chỉ nạp trên 4 trang này**
(`pages.asset_url`: bản băm của `bench build` qua `assets.json`, chưa build thì tệp gốc `?v=md5`) — không vào `web_include_js`.

Menu: ngữ cảnh shell `data_hub` thuộc khu **Báo cáo**; nhóm **Dữ liệu** trong `RAIL_LAYOUTS["reports"]` (luật A73).
"Điều phối" và "Quy tắc thời hạn" là mục registry `visible_when: role:EC Data Team` (UX; trang tự kiểm quyền).

## Luật (PO chốt 09/11/2026)

- **Công khai**: mọi nhân viên (hồ sơ Employee Active) đọc mọi yêu cầu, nhật ký, trao đổi, tệp. Không có chế độ riêng tư.
- **Gửi thẳng team Data**, không qua trưởng phòng. Mức **Khẩn** người gửi chỉ *đề xuất* + lý do bắt buộc; team Data
  **xác nhận hoặc hạ mức** khi nhận (ghi nhật ký "Đổi ưu tiên").
- **Trạng thái**: Chờ tiếp nhận → Đang xử lý ⇄ Tạm dừng (chờ người gửi) → Chờ nghiệm thu → Hoàn tất (Đạt / Đạt tự động);
  Chưa đạt (+ lý do) mở lại về Đang xử lý; Huỷ (người gửi khi còn Chờ tiếp nhận; team Data bất cứ lúc nào, lý do bắt buộc).
- **Hạn = ngày bắt đầu + N ngày làm việc** (không tính chính ngày bắt đầu; bỏ T7/CN + ngày lễ trong Holiday List mặc
  định của công ty). `N = ceil(số ngày theo loại × hệ số ưu tiên)`, tối thiểu 1. Đổi hạn (ở đây hoặc khi nhận lệch
  quy tắc) **bắt buộc lý do**, người gửi thấy. Hạn nhận việc = ngày gửi + 1 ngày làm việc ("Tiếp nhận yêu cầu mới").
- **Tạm dừng**: đồng hồ hạn dừng. Tiếp tục → hạn cộng thêm số ngày làm việc *x* với `ngày dừng < x ≤ ngày tiếp tục`
  (dừng và tiếp tục trong ngày = 0). Bấm Hoàn tất khi đang tạm dừng thì tính tiếp tục trước.
- **Nghiệm thu**: team Data Hoàn tất → Chờ nghiệm thu; người gửi Đạt / Chưa đạt. Không phản hồi **3 ngày làm việc** →
  "Đạt (tự động)" (job 09:00). **% đúng hạn** = số việc Hoàn tất trong tháng có `ngày team Data hoàn tất ≤ hạn đã chốt`
  (kể cả hạn đã dời có lý do) / số việc Hoàn tất trong tháng.
- **Hàng đợi + ngày bắt đầu dự kiến** (chỉ yêu cầu Chờ tiếp nhận, `domain.queue`):
  1. mỗi người team Data rảnh từ `max(hôm nay, hạn muộn nhất của việc Đang xử lý / Tạm dừng của họ)` (việc quá hạn coi như rảnh từ hôm nay);
  2. yêu cầu chờ xếp theo (Khẩn > Cao > Bình thường > Thấp — mức team Data đã chốt, chưa chốt thì mức đề xuất; rồi giờ gửi);
  3. lần lượt giao cho người rảnh sớm nhất (bằng nhau → theo tên): bắt đầu dự kiến = ngày rảnh đó, người đó rảnh lại từ
     `bắt đầu + N ngày làm việc`. Không có ai trong team → xếp nối nhau trên một làn chung.
- **KPI**: Đang xử lý · Chờ tiếp nhận · Quá hạn (Đang xử lý quá hạn + Chờ tiếp nhận quá hạn nhận) · Tạm dừng · Xong tháng này (+ % đúng hạn).
- **Sắp xếp danh sách**: Khẩn trước → quá hạn → hạn gần nhất → gửi trước; Chờ nghiệm thu sau các việc đang chạy; đã đóng cuối
  (`domain.sort_key` = `sortKey` trong bundle — test khoá hai bên khớp nhau).

## Quyền

| Việc | Ai |
|---|---|
| đọc (trang, popup, Gantt, tải tệp) | nhân viên Active, team Data, System Manager |
| gửi yêu cầu, theo dõi / bỏ theo dõi | như trên |
| nhắn tin (@tên, tệp) | người gửi, người xử lý, người theo dõi, team Data, System Manager (người khác bấm "Theo dõi" để tham gia) |
| nghiệm thu Đạt / Chưa đạt | người gửi (System Manager hỗ trợ) |
| huỷ | người gửi khi Chờ tiếp nhận; team Data / System Manager bất cứ lúc nào + lý do |
| nhận việc, đổi người / ưu tiên / ngày bắt đầu / hạn, tạm dừng, tiếp tục, hoàn tất | team Data (role trong Settings, mặc định `EC Data Team`) + System Manager |

Mọi DocType chỉ System Manager có quyền Desk (không create/delete); mọi quyền kiểm ở `service` / `ops_service`.
Đọc lại có khoá dòng (`repository.lock` = `SELECT … FOR UPDATE`) trước mọi chuyển trạng thái — hai người bấm "Nhận" cùng lúc thì người sau nhận lỗi.

## Lớp

`constants` → `domain` (thuần: ngày làm việc, hệ số, tạm dừng, hàng đợi, KPI, sắp xếp, Gantt, kanban) →
`repository` (chỗ DUY NHẤT chạm DB) → `service` (nhân viên + phần đọc / trang) · `ops_service` (team Data; `apply_*` =
bước ghi dùng chung cho mọi đường: trang, /pm, job) · `pm_sync` + `pm_gateway` (đồng bộ /pm) · `notify` (thông báo + job 09:00) →
`api.py` (whitelist, user từ phiên, trả `{success, message, data}`) và `www/du_lieu/*` (`pages.py`: shell, asset, đăng nhập).

DocTypes (module **Data Hub**): `EC Data Ticket` (+ bảng con `EC Data Ticket Follower`, `EC Data Ticket File`) ·
`EC Data Ticket Log` (nhật ký, chỉ thêm) · `EC Data Ticket Message` (trao đổi) · `EC Data Hub Settings` (Single) ·
`EC Data SLA Rule Set` (+ `EC Data SLA Rule Item`). Patch `data_hub/patches/p001_seed_data_hub` (đánh số riêng của module):
role `EC Data Team`, bộ quy tắc v1 "Đang áp dụng", Settings (role, người duyệt quy tắc, project /pm, bộ quy tắc),
project /pm "Trung tâm Dữ liệu" (qua `pm.api.projects.create`). Chạy lại được, không ghi đè, không bao giờ chặn migrate.
Không có email nào trong code: người duyệt quy tắc là dữ liệu seed trong patch, sửa ở `/app/ec-data-hub-settings`.

## Đồng bộ /pm (hai chiều)

Trung tâm → /pm (qua `pm_gateway`, dùng **service của PM**: `tasks.create / update / set_status`, chạy dưới
`Administrator` vì quyền đã kiểm ở đây; form_dict được làm rỗng để `tasks.update` không đọc nhầm tham số của request này):

| Ở Trung tâm | Ở /pm |
|---|---|
| team Data **Nhận** | tạo Task trong `Settings.pm_project`: `[DR-…] tiêu đề`, người nhận, bắt đầu/hạn, ưu tiên (Khẩn=Urgent, Cao=High, Bình thường=Medium, Thấp=Low), mô tả có link `/du-lieu?ma=…`; Task → In Progress; lưu `ticket.pm_task` |
| đổi hạn / ngày bắt đầu / ưu tiên / người xử lý | sửa Task (đổi người: gỡ người cũ, giao người mới) |
| Hoàn tất | Task Done (chốt của PM vẫn áp: việc con / bước bắt buộc) |
| Chưa đạt (mở lại) | Task In Progress |
| Huỷ | Task Cancelled |
| ticket Đang xử lý mà chưa có task (lần tạo trước lỗi) | lần cập nhật sau **tạo bù** |

/pm → Trung tâm (ba hook, `hooks.py` nối thêm — không đè hook cũ):

| Hook | Bắt | Áp lên ticket |
|---|---|---|
| `Task.on_update` → `pm_sync.on_task_update` | mọi `doc.save()` (tasks.update, Desk) | đổi `exp_end_date` → đổi hạn (nhật ký "từ /pm", báo người gửi); đổi bắt đầu; trạng thái như dưới |
| `ec_pm_task_state_listeners` → `pm_sync.on_task_state` | `pm.task_flow.write_state` (set_status / mark_done ghi bằng `db.set_value` nên on_update **không** chạy) | Task Done → **Chờ nghiệm thu** (báo người gửi); Task mở lại khi ticket Chờ nghiệm thu → Đang xử lý; Task Cancelled → chỉ ghi nhật ký (huỷ yêu cầu cần lý do + báo người gửi, team Data làm ở đây) |
| `ToDo.after_insert` → `pm_sync.on_todo_insert` | giao Task cho người khác trên /pm | đổi người xử lý |

`ec_pm_task_state_listeners` là điểm nghe chung PM mở ra (6 dòng trong `pm/task_flow.py`) — PM không biết ai nghe.
**Chống vòng lặp**: mọi lần Trung tâm ghi sang /pm, và mọi lần áp thay đổi từ /pm, đặt `frappe.flags.ec_data_hub_pm_sync`;
ba hook thấy cờ thì bỏ qua. **Lỗi không làm hỏng thao tác chính**: lỗi /pm → Error Log + dòng "Lỗi đồng bộ /pm" trong
nhật ký + cảnh báo nhẹ trên trang; thay đổi ở Trung tâm vẫn lưu. Hook phía /pm nuốt mọi lỗi. Tắt đồng bộ:
`EC Data Hub Settings.pm_sync_enabled = 0` (khi đó Trung tâm tự báo người xử lý + tự nhắc hạn).

## Thông báo (`notify.py`, qua `notification_center` — chỉ event type có sẵn)

| Khi | Ai | Event |
|---|---|---|
| yêu cầu mới | mọi người team Data | `task_assigned` |
| nhận / đổi hạn / tạm dừng / tiếp tục / đổi người / huỷ / tin nhắn mới | người gửi + người theo dõi (+ người xử lý với tin nhắn) | `mention` |
| @tên | người được gọi | `mention` |
| Hoàn tất | người gửi ("Cần nghiệm thu") | `approval_required` |
| Chưa đạt | người xử lý + người theo dõi | `mention` |
| 09:00 ngày làm việc (`notify.daily`, bọc `gop_tin_job`) | người xử lý: sắp tới hạn (≤ 1 ngày làm việc) / quá hạn — **bỏ** yêu cầu đã có task /pm (PM tự nhắc) và người đang nghỉ; người gửi: nhắc nghiệm thu mỗi ngày, đủ 3 ngày làm việc → Đạt (tự động) | `task_due_soon` / `task_overdue` / `approval_required` |

Người thao tác không tự nhận thông báo của mình. Thông báo hỏng không làm hỏng thao tác (Error Log).

## Test

    python -m unittest ecentric_workspace.data_hub.tests.test_data_hub ecentric_workspace.data_hub.tests.test_pm_gateway
    node ecentric_workspace/data_hub/tests/js/test_ec_data_hub.mjs

- `test_data_hub`: domain (ngày làm việc + ngày lễ, hệ số, tạm dừng, hàng đợi, KPI, sắp xếp, Gantt, kanban), luồng đủ
  (tạo → nhận → đổi hạn → tạm dừng → tiếp tục → hoàn tất → chưa đạt → đạt / tự đóng / huỷ), **ma trận quyền**
  (12 việc × 7 vai), pm_sync hai chiều + chống vòng lặp + lỗi /pm, người nhận thông báo, job 09:00, render 4 trang
  bằng jinja2 (escape, tab theo vai, deep link, trạng thái server), hooks nối thêm, DocType, menu.
- `test_pm_gateway`: `pm_gateway` chạy THẬT trên `pm.api.tasks` với frappe giả của bộ test PM (`_pm_fake`) — tạo /
  sửa / giao / đổi trạng thái, form_dict không lọt, listener `write_state`, đầu-cuối /pm Xong → ticket Chờ nghiệm thu.
- jsdom (`tests/js/test_ec_data_hub.mjs`, cổng QC chạy qua `approval_center/tests/js/test_data_hub_bundle.mjs`):
  chạy bundle trên HTML THẬT (`tests/js/fixtures/*.html` render từ bộ mẫu; `TestFixtures` khoá fixture không cũ —
  sinh lại: `EDH_UPDATE_FIXTURES=1 python -m unittest ecentric_workspace.data_hub.tests.test_data_hub`).
- Bản xem thử tự chứa cho PO: `python -m ecentric_workspace.data_hub.tests.build_preview ra.html`.

**Không kiểm được ngoài bench** (thử trên site sau deploy): `SELECT … FOR UPDATE`, `as_system()` khôi phục phiên,
tải tệp private, `bench build` sinh `ec_data_hub.bundle.*` vào `assets.json`, Teams theo event type.

## Đợt 2 / đợt 3 cắm vào đâu

- **Đợt 2 — Data availability**: DocType mới `EC Data Availability`, `EC Data Proposal`, `EC Report Library` (module Data Hub).
  Kế hoạch bổ sung = `EC Data Ticket` **kind=`availability`** (dãy `DA-.YYYY.-.####` đã khai; trường `platforms`, `channels`,
  `method`, `availability_rows` đã có) → tự lên Gantt (thanh xanh ngọc `css=da`, cạnh tên "N yêu cầu + M bổ sung data"),
  tự tạo task /pm, cùng luồng nhận / hạn / hoàn tất. Thêm `ops_service.plan_availability` + hook "Hoàn tất" cập nhật ô ma trận.
  Duyệt đề xuất crawl dùng quy tắc `proposal_review` (đã seed). Trang `/du-lieu/san-co` thay template "Sắp có".
  Gợi ý "đã có dashboard tương tự" khi gõ tiêu đề: API mới đọc `EC Report Library`, gắn vào form tạo.
- **Đợt 3 — Quy tắc**: `EC Data SLA Rule Set` đã có trạng thái Draft / Chờ duyệt / Đang áp dụng / Từ chối / Hết hiệu lực,
  `proposed_by / reason / decided_by / decided_at / supersedes`; `Settings.rule_approver` đã seed. Thêm `rules_service`
  (sửa → gửi duyệt → duyệt: bản cũ "Hết hiệu lực", `Settings.active_rule_set` trỏ bản mới). Yêu cầu đã lưu `rule_version`
  nên quy tắc mới chỉ áp cho yêu cầu mới.
- **Đợt 3 — Phiếu Data Request cũ**: `EC Data Ticket.legacy_ref` giữ mã phiếu `EC Data Request`; patch chuyển dữ liệu
  + thẻ "Data Request" trong Approval Center trỏ `/du-lieu`.

## Đợt 2 — Data availability, đề xuất crawl, kế hoạch DA, độ tươi, Thư viện báo cáo (PO chốt 09/11/2026)

Lớp riêng, cắm vào đợt 1 (không viết lại): `avail_domain` (thuần) → `avail_repository` (`from repository import *`
+ hàm `avail_* / proposal_* / library_*`, vẫn là chỗ DUY NHẤT chạm DB) → `avail_service` → `api.py` (mục “dot 2”
cuối file) và `www/du_lieu/san_co.*` + `templates/includes/data_hub/avail_macros.html`. JS: IIFE thứ hai cuối
`ec_data_hub.bundle.js` (`ECDataHub.avail`, dùng lại App đợt 1: popup, toast, overlay, khoá nút). CSS nối cuối bundle.

DocTypes (module Data Hub, chỉ System Manager trên Desk, không create/delete): `EC Data Availability`
(team, data_type, platform, in_sharepoint / in_dw / in_powerbi, front_priority, note, last_updated, frequency,
data_owner, planned_ticket), `EC Data Proposal` (`DP-YYYY-####`: team, data_type, platforms JSON, purpose, urgency,
urgency_note, proposer, status Chờ duyệt / Đã duyệt / Từ chối, due_at, decided_by/at, reason, resulting_ticket,
rule_version), `EC Report Library` (`RL-#####`: title, link, report_owner — không dùng `owner` vì là trường hệ thống —,
team, data_sources, from_ticket, tags, active, added_by). Patch `data_hub/patches/p002_seed_data_availability`:
52 dòng Excel của PO; dòng (team, loại, sàn) đã có thì giữ nguyên; từng dòng trong try → Error Log; không chặn migrate.

### Luật

- **Tên sàn chuẩn**: Shopee / TikTok / Lazada là 3 cột ma trận (nhập “tiktok”, “Tiktok” → “TikTok”); sàn khác
  (Boxme, Misa, GOV, Omisell, Oms Boxme…) vào cột **Khác** kèm tên — một nhóm có thể có nhiều sàn Khác.
- **KPI**: % dòng có trên SharePoint / Data Warehouse / Power BI (trên mọi dòng — seed = 73% / 73% / 40% như mockup),
  số đề xuất Chờ duyệt (và số quá hạn duyệt), số dòng trễ cập nhật.
- **Độ tươi**: chỉ xét dòng ĐÃ có dữ liệu và có tần suất định kỳ. Trễ khi “cập nhật lần cuối” cũ hơn: Theo giờ 24h ·
  Hằng ngày 48h · Hằng tuần 8 ngày · Hằng tháng 35 ngày (`C.FRESH_MAX_HOURS`, có biên độ vì ngày cập nhật do team
  Data ghi / DA ghi). Không định kỳ → không cảnh báo. Có tần suất mà chưa ghi ngày → “chưa ghi ngày cập nhật”.
- **Cần bổ sung** = data CHƯA CÓ: nhóm (team, loại) có ô không kênh nào (“Chưa có”) hoặc đang có kế hoạch, cộng đề
  xuất Chờ duyệt chưa có dòng trong bảng. Thiếu riêng một kênh (vd chỉ chưa có Power BI) KHÔNG vào danh sách — xem
  trên ma trận / lọc “Có chỗ chưa có”. Nguồn: Đề xuất đã duyệt > Đề xuất chờ duyệt > Thiếu trong bảng.
- **Đề xuất data cần crawl** (mọi nhân viên, tối đa 10/ngày): team, loại, sàn (+ Khác), dùng để làm gì (bắt buộc),
  mức cần gấp (Bình thường / Cao / Khẩn) + ghi chú → Chờ duyệt; **hạn duyệt = cùng giờ sau N ngày làm việc** (quy tắc
  `proposal_review` của bộ đang áp dụng, mặc định 1); báo cả team Data (`approval_required`). Bảng hiện đếm ngược
  “còn 4h” / “quá hạn 3h”. Job 09:00 ngày làm việc (`avail_service.daily`, `gop_tin_job`) nhắc team Data đề xuất quá hạn
  (`task_overdue`, mỗi đề xuất / người / ngày một tin).
- **Duyệt** (team Data): tạo dòng trống cho sàn đề xuất nếu chưa có → hiện trong “Cần bổ sung” với nguồn “Đề xuất đã
  duyệt”; báo người đề xuất. **Từ chối** bắt buộc lý do (người đề xuất thấy trên bảng + nhận thông báo). Khoá dòng đề xuất
  trước khi quyết; đề xuất đã xử lý thì người bấm sau nhận lỗi.
- **Lên kế hoạch** (team Data, từ danh sách hoặc ô “Chưa có”): sàn, kênh đích, người xử lý (phải thuộc team), cách lấy
  (Crawl / API sàn / Nhập tay – file), bắt đầu (≥ hôm nay), kết thúc (mặc định quy tắc **Crawl data mới** × hệ số mức;
  mức = mức cần gấp của đề xuất nếu có), ghi chú. Tạo `EC Data Ticket` kind=`availability` (`DA-YYYY-####`,
  request_type “Crawl data mới”, platforms / channels / method / availability_rows JSON) ở Chờ tiếp nhận rồi gọi
  **`ops_service.accept`** của đợt 1 → task /pm, Gantt (thanh xanh ngọc “DA”, làn “N yêu cầu + M bổ sung data”),
  thông báo. Dòng ma trận gắn `planned_ticket` (ô hiện “Đang làm · hạn dd/mm”, bấm mở popup DA). Kiểm hết TRƯỚC khi
  tạo (không có ticket mồ côi); khoá dòng ma trận; ô đang có kế hoạch mở → từ chối kế hoạch thứ hai; các ô đã có đủ
  kênh chọn → từ chối. DA không vào bảng / KPI / kanban của Yêu cầu dữ liệu.
- **Người gửi của DA**: kế hoạch từ đề xuất đã duyệt → người đề xuất (`proposal.resulting_ticket` = mã DA);
  team Data tự lên → chính người lên kế hoạch.
- **Hoàn tất DA** (ở đây hoặc Task Done trên /pm): team Data tự lên → **Hoàn tất luôn**, không chờ nghiệm thu;
  từ đề xuất → **Chờ nghiệm thu** như yêu cầu thường (người đề xuất Đạt / Chưa đạt; 3 ngày làm việc tự Đạt). Khi DA
  sang Hoàn tất (`avail_service.on_ticket_closed`, gọi từ `ops_service.apply_done` / `apply_close`): các ô của DA bật
  ĐÚNG các kênh đã chọn, `last_updated` = lúc đó, người xử lý thành người phụ trách nếu dòng chưa có. Huỷ DA → ô trở lại
  “Chưa có” (kế hoạch chỉ “đang làm” khi ticket còn mở), lên kế hoạch lại được.
- **Sửa dòng ma trận** (team Data, bấm ô có dữ liệu hoặc “+ Thêm dòng”): kênh, ★ Front cần gấp, tần suất, người phụ
  trách, cập nhật lần cuối (nút “Bây giờ”), ghi chú. Không trùng (team, loại, sàn). Dòng vừa có dữ liệu lần đầu mà không
  ghi ngày → ngày = bây giờ. Không xoá dòng (giữ lịch sử; Version qua `track_changes`).
- **Thư viện báo cáo** (`?xem=thu-vien`): mọi người đọc mục đang dùng; team Data thêm / sửa / **ẩn – hiện lại**
  (không xoá). Link phải http(s), không trùng link; `from_ticket` phải tồn tại. Yêu cầu loại *Power BI mới* / *Sửa
  Power BI có sẵn* nghiệm thu **Đạt / Đạt (tự động)** có link kết quả → **tự thêm** (tiêu đề, link, người xử lý, team
  người gửi, dữ liệu dùng, từ yêu cầu) nếu link / yêu cầu chưa có trong thư viện. Popup yêu cầu Power BI hiện mục thư viện;
  đã đóng mà chưa có → team Data thấy “+ Thêm vào Thư viện báo cáo” (`?xem=thu-vien&tu=DR-…` mở form điền sẵn).
- **Gợi ý “đã có dashboard tương tự”** (form tạo yêu cầu, gõ tiêu đề ≥ 3 ký tự, debounce 350 ms, API `suggest`):
  bỏ dấu tiếng Việt + từ quá chung (dashboard, báo cáo, power bi, dữ liệu, theo, cho, brand…), giữ mục có ≥ 2 từ chung,
  hoặc 1 từ (≥ 3 ký tự) khi câu chỉ có 1–2 từ có nghĩa; xếp theo Jaccard; tối đa 3 mục thư viện (đang dùng) + 3 yêu cầu
  đang mở. Không dùng AI ngoài. Lỗi gợi ý → im lặng (gợi ý là phụ).

### Quyền (đợt 2)

| Việc | Ai |
|---|---|
| xem `/du-lieu/san-co` (ma trận, đề xuất, thư viện đang dùng), gửi đề xuất, gợi ý tiêu đề | nhân viên Active, team Data, System Manager |
| duyệt / từ chối đề xuất, lên kế hoạch DA, sửa / thêm dòng ma trận, thêm / sửa / ẩn báo cáo, xem báo cáo đã ẩn | team Data (role trong Settings) + System Manager |

Nút / hộp của team Data chỉ render cho team (boot JSON của nhân viên không có dữ liệu sửa); server vẫn kiểm từng API.

### API (`ecentric_workspace.data_hub.api.*`, POST cho mọi ghi)

`propose(data)` · `review_proposal(name, verdict, reason)` · `plan_availability(data)` · `plan_defaults(start_date,
priority)` (GET) · `save_availability(data)` · `save_library(data)` · `library_active(name, active)` · `suggest(q)` (GET).

### Test đợt 2

    python -m unittest ecentric_workspace.data_hub.tests.test_avail
    node ecentric_workspace/data_hub/tests/js/test_ec_data_hub_avail.mjs   # cũng chạy qua test_ec_data_hub.mjs

- `test_avail`: domain (tên sàn, seed 52 dòng = KPI mockup, ma trận + cột Khác nhiều sàn, Cần bổ sung, độ tươi,
  hạn duyệt + đếm ngược, kiểm nhập, gợi ý tiếng Việt), patch p002 (chạy lại không trùng, không ghi đè, dòng lỗi không
  chặn), đề xuất (hạn, thông báo, duyệt tạo dòng, từ chối cần lý do, giới hạn ngày, job nhắc), kế hoạch DA (luồng
  accept, Gantt, ô “Đang làm”, chặn trùng / ngày / người / đã đủ), hoàn tất (team tự lên đóng luôn, từ đề xuất chờ
  nghiệm thu, tự đóng, /pm Done, huỷ trả ô), thư viện (tự thêm, CRUD, ẩn), sửa dòng, **ma trận quyền 7 việc × 4 vai**,
  trang jinja (escape, vai, boot), hook / API POST / DocType khớp hằng số; fixture jsdom (`avail_*.html`,
  `index_suggest.html`, `avail_api.json`; sinh lại `EDH_UPDATE_FIXTURES=1`).
- jsdom: lọc ma trận / thư viện, đề xuất (kiểm nhập, chống bấm 2 lần, lỗi server), lên kế hoạch (từ danh sách + từ
  ô, điền sẵn đề xuất, hạn mặc định), sửa dòng, duyệt / từ chối, thư viện, gợi ý có debounce, CSS 390px.
- Bản xem thử PO: `python -m ecentric_workspace.data_hub.tests.build_preview data_hub_d2_preview.html` (bộ mẫu đợt 1 + 2).

**Không kiểm được ngoài bench**: `SELECT … FOR UPDATE` trên `tabEC Data Availability` / `tabEC Data Proposal`,
thứ tự `creation` (micro giây) của 52 dòng seed, kiểm `options: URL` của trường link Thư viện, Teams theo event type.

