# Copyright (c) 2026, eCentric
# EC Catalogue Sync Run - persistent audit/history for background catalogue
# sync (Phase 3-4, 2026-06-13). Schema/controller layer only; all logic lives
# in api_catalogue_sync + services.catalogue_sync.

import frappe
from frappe.model.document import Document

# Documented status lifecycle:
#   Queued     - run created, worker enqueued, not yet started
#   Running    - worker executing (progress fields update live)
#   Completed  - worker finished, whole window processed
#   Partial    - worker stopped at a cap/timebox; resumable
#   Failed     - worker raised; error_message set
#   Cancelled  - reserved (manual/admin abort)
ACTIVE_RUN_STATUSES = ("Queued", "Running")
TERMINAL_RUN_STATUSES = ("Completed", "Partial", "Failed", "Cancelled")


class ECCatalogueSyncRun(Document):
    pass
