#!/usr/bin/env python3
"""一步式交互下载：搜索 -> 选择 -> 打开浏览器 -> 确认 -> 处理。

适合在**自己的交互式终端**中直接运行（需要 TTY 输入）。
Agent 分步调用请改用 search_novels.py / download_novel.py。
"""
import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import download_novel as dn
from common import log, sanitize_filename
from search_novels import search


def ask(prompt):
    """读取一行输入；非交互式终端时报错退出。"""
    try:
        return input(prompt).strip()
    except EOFError:
        raise SystemExit("本脚本需要交互式终端（TTY）来输入选择与确认。")


def pick(results):
    """展示候选并让用户选择。"""
    print("\n搜索结果：")
    for item in results:
        intro = item["intro"] or "-"
        if len(intro) > 40:
            intro = intro[:40] + "…"
        print(
            f"  [{item['index']}] 《{item['title']}》 "
            f"{item['author'] or '-'} ({item['category'] or '-'}, "
            f"{item['status'] or '-'})  {intro}"
        )
    while True:
        raw = ask(f"\n请选择序号 [1-{len(results)}]（默认 1）: ") or "1"
        if raw.isdigit() and 1 <= int(raw) <= len(results):
            return results[int(raw) - 1]
        print("输入无效，请重新选择。")


def main():
    parser = argparse.ArgumentParser(description="一步式搜索并下载 80ge 小说")
    parser.add_argument("name", nargs="?", help="书名（不填则运行后提示输入）")
    parser.add_argument("--limit", type=int, default=10, help="候选数量，默认 10")
    parser.add_argument(
        "--output-dir",
        default=str(Path.home() / "Downloads" / "novels"),
        help="输出目录，默认 ~/Downloads/novels",
    )
    parser.add_argument("--profile-dir", default=None, help="浏览器用户数据目录")
    parser.add_argument(
        "--channel", default=None, help="浏览器通道，如 chrome / msedge"
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="浏览器下载目录（默认读取 Chrome 设置，回退 ~/Downloads）",
    )
    parser.add_argument(
        "--headless", action="store_true", help="搜索用无头模式（默认有头）"
    )
    args = parser.parse_args()

    name = args.name or ask("请输入书名: ")
    if not name:
        raise SystemExit("书名不能为空。")

    # 1. 搜索
    results = search(
        name,
        limit=args.limit,
        headless=args.headless,
        profile_dir=args.profile_dir,
        channel=args.channel,
        cdp_url=None,
        use_real_profile=False,
    )
    if not results:
        raise SystemExit(f"未找到与 “{name}” 相关的结果。")

    # 2. 选择
    selected = pick(results)
    title = selected["title"]
    detail_url = selected["url"]
    log(f"已选择：《{title}》 {selected['author'] or '-'}")

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(title)

    # 3. 解析下载地址并打开浏览器（交还控制权）
    handoff_args = SimpleNamespace(
        detail_url=detail_url,
        profile_dir=args.profile_dir,
        channel=args.channel,
        wait=False,
        download_dir=args.download_dir,
        handoff_timeout=300,
    )
    dn.run_handoff(handoff_args, output_dir, safe_name)

    # 4. 等用户确认
    ask("\n请在浏览器完成 Cloudflare 认证并下载，完成后按回车继续处理... ")

    # 5. 处理文件
    download_dir = dn.resolve_download_dir(args.download_dir)
    found = dn.find_newest_download(download_dir, safe_name, 120 * 60)
    log(f"找到文件：{found}")
    final_path = dn.process_download(found, title, output_dir)
    print(str(final_path.resolve()))


if __name__ == "__main__":
    main()
