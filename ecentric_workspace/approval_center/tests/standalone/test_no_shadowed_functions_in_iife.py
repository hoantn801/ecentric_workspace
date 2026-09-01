# Copyright (c) 2026, eCentric and contributors
"""Hai ham TRUNG TEN trong cung mot IIFE: ban sau de ban truoc, im lang.

Tim thay 02/09 khi chay E2E bang tay. `document_signing_section.html` khai bao

    dong 204:  function progressText(d)   // tien do cua MOT tai lieu
    dong 479:  function progressText()    // tien do cua NGAN dat chu ky

trong cung mot IIFE. Khai bao ham duoc hoisted, nen ban o 479 de ban o 204, va moi loi goi
`progressText(d)` khi dung dong tai lieu thuc chat chay ham cua ngan - bo qua tham so `d` va
doc `DRW.st`. Hau qua tren man hinh: dong tai lieu luon hien tien do cua NGAN, tuc "0/0" moi
lan tai trang. Mot cap duyet mo phieu ra se thay "Da thiet lap · 0/0" va co the ket luan chua
ai dat chu ky - trong khi ca 5 chan ky da thiet lap day du.

Khong co dau hieu nao. Khong loi console, khong 500, khong test do. Chi la mot con so sai
tren mot man hinh duyet chi tien.

Cong QC nay quet MOI template .html duoc bom vao trang: trong pham vi mot IIFE, hai
`function <ten>(` trung ten la DO. Doi ten mot trong hai la xong - khong ton gi - nhung neu
khong ai canh thi lan sau lai co mot cap trung ten khac.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()

#: Do SAU NGOAC quyet dinh pham vi, khong phai thut le.
#:
#: Ban dau cong nay chi so TEN va bao 12 cap trong pm_app.html (`close` 9 lan) - toan bo la
#: ham con nam trong cac ham cha khac nhau. Ban thu hai xap xi pham vi bang thut le, van bao
#: nham vi hai ham con cua hai cha khac nhau co the cung muc thut. Mot cong bao dong gia thi
#: khong ai dam bat, nen no thanh vo dung. Gio dem ngoac nhon that su.
_KHAI_BAO = re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\(")

#: Chu thich mot dong va khoi - go truoc khi quet, neu khong mot vi du trong chu thich se
#: bi tinh la khai bao that. Da mat mot vong chan doan vi bay nay (grep trung chu thich).
_CHU_THICH_KHOI = re.compile(r"/\*.*?\*/", re.S)
_CHU_THICH_DONG = re.compile(r"(?m)//.*$")


def _khai_bao_theo_pham_vi(block):
    """[(do_sau, ten)] cho moi `function ten(`, do_sau = so ngoac nhon dang mo tai cho do."""
    block = _CHU_THICH_KHOI.sub("", block)
    block = _CHU_THICH_DONG.sub("", block)
    ra, depth, i, n = [], 0, 0, len(block)
    while i < n:
        c = block[i]
        if c in "\"'`":                       # bo qua ca chuoi: ngoac ben trong khong tinh
            q, i = c, i + 1
            while i < n and block[i] != q:
                i += 2 if block[i] == "\\" else 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif block.startswith("function", i) and (i == 0 or not (block[i-1].isalnum()
                                                                or block[i-1] in "_$.")):
            m = _KHAI_BAO.match(block, i)
            if m:
                ra.append((depth, m.group(1)))
        i += 1
    return ra


def _script_blocks(src):
    """Noi dung tung <script>...</script>. Moi khoi la mot pham vi rieng."""
    return re.findall(r"<script\b[^>]*>(.*?)</script>", src, re.S | re.I)


def _templates():
    out = []
    for base, _dirs, files in os.walk(_ROOT):
        if "__pycache__" in base or os.sep + "tests" + os.sep in base:
            continue
        for f in files:
            if f.endswith(".html"):
                out.append(os.path.join(base, f))
    return sorted(out)


class TestKhongCoHamTrungTenTrongCungMotPhamVi(unittest.TestCase):
    def test_phep_do_bat_duoc_mot_cap_trung_ten_gia_lap(self):
        """Kiem CHINH CAI CONG truoc khi tin no.

        Neu regex hong (doi quy uoc thut le, doi cach viet ham) thi phep kiem duoi se xanh
        vinh vien va khong ai biet. Cho no mot mau CHAC CHAN sai truoc.
        """
        mau = ("<script>(function(){\n"
               "  function progressText(d) { return d; }\n"
               "  function progressText() { return 1; }\n"
               "})();</script>")
        trung = self._trung_ten(mau)
        self.assertEqual(trung, [("progressText", 2)],
                         "phep do khong bat duoc cap trung ten hien nhien -> moi ket qua "
                         "xanh ben duoi deu vo nghia")

    def test_phep_do_khong_bao_dong_gia(self):
        mau = ("<script>(function(){\n"
               "  function a() {}\n"
               "  // function a() {}   <- chu thich, khong tinh\n"
               "  function b() {}\n"
               "  function ngoai() {\n"
               "    function close() {}\n"   # ham con - pham vi rieng
               "  }\n"
               "  function ngoai2() {\n"
               "    function close() {}\n"   # trung ten nhung KHAC pham vi
               "  }\n"
               "})();</script>")
        self.assertEqual(self._trung_ten(mau), [],
                         "bao dong gia thi khong ai dam bat cong nay")

    @staticmethod
    def _trung_ten(src):
        xau = []
        for block in _script_blocks(src):
            # CHI xet cap cao nhat cua khoi <script> (do sau <= 1: ngay trong IIFE bao
            # ngoai). Do la pham vi DUY NHAT ma "cung do sau" chac chan la "cung pham vi".
            # Sau hon thi hai ham con cua hai cha khac nhau cung nam o cung do sau ma hoan
            # toan khong lien quan - da bao nham dung kieu do hai lan truoc khi siet lai.
            # Hep hon that, nhung bat dung lop loi da xay ra, va khong bao dong bao gio sai.
            dem = {}
            for depth, ten in _khai_bao_theo_pham_vi(block):
                if depth <= 1:
                    dem[ten] = dem.get(ten, 0) + 1
            xau += [(t, n) for t, n in sorted(dem.items()) if n > 1]
        return xau

    #: Da co san khi cong nay ra doi (02/09). KHONG phai duoc tha - la no chua duoc soi.
    #: `pm_app.html` co 3 cap trung ten o cap cao nhat: `out` (4), `render` (3), `walk` (3).
    #: Cung dung lop loi voi `progressText`, nhung nam ngoai pham vi Payment Request va sua
    #: mu thi de lam hong PM. Ghi ra day de no HIEN, khong bien mat trong im lang; go khoi
    #: danh sach nay khi co nguoi thuc su doc lai pm_app.
    NGOAI_LE = {"pm/frontend/pm_app.html"}

    def test_ngoai_le_van_con_ly_do_ton_tai(self):
        """Ngoai le khong duoc tro thanh vinh vien vi ai cung quen no."""
        for rel in self.NGOAI_LE:
            path = os.path.join(_ROOT, *rel.split("/"))
            self.assertTrue(os.path.exists(path),
                            "%s khong con ton tai - go khoi danh sach ngoai le" % rel)
            src = io.open(path, encoding="utf-8").read()
            self.assertTrue(self._trung_ten(src),
                            "%s da het trung ten - go khoi danh sach ngoai le, dung de mot "
                            "ngoai le rong che mat lan tai pham sau" % rel)

    def test_khong_template_nao_co_ham_trung_ten(self):
        loi = []
        for path in _templates():
            rel = os.path.relpath(path, _ROOT).replace(os.sep, "/")
            if rel in self.NGOAI_LE:
                continue
            src = io.open(path, encoding="utf-8").read()
            for ten, n in self._trung_ten(src):
                loi.append("%s: function %s khai bao %d lan"
                           % (os.path.relpath(path, _ROOT).replace(os.sep, "/"), ten, n))
        self.assertEqual(
            loi, [],
            "Hai ham trung ten trong cung mot <script>: ban sau DE ban truoc va moi loi goi "
            "ban truoc lang le chay ban sau. Khong loi, khong test do - chi la mot con so "
            "sai tren man hinh. Doi ten mot trong hai.\n  " + "\n  ".join(loi))


if __name__ == "__main__":
    unittest.main()
