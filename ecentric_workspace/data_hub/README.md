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
| `/du-lieu/san-co` | mọi nhân viên | “Sắp có” (đợt 2) — đã có chỗ trên menu / tab |

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

---

# Đợt 3 — Quy tắc thời hạn có người duyệt + chuyển phiếu Data Request cũ (09/11/2026)

## Sửa + duyệt quy tắc (`/du-lieu/quy-tac`)

Luồng: team Data **Sửa quy tắc** (bản nháp) → **Gửi <người duyệt> duyệt** (lý do bắt buộc) → người duyệt quy tắc
**Duyệt** / **Từ chối** (lý do bắt buộc). Người đề xuất **rút lại** được bản nháp / bản đang chờ duyệt.

| Trạng thái `EC Data SLA Rule Set` | Ý nghĩa |
|---|---|
| Draft | bản nháp của một người team Data (chỉ người đó / System Manager sửa, gửi, huỷ) |
| Chờ duyệt | đã gửi, `submitted_at`; quy tắc cũ vẫn chạy |
| Đang áp dụng | bản được duyệt (`effective_from` = ngày duyệt, `Settings.active_rule_set` trỏ tới) |
| Hết hiệu lực | bản đang áp dụng trước đó, khi bản mới được duyệt |
| Từ chối | `decided_by / decided_at / decision_note` = người duyệt + lý do |
| Đã huỷ | người đề xuất rút lại (giữ bản ghi — không xoá) |

- **Mỗi lúc MỘT thay đổi mở** (Draft hoặc Chờ duyệt). Người khác trong team thấy băng "X đang có bản nháp vN".
- Phiên bản: `version_no` = lớn nhất + 1 (`unique` → DB chặn trùng), tên `SLA-vN`; bản bị từ chối / huỷ vẫn giữ số
  (v2 từ chối → đề xuất sau là v3). `supersedes` = bản đang áp dụng lúc tạo nháp → lịch sử hiện **cũ → mới**.
- Kiểm nhập (`rules_domain.normalize_input`, JS `ECDataHubRules.validate` — test khoá hai bên cùng kết quả qua
  `fixtures/rules_api.json`): số ngày **nguyên 1..60** cho 7 mục; hệ số **0,25..3**, tối đa 2 chữ số thập phân
  (nhận dấu phẩy); mục không gửi = giữ giá trị đang áp dụng; không đổi gì → báo lỗi.
- **Người duyệt** = `EC Data Hub Settings.rule_approver` (dữ liệu, không có email trong code). Chưa cấu hình → chỉ
  System Manager duyệt được, và không gửi duyệt được (báo "Chưa cấu hình người duyệt quy tắc"). Khi đã cấu hình,
  System Manager **không** duyệt thay. Người duyệt đồng thời ở team Data tự đề xuất rồi tự duyệt được (PO là chủ quy tắc —
  ghi đủ dấu vết).
- **Chỉ áp cho yêu cầu MỚI**: yêu cầu lưu `rule_version` lúc gửi; `service.ticket_rules(t)` đọc đúng bộ đó cả khi team
  Data **Nhận việc sau ngày đổi quy tắc** (đợt 1 lúc nhận dùng bộ đang áp dụng — đã sửa) và cả gợi ý hạn trong hộp Nhận.
  Vị trí hàng đợi / ngày bắt đầu dự kiến vẫn ước tính bằng bộ đang áp dụng (chỉ là ước tính).
- Khoá: mọi ghi gọi `repository.lock_rules()` (`SELECT … FOR UPDATE` trên dòng Singles của Settings) rồi mới đọc lại
  trạng thái — hai người bấm cùng lúc thì người sau thấy trạng thái mới.
- Dấu vết: `proposed_by / reason / submitted_at / decided_by / decided_at / decision_note` + Version (track_changes)
  cho mọi lần sửa nháp.

| Thông báo (`notification_center`, event có sẵn) | Ai |
|---|---|
| gửi duyệt → `approval_required` (ERP + Teams), link `/du-lieu/quy-tac` | người duyệt quy tắc (Settings) |
| duyệt → `mention` ("áp dụng cho yêu cầu MỚI từ …") | người đề xuất + team Data |
| từ chối → `mention` (kèm lý do) | người đề xuất |
| rút lại bản đang chờ duyệt → `mention` | người duyệt quy tắc |

