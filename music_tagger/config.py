"""配置管理模块"""

from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config(config_path: str | Path | None = None) -> dict:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Config:
    def __init__(self, config_path: str | Path | None = None):
        self._data = load_config(config_path)

    @property
    def watch_dir(self) -> Path:
        return Path(self._data["paths"]["watch_dir"])

    @property
    def organized_dir(self) -> Path:
        return Path(self._data["paths"]["organized_dir"])

    @property
    def db_path(self) -> Path:
        return Path(self._data["paths"]["db_path"])

    @property
    def log_path(self) -> Path:
        return Path(self._data["paths"]["log_path"])

    @property
    def match_sources(self) -> list[str]:
        return self._data["matching"]["sources"]

    @property
    def confidence_threshold(self) -> float:
        return self._data["matching"]["confidence_threshold"]

    @property
    def search_limit(self) -> int:
        return self._data["matching"]["search_limit"]

    @property
    def tagging(self) -> dict:
        return self._data["tagging"]

    @property
    def rename_pattern(self) -> str:
        return self._data["rename"]["pattern"]

    @property
    def organize_pattern(self) -> str:
        return self._data["rename"]["organize_pattern"]

    @property
    def qq_music(self) -> dict:
        return self._data.get("qq_music", {})

    @property
    def netease(self) -> dict:
        return self._data.get("netease", {})

    @property
    def acoustid(self) -> dict:
        return self._data.get("acoustid", {})

    def get(self, key: str, default=None):
        return self._data.get(key, default)
