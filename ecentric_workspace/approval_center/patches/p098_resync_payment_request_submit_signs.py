# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: "Gui yeu cau" now does the whole thing.

The requester faced five actions for one intention: place the signature boxes, send the
request, prepare the package, lock the package, submit for signing. The middle three are
internal state-machine steps - nobody outside the esign module should have to know they
exist, and asking for them by name only invites the question the user finally asked on
2026-08-28: "why is there a Trinh ky button at all? Pressing Send should send it and sign
it."

They were also unreachable. On 27 and 28 August the flow stopped at those buttons twice with
the same report - "there is no button" - and both times it was unblocked by calling the API
by hand. Collapsing the steps removes the class of failure along with the clicks: a button
that no longer exists cannot go missing.

Submit now refuses outright when the placements are incomplete, naming what is missing. A
request that goes out carrying an unusable signing package is worse than one that refuses to
go out: the refusal is visible immediately, the broken package is not.

The panel keeps only its status line, the waiting state, and the recovery button for a
genuinely broken package - the one case that still needs a person.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
