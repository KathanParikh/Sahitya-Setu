"""Legacy-font pages must be OCR'd, never indexed as glyph codes."""
import unittest

from processing.pdf_extractor import is_legacy_encoded

# Real text layer from a GujaratiBook.pdf page set in a legacy font.
LEGACY = ("±ë ÕëÌuÕðVÖÀ ç_ØÛõý ±ëÕÞë_ çñÇÞù ±ëäÀëÝý Èõ. ÃðÉßëÖí (Õþ×Ü Ûëæë) "
          "ÔùßHë 8Þð_ ±ë ÕëÌuÕðVÖÀ ±ëÕ çúÞë èë×Üë_ ÜñÀÖë_ ±ëÞ_ØÞí áëÃHëí")
GUJARATI = ("તમને ક્યારે ક્યારે ઊંઘ નથી આવતી ? કેમ ? તમે કરેલા કોઈ બહાદુરીભર્યા "
            "કામ વિશે કહો. તમે કોઈ કિલ્લો જોયો છે? ક્યાં? કિલ્લો શા માટે બાંધવામાં આવતો હતો ?")
ENGLISH = ("Café owners in Zürich reported that the naïve résumé format was "
           "rejected; the committee preferred a plain one-page summary instead.")


class LegacyDetection(unittest.TestCase):
    def test_legacy_font_text_is_detected(self):
        self.assertTrue(is_legacy_encoded(LEGACY))

    def test_unicode_gujarati_is_not(self):
        self.assertFalse(is_legacy_encoded(GUJARATI))

    def test_accented_english_is_not(self):
        self.assertFalse(is_legacy_encoded(ENGLISH))

    def test_short_text_is_left_to_the_thin_page_check(self):
        self.assertFalse(is_legacy_encoded("ÕëÌuÕðVÖÀ"))


if __name__ == "__main__":
    unittest.main()
