# -*- coding: utf-8 -*-
"""
kb_rebuild_index.py —— 从卡片重建 INDEX.md 与 TAGS.md

设计原则：**卡片是唯一真源，索引只是派生视图。**
所以卡片改完后跑一次本脚本，索引自动同步，不会出现"索引与卡片不符"。

用法：python kb_rebuild_index.py [分类...]      默认 10_基金本子
"""
import glob
import os
import re
import sys

KB = r"D:\KnowledgeBase"
CATS = ("10_基金本子", "20_教学", "30_办公", "40_文献", "45_论文")


def parse_card(path):
    """解析卡片的 YAML front matter（不依赖 pyyaml）"""
    with open(path, encoding="utf-8") as f:
        t = f.read()
    m = re.match(r"---\s*\n(.*?)\n---", t, re.S)
    if not m:
        return None
    d = {}
    for line in m.group(1).split("\n"):
        if not line or line[0] in (" ", "\t", "-"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    d["标签"] = [x.strip() for x in d.get("标签", "[]").strip("[]").split(",") if x.strip()]
    return d


def head_of(path, marker):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            c = f.read()
        if marker in c:
            return c.split(marker)[0]
    return ""


COLS = {
    "10_基金本子": [("标题", "标题"), ("学科代码", "学科代码"), ("年份", "年份"),
                    ("项目类型", "项目类型"), ("标签", "标签"),
                    ("可借鉴度", "可借鉴度"), ("存储模式", "存储模式")],
    "20_教学": [("标题", "标题"), ("课程名", "课程名"), ("学年", "学年"),
                ("类型", "类型"), ("标签", "标签"), ("存储模式", "存储模式")],
    "30_办公": [("标题", "标题"), ("年份", "年份"), ("类别", "类别"),
                ("是否现行有效", "现行有效"), ("标签", "标签"), ("存储模式", "存储模式")],
    "40_文献": [("标题", "标题"), ("类型", "类型"), ("年份", "年份"),
                ("是否现行有效", "现行有效"), ("标签", "标签"), ("存储模式", "存储模式")],
    "45_论文": [("一句话总结", "一句话总结"), ("标题", "标题"), ("作者", "作者"), ("出处", "出处"),
                ("年份", "年份"), ("可放入本子的位置", "可放入本子的位置"),
                ("标签", "标签"), ("存储模式", "存储模式")],
}


def _clip(s, n=60):
    """索引单元格截断：卡片是唯一真源，索引只需可扫读"""
    s = str(s).replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def rebuild(cat):
    cols = COLS.get(cat) or COLS["10_基金本子"]
    cards = sorted(glob.glob(os.path.join(KB, cat, "cards", "*.md")))
    rows, tagmap = [], {}
    for p in cards:
        d = parse_card(p)
        if not d:
            print("  SKIP (no front matter): %s" % os.path.basename(p))
            continue
        i = d.get("id") or os.path.splitext(os.path.basename(p))[0]
        cells = []
        for key, _label in cols:
            if key == "标签":
                cells.append("、".join(d.get("标签", [])))
            else:
                cells.append(_clip(d.get(key, "") or "未提及"))
        rows.append("| %s | %s |" % (i, " | ".join(cells)))
        for t in d.get("标签", []):
            tagmap.setdefault(t, []).append(i)

    idx = os.path.join(KB, cat, "INDEX.md")
    header = "| 编号 | " + " | ".join(lbl for _k, lbl in cols) + " |"
    sep = "|" + "---|" * (len(cols) + 1)
    with open(idx, "w", encoding="utf-8", newline="\n") as f:
        f.write(head_of(idx, "| 编号 |"))
        f.write(header + "\n")
        f.write(sep + "\n")
        if rows:
            f.write("\n".join(rows) + "\n")
        f.write("\n**条目数：%d**\n" % len(rows))

    tg = os.path.join(KB, cat, "TAGS.md")
    with open(tg, "w", encoding="utf-8", newline="\n") as f:
        f.write(head_of(tg, "| 标签 |"))
        f.write("| 标签 | 篇数 | 编号列表 |\n|---|---|---|\n")
        for t in sorted(tagmap, key=lambda x: (-len(tagmap[x]), x)):
            f.write("| %s | %d | %s |\n" % (t, len(tagmap[t]), " ".join(tagmap[t])))
    return len(rows), len(tagmap)


if __name__ == "__main__":
    cats = [a for a in sys.argv[1:] if not a.startswith("-")] or ["10_基金本子"]
    for c in cats:
        if not os.path.isdir(os.path.join(KB, c)):
            print("SKIP unknown category: %s" % c)
            continue
        n, tn = rebuild(c)
        print("REBUILT %s entries=%d tags=%d" % (c, n, tn))
