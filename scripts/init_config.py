#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""初始化 / 重建配置（换机器、新增客户文件夹后跑一次）。

产物两个：
  local.json                      每台机器一份，只记合同根目录在哪
  <root>/.合同归档/config.json     规则表（客户别名、固定规则），跟 iCloud 走，两台机器共用

用法：
  python3 init_config.py                     # 自动探测根目录
  python3 init_config.py --root "<路径>"
  python3 init_config.py --print             # 只看结果不写
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg as cfgmod

BASE = cfgmod.BASE
DROP_PREFIX = re.compile(r"^(?:\d{4}年|🔥|【[^】]*】)+")


def guess_client(folder):
    name = DROP_PREFIX.sub("", folder)
    for suf in ("审核回复过的合同", "审核回复"):
        if name.endswith(suf) and len(name) > len(suf):
            name = name[: -len(suf)]
    return name or folder


def build(root, old):
    archive = os.path.join(root, "00.已经处理")
    if not os.path.isdir(archive):
        raise SystemExit(f"找不到归档目录：{archive}")

    old_by_name = {c["name"]: c for c in old.get("clients", [])}
    clients, have = [], set()
    for folder in sorted(os.listdir(archive)):
        p = os.path.join(archive, folder)
        if not os.path.isdir(p) or folder.startswith(".") or folder == "其他":
            continue
        name = guess_client(folder)
        prev = old_by_name.get(name, {})
        aliases = list(prev.get("aliases") or [name])
        if folder not in aliases and folder != name:
            aliases.append(folder)
        entry = {"name": name, "aliases": aliases, "dir": folder}
        if prev.get("weak"):
            entry["weak"] = True
        clients.append(entry)
        have.add(name)

    # 没有独立文件夹、但指向已有文件夹的客户（弱别名，如 齐心集团 → 坪山实验）
    for name, prev in old_by_name.items():
        if name in have:
            continue
        d = prev.get("dir")
        if d and os.path.isdir(os.path.join(archive, d)):
            clients.append(prev)

    out = {k: old.get(k, v) for k, v in cfgmod.DEFAULTS.items() if k != "clients"}
    out["clients"] = clients
    return out


def main():
    if "--root" in sys.argv:
        root = os.path.abspath(os.path.expanduser(sys.argv[sys.argv.index("--root") + 1]))
    else:
        root = cfgmod.find_root()
    if not root:
        sys.exit("找不到合同审查目录。请用：python3 init_config.py --root \"<路径>\"")

    # 老配置来源：skill 内 config.json（1.0 遗留）与示例配置，示例打底、老配置覆盖
    old = {}
    for src in (os.path.join(BASE, "config.example.json"), os.path.join(BASE, "config.json")):
        if not os.path.exists(src):
            continue
        with open(src, encoding="utf-8") as f:
            cur = json.load(f)
        by_name = {c["name"]: c for c in old.get("clients", [])}
        for c in cur.get("clients", []):
            by_name[c["name"]] = {**by_name.get(c["name"], {}), **c}
        old.update({k: v for k, v in cur.items() if k != "clients"})
        old["clients"] = list(by_name.values())

    shared = build(root, old)

    if "--print" in sys.argv:
        shared["root"] = root
        print(json.dumps(shared, ensure_ascii=False, indent=2))
        return

    cfgmod.save_local(root)
    sp = cfgmod.save_shared(shared, root)
    print(f"根目录：{root}")
    print(f"客户 {len(shared['clients'])} 个：" + "、".join(c["name"] for c in shared["clients"]))
    print(f"固定规则 {len(shared['file_rules'])} 条")
    print(f"本机配置：{cfgmod.LOCAL}")
    print(f"共享规则：{sp}（跟 iCloud 同步，两台机器共用）")
    print("别名、规则以后直接改共享 config.json，或在会话里让我改。")


if __name__ == "__main__":
    main()
