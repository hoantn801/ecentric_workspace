# PM Recurrence — Self-Contained Redesign (Cách 2)

**Date:** 2026-08-04 · **Author session:** PM recurrence refactor · **Status:** DESIGN — awaiting Hoàn approval before build
**Trigger:** User feedback — "bỏ cái task mẫu đi, chỉnh sửa task/nhiệm vụ con trong quy tắc luôn, hơi cồng kềnh quá."

Locked decisions (Hoàn, 2026-08-04):
1. **Xoá task gốc** sau khi migrate (fallback = ẩn nếu xoá bị chặn bởi link).
2. **Subtask 1 tầng** (task chính + nhiệm vụ con trực tiếp, không lồng nhiều cấp).
3. **Chỉ giữ cửa A** — tạo mới tự chứa trong trang Recurring; bỏ nút "biến task đang có thành định kỳ".

North-star alignment (CLAUDE.md): clean data model (1 concept = 1 canonical DocType), maintainable, auditable, permission-aware. Production write (DocType + migrate) ⇒ **explicit confirm required before deploy**.

---

## 1. Vấn đề hiện tại

`PM Recurrence` hôm nay **trỏ tới 1 Task gốc** (`source_task`, reqd) và tùy chọn `checklist_template` (Link → `PM Checklist Template`). Máy sinh (`recurrence._clone`) dựng Task mới **từ Task gốc đó**: copy subject/description/priority/project/time-window + assignees + checklist (từ template) + labels.

Hệ quả cồng kềnh:
- Task gốc là **một Task thật lang thang** trong mọi danh sách → rác, khó hiểu.
- Muốn đổi nội dung task sinh ra phải **đi tìm Task gốc ở nơi khác** để sửa; modal quy tắc chỉ xem, không sửa được.
- Checklist mẫu nằm ở DocType thứ 3 (`PM Checklist Template`) → phân mảnh, "một khái niệm nằm ở 3 chỗ".

## 2. Mô hình dữ liệu mới (canonical)

`PM Recurrence` trở thành **tự chứa**: template sống ngay trong quy tắc, không còn Task gốc.

### 2.1 `PM Recurrence` — thêm field template (giữ nguyên field lịch)

Giữ nguyên: `frequency`, `start_date`, `next_run_date`, `end_date`, `max_occurrences`, `occurrences_done`, `last_task`, `last_run_date`, `status`, `project`.

**Thêm** (nội dung template, trước đây lấy từ `source_task`):
| Field | Type | Ghi chú |
|---|---|---|
| `template_subject` | Data (reqd) | tiêu đề task sinh ra |
| `template_description` | Text | mô tả |
| `template_priority` | Select (Low/Medium/High/Urgent — khớp Task) | |
| `template_assignees` | Small Text (JSON list email) | người thực hiện, snapshot vào mỗi task |
| `template_start_time` | Data/Time | pm_start_time (giờ trong ngày, tùy chọn) |
| `template_end_time` | Data/Time | pm_end_time |
| `template_duration_days` | Int (default 0) | exp_end = occ_date + duration (thay cho "copy khoảng cách start→end") |
| `pm_checklist_items` | Table → `PM Recurrence Checklist Item` | checklist mẫu |
| `pm_subtasks` | Table → `PM Recurrence Subtask` | nhiệm vụ con 1 tầng |
| `template_labels` | Small Text (JSON list label name) | nhãn snapshot |

**Deprecate** (giữ cột để migrate/audit, ngừng dùng):
- `source_task` → đổi `reqd:0`, không còn ghi mới; chỉ đọc trong migration. (Có thể xoá hẳn ở đợt dọn sau — KHÔNG xoá ngay để migration idempotent + audit.)
- `checklist_template` → ngừng dùng (nội dung được copy vào `pm_checklist_items`).

### 2.2 Child DocType `PM Recurrence Checklist Item`
`istable=1`, parent = PM Recurrence.
| Field | Type |
|---|---|
| `item_label` | Data (reqd) |
| `is_required` | Check |

