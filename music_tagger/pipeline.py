"""处理流水线 - 串联各模块完成一键处理"""

import asyncio
import logging
from pathlib import Path

from .config import Config
from .db import Database
from .scanner import scan_directory
from .extractor import extract_metadata, get_best_clues
from .matcher.qq_music import QQMusicMatcher
from .tagger import write_tags, download_cover
from .lyrics import save_lrc_file
from .renamer import rename_track, organize_track

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: Config):
        self.config = config
        self.db = Database(config.db_path)

    def close(self):
        self.db.close()

    def scan(self) -> list[int]:
        return scan_directory(
            self.config.watch_dir,
            self.db,
            organized_dir=self.config.organized_dir,
        )

    def extract(self, track_ids: list[int] | None = None):
        if track_ids:
            tracks = [self.db.get_track(tid) for tid in track_ids]
            tracks = [t for t in tracks if t and t["status"] == "new"]
        else:
            tracks = self.db.list_tracks(status="new", limit=9999)

        for track in tracks:
            extract_metadata(track, self.db)

    def match(self, track_ids: list[int] | None = None):
        asyncio.run(self._match_async(track_ids))

    async def _match_async(self, track_ids: list[int] | None = None):
        if track_ids:
            tracks = [self.db.get_track(tid) for tid in track_ids]
            tracks = [t for t in tracks if t and t["status"] == "extracted"]
        else:
            tracks = self.db.list_tracks(status="extracted", limit=9999)

        if not tracks:
            logger.info("没有待匹配的文件")
            return

        qq = QQMusicMatcher(request_delay=self.config.qq_music.get("request_delay", 0.5))
        threshold = self.config.confidence_threshold

        for track in tracks:
            clues = get_best_clues(track)
            title = clues.get("title", "")
            artist = clues.get("artist")

            if not title:
                self.db.update_status(track["id"], "failed", "无法提取歌曲标题")
                continue

            result = await qq.search(title=title, artist=artist, limit=self.config.search_limit)

            if result and result.confidence >= threshold:
                self.db.set_matched(
                    track["id"],
                    source=result.source,
                    confidence=result.confidence,
                    matched_title=result.title,
                    matched_artist=result.artist,
                    matched_album=result.album,
                    matched_year=result.year,
                    matched_song_id=result.song_id,
                    matched_album_id=result.album_id,
                    cover_url=result.cover_url,
                    lyrics_source=result.source if result.lrc_lyrics else None,
                )
                # 暂存歌词到数据库
                if result.lrc_lyrics:
                    self.db.update_track(track["id"], lrc_content=result.lrc_lyrics)
                logger.info("匹配成功: %s → %s - %s (%.2f)",
                            Path(track["file_path"]).name,
                            result.artist, result.title, result.confidence)
            elif result:
                self.db.update_status(
                    track["id"], "pending_review",
                    f"低置信度 ({result.confidence:.2f}): {result.artist} - {result.title}",
                )
                logger.info("低置信度: %s → %s - %s (%.2f)",
                            Path(track["file_path"]).name,
                            result.artist, result.title, result.confidence)
            else:
                self.db.update_status(track["id"], "failed", "QQ音乐未找到匹配")

    def tag(self, track_ids: list[int] | None = None):
        asyncio.run(self._tag_async(track_ids))

    async def _tag_async(self, track_ids: list[int] | None = None):
        if track_ids:
            tracks = [self.db.get_track(tid) for tid in track_ids]
            tracks = [t for t in tracks if t and t["status"] == "matched"]
        else:
            tracks = self.db.list_tracks(status="matched", limit=9999)

        if not tracks:
            logger.info("没有待标签的文件")
            return

        overwrite = self.config.tagging.get("overwrite", True)

        for track in tracks:
            filepath = Path(track["file_path"])
            if not filepath.exists():
                self.db.update_status(track["id"], "failed", f"文件不存在: {filepath}")
                continue

            from .matcher import MatchResult
            match = MatchResult(
                source=track["matched_source"] or "",
                title=track["matched_title"] or "",
                artist=track["matched_artist"] or "",
                album=track["matched_album"] or "",
                year=track["matched_year"] or "",
                song_id=track["matched_song_id"] or "",
                album_id=track["matched_album_id"] or "",
                confidence=track["match_confidence"] or 0.0,
                cover_url=track.get("cover_url") or "",
            )

            # 恢复歌词
            lrc_content = track.get("lrc_content") or ""
            match.lrc_lyrics = lrc_content
            # 从 LRC 提取纯文本歌词用于内嵌
            if lrc_content:
                import re
                lines = []
                for line in lrc_content.splitlines():
                    cleaned = re.sub(r"\[[\d:.]+\]", "", line).strip()
                    if cleaned and not cleaned.startswith("["):
                        lines.append(cleaned)
                match.lyrics = "\n".join(lines)

            # 下载封面
            cover_data = await download_cover(match.cover_url)

            try:
                written = write_tags(filepath, match, cover_data, overwrite)
                # 保存 LRC 文件
                if match.lrc_lyrics:
                    save_lrc_file(filepath, match.lrc_lyrics, overwrite=overwrite)

                self.db.set_tagged(track["id"], written)
                logger.info("标签完成: %s → %s", filepath.name, written)
            except Exception as e:
                self.db.update_status(track["id"], "failed", f"标签写入失败: {e}")

    def rename(self, track_ids: list[int] | None = None):
        if track_ids:
            tracks = [self.db.get_track(tid) for tid in track_ids]
            tracks = [t for t in tracks if t and t["status"] == "tagged"]
        else:
            tracks = self.db.list_tracks(status="tagged", limit=9999)

        for track in tracks:
            rename_track(track, self.db)

    def organize(self, track_ids: list[int] | None = None):
        if track_ids:
            tracks = [self.db.get_track(tid) for tid in track_ids]
            tracks = [t for t in tracks if t and t["status"] == "renamed"]
        else:
            tracks = self.db.list_tracks(status="renamed", limit=9999)

        for track in tracks:
            organize_track(
                track,
                self.config.organized_dir,
                self.config.organize_pattern,
                self.db,
            )

    def run(self):
        """一键执行完整流程"""
        logger.info("=== 开始处理 ===")

        # Step 1: 扫描
        new_ids = self.scan()
        if not new_ids:
            logger.info("没有发现新文件")
            return

        # Step 2: 提取
        self.extract(new_ids)

        # Step 3: 匹配
        self.match()

        # Step 4: 标签
        self.tag()

        # Step 5: 重命名
        self.rename()

        # Step 6: 归类
        self.organize()

        # 报告
        stats = self.db.count_by_status()
        logger.info("=== 处理完成 === %s", stats)

    def status(self) -> dict:
        return self.db.count_by_status()
