"""seq_stats：读取 FASTA，输出每条序列的 ID、长度、GC 含量。"""
import random
import sys
import time

from scripts.fasta_utils import FastaRecord, parse_fasta


def stats(records: list[FastaRecord]) -> list[tuple[str, int, float]]:
    result: list[tuple[str, int, float]] = []
    for r in records:
        seq = r.sequence
        length = len(seq)
        if length == 0:
            gc = 0.0
        else:
            gc = round((seq.count("G") + seq.count("C")) / length * 100, 2)
        result.append((r.id, length, gc))
    return result


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: seq_stats.py <fasta文件>", file=sys.stderr)
        sys.exit(1)
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            records = parse_fasta(f.read())
    except (OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    time.sleep(random.uniform(3, 5))
    for rid, length, gc in stats(records):
        print(f"{rid}\t{length}\t{gc:.2f}%")


if __name__ == "__main__":
    main()
