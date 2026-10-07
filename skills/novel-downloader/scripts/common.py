#!/usr/bin/env python3
"""novel-downloader 共享工具：站点常量、浏览器启动/附加、URL/标题处理。"""
import os
import re
import sys
from pathlib import Path

SITE_URL = "http://www.80ge.info"
SEARCH_URL = f"{SITE_URL}/modules/article/search.php"

# 持久化浏览器配置目录：复用登录态与 Cloudflare 认证（cf_clearance）Cookie。
DEFAULT_PROFILE_DIR = Path(
    os.environ.get(
        "NOVEL_DOWNLOADER_PROFILE",
        Path.home() / ".novel-downloader" / "profile",
    )
)

# 浏览器通道优先级：只使用系统已安装的浏览器（Chrome，其次 Edge）。
# 如需 Playwright 自带 Chromium，请显式使用 --channel chromium（需先 playwright install chromium）。
CHANNEL_CANDIDATES = ("chrome", "msedge")

# Cloudflare 会拦截“全新空白 profile”，因此可通过本机 Chrome 真实配置或 CDP 附加来通过验证。
CDP_DEFAULT_URL = "http://127.0.0.1:9222"


def _real_chrome_profile():
    """本机 Chrome 的真实用户数据目录。"""
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Google/Chrome"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "Google/Chrome/User Data" if base else None
    return Path.home() / ".config/google-chrome"


REAL_CHROME_PROFILE = _real_chrome_profile()


def chrome_download_dir():
    """读取 Chrome 设置的默认下载目录，回退到 ~/Downloads。"""
    import json

    if sys.platform == "darwin":
        prefs = Path.home() / "Library/Application Support/Google/Chrome/Default/Preferences"
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        prefs = Path(base) / "Google/Chrome/User Data/Default/Preferences" if base else None
    else:
        prefs = Path.home() / ".config/google-chrome/Default/Preferences"

    for candidate in (prefs,):
        if not candidate:
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        directory = data.get("download", {}).get("default_directory") or data.get(
            "savefile", {}
        ).get("default_directory")
        if directory:
            return Path(os.path.expanduser(directory))
    return Path.home() / "Downloads"

INSTALL_HINT = (
    "未检测到可用的系统浏览器。请先安装 Google Chrome 或 Microsoft Edge 后重试：\n"
    "  - Google Chrome:  https://www.google.com/chrome/\n"
    "  - Microsoft Edge:  https://www.microsoft.com/edge\n"
    "或改用 Playwright 自带 Chromium（需先下载）：\n"
    "  playwright install chromium\n"
    "  然后在命令中加上 --channel chromium"
)

QUIT_CHROME_HINT = (
    "使用本机真实配置需要 Chrome 已完全退出（⌘Q）。\n"
    "注意：Chrome 136+ 已禁止对默认用户目录开启远程调试端口，"
    "因此请勿使用 --remote-debugging-port，直接使用 --use-real-profile 即可。"
)


def log(message):
    """输出进度信息到 stderr，避免干扰 stdout 的结构化结果。"""
    print(message, file=sys.stderr, flush=True)


def _is_missing_browser_error(exc):
    """判断异常是否为“浏览器未安装/可执行文件不存在”。"""
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "doesn't exist",
            "does not exist",
            "not found",
            "no such file",
            "cannot find",
        )
    )


def _resolve_channels(explicit=None):
    """确定候选浏览器通道。可用 --channel 或环境变量 NOVEL_DOWNLOADER_CHANNEL 覆盖。"""
    chosen = explicit or os.environ.get("NOVEL_DOWNLOADER_CHANNEL")
    if chosen:
        return (chosen,)
    return CHANNEL_CANDIDATES


def launch_context(playwright, *, headless=False, profile_dir=None, channel=None):
    """启动持久化浏览器上下文（使用系统已安装的浏览器）。

    Args:
        playwright: sync_playwright() 返回的 Playwright 实例。
        headless: 是否无头模式。CF 真人认证需要可见浏览器，默认有头。
        profile_dir: 用户数据目录，默认 ~/.novel-downloader/profile。
        channel: 指定浏览器通道，如 "chrome" / "msedge" / "chromium"；None 表示自动。

    Returns:
        BrowserContext（持久化上下文）。

    Raises:
        RuntimeError: 未安装 Chrome/Edge（或其他启动失败）时抛出。
    """
    profile = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
    profile.mkdir(parents=True, exist_ok=True)

    tried = []
    for candidate in _resolve_channels(channel):
        tried.append(candidate)
        options = {
            "user_data_dir": str(profile),
            "headless": headless,
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 900},
            "locale": "zh-CN",
            # 隐藏自动化特征，降低被 Cloudflare 直接拦截的概率。
            "args": ["--disable-blink-features=AutomationControlled"],
            # 去掉 --enable-automation，避免出现“Chrome 正受自动测试软件控制”横幅。
            "ignore_default_args": ["--enable-automation"],
        }
        if candidate:
            options["channel"] = candidate
        # 仅在显式指定时覆盖 UA，避免 UA 与实际系统不一致而触发风控。
        user_agent = os.environ.get("NOVEL_DOWNLOADER_UA")
        if user_agent:
            options["user_agent"] = user_agent
        try:
            return playwright.chromium.launch_persistent_context(**options)
        except Exception as exc:  # noqa: BLE001
            if not _is_missing_browser_error(exc):
                # 浏览器存在但启动失败（如 profile 被占用），直接抛出真实错误。
                raise RuntimeError(
                    f"浏览器启动失败（channel={candidate or 'default'}）：{exc}"
                ) from exc
            log(f"未找到浏览器通道 {candidate}，尝试下一个 ...")

    raise RuntimeError(f"{'，'.join(tried)} 均不可用。")


