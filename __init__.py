"""Platform registry: each platform posts natively unless PUBLISH_<NAME>=aggregator."""

from __future__ import annotations

import os

from .aggregator import Aggregator
from ..languages import LANGUAGES, Lang
from .base import Post, Publisher
from .meta import Facebook, Instagram
from .tiktok import TikTok
from .x import X
from .youtube import YouTube

NATIVE = {"youtube": YouTube, "tiktok": TikTok, "instagram": Instagram, "facebook": Facebook,
          "x": X}
PLATFORMS = list(NATIVE)


def publisher(platform: str, lang: Lang = LANGUAGES["en"]) -> Publisher:
    key = f"PUBLISH_{platform.upper()}"
    if os.getenv(key + lang.suffix, os.getenv(key, "native")).lower() == "aggregator":
        return Aggregator(platform, lang)
    return NATIVE[platform](lang)


__all__ = ["PLATFORMS", "Post", "Publisher", "publisher"]
