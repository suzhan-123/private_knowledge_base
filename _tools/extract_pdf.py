# -*- coding: utf-8 -*-
"""
extract_pdf.py —— PDF 抽取器（v2 保守合并版）

与旧方案的区别：
  1. 块提取 + 页眉页脚过滤（旧方案把「评审材料: 某某专家评议专用」也抽进正文）
  2. 保守合并：只合并明显的正文硬换行；表格行、短行、多空格行一律不动
     （旧方案不合并 -> 段落碎；激进合并 -> 表格挤成一行。都不行）
  3. 元信息从原文抽取（资助类别/申请代码/项目名称/申请人/年份），不再靠文件名猜
  4. 输出一律 UTF-8

用法：
    python extract_pdf.py <pdf路径> <输出txt路径>      # 抽文本
    python extract_pdf.py --meta <pdf路径>             # 只看元信息
"""
import json
import re
import sys

import pymupdf

ENDERS = "。！？；：”』）】…，、,.;:!?)]}"
CJK = "[\u4e00-\u9fff]"

# 页脚常见模式（不同年份模板不同）
FOOT_PATTERNS = [
    re.compile(r"^第\s*\d+\s*页"),
    re.compile(r"^版本\s*[\d.]+"),
    re.compile(r"^\d{1,4}$"),
    re.compile(r"^-\s*\d+\s*-$"),
    re.compile(r"^国家自然科学基金委员会$"),
]


# ============================================================ 文本抽取

def _pages_blocks(doc):
    pages = []
    for p in doc:
        pages.append([(b[1], b[4]) for b in p.get_text("blocks")])   # (y0, text)
    return pages


def _find_running(pages, n):
    """跨页重复出现的短文本 = 页眉/页脚"""
    from collections import Counter
    cnt = Counter()
    for blocks in pages:
        seen = set()
        for _, t in blocks:
            for ln in t.split("\n"):
                ln = ln.strip()
                if ln and len(ln) < 80 and ln not in seen:
                    seen.add(ln)
                    cnt[ln] += 1
    th = max(2, int(n * 0.6))
    return {t for t, c in cnt.items() if c >= th}


def _can_merge(prev, nxt):
    """保守合并判据：全部满足才合并"""
    if len(prev) < 20 or len(nxt) < 20:        # 短行 = 表格/字段行
        return False
    if "\t" in prev or "\t" in nxt:
        return False
    if prev[-1] in ENDERS:                      # 已到句末，本该断段
        return False
    if not re.match(CJK, nxt):                  # 下一行不是中文起头
        return False
    if re.search(r"\s{2,}", prev) or re.search(r"\s{2,}", nxt):   # 多空格 = 疑似表格
        return False
    if re.match(r"^\s*[\(（]?\d+[\)）]?\s*$", prev):               # 纯序号行
        return False
    return True


def _merge(lines):
    res, buf = [], ""
    for ln in lines:
        if not buf:
            buf = ln
            continue
        if _can_merge(buf, ln):
            buf += ln
        else:
            res.append(buf)
            buf = ln
    if buf:
        res.append(buf)
    return res


def extract_pdf(path):
    try:
        doc = pymupdf.open(path)
    except Exception as e:
        return None, 0, "PDF 打不开：%s" % type(e).__name__
    try:
        n = doc.page_count
        if doc.needs_pass:
            return None, n, "PDF 已加密，需要密码"
        pages = _pages_blocks(doc)
    finally:
        doc.close()

    running = _find_running(pages, n)
    out = []
    for blocks in pages:
        lines = []
        for _, t in blocks:
            flat = re.sub(r"[ \t]+", " ", t).strip()
            if not flat:
                continue
            for ln in flat.split("\n"):
                ln = re.sub(r"[ \t]+", " ", ln).strip()
                if not ln or ln in running:
                    continue
                if any(p.search(ln) for p in FOOT_PATTERNS):
                    continue
                lines.append(ln)
        out.extend(_merge(lines))
    return "\n".join(out), n, ""


# ============================================================ 元信息（从原文读）

def _grab(patterns, src):
    for p in patterns:
        m = re.search(p, src, re.M)          # re.M：让 $ 能匹配行尾
        if m:
            v = m.group(1).strip()
            v = re.sub(r"[\t ]+", " ", v).strip()
            v = v.strip("：: 　")
            if v:
                return v
    return "未提及"