### 2.3 Child DocType `PM Recurrence Subtask` (1 tầng)
`istable=1`, parent = PM Recurrence.
| Field | Type | Ghi chú |
|---|---|---|
| `subject` | Data (reqd) | |
| `description` | Small Text | |
| `assignees` | Small Text (JSON list) | tùy chọn; rỗng ⇒ theo task cha |
| `priority` | Select | tùy chọn |

> Không có `parent_subtask` / cây lồng — đúng quyết định "1 tầng con".

Permissions của 2 child DocType: chỉ **System Manager** (child table không cần DocPerm PM-role; ghi qua parent + service layer — giống pattern label DocTypes trong CLAUDE.md).

## 3. Logic sinh task (rewrite `_clone`)

`_clone(rule, occ_date)` build **hoàn toàn từ dữ liệu của chính rule**, KHÔNG đọc Task nào:

1. Tạo Task chính: `subject=template_subject`, `description`, `priority`, `project`, `exp_start_date=occ_date`, `exp_end_date=occ_date + template_duration_days` (nếu >0), `pm_start_time/pm_end_time`.
2. Assignees: `_assign_add(template_assignees, notify=0)`.
3. Checklist: append từ `pm_checklist_items` (snapshot, `is_done=0`).
4. Labels: insert `PM Task Label Assignment` từ `template_labels` (bỏ nhãn không tồn tại/không active — không fail sinh).
5. Subtasks (1 tầng): mỗi row `pm_subtasks` → tạo Task con với `parent_task = <task chính>`, `exp_start_date=occ_date`, assignees riêng (nếu có) hoặc kế thừa task cha.
6. Mỗi bước bọc try/except + `frappe.log_error` → **không bao giờ fail cả lần sinh** vì 1 phần phụ.
7. Giữ nguyên: deadlock-retry (đã có ở main), idempotent guard (`last_run_date == next_run_date`), advance `next_run_date`, cập nhật `occurrences_done`/`last_task`, chuyển `Completed` khi hết hạn/hết lượt.

Kết quả task sinh ra **giống hệt hiện tại**, chỉ khác nguồn dữ liệu (rule thay vì Task gốc).

## 4. Migration (patch mới `p0XX_recurrence_selfcontained.py`)

Idempotent, chạy khi `bench migrate`. Cho **mọi** rule (Active/Paused/Completed/Cancelled) còn `source_task` và chưa có `template_subject`:

1. Đọc `Task = source_task`. Snapshot vào rule:
   - `template_subject/description/priority/project/assignees/start_time/end_time`.
   - `template_duration_days` = (exp_end − exp_start).days nếu cả hai có, else 0.
   - `pm_checklist_items` ← ưu tiên checklist thật trên source Task (`pm_checklist`); nếu rỗng và rule có `checklist_template` → lấy items của template đó.
   - `pm_subtasks` ← các Task con trực tiếp (`parent_task = source_task`), 1 tầng.
   - `template_labels` ← `PM Task Label Assignment` của source Task.
   - `save(ignore_permissions=True)`.
2. **Xoá task gốc** (quyết định 1): `frappe.delete_doc("Task", source_task, ignore_permissions=True, force=1)` sau khi detach an toàn (xoá label assignment của nó, reparent subtask con về `None` trước khi xoá).
   - **Fallback an toàn:** nếu delete ném `LinkExistsError`/nested-set lỗi → KHÔNG để migration vỡ; gắn cờ ẩn (`disabled`/custom flag) + log, để dọn tay sau. Migration luôn chạy trọn.
3. Ghi log tóm tắt: `migrated=N, deleted=N, hidden=N`.

**Không đụng** tới các Task đã sinh trước đó (00318–00322…) — chúng là task thật, giữ nguyên.

`PM Checklist Template` DocType: **giữ lại** (không xoá — ngoài scope), chỉ cắt phụ thuộc từ recurrence.

## 5. API thay đổi (`recurrence.py`)

