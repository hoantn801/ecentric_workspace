# Copyright (c) 2026, eCentric and contributors
"""Use case cua creator master: tim, xem, tao, sua, va hang doi ma MISA cho ke toan.

Quyen (chot 11/11/2026):
- Moi nhan vien dang nhap: tim creator (truong cong khai), tao creator moi.
- Chu ban ghi (nguoi tao), EC Finance, System Manager: xem day du CCCD / so tai khoan, sua.
- Chi EC Finance / System Manager: nhap ma khach hang MISA.
"""
from ecentric_workspace.approval_center.shared.creators import domain
from ecentric_workspace.approval_center.shared.creators.repository import CreatorRepository

FINANCE_ROLES = {"EC Finance", "System Manager"}
SEARCH_LIMIT = 20


class CreatorError(Exception):
    """Loi nghiep vu - thong bao da viet cho nguoi dung."""


class CreatorPermissionError(CreatorError):
    pass


class CreatorService:
    def __init__(self, repo=None):
        self.repo = repo or CreatorRepository()

    # ---- quyen -----------------------------------------------------------------
    def is_finance(self, user):
        return bool(self.repo.roles(user) & FINANCE_ROLES)

    def can_see_pii(self, user, row):
        return self.is_finance(user) or (row.get("owner") == user)

    # ---- doc -------------------------------------------------------------------
    def search(self, user, query=None, limit=SEARCH_LIMIT):
        query = str(query or "").strip()[:80]
        limit = max(1, min(int(limit or SEARCH_LIMIT), 50))
        return [domain.public_view(r, False) for r in self.repo.search(query, limit)]

    def get(self, user, name):
        row = self.repo.get(name)
        if not row:
            raise CreatorError("Không tìm thấy creator %s." % name)
        return domain.public_view(row, self.can_see_pii(user, row))

    def check_duplicates(self, data, exclude=None):
        return domain.classify_duplicates(data, self.repo.identity_rows(exclude))

    # ---- ghi -------------------------------------------------------------------
    def create(self, user, data, confirm_soft=False):
        values = self._clean(data, with_identity=True)
        self._validate(values)
        dup = self.check_duplicates(values)
        self._refuse_hard(dup)
        if dup["soft"] and not confirm_soft:
            return {"needs_confirm": True, "matches": dup["soft"],
                    "message": self._soft_message(dup["soft"])}
        values.update({
            "supplier_group": domain.CREATOR_GROUP,
            "supplier_type": domain.SUPPLIER_TYPE_BY_CREATOR[values["ec_cr_type"]],
            "ec_cr_dup_ack": self._ack_note(dup["soft"]) if dup["soft"] else None,
        })
        name = self.repo.insert(values)
        return {"needs_confirm": False, "name": name}

    def update(self, user, name, data):
        row = self.repo.get(name)
        if not row:
            raise CreatorError("Không tìm thấy creator %s." % name)
        if not self.can_see_pii(user, row):
            raise CreatorPermissionError("Chỉ người tạo creator hoặc Kế toán được sửa thông tin.")
        values = self._clean(data, with_identity=False)
        merged = dict(row, **values)
        self._validate(merged)
        self._refuse_hard(self.check_duplicates(merged, exclude=name))
        self.repo.update(name, values)
        return {"name": name}

    def missing_misa(self, user):
        self._require_finance(user)
        return self.repo.missing_misa()

    def set_misa_code(self, user, name, code):
        self._require_finance(user)
        code = str(code or "").strip()
        if not code:
            raise CreatorError("Mã khách hàng MISA không được để trống.")
        if not self.repo.get(name):
            raise CreatorError("Không tìm thấy creator %s." % name)
        other = self.repo.misa_owner(code, name)
        if other:
            raise CreatorError("Mã %s đã gán cho creator %s." % (code, other))
        self.repo.update(name, {"ec_cr_misa_code": code})
        return {"name": name, "ec_cr_misa_code": code}

    # ---- noi bo ----------------------------------------------------------------
    def _require_finance(self, user):
        if not self.is_finance(user):
            raise CreatorPermissionError("Chỉ Kế toán (EC Finance) được làm việc này.")

    @staticmethod
    def _clean(data, with_identity):
        allowed = set(domain.WRITABLE_FIELDS)
        if with_identity:
            allowed |= {"supplier_name", "ec_cr_type"}
        out = {}
        for key, value in (data or {}).items():
            if key in allowed:
                out[key] = value.strip() if isinstance(value, str) else value
        return domain.normalize_for_storage(out)

    @staticmethod
    def _validate(values):
        errors = domain.validate_payload(values)
        if errors:
            raise CreatorError(" ".join(errors))

    @staticmethod
    def _refuse_hard(dup):
        if dup["hard"]:
            raise CreatorError("Creator này đã có trong hệ thống: %s. Hãy chọn creator có sẵn."
                               % "; ".join(domain.describe_match(m) for m in dup["hard"]))

    @staticmethod
    def _soft_message(matches):
        return ("Có thể đã có creator này: %s. Vẫn tạo creator mới?"
                % "; ".join(domain.describe_match(m) for m in matches))

    @staticmethod
    def _ack_note(matches):
        return "Người tạo xác nhận khác với: " + "; ".join(
            domain.describe_match(m) for m in matches)
