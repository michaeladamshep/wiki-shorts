"""Common publisher interface and per-platform caption formatting."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import env
from ..languages import LANGUAGES, Lang


@dataclass
class Post:
    video: Path
    thumb: Path
    title: str
    description: str
    hashtags: list[str]
    x_post: str
    source_url: str
    credits: list[dict] = field(default_factory=list)
    lang: Lang = LANGUAGES["en"]
    publish_at: datetime | None = None  # YouTube only: release at this time instead of now

    def tags(self, limit: int = 8) -> str:
        return " ".join(f"#{t.lstrip('#').replace(' ', '')}" for t in self.hashtags[:limit])

    def credit_lines(self) -> str:
        label = {"source": "Source", "image": "Image", "video": "Stock footage", **self.lang.labels}
        lines = [f"{label['source']}: {self.source_url} (CC BY-SA 4.0)"]
        for c in self.credits:
            if c["kind"] == "image":
                lines.append(f"{label['image']}: {c['title']} by {c['author']}, {c['license']} ({c['url']})")
        if any(c["kind"] == "video" for c in self.credits):
            lines.append(f"{label['video']}: Pexels")
        return "\n".join(lines)

    def long_caption(self) -> str:
        """YouTube / Facebook: room for attribution."""
        return f"{self.description}\n\n{self.tags()}\n\n{self.credit_lines()}"

    def short_caption(self, limit: int = 2200) -> str:
        """TikTok / Instagram: keep the hook text up front, credits below."""
        text = f"{self.title}\n\n{self.description}\n\n{self.tags()}\n\n{self.credit_lines()}"
        return text[:limit]


class Publisher:
    """Posts to one language's account on one platform.

    Account settings are per language: TIKTOK_ACCESS_TOKEN is the English account,
    TIKTOK_ACCESS_TOKEN_ES the Spanish one. A translation never falls back to the English
    account, because that would show it to the wrong audience.
    """

    name = "base"
    account_vars: tuple[str, ...] = ()  # settings that identify the account, suffixed per language

    def __init__(self, lang: Lang = LANGUAGES["en"]) -> None:
        self.lang = lang

    def var(self, name: str) -> str:
        return env(f"{name}{self.lang.suffix}")

    def missing(self) -> list[str]:
        """Account settings this language hasn't filled in yet ([] = ready to post)."""
        return [f"{n}{self.lang.suffix}" for n in self.account_vars
                if not os.getenv(f"{n}{self.lang.suffix}", "").strip()]

    def publish(self, post: Post) -> str:
        """Upload the video and return the public URL (or the platform's post id)."""
        raise NotImplementedError

    def preview(self, post: Post) -> dict:
        """What would be sent, for --dry-run."""
        return {"caption": post.short_caption()}
