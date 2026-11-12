# Copyright (c) 2026, eCentric and contributors
"""Cap ve tuan (tran 3 ve / nguoi / tuan, tinh chung moi nguon). Moi (nguon, ref, nguoi) chi cap
MOT lan - khoa chinh EC Training Ticket = nguon|ref|bam email, nen goi lai khong cap trung."""
from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain import tickets


def grant(repo, user, source, ref, want, label):
    """-> so ve thuc cap (0 neu da cap truoc do / het tran tuan)."""
    if want <= 0 or repo.ticket_exists(source, ref, user):
        return 0
    ws = tickets.week_start(repo.now())
    n = tickets.grant(repo.tickets_in_week(user, ws), want)
    if n <= 0:
        return 0
    repo.insert_ticket({"user": user, "week_start": ws, "source": source, "ref": ref,
                        "label": label[:140], "count": n})
    return n


def summary(repo, user):
    ws = tickets.week_start(repo.now())
    rows = repo.tickets_of(user)
    return {"week": tickets.week_label(repo.now()), "this_week": repo.tickets_in_week(user, ws),
            "cap": C.TICKETS_PER_WEEK,
            "history": [{"label": r["label"], "count": r["count"], "revoked": int(r["revoked"] or 0),
                         "week_start": r["week_start"], "source": r["source"]} for r in rows]}
