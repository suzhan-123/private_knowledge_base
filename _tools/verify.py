# -*- coding: utf-8 -*-
"""verify.py —— 汇总各抽取结果的统计与元信息，写成 UTF-8 报告"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_pdf import extract_meta                                  # noqa: E402

outdir = sys.argv[1]
report = sys.argv[2]

L = ["抽取结果汇总", "=" * 78, ""]
for path in sorted(glob.glob(os.path.join(outdir, "*.txt"))):
    name = os.path.basename(path)
    if name.startswith("_"):
        continue
    with open(path, encoding="utf-8") as f:
        t = f.read()
    body = t.split("---", 1)[-1] if "---" in t[:1200] else t
    cn = sum(1 for c in body if "\u4e00" <= c <= "\u9fff")
    bad = sum(1 for c in body if c == "\ufffd")
    lines = [x for x in body.split("\n") if x.strip()]
    meta = extract_meta(body)
    tbl = sum(1 for x in body.split("\n") if "\t" in x)          # 疑似表格行/字段行

    L.append("### %s" % name)
    L.append("  正文 %d 字（中文 %d，乱码 %d）｜非空行 %d｜含制表符的行 %d"
             % (len(body), cn, bad, len(lines), tbl))
    L.append("  元信息: " + json.dumps(meta, ensure_ascii=False))
    L.append("  前 8 行:")
    for x in lines[:8]:
        L.append("    " + x[:110])
    L.append("")

with open(report, "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("report written:", report, "files:", len(glob.glob(os.path.join(outdir, '*.txt'))))
