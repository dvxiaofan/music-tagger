"""歌词模块 - 歌词获取与 LRC 文件生成"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def save_lrc_file(filepath: Path, lrc_content: str) -> bool:
    """
    保存 LRC 歌词文件。
    filepath: 音频文件路径（自动替换扩展名为 .lrc）
    """
    if not lrc_content or not lrc_content.strip():
        return False

    lrc_path = filepath.with_suffix(".lrc")

    # 如果已有 LRC 文件，不覆盖
    if lrc_path.exists():
        logger.info("LRC 文件已存在，跳过: %s", lrc_path.name)
        return False

    try:
        lrc_path.write_text(lrc_content, encoding="utf-8")
        logger.info("LRC 文件已保存: %s", lrc_path.name)
        return True
    except Exception as e:
        logger.error("保存 LRC 失败 %s: %s", lrc_path.name, e)
        return False
