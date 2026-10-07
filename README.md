# skills

个人 Agent Skills 集合，遵循 [Agent Skills](https://skills.sh/) 规范。每个技能是一个自包含目录，包含 `SKILL.md`（元数据 + 指令）及所需脚本。

## 技能列表

| 技能 | 说明 | 依赖 |
| --- | --- | --- |
| [`git-summarize`](skills/git-summarize/SKILL.md) | 汇总当前项目改动 → 暂存并提交 → 推送远端 → 创建到 `master` 的 PR | `git`、[`gh`](https://cli.github.com/) |
| [`novel-downloader`](skills/novel-downloader/SKILL.md) | 从 80ge.info 搜索并下载 TXT 小说（搜索 → 选择 → 下载 → 解压重命名） | Python 3.10+、playwright、系统 Chrome/Edge |

## 通过 npx 安装（推荐）

使用官方的 Skills CLI 一键安装，无需预先安装任何工具（`npx` 会按需拉取）：

```bash
# 安装本仓库中的全部技能
npx skills add TimeOfPassage/skills

# 或只安装单个技能
npx skills add TimeOfPassage/skills@git-summarize
npx skills add TimeOfPassage/skills@novel-downloader
```

常用参数：

- `-g`：安装到用户级（全局）目录，对所有项目生效；
- `-y`：跳过交互确认，适合脚本化安装。

例如全局安装 `git-summarize`：

```bash
npx skills add TimeOfPassage/skills@git-summarize -g -y
```

其它相关命令：

```bash
npx skills find novel        # 搜索技能
npx skills check             # 检查已安装技能的更新
npx skills update            # 更新全部已安装技能
```

> 遥测：CLI 默认上报匿名安装数据用于排行榜；如需关闭，设置环境变量 `DISABLE_TELEMETRY=1`。

## 手动安装

若不使用 CLI，可直接将技能目录复制到 Agent 的技能目录（Zed 为用户级 `~/.agents/skills/`）：

```bash
git clone https://github.com/TimeOfPassage/skills.git
cp -R skills/skills/git-summarize ~/.agents/skills/
```

## 使用

安装后在支持 Agent Skills 的客户端（如 Zed）中直接以自然语言触发，例如：

- 「把这些改动提交并创建 PR」→ 触发 `git-summarize`
- 「下载小说《斗破苍穹》」→ 触发 `novel-downloader`

部分技能带有交互式参数，详见各自 `SKILL.md`，例如：

```bash
/git-summarize [branch-name] [base-branch]
```

## 目录结构

```
skills/
├── git-summarize/       # 纯指令型技能
│   └── SKILL.md
└── novel-downloader/    # 指令 + 脚本型技能
    ├── SKILL.md
    ├── download.sh
    ├── requirements.txt
    └── scripts/
```

## 免责声明

`novel-downloader` 仅用于个人学习与备份已获授权的内容，请遵守目标站点条款及当地法律法规。
