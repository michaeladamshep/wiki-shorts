"""Stage 4: plan a shot list and download Wikimedia images + Pexels clips for it."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import wiki
from .config import SHOT_SECONDS, env

PEXELS_URL = "https://api.pexels.com/videos/search"


class Pexels:
    def __init__(self, key: str) -> None:
        self.http = httpx.Client(headers={"Authorization": key}, timeout=60,
                                 follow_redirects=True)
        self.used: set[int] = set()
        self.cache: dict[str, list[dict]] = {}

    def search(self, query: str) -> list[dict]:
        if query not in self.cache:
            r = self.http.get(PEXELS_URL, params={"query": query, "orientation": "portrait",
                                                  "size": "medium", "per_page": 15})
            r.raise_for_status()
            self.cache[query] = r.json().get("videos", [])
        return self.cache[query]

    def next_clip(self, query: str, min_seconds: float) -> dict | None:
        for video in self.search(query):
            if video["id"] in self.used or video.get("duration", 0) < min_seconds:
                continue
            files = [f for f in video["video_files"]
                     if f.get("height") and f.get("width") and f["height"] >= 1280
                     and f["height"] > f["width"] and f.get("file_type") == "video/mp4"]
            if not files:
                continue
            best = min(files, key=lambda f: abs(f["height"] - 1920))
            self.used.add(video["id"])
            return {"id": video["id"], "link": best["link"], "url": video["url"],
                    "author": video.get("user", {}).get("name", "Pexels")}
        return None


def _download(url: str, folder: Path, suffix: str) -> Path:
    path = folder / (hashlib.sha1(url.encode()).hexdigest()[:12] + suffix)
    if not path.exists():
        wiki.download(url, path)
    return path


def build(sections: list[dict], images: list[dict], out_dir: Path) -> tuple[list[dict], list[dict]]:
    """Return (shots, credits).

    `sections` are [{start, end, visual_query, wiki_image}] in speaking order. Each section is
    split into ~SHOT_SECONDS shots that alternate between article images and stock clips, so the
    picture changes every few seconds (the main lever for holding attention after the hook).
    """
    assets = out_dir / "assets"
    assets.mkdir(exist_ok=True)
    # Pexels is optional (new key issuance was paused in Oct 2026): without a key, use images only.
    key = env("PEXELS_API_KEY", required=False)
    pexels = Pexels(key) if key else None
    if pexels is None:
        print("No PEXELS_API_KEY set: using article images only, no stock clips.")
    by_file = {i["file"]: i for i in images}
    unused_images = list(images)
    shots: list[dict] = []
    credits: dict[str, dict] = {}

    def take_image(preferred: str = "") -> dict | None:
        img = by_file.get(preferred) if preferred else None
        if img is None and unused_images:
            img = unused_images[0]
        if img is None and images:
            # Pool exhausted: cycle through the images rather than repeating the last shot.
            img = images[len(shots) % len(images)]
        if img is None:
            return None
        if img in unused_images:
            unused_images.remove(img)
        credits[img["file"]] = {"kind": "image", "title": img["file"].removeprefix("File:"),
                                "author": img["artist"], "license": img["license"],
                                "url": img["page_url"]}
        suffix = Path(urlparse(img["url"]).path).suffix or ".jpg"
        return {"type": "image", "path": str(_download(img["url"], assets, suffix))}

    def take_clip(query: str, seconds: float) -> dict | None:
        clip = pexels.next_clip(query, seconds) if pexels else None
        if clip is None:
            return None
        credits[f"pexels-{clip['id']}"] = {"kind": "video", "title": "Pexels video",
                                           "author": clip["author"], "license": "Pexels License",
                                           "url": clip["url"]}
        return {"type": "video", "path": str(_download(clip["link"], assets, ".mp4"))}

    for index, section in enumerate(sections):
        duration = section["end"] - section["start"]
        # The hook gets quicker cuts to earn the first two seconds.
        target = SHOT_SECONDS * (0.55 if index == 0 else 1)
        count = max(2 if index == 0 else 1, round(duration / target))
        length = duration / count
        preferred = section["wiki_image"]
        for k in range(count):
            shot = None
            if len(shots) % 2 == 0:  # alternate image / clip across the whole video
                shot = take_image(preferred)
                preferred = ""
            shot = shot or take_clip(section["visual_query"], length) or take_image()
            if shot is None:
                shot = shots[-1].copy() if shots else None
            if shot is None:
                raise SystemExit("No usable images or clips found for this topic.")
            shot.update(start=section["start"] + k * length, duration=length)
            shots.append(shot)
    return shots, list(credits.values())
