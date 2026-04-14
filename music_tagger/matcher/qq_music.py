"""QQ音乐匹配器 - 主力搜索源"""

import asyncio
import base64
import logging
import re

import httpx
from thefuzz import fuzz

from . import BaseMatcher, MatchResult

logger = logging.getLogger(__name__)

SEARCH_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
COVER_URL_TEMPLATE = "https://y.qq.com/music/photo_new/T002R500x500M000{album_mid}.jpg"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://y.qq.com/",
    "Origin": "https://y.qq.com",
}


class QQMusicMatcher(BaseMatcher):
    name = "qq_music"

    def __init__(self, request_delay: float = 0.5):
        self.request_delay = request_delay

    async def search(self, title: str, artist: str = None, album: str = None,
                     limit: int = 5) -> MatchResult | None:
        keyword = f"{artist} {title}" if artist else title
        keyword = keyword.strip()

        if not keyword:
            return None

        try:
            songs = await self._search_songs(keyword, limit)
        except Exception as e:
            logger.error("QQ音乐搜索失败 [%s]: %s", keyword, e)
            return None

        if not songs:
            logger.info("QQ音乐未找到: %s", keyword)
            return None

        best = self._pick_best(songs, title, artist)
        if not best:
            return None

        result = self._build_result(best)

        # 获取歌词
        await asyncio.sleep(self.request_delay)
        try:
            lyrics_data = await self._fetch_lyrics(best["mid"])
            if lyrics_data:
                result.lrc_lyrics = lyrics_data.get("lrc", "")
                result.lyrics = _strip_lrc_tags(lyrics_data.get("lrc", ""))
        except Exception as e:
            logger.warning("QQ音乐歌词获取失败 [%s]: %s", best.get("name", ""), e)

        return result

    async def _search_songs(self, keyword: str, limit: int) -> list[dict]:
        payload = {
            "comm": {"ct": 19, "cv": 1859},
            "req_1": {
                "method": "DoSearchForQQMusicDesktop",
                "module": "music.search.SearchCgiService",
                "param": {
                    "query": keyword,
                    "num_per_page": limit,
                    "page_num": 1,
                    "search_type": 0,
                },
            },
        }

        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            resp = await client.post(SEARCH_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        body = data.get("req_1", {}).get("data", {}).get("body", {})
        song_list = body.get("song", {}).get("list", [])
        return song_list

    def _pick_best(self, songs: list[dict], title: str, artist: str = None) -> dict | None:
        best_song = None
        best_score = 0.0

        for song in songs:
            score = self._calc_confidence(song, title, artist)
            if score > best_score:
                best_score = score
                best_song = song

        if best_song and best_score >= 0.5:
            best_song["_confidence"] = best_score
            return best_song

        return None

    def _calc_confidence(self, song: dict, title: str, artist: str = None) -> float:
        # 新版 API 字段：name/title 均可
        song_title = song.get("name") or song.get("title") or song.get("songname", "")
        song_artists = " ".join(s.get("name", "") for s in song.get("singer", []))

        title_score = fuzz.ratio(title.lower(), song_title.lower()) / 100.0

        if artist:
            artist_score = fuzz.partial_ratio(artist.lower(), song_artists.lower()) / 100.0
            confidence = title_score * 0.6 + artist_score * 0.4
        else:
            confidence = title_score * 0.7

        return round(confidence, 3)

    def _build_result(self, song: dict) -> MatchResult:
        singers = [s.get("name", "") for s in song.get("singer", [])]
        album_info = song.get("album", {})
        album_mid = album_info.get("mid", "")

        song_title = song.get("name") or song.get("title") or song.get("songname", "")
        song_mid = song.get("mid") or song.get("songmid", "")

        return MatchResult(
            source=self.name,
            title=song_title,
            artist=" / ".join(singers) if singers else "",
            album=album_info.get("name", ""),
            year=_extract_year(song.get("time_public", "")),
            song_id=song_mid,
            album_id=album_mid,
            confidence=song.get("_confidence", 0.0),
            cover_url=COVER_URL_TEMPLATE.format(album_mid=album_mid) if album_mid else "",
        )

    async def _fetch_lyrics(self, songmid: str) -> dict | None:
        """获取歌词（LRC 格式）"""
        payload = {
            "comm": {"ct": 19, "cv": 1859},
            "req_1": {
                "module": "music.musichallSong.PlayLyricInfo",
                "method": "GetPlayLyricInfo",
                "param": {
                    "songMID": songmid,
                    "songID": 0,
                },
            },
        }

        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            resp = await client.post(SEARCH_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        lyric_data = data.get("req_1", {}).get("data", {})
        lrc = lyric_data.get("lyric", "")

        if lrc:
            try:
                lrc = base64.b64decode(lrc).decode("utf-8")
            except Exception:
                pass

        return {"lrc": lrc} if lrc else None


def _extract_year(time_str: str) -> str:
    if not time_str:
        return ""
    m = re.match(r"(\d{4})", time_str)
    return m.group(1) if m else ""


def _strip_lrc_tags(lrc_text: str) -> str:
    """去掉 LRC 时间标签，只保留纯文本歌词"""
    lines = []
    for line in lrc_text.splitlines():
        cleaned = re.sub(r"\[[\d:.]+\]", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)
