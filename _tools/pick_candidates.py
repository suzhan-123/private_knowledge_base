# -*- coding: utf-8 -*-
"""
pick_candidates.py —— 从素材里挑出「计算机方向」的申请书候选

为什么不用通用词：'系统/模型/信号/控制/网络/数据/识别' 在生物医学里到处都是，
拿它们筛会捞出一堆医学本子。所以这里只用**信息/计算机专有**的强特征词，
并显式排除生物医学/地学的强特征词。

用法：
    python pick_candidates.py <word_scan的jsonl（可多份用;分隔）> <pdf目录（可多个用;分隔）> <输出tsv>
"""
import json
import os
import re
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_pdf import extract_meta                                  # noqa: E402
import pymupdf                                                        # noqa: E402

# 信息/计算机专有强特征词（避免通用词）
STRONG = [
    "计算机", "软件", "算法", "程序语言", "编译", "操作系统", "数据库", "数据挖掘",
    "机器学习", "深度学习", "神经网络", "人工智能", "模式识别", "图像处理",
    "计算机视觉", "自然语言", "语音识别", "信息检索", "推荐系统", "知识图谱",
    "语义网", "语义", "本体", "网格计算", "网格", "普适计算", "云计算", "边缘计算",
    "物联网", "传感器网络", "传感网", "网络安全", "密码", "隐私保护", "分布式",
    "并行计算", "并行", "嵌入式", "芯片", "微处理器", "多核处理器", "多核", "VLSI",
    "忆阻器", "神经形态", "机器人", "SLAM", "多媒体", "流媒体", "拥塞控制", "网络协议",
    "信息通信", "移动通信", "无线通信", "宽带", "信息存储", "信息处理", "信息可用性",
    "虚拟现实", "人机交互", "用户界面", "可视化", "遥感图像", "图像压缩", "图像融合",
    "信号处理", "时空数据", "数据模型", "知识组织", "知识编辑", "服务组合", "SOA",
    "Web服务", "工作流", "高性能计算", "符号计算", "信息网格", "电子政务", "数字地球",
    "信息检索", "数据分发", "位置隐私", "无线传感器", "信息处理平台", "知识处理",
]

# 明确排除：这些领域即便标题里带"信号/系统/数据"也不是我们要的
EXCLUDE = [
    "中医", "穴位", "脾", "肠道", "甜味觉", "蛋白", "基因", "细胞", "通路", "肿瘤", "癌",
    "白血病", "干细胞", "菌", "病毒", "免疫", "药理", "药物", "临床", "患者", "骨",
    "心肌", "血管", "肺", "肝", "肾", "脑缺血", "乳腺", "子宫内膜", "核酸", "RNA",
    "DNA", "质谱", "测序", "组学", "代谢", "受体", "分子机理", "酵母", "朊病毒",
    "禽流感", "地质", "盆地", "白垩纪", "流域", "土壤", "作物", "油菜", "水稻",
    "生态", "气象", "海洋", "矿床", "边坡", "水利", "水电", "玻璃", "钛合金",
    "复合材料", "太阳电池", "染料敏化", "LED", "摩擦学", "焊接", "冶金", "水泥",
    "生物学", "生物医学", "脑科学", "知觉", "认知功能成像", "植物", "动物", "水产",
]


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


def verdict(title, code):
    """返回 (等级, 命中词说明) 或 None"""
    if not title or title == "未提及":
        return None
    for x in EXCLUDE:
        if x in title:
            return None
    hits = [x for x in STRONG if x in title]
    cu = (code or "").upper()
    if cu.startswith(("F02", "F04")):
        return ("A", "F02/F04代码" + ("；命中:" + "、".join(hits[:3]) if hits else ""))
    if hits:
        return ("B", "命中:" + "、".join(hits[:5]))
    return None


def main(jsonls, roots, out_tsv):
    rows = []
    for jp in [x for x in jsonls.split(";") if x.strip() and os.path.exists(x)]:
        with open(jp, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if not r.get("ok"):
                    continue
                p = r["path"]
                meta = extract_meta(r.get("text", ""))
                v = verdict(meta.get("项目名称", ""), meta.get("申请代码", ""))
                if v:
                    rows.append([v[0], v[1], meta.get("申请代码", "未提及"),
                                 meta.get("年份", "未提及"), meta.get("项目类型", "未提及"),
                                 meta.get("项目名称", ""), p])

    seen = set()
    for root in [x for x in roots.split(";") if x.strip()]:
        for p in glob.glob(os.path.join(root, "**", "*.pdf"), recursive=True):
            if re.search(r"\(\d+\)$", os.path.splitext(os.path.basename(p))[0]):
                continue
            key = os.path.abspath(p).lower()
            if key in seen:
                continue
            seen.add(key)
            txt, _ = pdf_head(p)
            if not txt:
                continue
            meta = extract_meta(txt)
            v = verdict(meta.get("项目名称", ""), meta.get("申请代码", ""))
            if v:
                rows.append([v[0], v[1], meta.get("申请代码", "未提及"),
                             meta.get("年份", "未提及"), meta.get("项目类型", "未提及"),
                             meta.get("项目名称", ""), p])

    # 按 标题 去重（保留等级最高的那条），A 级优先
    best = {}
    for r in rows:
        t = r[5]
        if t not in best or (r[0] == "A" and best[t][0] == "B"):
            best[t] = r
    uniq = sorted(best.values(), key=lambda r: (r[0], r[2], r[3]))

    with open(out_tsv, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("\t".join(["等级", "命中依据", "申请代码", "年份", "项目类型", "标题", "完整路径"]) + "\n")
        for r in uniq:
            f.write("\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in r) + "\n")

    a = sum(1 for r in uniq if r[0] == "A")
    print("CANDIDATES=%d  (A级F代码=%d  B级标题命中=%d) -> %s" % (len(uniq), a, len(uniq) - a, out_tsv))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
