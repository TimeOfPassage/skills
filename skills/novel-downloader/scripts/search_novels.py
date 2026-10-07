#!/usr/bin/env python3
"""在 80ge.info 搜索小说，返回前 N 条结果（JSON）。

用法:
    python3 search_novels.py --name "斗破苍穹" [--limit 10] [--headless]

输出（stdout）:
    搜索结果 JSON 数组，字段: index/title/author/category/status/update/clicks/intro/url
"""
import argparse
import json
import re
import sys

from playwright.sync_api import sync_playwright

from common import (
    SEARCH_URL,
    abs_url,
    clean_title,
    first_page,
    log,
    open_browser,
)

FIELD_AUTHOR = re.compile(r"作者[:：]\s*(.+)")
FIELD_CATEGORY = re.compile(r"分类[:：]\s*(\S+)")
FIELD_STATUS = re.compile(r"状态[:：]\s*(\S+)")
FIELD_UPDATE = re.compile(r"更新[:：]\s*(\S+)")


def _parse_item(item, index):
    link = item.query_selector("a.bookname")
    if not link:
        return None

    url = abs_url(link.get_attribute("href"))
    title = clean_title(link.inner_text())

    clicks = ""
    badge = item.query_selector("span.bookdata")
    if badge:
        match = re.search(r"(\d+)", badge.inner_text())
        if match:
            clicks = match.group(1)

    author = category = status = update = intro = ""
    for para in item.query_selector_all("p"):
        text = " ".join(para.inner_text().split())
        if not text:
            continue
        if "作者" in text:
            author_link = para.query_selector("a")
            if author_link:
                author = author_link.inner_text().strip()
            match = FIELD_AUTHOR.search(text)
            if match and not author:
                author = match.group(1).split("分类")[0].strip()
            match = FIELD_CATEGORY.search(text)
            if match:
                category = match.group(1)
        elif "状态" in text:
            match = FIELD_STATUS.search(text)
            if match:
                status = match.group(1)
            match = FIELD_UPDATE.search(text)
            if match:
                update = match.group(1)
        elif len(text) > len(intro):
            intro = re.sub(r"[.\u3002\s]+$", "", text)

    return {
        "index": index,
        "title": title,
        "author": author,
        "category": category,
        "status": status,
        "update": update,
        "clicks": clicks,
        "intro": intro,
        "url": url,
    }


def parse_results(page, limit):
    results = []
    for item in page.query_selector_all("li.storelistbt5a"):
        parsed = _parse_item(item, len(results) + 1)
        if not parsed:
            continue
        results.append(parsed)
        if len(results) >= limit:
            break
    return results


def search(name, *, limit, headless, profile_dir, channel, cdp_url, use_real_profile):
    with sync_playwright() as playwright:
        context, close_context = open_browser(
            playwright,
            headless=headless,
            profile_dir=profile_dir,
            channel=channel,
            cdp_url=cdp_url,
            use_real_profile=use_real_profile,
        )
        try:
            page = first_page(context)
            page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
            # 搜索框由页面 JS (search_tag) 注入，需等待其出现。
            page.wait_for_selector("#Keyword", timeout=30000)
            page.fill("#Keyword", name)
            with page.expect_navigation(
                wait_until="domcontentloaded", timeout=60000
            ):
                page.click("input.searchbut")
            try:
                page.wait_for_selector("li.storelistbt5a", timeout=15000)
            except Exception:
                # 无结果时页面不含结果节点，交由上层判断。
                pass
            return parse_results(page, limit)
        finally:
            close_context()


def main():
    parser = argparse.ArgumentParser(description="搜索 80ge.info 小说")
    parser.add_argument("--name", required=True, help="小说名称或作者")
    parser.add_argument("--limit", type=int, default=10, help="返回结果数量")
    parser.add_argument(
        "--headless", action="store_true", help="无头模式（默认有头）"
    )
    parser.add_argument(
        "--profile-dir", default=None, help="浏览器用户数据目录"
    )
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
        help="使用本机 Chrome 真实配置（需先完全退出 Chrome）",
    )
    args = parser.parse_args()

    try:
        results = search(
            args.name,
            limit=args.limit,
            headless=args.headless,
            profile_dir=args.profile_dir,
            channel=args.channel,
            cdp_url=args.cdp_url,
            use_real_profile=args.use_real_profile,
        )
    except Exception as exc:  # noqa: BLE001 - 统一转为可读错误
        log(f"ERROR: {exc}")
        sys.exit(1)

    if not results:
        log(f"ERROR: 未找到与 “{args.name}” 相关的结果")
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