Trang: server vẽ sẵn bảng **Loại | Đang áp dụng | Đề xuất mới | Ghi chú** (ô đổi tô vàng `.edh-chg`), băng chờ duyệt /
bản nháp, nút theo vai, lịch sử v1, v2… (`<del>cũ</del> → <ins>mới</ins>`, người đề xuất / duyệt, lý do). Ô nhập số nằm
sẵn trong markup, CSS chỉ hiện khi bấm "Sửa quy tắc" (`.is-editing`). Xác nhận Duyệt / Từ chối / Rút lại / Huỷ nháp
bằng khung tại chỗ (không `confirm()`), chống bấm 2 lần. Người duyệt không có role team Data vẫn mở được trang
(tab hiện, link trong thông báo); mục menu trái "Quy tắc thời hạn" vẫn chỉ hiện cho role team Data (registry không
có điều kiện theo người dùng cụ thể).

Asset **riêng** `public/js/ec_data_hub_rules.bundle.js` + `public/css/ec_data_hub_rules.bundle.css`, chỉ nạp ở trang này
(`pages.ASSETS["rules_js" / "rules_css"]`, `www/du_lieu/quy_tac.py`), nạp SAU bundle chung và dùng `ECDataHub.call / busy`.

API (`api.py`, POST, user từ phiên): `save_rule_draft(data)` · `submit_rule(name, reason)` ·
`decide_rule(name, verdict=approve|reject, note)` · `cancel_rule(name, reason)`.

## Chuyển phiếu Data Request cũ

`migration.migrate_legacy(dry_run=1)` — bảng chuyển đổi ở `legacy.py` (thuần, test bảng):

| Phiếu cũ | Trung tâm Dữ liệu |
|---|---|
| request_type: Data accuracy, visualization, retrieval / New BI report / Historical data crawling | Xử lý dữ liệu / Power BI mới / Crawl data mới |
| Client onboarding, Client offboarding, Data training, Access, Other, (trống) | Khác (loại cũ ghi trong mô tả) |
| ưu tiên = mức CAO hơn của: urgency U0 Khẩn · U1 Cao · U2 Bình thường · U3 Thấp; importance I0 Cao · I1 Bình thường · I2/I3 Thấp | `proposed_priority` (+ `priority` nếu đã có người xử lý) |
| chưa gửi duyệt (không có EC Approval Request) | **bỏ qua** (nháp) |
| Pending / Information Required; Approved + Not Started/Assigned | Chờ tiếp nhận (hạn nhận tính từ ngày chuyển) |
| Approved + In Progress | Đang xử lý, người xử lý = `fulfillment_owner` (không có → Chờ tiếp nhận) |
| Approved + Completed | Hoàn tất · Đạt, `done_at = closed_at = completed_at`, `output_link` |
| Rejected / Cancelled | Huỷ, lý do = bình luận cuối của phiếu cũ |
| trạng thái lạ | bỏ qua, có trong báo cáo |

- Giữ: `legacy_ref` = mã cũ, tiêu đề, mô tả (+ khối "Thông tin từ phiếu cũ": loại, mức khẩn / quan trọng, ngày mong muốn,
  kết quả xử lý), người gửi, phòng ban, **giờ tạo = giờ gửi cũ**. Hạn = ngày của `fulfillment_due_at`, không có thì
  `expected_resolution_date` (không có cả hai → theo quy tắc từ ngày bắt đầu).
- Tệp: dòng `attachments` trỏ **đúng File cũ** (`file_url`) — không chép nội dung. `repository.file_content` tải được
  tệp đó chỉ khi File thuộc phiếu cũ mà ticket mang `legacy_ref` (không mở đường tải file bất kỳ).
- Nhật ký: mỗi `EC Approval Action` → "Lịch sử phiếu cũ" (giữ giờ gốc, người làm, cấp, bình luận; "Submitted" → "Tạo")
  + dòng "Chuyển từ phiếu cũ". Hai sự kiện mới được nối vào `LOG_EVENTS` + Select của `EC Data Ticket Log`.
- /pm: chỉ phiếu **Đang xử lý**, đồng bộ bật, chưa có task: task /pm có sẵn ghi mã cũ trong tiêu đề → gắn; không có → tạo
  qua `pm_sync.push_accept` (cổng của đợt 1). Phiếu đã đóng / chờ tiếp nhận: không tạo task.
