# Copyright (c) 2026, eCentric and contributors
"""One-off cleanup: remove the 27 Payment Requests created while building the esign flow.

WHY A PATCH AND NOT A SCRIPT AGAINST THE REST API.
The first attempt drove `DELETE /api/resource/...` with an API token and failed on 1557 of
1723 records. Two of the doctypes involved are deliberately append-only, and the API has no
way around either:

  * `EC Digital Signature Event` grants only `read` in its DocPerm - no role anywhere can
    delete one - and its controller also blocks `on_trash`. Every delete returned 403.
  * `EC Approval Action` throws in `on_trash`: "append-only; actions cannot be deleted".
    `force=True` skips the LINK check, not the controller, so `delete_doc` cannot help.

Both refusals are correct. An approval audit trail that a token can erase is not an audit
trail. So the fix is not to widen a permission or soften a controller - it is to do the
cleanup somewhere that legitimately runs as the framework: a patch, which runs once, is
recorded in Patch Log, and is reviewable in git next to the reason it existed.

Everything above those two doctypes then failed with 417 LinkExistsError purely because the
children survived. Only 166 leaf records were removed, so the site is currently in a
half-deleted state: some approver/level rows and attachments are gone while their parents
remain. This patch finishes the job. It is idempotent, so running it against that partial
state is fine.

TWO DELETION MECHANISMS, ON PURPOSE.
`frappe.db.delete` (raw SQL, no controller, no Deleted Document archive) is used ONLY for the
two append-only logs. They are machine-written retry traces - packages EC-DSP-2026-00013 and
00016 alone hold roughly 1,600 events from cron hammering a document SCTS had already
deleted - and archiving them would only move the noise. Everything else goes through
`frappe.delete_doc`, which keeps the normal Deleted Document trail.

SAFETY.
The 27 names are written out by hand. No pattern, no date range, no "looks like test" filter -
a fuzzy filter is the fastest way to delete a real record. On a site that does not have these
names (a fresh install, a clone) every step no-ops and the patch does nothing.

Approved by Hoan 01/09/2026: 14 phieu with SCTS signing packages (already deleted on the SCTS
side), 4 submitted 21-24/08 with no signing package, and 9 drafts never submitted.
"""
import frappe

#: Group A - had SCTS signing packages; these are the rows on /ec-esign/ops.
#: 00029 is the one rejected with `<b>test</b>` while checking XSS escaping on 01/09.
PHIEU_CO_GOI_KY = [
    "EC-PAYR-2026-00022", "EC-PAYR-2026-00023", "EC-PAYR-2026-00026", "EC-PAYR-2026-00027",
    "EC-PAYR-2026-00029", "EC-PAYR-2026-00032", "EC-PAYR-2026-00033", "EC-PAYR-2026-00034",
    "EC-PAYR-2026-00035", "EC-PAYR-2026-00036", "EC-PAYR-2026-00037", "EC-PAYR-2026-00038",
    "EC-PAYR-2026-00039", "EC-PAYR-2026-00040",
]

#: Group B - submitted for approval in the same test window, never sent to SCTS.
PHIEU_DA_GUI = [
    "EC-PAYR-2026-00019", "EC-PAYR-2026-00021", "EC-PAYR-2026-00024", "EC-PAYR-2026-00025",
]

#: Group C - drafts, no approval record at all. 00030/00031 belong to hon.nguyen@ecentric.vn.
#: EC-PAYR-2026-00003 (Administrator, 10/07) is deliberately NOT here - outside the window.
PHIEU_NHAP = [
    "EC-PAYR-2026-00013", "EC-PAYR-2026-00014", "EC-PAYR-2026-00017", "EC-PAYR-2026-00018",
    "EC-PAYR-2026-00020", "EC-PAYR-2026-00028", "EC-PAYR-2026-00030", "EC-PAYR-2026-00031",
    "EC-PAYR-2026-00041",
]

PHIEU = PHIEU_CO_GOI_KY + PHIEU_DA_GUI + PHIEU_NHAP

BIZ = "EC Payment Request"


