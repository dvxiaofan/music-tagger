"""重命名与归类模块"""

import logging
import re
import shutil
from pathlib import Path

from .db import Database

logger = logging.getLogger(__name__)

# 文件名中不允许的字符
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def rename_track(track: dict, db: Database) -> Path | None:
    """
    基于匹配到的元数据重命名文件。
    返回新文件路径，失败返回 None。
    """
    filepath = Path(track["file_path"])
    if not filepath.exists():
        db.update_status(track["id"], "failed", f"文件不存在: {filepath}")
        return None

    artist = track.get("matched_artist") or ""
    title = track.get("matched_title") or ""

    if not title:
        logger.warning("无标题信息，跳过重命名: %s", filepath.name)
        return filepath

    # 构建新文件名
    if artist:
        new_stem = f"{artist} - {title}"
    else:
        new_stem = title

    new_stem = _sanitize_filename(new_stem)
    new_name = f"{new_stem}{filepath.suffix}"
    new_path = filepath.parent / new_name

    if new_path == filepath:
        db.update_track(track["id"], status="renamed")
        return filepath

    # 处理文件名冲突
    new_path = _resolve_conflict(new_path)

    try:
        # 重命名音频文件
        filepath.rename(new_path)
        logger.info("重命名: %s → %s", filepath.name, new_path.name)

        # 同步重命名 LRC 文件
        old_lrc = filepath.with_suffix(".lrc")
        if old_lrc.exists():
            new_lrc = new_path.with_suffix(".lrc")
            new_lrc = _resolve_conflict(new_lrc)
            old_lrc.rename(new_lrc)
            logger.info("LRC 重命名: %s → %s", old_lrc.name, new_lrc.name)

        db.update_track(track["id"], file_path=str(new_path), status="renamed")
        return new_path

    except Exception as e:
        logger.error("重命名失败 %s: %s", filepath.name, e)
        db.update_status(track["id"], "failed", f"重命名失败: {e}")
        return None


def organize_track(track: dict, organized_dir: Path, organize_pattern: str,
                   db: Database) -> Path | None:
    """
    将已重命名的文件移入已整理目录。
    目录结构由 organize_pattern 控制（当前：已整理/艺术家/文件，歌曲平铺）
    """
    filepath = Path(track["file_path"])
    if not filepath.exists():
        db.update_status(track["id"], "failed", f"文件不存在: {filepath}")
        return None

    artist = track.get("matched_artist") or "未知艺术家"
    album = track.get("matched_album") or "未知专辑"

    # 构建目标目录
    rel_dir = organize_pattern.format(
        artist=_sanitize_filename(artist),
        album=_sanitize_filename(album),
    )
    target_dir = organized_dir / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filepath.name
    target_path = _resolve_conflict(target_path)

    try:
        shutil.move(str(filepath), str(target_path))
        logger.info("归类: %s → %s", filepath.name, target_path.relative_to(organized_dir))

        # 同步移动 LRC 文件
        old_lrc = filepath.with_suffix(".lrc")
        if old_lrc.exists():
            lrc_target = target_path.with_suffix(".lrc")
            lrc_target = _resolve_conflict(lrc_target)
            shutil.move(str(old_lrc), str(lrc_target))

        db.update_track(track["id"], file_path=str(target_path), status="organized")
        return target_path

    except Exception as e:
        logger.error("归类失败 %s: %s", filepath.name, e)
        db.update_status(track["id"], "failed", f"归类失败: {e}")
        return None


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    name = INVALID_CHARS.sub("", name)
    name = name.strip(". ")
    return name or "unknown"


def _resolve_conflict(path: Path) -> Path:
    """处理文件名冲突，追加序号"""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        new_path = parent / f"{stem} ({counter}){suffix}"
        if not new_path.exists():
            return new_path
        counter += 1
