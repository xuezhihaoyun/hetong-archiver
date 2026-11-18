# 给 AI 的部署说明（直接把整包丢给它，让它照做）

你手上是一个 macOS 上的合同归档 Skill 压缩包 `hetong-archiver`。
目标：把它装到**这台 Mac**上，让 Claude Code / Codex / pi 等 harness 都能调用，
并能把 `📚合同审查/中转` 里的合同按客户自动归档、按统一规则改名。

## 首选：从 GitHub 装

```bash
mkdir -p ~/claude-code-项目工作区/skills && cd ~/claude-code-项目工作区/skills
git clone https://github.com/xuezhihaoyun/hetong-archiver.git
cd hetong-archiver && bash install.sh
```

私有仓库，需要那台机器上 `gh auth login` 过（或配好 SSH key）。

## 备选：从压缩包装（离线/没配 git 时）

```bash
cd <解压后的 hetong-archiver 目录>
bash install.sh
```

脚本会依次做四件事，任何一步失败都会打印原因并退出：

1. 检查 `python3`（本机自带即可，无 pip 依赖）
2. 把本体软链到 `~/.claude/skills`、`~/.agents/skills`、`~/.codex/skills`、`~/.pi/agent/skills`
3. 生成两份配置
   - `local.json`（本机，只记合同根目录路径）
   - `<合同根目录>/.合同归档/config.json`（规则表，跟 iCloud 走，两台机器共用）
4. 冒烟测试：跑 `dispatch.py` 和 `rename.py` 的**演练模式**，只读不动文件

## 如果报"找不到合同审查目录"

说明这台机器上 iCloud 路径不是默认位置。手工指定：

```bash
cd scripts
python3 init_config.py --root "/实际/路径/📚合同审查"
```

路径确认方法：

```bash
find ~/Library/Mobile\ Documents -maxdepth 3 -name "*合同审查*" -type d
```

## 部署后自检（三条必须都过）

```bash
cd scripts
python3 cfg.py 2>/dev/null; python3 -c "import cfg;c=cfg.load(require_root=True);print(c['root']);print(len(c['clients']),'个客户')"
python3 dispatch.py            # 应输出「待归档共 N 份」或「中转是空的」
python3 rename.py "<root>/中转" # 应输出「共 N 份，其中建议改名 M 份」
```

## 硬约束，不许违反

- **只跑演练，不要加 `--apply`**。归档和改名必须由叶律师看过演练结果并明确同意后再执行。
- **不许删任何文件**。脚本自身也不删（重名加 `-2`），AI 更不许手工清理。
- 判不出客户的件会留在 `中转` 原地并列入"待人工确认"，**不要为了清空目录硬塞进别的文件夹**。
  叶律师说"丢其他"时才允许用 `--fallback`。
- 客户归属有歧义（两个当事人分属不同客户、或不确定我方是谁）→ 问人，不要猜。

## 装完之后怎么用

对 AI 说「归档」，它的标准动作是：

1. `python3 scripts/dispatch.py` → 出「自动分派／待人工确认」两张清单
2. 把清单压缩成表格报给叶律师，逐条问待定项
3. 得到确认后 `--apply` 执行
4. 把这一轮人工判定过的归属写回共享 `config.json` 的 `file_rules` 或客户的 `aliases`（沉淀规则）

## 目录说明

```
SKILL.md            工作流与红线（AI 的入口，先读这个）
install.sh          一键部署
换机安装.md          手工步骤与多机注意事项
scripts/cfg.py      配置加载（local.json + iCloud 共享配置）
scripts/init_config.py  扫 00.已经处理 反推客户名单
scripts/dispatch.py     归档分派（默认演练）
scripts/rename.py       统一命名（默认演练）
scripts/parties.py      合同当事人主体抽取
references/命名规则.md   命名口径
归档日志/ 改名台账/      历史记录（换机后各记各的，不冲突）
```