# 字段值的终止词：值独占一行时，遇到这些标签就截断
_STOP = (r"(?:亚类说明|附注说明|项目名称|英文名称|申请代码|学科代码|申请[人者]|依托单位|"
         r"合作研究单位|通讯地址|邮政编码|电子邮箱|办公电话|单位电话|申报日期|收件日期|"
         r"接收编号|接收部门|基地类别|研究期限|资助经费|执行年限|电\s*话|传\s*真)")


def _grab_lines(patterns, src):
    """取值：兼容「同行」与「值在下一行」两种排布。

    2000-2012 老标书是「资助类别：面上项目」同行；
    2020/2025 版申请书是「资助类别：\\n青年科学基金项目（C类）」换行，
    旧写法 [^\\s\\n]+ 会在换行处匹配失败。
    """
    for p in patterns:
        m = re.search(p, src, re.M)
        if m:
            v = re.split(_STOP, m.group(1))[0]
            v = re.sub(r"[\t \xa0]+", " ", v).strip("：: 　")
            if v:
                return v
    return "未提及"


def _pick_title(head):
    """项目名称：兼容「同一行」「换行」「表格单元格」三种排布"""
    for p in [r"项目名称[：:][^\S\n]*(.+)",
              r"项目名称[^\S\n]*\n[^\S\n]*(.+)",
              r"项目名称[^\S\n]*\t[^\S\n]*(.+)"]:
        m = re.search(p, head, re.M)
        if m:
            v = re.split(r"\t|申\s*请\s*[人者]|电\s*话|资助类别|亚类说明|附注说明", m.group(1))[0]
            v = re.sub(r"[\t ]+", " ", v).strip("：: 　")
            if 4 <= len(v) <= 120:
                return v
    return "未提及"