- Không gửi thông báo, không sửa / xoá phiếu cũ. Mỗi phiếu một savepoint; phiếu đã có ticket → bỏ qua (chạy lại an toàn).
- Patch `data_hub/patches/p003_chuyen_phieu_data_request_cu` (post_model_sync): (1) `redirect_catalog()` (2) `migrate_legacy(dry_run=0)`.
  Không bao giờ chặn migrate; báo cáo vào logger `data_hub` (+ Error Log nếu có phiếu lỗi).
- System Manager: `api.legacy_migration_report` (GET, dry run — chỉ đọc) · `api.run_legacy_migration` (POST, chạy bù).

## Thẻ "Data Request" trong Approval Center → `/du-lieu`

- **Cấu hình, không phải code**: patch đổi `EC Approval Type DATA_REQUEST.route` → `/du-lieu` (chỉ khi route đang là route
  cũ — không đè route đã chỉnh tay; ghi comment trên bản ghi). Catalog `/approvals` mở `/du-lieu`.
- Link cũ dựng từ route (`<route>?id=EC-DATA-…`: Teams, chuông, Việc của tôi) thành `/du-lieu?id=…`; `/du-lieu` đọc
  `?ma=` **hoặc** `?id=` và `service.detail` / `resolve_code` nhận cả mã cũ (tra `legacy_ref`) → mở đúng ticket.
- Approval Center **từ chối gửi phiếu Data Request mới** khi thẻ trỏ ra ngoài `/approvals/`
  (`features/data_request/application/service.moved_route`) — trả route về `/approvals/data-request` là mở lại form cũ.
  Phiếu cũ đang "cần bổ sung" vẫn gửi lại được (resubmit không qua chốt này).
- Trang `/approvals/data-request` (sửa nguồn `ui/main_section.html` — 3 bước: BASELINE_SHA256 + SUPERSEDES,
  `resync_manifest.json`, patch `approval_center/patches/p358_resync_data_request_chuyen_trung_tam_du_lieu` = max dãy
  approval_center p348 + 10): băng "Data Request đã chuyển sang Trung tâm Dữ liệu" có sẵn trong markup; tab "Tạo yêu cầu"
  thành thẻ "Gửi Data Request mới tại Trung tâm Dữ liệu"; chi tiết phiếu cũ có "Xem trên Trung tâm Dữ liệu"
  (`/du-lieu?ma=<mã cũ>`).

## Test đợt 3

    python -m unittest ecentric_workspace.data_hub.tests.test_data_hub_d3
    node ecentric_workspace/data_hub/tests/js/test_ec_data_hub_rules.mjs          # cổng QC: approval_center/tests/js/test_data_hub_rules_bundle.mjs
    node ecentric_workspace/approval_center/tests/js/test_data_request_moved.mjs

- `test_data_hub_d3`: kiểm nhập (bảng giới hạn), diff, luồng nháp → gửi → duyệt / từ chối / rút lại, một thay đổi mở,
  quyền (team / người duyệt / System Manager / nhân viên), người nhận thông báo theo Settings, quy tắc mới chỉ áp cho
  yêu cầu mới (kể cả nhận việc sau ngày đổi), trang theo vai (jinja), bảng chuyển đổi phiếu cũ, dry run không ghi,
  chạy thật + chạy lại, savepoint, /pm chỉ cho việc đang làm, deep link mã cũ, thẻ catalog, chốt gửi phiếu mới, patch
  không bao giờ ném. Repo giả đợt 3: `tests/fake_d3.py` (gắn vào FakeRepo).
- Sinh lại fixture: `EDH_UPDATE_FIXTURES=1 python -m unittest ecentric_workspace.data_hub.tests.test_data_hub_d3`.

**Không kiểm được ngoài bench**: `SELECT … FOR UPDATE` trên `tabSingles`, `frappe.db.savepoint/rollback(save_point)`,
`ignore_links` khi người dùng cũ đã bị xoá, backdate `creation` bằng `db.set_value(update_modified=False)`, tải tệp cũ
qua `File.get_content()`, `bench build` sinh `ec_data_hub_rules.bundle.*`.