def ensure_system_browser(playwright, *, headless=False, profile_dir=None, channel=None):
    """带友好提示的启动封装：未安装系统浏览器时提示用户安装。"""
    try:
        return launch_context(
            playwright,
            headless=headless,
            profile_dir=profile_dir,
            channel=channel,
        )
    except RuntimeError as exc:
        raise RuntimeError(f"{exc}\n\n{INSTALL_HINT}") from None


def connect_over_cdp(playwright, cdp_url=CDP_DEFAULT_URL):
    """附加到已带调试端口启动的浏览器，复用其真实会话（推荐用于通过 CF）。"""
    browser = playwright.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return context


def open_browser(
    playwright,
    *,
    headless=False,
    profile_dir=None,
    channel=None,
    cdp_url=None,
    use_real_profile=False,
):
    """统一的浏览器打开入口。

    优先级：--cdp-url > --use-real-profile > 默认（独立 profile）。

    Returns:
        (context, close_fn)：close_fn 用于收尾；CDP 附加时为 no-op（不关闭用户浏览器）。
    """
    if cdp_url:
        context = connect_over_cdp(playwright, cdp_url)
        return context, (lambda: None)

    if use_real_profile:
        if not REAL_CHROME_PROFILE or not Path(REAL_CHROME_PROFILE).exists():
            raise RuntimeError("未找到本机 Chrome 真实配置目录，无法使用 --use-real-profile。")
        try:
            context = launch_context(
                playwright,
                headless=headless,
                profile_dir=str(REAL_CHROME_PROFILE),
                channel=channel or "chrome",
            )
        except RuntimeError as exc:
            raise RuntimeError(f"{exc}\n\n{QUIT_CHROME_HINT}") from None
        return context, context.close

    context = ensure_system_browser(
        playwright, headless=headless, profile_dir=profile_dir, channel=channel
    )
    return context, context.close


def open_in_default_browser(url):
    """用系统默认浏览器（真人浏览器）打开链接。

    先把 URL 中的非 ASCII 路径按 UTF-8 百分号编码，避免 macOS `open`/osascript
    传参时按错误编码处理，导致下载文件名乱码（如 我真没想重生啊 -> Œ“’Ê√ªœÎ÷ÿ…˙∞°）。
    """
    import webbrowser
    from urllib.parse import quote, urlsplit, urlunsplit

    parts = urlsplit(url)
    # 保留已有的 %XX 与路径分隔符，仅编码非 ASCII 与空格
    path = quote(parts.path, safe="/%")
    query = quote(parts.query, safe="=&%?:/")
    safe_url = urlunsplit(
        (parts.scheme, parts.netloc, path, query, parts.fragment)
    )
    return webbrowser.open(safe_url)


def context_user_agent(context, default=None):
    """读取浏览器实际 UA（用于兜底请求与 CF 认证保持一致）。"""
    try:
        page = context.pages[0] if context.pages else context.new_page()
        return page.evaluate("navigator.userAgent") or default
    except Exception:
        return default


def first_page(context):
    """返回上下文中的第一个页面，没有则新建。"""
    return context.pages[0] if context.pages else context.new_page()


def abs_url(href):
    """将相对链接补全为绝对链接。"""
    if not href:
        return href
    if href.startswith("//"):
        return "http:" + href
    if href.startswith("/"):
        return SITE_URL + href
    if not href.startswith("http"):
        return SITE_URL + "/" + href.lstrip("/")
    return href


def clean_title(raw):
    """从搜索结果标题中提取书名，如 `《斗破苍穹》TXT下载` -> `斗破苍穹`。"""
    if not raw:
        return raw
    title = " ".join(raw.split())
    match = re.match(r"^《(.+?)》", title)
    if match:
        return match.group(1).strip()
    title = re.sub(
        r"(?i)\s*(txt全集下载|txt下载|全集下载|下载)$", "", title
    ).strip()
    return title or raw.strip()


def sanitize_filename(name):
    """移除文件名中的非法字符。"""
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name.strip() or "novel"
