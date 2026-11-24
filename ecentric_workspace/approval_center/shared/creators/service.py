# Copyright (c) 2026, eCentric and contributors
"""Use case cua creator master: tim, xem, tao, sua, va hang doi ma MISA cho ke toan.

Quyen (chot 11/11/2026):
- Moi nhan vien dang nhap: tim creator (truong cong khai), tao creator moi.
- Chu ban ghi (nguoi tao), EC Finance, System Manager: xem day du CCCD / so tai khoan, sua.
- Chi EC Finance / System Manager: nhap ma khach hang MISA.
"""
from ecentric_workspace.approval_center.shared.creators import domain
from ecentric_workspace.approval_center.shared.creators.repository import CreatorRepository, InsertError

FINANCE_ROLES = {"EC Finance", "System Manager"}
SEARCH_LIMIT = 20


class CreatorError(Exception):
    """Loi nghiep vu - thong bao da viet cho nguoi dung."""


class CreatorPermissionError(CreatorError):
    pass


class MisaCodeError(CreatorError):
    """Ma MISA khong gan duoc. `status` la ma trang thai dong (misa_import.STATUS_LABELS)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


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
        values = self.prepare(data)
        dup = self.check_duplicates(values)
        self._refuse_hard(self._shown(user, dup["hard"]))
        if dup["soft"] and not confirm_soft:
            shown = self._shown(user, dup["soft"])
            return {"needs_confirm": True, "matches": shown, "message": self._soft_message(shown)}
        return {"needs_confirm": False, "name": self.insert_prepared(values, dup["soft"])}

    def prepare(self, data):
        """Lam sach + kiem loi nhap lieu. Dung chung cho form va nhap tu sheet."""
        values = self._clean(data, with_identity=True)
        self._validate(values)
        return values

    def insert_prepared(self, values, soft_matches):
        """Ghi creator da qua prepare() va da do trung CUNG. soft_matches = nguoi tao da xac nhan."""
        row = dict(values, supplier_group=domain.CREATOR_GROUP,
                   supplier_type=domain.SUPPLIER_TYPE_BY_CREATOR[values["ec_cr_type"]],
                   ec_cr_dup_ack=self._ack_note(soft_matches) if soft_matches else None)
        try:
            return self.repo.insert(row)
        except InsertError as e:
            raise CreatorError("Không lưu được creator: %s" % e)

    def require_finance(self, user):
        self._require_finance(user)

    def update(self, user, name, data):
        row = self.repo.get(name)
        if not row:
            raise CreatorError("Không tìm thấy creator %s." % name)
        if not self.can_see_pii(user, row):
            raise CreatorPermissionError("Chỉ người tạo creator hoặc Kế toán được sửa thông tin.")
        # PO 17/11: Ke toan sua duoc ten / loai creator (go sai ten in vao hop dong + so HD).
        finance = self.is_finance(user)
        values = self._clean(data, with_identity=finance)
        if finance and "disabled" in (data or {}):
            values["disabled"] = 1 if str(data.get("disabled")).strip().lower() in ("1", "true", "yes") else 0
        if values.get("ec_cr_type") and values["ec_cr_type"] != row.get("ec_cr_type"):
            # Hop dong da duyet giu loai cu (mau BBNT, so ngay thanh toan theo loai luc ky): doi loai
            # thi BBNT sau do lech ben ky (QC 17/11). Sai loai tu dau = lap creator dung loai + HD moi.
            used = getattr(self.repo, "approved_contract", None)
            hit = used(name) if used else None
            if hit:
                raise CreatorError("Creator đã có hợp đồng duyệt xong (%s) nên không đổi loại được. Tích \"Ngừng dùng "
                                   "creator này\", lưu, rồi tạo creator mới đúng loại và lập hợp đồng mới." % hit)
            values["supplier_type"] = domain.SUPPLIER_TYPE_BY_CREATOR.get(values["ec_cr_type"])
        merged = dict(row, **values)
        self._validate(merged)
        self._refuse_hard(self._shown(user, self.check_duplicates(merged, exclude=name)["hard"]))
        changed = domain.payment_changes(row, values)
        notes = []
        if changed:
            notes.append("Đổi thông tin nhận tiền (%s) bởi %s - Kế toán đối chiếu trước khi chi cho hợp "
                         "đồng đã ký." % (", ".join(changed), user))
        for field, label in (("supplier_name", "tên"), ("ec_cr_type", "loại")):
            if field in values and str(values[field] or "") != str(row.get(field) or ""):
                notes.append("%s đổi %s creator: \"%s\" -> \"%s\"." % (user, label, row.get(field) or "",
                                                                    values[field] or ""))
        if "disabled" in values:
            if values["disabled"] != (1 if row.get("disabled") else 0):
                notes.append("%s %s creator." % (user, "ngừng dùng" if values["disabled"] else "dùng lại"))
        note = " ".join(notes) or None
        self.repo.update(name, values, note=note)
        return {"name": name}

    def missing_misa(self, user):
        self._require_finance(user)
        return self.repo.missing_misa()

    def check_misa_code(self, name, code, overwrite=True, row=None):
        """Kiem MOT cap (creator, ma MISA) truoc khi ghi -> (row, ma da strip) hoac MisaCodeError.
        Noi DUY NHAT chua luat gan ma: nut Luu tung dong, xem truoc va ap dung khi nhap file deu goi day.
        overwrite=False (nhap file): khong de len creator da co ma - ma cu co the da nam tren hop dong."""
        code = str(code or "").strip()
        if not code:
            raise MisaCodeError("ma_trong", "Mã khách hàng MISA không được để trống.")
        bad = domain.misa_code_error(code)
        if bad:
            raise MisaCodeError("sai_dinh_dang", bad)
        row = row or (self.repo.get(name) if name else None)
        if not row:
            raise MisaCodeError("khong_tim_thay", "Không tìm thấy creator %s." % (name or "(trống)"))
        current = str(row.get("ec_cr_misa_code") or "").strip()
        if current and not overwrite:
            if current.casefold() == code.casefold():
                raise MisaCodeError("da_co_cung_ma", "Creator đã có đúng mã %s." % current)
            raise MisaCodeError("da_co_ma", "Creator đã có mã %s (khác %s): sửa tay nếu cần đổi." % (current, code))
        other = self.repo.misa_owner(code, name)
        if other:
            raise MisaCodeError("trung_creator_khac", "Mã %s đã gán cho creator %s." % (code, other))
        return row, code

    def set_misa_code(self, user, name, code, note=None, overwrite=True):
        """Ghi ma MISA cho mot creator: kiem quyen + luat (check_misa_code) + ghi + ghi vet tren ban ghi.
        Nhap file goi LAI ham nay cho tung dong (overwrite=False), khong co duong ghi thu hai."""
        self._require_finance(user)
        row, code = self.check_misa_code(name, code, overwrite=overwrite)
        old = str(row.get("ec_cr_misa_code") or "").strip()
        trace = note or "%s gán mã khách hàng MISA %s%s." % (user, code, (" (thay %s)" % old) if old and old != code else "")
        try:
            # isolate: loi validate cua Frappe chi huy DONG nay (nhap 500 dong khong mat ca lo vi 1 dong).
            self.repo.update(name, {"ec_cr_misa_code": code}, note=trace, isolate=True)
        except InsertError as e:
            raise CreatorError("Không lưu được mã MISA cho %s: %s" % (name, e))
        return {"name": name, "ec_cr_misa_code": code}

    # ---- noi bo ----------------------------------------------------------------
    def _require_finance(self, user):
        if not self.is_finance(user):
            raise CreatorPermissionError("Chỉ Kế toán (EC Finance) được làm việc này.")

    @staticmethod
    def _clean(data, with_identity):
        allowed = set(domain.WRITABLE_FIELDS)
        if with_identity:
            # Ke toan: sua ten / loai (PO 17/11). `disabled` KHONG qua day: chi update() cua Ke toan nhan
            # (QC he thong 17/11 - tao moi gui "disabled": "0" de lach chan trung cung).
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

    def _shown(self, user, matches):
        finance = self.is_finance(user)
        return [domain.mask_match(m, finance or m.get("owner") == user) for m in matches]

    @staticmethod
    def _refuse_hard(hard):
        if hard:
            raise CreatorError("Creator này đã có trong hệ thống: %s. Hãy chọn creator có sẵn."
                               % "; ".join(domain.describe_match(m) for m in hard))

    @staticmethod
    def _soft_message(matches):
        return ("Có thể đã có creator này: %s. Vẫn tạo creator mới?"
                % "; ".join(domain.describe_match(m) for m in matches))

    @staticmethod
    def _ack_note(matches):
        return "Người tạo xác nhận khác với: " + "; ".join(
            domain.describe_match(m) for m in matches)
