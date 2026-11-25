"""find_orf：找出每条序列正链上最长的完整开放阅读框（ORF）。"""
import random
import sys
import time

from scripts.fasta_utils import FastaRecord, parse_fasta

START = "ATG"
STOP = {"TAA", "TAG", "TGA"}


def longest_orf(seq: str) -> tuple[int, int, int] | None:
    seq = seq.upper()
    n = len(seq)
    best: tuple[int, int, int] | None = None
    for frame in range(3):
        i = frame
        while i + 3 <= n:
            if seq[i:i + 3] == START:
                j = i
                found = False
                while j + 3 <= n:
                    if seq[j:j + 3] in STOP:
                        length = (j + 3) - i
                        orf = (i + 1, j + 3, length)
                        if best is None or length > best[2]:
                            best = orf
                        i = j + 3
                        found = True
                        break
                    j += 3
                if not found:
                    break
            else:
                i += 3
    return best


def format_records(records: list[FastaRecord]) -> list[str]:
    lines: list[str] = []
    for r in records:
        orf = longest_orf(r.sequence)
        if orf is None:
            lines.append(f"{r.id}\t未找到完整ORF")
        else:
            start, end, length = orf
            lines.append(f"{r.id}\t{start}\t{end}\t{length}")
    return lines


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: find_orf.py <fasta文件>", file=sys.stderr)
        sys.exit(1)
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            records = parse_fasta(f.read())
    except (OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    time.sleep(random.uniform(3, 5))
    for line in format_records(records):
        print(line)


if __name__ == "__main__":
    main()
