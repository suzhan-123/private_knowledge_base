# -*- coding: utf-8 -*-
"""
kb_import.py —— 把文件正式导入知识库

用法：
    python kb_import.py --cat 10_基金本子 <文件1> [文件2 ...]
    python kb_import.py --cat 10_基金本子 --dry-run <文件...>      # 预演，不落盘

做四件事：
  1. 抽取（_tools/kb_extract.py），拿到正文 + 元信息
  2. 按内容指纹查重（_schema/hashes.tsv），重复的移入 00_收件箱/重复文件/
  3. 分配编号（扫该分类 INDEX.md 的当前最大序号 +1）—— 编号一经分配永不更改
  4. 落盘：原件 -> raw/、文字 -> md/，并更新 INDEX.md / hashes.tsv / manifest.tsv

只增不改：绝不覆盖已存在的编号文件；遇到冲突直接报错停下。
控制台输出全 ASCII；中文只在文件里。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

KB = r"D:\KnowledgeBase"
TOOLS = os.path.join(KB, "_tools")
sys.path.insert(0, TOOLS)
from kb_extract import run as extract_run, render, sniff          # noqa: E402
from kb_cats import CATS as CAT_CONF                                # noqa: E402

EXT = {"pdf": ".pdf", "doc": ".doc", "docx": ".docx"}
TMAP = {"青年": "青年", "面上": "面上", "地区": "地区", "重点": "重点", "重大": "重大"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hashes():
    p = os.path.join(KB, "_schema", "hashes.tsv")
    d = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f.read().splitlines()[1:]:
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0]:
                    d[parts[0]] = parts[1]
    return d


def next_seq(cat):
    p = os.path.join(KB, cat, "INDEX.md")
    mx = 0
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for m in re.finditer(r"\|\s*([0-9A-Z]{4}-[^|]+?)\s*\|", f.read()):
                mm = re.search(r"-(\d{4})$", m.group(1).strip())
                if mm:
                    mx = max(mx, int(mm.group(1)))
    return mx + 1


def make_id(meta, seq, cat="10_基金本子"):
    conf = CAT_CONF.get(cat) or {}
    if conf.get("id"):
        return conf["id"](meta, seq)
    y = meta.get("年份", "未提及")
    year = y if re.match(r"^(19|20)\d{2}$", y) else "XXXX"
    t = TMAP.get(meta.get("项目类型", ""), "XX")
    code = meta.get("申请代码", "未提及").replace(" ", "")
    code = code if re.match(r"^[A-H]\d{4,8}$", code) else "XX"
    return "%s-%s-%s-%04d" % (year, t, code, seq)


def append_index(cat, row):
    p = os.path.join(KB, cat, "INDEX.md")
    with open(p, encoding="utf-8") as f:
        c = f.read()
    if not c.endswith("\n"):
        c += "\n"
    c += row + "\n"
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(c)


def append_tsv(rel, row):
    p = os.path.join(KB, "_schema", rel)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(row + "\n")


def park_or_copy(src, subdir):
    """决定源文件的去向。

    收件箱（00_收件箱\待归档）来的 -> **移动**（归档完不留滞）；
    库外来源（素材区等）-> **复制**（保持原有行为，不动素材区）。
    返回落位后的完整路径。
    """
    dst_dir = os.path.join(KB, "00_收件箱", subdir)
    os.makedirs(dst_dir, exist_ok=True)
    name = os.path.basename(src)
    dst = os.path.join(dst_dir, name)
    if os.path.exists(dst):
        base, ext = os.path.splitext(name)
        i = 2
        while os.path.exists(dst):
            dst = os.path.join(dst_dir, "%s_%d%s" % (base, i, ext))
            i += 1
    wait = os.path.abspath(os.path.join(KB, "00_收件箱", "待归档")) + os.sep
    if os.path.abspath(src).startswith(wait):
        shutil.move(src, dst)
    else:
        shutil.copy2(src, dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()

    cat = a.cat
    if not os.path.isdir(os.path.join(KB, cat)):
        print("ERR unknown category: %s" % cat)
        return 2

    today = datetime.date.today().isoformat()
    hashes = load_hashes()
    seen = {}          # 批内指纹：同一批里重复的文件只入第一个
    seq = next_seq(cat)
    done, dup, manual, fail = [], [], [], []

    for src in a.files:
        name = os.path.basename(src)
        if not os.path.exists(src):
            print("MISS %s" % name)
            fail.append((name, "file not found"))
            continue

        fp = sha256(src)
        if fp in hashes:
            dup.append((name, hashes[fp]))
            if not a.dry_run:
                park_or_copy(src, "重复文件")
            print("DUP  %s  (same as %s)" % (name, hashes[fp]))
            continue
        if fp in seen:
            dup.append((name, seen[fp]))
            if not a.dry_run:
                park_or_copy(src, "重复文件")
            print("DUP  %s  (batch duplicate of %s)" % (name, seen[fp]))
            continue
        seen[fp] = name

        r = extract_run(src)
        # 非本子分类：元信息由 kb_cats 按文件名+正文另行提取
        conf = CAT_CONF.get(cat) or {}
        if conf.get("meta") and r.get("text"):
            r["meta"] = conf["meta"](name, r.get("text") or "")
        if r["route"] != "normal":
            manual.append((name, "; ".join(r["reasons"])))
            if not a.dry_run:
                park_or_copy(src, "需人工确认")
            print("MANUAL %s  %s" % (name, " | ".join(r["reasons"])))
            continue

        nid = make_id(r["meta"], seq, cat)
        seq += 1
        ext = EXT.get(sniff(src), os.path.splitext(src)[1].lower())
        rel_raw = "%s/raw/%s%s" % (cat, nid, ext)
        rel_md = "%s/md/%s.md" % (cat, nid)
        rel_card = "%s/cards/%s.md" % (cat, nid)

        print("OK   %s -> %s  grade=%s chars=%s type=%s code=%s year=%s"
              % (name, nid, r["grade"], r["stats"].get("总字符数", 0),
                 r["meta"].get("项目类型"), r["meta"].get("申请代码"), r["meta"].get("年份")))

        if a.dry_run:
            done.append((nid, r))
            continue

        for rel in (rel_raw, rel_md):
            if os.path.exists(os.path.join(KB, rel)):
                print("ERR  target exists, abort: %s" % rel)
                return 3
        # 先取大小再落盘：源文件若来自收件箱，下面会被移走
        size = os.path.getsize(src)
        shutil.copy2(src, os.path.join(KB, rel_raw))
        with open(os.path.join(KB, rel_md), "w", encoding="utf-8", newline="\n") as f:
            f.write(render(src, r))

        parked = park_or_copy(src, "已归档")
        if parked.startswith(os.path.join(KB, "00_收件箱")):
            print("PARK %s -> 00_收件箱/%s/" % (name, os.path.basename(os.path.dirname(parked))))
        m = r["meta"]
        title = (m.get("项目名称") or os.path.splitext(name)[0]).replace("|", "/")
        append_index(cat, "| %s | %s | %s | %s | %s |  |  | 存档型 |"
                     % (nid, title, m.get("申请代码", "未提及"),
                        m.get("年份", "未提及"), m.get("项目类型", "未提及")))
        append_tsv("hashes.tsv", "%s\t%s\t%s\t%s" % (fp, nid, os.path.basename(rel_raw), today))
        append_tsv("manifest.tsv", "%s\t%d\t%s\t%s" % (rel_raw, size, fp, today))
        hashes[fp] = nid
        done.append((nid, r))

    print("\nSUMMARY ok=%d dup=%d manual=%d fail=%d%s"
          % (len(done), len(dup), len(manual), len(fail), "  (DRY RUN)" if a.dry_run else ""))
    if done:
        print("IDS " + " ".join(x[0] for x in done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
