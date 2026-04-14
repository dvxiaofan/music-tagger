"""MCP Server - 供 Agent 调用的音乐标签工具"""

import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import Config
from .pipeline import Pipeline

logger = logging.getLogger(__name__)

mcp = FastMCP("music-tagger")


def _get_pipeline() -> Pipeline:
    config = Config()
    return Pipeline(config)


@mcp.tool()
def scan_new_music() -> str:
    """扫描临时目录，发现新入库的音乐文件"""
    pipeline = _get_pipeline()
    try:
        new_ids = pipeline.scan()
        if not new_ids:
            return "没有发现新文件"
        return f"发现 {len(new_ids)} 个新文件，ID: {new_ids}"
    finally:
        pipeline.close()


@mcp.tool()
def process_all() -> str:
    """一键处理所有新文件（扫描→匹配→标签→重命名→归类）"""
    pipeline = _get_pipeline()
    try:
        pipeline.run()
        stats = pipeline.status()
        return f"处理完成: {json.dumps(stats, ensure_ascii=False)}"
    except Exception as e:
        return f"处理失败: {e}"
    finally:
        pipeline.close()


@mcp.tool()
def get_status() -> str:
    """获取当前处理状态统计"""
    pipeline = _get_pipeline()
    try:
        stats = pipeline.status()
        if not stats:
            return "数据库为空"
        return json.dumps(stats, ensure_ascii=False)
    finally:
        pipeline.close()


@mcp.tool()
def list_tracks(status: str = "", limit: int = 20) -> str:
    """列出指定状态的文件。status 可选: new, extracted, matched, tagged, renamed, organized, failed, pending_review"""
    pipeline = _get_pipeline()
    try:
        s = status if status else None
        tracks = pipeline.db.list_tracks(status=s, limit=limit)
        if not tracks:
            return "没有找到记录"
        result = []
        for t in tracks:
            name = Path(t["file_path"]).name
            matched = ""
            if t.get("matched_artist") or t.get("matched_title"):
                matched = f"{t.get('matched_artist', '')} - {t.get('matched_title', '')}"
            conf = f"{t['match_confidence']:.2f}" if t.get("match_confidence") else ""
            result.append(
                f"ID={t['id']} | {name} | {t['status']} | {matched} | 置信度:{conf}"
            )
        return "\n".join(result)
    finally:
        pipeline.close()


@mcp.tool()
def retry_failed(track_id: int = 0) -> str:
    """重试失败的文件。不指定 track_id 则重试所有失败文件"""
    pipeline = _get_pipeline()
    try:
        if track_id:
            track = pipeline.db.get_track(track_id)
            if not track:
                return f"未找到 ID={track_id}"
            pipeline.db.update_status(track_id, "new")
            pipeline.run()
        else:
            failed = pipeline.db.list_tracks(status="failed", limit=9999)
            if not failed:
                return "没有失败文件"
            for t in failed:
                pipeline.db.update_status(t["id"], "new")
            pipeline.run()
        stats = pipeline.status()
        return f"重试完成: {json.dumps(stats, ensure_ascii=False)}"
    except Exception as e:
        return f"重试失败: {e}"
    finally:
        pipeline.close()


@mcp.tool()
def manual_tag(
    track_id: int,
    title: str = "",
    artist: str = "",
    album: str = "",
    year: str = "",
) -> str:
    """为指定文件手动设置元数据"""
    pipeline = _get_pipeline()
    try:
        track = pipeline.db.get_track(track_id)
        if not track:
            return f"未找到 ID={track_id}"

        updates = {}
        if title:
            updates["matched_title"] = title
        if artist:
            updates["matched_artist"] = artist
        if album:
            updates["matched_album"] = album
        if year:
            updates["matched_year"] = year

        if not updates:
            return "请至少指定一个字段（title/artist/album/year）"

        updates["matched_source"] = "manual"
        updates["match_confidence"] = 1.0
        pipeline.db.update_track(track_id, status="matched", **updates)

        # 自动执行后续步骤：tag → rename → organize
        pipeline.tag([track_id])
        pipeline.rename([track_id])
        pipeline.organize([track_id])

        return f"手动标注完成: ID={track_id} → {artist} - {title}"
    except Exception as e:
        return f"手动标注失败: {e}"
    finally:
        pipeline.close()


def main():
    mcp.run()


if __name__ == "__main__":
    main()
