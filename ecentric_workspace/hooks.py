from . import __version__ as app_version

app_name = "ecentric_workspace"
app_title = "eCentric Workspace"
app_publisher = "eCentric"
app_description = "Employee portal + approval workflow"
app_email = "it@ecentric.vn"
app_license = "MIT"

# Global asset includes (website context only)
# --------------------------------------------
# Notification Center is an app-owned, ERP-wide foundation. It must run on EVERY
# custom eCentric Workspace page that renders the shared shell (the website/portal
# context: /home, /overview, /approval, /tasks, /weekly-update, Team Pulse, Alert
# Center, HR/Resource pages, and any future custom page), not just the homepage.
#
# `web_include_js` loads a CONTENT-HASHED bundle (notification_center.bundle.js ->
# /assets/.../dist/js/notification_center.bundle.<hash>.js) so deploys bust the
# immutable /assets cache uniformly. It injects this asset into
# every website-rendered page exactly once. This is deliberately NOT `app_include_js`
# (that would load into Frappe Desk /app/* and bind to Desk's native bell, which we
# must never do). The asset itself bails out on /app/* and on pages with no eCentric
# bell, and is single-install guarded so the homepage (which also still carries the
# legacy per-page loader) never double-installs.
web_include_js = ["notification_center.bundle.js", "ec_shell.bundle.js", "ec_datepicker.bundle.js", "ec_formkit.bundle.js", "ec_webpush.bundle.js", "ec_alltab.bundle.js", "ec_aifill.bundle.js", "ec_khay.bundle.js"]

# ERP Shell v1 (Phase 1B pilot). Both assets are loaded site-wide via the same
# proven content-hashed-bundle mechanism as the Notification Center, but
# ec_shell.js is a hard NO-OP unless the page opts in with a
# `data-ec-shell="1"` marker node (Phase 1B: only the 4 approval pilot pages).
# Kill switch: site_config `ec_shell_disabled: 1` (fail-closed for the shell
# only; never affects Notification Center or any business logic).
web_include_css = ["ec_shell.bundle.css", "ec_datepicker.bundle.css", "ec_formkit.bundle.css", "ec_alltab.bundle.css", "ec_aifill.bundle.css"]

# Document Events
# ---------------
# Hook on doctype methods - approval side effects, validation, etc.

# doc_events = {
#     "Vendor Code Request": {
#         "on_update": "ecentric_workspace.hooks_handlers.vrq_on_update"
#     }
# }

# WR1A weekly obligation lifecycle (local-only until deployed).
doc_events = {
    "Weekly Team Update": {
        "on_update": "ecentric_workspace.weekly_report.events.on_weekly_update",
    },
    "ToDo": {
        "validate": "ecentric_workspace.weekly_report.events.validate_weekly_report_todo",
    },
    "File": {
        # 08/09 (Hoan): tep da ky so KHONG BAO GIO duoc xoa - moi duong, ke ca Administrator.
        # Cong cu quan tri co ly do that bat frappe.flags.ec_allow_signed_file_delete.
        "on_trash": "ecentric_workspace.platform.esign.file_guard.forbid_signed_file_delete",
    },
    "Task": {
        # G4.10: enforce PM transition rules on EVERY save path (API + generic apply_workflow).
        "before_save": "ecentric_workspace.pm.api.tasks.pm_task_transition_guard",
        # AC-1a: close assignment ToDos when a Task enters a terminal state
        # (keeps the shared Action feed / tabToDo hygienic).
        "on_update": "ecentric_workspace.pm.api.todo_lifecycle.pm_task_close_todos_on_terminal",
    },
    "PM Task Label": {
        # G4.9: block hard-delete of an in-use label on EVERY delete path (incl. Administrator).
        "on_trash": "ecentric_workspace.pm.api.labels.pm_label_before_delete",
    },
    "Employee": {
        # 14/09: ba lan trong hai tuan mot ho so Active duoc tao ma thieu `user_id`,
        # va ca ba lan nhan vien bao "loi phan mem cham cong". Hook nay tu dien
        # `user_id` tu email cong ty khi co the, khong thi hien canh bao - KHONG chan
        # luu (xem ly do trong hr/employee_guard.py).
        # PHAI la `before_validate`: hook doc_events chay SAU controller validate cua
        # Employee, ma chinh doan do moi dung `user_id` de tao User Permission.
        "before_validate": "ecentric_workspace.hr.employee_guard.autofill_user_id",
    },
    "PM Assignment Request": {
        # G5.0 B2: service-only mutation guard (rejects generic insert/update, incl. Administrator;
        # enforces append-only events) + hard-delete guard for decided audit history.
        "before_save": "ecentric_workspace.pm.api.assignment.pm_assignment_request_guard",
        "on_trash": "ecentric_workspace.pm.api.assignment.pm_assignment_request_before_delete",
    },
}

# Scheduled Tasks
# ---------------
# scheduler_events = {
#     "cron": {
#         "*/15 * * * *": [
#             "ecentric_workspace.tasks.sync_sharepoint_attendance"
#         ]
#     }
# }

# PM v2 recurring tasks: daily generation of due PM Recurrence rules.
# WR1A weekly obligations: daily idempotent generator (see
# ecentric_workspace.weekly_report.scheduler).
scheduler_events = {
    "daily": [
        "ecentric_workspace.sla.tasks.sync_attendance",
        "ecentric_workspace.pm.api.recurrence.run_due",
        # pm_overdue_scan / pm_due_soon_scan / wr_due_overdue_scan: chuyen sang cron 09:00
        # (04/10) - xem "Nhac viec 09:00" cuoi file.
        "ecentric_workspace.weekly_report.scheduler.generate_weekly_obligations",
    ],
    # Alert Center Phase E (decision D2-E): both jobs are dry-run-safe and
    # kill-switchable via site_config `ec_alerts_scheduler_disabled: 1`.
    "hourly": [
        "ecentric_workspace.sla.tasks.sync_weekly_reports",
        "ecentric_workspace.sla.tasks.sweep_overdue",
        "ecentric_workspace.alerts.tasks.expire_automation_pauses",
        # Doc lai moc sua tren SharePoint cho cac phieu CON CHO DUYET. Khong co no thi bang
        # canh bao "tep doi sau khi duyet" khong bao gio bat duoc mot lan sua that (15/09).
        # Frappe khoa Scheduled Job Type theo `method`, nen ten nay chi duoc xuat hien MOT lan
        # trong ca file - dat o hai cho thi chi con mot, khong log khong loi.
        "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror.lam_tuoi_moc_sua",
    ],
    "cron": {
        "*/10 * * * *": [
            "ecentric_workspace.alerts.tasks.process_action_queue_job",
            # Hotfix B (2026-06-13): durable failed-order retry. LIGHTWEIGHT cron
            # = enqueue dispatcher only. Dispatcher finds brands with due items
            # and enqueues <=1 per-brand worker (Redis brand lock); the worker
            # atomically claims + re-pulls each item. Nothing is claimed in the
            # cron/dispatcher (no item stuck Processing while only queued).
            # Same kill switch ec_alerts_scheduler_disabled / ec_alerts_pull_disabled.
            "ecentric_workspace.alerts.tasks.dispatch_order_retries",
            # Cong AI (28/09): ping moi model Kie mot cau ngan -> ti le thanh cong 60 phut.
            # Duoi 30% thi cong AI bo qua model do (Kie co status 24h nhung doi dang nhap web).
            "ecentric_workspace.platform.ai.health.ping_models",
        ],
        # Narrow Omisell pull scheduler (approved 2026-06-10): quadruple-gated
        # in tasks.scheduled_omisell_pull - runs nothing until site_config
        # ec_alerts_scheduled_pull_brands lists at least one brand.
        "*/15 * * * *": [
            "ecentric_workspace.alerts.tasks.scheduled_omisell_pull",
        ],
        # Notification Delivery v1: bounded Teams retry sweep. Idempotent -- only picks
        # up EC Notification Delivery Log rows (channel=teams, status=Failed) whose
        # next_retry_at is due and attempt_count < MAX_ATTEMPTS.
        "*/5 * * * *": [
            "ecentric_workspace.notification_center.providers.teams.process_teams_retries",
            # Cung co che cho web push: chi nhat lai dong Failed da den han thu lai.
            "ecentric_workspace.notification_center.providers.webpush.process_webpush_retries",
            # esign (2026-08-27): a leg the provider ACCEPTED but never acted on. Until now
            # the only backstop was sweep_stale at 24h - far too long on a live system that
            # signs real payment approvals, and indistinguishable from "provider is slow".
            "ecentric_workspace.platform.esign.tasks.flag_silent_legs",
            # esign S2A (2026-07-11): polling reconciler - AUTHORITATIVE status path
            # (Phase 1 works with polling only; callback is a later acceleration
            # signal). Kill-switched via site_config ec_esign_scheduler_disabled
            # (fail-safe: config read error => disabled). Inert until an esign
            # profile is enabled + gates opened.
        ],
        # poll_pending moved from */5 to */1 (2026-08-27). After "Duyệt & Ký" the screen shows
        # nothing until verification lands, so a five-minute worst case reads as a broken
        # button. The query is a single indexed lookup that returns nothing most minutes, and
        # it only reaches SCTS while a request is genuinely in flight - bounded by
        # max_poll_attempts. Kept separate from the */5 block so the reason stays visible.
        "*/1 * * * *": [
            "ecentric_workspace.platform.esign.tasks.poll_pending",
        ],
    },
}

