# Copyright (c) 2026, eCentric and contributors
"""Step catalog primitives (NO frappe import - pure, unit-testable anywhere).

A Step names one unit of the signing lifecycle: who acts, which existing service
function backs it (for traceability - this module calls nothing), and which
``esign.state`` PACKAGE/DSR statuses bound its entry and exit. ``park`` lists the
non-terminal-by-design statuses this step can land in when something needs a human
(mapping missing, placement missing, ambiguous provider write, mismatch, review).

Declaring a step here changes NOTHING about runtime behavior. It is read by
``flow.resolve`` (to name the current step from live state) and by
``tests.test_esign_flow_contract`` (to prove every entry/exit/park pair is a state
`esign.state` actually allows).
"""
from collections import namedtuple

Step = namedtuple("Step", [
    "id",              # short stable key, e.g. "package_lock"
    "title_vi",        # label shown to a human reading a report/log
    "actor",           # "requester" | "approver" | "system"
    "backed_by",       # "module.function" this step's behavior actually lives in
    "package_entry",   # esign.state PACKAGE status(es) this step starts from, or None
    "package_exit",    # esign.state PACKAGE status this step ends in, or None
    "dsr_entry",       # esign.state DSR status(es) this step starts from, or None
    "dsr_exit",        # esign.state DSR status this step ends in, or None
    "park",            # tuple of PACKAGE/DSR statuses this step can park at instead
    "notes",           # short "why", only when non-obvious
])


def step(id, title_vi, actor, backed_by, package_entry=None, package_exit=None,
         dsr_entry=None, dsr_exit=None, park=(), notes=""):
    def _tup(v):
        if v is None:
            return None
        return (v,) if isinstance(v, str) else tuple(v)
    return Step(id=id, title_vi=title_vi, actor=actor, backed_by=backed_by,
               package_entry=_tup(package_entry), package_exit=package_exit,
               dsr_entry=_tup(dsr_entry), dsr_exit=dsr_exit, park=tuple(park), notes=notes)
