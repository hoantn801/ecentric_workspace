# Copyright (c) 2026, eCentric and contributors
"""Ban tin gop y hang thang cho BGD (PO chot 04/10): so lieu + "chu de nong" do AI gom.

AI di qua cong chung platform/ai (MOT cho cam key - quyet dinh 28/09). Gui cho AI CHI tieu de +
noi dung + so "+1": khong ten, khong phong ban, khong co cot an danh. AI loi -> van luu so lieu,
chu de nong de trong (khong bia).
"""
import json

from ecentric_workspace.feedback import constants as C
from ecentric_workspace.feedback import domain as D
from ecentric_workspace.feedback import handler_service as H


def _boot(repo):
    if repo is not None:
        return repo
    import frappe
    frappe.set_user(C.SYSTEM_USER)
    from ecentric_workspace.feedback import repository
    return repository


def build(repo, month, send=False):
    """Tinh so lieu + chu de nong cua `month`, luu EC Feedback Digest. send -> bao BGD (mot lan)."""
    now = repo.now()
    st, rows = H.period(repo, month, now)
    items = sorted(rows, key=lambda r: (-(r.get("vote_count") or 0), str(r.get("creation"))))
    hot, model = [], ""
    if items:
        res = repo.generate_ai(D.digest_prompt(items), D.DIGEST_SCHEMA) or {}
        if res.get("ok"):
            hot = D.clean_hot(res.get("data"))
            model = res.get("model") or ""
        else:
            repo.log_message("feedback.digest AI", res.get("error") or "loi khong ro")
    repo.save_digest(month, {"stats": json.dumps(st, ensure_ascii=False), "hot_topics": json.dumps(hot, ensure_ascii=False),
                             "generated_on": now, "ai_model": model})
    if send:
        old = repo.digest(month) or {}
        if not old.get("sent_on"):
            _announce(repo, month, st, hot)
            repo.save_digest(month, {"sent_on": now})
    repo.commit()
    return hot


def _announce(repo, month, st, hot):
    label = "%s/%s" % (month[5:], month[:4])
    bits = ["%d góp ý" % st["total"]]
    if st.get("on_time_pct") is not None:
        bits.append("%d%% trả lời đúng hạn" % st["on_time_pct"])
    if hot:
        bits.append("nhắc nhiều: " + ", ".join(h["name"] for h in hot[:3]))
    url = "%s?thang=%s" % (C.ROUTE_OVERVIEW, month)
    for u in repo.handlers():
        try:
            repo.notify(C.EV_DIGEST, u, "Bản tin góp ý tháng " + label, " · ".join(bits), url, None,
                        "feedback_digest|%s|%s" % (month, u))
        except Exception:
            repo.log_error("feedback.digest.notify")


def monthly(repo=None):
    """Scheduler ngay 1 hang thang: ban tin cua thang TRUOC."""
    repo = _boot(repo)
    month = D.prev_month(repo.today())
    try:
        return build(repo, month, send=True)
    except Exception:
        repo.log_error("feedback.digest.monthly")
        return None