| Hàm | Thay đổi |
|---|---|
| `create(...)` | Nhận template fields + checklist items + subtasks (thay `source_task`). Validate + insert rule tự chứa. |
| `create_with_task(...)` | **Bỏ** (không còn tạo Task gốc). Cửa A gọi `create` trực tiếp. |
| `update_template(name, ...)` | **MỚI** — sửa inline mọi field template + checklist + subtasks của rule (permission qua `_manage`). Đây là "sửa task/subtask trong quy tắc luôn". |
| `get(name)` | Trả template fields + checklist items + subtasks để render editor (bỏ đọc `source_task`). |
| `list/get_for_task` | `get_for_task` (dựa source_task) → **bỏ/deprecate** (cửa B bỏ). `list` bỏ cột `source_task`, thêm `template_subject`. |
| `_clone/_process/run_due` | `_clone` rewrite (mục 3); `_process/run_due` giữ nguyên khung + deadlock-retry. |
| `pause/resume/cancel` | Giữ nguyên. |

Permission: mọi hàm giữ `require_pm_access` + `_manage` (owner/can_see_all). Bỏ phụ thuộc `can_view_task(source_task)` (không còn task gốc) → quyền dựa trên `owner`/project/role.

## 6. Frontend (`pm_app.html`)

1. **Modal quy tắc** từ *chỉ xem* → **editor sửa inline**: sửa tên/mô tả/độ ưu tiên/người làm/giờ + **checklist** (thêm/xoá dòng) + **nhiệm vụ con** (thêm/xoá, 1 tầng) → nút Lưu gọi `update_template`. Bỏ các field rối (sức khoẻ/tạo lúc/cập nhật gom vào 1 dòng nhỏ).
2. **Form tạo mới (cửa A)**: 1 form tự chứa — tên task + độ ưu tiên + người làm + checklist + nhiệm vụ con + tần suất + ngày bắt đầu/kết thúc (giờ/ngày để trong `<details>` như đã làm). Gọi `create`.
3. **Bỏ cửa B**: gỡ nút "biến task này thành định kỳ" ở task-detail + các nhánh gọi `create_with_task`/`get_for_task`.
4. Giữ nút **"Sinh ngay"** (`generate_now`) đã có.

## 7. An toàn & tương thích

- Migration **idempotent** (skip rule đã có `template_subject`); chạy lại nhiều lần vô hại.
- Xoá task gốc có **fallback ẩn** → migration không bao giờ nửa vời.
- Task đã sinh: **không đụng**.
- `source_task`/`checklist_template`/`PM Checklist Template`: giữ cột/DocType để audit + rollback; dọn ở đợt sau nếu muốn.
- Rollback: nếu cần, chỉ việc ngừng dùng field mới + khôi phục engine cũ (source_task vẫn còn dữ liệu ở rule chưa migrate — nhưng đã migrate thì task gốc đã xoá; nên **backup DB trước khi migrate prod** — sẽ ghi rõ trong bước deploy).

## 8. Kiểm thử

- `py_compile` toàn bộ .py; validate JSON DocType mới.
- jsdom test cho editor inline (thêm/xoá checklist + subtask, payload đúng) + create form.
- Migration **dry-run reasoning** + test idempotent (chạy 2 lần).
- Sinh thử: rule mới → "Sinh ngay" → task ra đủ checklist + 1 tầng subtask + assignees + labels.
- Regression: pause/resume/cancel, quyền user thường (không thấy rule ngoài scope).

## 9. Kế hoạch deploy (CẦN confirm — có `bench migrate`)

1. Build trên branch `feat/pm-recurrence-selfcontained` (base = origin/main mới nhất). **Không** deploy khi build.
2. Bạn duyệt bundle.
3. Deploy: **backup DB trước** → Frappe Cloud Apps → Update lên commit này → deploy tự chạy `migrate` (chạy patch backfill+xoá) → đẩy `pm_app.html` vào Web Page → Ctrl+Shift+R.
4. Verify prod: 1 rule cũ đã migrate (task gốc biến mất, nội dung nằm trong quy tắc), tạo rule mới, "Sinh ngay", test user thường.

---

### Ước lượng
Backend (2 child DocType + fields + migration + rewrite): vừa. Frontend (editor inline + create form + gỡ cửa B): phần lớn công. Tổng: 1 phiên build gọn, có test.

**→ Chờ Hoàn duyệt design này để bắt đầu build trên branch (chưa deploy).**
