"""TikTok via the Content Posting API (Direct Post).

Needs a TikTok developer app with the `video.publish` scope and a user access token in
TIKTOK_ACCESS_TOKEN. Until the app passes TikTok's audit, posts can only be SELF_ONLY (private).
Access tokens expire after 24h; refresh them with the refresh token (see README).
"""

from __future__ import annotations

import os
import time

import httpx

from .base import Post, Publisher

API = "https://open.tiktokapis.com/v2"


class TikTok(Publisher):
    name = "tiktok"
    account_vars = ("TIKTOK_ACCESS_TOKEN",)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.var('TIKTOK_ACCESS_TOKEN')}",
                "Content-Type": "application/json; charset=UTF-8"}

    def _privacy(self) -> str:
        r = httpx.post(f"{API}/post/publish/creator_info/query/", headers=self._headers())
        r.raise_for_status()
        options = r.json()["data"]["privacy_level_options"]
        wanted = os.getenv("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE")
        return wanted if wanted in options else options[-1]

    def preview(self, post: Post) -> dict:
        return {"title": post.short_caption(2200)}

    def publish(self, post: Post) -> str:
        size = post.video.stat().st_size
        r = httpx.post(f"{API}/post/publish/video/init/", headers=self._headers(), json={
            "post_info": {"title": post.short_caption(2200), "privacy_level": self._privacy(),
                          "disable_comment": False, "disable_duet": False,
                          "disable_stitch": False, "is_aigc": True},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size,
                            "total_chunk_count": 1},
        })
        r.raise_for_status()
        data = r.json()["data"]
        upload = httpx.put(data["upload_url"], content=post.video.read_bytes(), timeout=600,
                           headers={"Content-Type": "video/mp4",
                                    "Content-Range": f"bytes 0-{size - 1}/{size}"})
        upload.raise_for_status()

        for _ in range(60):
            s = httpx.post(f"{API}/post/publish/status/fetch/", headers=self._headers(),
                           json={"publish_id": data["publish_id"]})
            s.raise_for_status()
            status = s.json()["data"]
            if status["status"] == "PUBLISH_COMPLETE":
                ids = status.get("publicaly_available_post_id") or []  # sic: TikTok's spelling
                return f"https://www.tiktok.com/video/{ids[0]}" if ids else data["publish_id"]
            if status["status"] == "FAILED":
                raise RuntimeError(f"TikTok publish failed: {status.get('fail_reason')}")
            time.sleep(5)
        return data["publish_id"]
