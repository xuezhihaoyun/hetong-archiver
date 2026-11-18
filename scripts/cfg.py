#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置加载：分两层。

  local.json   每台机器一份（只存 root 路径），放 skill 目录下
  <root>/.合同归档/config.json   规则表（客户别名、固定规则、模板目录），跟着 iCloud 走，
                                 两台机器共用同一份，改一处两边都生效
"""

import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.path.join(BASE, "local.json")
DEFAULT_ROOT = os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/📚合同审查")
SHARED_DIRNAME = ".合同归档"

DEFAULTS = {
    "inbox": "中转",
    "archive": "00.已经处理",
    "review_dir": "中转/_待定",
    "fallback_dir": "其他",
    "template_dir": "其他/模板库",
    "template_patterns": ["模板", "标准版", "甲方版"],
    "min_content_alias_len": 3,
    "ignore": [".DS_Store", "~$", ".tmp", ".crdownload"],
    "file_rules": [],
    "clients": [],
}


def find_root():
    env = os.environ.get("HETONG_ROOT")
    if env and os.path.isdir(env):
        return env
    if os.path.exists(LOCAL):
        with open(LOCAL, encoding="utf-8") as f:
            r = json.load(f).get("root")
        if r and os.path.isdir(os.path.expanduser(r)):
            return os.path.expanduser(r)
    if os.path.isdir(DEFAULT_ROOT):
        return DEFAULT_ROOT
    base = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs")
    if os.path.isdir(base):
        for d in os.listdir(base):
            if "合同审查" in d:
                return os.path.join(base, d)
    return ""


def shared_path(root):
    return os.path.join(root, SHARED_DIRNAME, "config.json")


def load(require_root=False):
    root = find_root()
    if require_root and not root:
        raise SystemExit("找不到合同审查根目录，先跑 scripts/init_config.py --root \"<路径>\"")
    cfg = dict(DEFAULTS)
    sp = shared_path(root) if root else ""
    if sp and os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            cfg.update(json.load(f))
    else:                                     # 还没初始化共享配置时退回示例
        ex = os.path.join(BASE, "config.example.json")
        if os.path.exists(ex):
            with open(ex, encoding="utf-8") as f:
                cfg.update(json.load(f))
    cfg["root"] = root
    cfg["_shared"] = sp
    return cfg


def save_shared(cfg, root=None):
    root = root or cfg["root"]
    sp = shared_path(root)
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    out = {k: v for k, v in cfg.items() if not k.startswith("_") and k != "root"}
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return sp


def save_local(root):
    with open(LOCAL, "w", encoding="utf-8") as f:
        json.dump({"root": root}, f, ensure_ascii=False, indent=2)
    return LOCAL
