"""元数据线索提取模块 - 从标签、文件名、目录名提取信息"""

import logging
import re
from pathlib import Path

import mutagen
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.apev2 import APEv2
from mutagen.id3 import ID3

from .db import Database

logger = logging.getLogger(__name__)

# 文件名解析正则（按优先级排列）
FILENAME_PATTERNS = [
    # "NNN.艺术家 - 歌名" （带编号）
    re.compile(r"^\d+[.\s]+(.+?)\s*[-–—]\s*(.+?)$"),
    # "艺术家 - 歌名"
    re.compile(r"^(.+?)\s*[-–—]\s*(.+?)$"),
]

# 目录名中 "艺术家 - 专辑名" 模式
DIR_ARTIST_ALBUM = re.compile(r"^(.+?)\s*[-–—]\s*(.+?)$")


def extract_metadata(track: dict, db: Database):
    """提取一条 track 的所有可用元数据线索"""
    filepath = Path(track["file_path"])
    if not filepath.exists():
        db.update_status(track["id"], "failed", f"文件不存在: {filepath}")
        return

    updates = {}

    # 1. 读取文件内嵌标签
    tag_info = _read_embedded_tags(filepath)
    if tag_info:
        updates.update({
            "existing_title": tag_info.get("title"),
            "existing_artist": tag_info.get("artist"),
            "existing_album": tag_info.get("album"),
            "existing_year": tag_info.get("year"),
            "has_existing_cover": 1 if tag_info.get("has_cover") else 0,
            "has_existing_lyrics": 1 if tag_info.get("has_lyrics") else 0,
        })

    # 2. 解析文件名
    parsed = _parse_filename(filepath.stem)
    updates["parsed_title"] = parsed.get("title")
    updates["parsed_artist"] = parsed.get("artist")

    # 3. 解析目录名补充
    dir_info = _parse_directory(filepath, track.get("format"))
    if dir_info.get("artist") and not updates.get("parsed_artist"):
        updates["parsed_artist"] = dir_info["artist"]
    if dir_info.get("album"):
        updates["parsed_album"] = dir_info["album"]

    updates["status"] = "extracted"
    db.update_track(track["id"], **updates)
    logger.info("提取完成: %s → artist=%s, title=%s",
                filepath.name,
                updates.get("parsed_artist") or updates.get("existing_artist") or "?",
                updates.get("parsed_title") or updates.get("existing_title") or "?")


def get_best_clues(track: dict) -> dict:
    """从 track 记录中提取最佳搜索线索（优先用嵌入标签，其次用解析结果）"""
    artist = track.get("existing_artist") or track.get("parsed_artist")
    title = track.get("existing_title") or track.get("parsed_title")
    album = track.get("existing_album") or track.get("parsed_album")
    return {"artist": artist, "title": title, "album": album}


def _read_embedded_tags(filepath: Path) -> dict | None:
    """读取文件内嵌标签"""
    try:
        ext = filepath.suffix.lower()
        if ext == ".flac":
            return _read_flac_tags(filepath)
        elif ext == ".m4a":
            return _read_m4a_tags(filepath)
        elif ext == ".mp3":
            return _read_mp3_tags(filepath)
        elif ext == ".ape":
            return _read_ape_tags(filepath)
        elif ext == ".wav":
            return _read_wav_tags(filepath)
    except Exception as e:
        logger.warning("读取标签失败 %s: %s", filepath.name, e)
    return None


def _read_flac_tags(filepath: Path) -> dict:
    audio = FLAC(filepath)
    return {
        "title": _first(audio.get("title")),
        "artist": _first(audio.get("artist")),
        "album": _first(audio.get("album")),
        "year": _first(audio.get("date")),
        "has_cover": len(audio.pictures) > 0,
        "has_lyrics": bool(audio.get("lyrics") or audio.get("unsyncedlyrics")),
    }


