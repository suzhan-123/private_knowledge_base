# -*- coding: utf-8 -*-
"""extract_office.py —— 零依赖解析 .pptx / .xlsx，以及纯文本类文件

为什么不用 python-pptx / openpyxl：
  这两个格式本质是 zip + XML，标准库 zipfile + ElementTree 就能读，
  不引入任何第三方依赖，换电脑不用重新装包。

支持的格式：
  .pptx  按幻灯片顺序抽取 <a:t> 文本
  .xlsx  读 sharedStrings + 各工作表单元格（按行拼）
  .txt / .md / .csv   编码嗅探直接读
  .html / .htm        剥掉标签与脚本样式
老的 .ppt / .xls（OLE2 复合文档）本模块不处理 —— 它们需要 PowerPoint/Excel COM，
调用方应转人工或提示先另存为新格式。
"""
import os
import re
import zipfile
from xml.etree import ElementTree as ET

A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
S_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sniff_zip(path):
    """OOXML 家族（docx/pptx/xlsx）文件头都是 PK，靠 zip 内部结构区分"""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except Exception:
        return "unknown"
    if any(n.startswith("word/") for n in names):
        return "docx"
    if any(n.startswith("ppt/") for n in names):
        return "pptx"
    if any(n.startswith("xl/") for n in names):
        return "xlsx"
    return "zip"


def sniff_ole(path):
    """OLE2 复合文档：老 .doc / .xls / .ppt 共用同一个文件头。

    OLE2 目录流里存着流名（UTF-16LE 编码），据此区分；找不到再退回扩展名。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
    except OSError:
        return "doc"
    if "WordDocument".encode("utf-16-le") in head:
        return "doc"
    if "Workbook".encode("utf-16-le") in head:
        return "xls"
    if "PowerPoint Document".encode("utf-16-le") in head:
        return "ppt"
    ext = os.path.splitext(path)[1].lower()
    if ext in (".doc", ".xls", ".ppt"):
        return ext.lstrip(".")
    return "doc"


def _slide_no(name):
    m = re.search(r"(\d+)", name.rsplit("/", 1)[-1])
    return int(m.group(1)) if m else 0


MAX_CHARS = 300000          # 单文件抽取上限：超出则截断，避免生成读不动的巨型 md


def _cap(text):
    """抽出的文本过长时截断，并留下明确提示"""
    if text and len(text) > MAX_CHARS:
        return (text[:MAX_CHARS]
                + "\n\n（已截断：原文过长，只保留前 %d 字符；完整内容见原件）" % MAX_CHARS)
    return text


def extract_pptx(path):
    """按幻灯片顺序抽文本，返回 (text, slide_count, note)"""
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)]
            names.sort(key=_slide_no)
            if not names:
                return None, 0, "pptx 里没有幻灯片"
            out = []
            for n in names:
                root = ET.fromstring(z.read(n))
                texts = [(e.text or "").strip() for e in root.iter(A_NS + "t")]
                texts = [t for t in texts if t]
                body = "\n".join(texts) if texts else "（本页无文字）"
                out.append("【幻灯片 %d】\n%s" % (_slide_no(n), body))
            return _cap("\n\n".join(out)), len(names), ""
    except Exception as e:
        return None, 0, "pptx 解析失败：%s" % type(e).__name__


def extract_xlsx(path):
    """读 sharedStrings + 各工作表，按行拼成文本，返回 (text, sheet_count)"""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            shared = []
            if "xl/sharedStrings.xml" in names:
                root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in root.iter(S_NS + "si"):
                    shared.append("".join((t.text or "") for t in si.iter(S_NS + "t")))
            sheets = [n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
            sheets.sort(key=_slide_no)
            out = []
            for i, n in enumerate(sheets, 1):
                root = ET.fromstring(z.read(n))
                rows = []
                for row in root.iter(S_NS + "row"):
                    cells = []
                    for c in row.iter(S_NS + "c"):
                        v = c.find(S_NS + "v")
                        if v is None or v.text is None:
                            continue
                        if c.get("t") == "s":
                            try:
                                idx = int(v.text)
                                cells.append(shared[idx] if 0 <= idx < len(shared) else "")
                            except ValueError:
                                cells.append("")
                        else:
                            cells.append(v.text)
                    if any(x.strip() for x in cells):
                        rows.append(" | ".join(cells))
                out.append("【工作表 %d】\n%s" % (i, "\n".join(rows) if rows else "（空表）"))
            if not out:
                return None, 0, "xlsx 里没找到工作表"
            return _cap("\n\n".join(out)), len(sheets), ""
    except Exception as e:
        return None, 0, "xlsx 解析失败：%s" % type(e).__name__


def _strip_html(t):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|tr|li|h[1-6])>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", "", t)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def extract_text_file(path):
    """读纯文本类文件：编码嗅探（UTF-8 优先，回退 GB18030 / UTF-16）"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        return None, 0, "读取失败：%s" % type(e).__name__
    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        return None, 0, "编码识别失败（既不是 UTF-8 也不是 GB18030/UTF-16）"
    ext = os.path.splitext(path)[1].lower()
    if ext in (".html", ".htm"):
        text = _strip_html(text)
    return text, 0, ""
