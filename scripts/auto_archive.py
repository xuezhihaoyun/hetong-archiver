#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动归档：文件落进「中转」就自动改名、归位，完成后弹通知。

由 launchd 监听「中转」目录触发（见 install_watcher.sh）。
流程：等文件稳定 → 强制下载 iCloud 占位符 → 改名 → 归档 → 弹通知 + 写日志。

安全：
  · 只动高置信度的件；判不出的留在 中转 原地，通知里列出来
  · 不删任何文件；重名加 -2
  · 加锁，重复触发不会并发跑
"""

import datetime
import json
import os
import subprocess
import sys
import time

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
import cfg as cfgmod

LOCK = os.path.join(BASE, ".auto_archive.lock")
LOG = os.path.join(BASE, "自动归档日志.md")
STABLE_SECONDS = 4
MAX_WAIT = 60


def notify(title, msg, sound="Glass"):
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification {json.dumps(msg)} with title {json.dumps(title)} '
             f'sound name "{sound}"'],
            capture_output=True, timeout=10)
    except Exception:
        pass


def acquire_lock():
    if os.path.exists(LOCK):
        try:
            age = time.time() - os.path.getmtime(LOCK)
            if age < 300:                     # 5 分钟内的锁视为仍在运行
                return False
        except OSError:
            pass
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


def wait_stable(files):
    """等文件不再变化（iCloud 拷贝中可能出现半截文件）。"""
    start = time.time()
    last = None
    while time.time() - start < MAX_WAIT:
        snap = {}
        for f in files:
            try:
                st = os.stat(f)
                snap[f] = (st.st_size, int(st.st_mtime))
            except OSError:
                pass
        if snap == last and snap:
            time.sleep(STABLE_SECONDS)
            return True
        last = snap
        time.sleep(2)
    return False


def ensure_downloaded(files):
    """iCloud 占位符强制下载，否则读不到正文，主体识别会失效。"""
    for f in files:
        try:
            subprocess.run(["brctl", "download", f], capture_output=True, timeout=60)
        except Exception:
            pass


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, cwd=SCRIPTS,
                       capture_output=True, text=True, timeout=600)
    return r.returncode, r.stdout + r.stderr


def main():
    if not acquire_lock():
        return
    try:
        c = cfgmod.load(require_root=False)
        root = c.get("root")
        if not root:
            notify("合同归档 · 未运行", "找不到合同审查目录，先跑 install.sh")
            return
        inbox = os.path.join(root, c["inbox"])
        files = []
        for dp, dn, fn in os.walk(inbox):
            dn[:] = [d for d in dn if not d.startswith(".")]
            for f in fn:
                if f.startswith(".") or f == ".DS_Store":
                    continue
                files.append(os.path.join(dp, f))
        if not files:
            return

        wait_stable(files)
        ensure_downloaded(files)

        rc1, out1 = run(["rename.py", inbox, "--apply"])
        rc2, out2 = run(["dispatch.py", "--apply"])

        # 统计结果
        archived = [l for l in out2.splitlines() if l.startswith("✔")]
        stays = [l for l in out2.splitlines() if l.strip().startswith("·") or "待人工确认" in l]
        renamed = out1.split("已改名")[-1].strip().split("份")[0] if "已改名" in out1 else "0"

        left = []
        for dp, dn, fn in os.walk(inbox):
            for f in fn:
                if not f.startswith(".") and f != ".DS_Store":
                    left.append(f)

        if archived:
            groups = {}
            for l in archived:
                dest = l.split("→")[-1].strip()
                folder = dest.split("/")[1] if len(dest.split("/")) > 2 else dest.split("/")[0]
                groups[folder] = groups.get(folder, 0) + 1
            summary = "、".join(f"{k} {v}份" for k, v in groups.items())
            title = f"合同已归档 {len(archived)} 份"
            msg = summary + (f"；{len(left)} 份需你看一眼" if left else "")
        else:
            title = "中转有新文件，但没归档"
            msg = f"{len(left)} 份都判不出客户，等你处理"

        notify(title, msg)

        with open(LOG, "a", encoding="utf-8") as f:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n## {ts}\n\n- 改名：{renamed} 份\n")
            for l in archived:
                f.write(f"- {l.lstrip('✔ ').strip()}\n")
            if left:
                f.write("- 留在中转：" + "、".join(left) + "\n")
    finally:
        release_lock()


if __name__ == "__main__":
    main()
