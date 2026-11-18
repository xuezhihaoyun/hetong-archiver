#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合同归档分派 —— 把「中转」里处理完毕的合同，按客户归到「00.已经处理/<客户>/」。

用法：
  python3 dispatch.py                 # 演练：只打印对照表，不动文件
  python3 dispatch.py --apply         # 真的移动
  python3 dispatch.py --apply --force # 低置信度也强制移动（默认不动，留给人工/AI 判定）
  python3 dispatch.py --list-clients  # 只看客户别名表

判定依据（从强到弱）：
  1) 文件名里出现客户别名  → 高置信
  2) 文件所在的子文件夹名出现别名（如 中转/未来学校/xxx.docx）→ 高置信
  3) 只命中 weak 别名（如「齐心」）→ 低置信，不自动移动
  没命中任何客户 → 待定，留在原处并列进报告。

安全约定：从不删除、从不覆盖。同名冲突自动加 「 (2)」后缀。
"""

import json
import os
import re
import shutil
import sys
import datetime

from parties import extract_parties, has_parties

import cfg as cfgmod

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE, "归档日志")


def load_cfg():
    return cfgmod.load(require_root=True)


def check_placeholders(files):
    """iCloud 未下载的占位符：读不到正文，主体识别会失效，提前报出来。"""
    bad = []
    for rel, full in files:
        try:
            if os.path.getsize(full) == 0 or os.path.getsize(full) < 1024:
                bad.append(rel)
        except OSError:
            bad.append(rel)
    return bad


def check_conflicts(inbox_abs):
    """iCloud 冲突副本：名字里带 ' 2'、'conflicted copy' 之类。"""
    out = []
    for dp, dn, fn in os.walk(inbox_abs):
        for f in fn:
            if re.search(r"( 2\.|conflicted copy|\(conflict)", f, re.I):
                out.append(os.path.relpath(os.path.join(dp, f), inbox_abs))
    return out


def is_ignored(name, patterns):
    return any(p in name for p in patterns)


def scan_inbox(inbox_abs, ignore):
    """返回 [(相对路径, 绝对路径)]，跳过隐藏目录与忽略文件。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(inbox_abs):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.startswith(".") or is_ignored(fn, ignore):
                continue
            full = os.path.join(dirpath, fn)
            out.append((os.path.relpath(full, inbox_abs), full))
    return sorted(out)


def sniff_text(path, limit=200000):
    """尽量取出正文文字用于识别客户：docx 走 zip，doc 走 textutil，pdf 走 Spotlight。"""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".docx", ".xlsx", ".pptx"):
            import zipfile
            import re as _re
            with zipfile.ZipFile(path) as z:
                names = [n for n in z.namelist()
                         if n.endswith("document.xml") or n.startswith("docProps/")]
                buf = []
                for n in names:
                    buf.append(z.read(n).decode("utf-8", "ignore"))
            txt = " ".join(buf)
            return _re.sub(r"<[^>]+>", " ", txt)[:limit]
        if ext == ".doc":
            import subprocess
            r = subprocess.run(["textutil", "-convert", "txt", "-stdout", path],
                               capture_output=True, timeout=30)
            return r.stdout.decode("utf-8", "ignore")[:limit]
        if ext == ".pdf":
            import subprocess
            r = subprocess.run(["mdls", "-raw", "-name", "kMDItemTextContent", path],
                               capture_output=True, timeout=30)
            out = r.stdout.decode("utf-8", "ignore")
            if out.strip() and out.strip() != "(null)":
                return out[:limit]
    except Exception:
        pass
    return ""


def match_client(rel_path, clients):
    """返回 (client, 依据, 是否低置信) 或 (None, None, False)。"""
    parts = rel_path.split(os.sep)
    name = parts[-1]
    parent = parts[-2] if len(parts) >= 2 else ""

    strong, weak = [], []
    for c in clients:
        for a in c["aliases"]:
            if a in name:
                (weak if c.get("weak") else strong).append((c, f"文件名含「{a}」"))
            elif parent and a in parent:
                (weak if c.get("weak") else strong).append((c, f"所在文件夹含「{a}」"))

    def dedupe(lst):
        seen, res = set(), []
        for c, why in lst:
            if c["name"] in seen:
                continue
            seen.add(c["name"])
            res.append((c, why))
        return res

    strong, weak = dedupe(strong), dedupe(weak)
    if len(strong) == 1:
        return strong[0][0], strong[0][1], False
    if not strong and not weak:
        return None, "文件名/文件夹未识别", True
    if len(strong) > 1:
        return None, "同时命中多个客户：" + "、".join(c["name"] for c, _ in strong), True
    if len(weak) == 1:
        return weak[0][0], weak[0][1] + "（弱别名）", True
    if len(weak) > 1:
        return None, "弱别名同时命中：" + "、".join(c["name"] for c, _ in weak), True
    return None, "未识别客户", True


