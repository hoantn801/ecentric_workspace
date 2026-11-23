"""Immutable contract implemented by every Approval Center request type."""
import re
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Tuple


FilterBuilder = Callable[[dict, dict], None]
OptionsProvider = Callable[[], dict]
TitleBuilder = Callable[[object], str]
Submitter = Callable[[str], str]
Resubmitter = Callable[[str, Optional[str]], dict]

STANDARD_STATUS_LABELS = (
    ("Draft", "Nháp"),
    ("Pending", "Đang phê duyệt"),
    ("Information Required", "Cần bổ sung"),
    ("Approved", "Đã duyệt"),
    ("Rejected", "Bị từ chối"),
    ("Cancelled", "Đã hủy"),
)

#: Kieu hien thi hop le cho mot cot them o tab "Tat ca" (xem `all_tab_columns`).
ALL_TAB_COLUMN_KINDS = ("text", "money", "date", "select")
#: Ten truong duoc phep khai cho tab "Tat ca". Ten nay se di vao SQL (duoi dang dinh danh
#: trong dau backtick) nen chan ngay tu luc nap registry, khong doi toi luc truy van.
_FIELDNAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
#: Loai buoc hop le trong `journey_after`.
JOURNEY_KINDS = ("fulfillment", "auto", "form", "info")