# esign S2A: stale monitor + orphan-file scan share the same kill switch and are
# inert without enabled profiles.
scheduler_events["hourly"].append(
    "ecentric_workspace.platform.esign.tasks.sweep_stale")
scheduler_events["daily"].append(
    "ecentric_workspace.platform.esign.tasks.orphan_file_scan")
# Payment Request buoc 6: nhac Finance xu ly UNC tu D-3 truoc ngay thanh toan (07/09).
# Moi phieu mot lan/ngay; tat bang site_config ec_payment_unc_reminder_disabled.
# 03/10: chuyen sang 09:00 (cron ben duoi) - xem "Nhac viec 09:00".
# Chia dot: nhac nguoi de nghi tao phieu dot ke tu D-7 truoc ngay du kien.
# 03/10: chuyen sang 09:00 (cron ben duoi) - xem "Nhac viec 09:00".
# Booking Request: nhac Booking tu D-3 truoc NGAY DU KIEN XONG ma chinh ho cam ket luc
# nhan viec (11/09). Moi phieu mot lan/ngay; tat bang site_config ec_booking_reminder_disabled.
# 03/10: chuyen sang 09:00 (cron ben duoi) - xem "Nhac viec 09:00".
# esign S2B-C1: bounded retry (*/30) of signed-PDF retrieval for terminal-completed
# packages whose signed bundle is not yet complete. Safe GET/download only; never resends
# AddDocument/bulk-process. Same kill switch (ec_esign_scheduler_disabled) + per-provider
# integration gate (exits with zero SCTS calls while OFF).
# Luoi do nhom Phan hoi phe duyet - MOT LAN moi dem, khong phai hang gio:
# job nay ghi vao `EC SLA Obligation`, dung bang ma hook dong bo ghi ben
# trong giao dich duyet don cua nguoi dung. Hai ben cham nhau thi DB
# rollback ca giao dich duyet, va nguoi dung thay "Da duyet" trong khi ho
# so khong doi trang thai. 02:00 dua xac suat do ve gan khong.
# Gio cron o site nay la GIO DIA PHUONG (Asia/Ho_Chi_Minh) - xem ghi chu
# o cac cron esign phia duoi; KHONG quy ra UTC.
scheduler_events["cron"].setdefault("0 2 * * *", []).append(
    "ecentric_workspace.sla.tasks.sync_approvals")
# Nghi phep dung dong ho cua nhom Phe duyet. 02:10 - SAU sync_approvals
# (02:00), vi luoi do kia co the vua mo them dau viec va cam doan tam dung
# cho chung ngay trong dem thi tot hon doi them 24 tieng.
# Gio cron o site nay la GIO DIA PHUONG (Asia/Ho_Chi_Minh).
scheduler_events["cron"].setdefault("10 2 * * *", []).append(
    "ecentric_workspace.sla.tasks.sync_leave_pauses")
scheduler_events["cron"].setdefault("*/30 * * * *", []).append(
    "ecentric_workspace.platform.esign.tasks.retrieve_signed_bundles")

# PM time-blocking: remind users to confirm elapsed unconfirmed hours TWICE a day
# (site timezone Asia/Ho_Chi_Minh = Vietnam): 09:00 + 18:00.
# NOTE (2026-09-10): one method = ONE Scheduled Job Type (frappe sync_jobs keys by
# dotted method path), so two cron keys for the same method silently keep only the
# LAST one - measured live: a single record '0 18 * * *', the 09:00 run never
# existed. A comma cron list keeps both runs in a single registration.
scheduler_events["cron"].setdefault("0 9,18 * * *", []).append(
    "ecentric_workspace.pm.api.schedule.nudge_unconfirmed")

# Unanswered meeting invites: one nudge in the morning (one Graph call per active
# employee, skipped entirely when ec_pm_calendar_sync is off).
scheduler_events["cron"].setdefault("0 9 * * *", []).append(
    "ecentric_workspace.pm.api.schedule.nudge_unanswered_invites")

# Khao sat (01/10/2026): quay so may man / dua ve dich THEO GIO HEN - bao truoc 5 phut va chot
# ket qua dung gio. Mot truy van co chi muc tren draw_scheduled_at, gan nhu luon rong.
# Tat khan cap: site_config ec_survey_draw_disabled: 1.
scheduler_events["cron"].setdefault("*/1 * * * *", []).append(
    "ecentric_workspace.surveys.application.draw_service.tick")

# Permissions
# -----------
# PM v2 scopes every query in the SERVICE LAYER (ecentric_workspace.pm.api.*). That covers
# the SPA, but NOT the native Desk list, the ec_pm_time_block.task Link dropdown, or the
# native REST list (frappe.client.get_list) -- the E2E security audit (2026-09-01) showed a
# non-leader could list EVERY Task/Project company-wide through those. These hooks close that
# surface. Codebase audit: the app's own Python is all frappe.get_all (ignore_permissions),
# so GBS / Approval / notification / reporting are unaffected; the condition functions return
# "" (no restriction) for Administrator / System Manager / Management dept / PM Manager, so
# leaders and Desk power users are untouched.
#
# Weekly Team Update (2026-09-28): Custom DocPerm cho role Employee la read=1,
# if_owner=0 va khong co query condition -- moi nhan vien doc duoc moi bao cao
# tuan, ke ca cua nhom Management. Hai hook duoi thay the Server Script tam
# `ec_wtu_list_scope` bang code trong app (A57). Luat port nguyen tu script do.
permission_query_conditions = {
    "EC SLA Obligation": "ecentric_workspace.sla.permissions.obligation_query_conditions",
    "Task": "ecentric_workspace.pm.permissions.task_query_conditions",
    "Project": "ecentric_workspace.pm.permissions.project_query_conditions",
    # 28/09/2026 (VA_BAO_MAT muc 2): nguoi ngoai HR chi thay chinh minh trong list/report/
    # search Employee - chan do so TK / CCCD bang filter tren field permlevel cao. Thay cho
    # Server Script `ec_employee_list_scope` (disable script do sau khi deploy).
    "Employee": "ecentric_workspace.hr.privacy.employee_scope.employee_query_conditions",
    "Weekly Team Update": "ecentric_workspace.weekly_report.permissions.wtu_query_conditions",
}
has_permission = {
    "Task": "ecentric_workspace.pm.permissions.task_has_permission",
    "Project": "ecentric_workspace.pm.permissions.project_has_permission",
    "Weekly Team Update": "ecentric_workspace.weekly_report.permissions.wtu_has_permission",
}

