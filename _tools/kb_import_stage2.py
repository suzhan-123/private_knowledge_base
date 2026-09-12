# -*- coding: utf-8 -*-
"""阶段 B（提权运行）：纯文件 I/O 落盘。

读阶段 A 的 JSON，完成：原件复制到 raw/、文本写入 md/、
追加 INDEX.md / hashes.tsv / manifest.tsv。不调用 Word、不抽取。

用法：
    python _commit_import.py <阶段A的json>
"""
import datetime
import json
import os
import shutil
import sys

sys.path.insert(0, r"D:\KnowledgeBase\_tools")
import kb_import as K

d = json.load(open(sys.argv[1], encoding="utf-8"))
cat = d["cat"]
today = datetime.date.today().isoformat()

for it in d["items"]:
    rel_raw = "%s/raw/%s%s" % (cat, it["nid"], it["ext"])
    rel_md = "%s/md/%s.md" % (cat, it["nid"])
    for rel in (rel_raw, rel_md):
        if os.path.exists(os.path.join(K.KB, rel)):
            print("ERR target exists, abort: %s" % rel)
            sys.exit(3)

    shutil.copy2(it["src"], os.path.join(K.KB, rel_raw))
    with open(os.path.join(K.KB, rel_md), "w", encoding="utf-8", newline="\n") as f:
        f.write(it["md"])

    m = it["meta"]
    title = (m.get("项目名称") or os.path.splitext(it["name"])[0]).replace("|", "/")
    K.append_index(cat, "| %s | %s | %s | %s | %s |  |  | 存档型 |"
                   % (it["nid"], title, m.get("申请代码", "未提及"),
                      m.get("年份", "未提及"), m.get("项目类型", "未提及")))
    K.append_tsv("hashes.tsv", "%s\t%s\t%s\t%s" % (it["fp"], it["nid"], os.path.basename(rel_raw), today))
    K.append_tsv("manifest.tsv", "%s\t%d\t%s\t%s" % (rel_raw, it["size"], it["fp"], today))
    print("COMMIT %s  (%s)" % (it["nid"], it["name"]))

print("DONE %d" % len(d["items"]))
