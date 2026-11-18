#!/bin/bash
# 装「自动归档」：往 中转 里一丢文件，就自动改名归档并弹通知
# 用法：bash install_watcher.sh            安装/更新
#       bash install_watcher.sh --uninstall 卸载
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.xuezhihaoyun.hetong-autuarchive"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
die()  { printf "  \033[31m✗\033[0m %s\n" "$1"; exit 1; }

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl unload "$PLIST" 2>/dev/null
  rm -f "$PLIST"
  ok "已卸载自动归档（文件仍在，删掉中转里的东西不会再自动跑）"
  exit 0
fi

ROOT=$(cd "$DIR/scripts" && python3 -c "import cfg;print(cfg.load()['root'])" 2>/dev/null)
[[ -n "$ROOT" && -d "$ROOT" ]] || die "找不到合同审查目录，先跑 bash install.sh"
INBOX="$ROOT/中转"
[[ -d "$INBOX" ]] || die "找不到 $INBOX"

mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$DIR/scripts/auto_archive.py</string>
  </array>
  <key>WatchPaths</key>
  <array><string>$INBOX</string></array>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$DIR/logs/auto.out.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/auto.err.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>HETONG_ROOT</key><string>$ROOT</string></dict>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" || die "launchctl load 失败"
ok "已安装并启动：$LABEL"
echo
echo "  监听目录：$INBOX"
echo "  行为：丢进去 → 等几秒稳定 → 自动改名并归到客户目录 → 弹通知告诉你归到哪几家、剩几份要你看"
echo "  判不出客户的件留在 中转 不动，通知里会点出来"
echo "  日志：$DIR/自动归档日志.md（脚本运行输出：$DIR/logs/）"
echo
echo "  卸载：bash install_watcher.sh --uninstall"
echo "  先手测一次：python3 scripts/auto_archive.py"
