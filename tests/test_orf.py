from scripts.find_orf import longest_orf


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
