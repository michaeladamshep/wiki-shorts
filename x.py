"""X (Twitter) via API v2: chunked media upload, then a post with the video attached.

Needs an X developer app on a tier that allows posting and media upload, plus an OAuth 2.0
user access token with `tweet.write`, `users.read` and `media.write` scopes in X_ACCESS_TOKEN.
"""

from __future__ import annotations

import time

import httpx

from .base import Post, Publisher

API = "https://api.x.com/2"
CHUNK = 4 * 1024 * 1024


class X(Publisher):
    name = "x"
    account_vars = ("X_ACCESS_TOKEN",)

    def _text(self, post: Post) -> str:
        return f"{post.x_post}\n\n{post.tags(3)}"[:280]

    def preview(self, post: Post) -> dict:
        return {"text": self._text(post)}

    def publish(self, post: Post) -> str:
        auth = {"Authorization": f"Bearer {self.var('X_ACCESS_TOKEN')}"}
        size = post.video.stat().st_size
        init = httpx.post(f"{API}/media/upload/initialize", headers=auth, json={
            "media_type": "video/mp4", "total_bytes": size, "media_category": "amplify_video"})
        init.raise_for_status()
        media_id = init.json()["data"]["id"]

        with open(post.video, "rb") as f:
            index = 0
            while chunk := f.read(CHUNK):
                r = httpx.post(f"{API}/media/upload/{media_id}/append", headers=auth,
                               data={"segment_index": str(index)},
                               files={"media": ("chunk", chunk, "application/octet-stream")},
                               timeout=300)
                r.raise_for_status()
                index += 1

        final = httpx.post(f"{API}/media/upload/{media_id}/finalize", headers=auth)
        final.raise_for_status()
        info = final.json()["data"].get("processing_info")
        while info and info.get("state") in ("pending", "in_progress"):
            time.sleep(info.get("check_after_secs", 5))
            s = httpx.get(f"{API}/media/upload", headers=auth,
                          params={"command": "STATUS", "media_id": media_id})
            s.raise_for_status()
            info = s.json()["data"].get("processing_info")
        if info and info.get("state") == "failed":
            raise RuntimeError(f"X media processing failed: {info}")

        tweet = httpx.post(f"{API}/tweets", headers=auth,
                           json={"text": self._text(post), "media": {"media_ids": [media_id]}})
        tweet.raise_for_status()
        return f"https://x.com/i/status/{tweet.json()['data']['id']}"
