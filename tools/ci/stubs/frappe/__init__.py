# Copyright (c) 2026, eCentric and contributors
"""Stub `frappe` -- vừa đủ để IMPORT một module của app, KHÔNG hơn.

Phép kiểm `pagesync` trong `tools/ci/check.py` cần gọi thật hàm `_html()` của từng
`page_sync.py` để băm chuỗi HTML mà commit này ship. Muốn gọi được thì phải import được
module, mà mọi module ấy đều mở đầu bằng `import frappe` + `from frappe import _` và kết
thúc bằng `@frappe.whitelist(...)`. Cài `frappe` thật vào job CI thì cần MariaDB + Redis +
một site -- tức là không còn là job nhẹ nữa.

PHẠM VI. Stub này chỉ bảo đảm một điều: `import` không nổ. Nó KHÔNG mô phỏng hành vi của
Frappe. Mọi thuộc tính chưa khai bên dưới trả về `_Anything` -- một vật thể nuốt mọi thao
tác. Nếu một ngày phép kiểm cần tới hành vi thật của `frappe.db` thì đó là dấu hiệu phép
kiểm đã đi quá xa khỏi "chạy được mà không cần bench", chứ không phải dấu hiệu cần làm
stub dày thêm.

`_html()` của các page_sync hiện chỉ đụng `os`, `open` và (ở payment_request) nối chuỗi --
không chạm `frappe` lần nào. Đó là lý do stub mỏng thế này là đủ.
"""
import sys
import types


class _Anything:
    """Nuốt mọi thao tác và trả về chính loại của mình.

    Dùng được như module, như đối tượng, như hàm, như decorator có/không tham số.
    """

    __slots__ = ("_path",)

    def __init__(self, path="frappe"):
        object.__setattr__(self, "_path", path)

    def __getattr__(self, item):
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        return _Anything("%s.%s" % (self._path, item))

    def __setattr__(self, item, value):
        pass

    def __call__(self, *args, **kwargs):
        # Decorator dùng trần: @frappe.whitelist
        if len(args) == 1 and not kwargs and callable(args[0]):
            return args[0]
        return _Anything("%s()" % self._path)

    def __getitem__(self, item):
        return _Anything("%s[%r]" % (self._path, item))

    def __setitem__(self, item, value):
        pass

    def __iter__(self):
        return iter(())

    def __contains__(self, item):
        return False

    def __bool__(self):
        return False

    def __len__(self):
        return 0

    def __repr__(self):
        return "<stub %s>" % self._path


# -- những thứ phải là thật, không thể là _Anything ------------------------

def _(text, *args, **kwargs):
    """`from frappe import _` -- trả lại nguyên văn.

    Phải là hàm thật: một số module nối chuỗi dịch vào HTML, và `_Anything` sẽ biến
    chuỗi đó thành `<stub ...>` -- sai một cách im lặng, đúng loại lỗi phép kiểm này
    sinh ra để bắt.
    """
    return text


def whitelist(*args, **kwargs):
    """`@frappe.whitelist()` và `@frappe.whitelist(methods=[...])` đều thành no-op."""
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]

    def decorator(fn):
        return fn

    return decorator


# Một số module kế thừa các lớp này ở cấp module (`class X(frappe.ValidationError)`),
# nên chúng phải là exception thật chứ không phải _Anything.
class ValidationError(Exception):
    pass


class PermissionError(ValidationError):
    pass


class DoesNotExistError(ValidationError):
    pass


class DuplicateEntryError(ValidationError):
    pass


class LinkValidationError(ValidationError):
    pass


class MandatoryError(ValidationError):
    pass


class TimestampMismatchError(ValidationError):
    pass


def throw(msg, exc=ValidationError, **kwargs):
    raise exc(msg) if isinstance(exc, type) else ValidationError(msg)


def msgprint(*args, **kwargs):
    return None


def __getattr__(name):
    """Mọi thứ chưa khai ở trên (`frappe.db`, `frappe.session`, ...) -> _Anything."""
    if name.startswith("__"):
        raise AttributeError(name)
    return _Anything("frappe.%s" % name)


# -- module con sinh theo yêu cầu -----------------------------------------

class _StubFinder:
    """Sinh `frappe.<bất kỳ>` ra như một module rỗng, tự động.

    `from frappe.utils import cint`, `from frappe.model.document import Document`... --
    thay vì đoán trước danh sách và tạo sẵn file cho từng cái, cứ để import máy hỏi tới
    đâu thì dựng tới đó. Chỉ nhận tên bắt đầu bằng `frappe.`, nên không đụng gì khác.
    """

    @staticmethod
    def find_module(fullname, path=None):  # API cũ, một số công cụ vẫn gọi
        return None

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith("frappe."):
            return None
        import importlib.machinery

        return importlib.machinery.ModuleSpec(fullname, _StubLoader(), is_package=True)


class _StubLoader:
    def create_module(self, spec):
        module = types.ModuleType(spec.name)
        module.__path__ = []
        return module

    def exec_module(self, module):
        module.__getattr__ = lambda name: _Anything("%s.%s" % (module.__name__, name))


sys.meta_path.append(_StubFinder())
