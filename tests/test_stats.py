from scripts.fasta_utils import FastaRecord
from scripts.seq_stats import stats


def test_stats_gc():
    assert stats([FastaRecord("a", "ATGC")]) == [("a", 4, 50.0)]
    assert stats([FastaRecord("b", "AAAA")]) == [("b", 4, 0.0)]


def test_stats_multiple_and_empty():
    recs = [FastaRecord("a", "GGCC"), FastaRecord("empty", "")]
    assert stats(recs) == [("a", 4, 100.0), ("empty", 0, 0.0)]
