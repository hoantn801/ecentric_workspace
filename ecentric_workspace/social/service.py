# Copyright (c) 2026, eCentric and contributors
"""Bang tin - phia NGUOI DUNG: trang bang tin, trang mot bai, dang / sua / xoa bai, tha tim, tham gia
su kien, bao cao bai, HR an bai. Moi ham nhan `user` do api.py / trang www lay tu PHIEN.

Ai dung duoc: nhan vien co ho so Employee Active (PO 04/10: moi nhan vien Active duoc dang) va HR /
System Manager (kiem duyet). Bai dang thang, khong cho duyet; ai thay bai cung bao cao duoc, HR an.
`repo` tiem vao duoc: test chay bang repo gia, khong can bench.
"""
import datetime

from ecentric_workspace.social import cards, notify
from ecentric_workspace.social import constants as C
from ecentric_workspace.social import domain as D
from ecentric_workspace.social.domain import Forbidden, NotFound, SocialError  # noqa: F401


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.social import repository
    return repository


def context(repo, user):
    """Nguoi dang dung + quyen. Khong phai nhan vien Active, khong phai HR -> Forbidden."""
    if not user or user == "Guest":
        raise Forbidden("Cần đăng nhập.")
    mod = repo.is_moderator(user)
    v = repo.viewer(user)
    if not v and not mod:
        raise Forbidden("Bảng tin dành cho nhân viên eCentric (có hồ sơ nhân sự đang làm việc).")
    return {"user": user, "moderator": mod, "employee": bool(v), "lft": v and v.get("lft"),
            "department": v and v.get("department"), "tree": repo.dept_tree()}


def visible(cx, row):
    return D.can_see(row, cx["user"], cx["lft"], cx["tree"], cx["moderator"])


def load(repo, cx, name):
    row = repo.post(name)
    if not row:
        raise NotFound("Không tìm thấy bài (có thể đã bị xoá).")
    if not visible(cx, row):
        raise Forbidden("Bạn không xem được bài này.")
    return row


