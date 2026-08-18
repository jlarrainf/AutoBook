from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class BrowserConfig:
    headless: bool = False
    user_data_dir: str = ".chrome-profile"
    timeout_ms: int = 60000
    cdp_port: int = 9333
    binary: str | None = None


@dataclass
class BehaviorConfig:
    request_delay_min: float = 2.0
    request_delay_max: float = 6.0
    slow_download_poll_interval: int = 15
    slow_download_timeout_min: int = 15
    challenge_timeout_s: float = 180.0


@dataclass
class FileConfig:
    layout: str = "author_title"
    overwrite: bool = False


@dataclass
class Config:
    mirrors: list[str] = field(default_factory=list)
    default_language: str = "es"
    default_format: str = "epub"
    download_dir: Path = Path("downloads")
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    files: FileConfig = field(default_factory=FileConfig)

    @classmethod
    def load(cls, base_dir: Path | None = None) -> "Config":
        base_dir = base_dir or Path(__file__).resolve().parent.parent
        load_dotenv(base_dir / ".env")
        raw: dict = {}
        cfg_file = base_dir / "config.yaml"
        if cfg_file.exists():
            raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}

        cfg = cls(
            mirrors=raw.get("mirrors") or ["https://annas-archive.gl"],
            default_language=raw.get("defaults", {}).get("language", "es"),
            default_format=raw.get("defaults", {}).get("format", "epub"),
            download_dir=Path(raw.get("download_dir", "downloads")),
            browser=BrowserConfig(**raw.get("browser", {})),
            behavior=BehaviorConfig(**raw.get("behavior", {})),
            files=FileConfig(**raw.get("files", {})),
        )
        cfg._apply_env(base_dir)
        return cfg

    def _apply_env(self, base_dir: Path) -> None:
        env_dir = os.getenv("DOWNLOAD_DIR")
        if env_dir:
            self.download_dir = Path(env_dir)
        mirror = os.getenv("ANNAS_MIRROR")
        if mirror:
            self.mirrors.insert(0, mirror)
        lang = os.getenv("DEFAULT_LANGUAGE")
        if lang:
            self.default_language = lang
        fmt = os.getenv("DEFAULT_FORMAT")
        if fmt:
            self.default_format = fmt
        headless = os.getenv("HEADLESS")
        if headless is not None:
            self.browser.headless = headless.lower() in ("1", "true", "yes")
        binary = os.getenv("BROWSER_BINARY")
        if binary:
            self.browser.binary = binary

        if not self.download_dir.is_absolute():
            self.download_dir = (base_dir / self.download_dir).resolve()