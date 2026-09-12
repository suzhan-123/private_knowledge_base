# -*- coding: utf-8 -*-
"""kb_cats.py —— 各分类的元信息提取与编号规则

基金本子（10）沿用 kb_extract 的本子字段提取；
教学 / 办公 / 文献 / 论文 各有自己的规则 —— 这些文件没有「申请代码」，
元信息主要来自**文件名**（下载与命名习惯使然），正文只作补充。

命名规则见 _schema/naming.md。
"""
import os
import re

# ---------------------------------------------------------------- 通用

def _title(name):
    return os.path.splitext(os.path.basename(name))[0].strip()


def _year(name, head=""):
    """年份：先看文件名，再看正文前 1500 字"""
    for src in (name or "", (head or "")[:1500]):
        m = re.search(r"(19|20)\d{2}", src)
        if m:
            return m.group(0)
    return "XXXX"


def _pick(name, pairs, default):
    for k, v in pairs:
        if k in name:
            return v
    return default


def _mk(parts, seq):
    return "-".join([str(p) for p in parts if p] + ["%04d" % seq])


# ---------------------------------------------------------------- 教学

JX_PAIRS = [("试卷", "试卷"), ("习题", "习题"), ("实验", "实验指导"),
            ("教案", "教案"), ("大纲", "大纲"), ("讲", "课件"), ("课件", "课件")]


def jx_meta(name, head):
    return {"标题": _title(name),
            "类型": _pick(name, JX_PAIRS, "课件"),
            "年份": _year(name, head)}


def jx_id(meta, seq):
    return _mk([meta.get("年份", "XXXX"), meta.get("类型", "XX")], seq)


# ---------------------------------------------------------------- 办公

# 顺序即优先级：先用「自身就是那份文件」的词，再用泛化的制度类词
BG_PAIRS = [("通知", "通知"), ("报告", "报告"), ("总结", "总结"), ("纪要", "会议纪要"),
            ("目录", "目录"), ("名单", "名单"),
            ("简历", "简历"), ("CV", "简历"),
            ("方案", "方案"), ("表格", "表格"),
            ("办法", "制度"), ("规定", "制度"), ("制度", "制度"), ("考核", "制度"),
            ("评价体系", "制度"), ("指标", "制度"), ("岗位", "制度"), ("聘期", "制度"),
            ("附件", "材料")]


def bg_meta(name, head):
    return {"标题": _title(name),
            "类别": _pick(name, BG_PAIRS, "其他"),
            "年份": _year(name, head)}


def bg_id(meta, seq):
    return _mk([meta.get("年份", "XXXX"), meta.get("类别", "XX")], seq)


# ---------------------------------------------------------------- 文献（参考资料）

WX_PAIRS = [("综述", "综述"), ("标准", "标准"), ("专利", "专利"), ("教材", "教材"),
            ("白皮书", "白皮书"), ("指南", "技术报告"), ("报告", "技术报告")]


def wx_meta(name, head):
    return {"标题": _title(name),
            "类型": _pick(name, WX_PAIRS, "其他"),
            "年份": _year(name, head)}


def wx_id(meta, seq):
    return _mk([meta.get("年份", "XXXX"), meta.get("类型", "XX")], seq)


# ---------------------------------------------------------------- 论文

VENUES = ["CVPR", "ICCV", "ECCV", "NeurIPS", "NIPS", "ICML", "ICLR", "AAAI", "IJCAI",
          "ACL", "EMNLP", "NAACL", "KDD", "SIGIR", "WWW", "CIKM", "WSDM",
          "TKDE", "TPAMI", "TNNLS", "TMC", "TOIS", "TITS", "TIM", "TIST",
          "Nature", "Science", "Cell"]


def lw_meta(name, head):
    base = _title(name)
    # 第一作者姓：文件名开头的英文词（下载的论文常以作者起头）
    m = re.match(r"([A-Z][A-Za-z\-']{1,20})", base)
    author = m.group(1) if m else "XX"
    venue = "XX"
    for v in VENUES:
        if re.search(r"(?<![A-Za-z])" + re.escape(v) + r"(?![A-Za-z])", base, re.I):
            venue = v
            break
    if venue == "XX" and re.search(r"arxiv", base, re.I):
        venue = "arXiv"
    return {"标题": base, "第一作者": author, "出处": venue, "年份": _year(name, head)}


def lw_id(meta, seq):
    return _mk([meta.get("年份", "XXXX"), meta.get("第一作者", "XX"),
                meta.get("出处", "XX")], seq)


# ---------------------------------------------------------------- 配置表

CATS = {
    # 基金本子用 kb_extract 的本子字段提取，这里不接管
    "10_基金本子": {"meta": None, "id": None},
    "20_教学":     {"meta": jx_meta, "id": jx_id},
    "30_办公":     {"meta": bg_meta, "id": bg_id},
    "40_文献":     {"meta": wx_meta, "id": wx_id},
    "45_论文":     {"meta": lw_meta, "id": lw_id},
}
