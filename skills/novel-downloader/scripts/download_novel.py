#!/usr/bin/env python3
"""从详情页获取下载地址、交由用户完成 CF 认证、下载并处理小说文件。

流程:
    1. 打开小说详情页
    2. 点击 [TXT下载列表]（通常打开新标签页）
    3. 在“普通下载”中选择【电脑】地址，得到下载 URL
    4. 浏览器保持可见，交由用户完成 Cloudflare 真人认证
    5. 下载 ZIP -> 解压 -> 按小说名重命名 TXT -> 删除 ZIP

用法:
    python3 download_novel.py --detail-url <URL> --name "斗破苍穹" [--output-dir ./novels]
                             [--cf-timeout 180] [--headless] [--profile-dir DIR]

输出（stdout）:
    处理后 TXT 文件的绝对路径。
"""
import argparse
import shutil
import sys
import time
import zipfile
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from common import (
    SITE_URL,
    abs_url,
    chrome_download_dir,
    context_user_agent,
    log,
    open_browser,
    open_in_default_browser,
    sanitize_filename,
)

DOWNLOAD_LIST_SELECTORS = (
    "a#read_book",
    "a:has-text('TXT下载列表')",
    "a:has-text('下载列表')",
)


def _wait_for_download_list_page(context, origin_page, existing_pages, timeout=15):
    """等待 [TXT下载列表] 触发的新标签页或同页跳转。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        new_pages = [pg for pg in context.pages if pg not in existing_pages]
        if new_pages:
            return new_pages[0]
        if "down.html" in origin_page.url:
            return origin_page
        time.sleep(0.2)
    return origin_page


def _find_common_download_anchors(page):
    """定位“普通下载”区块内的下载链接。"""
    for box in page.query_selector_all(".wanpan_url"):
        title = box.query_selector(".pan_sm")
        if title and "普通下载" in title.inner_text():
            return box.query_selector_all(".pan_url a")
    # 回退：整块下载区域的链接
    return page.query_selector_all(".down_url_txt a")


def resolve_download_url(context, detail_url):
    """打开详情页（新标签页）-> 下载列表 -> 返回“普通下载/电脑”下载地址。"""
    page = context.new_page()
    page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)

    entry = None
    for selector in DOWNLOAD_LIST_SELECTORS:
        entry = page.query_selector(selector)
        if entry:
            break
    if not entry:
        raise RuntimeError("详情页未找到 [TXT下载列表] 入口")

    existing_pages = set(context.pages)
    entry.click()
    down_page = _wait_for_download_list_page(context, page, existing_pages)
    down_page.wait_for_load_state("domcontentloaded")
    down_page.wait_for_selector(".wanpan_url, .down_url_txt", timeout=30000)

    anchors = _find_common_download_anchors(down_page)
    if not anchors:
        raise RuntimeError("下载列表页未找到任何下载地址")

    # 【电脑】链接指向 .zip，【手机】链接指向 .txt，优先取 zip。
    url = None
    for anchor in anchors:
        href = abs_url(anchor.get_attribute("href"))
        if href and href.lower().endswith(".zip"):
            url = href
            break
    if not url:
        url = abs_url(anchors[0].get_attribute("href"))
    if not url:
        raise RuntimeError("下载地址为空")
    return url


def _download_via_request(context, url, raw_path):
    """兜底：用户已通过 CF 认证后，用上下文 Cookie 直接请求文件。"""
    headers = {"Referer": SITE_URL + "/"}
    user_agent = context_user_agent(context)
    if user_agent:
        headers["User-Agent"] = user_agent
    response = context.request.get(url, headers=headers, timeout=120000)
    if not response.ok:
        raise RuntimeError(
            f"下载失败：HTTP {response.status}（Cloudflare 认证可能未通过）"
        )
    body = response.body()
    if body.lstrip()[:1] == b"<":
        raise RuntimeError("下载得到的是网页而非文件，Cloudflare 认证可能未通过")
    raw_path.write_bytes(body)
    return raw_path


def download_with_browser(context, url, raw_path, timeout_ms):
    """打开下载地址；出现 CF 真人认证时交由用户完成后自动下载。

    优先捕获浏览器自身的下载事件（最贴近真实用户流程，可携带 CF 认证）；
    若等待超时，则退回使用上下文 Cookie 直接请求。
    """
    page = context.new_page()
    log(
        "已打开下载地址。若出现 Cloudflare 真人认证（“请稍候…”或人机验证），"
        "请在浏览器窗口中完成，认证通过后将自动开始下载。"
    )
    captured = False
    try:
        with page.expect_download(timeout=timeout_ms) as download_info:
            try:
                page.goto(url, wait_until="commit", timeout=20000)
            except Exception:
                # 命中附件下载时，goto 会因导航中断而抛错，属正常现象。
                pass
        download_info.value.save_as(str(raw_path))
        captured = True
    except PlaywrightTimeoutError:
        log("未捕获到浏览器下载，尝试使用已通过的认证直接请求下载地址 ...")
    finally:
        try:
            page.close()
        except Exception:
            pass

    if not captured:
        _download_via_request(context, url, raw_path)
    return raw_path


def process_download(raw_path, name, output_dir):
    """ZIP 则解压并按小说名重命名 TXT，同时删除 ZIP；否则直接重命名。"""
    safe_name = sanitize_filename(name)
    final_path = output_dir / f"{safe_name}.txt"

    if not zipfile.is_zipfile(raw_path):
        if final_path.exists():
            final_path.unlink()
        raw_path.rename(final_path)
        log(f"下载内容已是 TXT，直接重命名为：{final_path}")
        return final_path

    extract_dir = output_dir / f".{safe_name}_extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)
    try:
        with zipfile.ZipFile(raw_path, "r") as archive:
            for member in archive.namelist():
                member_path = Path(member)
                # 过滤目录穿越（Zip Slip）风险
                if member_path.is_absolute() or ".." in member_path.parts:
                    continue
                archive.extract(member, extract_dir)

        txt_files = [
            path
            for path in sorted(extract_dir.rglob("*.txt"))
            if not path.name.startswith("._")
        ]
        if not txt_files:
            raise RuntimeError("ZIP 中未找到 TXT 文件")

        if final_path.exists():
            final_path.unlink()
        if len(txt_files) == 1:
            shutil.move(str(txt_files[0]), str(final_path))
        else:
            # 多个 TXT 时按文件名顺序合并为一个文件
            with open(final_path, "wb") as out:
                for txt in txt_files:
                    with open(txt, "rb") as src:
                        shutil.copyfileobj(src, out)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raw_path.unlink(missing_ok=True)

    log(f"已解压并按小说名重命名为：{final_path}")
    return final_path


def _newest_matching_download(download_dir, safe_name, started_at):
    """在下载目录中查找刚下载完成的文件（优先名字匹配，否则取最新的 zip/txt）。

    服务器可能返回非 UTF-8 文件名（浏览器保存后乱码），因此名字匹配失败时
    回退为“下载开始后新出现的最新 zip/txt”。
    """
    named = None
    newest = None
    for path in download_dir.glob("*"):
        if not path.is_file() or path.name.endswith(".crdownload"):
            continue
        if path.suffix.lower() not in (".zip", ".txt"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size == 0 or stat.st_mtime < started_at - 2:
            continue
        if newest is None or stat.st_mtime > newest.stat().st_mtime:
            newest = path
        if safe_name and safe_name in path.name:
            if named is None or stat.st_mtime > named.stat().st_mtime:
                named = path
    return named or newest


def wait_for_download(download_dir, safe_name, timeout):
    """等待用户在真人浏览器中完成 CF 并下载文件到本地。"""
    download_dir = Path(download_dir).expanduser()
    started_at = time.time()
    deadline = started_at + timeout
    log(
        f"将在系统默认浏览器打开下载地址，请在浏览器完成 Cloudflare 认证并下载。"
        f"脚本会等待文件保存到 {download_dir}（最长 {timeout}s）..."
    )
    last_size = -1
    while time.time() < deadline:
        candidate = _newest_matching_download(download_dir, safe_name, started_at)
        if candidate is not None:
            size = candidate.stat().st_size
            if size > 0 and size == last_size:
                log(f"检测到下载完成：{candidate}")
                return candidate
            last_size = size
        time.sleep(1)
    raise RuntimeError(
        f"等待下载超时（{timeout}s）：未在 {download_dir} 找到与 “{safe_name}” 匹配的文件"
    )


def resolve_download_dir(download_dir=None):
    """确定浏览器下载目录：显式指定 > 读取 Chrome 设置 > ~/Downloads。"""
    if download_dir:
        return Path(download_dir).expanduser()
    return chrome_download_dir()


def find_newest_download(download_dir, safe_name=None, max_age_seconds=None):
    """在下载目录中取最新的 zip/txt。

    服务器文件名可能是非 UTF-8（浏览器保存后乱码），因此不强制名字匹配，
    仅优先匹配，匹配不到则取最新的 zip/txt。
    """
    download_dir = Path(download_dir).expanduser()
    now = time.time()
    candidates = []
    for path in download_dir.glob("*"):
        if not path.is_file() or path.name.endswith(".crdownload"):
            continue
        if path.suffix.lower() not in (".zip", ".txt"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size <= 0:
            continue
        if max_age_seconds and now - stat.st_mtime > max_age_seconds:
            continue
        candidates.append(path)
    if not candidates:
        raise RuntimeError(f"在 {download_dir} 未找到符合条件的 zip/txt 文件")
    named = [p for p in candidates if safe_name and safe_name in p.name]
    return max(named or candidates, key=lambda p: p.stat().st_mtime)


def run_handoff(args, output_dir, safe_name):
    """交接模式：脚本解析下载地址并用系统默认浏览器打开，随后交还控制权。

    默认（无 --wait）打开浏览器后立即返回（不再死等）；
    用户完成 CF 认证与下载并确认后，再用 --from-downloads 处理文件。
    """
    with sync_playwright() as playwright:
        context, close_context = open_browser(
            playwright,
            headless=True,  # 仅解析 www.80ge.info 页面，无需 CF
            profile_dir=args.profile_dir,
            channel=args.channel,
        )
        try:
            url = resolve_download_url(context, args.detail_url)
        finally:
            close_context()

    log(f"获取到下载地址：{url}")
    if not open_in_default_browser(url):
        log(f"未能自动打开浏览器，请在浏览器手动访问：{url}")
    print(url)

    if not args.wait:
        download_dir = resolve_download_dir(args.download_dir)
        log(
            "已在系统默认浏览器打开下载地址。请在浏览器完成 Cloudflare 认证并下载；"
            f"下载完成后，用 --from-downloads 处理文件（将扫描 {download_dir}）。"
        )
        return None

    download_dir = resolve_download_dir(args.download_dir)
    downloaded = wait_for_download(download_dir, safe_name, args.handoff_timeout)
    return process_download(downloaded, args.name, output_dir)


def main():
    parser = argparse.ArgumentParser(description="下载并处理 80ge.info 小说")
    parser.add_argument("--detail-url", required=False, help="小说详情页 URL")
    parser.add_argument("--name", required=True, help="小说名称（用于重命名）")
    parser.add_argument(
        "--from-file",
        default=None,
        help="直接处理已下载的 zip/txt 文件（跳过浏览器下载）",
    )
    parser.add_argument(
        "--output-dir", default="./novels", help="输出目录（默认 ./novels）"
    )
    parser.add_argument(
        "--cf-timeout",
        type=int,
        default=180,
        help="等待 Cloudflare 真人认证/下载的秒数（默认 180）",
    )
    parser.add_argument(
        "--handoff",
        action="store_true",
        help="交接模式：解析下载地址并用系统默认浏览器打开，随后交还控制权（不死等）",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="交接模式下等待文件落盘后自动处理（默认打开后即交还控制权）",
    )
    parser.add_argument(
        "--from-downloads",
        action="store_true",
        help="在下载目录中取最新的 zip/txt 并处理（自动探测 Chrome 下载目录）",
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="下载目录（默认读取 Chrome 设置，回退 ~/Downloads）",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=120,
        help="配合 --from-downloads：仅选取该分钟数内修改过的文件（默认 120）",
    )
    parser.add_argument(
        "--handoff-timeout",
        type=int,
        default=300,
        help="配合 --wait 使用：等待文件落盘的秒数（默认 300）",
    )
    parser.add_argument(
        "--headless", action="store_true", help="无头模式（CF 认证需有头）"
    )
    parser.add_argument("--profile-dir", default=None, help="浏览器用户数据目录")
    parser.add_argument(
        "--channel",
        default=None,
        help="浏览器通道，如 chrome / msedge（默认自动：优先系统 Chrome）",
    )
    parser.add_argument(
        "--cdp-url",
        default=None,
        help="附加到已带调试端口启动的浏览器，如 http://127.0.0.1:9222",
    )
    parser.add_argument(
        "--use-real-profile",
        action="store_true",
        help="使用本机 Chrome 真实配置（Chrome 136+ 已不支持，建议改用 --handoff）",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(args.name)
    raw_path = output_dir / f".{safe_name}.download"

    final_path = None
    try:
        if args.from_file:
            final_path = process_download(
                Path(args.from_file).expanduser(), args.name, output_dir
            )
        elif args.from_downloads:
            download_dir = resolve_download_dir(args.download_dir)
            found = find_newest_download(
                download_dir, safe_name, args.max_age * 60
            )
            log(f"找到文件：{found}")
            final_path = process_download(found, args.name, output_dir)
        elif args.handoff:
            if not args.detail_url:
                raise RuntimeError("交接模式需要提供 --detail-url")
            final_path = run_handoff(args, output_dir, safe_name)
        else:
            if not args.detail_url:
                raise RuntimeError("需要提供 --detail-url（或使用 --from-file / --handoff）")
            with sync_playwright() as playwright:
                context, close_context = open_browser(
                    playwright,
                    headless=args.headless,
                    profile_dir=args.profile_dir,
                    channel=args.channel,
                    cdp_url=args.cdp_url,
                    use_real_profile=args.use_real_profile,
                )
                try:
                    log(f"打开详情页：{args.detail_url}")
                    url = resolve_download_url(context, args.detail_url)
                    log(f"获取到下载地址：{url}")
                    download_with_browser(
                        context, url, raw_path, args.cf_timeout * 1000
                    )
                    log("下载完成，开始解压/重命名 ...")
                    final_path = process_download(raw_path, args.name, output_dir)
                finally:
                    close_context()
    except Exception as exc:  # noqa: BLE001 - 统一转为可读错误
        raw_path.unlink(missing_ok=True)
        log(f"ERROR: {exc}")
        sys.exit(1)

    if final_path is None:
        # 交接模式（未 --wait）：已打开浏览器并交还控制权，无最终文件
        return
    print(str(final_path.resolve()))


if __name__ == "__main__":
    main()