@dataclass(frozen=True, slots=True)
class ApprovalDefinition:
    """Stateless singleton configuration for one business request type.

    Values must be immutable. Callbacks receive all request-specific state as
    arguments and must never retain Documents, users, or request context.
    """

    code: str
    business_doctype: str
    editable_fields: Tuple[str, ...]
    my_request_fields: Tuple[str, ...]
    approval_list_fields: Tuple[str, ...]
    status_labels: Tuple[Tuple[str, str], ...]
    options_provider: OptionsProvider
    title_builder: Optional[TitleBuilder]
    submitter: Submitter
    resubmitter: Resubmitter
    filter_builder: Optional[FilterBuilder] = None
    max_page_length: int = 50
    approval_projection: str = "standard"
    draft_preparer: Optional[Callable] = None
    feature: str = ""
    #: "Cho toi duyet" tren dien thoai (06/10/2026): MOI loai phieu tu khai 3-5 cap
    #: (nhan, fieldname) hien tren the duyet nhanh. Chi dua truong nguoi duyet VON da xem o
    #: trang chi tiet; KHONG dua luong ca nhan. De trong -> the chi co tieu de + nguoi nop.
    quick_summary: Tuple[Tuple[str, str], ...] = ()
    #: Trang form bat buoc nhan xet khi DUYET (luat dang nam o UI tung form) -> the duyet
    #: nhanh cung bat, va loai nay khong vao duyet hang loat.
    quick_comment_required: bool = False
    #: Loai phieu co nut "Tu choi" hay khong (23/11/2026, HR v2). Mac dinh True = nhu cu.
    #: False -> command_service.reject chan o may chu (moi duong: trang form, hub, duyet nhanh
    #: tren dien thoai deu qua do) va capabilities.derive tra can_reject=False de UI an nut.
    #: Vd Don nghi viec: NLD co quyen don phuong nghi khi bao truoc du ngay (Dieu 35 BLLD 2019),
    #: nguoi duyet chi "Duyet" hoac "Tra lai dieu chinh" - khong co "Tu choi".
    allow_reject: bool = True
    #: Truong KHONG duoc chep khi "Tao phieu moi tu phieu nay".
    #:
    #: Danh cho cac o mang tinh CAM KET CA NHAN - nguoi dung tich vao de xac nhan mot dieu
    #: gi do. Chep nguyen mot lo cam ket sang phieu moi la ky thay ho: man hinh se noi ho
    #: "da xac nhan thong tin va tep dinh kem la chinh xac" cho mot bo ho so ho chua doc lai.
    #: De trong la mac dinh; module nao co o nhu vay thi tu khai ra.
    clone_exclude_fields: Tuple[str, ...] = ()
    #: Truong KHONG duoc de AI dien ho (du no nam trong `editable_fields`).
    #:
    #: Ba luat loai tru chay song song, khai o `shared/integrations/ai_formfill.build_schema`:
    #:   1. kieu truong  - tep dinh kem, bang con, chu ky, va MOI `Check` (o tick nao cung la
    #:      mot khang dinh cua nguoi dung, khong phai du kien doc duoc tu ho so);
    #:   2. `clone_exclude_fields` - dung lai NGUYEN SI. Tuple do da duoc dinh nghia dung la
    #:      "o cam ket ca nhan, chep sang la ky thay nguoi dung". AI dien vao do cung la ky
    #:      thay, cung mot ly do;
    #:   3. tuple NAY - cho truong khong phai tep, khong phai cam ket, nhung van phai do
    #:      nguoi lam: phan doan nghiep vu (`is_cost_valid`), o keo theo mot picker co phan
    #:      quyen (`funding_source_*`), hay o ma gui di se TAO mot ban ghi danh muc moi
    #:      (`ec_brand_ten`).
    ai_exclude_fields: Tuple[str, ...] = ()

    #: Chi dan THEM cho AI o mot so truong, dang {fieldname: "cau chi dan"}.
    #:
    #: Vi sao khong nhet vao `description` cua truong: `description` la chu hien tren MAN
    #: HINH cho nguoi dung doc. Chi dan cho AI la thu khac - no noi ve cach dien, doi khi
    #: noi "de trong di", va khong ai muon doc cau do duoi o nhap.
    #:
    #: Day KHONG phai schema viet tay cho tung form: schema van tu sinh tu `editable_fields`.
    #: Day chi la mot cau ghi chu cho MOT truong, tuy chon, mac dinh rong.
    #: Mac dinh la MappingProxyType({}) chu khong phai {}: dataclass tu choi default kieu
    #: dict, va lop nay `frozen` nen mot dict dung chung giua cac dinh nghia la bay.
    ai_hints: Mapping[str, str] = MappingProxyType({})
    #: Khoi doc them cho man hinh chi tiet, do module so huu: (business_doc, approval_request)
    #: -> dict, gan vao detail["extra"]. Dung khi form can ngu canh ngoai phieu (Payment Request:
    #: chuoi cac dot thanh toan). Chi DOC; khong ghi, khong giu tham chieu.
    detail_extender: Optional[Callable] = None
    #: An bot truong nhay cam khoi man hinh chi tiet theo NGUOI XEM, do module so huu:
    #: (business_dict, approval_request) -> None, sua business_dict tai cho. Chay SAU khi doc
    #: phieu, TRUOC khi tra ve trinh duyet - moi duong doc chi tiet (form, hub, action center)
    #: di qua query_service.get_detail nen chi can mot cho. Vd Promotion (29/09): nguoi duyet
    #: khong xem duoc luong nhan su do (Lead o buoc quan ly truc tiep) khong thay so luong.
    business_redactor: Optional[Callable] = None
    #: Loc danh sach dinh kem cua man hinh chi tiet theo NGUOI XEM, do module so huu:
    #: (attachments, business_doc, approval_request) -> list moi. Vd Hop dong KOL (17/11/2026):
    #: ban hop dong / BBNT du thong tin ca nhan creator chi nguoi tao creator + Ke toan thay.
    attachment_redactor: Optional[Callable] = None
    #: Ba dau hieu ngoai le cho tab "Tao hang loat", do module so huu:
    #: (rows, user) -> {key: {ten_co: bool}}. Mac dinh None = form nay khong co dau hieu nao
    #: va man hinh chi don gian khong ve cot do.
    #:
    #: Vi sao la mot callback tren dinh nghia chu khong phai mot nhanh `if approval_code ==`
    #: trong endpoint dung chung: dau hieu la NGHIEP VU cua tung form (Payment Request dem
    #: so tai khoan; mot form nghi phep se dem thu khac hoan toan), va endpoint dung chung
    #: da co dung mot luat - hoi registry. Them form thu 29 khong duoc sua file nay.
    batch_flagger: Optional[Callable] = None
    #: Cot THEM cho tab "Tat ca" cua form nay: ((nhan, fieldname, kieu), ...), kieu thuoc
    #: ALL_TAB_COLUMN_KINDS. fieldname la truong cua `business_doctype` (khong phai cua
    #: EC Approval Request). Server doc gia tri theo lo cho trang dang xem va dua vao tep
    #: xuat. Cot trung voi truong so tien cua form (business_summary.AMOUNT_FIELDS) KHONG
    #: them cot moi - nhan cua no thay cho nhan "So tien" cua cot da co.
    #: Mac dinh rong = bang giu nguyen 5 cot nhu cu.
    all_tab_columns: Tuple[Tuple[str, str, str], ...] = ()
    #: Truong (cua `business_doctype`) co o loc dang danh sach chon tren tab "Tat ca". Gia tri
    #: trong danh sach chi lay tu nhung phieu NGUOI XEM DUOC PHEP XEM (scope_predicate).
    all_tab_filters: Tuple[str, ...] = ()
    #: PHIEU RIENG TU (Dot 0 HR, 23/11/2026). True -> chi nguoi gui, nguoi co dong duyet trong
    #: snapshot, nguoi theo doi, nguoi xu ly cua phieu va System Manager (co nhat ky) xem duoc.
    #: Loai khoi pham vi truong phong / Approval Admin / tab "Tat ca" / thong ke / export.
    #: Mot luat DUY NHAT o `shared/workflow/privacy.py` - EC Approval Type.private = 1 cung bat
    #: duoc (cau hinh), hai nguon OR voi nhau. Xem HR_DOT0_INTERFACE.md.
    private: bool = False
    #: Truong cua `business_doctype` chi DOI TUONG cua phieu (nguoi duoc noi toi: nhan vien
    #: nghi viec, nguoi duoc danh gia...). Gia tri la email/User hoac ma Employee. Engine loai
    #: nguoi gui + doi tuong khoi moi cap duyet (chan tu duyet) - xem transitions._self_exclusion.
    subject_fields: Tuple[str, ...] = ()
    #: CHAN NGUOI GUI tu duyet (opt-in, 23/11/2026). MAC DINH False vi F12 (25/09, Hoan xac nhan):
    #: o 34 form cu nguoi gui nam trong cap duyet cua chinh minh thi DUOC tu duyet - la rule, khong
    #: phai loi. Chi cac form HR moi bat (dot 0-3). Muon ap cho form cu phai hoi Hoan.
    #: Doi tuong (subject_fields) thi luon bi loai khoi cap duyet, khong phu thuoc co nay.
    block_self_approval: bool = False
    #: Truong AN voi nguoi CHI la nguoi theo doi (participant_purpose="Notify") - vd luong offer.
    #: query_service.detail xoa gia tri truoc khi tra ve trinh duyet. Nguoi gui / nguoi duyet /
    #: System Manager van thay.
    watcher_hidden_fields: Tuple[str, ...] = ()
    #: CAC BUOC SAU KHI DUYET XONG (24/11/2026, Hoan: "show full quy trinh tu A-Z"). Moi phan tu
    #: (ten buoc, mo ta ngan, loai): loai thuoc JOURNEY_KINDS -
    #:   "fulfillment" bo phan nhan viec tren chinh phieu nay (hang doi xu ly);
    #:   "auto"        he thong tu lam ngay khi duyet xong (ghi ho so, ghi cong...);
    #:   "form"        tu tao / mo tiep MOT PHIEU KHAC (Offer, New Staff Preparation, Clearance...);
    #:   "info"        viec tiep theo ngoai phieu (onboard, ban hanh quyet dinh...).
    #: Trang ve bang EcApprovalUI.withJourney (public/js/ec_approval_ui.bundle.js). Ten buoc trung
    #: ten buoc trang da tu ve (vd "Finance xu ly UNC") thi giu buoc cua trang (co trang thai that).
    journey_after: Tuple[Tuple[str, str, str], ...] = ()

    @property
    def status_label_map(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self.status_labels))