# Ham cho Jinja trong Web Page
# ---------------------------
# Trang /weekly-update doc ban ghi bang `frappe.db.get_value` ngay trong
# template, voi ten lay tu `?view=`. Duong do KHONG di qua has_permission, nen
# phai tu kiem. Dua ham vao day de template goi duoc, thay vi chep luat vao HTML
# -- chep la co ba ban luat, va ban trong HTML se la ban khong ai sua khi doi.
jinja = {
    "methods": [
        "ecentric_workspace.weekly_report.permissions.can_view_weekly_record",
        # 29/09/2026 (NHIEU_LOP GD2): trang chu ve san dong thoi gian dung trang thai cho nguoi
        # CO quyen PM (dang tai lich) va KHONG co (khong bao gio co lich) - khong doan trong HTML.
        "ecentric_workspace.pm.permissions.has_pm_module_access",
    ],
}

# 28/09/2026 (VA_BAO_MAT muc 2, Hoan chot CHAN): tu choi list/count/search/export tren Employee
# neu filters / order_by / group_by nhac toi field nguoi goi khong doc duoc (lech permlevel
# hoac bi mask) - chan do so TK / CCCD bang `like '9%'`. Xem hr/privacy/filter_guard.py.
# auth_hooks CHU KHONG PHAI before_request (loi 28/09 17:10): before_request chay TRUOC
# validate_auth(), nen request dung API token luc do van la Guest -> moi filter bi chan (403).
# auth_hooks chay trong validate_auth(), SAU khi da xac thuc token / bearer / cookie.
auth_hooks = ["ecentric_workspace.hr.privacy.filter_guard.guard_employee_filters"]

# Override standard whitelisted methods
# -------------------------------------
# override_whitelisted_methods = {}
# Cong AI chung (28/09/2026). Trang chu, /weekly-update, /team-pulse goi hai ten nay; truoc
# day la Server Script goi thang Google. Frappe xet override TRUOC khi tim Server Script
# (frappe/handler.py execute_cmd), nen khong phai sua trang nao va script cu khong con chay.
# 28/09/2026 (VA_BAO_MAT muc 1, chat HR): lich su thay doi (Version) tra ve form duoc LOC theo
# permlevel cua nguoi xem. Ba ham goi ban goc cua Frappe y nguyen roi moi loc - hr/privacy/form_load.py.
override_whitelisted_methods = {
    "gemini_chat": "ecentric_workspace.platform.ai.chat.gemini_chat",
    "gemini_company_summary": "ecentric_workspace.platform.ai.company_summary.gemini_company_summary",
    "frappe.desk.form.load.getdoc": "ecentric_workspace.hr.privacy.form_load.getdoc",
    "frappe.desk.form.load.get_docinfo": "ecentric_workspace.hr.privacy.form_load.get_docinfo",
    "frappe.desk.form.save.savedocs": "ecentric_workspace.hr.privacy.form_load.savedocs",
}