def match_by_parties(parties, clients):
    """按合同当事人名称匹配客户。返回 (client, 依据, 低置信)。"""
    if not parties:
        return None, None, False
    hits = []
    for role, name in parties.items():
        for c in clients:
            if c.get("weak"):
                continue
            for a in sorted(c["aliases"], key=len, reverse=True):
                if len(a) < 3:
                    continue
                if a in name:
                    hits.append((c, f"{role}「{name}」"))
                    break
    names = {c["name"] for c, _ in hits}
    if len(names) == 1:
        c0 = hits[0][0]
        return c0, "当事人 " + hits[0][1], False
    if len(names) > 1:
        return None, "当事人分属多个客户：" + "、".join(sorted(names)), True
    return None, None, False


def target_dir(archive_abs, client):
    if client.get("dir"):
        return os.path.join(archive_abs, client["dir"])
    return os.path.join(archive_abs, f"{datetime.date.today().year}年{client['name']}")


def unique_path(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def main():
    cfg = load_cfg()
    args = sys.argv[1:]

    if "--list-clients" in args:
        for c in cfg["clients"]:
            print(f"{c['name']:<8} → {c.get('dir') or '(自动新建 ' + str(datetime.date.today().year) + '年' + c['name'] + ')'}"
                  f"   别名: {', '.join(c['aliases'])}" + ("  [弱]" if c.get("weak") else ""))
        return

    apply_ = "--apply" in args
    fallback = "--fallback" in args      # 把待定件也收进「其他」
    force = "--force" in args
    root = cfg["root"]
    inbox_abs = os.path.join(root, cfg["inbox"])
    archive_abs = os.path.join(root, cfg["archive"])

    if not os.path.isdir(inbox_abs):
        sys.exit(f"找不到待归档目录：{inbox_abs}")

    files = scan_inbox(inbox_abs, cfg.get("ignore", []))
    if not files:
        print(f"「{cfg['inbox']}」是空的，没有要归档的东西。")
        return

    ph = check_placeholders(files)
    if ph:
        print("⚠ 以下文件是 iCloud 占位符或读不到内容，本体识别可能失效，建议先下载：")
        for x in ph:
            print(f"    {x}")
        print()
    cf = check_conflicts(inbox_abs)
    if cf:
        print("⚠ 检测到 iCloud 冲突副本，先处理再归档：")
        for x in cf:
            print(f"    {x}")
        print()

    plan, hold = [], []
    tpl_patterns = cfg.get("template_patterns", ["模板", "标准版", "甲方版"])
    for rel, full in files:
        client, why, lowconf = match_client(rel, cfg["clients"])
        ctext = ""
        parties = {}

        # 第一优先：当事人主体
        if client is None or lowconf:
            ctext = sniff_text(full)
            parties = extract_parties(ctext)
            pc, pwhy, plow = match_by_parties(parties, cfg["clients"])
            if pc is not None:
                client, why, lowconf = pc, pwhy, plow
            elif pwhy:
                client, why, lowconf = None, pwhy, True

        # 仍未命中 → 正文关键词兜底
        if client is None or lowconf:
            if ctext:
                hits = []
                minlen = cfg.get("min_content_alias_len", 3)
                for c in cfg["clients"]:
                    if c.get("weak"):
                        continue
                    for a in sorted(c["aliases"], key=len, reverse=True):
                        if len(a) < minlen:
                            continue
                        if a in ctext:
                            hits.append((c, a))
                            break
                names = {c["name"] for c, _ in hits}
                if len(names) == 1:
                    c0, a0 = hits[0]
                    client, why, lowconf = c0, f"正文含「{a0}」", False
                elif len(names) > 1:
                    client, why = None, "正文同时命中：" + "、".join(sorted(names))

        # 人工确认过的固定规则（文件名命中即归属），仅在前面都没判定出来时生效
        if client is None:
            for r in cfg.get("file_rules", []):
                if r["pattern"] in rel:
                    if r["client"] == "__TEMPLATE__":
                        client = {"name": "模板库", "dir": cfg.get("template_dir", "其他/模板库")}
                        why = f"固定规则「{r['pattern']}」→ 模板库"
                    elif r["client"].startswith("__DIR__:"):
                        sub = r["client"].split(":", 1)[1]
                        client = {"name": sub, "dir": sub}
                        why = f"固定规则「{r['pattern']}」→ {sub}"
                    elif r["client"] == "__OTHER__":
                        client = {"name": "其他", "dir": cfg.get("fallback_dir", "其他")}
                        why = f"固定规则「{r['pattern']}」→ 其他"
                    else:
                        tgt = next((x for x in cfg["clients"] if x["name"] == r["client"]), None)
                        if tgt:
                            client, why = tgt, f"固定规则「{r['pattern']}」"
                    lowconf = False
                    break

        # 仍未识别 → 看是不是空白模板（模板不归客户，归模板库）
        if client is None:
            tail = os.path.splitext(rel)[0].split(os.sep)[-1]
            if not has_parties(parties) and (
                    any(p in tail for p in tpl_patterns) or (ctext and ctext.count("____") >= 3)):
                client = {"name": "模板库", "dir": cfg.get("template_dir", "98.模板库")}
                why = "空白模板/标准版"

        if client is None:
            hold.append((rel, why))
        elif lowconf and not force:
            hold.append((rel, why + " → 建议 " + client["name"] + "（未移动）"))
        else:
            plan.append((rel, full, client, target_dir(archive_abs, client), why))

    print(f"待归档共 {len(files)} 份：可自动分派 {len(plan)} 份，需人工确认 {len(hold)} 份\n")
    if plan:
        print("【自动分派】")
        cur = None
        for rel, full, client, tdir, why in sorted(plan, key=lambda x: x[3]):
            if tdir != cur:
                cur = tdir
                print(f"\n  ▸ {os.path.basename(tdir)}/")
            print(f"      {rel}   ({why})")
    if hold:
        print("\n【需人工确认，暂不移动】")
        for rel, why in hold:
            print(f"      {rel}   ({why})")

    # 写报告
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report = os.path.join(LOG_DIR, f"{stamp}-{'apply' if apply_ else 'dryrun'}.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write(f"# 归档分派报告 {stamp}\n\n模式：{'实际执行' if apply_ else '演练（未移动）'}\n\n")
        f.write("## 自动分派\n\n")
        for rel, full, client, tdir, why in plan:
            f.write(f"- `{rel}` → `{os.path.basename(tdir)}/`（{why}）\n")
        f.write("\n## 待人工确认\n\n")
        for rel, why in hold:
            f.write(f"- `{rel}`（{why}）\n")
    print(f"\n报告：{report}")

    if not apply_:
        print("\n（演练模式，未移动任何文件。确认无误后加 --apply 执行）")
        return

    if fallback and hold:
        other = os.path.join(archive_abs, cfg.get("fallback_dir", "其他"))
        for rel, why in hold:
            plan.append((rel, os.path.join(inbox_abs, rel),
                         {"name": "其他", "dir": cfg.get("fallback_dir", "其他")},
                         other, f"兜底进其他（{why}）"))

    moved = 0
    for rel, full, client, tdir, why in plan:
        os.makedirs(tdir, exist_ok=True)
        dest = unique_path(os.path.join(tdir, os.path.basename(full)))
        shutil.move(full, dest)
        moved += 1
        print(f"✔ {rel} → {os.path.relpath(dest, root)}")

    # 清理空目录（只清 inbox 下变空的子目录）
    for dirpath, dirnames, filenames in os.walk(inbox_abs, topdown=False):
        if dirpath == inbox_abs:
            continue
        try:
            os.rmdir(dirpath)
            print(f"· 清空目录并移除：{os.path.relpath(dirpath, inbox_abs)}")
        except OSError:
            pass

    print(f"\n完成：移动 {moved} 份，待确认 {len(hold)} 份。")


if __name__ == "__main__":
    main()
