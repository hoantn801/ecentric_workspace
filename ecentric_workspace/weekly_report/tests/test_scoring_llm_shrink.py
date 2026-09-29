# Copyright (c) 2026, eCentric and contributors
"""Nhanh NEN trong `_bytes_for_kie` (them 25/09, chat Weekly Report).

Ban goc cua buoc 1: tong PDF vuot tran inline -> bo ca luot Kie, di Google. Dung
ve nguyen tac, nhung Google dang tra 400 tu 17/09 nen "du phong" luc nay la luoi
rach: deck lon se khong bao gio co diem. Hoan chot 25/09 la thu NEN truoc khi bo
cuoc.

Dieu PHAI giu, va la ly do bo test nay ton tai: ky luat tat-ca-hoac-khong-gi
khong duoc suy yeu. Nen duoc thi di Kie voi DU tep; nen khong duoc thi van tra
([], ly_do) nhu cu. Khong bao gio duoc gui mot phan deck -- model van cham diem,
cham tren du lieu thieu, va diem do vao KPI.
"""

import unittest

from ecentric_workspace import gemini_api
from ecentric_workspace.weekly_report import scoring_llm


class BytesForKieShrinkTest(unittest.TestCase):
    def setUp(self):
        from ecentric_workspace.weekly_report import sharepoint
        self._sp = sharepoint
        # Va vao module ma scoring_llm DANG tro toi, khong phai ban tu import:
        # bo test test_scoring_llm co luc gan de `scoring_llm.gemini_api` bang
        # stub, nen hai cai co the KHAC nhau tuy thu tu chay. Va nham = test
        # xanh gia vi no do ham that chu khong do ham minh dat vao.
        self.G = scoring_llm.gemini_api
        self._fetch = self.G.fetch_pdf_bytes
        self._shrink = self.G.shrink_pdf_for_inline
        self._max = scoring_llm.MAX_INLINE_TOTAL
        self._token = sharepoint.get_app_token
        # Thay tren CHINH module that: `_bytes_for_kie` dung
        # `from ... import sharepoint`, tuc lay thuoc tinh da gan tren package --
        # doi sys.modules khong an thua (da thu, 5 test do).
        sharepoint.get_app_token = lambda: "TOKEN"

    def tearDown(self):
        self.G.fetch_pdf_bytes = self._fetch
        self.G.shrink_pdf_for_inline = self._shrink
        scoring_llm.MAX_INLINE_TOTAL = self._max
        self._sp.get_app_token = self._token

    def _serve(self, sizes):
        blobs = [b"%PDF" + b"x" * (n - 4) for n in sizes]
        seq = list(blobs)

        def fake(url, token, dept):
            b = seq.pop(0)
            return {"ok": True, "data": b, "size_bytes": len(b),
                    "display_name": "d.pdf"}
        self.G.fetch_pdf_bytes = fake

    def test_under_limit_never_calls_shrink(self):
        scoring_llm.MAX_INLINE_TOTAL = 1000
        self._serve([300, 300])
        called = []
        self.G.shrink_pdf_for_inline = lambda *a, **k: called.append(1) or (None, "x")
        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(why, "")
        self.assertEqual(len(files), 2)
        self.assertEqual(called, [], "duoi tran thi khong duoc dung toi nen")

    def test_over_limit_shrinks_and_keeps_all_files(self):
        scoring_llm.MAX_INLINE_TOTAL = 1000
        self._serve([400, 900])
        self.G.shrink_pdf_for_inline = lambda data, max_bytes=None: (
            b"%PDF" + b"y" * 396, "da nen")
        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(why, "")
        self.assertEqual(len(files), 2, "phai giu DU tep, khong duoc bo bot")
        self.assertEqual(len(files[1]["data"]), 400)

    def test_shrink_fails_gives_up_whole_batch(self):
        """Khong nen duoc => ([], ly_do). Tuyet doi khong gui mot phan deck."""
        scoring_llm.MAX_INLINE_TOTAL = 1000
        self._serve([400, 900])
        self.G.shrink_pdf_for_inline = lambda data, max_bytes=None: (None, "qua san")
        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(files, [])
        self.assertIn("qua san", why)

    def test_download_failure_still_gives_up_whole_batch(self):
        """Nhanh nen KHONG duoc lam yeu ky luat cu."""
        scoring_llm.MAX_INLINE_TOTAL = 10000
        self.G.fetch_pdf_bytes = lambda url, token, dept: {
            "ok": False, "error": "Graph 404 itemNotFound"}
        files, why = scoring_llm._bytes_for_kie(["u1"], "Svc")
        self.assertEqual(files, [])
        self.assertIn("404", why)

    def test_all_files_are_shrunk_not_just_the_one_that_overflowed(self):
        """Vuot tran => nen DEU, khong don het len tep cuoi.

        Ban dau chi nen tep lam tran nguong: may tep dau an gan het ngan sach,
        tep cuoi du nen con 1MB van khong lot -> tu choi ca luot, trong khi nen
        deu ca ba thi vua. Dinh that 25/09 o WTU-2026-W37-HR-EMP-00011.
        """
        scoring_llm.MAX_INLINE_TOTAL = 900
        self._serve([600, 600])          # tong 1200 > 900
        seen = []

        def fake_shrink(data, max_bytes=None):
            seen.append((len(data), max_bytes))
            return b"%PDF" + b"z" * 396, "nen"
        self.G.shrink_pdf_for_inline = fake_shrink

        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(why, "")
        self.assertEqual(len(files), 2)
        self.assertEqual(len(seen), 2, "CA HAI tep phai duoc nen, khong chi mot")
        for _size, budget in seen:
            self.assertEqual(budget, 450, "ngan sach chia theo ty le kich thuoc")

    def test_final_total_check_catches_a_lying_shrinker(self):
        """Nen bao "thanh cong" ma ket qua van qua to => VAN phai tu choi.

        Luoi cuoi cung. Them sau khi dot bien "bo kiem lai tong sau khi nen"
        SONG SOT: moi ca test truoc do dung stub nen tra ve tep vua van, nen cai
        cong nay chua bao gio duoc thu. Mot cong khong ai do thi khong biet no
        co chay khong.
        """
        scoring_llm.MAX_INLINE_TOTAL = 900
        self._serve([600, 600])
        # tra ve "da nen" nhung van 600 byte moi tep -> tong 1200 > 900
        self.G.shrink_pdf_for_inline = lambda data, max_bytes=None: (
            b"%PDF" + b"q" * 596, "noi la da nen")
        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(files, [], "tong van qua tran thi khong duoc gui")
        self.assertIn("sau khi nen tat ca", why)

    def test_refuses_when_even_shrinking_everything_is_not_enough(self):
        scoring_llm.MAX_INLINE_TOTAL = 900
        self._serve([600, 600])
        self.G.shrink_pdf_for_inline = lambda data, max_bytes=None: (None, "qua san")
        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(files, [])
        self.assertIn("qua san", why)



