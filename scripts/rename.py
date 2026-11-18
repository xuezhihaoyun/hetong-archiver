#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一合同文件命名。

规则：客户-合同名（标的/对方）-状态-版本-YYYYMMDD.扩展名
  · 客户   与 00.已经处理/ 下文件夹同名，简体
  · 合同名 合同/协议/法律意见书/备忘录/函，是什么写什么，括号全角
  · 状态   拟定稿-P｜修订版｜审核回复｜批注版｜定稿｜签署版｜草稿
  · 版本   V1、V2…，同一状态多稿才写
  · 日期   YYYYMMDD，取该件出具日；查不出就不写

用法：
  python3 rename.py "<文件夹>"             # 演练，出台账（默认）
  python3 rename.py "<文件夹>" --apply     # 真改名
  python3 rename.py "<文件夹>" --csv out.csv
"""

import csv
import json
import os
import re
import sys
import datetime

from dispatch import load_cfg, sniff_text
from parties import extract_parties

STATUS = ["拟定稿-P", "拟定稿", "审核回复", "审查批注版", "批注版",
          "修订版", "修改稿", "定稿", "签署版", "草稿", "最终版"]

JUNK = [r"_副本\d*", r"_copy\d*", r"\(\d+\)", r"（\d+）", r"最终版", r"最后版",
        r"最新版?", r"【[^】]*】", r"\[[^\]]*\]", r"^\s*\d{2,4}\s*",
        r"部门核对", r"定稿版", r"修改搞", r"修改稿"]

EXT_OK = (".doc", ".docx", ".pdf", ".xls", ".xlsx", ".wps", ".ppt", ".pptx")


def norm_date(text, mtime):
    """从字符串里找日期，返回 YYYYMMDD 或 ''。"""
    m = re.search(r"(20\d{2})(\d{2})(\d{2})(?!\d)", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}{mo:02d}{d:02d}"
    m = re.search(r"(20\d{2})\s*[-.年/]\s*(\d{1,2})\s*[-.月/]\s*(\d{1,2})\s*[日号]?", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}{mo:02d}{d:02d}"
    m = re.search(r"(?<!\d)(\d{1,2})[.月](\d{1,2})(?!\d)", text)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            y = datetime.datetime.fromtimestamp(mtime).year
            return f"{y}{mo:02d}{d:02d}"
    return ""


def norm_status(text):
    for s in STATUS:
        if s in text:
            return "拟定稿-P" if s == "拟定稿" and "拟定稿-P" in text else s
    return ""


def find_client(name, path, cfg, parent=""):
    """先按文件名/所在文件夹找客户，再按当事人主体找。"""
    for c in cfg["clients"]:
        if c.get("weak"):
            continue
        for a in sorted(c["aliases"], key=len, reverse=True):
            if len(a) >= 2 and a in name:
                return c["name"], a
            if parent and len(a) >= 2 and a in parent:
                return c["name"], f"文件夹「{parent}」"
    try:
        parties = extract_parties(sniff_text(path))
    except Exception:
        parties = {}
    for role, pname in parties.items():
        for c in cfg["clients"]:
            if c.get("weak"):
                continue
            for a in sorted(c["aliases"], key=len, reverse=True):
                if len(a) >= 3 and a in pname:
                    return c["name"], f"{role}:{pname}"
    for r in cfg.get("file_rules", []):
        if r["pattern"] in name and r["client"] != "__TEMPLATE__":
            return r["client"], f"固定规则「{r['pattern']}」"
    return "", ""


def clean_object(text):
    s = text
    for pat in JUNK:
        s = re.sub(pat, " ", s)
    # 公司名（含“有限公司/分公司”）整段去掉：客户信息已在第一段
    s = re.sub(r"[\u4e00-\u9fa5A-Za-z（）()]{2,25}?(?:股份)?有限公司", " ", s)
    s = re.sub(r"[（(]深圳[）)]", " ", s)
    # 合同编号类：JM-I-20260316009-1-SUP01 / XC2611…
    s = re.sub(r"[A-Za-z]{2,}-[\w\-]{4,}", " ", s)
    s = re.sub(r"[A-Z]{2}\d{6,}", " ", s)
    s = s.replace("：", "").replace(":", "")
    s = re.sub(r"[_\s]+", " ", s)
    s = s.replace("(", "（").replace(")", "）")
    s = re.sub(r"（\s*）", "", s)
    s = re.sub(r"（(合同编号|编号|附件|以下简称|以下简称\w+)[：:]?[^）]*）", "", s)          # 去掉被清理空的括号
    s = re.sub(r"[（(][\s\-—·、，,]*", "（", s)
    s = re.sub(r"^[\s\-—·、，,0-9]+", "", s)
    s = re.sub(r"[\s\-—·、，,]+$", "", s)
    s = re.sub(r"\s+", "", s)
    return s[:30] or ""


def build(name, path, cfg, parent=""):
    stem, ext = os.path.splitext(name)
    mtime = os.path.getmtime(path)
    date = norm_date(stem, mtime)
    status = norm_status(stem)
    marks = [m for m in ["双审"] if m in stem]
    ver = ""
    mv = re.search(r"[Vv](\d+)", stem)
    if mv:
        ver = "V" + mv.group(1)
    client, how = find_client(stem, path, cfg, parent)

    obj = stem
    obj = re.sub(r"20\d{6}(?!\d)", " ", obj)
    obj = re.sub(r"20\d{2}[-.年/]?\d{1,2}[-.月/]?\d{1,2}", " ", obj)
    obj = re.sub(r"(?<!\d)\d{1,2}[.月]\d{1,2}(?!\d)", " ", obj)
    if status:
        obj = obj.replace(status, " ")
    for m in marks:
        obj = obj.replace(m, " ")
    # 只去掉开头的客户前缀，避免“飞力达-飞力达…”；机构全称里的字不动
    if client:
        for c in cfg["clients"]:
            if c["name"] == client:
                for a in sorted(c["aliases"], key=len, reverse=True):
                    obj = re.sub(r"^" + re.escape(a) + r"[-_\s]*", "", obj)
    obj = re.sub(r"[Vv]\d+", " ", obj)
    obj = clean_object(obj)
    if not obj:
        obj = status or "合同"

    mark_txt = "".join(f"（{m}）" for m in marks)   # 客户给的标记，紧跟合同名，用括号标注
    parts = [p for p in [client, obj + mark_txt, status, ver, date] if p]
    new = "-".join(parts) + ext
    new = re.sub(r"-{2,}", "-", new)
    new = new.replace("-." + ext.lstrip("."), ext)
    return new, {"client": client, "status": status, "ver": ver, "date": date,
                 "how": how, "marks": ",".join(marks)}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    target = os.path.abspath(sys.argv[1])
    apply_ = "--apply" in sys.argv
    csv_path = None
    if "--csv" in sys.argv:
        csv_path = sys.argv[sys.argv.index("--csv") + 1]
    cfg = load_cfg()

    rows = []
    for dp, dn, fn in os.walk(target):
        dn[:] = [d for d in dn if not d.startswith(".")]
        for f in sorted(fn):
            if f.startswith(".") or not f.lower().endswith(EXT_OK):
                continue
            p = os.path.join(dp, f)
            parent = os.path.basename(dp)
            new, info = build(f, p, cfg, "" if parent == os.path.basename(target) else parent)
            rows.append((os.path.relpath(p, target), new, info))

    print(f"{target}\n共 {len(rows)} 份，其中建议改名 {sum(1 for a, b, _ in rows if a != b)} 份\n")
    for old, new, info in rows:
        flag = "  " if old == new else "→ "
        note = f"[{info['how']}]" if info["how"] else ""
        print(f"{flag}{old}\n    {new}  {note}")

    out = csv_path or os.path.join(BASE, "改名台账",
                                   datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["原文件名", "新文件名", "客户", "状态", "标记", "版本", "日期", "识别依据"])
        for old, new, info in rows:
            w.writerow([old, new, info["client"], info["status"], info["marks"],
                        info["ver"], info["date"], info["how"]])
    print(f"\n台账：{out}")

    if not apply_:
        print("\n（演练模式，未改名。确认后加 --apply）")
        return

    n = 0
    for old, new, _ in rows:
        if old == new:
            continue
        src = os.path.join(target, old)
        dst = os.path.join(os.path.dirname(src), new)
        if os.path.exists(dst):
            base, ext = os.path.splitext(dst)
            i = 2
            while os.path.exists(f"{base}-{i}{ext}"):
                i += 1
            dst = f"{base}-{i}{ext}"
        os.rename(src, dst)
        n += 1
    print(f"\n已改名 {n} 份。")


if __name__ == "__main__":
    main()