def _read_m4a_tags(filepath: Path) -> dict:
    audio = MP4(filepath)
    tags = audio.tags or {}
    return {
        "title": _first(tags.get("\xa9nam")),
        "artist": _first(tags.get("\xa9ART")),
        "album": _first(tags.get("\xa9alb")),
        "year": _first(tags.get("\xa9day")),
        "has_cover": bool(tags.get("covr")),
        "has_lyrics": bool(tags.get("\xa9lyr")),
    }


def _read_mp3_tags(filepath: Path) -> dict:
    audio = MP3(filepath)
    tags = audio.tags
    if not tags:
        return {}
    return {
        "title": _id3_text(tags, "TIT2"),
        "artist": _id3_text(tags, "TPE1"),
        "album": _id3_text(tags, "TALB"),
        "year": _id3_text(tags, "TDRC"),
        "has_cover": any(k.startswith("APIC") for k in tags.keys()),
        "has_lyrics": any(k.startswith("USLT") for k in tags.keys()),
    }


def _read_ape_tags(filepath: Path) -> dict:
    try:
        tags = APEv2(filepath)
    except Exception:
        return {}
    return {
        "title": str(tags.get("Title", "")),
        "artist": str(tags.get("Artist", "")),
        "album": str(tags.get("Album", "")),
        "year": str(tags.get("Year", "")),
        "has_cover": False,
        "has_lyrics": False,
    }


def _read_wav_tags(filepath: Path) -> dict:
    try:
        tags = ID3(filepath)
    except Exception:
        return {}
    return {
        "title": _id3_text(tags, "TIT2"),
        "artist": _id3_text(tags, "TPE1"),
        "album": _id3_text(tags, "TALB"),
        "year": _id3_text(tags, "TDRC"),
        "has_cover": any(k.startswith("APIC") for k in tags.keys()),
        "has_lyrics": any(k.startswith("USLT") for k in tags.keys()),
    }


def _parse_filename(stem: str) -> dict:
    """从文件名（不含扩展名）解析 artist 和 title"""
    for pattern in FILENAME_PATTERNS:
        m = pattern.match(stem)
        if m:
            groups = m.groups()
            # 清理括号内的附加信息（如电视剧信息），保留作为标题一部分
            return {"artist": groups[0].strip(), "title": groups[1].strip()}
    # 无法匹配 artist，整个文件名当 title
    return {"artist": None, "title": stem.strip()}


def _parse_directory(filepath: Path, fmt: str = None) -> dict:
    """从目录路径推断 artist 和 album"""
    result = {}
    parts = filepath.parent.parts

    # 查找有意义的目录层级（跳过 "临时"、"已整理" 等）
    skip_names = {"临时", "已整理", "Music"}

    meaningful = [p for p in parts if p not in skip_names and not p.startswith("/") and p != "Volumes"]

    if not meaningful:
        return result

    # 尝试解析最近的目录名
    for part in reversed(meaningful):
        m = DIR_ARTIST_ALBUM.match(part)
        if m:
            if not result.get("artist"):
                result["artist"] = m.group(1).strip()
            if not result.get("album"):
                # 清理年份括号 "专辑名(2001)" → "专辑名"
                album = m.group(2).strip()
                album = re.sub(r"\s*[\(（]\d{4}[\)）]\s*$", "", album)
                result["album"] = album
            break

    # 如果只有一个有意义的目录名且无 "-" 分隔，可能是歌手名
    if not result.get("artist") and len(meaningful) >= 1:
        candidate = meaningful[-1]
        if not DIR_ARTIST_ALBUM.match(candidate):
            result["artist"] = candidate

    return result


def _first(val) -> str | None:
    """从标签值（可能是列表）取第一个"""
    if isinstance(val, list) and val:
        return str(val[0]).strip() or None
    if val:
        s = str(val).strip()
        return s or None
    return None


def _id3_text(tags, key: str) -> str | None:
    frame = tags.get(key)
    if frame and hasattr(frame, "text") and frame.text:
        return str(frame.text[0]).strip() or None
    return None
