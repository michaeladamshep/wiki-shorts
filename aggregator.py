"""Fallback: post through Upload-Post (upload-post.com), one API key for every platform.

Use this for any platform whose native developer app isn't approved yet: set
PUBLISH_<PLATFORM>=aggregator in .env (e.g. PUBLISH_TIKTOK=aggregator). Connect your social
accounts in the Upload-Post dashboard under a profile name (UPLOAD_POST_USER). Each language
needs its own profile holding that language's accounts (UPLOAD_POST_USER_ES, ...).
"""

from __future__ import annotations

import httpx

from ..config import env
from ..languages import LANGUAGES, Lang
from .base import Post, Publisher

URL = "https://api.upload-post.com/api/upload"
PLATFORM_NAMES = {"youtube": "youtube", "tiktok": "tiktok", "instagram": "instagram",
                  "facebook": "facebook", "x": "x"}


class Aggregator(Publisher):
    account_vars = ("UPLOAD_POST_USER",)

    def __init__(self, platform: str, lang: Lang = LANGUAGES["en"]) -> None:
        super().__init__(lang)
        self.platform = platform
        self.name = f"{platform} (via upload-post)"

    def publish(self, post: Post) -> str:
        caption = post.long_caption() if self.platform in ("youtube", "facebook") else post.short_caption()
        data = {"user": self.var("UPLOAD_POST_USER"), "title": post.title,
                "description": caption, "platform[]": PLATFORM_NAMES[self.platform]}
        if self.platform == "x":
            data["title"] = f"{post.x_post}\n\n{post.tags(3)}"[:280]
        with open(post.video, "rb") as f:
            r = httpx.post(URL, headers={"Authorization": f"Apikey {env('UPLOAD_POST_API_KEY')}"},
                           data=data, files={"video": ("final.mp4", f, "video/mp4")}, timeout=900)
        if r.status_code >= 400:
            raise RuntimeError(f"Upload-Post {r.status_code}: {r.text[:500]}")
        result = r.json()
        return str(result.get("results", {}).get(self.platform, {}).get("url") or result)
