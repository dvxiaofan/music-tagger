"""目录扫描模块 - 发现新入库的音频文件"""

import hashlib
import logging
from pathlib import Path

from .db import Database

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".flac", ".m4a", ".mp3", ".wav", ".ape"}


def compute_file_hash(filepath: Path, chunk_size: int = 8192) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def scan_directory(watch_dir: Path, db: Database, organized_dir: Path | None = None) -> list[int]:
    """
    递归扫描目录，发现新音频文件并注册到数据库。
    跳过已整理目录，避免重复处理。
    返回新注册的 track ID 列表。
    """
    if not watch_dir.exists():
        logger.error("监控目录不存在: %s", watch_dir)
        return []

    new_ids = []
    audio_files = []

    for f in watch_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        # 跳过已整理目录
        if organized_dir and _is_under(f, organized_dir):
            continue
        audio_files.append(f)

    logger.info("扫描到 %d 个音频文件", len(audio_files))

    for filepath in audio_files:
        try:
            file_hash = compute_file_hash(filepath)

            if db.hash_exists(file_hash):
                continue

            # 检查是否有配套 LRC 文件
            lrc_path = filepath.with_suffix(".lrc")
            has_lrc = 1 if lrc_path.exists() else 0

            track_id = db.insert_track(
                file_path=str(filepath),
                original_path=str(filepath),
                file_hash=file_hash,
                file_size=filepath.stat().st_size,
                format=filepath.suffix.lstrip(".").lower(),
                has_existing_lrc=has_lrc,
            )

            if track_id:
                new_ids.append(track_id)
                logger.info("新文件: %s (id=%d)", filepath.name, track_id)

        except Exception as e:
            logger.error("扫描文件失败 %s: %s", filepath, e)

    logger.info("本次新增 %d 个文件", len(new_ids))
    return new_ids


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
