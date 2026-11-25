"""严格的 FASTA 解析与校验。

规则：
- 每行去首尾空白，空行跳过。
- 以 ``>`` 开头的行是新标题行，id 取 ``>`` 后按空白切分的第 1 段。
- 其余行视为序列行；序列只允许 A/C/G/T/N（大小写不敏感），否则报「包含非法字符」。
- 若文件第一条内容行不以 ``>`` 开头，报「缺少以 '>' 开头的标题行」，并把它当作
  一条缺标题的记录继续解析，以便同时报告后续序列行的非法字符。
- 所有问题汇总进一次 ``ValueError``。
"""
from dataclasses import dataclass

VALID_BASES = set("ACGTN")


@dataclass
class FastaRecord:
    id: str
    sequence: str


def parse_fasta(text: str) -> list[FastaRecord]:
    records: list[FastaRecord] = []
    errors: list[str] = []
    current_id: str | None = None
    current_seq: list[str] = []
    in_record = False

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue

        if line.startswith(">"):
            if in_record:
                records.append(FastaRecord(current_id, "".join(current_seq)))
            header = line[1:].strip()
            current_id = header.split()[0] if header else ""
            current_seq = []
            in_record = True
        else:
            if not in_record:
                errors.append(f"第 {lineno} 行缺少以 '>' 开头的标题行")
                current_id = line.split()[0]
                current_seq = []
                in_record = True
            else:
                bad = sorted({c for c in line.upper() if c not in VALID_BASES})
                if bad:
                    errors.append(f"第 {lineno} 行包含非法字符 {', '.join(bad)}")
                current_seq.append(line.upper())

    if in_record:
        records.append(FastaRecord(current_id, "".join(current_seq)))

    if errors:
        raise ValueError("FASTA 解析失败：" + "；".join(errors))

    return records
