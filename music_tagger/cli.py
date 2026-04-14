"""CLI 命令行接口"""

import logging
import sys

import click
from rich.console import Console
from rich.table import Table
from rich.logging import RichHandler

from .config import Config
from .pipeline import Pipeline

console = Console()


def setup_logging(log_path: str = None, verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    handlers = [RichHandler(console=console, show_path=False, show_time=False)]
    if log_path:
        from pathlib import Path
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(level=level, handlers=handlers, format="%(message)s")


@click.group()
@click.option("--config", "-c", "config_path", default=None, help="配置文件路径")
@click.option("--verbose", "-v", is_flag=True, help="详细输出")
@click.pass_context
def main(ctx, config_path, verbose):
    """music-tagger: 音乐曲库自动标签整理工具"""
    ctx.ensure_object(dict)
    cfg = Config(config_path)
    setup_logging(str(cfg.log_path), verbose)
    ctx.obj["config"] = cfg
    ctx.obj["pipeline"] = Pipeline(cfg)


@main.command()
@click.pass_context
def run(ctx):
    """一键执行完整流程（扫描→提取→匹配→标签→重命名→归类）"""
    pipeline = ctx.obj["pipeline"]
    try:
        pipeline.run()
        _print_status(pipeline)
    finally:
        pipeline.close()


@main.command()
@click.pass_context
def scan(ctx):
    """扫描临时目录，发现新文件"""
    pipeline = ctx.obj["pipeline"]
    try:
        new_ids = pipeline.scan()
        console.print(f"发现 [bold green]{len(new_ids)}[/] 个新文件")
    finally:
        pipeline.close()


@main.command()
@click.pass_context
def match(ctx):
    """搜索匹配未处理的文件"""
    pipeline = ctx.obj["pipeline"]
    try:
        pipeline.extract()
        pipeline.match()
        _print_status(pipeline)
    finally:
        pipeline.close()


@main.command()
@click.pass_context
def tag(ctx):
    """为已匹配的文件写入标签"""
    pipeline = ctx.obj["pipeline"]
    try:
        pipeline.tag()
        _print_status(pipeline)
    finally:
        pipeline.close()


@main.command()
@click.pass_context
def rename(ctx):
    """重命名已标签的文件"""
    pipeline = ctx.obj["pipeline"]
    try:
        pipeline.rename()
        _print_status(pipeline)
    finally:
        pipeline.close()


@main.command()
@click.pass_context
def organize(ctx):
    """将已重命名的文件归类到已整理目录"""
    pipeline = ctx.obj["pipeline"]
    try:
        pipeline.organize()
        _print_status(pipeline)
    finally:
        pipeline.close()


@main.command()
@click.pass_context
def status(ctx):
    """查看处理状态统计"""
    pipeline = ctx.obj["pipeline"]
    try:
        _print_status(pipeline)
    finally:
        pipeline.close()


@main.command("list")
@click.option("--status", "-s", "filter_status", default=None,
              help="过滤状态: new/extracted/matched/tagged/renamed/organized/failed/pending_review")
@click.option("--limit", "-n", default=20, help="显示数量")
@click.pass_context
def list_tracks(ctx, filter_status, limit):
    """列出文件详情"""
    pipeline = ctx.obj["pipeline"]
    try:
        tracks = pipeline.db.list_tracks(status=filter_status, limit=limit)
        if not tracks:
            console.print("没有找到记录")
            return

        table = Table(title=f"文件列表 (status={filter_status or 'all'})")
        table.add_column("ID", style="dim", width=4)
        table.add_column("文件名", max_width=40)
        table.add_column("状态", width=14)
        table.add_column("匹配结果", max_width=35)
        table.add_column("置信度", width=6)

        for t in tracks:
            from pathlib import Path
            name = Path(t["file_path"]).name
            matched = ""
            if t.get("matched_artist") or t.get("matched_title"):
                matched = f"{t.get('matched_artist', '')} - {t.get('matched_title', '')}"
            conf = f"{t['match_confidence']:.2f}" if t.get("match_confidence") else ""

            status_style = {
                "new": "white",
                "extracted": "cyan",
                "matched": "blue",
                "tagged": "yellow",
                "renamed": "magenta",
                "organized": "green",
                "failed": "red",
                "pending_review": "bold red",
            }.get(t["status"], "white")

            table.add_row(
                str(t["id"]),
                name[:40],
                f"[{status_style}]{t['status']}[/]",
                matched[:35],
                conf,
            )

        console.print(table)
    finally:
        pipeline.close()


@main.command()
@click.option("--id", "track_id", default=None, type=int, help="重试指定 ID")
@click.pass_context
def retry(ctx, track_id):
    """重试失败的文件"""
    pipeline = ctx.obj["pipeline"]
    try:
        if track_id:
            track = pipeline.db.get_track(track_id)
            if not track:
                console.print(f"[red]未找到 ID={track_id}[/]")
                return
            pipeline.db.update_status(track_id, "new")
            console.print(f"已重置 ID={track_id} 为 new 状态")
        else:
            failed = pipeline.db.list_tracks(status="failed", limit=9999)
            for t in failed:
                pipeline.db.update_status(t["id"], "new")
            console.print(f"已重置 [bold]{len(failed)}[/] 个失败文件")

        pipeline.run()
        _print_status(pipeline)
    finally:
        pipeline.close()


def _print_status(pipeline: Pipeline):
    stats = pipeline.status()
    if not stats:
        console.print("数据库为空")
        return

    table = Table(title="处理状态统计")
    table.add_column("状态", style="bold")
    table.add_column("数量", justify="right")

    order = ["new", "extracted", "matched", "tagged", "renamed", "organized",
             "done", "pending_review", "failed", "skipped"]
    for s in order:
        if s in stats:
            table.add_row(s, str(stats[s]))

    total = sum(stats.values())
    table.add_row("[bold]合计[/]", f"[bold]{total}[/]")
    console.print(table)
