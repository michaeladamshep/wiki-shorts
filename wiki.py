"""Thin client for the MediaWiki Action API and Wikimedia REST API."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import httpx

from .config import USER_AGENT

API = "https://en.wikipedia.org/w/api.php"
_client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)

FREE_LICENSE = re.compile(r"^(cc0|public domain|pd|cc by(-sa)?( \d\.\d)?)", re.I)


def api(**params: Any) -> dict:
    params = {"format": "json", "formatversion": 2, **params}
    r = _client.get(API, params=params)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"MediaWiki error: {data['error']}")
    return data


def page_links(title: str) -> list[str]:
    """All article-namespace links on a page (e.g. Wikipedia:Unusual articles)."""
    titles: list[str] = []
    params: dict[str, Any] = {"action": "query", "titles": title, "prop": "links",
                              "plnamespace": 0, "pllimit": "max"}
    while True:
        data = api(**params)
        for page in data["query"]["pages"]:
            titles += [link["title"] for link in page.get("links", [])]
        if "continue" not in data:
            return titles
        params.update(data["continue"])


def top_viewed(days_ago: int = 2, limit: int = 200) -> list[str]:
    day = date.today() - timedelta(days=days_ago)
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/"
           f"{day:%Y/%m/%d}")
    r = _client.get(url)
    r.raise_for_status()
    skip = ("Main_Page", "Special:", "Wikipedia:", "Portal:", "File:", "Help:", "-")
    articles = r.json()["items"][0]["articles"]
    return [a["article"].replace("_", " ") for a in articles
            if not a["article"].startswith(skip)][:limit]


def summaries(titles: list[str]) -> list[dict]:
    """Intro extract + byte length for up to 20 titles per call (the extracts intro limit)."""
    out: list[dict] = []
    for i in range(0, len(titles), 20):
        data = api(action="query", titles="|".join(titles[i:i + 20]), prop="info|extracts",
                   exintro=1, explaintext=1, exlimit="max", redirects=1)
        for page in data["query"]["pages"]:
            if page.get("missing") or not page.get("extract"):
                continue
            out.append({"title": page["title"], "length": page.get("length", 0),
                        "intro": page["extract"]})
    return out


def full_text(title: str) -> tuple[str, str]:
    """Return (canonical title, plain-text article)."""
    data = api(action="query", titles=title, prop="extracts", explaintext=1, redirects=1)
    page = data["query"]["pages"][0]
    if page.get("missing"):
        raise SystemExit(f"Wikipedia has no article titled {title!r}")
    return page["title"], page["extract"]


def local_title(title: str, lang: str) -> str | None:
    """The same article's title on another language's Wikipedia, if it has one."""
    data = api(action="query", titles=title, prop="langlinks", lllang=lang, redirects=1)
    links = data["query"]["pages"][0].get("langlinks", [])
    return links[0]["title"] if links else None


def free_images(title: str, max_images: int = 25) -> list[dict]:
    """Freely licensed raster images used in an article, with attribution metadata."""
    data = api(action="query", titles=title, generator="images", gimlimit="max",
               prop="imageinfo", iiprop="url|size|mime|extmetadata", iiurlwidth=1600,
               redirects=1)
    images = []
    for page in data.get("query", {}).get("pages", []):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        license_name = meta.get("LicenseShortName", {}).get("value", "")
        if info.get("mime") not in ("image/jpeg", "image/png"):
            continue  # skips SVG icons, maps-as-SVG, audio, video
        if min(info.get("width", 0), info.get("height", 0)) < 500:
            continue
        if not FREE_LICENSE.match(license_name.strip()):
            continue
        artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "Unknown")).strip()
        images.append({
            "file": page["title"],
            "url": info.get("thumburl") or info["url"],
            "page_url": info.get("descriptionurl", ""),
            "description": re.sub(r"<[^>]+>", "",
                                  meta.get("ImageDescription", {}).get("value", ""))[:200],
            "artist": artist,
            "license": license_name,
        })
    return images[:max_images]


def download(url: str, dest) -> None:
    with _client.stream("GET", url) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
