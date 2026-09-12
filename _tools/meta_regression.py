# -*- coding: utf-8 -*-
"""元信息回归探针：对目录内所有 PDF 抽取元信息，输出 TSV 便于改前改后对比"""
import glob
import os
import sys

sys.path.insert(0, r"D:\KnowledgeBase\_tools")
import extract_pdf

d = sys.argv[1]
out = sys.argv[2]
cols = ["年份", "项目类型", "类型存疑", "申请代码", "资助类别", "申请人", "依托单位", "项目名称"]
rows = []
for f in sorted(glob.glob(os.path.join(d, "*.pdf"))):
    text, pc, note = extract_pdf.extract_pdf(f)
    m = extract_pdf.extract_meta(text) if text else {}
    rows.append([os.path.basename(f)] + [str(m.get(c, "未提及")).replace("\t", " ") for c in cols])

with open(out, "w", encoding="utf-8") as fh:
    fh.write("文件名\t" + "\t".join(cols) + "\n")
    for r in rows:
        fh.write("\t".join(r) + "\n")
print("rows=%d -> %s" % (len(rows), out))