# Fixtures
# --------
# Custom Fields owned by this app. Filtered so only these Custom Fields are
# exported/synced -- never every Custom Field on the site.
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["name", "in", [
            "Project-ec_department", "Project-ec_manager",
            # Phase 1b.3.1b: fulfillment-action marker on ToDo (p044) -- scopes the
            # fulfillment ToDo lifecycle so unrelated ToDos are never touched.
            "ToDo-ec_fulfillment",
            # PM v2 Batch G1 checklist foundation (created by p005_pm_checklist):
            "PM Recurrence-checklist_template", "Task-pm_checklist",
            # Brand consolidation (2026-07-28): native Brand is the single brand
            # master after Brand Approver was retired. ALL 16 ec_* Custom Fields on
            # Brand are app-owned and MUST ship as fixtures -- a bench built from
            # this app alone would otherwise get a Brand with no ec_status /
            # ec_kam_owner, and alerts.permissions.get_allowed_brands would fall
            # back to an EMPTY scope (every KAM sees zero brands, silently).
            # ec_kam_owner = daily KAM for marketplace alerts (Alert Center
            # decision D1) - NOT the approval manager.
            "Brand-ec_legacy_key",
            "Brand-ec_sect", "Brand-ec_brand_code", "Brand-ec_brand_name",
            "Brand-ec_status", "Brand-ec_parent_client", "Brand-ec_cb1",
            "Brand-ec_kam_owner", "Brand-ec_manager_email",
            "Brand-ec_leader_email", "Brand-ec_finance_email",
            "Brand-ec_sect2", "Brand-ec_approval_recipe", "Brand-ec_gbs_recipe",
            "Brand-ec_cb2", "Brand-ec_boxme_customer",
            # Booking Request (2026-09-11): moi brand co MOT ban Booking va MOT ban
            # Account phu trach, nen phieu booking giao duoc cho dung nguoi ma khong
            # can bang anh xa rieng. Brand ngoai do Account tu go tren form thi chinh
            # ho khai luon nguoi Booking ngay luc do va ta luu lai (y Hoan 11/09), nen
            # o binh thuong khong bao gio trong; Role EC Booking chi la luoi do cuoi.
            "Brand-ec_booking_owner", "Brand-ec_account_owner",
            "Brand-ec_brand_source", "Brand-ec_can_chuan_hoa",
            # C4b B7 (2026-08-03): buoc "Gui lai / Can sua" cho MSO / Sales Order /
            # Purchase Order. ec_revision_reason giu ly do nguoi duyet yeu cau sua,
            # ec_revision_count dem so lan. CHUNG KHONG PHAI TRANG THAI -- trang thai
            # duy nhat van la workflow_state cua Frappe Workflow. Nhan "Can sua" tren
            # trang /approval duoc suy ra tu (workflow_state == "Draft" VA
            # ec_revision_reason con noi dung), nen khong co cho nao luu trang thai
            # song song. Thieu 2 field nay thi ec_*_before_save se chan moi buoc
            # Pending -> Draft (bat buoc co ly do >= 10 ky tu) => phai ship cung nhau.
            "MSO-ec_revision_reason", "MSO-ec_revision_count",
            "Sales Order-ec_revision_reason", "Sales Order-ec_revision_count",
            "Purchase Order-ec_revision_reason", "Purchase Order-ec_revision_count",
            # HR MVP (2026-09): custom field cua module cham cong / nghi phep.
            # Truoc day CHUA nam trong fixtures -> rebuild site la mat sach, hong
            # ca luong 2 buoc (ec_approval_stage), appeal (ec_appeal_status) va
            # tracking di muon (ec_late_*). Ship cung ec_hr_* Server Script + trang.
            "Leave Application-ec_approval_stage", "Leave Application-ec_source_request",
            "Attendance-ec_late_reason", "Attendance-ec_late_status",
            "Attendance-ec_late_comment", "Attendance-ec_late_decided_by",
            "Attendance Request-ec_decided_by", "Attendance Request-ec_appeal_status",
            "Attendance Request-ec_decision_comment",
            # Phong ban SCTS (09/09/2026): ma phong ban ben cong ky so, dat tren chinh
            # ban ghi Department. Thieu field nay thi resolver luon lui ve gia tri co
            # dinh cua Profile va MOI tai lieu lai hien sai phong nhu truoc.
            "Department-custom_scts_department_id",
            # Phan loai chi phi tren de nghi thanh toan (09/09/2026, Hoan) - PnL doc de gom
            # nhom va chong dem trung luong. `ec_loai_chi_phi` la Link toi DocType
            # `EC Loai Chi Phi` (ship o fixture DocType ngay duoi) va la truong BAT BUOC khi
            # gui phieu: bench moi thieu no thi form DNTT chan gui va PnL mu tro lai. Ba
            # truong PHAI di cung nhau - ec_can_brand fetch tu danh muc va la dieu kien
            # an/hien cua ec_brand.
            "EC Payment Request-ec_loai_chi_phi", "EC Payment Request-ec_can_brand",
            "EC Payment Request-ec_brand",
            # GO 11/09/2026: `Brand-ec_phi_ql_pct` da bi xoa. No chi chua duoc MOT con so
            # cho ca brand, ma bang phi that cua Hoan co BBT-VN Shopee 2% va TikTok 18%,
            # cong them fix fee va muc thu toi thieu. Thay bang DocType
            # `EC Phi Quan Ly Brand` (fixture DocType ngay duoi).
            # Ma brand ben Fabric/PowerBI (11/09/2026). Bang anh xa phai o DAY chu khong
            # o trong notebook - de trong code thi them mot brand la phai sua code va
            # khong ai nho. ec_nmv_upsert tra: ten brand -> o nay -> ec_brand_code.
            "Brand-ec_fabric_code",
            # LUU Y (CnB xac nhan truoc khi them): cac field luong tren Employee cung
            # chua versioned -- ec_pit_10, ec_pit_luytien, ec_dong_bhxh, ec_mst_ca_nhan,
            # ec_so_nguoi_phu_thuoc, ec_allow_lunch/coffee/computer, ec_late_early_bank.
                    # LLM provider (2026-09-23). CHU Y: `ec_gemini_api_key` da nam trong
            # fixtures/custom_field.json tu truoc NHUNG khong co trong bo loc nay ->
            # mot lan `bench export-fixtures` se XOA no khoi file, va site moi se
            # thieu field trong im lang. Khai ca bon de xuat/nhap doi xung.
            "System Settings-ec_gemini_api_key",
            "System Settings-ec_llm_provider",
            "System Settings-ec_kie_api_key",
            "System Settings-ec_llm_model_kie",
            # Cong AI chung (28/09): model du phong CUNG ben Kie.
            "System Settings-ec_llm_model_kie_fallback",
            # EC Payment Request (2026-09-23): 4 field nay DA nam trong
            # fixtures/custom_field.json nhung THIEU o bo loc -> mot lan
            # `bench export-fixtures` la xoa chung khoi file, site dung moi
            # thieu field trong im lang. Cung loi voi nhom LLM da va hom nay.
            "EC Payment Request-ec_brand_moi",
            "EC Payment Request-ec_brand_ten",
            "EC Payment Request-ec_ky_chi_phi",
            "EC Payment Request-ec_vat_pct",
            # Ho so nhan su (28/09/2026, HO_SO_NHAN_SU_thiet_ke.md). L0: sub-department;
            # L1 (HR Manager / EC CnB): bien so xe, ma/noi KCB; L2 (+ HR User): laptop,
            # thang tang BHXH, bang hop dong. Quyen L1/L2 do patch hr p002 dam bao.
            "Employee-ec_sub_department", "Employee-ec_bien_so_xe", "Employee-ec_ma_kcb",
            "Employee-ec_noi_kcb", "Employee-ec_laptop", "Employee-ec_thang_tang_bhxh",
            "Employee-ec_hop_dong_section", "Employee-ec_contracts",
            # Thu vien tai lieu ISO (05/10/2026, iso_docs/README.md): 36 field ec_* tren
            # Quality Procedure (khong sua DocType goc). Patch iso_docs p001 cung tao neu thieu.
            "Quality Procedure-ec_sb_iso", "Quality Procedure-ec_doc_code",
            "Quality Procedure-ec_doc_type", "Quality Procedure-ec_department",
            "Quality Procedure-ec_parent_doc", "Quality Procedure-ec_cb_iso",
            "Quality Procedure-ec_doc_state", "Quality Procedure-ec_current_version",
            "Quality Procedure-ec_effective_from", "Quality Procedure-ec_approver",
            "Quality Procedure-ec_review_months", "Quality Procedure-ec_next_review",
            "Quality Procedure-ec_sb_draft", "Quality Procedure-ec_draft_version",
            "Quality Procedure-ec_change_kind", "Quality Procedure-ec_change_summary",
            "Quality Procedure-ec_changed_sections", "Quality Procedure-ec_cb_draft",
            "Quality Procedure-ec_drafter", "Quality Procedure-ec_dept_head",
            "Quality Procedure-ec_iso_reviewer", "Quality Procedure-ec_source",
            "Quality Procedure-ec_draft_pdf", "Quality Procedure-ec_draft_docx",
            "Quality Procedure-ec_sb_flow", "Quality Procedure-ec_mermaid",
            "Quality Procedure-ec_steps_json", "Quality Procedure-ec_sb_scope",
            "Quality Procedure-ec_company_wide", "Quality Procedure-ec_scope_departments",
            "Quality Procedure-ec_cb_scope", "Quality Procedure-ec_notify_home",
            "Quality Procedure-ec_notify_summary", "Quality Procedure-ec_home_announcement",
            "Quality Procedure-ec_sb_history", "Quality Procedure-ec_revisions",
]]],
    },
    # Ba DocType custom cua PnL dashboard (09-10/09/2026). Truoc day chi ton tai tren
    # production -> bench moi hoac site dung lai la mat sach: `EC Loai Chi Phi` mat thi
    # form DNTT chan gui (truong bat buoc tro toi mot DocType khong ton tai), va PnL het
    # gom nhom duoc. Schema di theo repo; RIENG 27 dong danh muc thi do patch
    # p173_seed_loai_chi_phi gieo va chi gieo dong CON THIEU, nen Finance sua tren site
    # khong bao gio bi migrate ghi de.
    # `EC NMV Ngay` (10/09/2026) giu doanh so thuan theo brand x SAN x NGAY, nap tu PowerBI
    # qua API `ec_nmv_upsert` hoac Data Import. Chi SCHEMA di theo repo - du lieu ngay thi
    # khong, vi no la so nghiep vu chay hang ngay.
    # `EC Phi Quan Ly Brand` (11/09/2026) giu MUC PHI: % tren NMV, fix fee moi thang, muc
    # thu toi thieu, co hieu luc tu-den. Dong ghi ro SAN thang dong "Tat ca san" - do la
    # cach duy nhat dien ta duoc BBT-VN (Shopee 2% + 20tr co dinh, TikTok 18%). Doi gia
    # thi THEM dong moi chu khong sua de len dong cu, neu khong so cua thang truoc sai
    # theo. Chi SCHEMA di theo repo; 12 dong muc phi la du lieu nghiep vu, Finance tu sua.
    {
        "dt": "DocType",
        "filters": [["name", "in", ["EC Loai Chi Phi", "EC Nhan Su Brand",
                                    "EC NMV Ngay", "EC Phi Quan Ly Brand",
                                    # Ho so nhan su 28/09/2026 (module HR, giu nhu tren site)
                                    "EC Employee Contract", "EC Sub Department"]]],
    },
    {
        "dt": "Role",
        # EC AI Formfill Pilot da nam trong role.json tu 16/09 nhung thieu o day -> export lai
        # se lam roi mat. EC Khay Pilot (28/09): mo dan tro ly Khay o goc moi trang.
        # EC AI Video Admin (05/10): quan tri prompt trang /ai-video (prompt chung + theo nhom SP).
        "filters": [["name", "in", ["PM Manager", "PM Member", "EC AI Formfill Pilot",
                                    "EC Khay Pilot", "EC AI Video Admin",
                                    "EC AI Usage Viewer"]]],
    },
    # HR MVP (2026-09): cac Server Script `ec_hr_*` va cac trang `/ec-hr/*` truoc
    # day chi song trong DB, khong co ban trong git -- rebuild site la mat sach
    # logic cham cong / nghi phep / luong. Ship duoi dang fixtures de version-control
    # va deploy lai duoc. Filter theo prefix nen chi cham vao cac record cua app nay.
    # LUU Y: sau khi vao fixtures, `bench migrate` dong bo DB TU FILE -- moi thay doi
    # logic sau nay nen sua trong repo roi migrate (hoac sua live xong export lai).
    {
        "dt": "Server Script",
        # or_filters (KHONG phai them mot muc Server Script thu hai): export-fixtures ghi moi
        # muc ra fixtures/server_script.json, muc sau se GHI DE muc truoc.
        # sso_update_employee / add_emp_additional_dept (28/09/2026, VA_BAO_MAT muc 4): hai API
        # sua ho so nguoi khac, nay chi SM / HR Manager / HR User goi duoc - dua vao git de
        # guard khong mat khi dung lai site.
        "or_filters": [["name", "like", "ec_hr_%"],
                       ["name", "in", ["sso_update_employee", "add_emp_additional_dept"]]],
    },
    # Nhan CCCD / BHXH va permlevel 1 cho ngay cap / noi cap (truoc day L0, ai cung doc duoc).
    # Employee-main-track_changes = 1: BAT LAI lich su thay doi sau khi da loc theo permlevel;
    # gia tri 1 chu khong xoa Property Setter.
    {
        "dt": "Property Setter",
        "filters": [["name", "in", [
            "Employee-date_of_issue-permlevel", "Employee-place_of_issue-permlevel",
            "Employee-passport_details_section-label", "Employee-passport_number-label",
            "Employee-date_of_issue-label", "Employee-place_of_issue-label",
            "Employee-health_insurance_no-label", "Employee-main-track_changes",
        ]]],
    },
    {
        "dt": "Web Page",
        "filters": [["route", "like", "ec-hr/%"]],
    },
]

