"""Hybrid search skips BM25 for queries with no Gujarati script."""
import unittest
from unittest import mock

from indexing import hybrid_search
from indexing.bm25_index import BM25Result


def _vector_row(chunk_id, rank):
    return {"chunk_id": chunk_id, "text": f"text {chunk_id}", "rank": rank, "score": 0.8,
            "metadata": {"page_start": 16, "page_end": 16, "chapter_index": 0,
                         "chapter_title": ""}}


class ScriptCheck(unittest.TestCase):
    def setUp(self):
        # BM25 would put a noise chunk first; vector search has the right one.
        self.index = mock.Mock()
        self.index.search.return_value = [BM25Result("noise", 5.0, 1)]
        patches = [
            mock.patch.object(hybrid_search.bm25_index, "get_index", return_value=self.index),
            mock.patch.object(hybrid_search.vector_store, "search",
                              return_value=[_vector_row("right", 1)]),
            mock.patch.object(hybrid_search.vector_store, "get_by_ids",
                              return_value={"noise": _vector_row("noise", 0)}),
            mock.patch.object(hybrid_search, "embed_query", return_value=[0.0]),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_english_query_skips_bm25(self):
        results = hybrid_search.hybrid_search("doc", "Where was Karsandas Manek born?", top_k=5)
        self.index.search.assert_not_called()
        self.assertEqual([r.chunk_id for r in results], ["right"])
        self.assertEqual(results[0].sources, ["vector"])

    def test_gujarati_query_uses_bm25(self):
        results = hybrid_search.hybrid_search("doc", "કરસનદાસ માણેકનો જન્મ ક્યાં થયો હતો?", top_k=5)
        self.index.search.assert_called_once()
        self.assertEqual({r.chunk_id for r in results}, {"right", "noise"})

    def test_gujarati_query_with_english_name_uses_bm25(self):
        hybrid_search.hybrid_search("doc", "Father Valles નું મૂળ નામ શું હતું?", top_k=5)
        self.index.search.assert_called_once()


class ExtraVectorQuery(unittest.TestCase):
    def test_english_wording_adds_a_third_list(self):
        def search(doc_id, vector, top_k=None):
            # embed_query is patched to return the query text itself
            return [_vector_row("from_english", 1)] if vector == "english" \
                else [_vector_row("from_gujarati", 1)]

        with mock.patch.object(hybrid_search.bm25_index, "get_index", return_value=None), \
             mock.patch.object(hybrid_search.vector_store, "search", side_effect=search), \
             mock.patch.object(hybrid_search, "embed_query", side_effect=lambda q: q):
            results = hybrid_search.hybrid_search("doc", "ગુજરાતી", top_k=5,
                                                  extra_vector_query="english")
        self.assertEqual({r.chunk_id for r in results}, {"from_gujarati", "from_english"})




def _row(index, text, page, chapter=0):
    return {"chunk_id": f"doc:{index}", "text": text,
            "metadata": {"chunk_index": index, "page_start": page, "page_end": page,
                         "chapter_index": chapter, "chapter_title": "ચીલઝડપ"}}


def _hit(index, text, page, chapter=0):
    return hybrid_search.RetrievedChunk(f"doc:{index}", text, page, page, chapter, "ચીલઝડપ", 1.0)


class Widening(unittest.TestCase):
    def test_overlap_between_chunks_is_not_repeated(self):
        a = "કુમારે તેને પકડી લીધો. આ છે તમારા પાકીટનો ચોર."
        b = "આ છે તમારા પાકીટનો ચોર. પાકીટ ખુરશી નીચે ચોંટાડેલું હતું."
        self.assertEqual(hybrid_search._join_overlapping(a, b),
                         "કુમારે તેને પકડી લીધો. આ છે તમારા પાકીટનો ચોર. પાકીટ ખુરશી નીચે ચોંટાડેલું હતું.")

    def test_chunks_without_overlap_are_joined_with_a_space(self):
        self.assertEqual(hybrid_search._join_overlapping("એક વાક્ય.", "બીજું વાક્ય."),
                         "એક વાક્ય. બીજું વાક્ય.")

    def widen(self, hits, rows, top_n=3):
        with mock.patch.object(hybrid_search.vector_store, "get_by_indexes",
                               return_value={r["metadata"]["chunk_index"]: r for r in rows}):
            return hybrid_search.widen_passages("doc", hits, top_n=top_n)

    def test_passage_gets_its_neighbours_and_their_pages(self):
        rows = [_row(151, "આરોપ પહેલાં.", 93), _row(152, "આ છે ચોર.", 93),
                _row(153, "પાકીટ ખુરશી નીચે.", 94)]
        out = self.widen([_hit(152, "આ છે ચોર.", 93)], rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].text, "આરોપ પહેલાં. આ છે ચોર. પાકીટ ખુરશી નીચે.")
        self.assertEqual((out[0].page_start, out[0].page_end), (93, 94))
        self.assertEqual(out[0].chunk_id, "doc:151-153")

    def test_neighbour_from_another_chapter_is_left_out(self):
        rows = [_row(9, "પાછલા પાઠનો અંત.", 40, chapter=1), _row(10, "નવો પાઠ.", 41, chapter=2),
                _row(11, "આગળ.", 41, chapter=2)]
        out = self.widen([_hit(10, "નવો પાઠ.", 41, chapter=2)], rows)
        self.assertEqual(out[0].text, "નવો પાઠ. આગળ.")

    def test_adjacent_hits_merge_into_one_passage_in_rank_order(self):
        rows = [_row(i, f"ભાગ {i}.", 90) for i in (4, 5, 6, 7, 20, 21, 22)]
        hits = [_hit(21, "ભાગ 21.", 90), _hit(5, "ભાગ 5.", 90), _hit(6, "ભાગ 6.", 90)]
        out = self.widen(hits, rows)
        self.assertEqual([c.chunk_id for c in out], ["doc:20-22", "doc:4-7"])

    def test_only_the_top_n_are_widened(self):
        rows = [_row(i, f"ભાગ {i}.", 90) for i in range(0, 12)]
        hits = [_hit(i, f"ભાગ {i}.", 90) for i in (1, 5, 10)]
        out = self.widen(hits, rows, top_n=2)
        self.assertEqual([c.chunk_id for c in out], ["doc:0-2", "doc:4-6"])


if __name__ == "__main__":
    unittest.main()
