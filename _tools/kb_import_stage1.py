# -*- coding: utf-8 -*-
"""阶段 A（不提权运行）：抽取 + 查重 + 定编号，结果写入 JSON。

之所以拆两阶段：本沙箱在 danger-full-access 提权环境下 Word COM 会挂死，
而非提权环境正常。因此把需要 Word 的抽取放在不提权阶段，
提权阶段只做纯文件 I/O。

用法：
    python _prep_import.py <分类> <输出json> <源文件...>
"""
import json
import os
import sys

sys.path.insert(0, r"D:\KnowledgeBase\_tools")
import kb_import as K
from kb_extract import render, run as extract_run, sniff

cat = sys.argv[1]
outjson = sys.argv[2]
files = sys.argv[3:]

hashes = K.load_hashes()
seq = K.next_seq(cat)
items = []

for src in files:
    name = os.path.basename(src)
    if not os.path.exists(src):
        print("MISS " + name)
        continue
    fp = K.sha256(src)
    if fp in hashes:
        print("DUP  %s (same as %s)" % (name, hashes[fp]))
        continue
    r = extract_run(src)
    if r["route"] != "normal":
        print("MANUAL %s | %s" % (name, " | ".join(r["reasons"])))
        continue
    nid = K.make_id(r["meta"], seq)
    seq += 1
    ext = K.EXT.get(sniff(src), os.path.splitext(src)[1].lower())
    items.append({
        "src": src,
        "name": name,
        "nid": nid,
        "fp": fp,
        "ext": ext,
        "size": os.path.getsize(src),
        "md": render(src, r),
        "meta": r["meta"],
    })
    print("PREP %s -> %s  grade=%s chars=%s" % (name, nid, r["grade"], r["stats"].get("总字符数", 0)))

with open(outjson, "w", encoding="utf-8") as f:
    json.dump({"cat": cat, "items": items}, f, ensure_ascii=False, indent=1)
print("PREPARED %d -> %s" % (len(items), outjson))