# esign: soi lech chu ky 2 LUOT/NGAY (Hoan chot 09/09) - 08:30 va 14:30.
# Gio dia phuong: System Settings.time_zone = Asia/Ho_Chi_Minh, Frappe chay cron theo do
# (da doi chieu tren prod 09/09), nen KHONG phai quy ra UTC.
# CHI DOC + bao cho System Manager; khong bao gio tu dong dong bo chu ky. Dung chung kill
# switch ec_esign_scheduler_disabled voi cac task esign khac.
# HAI HAM KHAC NHAU, KHONG PHAI MOT HAM O HAI CRON: Frappe khoa Scheduled Job Type theo
# `method`, nen khai cung mot ham o hai bieu thuc chi giu lai MOT - luot 08:30 se bien mat
# khong bao gi. Do tren prod 10/09 dung nhu vay. Xem ghi chu day du o
# `platform/esign/tasks.py` ngay tren hai vo mong nay; test:
# `tests/standalone/test_hooks_cron_mot_method_mot_slot.py`.
scheduler_events["cron"].setdefault("30 8 * * *", []).append(
    "ecentric_workspace.platform.esign.tasks.sweep_provider_signature_drift_0830")
scheduler_events["cron"].setdefault("30 14 * * *", []).append(
    "ecentric_workspace.platform.esign.tasks.sweep_provider_signature_drift_1430")


# Nhac cham cong (2026-09-14). Han cham cong la 10:00; hai moc nhac 08:30 + 09:30.
# Gio cron o site nay la GIO DIA PHUONG (Asia/Ho_Chi_Minh) - da doi chieu tren prod,
# giong cac cron esign ben tren; KHONG quy ra UTC.
#
# HAI HAM RIENG, KHONG PHAI MOT HAM O HAI CRON: Frappe khoa Scheduled Job Type theo
# dotted path cua `method`, nen khai cung mot ham o hai bieu thuc cron chi giu lai MOT.
#
# Thay cho Server Script `ec_hr_checkin_reminder` (nay da disabled trong fixtures):
# ban Server Script chi tao duoc Notification Log trong app, khong goi duoc
# Notification Center nen khong bao gio ra duoc Teams / web push.
scheduler_events["cron"].setdefault("30 8 * * *", []).append(
    "ecentric_workspace.hr.checkin_reminder.remind_0830")
scheduler_events["cron"].setdefault("30 9 * * *", []).append(
    "ecentric_workspace.hr.checkin_reminder.remind_0930")

# Ra soat ho so Active thieu tai khoan dang nhap, bao cho HR Manager.
# 08:00 la co y: SOM HON moc nhac cham cong 08:30, de mot nguoi vao lam hom nay
# con kip duoc noi vao he thong truoc khi ho lo lan nhac dau tien.
scheduler_events["cron"].setdefault("0 8 * * *", []).append(
    "ecentric_workspace.hr.employee_guard.sweep_missing_user_id")
# --------------------------------------------------------------------------- #
# SLA: dong nghia vu ngay cong NGAY LUC cham cong
#
# Han cham cong la 10:00. Truoc dot nay, nghia vu chi duoc dong boi job chay
# moi dem, nen tu 10:00:01 den dem, mot nguoi da cham cong dung gio van bi bang
# diem doc ra thanh "Chua lam". Sai voi ca cong ty, moi ngay, va chi sai theo
# huong lam diem nguoi ta xau di.
#
# `sla.tasks.sync_attendance` (scheduler_events["daily"]) VAN GIU NGUYEN va van
# can: no la luoi do cho nhung lan hook truot, va la duong hoi to cho phieu nghi
# phep duyet muon. Hook nay khong thay the no.
#
# Ham duoc goi da nuot moi Exception (xem `sla.application.hooks`): no chay ben
# trong giao dich cham cong cua nguoi dung, nen mot loi lot ra se lam rollback
# CA lan cham cong.
# --------------------------------------------------------------------------- #
try:
    doc_events
except NameError:
    doc_events = {}

_SLA_CHECKIN_HOOK = "ecentric_workspace.sla.application.hooks.on_employee_checkin"
_sla_ec = doc_events.setdefault("Employee Checkin", {})
_sla_prev = _sla_ec.get("after_insert")
if _sla_prev is None:
    _sla_ec["after_insert"] = [_SLA_CHECKIN_HOOK]
elif isinstance(_sla_prev, str):
    if _sla_prev != _SLA_CHECKIN_HOOK:
        _sla_ec["after_insert"] = [_sla_prev, _SLA_CHECKIN_HOOK]
elif _SLA_CHECKIN_HOOK not in _sla_prev:
    _sla_prev.append(_SLA_CHECKIN_HOOK)

# --------------------------------------------------------------------------- #
# 25/09/2026 - Go role khoi mot nguoi thi cac dong duyet "Role: <role do>" con Pending
# cua ho tren phieu dang mo chuyen Skipped ngay (dong ToDo, loai dau viec SLA). Truoc do
# anh Lam van duyet duoc cap Finance cua EC-CTR-2026-00023 sau khi da bi go EC Finance.
# Xem approval_center/shared/workflow/role_pool.py. Ham nuot moi loi.
# --------------------------------------------------------------------------- #
_ROLE_POOL_HOOK = "ecentric_workspace.approval_center.shared.workflow.role_pool.on_user_update"
_rp_user = doc_events.setdefault("User", {})
_rp_prev = _rp_user.get("on_update")
if _rp_prev is None:
    _rp_user["on_update"] = [_ROLE_POOL_HOOK]
elif isinstance(_rp_prev, str):
    if _rp_prev != _ROLE_POOL_HOOK:
        _rp_user["on_update"] = [_rp_prev, _ROLE_POOL_HOOK]
elif _ROLE_POOL_HOOK not in _rp_prev:
    _rp_prev.append(_ROLE_POOL_HOOK)

# --------------------------------------------------------------------------- #
# 28/09/2026 - Tong hop cong ty hang tuan qua cong AI chung. Thay Server Script
# `auto_company_summary_weekly` (12:00 thu Hai, goi thang Google 2.5) - patch p214 tat
# script do. Chay 12:10 de khong chong gio voi cac job 12:00 khac.
# --------------------------------------------------------------------------- #
scheduler_events["cron"].setdefault("10 12 * * 1", []).append(
    "ecentric_workspace.platform.ai.company_summary.weekly_job")

# --------------------------------------------------------------------------- #
# 28/09/2026 (A65 / NHIEU_LOP giai doan 1.1) - Menu chung do SERVER dung luc render.
# Truoc day menu du phong "nuong" vao HTML tung trang luc sync nen lech moi khi registry
# doi (do 28/09: 7 kieu lech tren 59 trang). Hook nay dung lai DUNG vung .ec-shell-mount
# tu registry hien hanh; khong sua file trang, khong can sync. Menu khong theo nguoi nen
# cache trang giu nguyen. Kill switch: site_config `ec_shell_server_nav_disabled: 1`.
# Xem shell/server_nav.py.
# --------------------------------------------------------------------------- #
update_website_context = ["ecentric_workspace.shell.server_nav.fill_shell_mount"]

# --------------------------------------------------------------------------- #
# 28/09/2026 (A65 / NHIEU_LOP giai doan 1.2 + 1.3) - ec_api.js: MOT client goi app method
# cho moi trang web. GET giong nhau dang bay dung chung mot request (+ nho ngan khi nguoi
# goi xin); POST xin CSRF tuoi, gap CSRFTokenError thi xin lai va thu DUNG mot lan.
# KHONG boc window.fetch. Chi dinh nghia window.ecApi, khong tu chay gi.
# --------------------------------------------------------------------------- #
web_include_js.append("ec_api.bundle.js")

