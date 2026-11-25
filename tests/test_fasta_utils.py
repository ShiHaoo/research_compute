import pytest

from scripts.fasta_utils import FastaRecord, parse_fasta


def test_parse_two_records():
    recs = parse_fasta(">a desc\nATGC\n>b\nNNNN")
    assert [r.id for r in recs] == ["a", "b"]
    assert recs[0].sequence == "ATGC"
    assert recs[1].sequence == "NNNN"


def test_parse_lowercase_and_blank_lines():
    recs = parse_fasta(">a\natgcn\n\n")
    assert recs[0].id == "a"
    assert recs[0].sequence == "ATGCN"


def test_parse_fasta_reports_all_problems():
    text = (
        "seq_bad missing header marker\n"
        "ATGCCCXXXGGGTTT123AAATAG\n"
        ">seq_ok test sequence\n"
        "ATGAAATTTGGGTAA\n"
    )
    with pytest.raises(ValueError) as e:
        parse_fasta(text)
    msg = str(e.value)
    assert "缺少以 '>' 开头的标题行" in msg
    assert "非法字符" in msg
    assert "X" in msg
    assert "1" in msg


def test_parse_rejects_illegal_char_in_valid_record():
    with pytest.raises(ValueError) as e:
        parse_fasta(">ok\nATGCX\n")
    assert "非法字符" in str(e.value)
    assert "X" in str(e.value)


def test_empty_id_from_bare_header():
    recs = parse_fasta(">\nATGC\n")
    assert recs[0].id == ""
    assert recs[0].sequence == "ATGC"
