"""Chapter detection on a textbook laid out as titled pieces with author lines."""
import unittest

from processing.chunker import detect_chapters
from processing.pdf_extractor import Page

FILLER = "આ પાઠમાં વિદ્યાર્થીઓ ભાષા અને મૂલ્યો વિશે શીખે છે. સ્વાધ્યાય અને પ્રવૃત્તિઓ આપેલી છે."


def page(n, *lines):
    return Page(n, "\n".join(lines + (FILLER,)), "ocr")


def book(contents=None):
    pages = [
        # Epigraph page: several verses, each with its poet. Not a chapter.
        page(1, "રમતાં રમતાં લડી પડે ભે માણસ છે !", "હસતાં હસતાં રડી પડે ભે માણસ છે !",
             "- જયંત પાઠક", "હુંય ગની નીકળ્યો છું", "- ગની દહીંવાળા"),
        page(2, *(contents or ["પ્રસ્તાવના"])),
        page(3, "આ તો ઈશ તણો આવાસ", "- કરસનદાસ માણેક",
             "કરસનદાસ માણેકનો જન્મ કરાંચીમાં થયો હતો."),
        page(4, "1. વાતચીત.", "2. ઉદાહરણ વાંચો."),  # exercises: not a chapter
        page(5, "સાઈકલ-સવારીની ખાટીમીઠી", "- મનસુખ સલ્લા",
             "મનસુખ સલ્લાનો જન્મ થયો હતો."),
        # Dialogue lines that start with a dash: not author lines.
        page(6, ". રવીન્દ્ર ગયો ખરો.", "- મારી પાસે છત્રી નહોતી તેથી હું પલળી ગયો.",
             "- એ ઘરે આવ્યો."),
        # Title lost to OCR: only the author line and biography remain.
        page(7, "- ફાધર વાલેસ", "ફાધર વાલેસનો જન્મ સ્પેન દેશમાં થયો હતો."),
        page(8, "ગઢની રઢ છોડો !", "- ભાનુકુમાર ત્રિવેદી",
             "ભાનુકુમાર ત્રિવેદીનો જન્મ થયો હતો."),
    ]
    return pages


class AnthologyChapters(unittest.TestCase):
    def test_pieces_open_at_title_and_author_line(self):
        chapters = detect_chapters(book())
        self.assertEqual([(c.start_page, c.end_page) for c in chapters],
                         [(3, 4), (5, 6), (7, 7), (8, 8)])
        self.assertEqual(chapters[0].title, "આ તો ઈશ તણો આવાસ")
        self.assertEqual(chapters[1].title, "સાઈકલ-સવારીની ખાટીમીઠી")

    def test_missing_title_falls_back_to_author(self):
        self.assertEqual(detect_chapters(book())[2].title, "ફાધર વાલેસ")

    def test_contents_page_names_and_adds_pieces(self):
        # Printed page = PDF page - 2. Two titles agree, so the offset is trusted.
        contents = ["અનુક્રમણિકા", "આ તો ઈશ તણો આવાસ 1", "સાઈકલ-સવારીની ખાટીમીઠી 3",
                    "ખોટો જવાબ 5", "ગઢની રઢ છોડો ! 6"]
        chapters = detect_chapters(book(contents))
        self.assertEqual(chapters[2].title, "ખોટો જવાબ")
        self.assertEqual(len(chapters), 4)

    def test_excerpt_with_one_piece_uses_it(self):
        excerpt = [page(1, "- યશવંત મહેતા", "યશવંત મહેતાનો જન્મ લીલાપુરમાં થયો હતો."),
                   page(2, "4 a હિ \"", "ટેબલની સામે એક બારણું હતું.")]
        chapters = detect_chapters(excerpt)
        self.assertEqual([(c.start_page, c.end_page, c.title) for c in chapters],
                         [(1, 2, "યશવંત મહેતા")])

    def test_ocr_noise_is_not_a_numbered_heading(self):
        self.assertEqual(detect_chapters([page(1, "4 a હિ \""), page(2, "7 ; ૩ |")]), [])

    def test_contents_without_agreement_is_ignored(self):
        contents = ["અનુક્રમણિકા", "આ તો ઈશ તણો આવાસ 1", "ખોટો જવાબ 5"]
        self.assertEqual(detect_chapters(book(contents))[2].title, "ફાધર વાલેસ")


if __name__ == "__main__":
    unittest.main()