def validate_definition(definition: ApprovalDefinition) -> None:
    """Raise ValueError when a registered definition violates the ADR contract."""
    if not isinstance(definition, ApprovalDefinition):
        raise ValueError("request definition must be an ApprovalDefinition")
    if not definition.code or not definition.business_doctype:
        raise ValueError("request definition requires code and business_doctype")
    if definition.max_page_length < 1:
        raise ValueError("max_page_length must be positive")
    if definition.approval_projection not in ("standard", "legacy_level_name"):
        raise ValueError("unsupported approval_projection")
    for item in fields(definition):
        value = getattr(definition, item.name)
        if isinstance(value, (list, dict, set)):
            raise ValueError("mutable definition field: %s" % item.name)
    for callback_name in ("options_provider", "submitter", "resubmitter"):
        if not callable(getattr(definition, callback_name)):
            raise ValueError("definition callback is not callable: %s" % callback_name)
    if definition.title_builder is not None and not callable(definition.title_builder):
        raise ValueError("definition callback is not callable: title_builder")
    if definition.draft_preparer is not None and not callable(definition.draft_preparer):
        raise ValueError("definition callback is not callable: draft_preparer")
    if definition.detail_extender is not None and not callable(definition.detail_extender):
        raise ValueError("definition callback is not callable: detail_extender")
    if definition.attachment_redactor is not None and not callable(definition.attachment_redactor):
        raise ValueError("definition callback is not callable: attachment_redactor")
    if definition.batch_flagger is not None and not callable(definition.batch_flagger):
        raise ValueError("definition callback is not callable: batch_flagger")
    _validate_all_tab(definition)
    for attr in ("subject_fields", "watcher_hidden_fields"):
        for fieldname in getattr(definition, attr):
            if not (isinstance(fieldname, str) and _FIELDNAME_RE.match(fieldname)):
                raise ValueError("%s fieldname is not a plain fieldname: %r" % (attr, fieldname))
    for step in definition.journey_after:
        if not (isinstance(step, tuple) and len(step) == 3 and all(isinstance(x, str) and x for x in step)
                and step[2] in JOURNEY_KINDS):
            raise ValueError("journey_after entries must be (label, meta, kind in %s): %r"
                             % (JOURNEY_KINDS, step))
    if not isinstance(definition.private, bool):
        raise ValueError("private must be a bool")
    if not isinstance(definition.block_self_approval, bool):
        raise ValueError("block_self_approval must be a bool")


def _validate_all_tab(definition: ApprovalDefinition) -> None:
    """Khai bao tab "Tat ca" sai thi gay LUC NAP, khong phai luc mot nguoi bam loc."""
    for col in definition.all_tab_columns:
        if not (isinstance(col, tuple) and len(col) == 3
                and all(isinstance(x, str) for x in col)):
            raise ValueError("all_tab_columns entries must be (label, fieldname, kind)")
        label, fieldname, kind = col
        if not label.strip():
            raise ValueError("all_tab_columns label is empty: %s" % fieldname)
        if not _FIELDNAME_RE.match(fieldname):
            raise ValueError("all_tab_columns fieldname is not a plain fieldname: %r" % fieldname)
        if kind not in ALL_TAB_COLUMN_KINDS:
            raise ValueError("all_tab_columns kind not allowed: %r" % kind)
    for fieldname in definition.all_tab_filters:
        if not (isinstance(fieldname, str) and _FIELDNAME_RE.match(fieldname)):
            raise ValueError("all_tab_filters fieldname is not a plain fieldname: %r" % (fieldname,))


