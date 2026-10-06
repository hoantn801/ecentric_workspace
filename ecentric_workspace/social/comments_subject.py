# Copyright (c) 2026, eCentric and contributors
"""Binh luan / loi chuc tren Bang tin = CUNG bang EC Post Comment, CUNG bo luat voi Tin noi bo
(internal_posts/comments.py). File nay chi noi phan rieng cua bai Bang tin: tai bai, ai doc duoc,
ai la "chu bai" (nhan chuong), duong dan, cau chuong.

Khoanh khac (sinh nhat / ban moi / ky niem): bai EC Social Post kind=moment tao LUC NGUOI DAU TIEN
gui loi chuc (ensure_moment) - ngay khong ai chuc thi khong co ban ghi nao. "Chu bai" la nguoi duoc
chuc (tai khoan cua ho so nhan vien) nen ho nhan chuong khi co loi chuc.
"""
from ecentric_workspace.internal_posts import comments as engine
from ecentric_workspace.social import constants as C
from ecentric_workspace.social import domain as D
from ecentric_workspace.social import service as S
from ecentric_workspace.social import sources


def _repo():
    from ecentric_workspace.social import repository
    return repository


class SocialSubject:
    doctype = C.POST_DT
    dedupe = "social_cmt"

    def __init__(self, repo=None):
        self.repo = repo

    @property
    def r(self):
        return self.repo or _repo()

    def load(self, _engine_repo, user, name):
        return S.load(self.r, S.context(self.r, user), name)

    def can_read(self, _engine_repo, doc, user):
        v = self.r.viewer(user)
        if not v and not self.r.is_moderator(user):
            return False
        return D.can_see(doc, user, v and v.get("lft"), self.r.dept_tree(), self.r.is_moderator(user))

    def allowed(self, doc):
        return True

    def enabled(self, doc):
        return not doc.get("hidden")

    def owner(self, doc):
        return doc.get("author")

    def url(self, doc):
        return "%s/%s#binh-luan" % (C.POST_ROUTE, doc.get("name"))

    def titles(self, who, doc):
        if doc.get("kind") == C.KIND_MOMENT:
            mk = D.moment_kind(doc.get("moment_key"))
            what = {"bd": "chúc mừng sinh nhật bạn", "ann": "chúc mừng kỷ niệm gắn bó của bạn",
                    "new": "chào mừng bạn tới eCentric"}.get(mk, "gửi lời chúc tới bạn")
            return ("%s trả lời lời chúc của bạn" % who, "%s %s" % (who, what))
        return ("%s trả lời bình luận của bạn trên Bảng tin" % who, "%s bình luận bài của bạn trên Bảng tin" % who)

    def moderator(self, _engine_repo, user):
        return self.r.is_moderator(user)


SUBJECT = SocialSubject()


def _engine_repo():
    from ecentric_workspace.internal_posts import repository
    return repository


def view(user, name):
    """Khoi binh luan cua mot bai Bang tin (de template social/comments.html ve)."""
    r = SUBJECT.r
    cx = S.context(r, user)
    doc = S.load(r, cx, name)
    return decorate(engine.view(_engine_repo(), doc, user, cx["moderator"], SUBJECT), doc)


def decorate(view, doc=None):
    """Them co cho template: `moment` (bai khoanh khac: "loi chuc" thay "binh luan"), `hr` (binh
    luan cua bai Tin noi bo mo ngay tren Bang tin)."""
    doc = doc or SUBJECT.r.post(view.get("post"))
    view["moment"] = bool(doc) and doc.get("kind") == C.KIND_MOMENT
    view["hr"] = doc is None
    return view


# ------------------------------------------------------------------ the Tin noi bo tren Bang tin --
# PO 05/10: bam "Binh luan" tren the Tin HR thi binh luan NGAY tren Bang tin (khong nhay sang trang
# bai). Van la CUNG chuoi binh luan cua bai Tin noi bo (subject INTERNAL, quyen doc cua Tin noi bo) -
# binh o dau thi hien ca hai noi, khong co ban sao.

def subject_for(ref):
    return engine.INTERNAL if ref == "hr" else SUBJECT


def subject_of_comment(name):
    row = _engine_repo().comment(name)
    return engine.INTERNAL if row and (row.get("ref_doctype") or engine.C.POST_DT) == engine.C.POST_DT else SUBJECT


def hr_view(user, name):
    if not user or user == "Guest":
        raise D.Forbidden("Cần đăng nhập.")
    ir = _engine_repo()
    doc = engine.INTERNAL.load(ir, user, name)
    return engine.view(ir, doc, user, ir.is_editor(user), engine.INTERNAL)


def ensure_moment(user, key, repo=None):
    """Bai khoanh khac cua `key` (tao neu chua co). Chi khoa cua HOM NAY."""
    r = repo or _repo()
    S.context(r, user)
    post = r.moment_post(key)
    if post:
        return post["name"]
    people = sources.people_today(r)
    owner = None
    for group in ("birthdays", "anniversaries", "onboard"):
        for p in people.get(group) or []:
            if p.get("key") == key:
                owner = r.employee_user(p["emp"]) if p.get("emp") else None
                break
        else:
            continue
        break
    else:
        raise D.SocialError("Khoảnh khắc này không còn trong ngày hôm nay.")
    got = r.insert_moment(key, owner)
    if not got:
        raise D.SocialError("Có người vừa gửi lời chúc cùng lúc. Bấm gửi lại giúp mình nhé.")
    return got["name"]