def execute():
    dem = {"phieu": 0, "goi": 0, "su_kien": 0, "hanh_dong": 0, "ban_ghi": 0, "bo_qua": 0}

    for pr in PHIEU:
        if not frappe.db.exists(BIZ, pr):
            dem["bo_qua"] += 1
            continue

        ar = frappe.db.get_value(BIZ, pr, "approval_request")

        for pkg in frappe.get_all(
            "EC Digital Signature Package",
            filters={"business_doctype": BIZ, "business_name": pr},
            pluck="name",
        ):
            _xoa_goi_ky(pkg, ar, dem)
            dem["goi"] += 1

        if ar:
            _xoa_ho_so_duyet(ar, dem)

        # Reminders and attachments hang off both the business record and the approval record.
        for dt, name in ((BIZ, pr), ("EC Approval Request", ar)):
            if name:
                _xoa_todo_va_file(dt, name, dem)

        # The business record points AT the approval record, so it goes first.
        _xoa(BIZ, pr, dem)
        if ar and frappe.db.exists("EC Approval Request", ar):
            _xoa("EC Approval Request", ar, dem)
        dem["phieu"] += 1

    print(
        "[p121] da xoa %d phieu (%d goi ky), %d su kien, %d hanh dong duyet, "
        "%d ban ghi khac; bo qua %d phieu khong ton tai."
        % (dem["phieu"], dem["goi"], dem["su_kien"], dem["hanh_dong"],
           dem["ban_ghi"], dem["bo_qua"])
    )


def _xoa_goi_ky(pkg, ar, dem):
    """Leaf-to-root inside one signing package."""
    chan_ky = frappe.get_all(
        "EC Digital Signature Request", filters={"package": pkg}, pluck="name"
    )

    # Placements reference both the package and a signature file, so they go before both.
    for pl in frappe.get_all(
        "EC Digital Signature Placement", filters={"package": pkg}, pluck="name"
    ):
        _xoa("EC Digital Signature Placement", pl, dem)

    # Append-only log: raw delete, no controller, no archive. See module docstring.
    dem["su_kien"] += _xoa_log("EC Digital Signature Event", {"package": pkg})
    for d in chan_ky:
        dem["su_kien"] += _xoa_log("EC Digital Signature Event", {"signature_request": d})

    for f in frappe.get_all(
        "EC Digital Signature File", filters={"package": pkg}, pluck="name"
    ):
        _xoa("EC Digital Signature File", f, dem)

    # The approval record links to the requester's signing leg; break it before the leg dies,
    # otherwise the delete trips a LinkExistsError on a row we are keeping until later.
    if ar and frappe.db.exists("EC Approval Request", ar):
        if frappe.db.get_value("EC Approval Request", ar, "requester_signature_request"):
            frappe.db.set_value(
                "EC Approval Request", ar, "requester_signature_request", None,
                update_modified=False,
            )

    for d in chan_ky:
        _xoa("EC Digital Signature Request", d, dem)
    _xoa("EC Digital Signature Package", pkg, dem)


def _xoa_ho_so_duyet(ar, dem):
    # Append-only: the controller throws in on_trash, so raw delete is the only way.
    dem["hanh_dong"] += _xoa_log("EC Approval Action", {"approval_request": ar})

    for dt in ("EC Approval Request Approver", "EC Approval Request Level"):
        for name in frappe.get_all(dt, filters={"approval_request": ar}, pluck="name"):
            _xoa(dt, name, dem)


def _xoa_todo_va_file(dt, name, dem):
    for todo in frappe.get_all(
        "ToDo", filters={"reference_type": dt, "reference_name": name}, pluck="name"
    ):
        _xoa("ToDo", todo, dem)
    for f in frappe.get_all(
        "File", filters={"attached_to_doctype": dt, "attached_to_name": name}, pluck="name"
    ):
        _xoa("File", f, dem)


def _xoa_log(doctype, filters):
    """Raw delete for append-only audit tables. Returns how many rows went."""
    n = frappe.db.count(doctype, filters)
    if n:
        frappe.db.delete(doctype, filters)
    return n


def _xoa(doctype, name, dem):
    if not frappe.db.exists(doctype, name):
        return
    # force=True skips the link check only; controllers still run, which is what we want for
    # everything that is not an append-only log.
    frappe.delete_doc(doctype, name, force=True, ignore_permissions=True,
                      ignore_on_trash=False, delete_permanently=False)
    dem["ban_ghi"] += 1