# --------------------------------------------------------------------------- #
# 28/09/2026 - Thiep "Chao mung thanh vien moi" len Teams luc 10:00 ngay onboard (Hoan chot
# gio). Doc New Staff Preparation co onboard_date = hom nay; gui qua Workflow webhook
# (site_config ec_onboard_welcome_webhook_url - webhook tao trong group chat NHOM CHUNG cua cong
# ty, KHONG phai kenh thong bao approval); moi phieu mot lan. Chay lai 10:15/10:30/10:45
# chi de gui bu phieu lan truoc loi (job idempotent). Popup trang chu (tu 08:30) khong can job;
# no cho khe widget trang chu (A65 muc 6). Tat: site_config ec_onboard_welcome_disabled.
# --------------------------------------------------------------------------- #
scheduler_events["cron"].setdefault("*/15 10 * * *", []).append(
    "ecentric_workspace.approval_center.features.new_staff_preparation.application.welcome.send_welcome_teams")

# --------------------------------------------------------------------------- #
# 29/09/2026 - Cho nghi /attendance-database (Web Page "attendance", tao 05/2026): ban tien than
# cua /ec-hr/attendance, khong menu, khong trang nao link toi, nguon chi nam trong DB va co khoi
# boc window.fetch (NHIEU_LOP brief_hr buoc 6). Hoan chot 29/09: cho nghi -> chuyen sang
# /ec-hr/attendance. 302 (khong 301) de trinh duyet khong nho vinh vien, muon mo lai chi can go
# dong nay. KHONG xoa / unpublish Web Page tren production.
# --------------------------------------------------------------------------- #
website_redirects = list(globals().get("website_redirects") or []) + [
    {"source": "/attendance-database", "target": "/ec-hr/attendance", "redirect_http_status": 302},
]

# 29/09/2026 (popup "Hom nay o eCentric", PO Hoan chot): trang chu ve san muc trang tri sinh nhat
# cho TUNG nguoi xem (ca cong ty Nhe / cung phong ban Vua / nguoi sinh nhat Ruc ro) va biet popup
# co gi de hien khong - tu truoc lan ve dau (A65 §5), khong doan trong HTML. Xem home_today/.
jinja["methods"].append("ecentric_workspace.home_today.jinja.home_today_celebration")

# --------------------------------------------------------------------------- #
# 29/09/2026 - Chot cong thang (Hoan chot, project doc claude/chot-cong-thang.md).
# Nhan vien chot truoc 12:00, leader chot team truoc 15:00 NGAY 2 thang sau (doi qua
# T7/CN/le). Ky dau: cong thang 9/2026 (han T6 02/10). Logic: hr/timesheet_close.
#   00:05 hang ngay : sinh dong EC Timesheet Close khi cua so chot mo (ngay 1).
#   08:35 hang ngay : nhac ngay 1 (ham tu loc ngay 1).
#   09:00 hang ngay : nhac ngay chot, chi nguoi chua chot (ham tu loc ngay chot).
# Tat nhac: site_config ec_timesheet_close_reminder_disabled.
# --------------------------------------------------------------------------- #
scheduler_events["cron"].setdefault("5 0 * * *", []).append(
    "ecentric_workspace.hr.timesheet_close.service.ensure_current")
scheduler_events["cron"].setdefault("35 8 * * *", []).append(
    "ecentric_workspace.hr.timesheet_close.reminders.remind_day1")
scheduler_events["cron"].setdefault("0 9 * * *", []).append(
    "ecentric_workspace.hr.timesheet_close.reminders.remind_close_day")

# --------------------------------------------------------------------------- #
# 29/09/2026 - Nghi viec: 00:30 hang ngay, nhan vien Active da qua ngay lam viec cuoi
# (Employee.relieving_date - Don nghi viec ghi luc duyet xong) -> status Left + khoa tai khoan
# (khong go role, khong xoa User Permission; ai giu System Manager thi chi bao, khong khoa).
# Tat khan cap: site_config ec_offboarding_lock_disabled. Xem hr/offboarding/.
# --------------------------------------------------------------------------- #
scheduler_events["cron"].setdefault("30 0 * * *", []).append(
    "ecentric_workspace.hr.offboarding.lock_left_employees_job.run")

# --------------------------------------------------------------------------- #
# 30/09/2026 - Moi Attendance phai co ca (Shift Type): Attendance tu duyet don nghi / duyet
# giai trinh truoc day KHONG co ca -> bang cong tach nguoi do thanh 2 dong. Xem
# hr/attendance_shift.py (+ patch hr.p003 dien ca cho du lieu cu).
# --------------------------------------------------------------------------- #
_ATT_SHIFT_HOOK = "ecentric_workspace.hr.attendance_shift.ensure_shift"
_att_ev = doc_events.setdefault("Attendance", {})
_att_prev = _att_ev.get("before_insert")
if _att_prev is None:
    _att_ev["before_insert"] = [_ATT_SHIFT_HOOK]
elif isinstance(_att_prev, str):
    if _att_prev != _ATT_SHIFT_HOOK:
        _att_ev["before_insert"] = [_att_prev, _ATT_SHIFT_HOOK]
elif _ATT_SHIFT_HOOK not in _att_prev:
    _att_prev.append(_ATT_SHIFT_HOOK)

# --------------------------------------------------------------------------- #
# 30/09/2026 - Phep duyet tre (>7 ngay) khong con duoc job dem SLA quet toi -> ngay nghi
# van hien "Chua lam". Duyet phep (on_submit, Approved) -> dong bo lai ngay cong SLA cua
# dung nhung ngay trong phieu. Xem sla/application/hooks.py + patch sla.p015.
# --------------------------------------------------------------------------- #
_SLA_LEAVE_HOOK = "ecentric_workspace.sla.application.hooks.on_leave_application_submit"
_sla_la = doc_events.setdefault("Leave Application", {})
_sla_la_prev = _sla_la.get("on_submit")
if _sla_la_prev is None:
    _sla_la["on_submit"] = [_SLA_LEAVE_HOOK]
elif isinstance(_sla_la_prev, str):
    if _sla_la_prev != _SLA_LEAVE_HOOK:
        _sla_la["on_submit"] = [_sla_la_prev, _SLA_LEAVE_HOOK]
elif _SLA_LEAVE_HOOK not in _sla_la_prev:
    _sla_la_prev.append(_SLA_LEAVE_HOOK)

# --------------------------------------------------------------------------- #
# 01/10/2026 - Bang cong HRMS (Monthly Attendance Sheet) them 2 cot "NV chot cong" /
# "Lead chot cong" cho CnB. Khong sua HRMS: lop Report goi execute goc roi gan cot; loi
# thi tra nguyen ket qua goc. Xem hr/timesheet_close/report_override.py.
# --------------------------------------------------------------------------- #
try:
    override_doctype_class
except NameError:
    override_doctype_class = {}
override_doctype_class.setdefault(
    "Report", "ecentric_workspace.hr.timesheet_close.report_override.EcReport")

# AI Video hang loat: day tiep du an dang chay / chay dem (10 phut). Tat bang site_config
# `ec_video_scheduler_disabled: 1`.
scheduler_events["cron"]["*/10 * * * *"].append(
    "ecentric_workspace.ai_tools.features.ai_video.application.scheduler.tick")

# Nut "Nhac nguoi xu ly" dung chung cho cac form approval (01/10). Mot asset, cac trang chi goi
# EcRemind.buttonHTML / EcRemind.run. Backend: approval_center/shared/requests/remind.py.
web_include_js.append("ec_remind.bundle.js")

# --------------------------------------------------------------------------- #
# 01/10/2026 - "Mac dinh du cong" (Employee.ec_full_cong): 06:05 hang ngay tu ghi Present
# cho ngay lam viec con trong, tu ngay 1 thang truoc toi hom nay. Nguoi bat co khong co SLA
# cham cong, khong bi nhac cham cong, khong can chot cong. Xem hr/full_cong.py + hr.p004.
# --------------------------------------------------------------------------- #
scheduler_events["cron"].setdefault("5 6 * * *", []).append(
    "ecentric_workspace.hr.full_cong.run_daily")

