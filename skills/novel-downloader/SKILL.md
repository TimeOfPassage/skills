---
name: novel-downloader
description: 从 80ge.info 搜索并下载 TXT 格式小说。当用户提供小说名称并希望下载到本地时使用。支持搜索、选择、下载、解压 ZIP 并重命名 TXT 文件。
compatibility: Requires Python 3.10+, playwright (+ chromium), 有头浏览器环境
metadata:
  author: charles.h
  version: "2.0"
---

# Novel Downloader

从 80ge.info 搜索并下载 TXT 格式小说到本地。

## 环境准备

```bash
pip install -r requirements.txt
```

> 默认**直接操作用户电脑上已安装的浏览器**（优先 Google Chrome，其次 Microsoft Edge），
> 因此**无需** `playwright install chromium`。
> 若机器未安装 Chrome/Edge，脚本会**提示用户安装**（含下载地址），不会静默使用自带 Chromium。
> 如需回退到自带 Chromium：先 `playwright install chromium`，再加 `--channel chromium`。

> 下载环节可能出现 Cloudflare 真人认证，因此需在**有图形界面**的环境运行，并保持浏览器窗口可见（默认有头模式）。

## 快捷用法（推荐）

在**自己的交互式终端**中一条命令搞定（搜索 → 选择 → 打开浏览器 → 回车确认 → 处理）：

```bash
./download.sh "从今天开始做藩王"
```

流程：

1. 自动搜索并列出候选，输入序号选择；
2. 自动解析下载地址并打开默认浏览器；
3. 你在浏览器完成 Cloudflare 认证并下载，然后回车确认；
4. 自动识别文件（兼容乱码文件名）→ 解压 → 重命名为 `书名.txt` → 删除 zip，输出最终路径。

可选环境变量：`PYTHON=python3`、`OUTPUT_DIR=~/Downloads/novels`。

> 需要 TTY 交互；Agent 分步编排请用下面的 `search_novels.py` / `download_novel.py`。

## 工作流程（Agent 分步编排）

1. **搜索**：调用 `scripts/search_novels.py --name "小说名"`，得到前 10 条结果（JSON）。
2. **呈现与选择**：把结果整理成列表展示给用户（序号、书名、作者、简介、详情页 URL），请用户选择其中之一。**必须等待用户明确选择后再进行下一步。**
3. **解析下载地址（交接模式）**：用选中结果的 `url` 作为 `--detail-url`，书名作为 `--name`，调用：
   `scripts/download_novel.py --detail-url <URL> --name "书名" --output-dir <目录> --handoff`
   脚本会：打开详情页 → 点击 **[TXT下载列表]** → 在 **普通下载** 选 **【电脑】** 地址 → 用**系统默认（真人）浏览器**打开该地址 → **交还控制权并退出**（stdout 输出下载地址）。
4. **等用户确认**：告知用户“请在浏览器完成 Cloudflare 认证并下载”，**等用户确认已下载完成**后再继续。
5. **处理文件**：调用 `scripts/download_novel.py --name "书名" --output-dir <目录> --from-downloads`。
   脚本会扫描下载目录（自动读取 Chrome 设置），取最新的 zip/txt，解压 → 按书名重命名 TXT → 删除 ZIP，stdout 输出最终 TXT 路径。

> 备选：加 `--wait` 可让 `--handoff` 打开浏览器后自行轮询文件落盘并直接处理（不交还控制权）。
> 若已知文件路径，也可用 `--from-file <路径>` 直接处理。

## 搜索结果展示模板

搜索脚本返回 JSON 后，按下表整理为带序号的候选列表展示给用户，再请其选择：

```markdown
在 80ge.info 找到以下与「<关键词>」相关的小说，请回复序号选择要下载的一本：

| # | 书名 | 作者 | 分类 | 状态 | 简介 |
| --- | --- | --- | --- | --- | --- |
| 1 | 斗破苍穹 | 天蚕土豆 | 玄幻异界 | 已完成 | （简介摘要…） |
| 2 | 穿越斗破苍穹 | 午时一刻 | 虚拟网游 | 已完成 | （简介摘要…） |

> 也可以回复书名或序号，例如「2」或「穿越斗破苍穹」。
```

展示规则：

- 保留 `index` 作为序号，用户回复序号即对应结果的 `url`。
- `intro` 过长时截断到约 40–60 字并加省略号，避免刷屏。
- `author`/`category`/`intro` 为空时用 `-` 占位，不要编造。
- 仅在用户明确选定后，才用该结果的 `url` 与 `title` 进入下载步骤。

## 脚本说明

### download.sh / scripts/quick_download.py

交互式一键脚本：搜索 → 选择 → 交接浏览器 → 回车确认 → 处理。参数：`<书名>`（可省略，运行后提示输入）、`--limit`、`--output-dir`、`--download-dir`、`--channel`、`--profile-dir`。

