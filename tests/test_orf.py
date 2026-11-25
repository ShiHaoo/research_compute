from scripts.fasta_utils import FastaRecord
from scripts.find_orf import format_records, longest_orf


def test_longest_orf_basic():
    assert longest_orf("ATGAAATAA") == (1, 9, 9)


def test_longest_orf_shifted_frame():
    assert longest_orf("AAATGCCCTAA") == (3, 11, 9)


def test_longest_orf_picks_longest():
    assert longest_orf("ATGTAAATGCCCTAA") == (7, 15, 9)


def test_longest_orf_no_orf():
    assert longest_orf("CCCC") is None
    assert longest_orf("ATG") is None


def test_longest_orf_lowercase():
    assert longest_orf("atgaaataa") == (1, 9, 9)


def test_format_records_no_orf():
    lines = format_records([FastaRecord("a", "CCCC"), FastaRecord("b", "ATGAAATAA")])
    assert lines == ["a\t未找到完整ORF", "b\t1\t9\t9"]
