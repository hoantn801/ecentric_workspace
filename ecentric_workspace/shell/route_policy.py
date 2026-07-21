# Copyright (c) 2026, eCentric and contributors
"""Central route policy -- INDEPENDENT of navigation ownership.

Navigation visibility/context (shell/nav.py) and navigation-acceleration
policy are separate concerns. A route listed here is NEVER warmed by the
shell (prefetch allow-list, eager pointer/focus prerender, Speculation
Rules list) regardless of which provider/context returns it, whether it
appears in compose()/compose_all()/search/Quick Access, or whether the
owning nav item carries its own `no_prerender` flag.

Finding a route is not warming it: policy routes stay fully navigable and
discoverable; their pages remain session-scoped and permission-enforced
server-side.
"""

#: routes the shell must never prefetch/prerender/warm. Exact path or the
#: whole subtree of that path.
NO_WARM_ROUTES = frozenset({
    "/ec-hr/salary",     # salary: session-scoped personal data (HR commit 7fef8fa)
})


def _norm(p):
    p = (p or "/").split("?")[0].split("#")[0]
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p or "/"


def no_warm(route):
    """True if `route` (exact or a descendant of a policy path) must never
    be warmed."""
    p = _norm(route)
    for base in NO_WARM_ROUTES:
        b = _norm(base)
        if p == b or p.startswith(b + "/"):
            return True
    return False