### scripts/search_novels.py

参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--name` | 是 | 小说名称或作者 |
| `--limit` | 否 | 返回结果数量，默认 10 |
| `--headless` | 否 | 无头模式（默认有头；搜索一般无需 CF 认证，可用无头） |
| `--profile-dir` | 否 | 浏览器用户数据目录，默认 `~/.novel-downloader/profile` |
| `--channel` | 否 | 浏览器通道（`chrome`/`msedge`），默认自动优先系统 Chrome |

输出：JSON 数组，字段 `index/title/author/category/status/update/clicks/intro/url`。

```bash
python3 scripts/search_novels.py --name "斗破苍穹"
```

### scripts/download_novel.py

参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--detail-url` | 是 | 详情页 URL（来自搜索结果 `url`） |
| `--name` | 是 | 小说名称，用于重命名 TXT |
| `--output-dir` | 否 | 输出目录，默认 `./novels` |
| `--cf-timeout` | 否 | 等待 CF 认证/下载的秒数，默认 180 |
| `--headless` | 否 | 无头模式（CF 认证需有头，一般不要开启） |
| `--profile-dir` | 否 | 浏览器用户数据目录 |
| `--channel` | 否 | 浏览器通道（`chrome`/`msedge`），默认自动优先系统 Chrome |
| `--handoff` | 否 | **交接模式（推荐）**：解析下载地址并用系统默认浏览器打开，随后交还控制权 |
| `--wait` | 否 | 交接模式下等待文件落盘后自动处理（默认打开后即交还） |
| `--from-downloads` | 否 | 取下载目录中最新的 zip/txt 并处理（自动探测 Chrome 下载目录） |
| `--max-age` | 否 | 配合 `--from-downloads`：仅取该分钟数内修改过的文件，默认 120 |
| `--download-dir` | 否 | 下载目录（默认读取 Chrome 设置，回退 `~/Downloads`） |
| `--from-file` | 否 | 直接处理已下载的 zip/txt（跳过浏览器），适合用户已手动下载的情况 |

输出：处理后 TXT 的绝对路径。

```bash
python3 scripts/download_novel.py \
  --detail-url "http://www.80ge.info/txtxz/426.html" \
  --name "斗破苍穹" \
  --output-dir ./novels
```

## 下载文件名乱码说明

根因：`webbrowser.open`（macOS 走 `open`/osascript）传递**非 ASCII 路径**时按错误编码处理，
使浏览器请求的路径变成错误字节，服务端据此回显的文件名也随之乱码
（如 `我真没想重生啊.zip` → `Œ“’Ê√ªœÎ÷ÿ…˙∞°.zip`）。

修复：打开前先对 URL 路径做 **UTF-8 百分号编码**（见 `common.open_in_default_browser`），
下载文件名即正确。`--from-downloads` / `--from-file` 仍按“最新文件”识别作为兜底，
并最终统一按 `--name` 输出 `书名.txt`。

## Cloudflare 下载地址说明

下载域名 `dz.80ge.info` 使用 Cloudflare Turnstile 人机验证。实测结论：

- **自动化浏览器（含全新空白 profile）无法通过验证**。
- **Chrome 136+ 禁止对默认用户目录开启远程调试**（`--remote-debugging-port` 和 Playwright 的调试管道都被禁），
  因此 `--use-real-profile` / `--cdp-url` 在 Chrome 136+ 上不可用。
- 因此推荐 **`--handoff` 交接模式**：脚本用无头浏览器解析出下载地址，再用**系统默认（真人）浏览器**打开下载；
  由用户完成 CF 认证并下载（真人浏览器天然可过），脚本最后自动解压、重命名、删除 ZIP。

## 注意事项

- 默认使用系统已安装浏览器（Chrome/Edge）；**未安装时会明确提示用户安装**，不会静默改用自带 Chromium。
  可用 `--channel` 或环境变量 `NOVEL_DOWNLOADER_CHANNEL` 指定通道（如 `chromium`）。
- 不强制覆盖 User-Agent，保持与实际系统一致，以避免 Cloudflare 风控；如需自定义 UA，可设
  环境变量 `NOVEL_DOWNLOADER_UA`。
- 浏览器用户数据目录被持久化复用，Cloudflare 认证与站点 Cookie 在多次调用间保留，可减少重复认证。
- `download_novel.py` 在等待 CF 认证时会阻塞（最长 `--cf-timeout` 秒），这是预期行为：用户需在此期间于浏览器中完成认证。
- 同一时间只应有一个脚本实例使用该用户数据目录，避免 profile 被占用。
- 仅用于个人学习/备份已获授权的内容，请遵守目标站点条款与当地法律。