# --------------------------------------------------------------------------- #
# 01/10/2026 - Doi "Bao cao cho" tren ho so -> dong chot cong chua chot, giai trinh / don
# nghi dang cho quan ly chuyen sang quan ly moi. Xem hr/reports_to_sync.py. Nuot moi loi.
# --------------------------------------------------------------------------- #
_RT_HOOK = "ecentric_workspace.hr.reports_to_sync.on_employee_update"
_rt_emp = doc_events.setdefault("Employee", {})
_rt_prev = _rt_emp.get("on_update")
if _rt_prev is None:
    _rt_emp["on_update"] = [_RT_HOOK]
elif isinstance(_rt_prev, str):
    if _rt_prev != _RT_HOOK:
        _rt_emp["on_update"] = [_rt_prev, _RT_HOOK]
elif _RT_HOOK not in _rt_prev:
    _rt_prev.append(_RT_HOOK)

# --------------------------------------------------------------------------- #
# 01/10/2026 - Tin noi bo (/tin-noi-bo, PO Hoan chot, mockup v5). HR soan / dang bai cho nhan
# vien doc, phan chuyen muc, pham vi theo phong ban. Xem internal_posts/README.md.
#  * route: thu muc www khong duoc co gach ngang -> www/tin_noi_bo/ + 4 luat route. Route tinh
#    (viet-bai, quan-ly) dung TRUOC route slug; werkzeug cung uu tien route tinh.
#  * quyen doc: permission_query_conditions (danh sach / trang chu) + has_permission (mo bai,
#    tai tep private - File.has_permission di theo bai). Bai theo phong ban = phong do + con.
#  * /huong-dan (muc luc cu) -> chuyen muc Huong dan cua Tin noi bo. Bai /huong-dan/<slug> giu nguyen.
# --------------------------------------------------------------------------- #
website_route_rules = list(globals().get("website_route_rules") or []) + [
    {"from_route": "/tin-noi-bo", "to_route": "tin_noi_bo"},
    {"from_route": "/tin-noi-bo/viet-bai", "to_route": "tin_noi_bo/viet_bai"},
    {"from_route": "/tin-noi-bo/quan-ly", "to_route": "tin_noi_bo/quan_ly"},
    {"from_route": "/tin-noi-bo/<slug>", "to_route": "tin_noi_bo/bai"},
]
permission_query_conditions["EC Internal Post"] = "ecentric_workspace.internal_posts.permissions.query_conditions"
permission_query_conditions["EC Internal Post File"] = "ecentric_workspace.internal_posts.permissions.child_query_conditions"
permission_query_conditions["EC Internal Post Department"] = "ecentric_workspace.internal_posts.permissions.child_query_conditions"
has_permission["EC Internal Post"] = "ecentric_workspace.internal_posts.permissions.has_permission"
jinja["methods"].append("ecentric_workspace.internal_posts.jinja.internal_posts_home")
website_redirects = list(globals().get("website_redirects") or []) + [
    {"source": "/huong-dan", "target": "/tin-noi-bo?chuyen-muc=huong-dan", "redirect_http_status": 302},
]
# Anh AI khong duoc chon lam bia qua 3 ngay -> xoa (moi lan bam AI = 3 anh).
scheduler_events["daily"].append("ecentric_workspace.internal_posts.cover_ai.cleanup_unused")

# O nhap so tien dung chung (01/10): dau cham phan cach + can phai. Trang danh dau data-money.
web_include_js.append("ec_money.bundle.js")
web_include_css.append("ec_money.bundle.css")

# --------------------------------------------------------------------------- #
# 02/10/2026 - Vua bat "Mac dinh du cong" tren ho so -> ghi du cong ngay (khong doi job 06:05),
# huy SLA cham cong, tu chot cong cho nguoi do. Xem hr/full_cong.py. Nuot moi loi.
# --------------------------------------------------------------------------- #
_FC_HOOK = "ecentric_workspace.hr.full_cong.on_employee_update"
_fc_emp = doc_events.setdefault("Employee", {})
_fc_prev = _fc_emp.get("on_update")
if _fc_prev is None:
    _fc_emp["on_update"] = [_FC_HOOK]
elif isinstance(_fc_prev, str):
    if _fc_prev != _FC_HOOK:
        _fc_emp["on_update"] = [_fc_prev, _FC_HOOK]
elif _FC_HOOK not in _fc_prev:
    _fc_prev.append(_FC_HOOK)

# Nhac viec 09:00 (03/10/2026, Hoan): truoc chay "daily" = 00:00, tin Teams bat luc moi nguoi
# ngu. Nay 09:00 moi ngay; job tu bo nguoi dang nghi (cuoi tuan / le / nghi phep) qua
# approval_center/shared/workflow/ngay_lam_viec. Frappe khoa Scheduled Job Type theo method:
# ba method nay CHI duoc o day (da go khoi "daily" o tren).
scheduler_events["cron"].setdefault("0 9 * * *", []).extend([
    "ecentric_workspace.approval_center.features.payment_request.application.reminders.remind_unc_due",
    "ecentric_workspace.approval_center.features.payment_request.application.reminders.remind_next_installment",
    "ecentric_workspace.approval_center.features.booking_request.application.reminders.remind_booking_due",
    # 04/10 (Hoan): nhac task /pm qua han + sap den han, bao cao tuan qua han / sap han.
    "ecentric_workspace.pm.api.notifications.pm_overdue_scan",
    "ecentric_workspace.pm.api.notifications.pm_due_soon_scan",
    "ecentric_workspace.weekly_report.scheduler.wr_due_overdue_scan",
])

# --------------------------------------------------------------------------- #
# 04/10/2026 - Gop y cong ty (/gop-y, PO Hoan chot, mockup Ban 1). Thay muc "Gop y BGD (sap ra
# mat)". Nhan vien gui (co the an danh), phong Management - EC xu ly. Xem feedback/README.md.
#  * route: thu muc www khong duoc co gach ngang -> www/gop_y/ + 4 luat route; route tinh
#    (xu-ly, tong-quan) dung TRUOC route <code>.
#  * KHONG co has_permission / permission_query: moi DocType cua module chi System Manager doc
#    duoc, moi duong doc ghi di qua feedback/service.py (kiem nguoi gui / nguoi xu ly).
#  * gio cron o site nay la GIO DIA PHUONG (xem ghi chu nhac cham cong o tren).
# --------------------------------------------------------------------------- #
website_route_rules = list(globals().get("website_route_rules") or []) + [
    {"from_route": "/gop-y", "to_route": "gop_y"},
    {"from_route": "/gop-y/xu-ly", "to_route": "gop_y/xu_ly"},
    {"from_route": "/gop-y/tong-quan", "to_route": "gop_y/tong_quan"},
    {"from_route": "/gop-y/<code>", "to_route": "gop_y/chi_tiet"},
]
# Nhac han tra loi gop y: moi gio trong gio hanh chinh (phut 7 cho tranh dot :00).
scheduler_events["cron"].setdefault("7 9-17 * * 1-5", []).append("ecentric_workspace.feedback.notify.remind")
# Ban tin gop y thang truoc cho BGD: 08:45 ngay 1.
scheduler_events["cron"].setdefault("45 8 1 * *", []).append("ecentric_workspace.feedback.digest.monthly")

# --------------------------------------------------------------------------- #
# 03/10/2026 - Tin noi bo v6 (mockup v6, PO Hoan duyet): hen gio dang, gui kem Teams, AI viet
# giup, loc anh AI dinh chu, binh luan, xac nhan da doc. Xem internal_posts/README.md.
#  * Hen gio: job moi 5 phut dang cac bai toi gio (bai len tre toi da 5 phut).
#  * Xac nhan da doc: 09:00 moi ngay nhac nguoi chua xac nhan (1 ngay truoc han + dung ngay han).
#    Gio cron o site nay la GIO DIA PHUONG (Asia/Ho_Chi_Minh). Method khong trung o cron khac.
# --------------------------------------------------------------------------- #
scheduler_events["cron"].setdefault("*/5 * * * *", []).append(
    "ecentric_workspace.internal_posts.schedule.publish_due")
scheduler_events["cron"].setdefault("0 9 * * *", []).append(
    "ecentric_workspace.internal_posts.ack.remind_due")

