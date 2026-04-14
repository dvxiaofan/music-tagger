"""标签写入模块 - 使用 mutagen 写入音频文件标签"""

import logging
from pathlib import Path

import httpx
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC, USLT, ID3NoHeaderError

from .matcher import MatchResult

logger = logging.getLogger(__name__)


async def download_cover(url: str) -> bytes | None:
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            if len(resp.content) < 1000:
                logger.warning("封面图太小，可能无效: %s", url)
                return None
            return resp.content
    except Exception as e:
        logger.warning("下载封面失败 %s: %s", url, e)
        return None


def write_tags(filepath: Path, match: MatchResult, cover_data: bytes | None = None,
               overwrite: bool = False) -> list[str]:
    """
    写入标签到音频文件。
    overwrite=False 时只补缺不覆盖。
    返回实际写入的字段列表。
    """
    ext = filepath.suffix.lower()
    try:
        if ext == ".flac":
            return _tag_flac(filepath, match, cover_data, overwrite)
        elif ext == ".m4a":
            return _tag_m4a(filepath, match, cover_data, overwrite)
        elif ext == ".mp3":
            return _tag_mp3(filepath, match, cover_data, overwrite)
        elif ext == ".wav":
            return _tag_wav(filepath, match, cover_data, overwrite)
        else:
            logger.warning("不支持的格式: %s", ext)
            return []
    except Exception as e:
        logger.error("写入标签失败 %s: %s", filepath.name, e)
        raise


def _tag_flac(filepath: Path, match: MatchResult, cover_data: bytes | None,
              overwrite: bool) -> list[str]:
    audio = FLAC(filepath)
    written = []

    field_map = {
        "title": ("title", match.title),
        "artist": ("artist", match.artist),
        "album": ("album", match.album),
        "year": ("date", match.year),
    }

    for field, (tag_name, value) in field_map.items():
        if not value:
            continue
        if not overwrite and audio.get(tag_name):
            continue
        audio[tag_name] = [value]
        written.append(field)

    # 歌词（写入 LRC 格式，支持滚动显示）
    if match.lrc_lyrics and (overwrite or not audio.get("lyrics")):
        audio["lyrics"] = [match.lrc_lyrics]
        written.append("lyrics")

    # 封面
    if cover_data and (overwrite or not audio.pictures):
        pic = Picture()
        pic.type = 3  # Cover (front)
        pic.mime = "image/jpeg"
        pic.data = cover_data
        if not overwrite:
            audio.clear_pictures()
        audio.add_picture(pic)
        written.append("cover")

    if written:
        audio.save()
        logger.info("FLAC 标签写入: %s → %s", filepath.name, written)

    return written


def _tag_m4a(filepath: Path, match: MatchResult, cover_data: bytes | None,
             overwrite: bool) -> list[str]:
    audio = MP4(filepath)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    written = []

    field_map = {
        "title": ("\xa9nam", match.title),
        "artist": ("\xa9ART", match.artist),
        "album": ("\xa9alb", match.album),
        "year": ("\xa9day", match.year),
    }

    for field, (tag_name, value) in field_map.items():
        if not value:
            continue
        if not overwrite and tags.get(tag_name):
            continue
        tags[tag_name] = [value]
        written.append(field)

    # 歌词（写入 LRC 格式，支持滚动显示）
    if match.lrc_lyrics and (overwrite or not tags.get("\xa9lyr")):
        tags["\xa9lyr"] = [match.lrc_lyrics]
        written.append("lyrics")

    # 封面
    if cover_data and (overwrite or not tags.get("covr")):
        tags["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
        written.append("cover")

    if written:
        audio.save()
        logger.info("M4A 标签写入: %s → %s", filepath.name, written)

    return written


def _tag_mp3(filepath: Path, match: MatchResult, cover_data: bytes | None,
             overwrite: bool) -> list[str]:
    try:
        tags = ID3(filepath)
    except ID3NoHeaderError:
        tags = ID3()

    written = []

    id3_map = {
        "title": ("TIT2", TIT2, match.title),
        "artist": ("TPE1", TPE1, match.artist),
        "album": ("TALB", TALB, match.album),
        "year": ("TDRC", TDRC, match.year),
    }

    for field, (key, cls, value) in id3_map.items():
        if not value:
            continue
        if not overwrite and tags.get(key):
            continue
        tags.add(cls(encoding=3, text=[value]))
        written.append(field)

    # 歌词（写入 LRC 格式，支持滚动显示）
    if match.lrc_lyrics and (overwrite or not any(k.startswith("USLT") for k in tags.keys())):
        tags.add(USLT(encoding=3, lang="chi", text=match.lrc_lyrics))
        written.append("lyrics")

    # 封面
    if cover_data and (overwrite or not any(k.startswith("APIC") for k in tags.keys())):
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, data=cover_data))
        written.append("cover")

    if written:
        tags.save(filepath)
        logger.info("MP3 标签写入: %s → %s", filepath.name, written)

    return written


def _tag_wav(filepath: Path, match: MatchResult, cover_data: bytes | None,
             overwrite: bool) -> list[str]:
    # WAV 使用 ID3 标签，与 MP3 类似
    return _tag_mp3(filepath, match, cover_data, overwrite)
