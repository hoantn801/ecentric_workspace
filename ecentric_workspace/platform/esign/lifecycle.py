# Copyright (c) 2026, eCentric and contributors
"""What has to happen to a signing package when the approval flow reopens a request.

The gap this closes, observed live on 2026-08-27 (EC-PAYR-2026-00027):

    14:07  lien.vu     "Yêu cầu bổ sung"  - Pending -> Information Required
    17:54  hoan.tran   "Gửi lại"

`resubmit()` reset the approval levels and touched nothing else. The signing package stayed
Locked with the file list frozen at lock time, so a document attached after 14:07 was NOT in
it. Every later level would then sign the OLD set of documents while everyone believed they
were looking at the supplemented one. No error, no warning - the kind of wrong answer that
only surfaces during an audit, months later.

`package.create_revision()` was written for exactly this and documented as "used by resubmit
cycles", but nothing ever called it.

## The judgement call, stated plainly

A signature attests to the documents as they stood at the moment of signing. Change the
documents and an earlier signature no longer says what it appears to say. So when digital
signatures have ALREADY been collected and the package is reopened, the approval restarts
from level 1 rather than resuming mid-chain.

That is deliberately the inconvenient option. Re-signing costs people a few minutes;
a payment carrying signatures that attest to a different document set is not recoverable
after the fact. Accounting and legal should confirm the rule, but until they do, the safe
side is the one that asks for the signature again.

When nothing has been signed yet there is nothing to invalidate, so an ordinary resubmit
proceeds - only the package is revised so new attachments can join it.
"""
import frappe
from frappe import _

from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign import package as pkgsvc

#: Package states that hold a frozen file list. A Draft package still picks up new
#: attachments by itself, so it needs no revision.
_FROZEN = ("Locked", "Active", "Provider Created", "Provider Create Failed")

#: A leg that reached this state means a real signature exists at the provider.
_SIGNED = ("Approval Completed",)


def _frozen_package(approval_request):
    return frappe.db.get_value("EC Digital Signature Package",
                               {"approval_request": approval_request,
                                "status": ["in", _FROZEN]},
                               ["name", "business_doctype", "business_name"],
                               order_by="creation desc", as_dict=True)


def has_collected_signatures(package_name):
    return bool(frappe.db.count("EC Digital Signature Request",
                                {"package": package_name, "status": ["in", _SIGNED]}))


def on_request_reopened(approval_request):
    """Called by the approval flow BEFORE it resets levels.

    Returns {"revised": bool, "new_package": str|None, "force_restart": bool}.

    Failure is NOT swallowed. If a frozen package exists and cannot be revised, the resubmit
    must stop: carrying on would leave the request open against a stale package, which is the
    precise silent-wrong-result this function exists to prevent.
    """
    out = {"revised": False, "new_package": None, "force_restart": False}
    pkg = _frozen_package(approval_request)
    if not pkg:
        return out

    signed = has_collected_signatures(pkg.name)
    new = pkgsvc.create_revision(pkg.name)          # raises on its own guards - let it
    out["revised"] = True
    out["new_package"] = new.name
    out["force_restart"] = signed

    # The requester must prepare and lock again; without this the gate in requester.py
    # refuses (it only accepts _START_STATES + Processing) and the flow dead-ends.
    #
    # `requester_signature_status` lives on EC APPROVAL REQUEST, not on the business document.
    # The first version wrote it to pkg.business_doctype ("EC Payment Request"), which has no
    # such column - and the write was wrapped in `except Exception`, so it failed into a log
    # line while the flow carried on believing it had reset. The requester would then be told
    # "đã ký cho yêu cầu này" and the new package could never be signed. Writing to the wrong
    # place and swallowing the error is worse than not trying: it looks like it worked.
    frappe.db.set_value("EC Approval Request", approval_request,
                        "requester_signature_status", "Pending")

    events.emit("RequesterPackageReset", package=new.name,
                request_meta={"previous_package": pkg.name,
                              "had_collected_signatures": signed,
                              "approval_restarts_from_level_1": signed})
    return out


def reopen_notice(result):
    """One sentence for the person who pressed the button - never a silent change."""
    if not result.get("revised"):
        return ""
    if result.get("force_restart"):
        return _("Tài liệu ký đã được tạo phiên bản mới. Vì đã có chữ ký số được thu thập "
                 "trên bộ tài liệu cũ, quy trình duyệt bắt đầu lại từ cấp 1 và các cấp phải "
                 "ký lại.")
    return _("Tài liệu ký đã được tạo phiên bản mới. Hãy chuẩn bị và khoá lại gói ký để "
             "chứng từ bổ sung được đưa vào.")
