# -*- coding: utf-8 -*-
"""
kb_extract.py —— 知识库统一抽取入口

    python kb_extract.py <源文件> <输出txt路径>     # 抽取并写成 UTF-8 文本
    python kb_extract.py --json <源文件>            # 输出 JSON 摘要（ASCII 转义，控制台安全）

支持：PDF（pymupdf）、.doc/.docx（Word COM，见 extract_word.ps1）
不装 python-docx / pywin32：Word 部分交给 PowerShell + 本地 Word。
元信息从原文抽取，不靠文件名猜。

编码约定（重要）：
  * 写出的文本文件一律 UTF-8。
  * 控制台只打印 ASCII，中文一律走文件或 JSON 的 \\uXXXX 转义，
    避免 Windows 控制台代码页导致 agent 读到乱码。
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from extract_pdf import extract_pdf, extract_meta, check_quality      # noqa: E402
from extract_office import (extract_pptx, extract_xlsx, extract_text_file,
                            sniff_zip, sniff_ole)                       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, "extract_word.ps1")
GRADE_ASCII = {"高": "high", "中": "mid", "低": "low"}


def sniff(path):
    """按文件头判断真实类型（不看扩展名 —— 素材区文件名可能很乱）"""
    try:
        with open(path, "rb") as f:
            h = f.read(8)
    except OSError:
        return "unknown"
    if h.startswith(b"%PDF"):
        return "pdf"
    if h.startswith(b"PK\x03\x04"):
        # OOXML 家族：docx / pptx / xlsx 文件头都是 PK，靠内部结构区分
        return sniff_zip(path)
    if h.startswith(b"\xd0\xcf\x11\xe0"):
        # OLE2 复合文档：老 .doc / .xls / .ppt 共用此文件头
        return sniff_ole(path)
    if h.startswith(b"{\\rtf"):
        return "rtf"
    if h.startswith(b"\xff\xd8\xff") or h.startswith(b"\x89PNG"):
        return "image"
    # 纯文本类没有特征文件头，靠扩展名
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".csv", ".md", ".log"):
        return "txt"
    if ext in (".html", ".htm"):
        return "html"
    if ext in (".ppt", ".xls", ".doc"):
        return ext.lstrip(".")
    return "unknown"


def via_word(path):
    """调用 PowerShell + Word COM 抽 .doc/.docx。返回 (text, pages, info)"""
    tmp = os.path.join(tempfile.gettempdir(), "kb_extract_%d.txt" % os.getpid())
    if os.path.exists(tmp):
        os.remove(tmp)
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
           "-File", PS1, "-In", path, "-Out", tmp]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        info = ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return None, 0, "Word 抽取超时（>10 分钟）"
    pages = 0
    m = re.search(r"pages=(\d+)", info)
    if m:
        pages = int(m.group(1))
    if os.path.exists(tmp):
        with open(tmp, encoding="utf-8") as f:
            t = f.read()
        os.remove(tmp)
        return t, pages, info
    return None, pages, info or "Word 未产出文本"


def run(src):
    kind = sniff(src)
    note = ""
    if kind == "pdf":
        text, pc, note = extract_pdf(src)
    elif kind in ("doc", "docx"):
        text, pc, info = via_word(src)
        note = "" if text else ("Word 抽取失败：%s" % info)
    elif kind == "pptx":
        text, pc, note = extract_pptx(src)
        if text is None:
            note = note or "pptx 解析失败"
    elif kind == "xlsx":
        text, pc, note = extract_xlsx(src)
        if text is None:
            note = note or "xlsx 解析失败"
    elif kind in ("txt", "html"):
        text, pc, note = extract_text_file(src)
    elif kind == "rtf":
        text, pc, note = None, 0, "RTF 暂不支持，请用 Word 另存为 .docx"
    elif kind == "ppt":
        text, pc, note = None, 0, "老的 .ppt 需要 PowerPoint，请先另存为 .pptx"
    elif kind == "xls":
        text, pc, note = None, 0, "老的 .xls 需要 Excel，请先另存为 .xlsx"
    elif kind == "image":
        text, pc, note = None, 0, "这是图片不是文档，需要 OCR"
    else:
        text, pc, note = None, 0, "不认识的文件类型（文件头不是 PDF/Word/PPT/Excel/图片）"

    q = check_quality(text, pc, note)
    meta = extract_meta(text) if text else {}
    return {"kind": kind, "text": text, "pages": pc, "grade": q["grade"],
            "route": q["route"], "reasons": q["reasons"], "stats": q["stats"],
            "meta": meta}


def render(src, r):
    """渲染成写入 md/ 的文本（编号与分类留给归档环节补）"""
    meta = r["meta"]
    L = ["# %s" % (meta.get("项目名称") or os.path.splitext(os.path.basename(src))[0]), ""]
    L.append("> 来源文件：%s" % os.path.basename(src))
    L.append("> 抽取质量：%s ｜ 页数：%s ｜ 类型：%s" % (r["grade"], r["pages"], r["kind"]))
    if meta:
        L.append("> 元信息：" + " ｜ ".join("%s=%s" % (k, v) for k, v in meta.items()))
    if r["reasons"]:
        L.append("> 提示：" + "; ".join(r["reasons"]))
    L += ["", "---", "", r["text"] or ""]
    return "\n".join(L)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    src = args[0]
    r = run(src)

    if as_json:
        # ensure_ascii=True：中文转成 \uXXXX，任何控制台代码页都不会乱码
        print(json.dumps({"file": os.path.basename(src), "kind": r["kind"],
                          "grade": r["grade"], "grade_ascii": GRADE_ASCII.get(r["grade"], "?"),
                          "route": r["route"], "pages": r["pages"],
                          "chars": r["stats"].get("总字符数", 0),
                          "cn_chars": r["stats"].get("中文字符数", 0),
                          "reasons": r["reasons"], "meta": r["meta"]},
                         ensure_ascii=True))
        sys.exit(0 if r["route"] == "normal" else 1)

    dst = args[1] if len(args) > 1 else None
    if dst:
        with open(dst, "w", encoding="utf-8") as f:
            f.write(render(src, r))
        print("OK kind=%s route=%s grade=%s pages=%s chars=%s -> %s"
              % (r["kind"], r["route"], GRADE_ASCII.get(r["grade"], "?"), r["pages"],
                 r["stats"].get("总字符数", 0), os.path.basename(dst)))
        if r["reasons"]:
            print("   notes=%d (see output file header)" % len(r["reasons"]))
    else:
        print(render(src, r))
