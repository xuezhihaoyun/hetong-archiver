#!/bin/bash
# hetong-archiver 一键部署：装到当前这台 Mac 上
# 用法：bash install.sh            正常部署
#       bash install.sh --no-link  只建配置，不装软链
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }
die()  { printf "  \033[31m✗\033[0m %s\n" "$1"; exit 1; }

echo "== hetong-archiver 部署 =="
echo "本体目录：$DIR"

# 1. python3
command -v python3 >/dev/null 2>&1 || die "找不到 python3（装 Xcode 命令行工具：xcode-select --install）"
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
ok "python3 $PYV"

# 2. 软链到各 harness 的 skills 目录
if [[ "${1:-}" != "--no-link" ]]; then
  for d in "$HOME/.claude/skills" "$HOME/.agents/skills" "$HOME/.codex/skills" "$HOME/.pi/agent/skills"; do
    mkdir -p "$d"
    ln -sfn "$DIR" "$d/hetong-archiver"
  done
  ok "已软链到 claude / agents / codex / pi 四个 skills 目录"
fi

# 3. 生成配置
cd "$DIR/scripts" || die "进不去 $DIR/scripts"
OUT=$(python3 init_config.py 2>&1) || { echo "$OUT"; die "init_config 失败（多半是找不到合同审查目录，见下方提示）"; }
echo "$OUT" | sed 's/^/    /'
ok "配置已生成"

# 4. 冒烟测试（只演练，绝不动文件）
echo
echo "== 冒烟测试（演练模式，不改任何文件）=="
python3 dispatch.py 2>&1 | head -8 | sed 's/^/    /'
echo
python3 rename.py "$(python3 -c "import cfg;print(cfg.load(require_root=True)['root'])")/中转" 2>&1 | head -4 | sed 's/^/    /'

echo
echo "== 完成 =="
echo "  以后把合同丢进「中转」，对 AI 说「归档」，它会先出演练表，你点头再执行。"
echo "  规则表（客户别名/固定规则）：$(python3 -c "import cfg;print(cfg.load(require_root=True)['_shared'])")"
