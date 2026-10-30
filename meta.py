"""Instagram Reels and Facebook Page Reels via the Meta Graph API, using resumable uploads.

Needs a Meta app with `instagram_content_publish`, `instagram_basic`, `pages_manage_posts`,
`pages_read_engagement` and `pages_show_list`; an Instagram Business/Creator account linked to a
Facebook Page; and a long-lived Page access token (META_PAGE_TOKEN), the Page id (META_PAGE_ID)
and the IG user id (META_IG_USER_ID).
"""

from __future__ import annotations

import os
import time

import httpx

from .base import Post, Publisher

VERSION = os.getenv("META_GRAPH_VERSION", "v23.0")
GRAPH = f"https://graph.facebook.com/{VERSION}"
RUPLOAD = "https://rupload.facebook.com"


def _check(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        raise RuntimeError(f"Meta API {r.status_code}: {r.text[:500]}")
    return r.json()


def _upload(url: str, post: Post, token: str) -> None:
    _check(httpx.post(url, content=post.video.read_bytes(), timeout=600, headers={
        "Authorization": f"OAuth {token}", "offset": "0",
        "file_size": str(post.video.stat().st_size)}))


class Instagram(Publisher):
    name = "instagram"
    account_vars = ("META_PAGE_TOKEN", "META_IG_USER_ID")

    def publish(self, post: Post) -> str:
        token, ig = self.var("META_PAGE_TOKEN"), self.var("META_IG_USER_ID")
        container = _check(httpx.post(f"{GRAPH}/{ig}/media", data={
            "media_type": "REELS", "upload_type": "resumable", "caption": post.short_caption(2200),
            "share_to_feed": "true", "access_token": token}))
        _upload(f"{RUPLOAD}/ig-api-upload/{VERSION}/{container['id']}", post, token)

        for _ in range(60):
            status = _check(httpx.get(f"{GRAPH}/{container['id']}",
                                      params={"fields": "status_code,status",
                                              "access_token": token}))
            if status["status_code"] == "FINISHED":
                break
            if status["status_code"] == "ERROR":
                raise RuntimeError(f"Instagram processing failed: {status.get('status')}")
            time.sleep(5)
        else:
            raise RuntimeError("Instagram processing timed out")

        media = _check(httpx.post(f"{GRAPH}/{ig}/media_publish",
                                  data={"creation_id": container["id"], "access_token": token}))
        info = _check(httpx.get(f"{GRAPH}/{media['id']}",
                                params={"fields": "permalink", "access_token": token}))
        return info.get("permalink", media["id"])


class Facebook(Publisher):
    name = "facebook"
    account_vars = ("META_PAGE_TOKEN", "META_PAGE_ID")

    def preview(self, post: Post) -> dict:
        return {"description": post.long_caption()}

    def publish(self, post: Post) -> str:
        token, page = self.var("META_PAGE_TOKEN"), self.var("META_PAGE_ID")
        start = _check(httpx.post(f"{GRAPH}/{page}/video_reels",
                                  data={"upload_phase": "start", "access_token": token}))
        _upload(f"{RUPLOAD}/video-upload/{VERSION}/{start['video_id']}", post, token)
        _check(httpx.post(f"{GRAPH}/{page}/video_reels", data={
            "upload_phase": "finish", "video_id": start["video_id"], "video_state": "PUBLISHED",
            "description": post.long_caption(), "title": post.title, "access_token": token}))
        return f"https://www.facebook.com/reel/{start['video_id']}"
