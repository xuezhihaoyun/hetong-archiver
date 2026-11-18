#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从合同正文里抽当事人（主体）信息。

思路：先找「甲方／乙方／出租方……」标签，取标签后面紧跟的名称，
再在遇到「统一社会信用代码／地址／法定代表人／联系人／电话」等边界词时截断。
抽不出当事人的，视为空白模板或无主体文件。
"""

import re

# 标签 → 归一化角色名
LABELS = {
    "甲方": "甲方", "乙方": "乙方", "丙方": "丙方", "丁方": "丁方",
    "出租方": "出租方", "出租人": "出租方", "承租方": "承租方", "承租人": "承租方",
    "委托方": "委托方", "委托人": "委托方", "受托方": "受托方", "受托人": "受托方",
    "发包方": "发包方", "发包人": "发包方", "承包方": "承包方", "承包人": "承包方",
    "买方": "买方", "买受人": "买方", "卖方": "卖方", "出卖人": "卖方",
    "用人单位": "用人单位", "劳动者": "劳动者", "员工": "劳动者",
    "承诺人": "承诺人", "供方": "供方", "需方": "需方",
    "服务方": "服务方", "委托单位": "委托方", "被委托单位": "受托方",
}

STOP = ("统一社会信用代码", "信用代码", "法定代表人", "法定代表", "地址", "住所", "联系人",
        "联系电话", "电话", "税号", "纳税人", "邮箱", "电子邮箱", "身份证", "开户",
        "根据", "鉴于", "以下简称", "（以下", "(以下", "：", ":", "，", ",", "。", "；", ";")

FILLER = re.compile(r"^[\s_（）()【】\[\]：:、，,。．\.\-—－/／]*$")
PLACEHOLDER = ("____", "（空白）", "(空白)", "以下简称")


ORG_END = re.compile(r"(公司|学校|幼儿园|小学|中学|大学|高中|社区|居委会|工作站|医院|银行|事务所|工厂|厂|店|中心|集团|研究院|研究所|学院|基金|协会|商行|经营部|门市部|政府|管理局|委员会|工作室|物业|酒店|商场|超市|合作社|分行|分公司|支行|办事处)$")
TRAIL = ("乙方", "甲方", "丙方", "丁方", "证件类型", "联系方式", "联系", "电话", "法定代表人",
         "统一社会信用", "税号", "为提高", "根据", "鉴于", "合同编号", "签署", "签订", "开户",
         "邮箱", "证件", "编号", "以及", "双方", "签字", "盖章")


def _clean(raw):
    """清洗成尽可能干净的主体名称。"""
    s = re.sub(r"\s+", "", raw)                      # 中文里空格多是排版噪声，全部去掉
    s = re.sub(r"^[）)】\]：:、，,。]+", "", s)            # 去掉前置括注残留
    s = re.split(r"以下(?:简称|称)", s)[0]              # 去掉“（以下简称…）”
    # 未闭合的左括号 → 从这里截断
    if s.count("（") > s.count("）"):
        s = s[:s.rindex("（")]
    if s.count("(") > s.count(")"):
        s = s[:s.rindex("(")]
    for st in STOP + TRAIL:
        i = s.find(st)
        if i > 0:
            s = s[:i]
    s = s.strip(" ：:，,。;；、-—_）)")
    return s


def _is_org(name, role):
    if role in ("劳动者", "承诺人", "自然人"):
        # 人名：2-4 个汉字
        return bool(re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", name))
    return bool(ORG_END.search(name)) and 4 <= len(name) <= 40


def extract_parties(text, limit=8000):
    """返回 {角色: 名称}，抽不出则返回 {}。"""
    if not text:
        return {}
    head = text[:limit]
    found = {}
    for label, role in LABELS.items():
        if role in found:
            continue
        # 标签后可有“（发包方）”等括注，随后是冒号与名称
        pat = re.compile(label + r"\s*(?:[（(][^）)]{0,12}[）)])?\s*[:：]?\s*([^\n]{2,60})")
        for m in pat.finditer(head):
            name = _clean(m.group(1))
            if not name or FILLER.match(name):
                continue
            if any(p in name for p in PLACEHOLDER):
                continue
            if not _is_org(name, role):
                continue
            found[role] = name
            break
    return found


def has_parties(parties):
    return bool(parties)


def summary(parties, width=18):
    order = ["甲方", "乙方", "出租方", "承租方", "委托方", "受托方",
             "发包方", "承包方", "买方", "卖方", "用人单位", "劳动者"]
    items = [(r, parties[r]) for r in order if r in parties]
    items += [(r, v) for r, v in parties.items() if r not in order]
    return "｜".join(f"{r}:{v[:width]}" for r, v in items) if items else "（无主体信息）"


if __name__ == "__main__":
    import sys
    from dispatch import sniff_text
    for path in sys.argv[1:]:
        print(f"{path}\n    {summary(extract_parties(sniff_text(path)))}")