# ------------------------------------------------------------------ dang bai ---------
def _images(repo, files):
    """files: [{name, content}] tu api -> anh da ve lai (bo EXIF / GPS, thu nho)."""
    if len(files) > C.IMAGES_MAX:
        raise SocialError("Tối đa %d ảnh mỗi bài." % C.IMAGES_MAX)
    out = []
    for i, f in enumerate(files):
        ext = (f.get("name") or "").rsplit(".", 1)[-1].lower()
        if ext not in C.IMAGE_EXTS:
            raise SocialError("Chỉ nhận ảnh (jpg, png, gif, webp): %s" % (f.get("name") or "?"))
        if len(f.get("content") or b"") > C.IMAGE_MAX_BYTES:
            raise SocialError("Ảnh lớn quá %d MB: %s" % (C.IMAGE_MAX_BYTES // 1048576, f.get("name") or "?"))
        try:
            content, out_ext, w, h = repo.clean_image(f["content"], ext, C.IMAGE_MAX_SIDE)
        except ValueError:
            raise SocialError("Ảnh không mở được: %s" % (f.get("name") or "?"))
        out.append({"name": "anh-%d.%s" % (i + 1, out_ext), "content": content, "width": w, "height": h})
    return out


def _people(repo, users, me):
    """Danh sach tai khoan hop le (nhan vien Active), bo trung, bo chinh minh."""
    valid = {p["user"] for p in repo.people()}
    out = []
    for u in users or []:
        u = str(u or "")
        if u and u != me and u in valid and u not in out:
            out.append(u)
    return out


def create(user, data, files=(), repo=None):
    """data: {body, club, dept_only, kudos_to, kudos_value, mentions[], event_title, event_start, event_place}."""
    repo = _repo(repo)
    cx = context(repo, user)
    if not cx["employee"] and not cx["moderator"]:
        raise Forbidden("Chỉ nhân viên eCentric mới đăng bài được.")
    now = repo.now()
    if repo.posts_since(user, now - datetime.timedelta(seconds=C.POST_RATE_SECONDS)) >= C.POST_RATE_MAX:
        raise SocialError("Bạn đăng hơi nhiều trong ít phút. Nghỉ tay một chút rồi đăng tiếp nhé.")
    imgs = _images(repo, list(files or []))
    values = {"kind": C.KIND_POST, "author": user, "body": D.clean_text(data.get("body"), C.BODY_MAX)}
    club = None
    if data.get("club"):
        club = repo.club(str(data["club"]))
        if not club or club["status"] != C.CLUB_ACTIVE:
            raise SocialError("Câu lạc bộ này không còn hoạt động.")
        if not repo.find_member(club["name"], user) and not cx["moderator"]:
            raise Forbidden("Tham gia CLB trước rồi mới đăng vào CLB được.")
        values["club"] = club["name"]
    if data.get("event_title") or data.get("event_start"):
        if not club:
            raise SocialError("Sự kiện tạo trong một câu lạc bộ.")
        if club.get("lead") != user and not cx["moderator"]:
            raise Forbidden("Chỉ người phụ trách CLB (hoặc HR) tạo được sự kiện.")
        values.update(D.parse_event(data, now))
        values["kind"] = C.KIND_EVENT
    if data.get("kudos_to"):
        to = _people(repo, [data.get("kudos_to")], user)
        if not to:
            raise SocialError("Chọn một đồng nghiệp để khen (không tự khen mình được).")
        if data.get("kudos_value") and not D.kudos_label(data.get("kudos_value")):
            raise SocialError("Giá trị lời khen không hợp lệ.")
        if values["kind"] == C.KIND_EVENT:
            raise SocialError("Lời khen và sự kiện đăng riêng nhé.")
        values.update({"kind": C.KIND_KUDOS, "kudos_to": to[0], "kudos_value": data.get("kudos_value") or ""})
        if not values["body"]:
            raise SocialError("Viết vài dòng vì sao bạn khen nhé.")
    if values["kind"] == C.KIND_POST and not values["body"] and not imgs:
        raise SocialError("Bài đang trống. Viết gì đó hoặc thêm ảnh.")
    if str(data.get("dept_only") or "") in ("1", "true", "True"):
        if not cx["department"]:
            raise SocialError("Hồ sơ của bạn chưa có phòng ban nên không đăng 'Chỉ phòng tôi' được.")
        values["dept_only"] = 1
    values["department"] = cx["department"] or None
    mentions = _people(repo, (data.get("mentions") or [])[:C.MENTIONS_MAX], user)
    if values.get("kudos_to") in mentions:
        mentions.remove(values["kudos_to"])
    if values.get("dept_only"):
        # Bai "Chi phong toi": nguoi duoc khen / gan ten ngoai phong se KHONG thay bai -> chan luon.
        outside = [u for u in ([values.get("kudos_to")] if values.get("kudos_to") else []) + mentions
                   if not D.in_dept(cx["tree"], cx["department"], (repo.viewer(u) or {}).get("lft"))]
        if outside:
            names = repo.full_names(outside)
            raise SocialError("Bài 'Chỉ phòng tôi' không tới được %s (khác phòng). Bỏ 'Chỉ phòng tôi' hoặc bỏ tên."
                              % ", ".join(names.get(u) or u for u in outside))
    name = repo.insert_post(values, mentions)
    if imgs:
        repo.attach_images(name, imgs)
    row = repo.post(name)
    notify.new_post(repo, row, mentions, club)
    return post_view(user, name, repo=repo)


def edit(user, name, body, repo=None):
    repo = _repo(repo)
    cx = context(repo, user)
    row = load(repo, cx, name)
    if row.get("author") != user or row.get("kind") == C.KIND_MOMENT:
        raise Forbidden("Chỉ người đăng mới sửa được bài.")
    if row.get("hidden"):
        raise SocialError("HR đã ẩn bài này nên không sửa được.")
    text = D.clean_text(body, C.BODY_MAX)
    if not text and row.get("kind") != C.KIND_EVENT and not repo.images_of([name]).get(name):
        raise SocialError("Bài đang trống.")
    if row.get("kind") == C.KIND_KUDOS and not text:
        raise SocialError("Lời khen cần vài dòng.")
    repo.update_post(name, {"body": text, "edited_on": repo.now()})
    return post_view(user, name, repo=repo)


def delete(user, name, repo=None):
    repo = _repo(repo)
    cx = context(repo, user)
    row = load(repo, cx, name)
    if row.get("kind") == C.KIND_MOMENT:
        raise Forbidden("Bài tự động không xoá được.")
    if row.get("author") != user and not cx["moderator"]:
        raise Forbidden("Chỉ người đăng (hoặc HR) mới xoá được bài.")
    if not cx["moderator"] and (row.get("hidden") or repo.count_reports(name, C.REPORT_NEW)):
        raise SocialError("Bài đang được HR xem xét nên chưa xoá được.")
    repo.delete_post(name)
    return {"deleted": name}


# ------------------------------------------------------------------ mot bai ---------
def post_view(user, name, repo=None):
    """Mot the bai (api ve lai sau moi thao tac)."""
    repo = _repo(repo)
    cx = context(repo, user)
    row = load(repo, cx, name)
    return cards.build(repo, cx, [row])[0]


def react(user, name, repo=None):
    """Tha / bo tim. Bai Bang tin: target soc:<ten>. Bai khoanh khac: khoa popup (bd:/ann:/new:)."""
    repo = _repo(repo)
    cx = context(repo, user)
    row = load(repo, cx, name)
    if row.get("hidden"):
        raise SocialError("Bài này đã bị ẩn.")
    target = C.RX_PREFIX + name
    existing = repo.find_reaction(target, C.RX_KIND, user)
    if existing:
        repo.remove_reaction(existing)
    else:
        try:
            repo.add_reaction(target, C.RX_KIND, user, repo.today())
        except Exception as exc:
            if not repo.is_duplicate(exc):
                raise
    return D.rx_summary(repo.reactions([target]), target, user)


def react_moment(user, key, repo=None):
    """Tim / hoa / banh tren khoanh khac hom nay = CUNG cam xuc tren popup (home_today kiem khoa con
    trong ngay). Moi loai khoanh khac mot cam xuc (MOMENT_RX)."""
    repo = _repo(repo)
    context(repo, user)
    kind = C.MOMENT_RX.get(D.moment_kind(key))
    if not kind:
        raise SocialError("Khoảnh khắc không hợp lệ.")
    from ecentric_workspace.social import sources
    per = sources.toggle_moment(user, key, kind)["reactions"]
    order = [k for k in ("heart", "party", "flower", "cake") if per.get(k, {}).get("n")]
    return {"total": sum(v.get("n", 0) for v in per.values()), "emojis": "".join(C.RX_EMOJI[k] for k in order[:3]),
            "mine": bool(per.get(kind, {}).get("mine"))}


def rsvp(user, name, answer, repo=None):
    """Tham gia / Co the. Bam lai lua chon dang chon = bo."""
    repo = _repo(repo)
    cx = context(repo, user)
    row = load(repo, cx, name)
    if row.get("kind") != C.KIND_EVENT:
        raise SocialError("Bài này không phải sự kiện.")
    if row.get("hidden"):
        raise SocialError("Sự kiện này đã bị ẩn.")
    if D.event_state(row.get("event_start"), repo.now()) == "past":
        raise SocialError("Sự kiện đã diễn ra.")
    if answer not in C.RSVP_ANSWERS:
        raise SocialError("Lựa chọn không hợp lệ.")
    cur = repo.find_rsvp(name, user)
    if cur and cur["answer"] == answer:
        repo.remove_rsvp(cur["name"])
    elif cur:
        repo.set_rsvp(cur["name"], answer)
    else:
        try:
            repo.add_rsvp(name, user, answer)
        except Exception as exc:
            if not repo.is_duplicate(exc):
                raise
    return post_view(user, name, repo=repo)


def report(user, name, reason, repo=None):
    repo = _repo(repo)
    cx = context(repo, user)
    row = load(repo, cx, name)
    if row.get("author") == user:
        raise SocialError("Không báo cáo bài của chính mình được.")
    text = D.clean_text(reason, C.REPORT_REASON_MAX)
    if repo.find_report(name, user):
        return {"reported": True, "again": True}
    try:
        repo.add_report(name, user, text)
    except Exception as exc:
        if not repo.is_duplicate(exc):
            raise
        return {"reported": True, "again": True}
    # Dem bao cao DANG MO: HR "giu bai" roi ma co nguoi bao lai thi chuong lai (dot moi).
    n = repo.count_reports(name, C.REPORT_NEW)
    repo.update_post(name, {"report_count": n})
    if n == 1:
        notify.reported(repo, row, repo.count_reports(name))
    return {"reported": True, "again": False}


def hide(user, name, hidden=True, reason="", repo=None):
    """HR an / hien lai bai. An = dong moi bao cao dang mo cua bai."""
    repo = _repo(repo)
    cx = context(repo, user)
    if not cx["moderator"]:
        raise Forbidden("Chỉ HR được ẩn bài.")
    load(repo, cx, name)
    now = repo.now()
    if hidden:
        repo.update_post(name, {"hidden": 1, "hidden_by": user, "hidden_on": now,
                                "hidden_reason": D.clean_text(reason, C.REPORT_REASON_MAX)})
        repo.close_reports(name, user, "Ẩn bài", now)
    else:
        repo.update_post(name, {"hidden": 0, "hidden_by": None, "hidden_on": None, "hidden_reason": ""})
    return post_view(user, name, repo=repo)


def dismiss_reports(user, name, repo=None):
    repo = _repo(repo)
    cx = context(repo, user)
    if not cx["moderator"]:
        raise Forbidden("Chỉ HR xử lý báo cáo.")
    load(repo, cx, name)
    repo.close_reports(name, user, "Giữ bài", repo.now())
    return {"name": name}


def image(user, name, idx):
    """-> (ten tep, bytes) cua anh thu idx trong bai, neu nguoi xem thay bai."""
    repo = _repo(None)
    cx = context(repo, user)
    load(repo, cx, name)
    try:
        i = int(idx)
    except (TypeError, ValueError):
        raise NotFound("Không tìm thấy ảnh.")
    imgs = repo.images_of([name]).get(name) or []
    if not 0 <= i < len(imgs):
        raise NotFound("Không tìm thấy ảnh.")
    got = repo.image_content(name, imgs[i]["file_url"])
    if not got:
        raise NotFound("Không tìm thấy ảnh.")
    return got


def people(user, repo=None):
    repo = _repo(repo)
    context(repo, user)
    return [dict(p, initials=D.initials(p["name"]), av=D.avatar(p["user"])) for p in repo.people() if p["user"] != user]

