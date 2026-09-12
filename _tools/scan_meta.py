# -*- coding: utf-8 -*-
"""
scan_meta.py —— 汇总素材元信息，产出「人可直接筛」的清单

用法：
    python scan_meta.py "<目录1;目录2;...>" <word扫描的jsonl> <输出tsv>

做三件事：
  1. 读 word_scan 产出的 JSONL（.doc/.docx 文本片段）-> 抽元信息
  2. 扫各目录下的 PDF（只读前 3 页）-> 抽元信息
  3. 合并成 TSV：真实标题 / 申请代码 / 项目类型 / 年份 / 申请人 / 依托单位
     并按国自然二级代码给出相关度提示（面向计算机学院老师）

输出 UTF-8 with BOM，Excel / WPS 可直接打开。
只读素材区，不修改、不移动任何文件。
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_pdf import extract_meta                                  # noqa: E402
import pymupdf                                                        # noqa: E402

HEAD_COLS = ["序号", "相关度提示", "申请代码", "项目类型", "年份", "真实标题",
             "申请人", "依托单位", "格式", "页", "KB", "来源目录", "文件名", "抽取状态"]

RANK = {"★★计算机F02": 0, "★★人工智能F04": 1, "★F01电子/信息": 2, "★F03自动化": 3,
        "★F05半导体": 4, "☆F06其他信息": 5, "○信息学部其他": 6,
        "○工程材料(或交叉)": 7, "○非信息学部": 8}


def pdf_head(path, pages=3):
    try:
        d = pymupdf.open(path)
    except Exception:
        return None, 0
    try:
        if d.needs_pass:
            return None, d.page_count
        parts = []
        for i, p in enumerate(d):
            if i >= pages:
                break
            parts.append(p.get_text())
        return "\n".join(parts), d.page_count
    finally:
        d.close()


def relevance(code, title):
    """
    相关度提示（面向计算机科学与技术学院的老师）。
    注意：国自然「信息科学部 F」含 F01 电子 / F02 计算机 / F03 自动化 /
    F04 人工智能 / F05 半导体 等，范围远大于"计算机"，所以按二级代码细分。
    """
    c = (code or "").upper()
    if c.startswith("F02"):
        return "★★计算机F02"
    if c.startswith("F04"):
        return "★★人工智能F04"
    if c.startswith("F01"):
        return "★F01电子/信息"
    if c.startswith("F03"):
        return "★F03自动化"
    if c.startswith("F05"):
        return "★F05半导体"
    if c.startswith("F06"):
        return "☆F06其他信息"
    if c.startswith("F"):
        return "○信息学部其他"
    if c.startswith("E"):
        return "○工程材料(或交叉)"
    if c.startswith(("A", "B", "C", "D", "G", "H")):
        return "○非信息学部"
    t = title or ""
    if re.search(r"计算机|软件|算法|网络|数据|智能|学习|图像|视觉|计算|系统|模型|信息", t):
        return "?标题像计算机(代码缺失)"
    return "?代码缺失"


def row(seq, src, name, fmt, size, pages, ok, err, meta):
    code = meta.get("申请代码", "未提及")
    title = meta.get("项目名称", "未提及")
    return [str(seq), relevance(code, title), code, meta.get("项目类型", "未提及"),
            meta.get("年份", "未提及"), title, meta.get("申请人", "未提及"),
            meta.get("依托单位", "未提及"), fmt, str(pages), str(round(size / 1024)),
            src, name, ("OK" if ok else ("FAIL " + err[:40]))]


def main(root_arg, jsonl_paths, out_tsv):
    roots = [r for r in root_arg.split(";") if r.strip()]
    rows = []

    def rel_of(p):
        ap = os.path.abspath(p).lower()
        for r in roots:
            ar = os.path.abspath(r).lower()
            if ap.startswith(ar):
                return os.path.relpath(os.path.dirname(p), r)
        return os.path.dirname(p)

    # ---- 1) Word 扫描结果 ----
    for jp in [x for x in jsonl_paths.split(";") if x.strip()]:
        if not os.path.exists(jp):
            continue
        with open(jp, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                p = r.get("path", "")
                meta = extract_meta(r.get("text", "")) if r.get("ok") else {}
                rows.append(row(0, rel_of(p), os.path.basename(p),
                                os.path.splitext(p)[1].lstrip(".").lower(),
                                r.get("size", 0), r.get("pages", 0),
                                r.get("ok"), r.get("err", ""), meta))

    # ---- 2) PDF ----
    seen_pdf = set()
    for r in roots:
        for p in glob.glob(os.path.join(r, "**", "*.pdf"), recursive=True):
            if re.search(r"\(\d+\)$", os.path.splitext(os.path.basename(p))[0]):
                continue
            key = os.path.abspath(p).lower()
            if key in seen_pdf:
                continue
            seen_pdf.add(key)
            txt, pages = pdf_head(p)
            meta = extract_meta(txt) if txt else {}
            rows.append(row(0, rel_of(p), os.path.basename(p), "pdf", os.path.getsize(p),
                            pages, txt is not None,
                            "加密或打不开" if txt is None else "", meta))

    def key(r):
        return (RANK.get(r[1], 9), r[2], -(int(r[4]) if r[4].isdigit() else 0))
    rows.sort(key=key)
    for i, r in enumerate(rows, 1):
        r[0] = str(i)

    with open(out_tsv, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("\t".join(HEAD_COLS) + "\n")
        for r in rows:
            f.write("\t".join(x.replace("\t", " ").replace("\n", " ") for x in r) + "\n")

    f02 = sum(1 for r in rows if r[2].upper().startswith(("F02", "F04")))
    f_any = sum(1 for r in rows if r[2].upper().startswith("F"))
    okn = sum(1 for r in rows if r[13] == "OK")
    print("ROWS=%d  OK=%d  F-any=%d  F02/F04=%d  -> %s"
          % (len(rows), okn, f_any, f02, out_tsv))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