_CN_DIGIT = {"〇": 0, "零": 0, "○": 0, "O": 0, "o": 0,
             "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_year(s):
    """'二零零零' / '二〇〇〇' -> '2000'"""
    d = [_CN_DIGIT[c] for c in s if c in _CN_DIGIT]
    return "".join(str(x) for x in d) if len(d) == 4 else None


def _pick_year(head):
    """年份判定优先级：
       1. 封面「（2 0 2 5 版）」——兼容全角括号与不换行空格（新版申请书）
       2. 封面「NSFC YYYY」
       3. 「申报 / 申请日期」（值可能在下一行）
       4. 中文数字的申报日期
       5. 「YYYY 年 M 月」，逐行扫描并**跳过「出生」行**
          （新版申请书把「出生 年月 1996年02月」排在同一页，旧写法会误抓成申请年份）
       6. 兜底：全文第一个 19xx/20xx（同样跳过「出生」行）
    """
    # 1. （2 0 2 5 版）
    m = re.search(r"[（(][\s\xa0]*((?:\d[\s\xa0]*){4})[\s\xa0]*版[\s\xa0]*[）)]", head)
    if m:
        t = re.sub(r"[\s\xa0]+", "", m.group(1))
        if re.match(r"^(?:19|20)\d{2}$", t):
            return t
    # 2. NSFC YYYY
    m = re.search(r"NSFC[\s\xa0]*((?:19|20)\d{2})", head)
    if m:
        return m.group(1)
    # 3. 申报 / 申请日期（值可在下一行）
    m = re.search(r"(?:申报|申请)日期[：:][\s\xa0]*(?:\n[\s\xa0]*)?((?:19|20)\d{2})", head)
    if m:
        return m.group(1)
    # 4. 中文数字日期
    z = re.search(r"(?:申报|申请)日期[：:][^\n]{0,40}", head)
    if z:
        mm = re.search(r"([〇零○一二三四五六七八九Oo]{4})", z.group(0))
        if mm:
            y = _cn_year(mm.group(1))
            if y:
                return y
    # 5/6. 逐行兜底，跳过「出生」行
    for pat in (r"((?:19|20)\d{2})\s*年\s*\d{1,2}\s*月", r"((?:19|20)\d{2})"):
        for line in head.split("\n"):
            if "出生" in line:
                continue
            mm = re.search(pat, line)
            if mm:
                return mm.group(1)
    return "未提及"


def extract_meta(text):
    head = text[:4000]
    m = {}
    # 项目名称：兼容同一行 / 换行 / 表格单元格三种排布
    m["项目名称"] = _pick_title(head)
    # 限定同一行，避免吃到下一行的「附注说明：」
    m["资助类别"] = _grab_lines([r"资助类别[：:][^\S\n]*(?:\n[^\S\n]*)?([^\n]+)",
                                 r"项目类别[：:][^\S\n]*(?:\n[^\S\n]*)?([^\n]+)"], head)
    m["亚类说明"] = _grab_lines([r"亚类说明[：:][^\S\n]*(?:\n[^\S\n]*)?([^\n]+)"], head)
    m["申请代码"] = _grab([
        r"申请代码[：:]?[^\S\n]*\n?[^\S\n]*([A-H]\s?\d{2,8})",
        r"申报学科代码\s*1?[：:]?[^\S\n]*\n?[^\S\n]*([A-H]\s?\d{2,8})",
        r"\b([A-H]\d{6})\b",
    ], head)
    m["申请人"] = _grab_lines([
        r"申\s*请\s*[人者][：:][^\S\n]*(?:\n[^\S\n]*)?([^\n]+)",
    ], head)
    m["依托单位"] = _grab_lines([
        r"依托单位[：:][^\S\n]*(?:\n[^\S\n]*)?([^\n]+)",
        r"所在单位[：:][^\S\n]*(?:\n[^\S\n]*)?([^\n]+)",
    ], head)
    m["年份"] = _pick_year(head)

    # ---- 项目类型：资助类别为主，与亚类说明冲突时标注存疑 ----
    cat, sub = m["资助类别"], m["亚类说明"]
    order = ["青年", "地区", "重点", "重大", "面上"]
    in_cat = [t for t in order if t in cat]
    in_sub = [t for t in order if t in sub]
    if in_cat:
        m["项目类型"] = in_cat[0]
    elif in_sub:
        m["项目类型"] = in_sub[0]
    elif cat != "未提及":
        m["项目类型"] = cat
    else:
        m["项目类型"] = "未提及"
    if in_cat and in_sub and in_cat[0] != in_sub[0]:
        m["类型存疑"] = "资助类别=%s；亚类说明=%s" % (cat, sub)

    # 学科代码归一化（去掉空格）
    if m["申请代码"] != "未提及":
        m["申请代码"] = m["申请代码"].replace(" ", "")
    return m


# ============================================================ 质量检测

def check_quality(text, page_count, note):
    if text is None:
        return {"grade": "低", "route": "manual", "reasons": [note or "抽取失败"], "stats": {}}

    total = len(text.strip())
    cn = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    bad = sum(1 for c in text if c == "\ufffd" or 0xE000 <= ord(c) <= 0xF8FF)
    per_page = (total / page_count) if page_count else None
    reasons = []
    stats = {
        "总字符数": total, "中文字符数": cn,
        "中文占比": round(cn / total, 4) if total else 0,
        "乱码字符数": bad, "页数": page_count,
        "平均每页字符数": round(per_page, 1) if per_page else None,
    }
    if note:
        reasons.append(note)
    if total < 50:
        reasons.append("全文仅 %d 字，抽取失败或内容为空" % total)
    if page_count and per_page is not None and per_page < 50:
        reasons.append("平均每页仅 %.0f 字，疑似扫描件（无文字层，需 OCR）" % per_page)
    if total and bad / total > 0.05:
        reasons.append("乱码率 %.1f%% 超标" % (100 * bad / total))
    if reasons:
        return {"grade": "低", "route": "manual", "reasons": reasons, "stats": stats}

    if page_count and per_page and per_page >= 800 and bad / max(total, 1) <= 0.002:
        grade = "高"
    elif page_count and per_page and per_page < 200:
        grade = "中"
    else:
        grade = "高"
    return {"grade": grade, "route": "normal", "reasons": reasons, "stats": stats}


# ============================================================ CLI

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    meta_only = "--meta" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    src = args[0]
    text, pc, note = extract_pdf(src)
    q = check_quality(text, pc, note)

    if meta_only:
        out = {"文件": src.split("\\")[-1], "质量": q["grade"],
               "原因": q["reasons"], "统计": q["stats"],
               "元信息": extract_meta(text) if text else {}}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        sys.exit(0)

    dst = args[1]
    meta = extract_meta(text) if text else {}
    lines = ["# %s" % meta.get("项目名称", ""), ""]
    lines.append("> 来源文件：%s" % src.split("\\")[-1])
    lines.append("> 抽取质量：%s ｜ 页数：%s" % (q["grade"], pc))
    lines.append("> 元信息：" + " ｜ ".join("%s=%s" % (k, v) for k, v in meta.items()))
    if q["reasons"]:
        lines.append("> 提示：" + "; ".join(q["reasons"]))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(text if text else "")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("OK  chars=%d  pages=%s  grade=%s  type=%s  code=%s  year=%s"
          % (q["stats"].get("总字符数", 0), pc, q["grade"],
             meta.get("项目类型"), meta.get("申请代码"), meta.get("年份")))