# --------------------------------------------------------------------------- #
# 04/10/2026 - Bang tin + Cau lac bo (/bang-tin, PO Hoan duyet mockup v2). Mang xa hoi noi bo:
# nhan vien dang bai / anh / loi khen, CLB (de xuat -> HR duyet), su kien CLB (len popup "Hom nay").
# Tin noi bo / sinh nhat / khao sat / gop y hien lai TU MODULE GOC (khong luu ban sao). Xem social/README.md.
#  * route: thu muc www khong duoc co gach ngang -> www/bang_tin/ + 5 luat route; route tinh
#    (cau-lac-bo, quan-ly) dung TRUOC route <slug> / <name>.
#  * KHONG co has_permission / permission_query: moi DocType cua module chi System Manager (+ HR
#    Manager doc); moi duong doc / ghi di qua social/service.py (ai thay bai nao: domain.can_see).
#    Anh private, xem qua social.api.image.
# --------------------------------------------------------------------------- #
website_route_rules = list(globals().get("website_route_rules") or []) + [
    {"from_route": "/bang-tin", "to_route": "bang_tin"},
    {"from_route": "/bang-tin/cau-lac-bo", "to_route": "bang_tin/cau_lac_bo"},
    {"from_route": "/bang-tin/quan-ly", "to_route": "bang_tin/quan_ly"},
    {"from_route": "/bang-tin/cau-lac-bo/<slug>", "to_route": "bang_tin/clb"},
    {"from_route": "/bang-tin/bai/<name>", "to_route": "bang_tin/bai"},
]

# --------------------------------------------------------------------------- #
# 05/10/2026 - Thu vien tai lieu ISO, buoc 2 (nen du lieu + luong duyet). PO Hoan chot 04/10,
# mockup B rut gon + D. Tai lieu = Quality Procedure cua ERPNext (KHONG sua DocType goc): 36
# Custom Field ec_*, bang con EC Document Revision, Workflow "Tai lieu ISO" (patch iso_docs p001).
# Xem iso_docs/README.md.
#  * validate: kiem ma / pham vi / o thong bao; chuyen sang "Ban hanh" -> ghi lich su ban hanh.
#  * on_update: tich "Thong bao len trang chu" + toan cong ty -> EC Home Announcement qua
#    home_today/announce_service.py (idempotent theo phien ban, loi KHONG chan ban hanh).
#  * quyen: Employee co read + write (Custom DocPerm), has_permission / query thu hep lai.
#  * trang /tai-lieu, nhap goi, nhap file cu, AI: cac lan day sau.
# --------------------------------------------------------------------------- #
_ISO_EVENTS = {"validate": "ecentric_workspace.iso_docs.events.validate",
               "on_update": "ecentric_workspace.iso_docs.events.on_update"}
_iso_qp = doc_events.setdefault("Quality Procedure", {})
for _iso_evt, _iso_hook in _ISO_EVENTS.items():
    _iso_prev = _iso_qp.get(_iso_evt)
    if _iso_prev is None:
        _iso_qp[_iso_evt] = [_iso_hook]
    elif isinstance(_iso_prev, str):
        if _iso_prev != _iso_hook:
            _iso_qp[_iso_evt] = [_iso_prev, _iso_hook]
    elif _iso_hook not in _iso_prev:
        _iso_prev.append(_iso_hook)
permission_query_conditions["Quality Procedure"] = "ecentric_workspace.iso_docs.permissions.query_conditions"
permission_query_conditions["EC Document Revision"] = "ecentric_workspace.iso_docs.permissions.child_query_conditions"
permission_query_conditions["EC Document Department"] = "ecentric_workspace.iso_docs.permissions.child_query_conditions"
has_permission["Quality Procedure"] = "ecentric_workspace.iso_docs.permissions.has_permission"

# Nut "Chuyen nguoi xu ly" dung chung (05/10) - Hiring, Daily Target. Endpoint tu bind_fulfillment.
web_include_js.append("ec_reassign.bundle.js")

# 05/10/2026 - Thu vien tai lieu ISO, trang (/tai-lieu, PO Hoan duyet mockup D + B rut gon).
#  * route: thu muc www khong duoc co gach ngang -> www/tai_lieu/ + 3 luat route; route tinh
#    (quan-ly) dung TRUOC route <code>.
#  * doc trang qua frappe.get_list / has_permission (quyen o tren); ghi qua iso_docs/api.py.
website_route_rules = list(globals().get("website_route_rules") or []) + [
    {"from_route": "/tai-lieu", "to_route": "tai_lieu"},
    {"from_route": "/tai-lieu/quan-ly", "to_route": "tai_lieu/quan_ly"},
    {"from_route": "/tai-lieu/soan", "to_route": "tai_lieu/soan"},
    {"from_route": "/tai-lieu/<code>", "to_route": "tai_lieu/chi_tiet"},
]

# --------------------------------------------------------------------------- #
# 05/10/2026 - Outside Work da duyet -> Attendance "Present" cho ngay lam viec ben ngoai da qua
# (phieu duyet truoc cho ngay sau). Duyet xong cung ghi ngay qua engine handler.
# --------------------------------------------------------------------------- #
scheduler_events["cron"].setdefault("15 6 * * *", []).append(
    "ecentric_workspace.approval_center.features.outside_work.application.attendance.run_daily")


# --------------------------------------------------------------------------- #
# 05/10/2026 - Chat noi bo (Raven, PO chot A + C). O Tin nhan tren thanh tren do shell ve
# (fallback.render_chat_slot, server_nav luc render); ec_chat.js lo huy hieu + khay tha xuong,
# no-op khi trang khong co o. Trang A: www/chat. Tat: site_config ec_chat_disabled. Xem chat/.
# --------------------------------------------------------------------------- #
web_include_js.append("ec_chat.bundle.js")
web_include_css.append("ec_chat.bundle.css")


# --------------------------------------------------------------------------- #
# 06/10/2026 - Chat noi bo: "ruot" Raven tieng Viet + mau ERP. Chi dung trang /raven (chat/boot.py):
# extend_bootinfo phu ban dich vao boot; after_request chen 1 <link> CSS + 1 <script src> nho vao HTML.
# Khong doi ngon ngu tai khoan, khong sua Raven. Tat: site_config ec_chat_skin_disabled.
# --------------------------------------------------------------------------- #
extend_bootinfo = list(globals().get("extend_bootinfo") or []) + [
    "ecentric_workspace.chat.boot.extend_bootinfo"]
after_request = list(globals().get("after_request") or []) + [
    "ecentric_workspace.chat.boot.after_request"]

# "Cho toi duyet" - duyet nhanh tren dien thoai (06/10). Gan vao [data-ec-cho-duyet] (/viec-cua-toi).
web_include_js.append("ec_cho_duyet.bundle.js")
web_include_css.append("ec_cho_duyet.bundle.css")


# --------------------------------------------------------------------------- #
# 07/10/2026 - Chat noi bo: phieu trong chat (chat/phieu_gateway.py). Khong sua Raven, khong sua
# Approval Center. (1) the phieu trong chat mo trang /approvals thay vi Desk; (2) dan link phieu
# ERP -> tin nhan mang the phieu; (3) bot "Phieu duyet" nhan rieng thong bao phe duyet.
# Tat: site_config ec_chat_phieu_disabled (ca 3) / ec_chat_bot_disabled (chi bot).
# --------------------------------------------------------------------------- #
raven_document_link_override = list(globals().get("raven_document_link_override") or []) + [
    "ecentric_workspace.chat.phieu_gateway.document_link"]


def _ec_chat_add_doc_event(doctype, event, path):
    events = doc_events.setdefault(doctype, {})
    prev = events.get(event)
    if prev is None:
        events[event] = [path]
    elif isinstance(prev, str):
        events[event] = [prev, path] if prev != path else [prev]
    elif path not in prev:
        events[event] = list(prev) + [path]


_ec_chat_add_doc_event("Raven Message", "before_insert",
                       "ecentric_workspace.chat.phieu_gateway.on_raven_message_before_insert")
_ec_chat_add_doc_event("EC Notification Delivery Log", "after_insert",
                       "ecentric_workspace.chat.phieu_gateway.on_delivery_log_after_insert")
