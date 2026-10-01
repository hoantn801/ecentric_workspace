# Copyright (c) 2026, eCentric and contributors
"""Dua MOT ban ghi cua tinh nang khac len popup "Hom nay o eCentric" - service DUNG CHUNG.

Ai goi (PO chot 01/10/2026, phuong an A):
  * Tin noi bo: bai co tich "Dua len popup" (internal_posts/notify.py).
  * Thu vien tai lieu ISO (chat ISO gan sau): Quality Procedure chuyen sang "Ban hanh" voi
    ec_notify_home = 1 -> publish_from_source("Quality Procedure", ten, phien_ban, ...).

Popup KHONG doc thang DocType cua ai: no chi doc EC Home Announcement nhu truoc. Service
nay tao mot EC Home Announcement mang dau nguon (source_doctype / source_name /
source_version) va dam bao:

  1. MOT thong bao cho moi (nguon, ban ghi, phien ban). Goi lai (luu lai, chay lai workflow,
     job chay hai lan) -> tra thong bao da co, khong tao trung. Phien ban MOI -> thong bao moi,
     khong sua thong bao cu. Thong bao da bi rut (go bai) ma goi lai -> bat dang lai.
  2. Loi khi tao thong bao KHONG lam hong viec chinh cua nguoi goi: chay trong savepoint,
     loi -> rollback DUNG phan thong bao, ghi Error Log, tra None. (Bai hoc
     feedback_throw_after_write_rolls_back_the_fix: nem loi sau khi ghi = mat ca hai.)
  3. Rut lai (go bai) = bo dang thong bao, khong xoa - con dau vet.

Khong dung toi ec_home_popup.js / service.py / trang chu: thong bao moi co key moi nen popup
tu bat lai cho moi nguoi, ke ca nguoi da tich "Khong hien lai hom nay".

`repo` tiem vao duoc: test chay bang repo gia, khong can bench.
"""
SAVEPOINT = "ec_home_announce_source"
CATEGORIES = ("Tính năng mới", "Module mới", "Chính sách", "Sự kiện", "Thông báo")
CATEGORY_DEFAULT = "Thông báo"
DISPLAY_DEFAULT = "Ảnh + nội dung"


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.home_today import repository
    return repository


def publish_from_source(source_doctype, source_name, source_version, title, category=None,
                        summary="", link="", link_label="", image="", start_date=None, end_date=None, image_link=False,
                        repo=None):
    """-> ten EC Home Announcement (da co / vua tao / vua bat lai), hoac None neu loi."""
    repo = _repo(repo)
    try:
        repo.savepoint(SAVEPOINT)
        name = repo.announcement_by_source(source_doctype, source_name, source_version or "")
        if name:
            # Nguon doi tieu de / tom tat / link / anh -> popup doi theo. Bi rut roi bat lai ->
            # cua so ngay moi (cua so cu co the da qua). Dang hien -> giu ngay bat dau.
            fresh = {"title": (title or "")[:140], "summary": summary or "", "link": link or "",
                     "link_label": link_label or "", "image": image or None, "image_link": 1 if image_link else 0}
            if not repo.announcement_published(name):
                fresh.update(published=1, start_date=start_date or repo.nowdate(), end_date=end_date)
            repo.update_announcement(name, fresh)
            repo.cache_clear_today()
            return name
        name = repo.insert_announcement({
            "title": (title or "")[:140],
            "category": category if category in CATEGORIES else CATEGORY_DEFAULT,
            "display": DISPLAY_DEFAULT,
            "published": 1,
            "start_date": start_date or repo.nowdate(),
            "end_date": end_date,
            "image": image or None,
            "summary": summary or "",
            "link": link or "",
            "link_label": link_label or "",
            "image_link": 1 if image_link else 0,
            "source_doctype": source_doctype,
            "source_name": source_name,
            "source_version": source_version or "",
        })
        return name
    except Exception:
        try:
            repo.rollback_to(SAVEPOINT)
            repo.log_error("home_today.publish_from_source")
        except Exception:
            pass
        return None


def withdraw_source(source_doctype, source_name, repo=None):
    """Bo dang MOI thong bao cua ban ghi nay (go bai / xoa bai). -> so thong bao da rut."""
    repo = _repo(repo)
    names = repo.published_announcements_of(source_doctype, source_name)
    for n in names:
        repo.set_announcement_published(n, False)
    if names:
        repo.cache_clear_today()
    return len(names)