def _pdf_without_bitmaps(pages, ops=20000):
    """PDF to ma KHONG co anh bitmap nao: ruot la content stream vector.

    Day la hinh dang cua deck xuat tu Office -- chu va hinh khoi la vector, anh
    (neu co) da nen san. Ha do phan giai khong an gi. Dung cai lam mot ban ghi
    ngon 25 giay cua worker de giam 95 byte tren 10MB, 29/09.

    Ban dau fixture nay nhoi bang `add_metadata`, va SAI: pypdf vut metadata khi
    ghi lai, nen ham nen "thanh cong" bang cach xoa phan nhoi -- 400.567 xuong
    551 byte. Content stream thi pypdf giu nguyen tung byte (da do: 852.132 ->
    852.132), tuc dung 0% loi -- moi la thu can thu.
    """
    import io as _io
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    w = PdfWriter()
    for _ in range(pages):
        pg = w.add_blank_page(width=595, height=842)
        body = "\n".join("%d %d m %d %d l S" % (i % 500, i % 800, (i * 7) % 500,
                                                (i * 3) % 800)
                         for i in range(ops))
        st = DecodedStreamObject()
        st.set_data(body.encode("ascii"))
        pg[NameObject("/Contents")] = w._add_object(st)
    buf = _io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _pdf_with_bitmaps(pages, w=900, h=600):
    """PDF ma ruot LA anh bitmap -- hinh dang cua deck bao cao tuan that.

    Anh nhieu ngau nhien de JPEG khong nen qua de, giong anh chup slide.
    """
    import io as _io
    import random
    from PIL import Image
    from pypdf import PdfReader, PdfWriter
    wr = PdfWriter()
    for i in range(pages):
        random.seed(i)
        img = Image.new("RGB", (w, h), (248, 249, 251))
        px = img.load()
        for _ in range(w * h // 8):
            px[random.randrange(w), random.randrange(h)] = (
                random.randrange(256), random.randrange(256), random.randrange(256))
        b = _io.BytesIO()
        img.save(b, format="PDF", quality=95)
        wr.add_page(PdfReader(_io.BytesIO(b.getvalue())).pages[0])
    out = _io.BytesIO()
    wr.write(out)
    return out.getvalue()


class ShrinkActuallyShrinksTest(unittest.TestCase):
    """Ham nen co THAT SU nen khong.

    Bo test nay dang le phai co tu 25/09 va da khong co. Moi test truoc do deu
    STUB `shrink_pdf_for_inline`, nen chung kiem ky ky luat cua NGUOI GOI
    (tat-ca-hoac-khong-gi) ma khong lan nao chay ham that. Mot test khac co
    chay that, nhung voi PDF VECTOR -- tuc chi di qua nhanh BO CUOC.

    Ket qua: tu 25/09 den 29/09 ham khong nen duoc mot byte nao ma van xanh het.
    `img.replace()` nem "Cannot update an image not belonging to a PdfWriter" o
    MOI anh vi vong lap duyet trang cua READER; `except Exception: continue`
    nuot sach. Nhin tu ngoai giong het "deck nay nen khong an".
    """

    def test_an_image_heavy_pdf_really_gets_smaller(self):
        data = _pdf_with_bitmaps(3)
        cap = len(data) // 3
        out, note = gemini_api.shrink_pdf_for_inline(data, max_bytes=cap)
        self.assertIsNotNone(out, "phai nen duoc: " + str(note))
        self.assertTrue(out.startswith(b"%PDF"), "ket qua phai la PDF hop le")
        self.assertLessEqual(len(out), cap, "phai lot tran da yeu cau")
        self.assertLess(len(out), len(data) * 0.5,
                        "giam duoi mot nua moi goi la nen; ban hong chi giam ~0%")

    def test_the_note_reports_the_real_numbers(self):
        data = _pdf_with_bitmaps(2)
        out, note = gemini_api.shrink_pdf_for_inline(data, max_bytes=len(data) // 3)
        self.assertIn("da nen", note)
        self.assertIn(str(len(out)), note, "ghi chu phai mang kich thuoc THAT")

    def test_a_deck_of_the_size_users_actually_submit_fits(self):
        """29/09 Hoan: deck 15-20MB phai cham duoc. Do that: 17.8MB -> 1.6MB.

        Bo test giu ban nho hon cho nhanh, nhung ty le giam la thu duoc ghim.
        """
        data = _pdf_with_bitmaps(4)
        out, _note = gemini_api.shrink_pdf_for_inline(
            data, max_bytes=gemini_api.KIE_INLINE_MAX_BYTES)
        if len(data) > gemini_api.KIE_INLINE_MAX_BYTES:
            self.assertIsNotNone(out)
            self.assertLessEqual(len(out), gemini_api.KIE_INLINE_MAX_BYTES)

    def test_images_found_but_unreplaceable_is_reported_as_such(self):
        """CO anh ma thay khong duoc -- phai noi ra, kem so luong va loi that.

        Day dung la hinh dang cua bug 25/09: `page.images` tim thay anh, nhung
        moi lan `replace()` deu nem loi va bi `except: continue` nuot. Nhin tu
        ngoai khong phan biet duoc voi "PDF nay khong co anh". Bon ngay khong ai
        thay. Neu ai do bo phan DEM loi di, test nay phai do.
        """
        from PIL import Image
        data = _pdf_with_bitmaps(2)
        # Chan o `resize`, KHONG o `Image.open`: `page.images` cua pypdf cung
        # goi `Image.open` ben trong, nen chan cho do lam ngoai le thoat ra
        # vong ngoai va bai thu thanh vo nghia (da dinh khi viet test nay).
        # `resize` chi duoc goi trong than try cua ham -- dung cho can thu.
        orig = Image.Image.resize

        def boom(*a, **k):
            raise RuntimeError("gia bo hong")
        Image.Image.resize = boom
        try:
            out, note = gemini_api.shrink_pdf_for_inline(data, max_bytes=len(data) // 3)
        finally:
            Image.Image.resize = orig
        self.assertIsNone(out)
        self.assertIn("KHONG thay duoc anh nao", note)
        self.assertIn("gia bo hong", note, "phai mang loi THAT, khong phai cau chung chung")

    def test_zero_images_says_so_instead_of_blaming_compression(self):
        """Khong co anh nao va 'co anh ma thay khong duoc' la HAI chuyen.
        Gop chung vao mot cau chinh la cach loi cu an minh bon ngay."""
        data = _pdf_without_bitmaps(2)
        out, note = gemini_api.shrink_pdf_for_inline(data, max_bytes=len(data) // 4)
        self.assertIsNone(out)
        self.assertIn("khong co anh bitmap nao", note)


class ShrinkGivesUpEarlyTest(unittest.TestCase):
    """Nen khong an thi phai dung NGAY, khong chay het cac buoc.

    Khong stub `shrink_pdf_for_inline` o day: chinh no la thu can thu. Stub no
    thi chi dang thu cai stub cua minh.
    """

    def test_no_bitmaps_means_give_up_at_the_first_step(self):
        """29/09: thong diep doi tu 'nen khong an' sang 'khong co anh bitmap nao'.

        Khong phai doi chu cho dep. Truoc do hai nguyen nhan rat khac nhau --
        KHONG CO anh de nen, va CO anh ma thay khong duoc -- deu ra cung mot
        cau, va chinh cho do giau mot loi that suot bon ngay. Y dinh cua test
        khong doi: phai dung o buoc DAU, khong chay het ba buoc.
        """
        data = _pdf_without_bitmaps(3)
        self.assertGreater(len(data), 100000, "PDF thu phai du to de vuot tran")
        out, note = gemini_api.shrink_pdf_for_inline(data, max_bytes=len(data) // 4)
        self.assertIsNone(out, "khong nen duoc thi phai tu choi, khong gui bua")
        self.assertIn("khong nen duoc", note)
        self.assertNotIn("het cac buoc", note,
                         "phai dung o buoc DAU, khong chay het ba buoc")

    def test_the_message_tells_a_human_what_to_do(self):
        """Ly do hong di thang vao Error Log. `van vuot tran sau khi nen het cac
        buoc` khong cho ai biet phai lam gi; 'can nguoi nop xuat lai file nhe
        hon' thi co."""
        data = _pdf_without_bitmaps(2)
        _out, note = gemini_api.shrink_pdf_for_inline(data, max_bytes=len(data) // 4)
        self.assertIn("xuat lai file nhe hon", note)

    def test_threshold_is_a_stated_decision_not_a_magic_number(self):
        self.assertEqual(gemini_api.SHRINK_MIN_GAIN, 0.05)

    def test_small_enough_file_is_returned_untouched(self):
        """Canh doi: dung som KHONG duoc lam hong duong di binh thuong."""
        data = _pdf_without_bitmaps(1)
        out, note = gemini_api.shrink_pdf_for_inline(data, max_bytes=len(data) * 2)
        self.assertIs(out, data)
        self.assertEqual(note, "")


class InlineCeilingTest(unittest.TestCase):
    """Tran inline la con so DO DUOC, khong phai con so chon.

    Ghim lai de lan sau ai muon doi thi phai doi bang mot phep do moi, khong
    phai bang cam giac. Ba moc duoi deu tu snapshot kie_inline_20260929_133355.
    """

    def test_ceiling_is_at_most_what_the_primary_model_accepted(self):
        """gemini-3-8-flash nhan 3.152.375 byte. Tran khong duoc vuot moc do."""
        self.assertLessEqual(gemini_api.KIE_INLINE_MAX_BYTES, 3152375)

    def test_ceiling_is_below_the_size_kie_actually_refused(self):
        """Loi 400 dau tien: base64 len=5078436 -> PDF goc ~3.63 MiB."""
        self.assertLess(gemini_api.KIE_INLINE_MAX_BYTES, int(5078436 * 3 / 4))

    def test_ceiling_was_not_dragged_down_to_the_openai_dialect(self):
        """Nhanh `-openai` tu choi o ~2.1 MiB. Neu ai do "sua cho an toan" bang
        cach ha tran xuong duoi muc do, deck binh thuong se het cham duoc --
        trong khi cach dung la BO QUA nhanh do khi tep lon, nhu da bo qua
        gpt-6-luna. Test nay chan dung huong sua sai do."""
        oai_refused_raw = int(2800916 * 3 / 4)     # ~2.1 MiB
        self.assertGreater(gemini_api.KIE_INLINE_MAX_BYTES, oai_refused_raw)


class ShrinkGuardTest(unittest.TestCase):
    def test_returns_input_untouched_when_already_small(self):
        data = b"%PDF" + b"a" * 100
        out, note = gemini_api.shrink_pdf_for_inline(data, max_bytes=1000)
        self.assertIs(out, data)
        self.assertEqual(note, "")

    def test_empty_input_is_refused(self):
        out, note = gemini_api.shrink_pdf_for_inline(b"", max_bytes=10)
        self.assertIsNone(out)

    def test_floor_is_half_scale(self):
        """San chat luong la mot quyet dinh, khong phai con so tuy tien:
        ha them nua thi slide mo den muc model doc sai ma van cham diem."""
        self.assertEqual(gemini_api.SHRINK_MIN_SCALE, 0.5)
        self.assertTrue(all(s >= gemini_api.SHRINK_MIN_SCALE
                            for s, _q in gemini_api.SHRINK_STEPS))
