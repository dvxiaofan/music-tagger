"""匹配器基类"""

from dataclasses import dataclass, field


@dataclass
class MatchResult:
    source: str
    title: str = ""
    artist: str = ""
    album: str = ""
    year: str = ""
    song_id: str = ""
    album_id: str = ""
    confidence: float = 0.0
    cover_url: str = ""
    lyrics: str = ""          # 原始歌词文本
    lrc_lyrics: str = ""      # LRC 格式歌词


class BaseMatcher:
    name: str = "base"

    async def search(self, title: str, artist: str = None, album: str = None,
                     limit: int = 5) -> MatchResult | None:
        raise NotImplementedError
